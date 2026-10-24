"""One application service over the SQLite ledger and real v3 evaluator.

Demo commands author explicitly synthetic operator claims, never verdicts or
trusted verification. Read models are derived from verified ledger snapshots.
No fixture oracle/ground-truth or test helper is imported here.
"""
import copy
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integration"))
from pramaan_integration import Ledger, LedgerBlocked, ValidationFailure, encode_document
from pramaan_integration.profile import digest
from pramaan_integration import engine_bridge
from .audit import Audit
from . import lot_identity as lots
from . import registry_binding

DEFAULT_LOT_REGISTRY = None   # set by the server entry point (--lot-registry); None = bundled synthetic registry

RECALL_ID = "RC-026-014"
PART = "BR-6205"
ROLES = {
    "MES": ("MES-SYSTEM", ["WORK_ORDER_OPENED", "WORK_ORDER_CLOSED"]),
    "ASSY": ("OP-ASSEMBLY-07", ["COMPONENT_INSTALLED"]),
    "REWORK": ("OP-REWORK-12", ["COMPONENT_REMOVED", "COMPONENT_INSTALLED"]),
    "QA": ("QA-INDEPENDENT-03", ["SLOT_STATE_VERIFIED", "SLOT_ACCESS_EVIDENCE", "INSPECTION_RECORDED"]),
    "HANDHELD": ("OP-OBSERVATION-21", ["SLOT_STATE_VERIFIED"]),
    "MATERIAL": ("SUPPLIER-INTAKE-04", ["MATERIAL_ALLOCATED", "BEARING_MANUFACTURED"]),
    "SHIP": ("DISPATCH-09", ["MOTOR_SHIPPED"]),
}


class ShipmentRefused(ValidationFailure):
    """The ordinary shipment gate refused: no current trusted checkpoint, or no current release eligibility for the motor."""


class Manufacturing:
    def __init__(self, path, *, journal_cache=None, verification_deadline=None, lot_registry=None):
        try:
            given = lot_registry if lot_registry is not None else DEFAULT_LOT_REGISTRY
            self.registry = given if isinstance(given, lots.LotRegistry) else lots.LotRegistry.load(given)
        except lots.RegistryError as exc:
            raise LedgerBlocked(str(exc)) from exc       # fail closed: no registry, no identity, no decisions
        self.ledger = Ledger(path)
        self.db = self.ledger.db
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS app_units(serial TEXT PRIMARY KEY, title TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS app_clock(id INTEGER PRIMARY KEY CHECK(id=1), at TEXT NOT NULL);
        INSERT OR IGNORE INTO app_clock VALUES(1,'2026-10-10T08:00:00Z');
        CREATE TABLE IF NOT EXISTS recall_announcements(version INTEGER PRIMARY KEY, policy TEXT NOT NULL, hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS app_ship_tickets(motor TEXT PRIMARY KEY, fingerprint TEXT NOT NULL);
        """)
        for action in ("UPDATE", "DELETE"):
            self.db.execute(f"CREATE TRIGGER IF NOT EXISTS announcements_no_{action.lower()} BEFORE {action} ON recall_announcements BEGIN SELECT RAISE(ABORT,'immutable recall policy'); END")
        self.db.commit()
        try:
            self.audit = Audit(self.ledger,journal_cache=journal_cache,deadline=verification_deadline)
        except Exception:
            self.ledger.close()
            raise

    def close(self):
        self.ledger.close()

    def tick(self, minimum=None):
        at = self.db.execute("SELECT at FROM app_clock WHERE id=1").fetchone()[0]
        at = max(at, minimum) if minimum else at
        at = (datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ") + timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.db:
            self.db.execute("UPDATE app_clock SET at=? WHERE id=1", (at,))
        return at

    @staticmethod
    def source(role, motor):
        return f"{role}:{motor}"

    def create_unit(self, serial, title="IE3 11 kW electric motor", *, gap=False):
        if not isinstance(serial, str) or not re.fullmatch(r"MTR-[A-Z0-9-]{3,30}", serial):
            raise ValidationFailure("Use a distinct motor serial such as MTR-26006")
        if self.db.execute("SELECT 1 FROM app_units WHERE serial=?", (serial,)).fetchone():
            raise ValidationFailure("Motor serial already exists")
        sources = {self.source(role, serial): dict(streamScope="MOTOR", actors=[actor], eventTypes=kinds)
                   for role, (actor, kinds) in ROLES.items()}
        sessions = [dict(sessionId=f"session:{source}", sourceId=source, authenticated=True,
                         **{"from": "2026-01-01T00:00:00Z", "to": "2027-12-31T23:59:59Z"}) for source in sources]
        if gap:
            s = next(s for s in sessions if s["sourceId"] == self.source("ASSY", serial))
            s["from"] = "2026-10-09T00:00:00Z"
            sessions.append(dict(sessionId=f"old:{serial}", sourceId=s["sourceId"], authenticated=True,
                                 **{"from": "2026-10-01T00:00:00Z", "to": "2026-10-02T00:00:00Z"}))
        coverage = dict(coveragePolicyId=f"MFG-COVERAGE:{serial}:v3", mandatoryCapture=[
            dict(operation="COMPONENT_INSTALLED", sources=[self.source(x, serial) for x in ("ASSY", "REWORK")]),
            dict(operation="COMPONENT_REMOVED", sources=[self.source("REWORK", serial)]),
            dict(operation="WORK_ORDER_*", sources=[self.source("MES", serial)])],
            trustedVerifierSources=[self.source("QA", serial)], slotAttribution=dict(
                version=3, unknownSlotIsCandidate=True, labelAssociationWindowSeconds=60,
                slotLabels=[dict(labelId=f"LABEL:{serial}:{slot}", motorSerial=serial, slot=slot, status="ACTIVE",
                                 provisionedAt="2026-01-01T00:00:00Z", revokedAt=None) for slot in ("DE", "NDE")],
                labelScanSources=[], approvedVerificationMethods=["SERIAL_MARKING_VISUAL", "LOT_LABEL_AND_MARKING_VISUAL"],
                authorizedVerifierActors=[ROLES["QA"][0]], accessEvidenceSources=[self.source("QA", serial)],
                approvedAccessMethods=["STATION_FIXTURE_RECORD"], observationClockSkewSeconds=300,
                trustedTimeSources=[]))
        self.ledger.register_motor(serial, sources=sources, sessions=sessions, coverage=coverage)
        with self.db:
            self.db.execute("INSERT INTO app_units VALUES(?,?)", (serial, str(title)[:200]))
        return serial

    def events(self, motor):
        wm = self.ledger.watermark(motor)
        return self.ledger.snapshot(motor, wm)[0]["events"]

    def event(self, motor, kind, role, payload, *, work_order=None, supersedes=None, occurred=None):
        source = self.source(role, motor)
        wm = self.ledger.watermark(motor)
        at = self.tick()
        event = dict(eventId=f"urn:pramaan:{motor}:{role}:{wm[source]+1}", eventType=kind,
                     schemaVersion=1, motorSerial=motor, sourceId=source, sourceSeq=wm[source]+1,
                     occurredAt=occurred or at, recordedAt=(datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ")+timedelta(seconds=4)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     actorId=ROLES[role][0], timeSource="SYNTHETIC_SIMULATED", evidenceRefs=[f"demo-record:{motor}:{role}:{wm[source]+1}"],
                     workOrderId=work_order, recallId=None, supersedesEventId=supersedes,
                     captureSessionId=f"session:{source}", payload=payload)
        # Three distinct clocks: occurrence, producer record, simulated upstream
        # repository recordTime. SQLite additionally archives local wall-clock receipt.
        repository_time = (datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ")+timedelta(seconds=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
        raw = json.dumps(encode_document([event], repository_time), separators=(",", ":")).encode()
        self.ledger.capture(motor, raw, producer_source=source, expected_sha256=hashlib.sha256(raw).hexdigest())
        return event

    def clock(self):
        return self.db.execute("SELECT at FROM app_clock WHERE id=1").fetchone()[0]

    def lot(self, raw, what, *, dated=True):
        """Resolve a lot to its canonical registered identity BEFORE any event is written; anything else is refused."""
        res = self.registry.resolve(raw, at=self.clock() if dated else None, part=PART)
        if not res.ok:
            raise ValidationFailure(f"{what}: lot identity not established ({res.status}{': ' + res.detail if res.detail else ''})")
        return res.canonical

    def manufacture(self, motor, lot, serial=None):
        entry = self.registry.resolve(lot, at=self.clock(), part=PART).entry
        if entry is None:
            raise ValidationFailure("Lot identity not established")
        allocated = self.event(motor, "MATERIAL_ALLOCATED", "MATERIAL", dict(
            rawMaterialLot=entry.get("rawMaterialLot", "STEEL-" + lot), supplierId=entry["supplierId"], supplierName=entry["supplierName"]))
        return self.event(motor, "BEARING_MANUFACTURED", "MATERIAL", dict(
            rawMaterialLot=allocated["payload"]["rawMaterialLot"], supplierId=allocated["payload"]["supplierId"],
            part=PART, lot=lot, serial=serial, materialEventId=allocated["eventId"]))

    def assemble(self, motor, de_lot, nde_lot, identity="SERIAL"):
        events = self.events(motor)
        if any(e["eventType"] == "WORK_ORDER_OPENED" for e in events):
            raise ValidationFailure("This unit already has assembly evidence; use replacement")
        if identity not in ("LOT", "SERIAL"):
            raise ValidationFailure("Explicit valid DE/NDE bearing lots and identity required")
        de_lot, nde_lot = self.lot(de_lot, "DE lot"), self.lot(nde_lot, "NDE lot")   # all lots validated before the first event is written
        build = f"BUILD-{motor}"
        self.event(motor, "WORK_ORDER_OPENED", "MES", dict(orderType="BUILD", expectedChanges=[dict(slot=s, action="INSTALL") for s in ("DE", "NDE")]), work_order=build)
        for slot, lot in (("DE", de_lot), ("NDE", nde_lot)):
            serial = f"BRG-{motor}-{slot}-01" if identity == "SERIAL" else None
            made = self.manufacture(motor, lot, serial)
            payload = dict(componentType="BEARING", slot=slot, part=PART, lot=lot, identityGranularity=identity, manufacturingEventId=made["eventId"])
            if serial:
                payload["serial"] = serial
            self.event(motor, "COMPONENT_INSTALLED", "ASSY", payload, work_order=build)
        return self.event(motor, "WORK_ORDER_CLOSED", "MES", dict(disposition="COMPLETED"), work_order=build)

    def _shipment(self, motor):
        events = self.events(motor)
        if any(e["eventType"] == "MOTOR_SHIPPED" for e in events):
            raise ValidationFailure("Shipment already recorded")
        closed = next((e for e in events if e["eventType"] == "WORK_ORDER_CLOSED" and e["workOrderId"] == f"BUILD-{motor}"), None)
        if not closed:
            raise ValidationFailure("Completed assembly evidence is required")
        return "MOTOR_SHIPPED", "SHIP", dict(
            shipmentId=f"SHP-26-{motor.removeprefix('MTR-')}", customer="Aster Pump Systems — synthetic customer",
            destination="Coimbatore distribution centre", assemblyEventId=closed["eventId"])

    def record_historical_shipment_fixture(self, motor):
        """Synthetic SETUP only (demo seeding, tests, generators): records a shipment fact with no release check. The ordinary operational API never calls this."""
        return self.event(motor, *self._shipment(motor))

    # Ledger state a shipment ticket is bound to: row counts, newest rowids and the newest event hash of every table the anchor covers except raw captures.
    FINGERPRINT_SQL = "SELECT " + " || '|' || ".join(
        f"(SELECT count(*)||':'||ifnull(max(rowid),0) FROM main.{t})" for t in ("motors", "events", "rejections", "decision_runs", "app_units", "recall_announcements")
    ) + " || '|' || ifnull((SELECT hash FROM main.events ORDER BY ordinal DESC LIMIT 1),'')"

    def ship(self, motor, *, trusted_anchor=None):
        """Ordinary shipment: recorded only while this motor holds a CURRENT trusted checkpoint AND current operational release eligibility.
        The eligibility proof and the single-use ticket are written inside one snapshot transaction; the MOTOR_SHIPPED insert itself is then refused
        by a connection-local trigger unless the ledger is exactly at the state the ticket was issued for (no time-of-check/time-of-use gap)."""
        spec = self._shipment(motor)                       # existing preconditions first, so a refusal here never touches the ledger
        if trusted_anchor is None:
            raise ShipmentRefused("Shipment refused: a trusted checkpoint is required")
        snap = self.snapshot(trusted_anchor=trusted_anchor, ship_ticket=motor)
        if not snap["eligibility"].get(motor, {}).get("currentReleaseEligible"):
            raise ShipmentRefused("Shipment refused: no current trusted checkpoint and release eligibility for this motor")
        guard = "ship_ticket_guard"
        self.db.execute(f"""CREATE TEMP TRIGGER {guard} BEFORE INSERT ON main.events
            WHEN json_extract(NEW.native,'$.eventType')='MOTOR_SHIPPED' AND NOT EXISTS
                 (SELECT 1 FROM main.app_ship_tickets t WHERE t.motor=NEW.motor AND t.fingerprint=({self.FINGERPRINT_SQL}))
            BEGIN SELECT RAISE(IGNORE); END""")
        try:
            event = self.event(motor, *spec)
            if not any(e["eventType"] == "MOTOR_SHIPPED" for e in self.events(motor)):
                raise ShipmentRefused("Shipment not recorded: ledger or checkpoint state changed after eligibility was established")
        finally:
            self.db.execute(f"DROP TRIGGER IF EXISTS temp.{guard}")
            with self.db:
                self.db.execute("DELETE FROM app_ship_tickets WHERE motor=?", (motor,))
        return event

    def announce(self, affected_lot, affected_slots=None):
        affected_lot = self.lot(affected_lot, "Affected lot", dated=False)
        if affected_slots is None:
            slots = ["DE", "NDE"]
        elif not isinstance(affected_slots, list) or not affected_slots or any(type(s) is not str or s not in ("DE", "NDE") for s in affected_slots) or len(set(affected_slots)) != len(affected_slots):
            raise ValidationFailure("Scope must be a nonempty unique list containing DE, NDE or both")
        else:
            slots = sorted(affected_slots, key=("DE", "NDE").index)
        old = self.policy()
        if old and old["affectedLots"] == [affected_lot] and old['affectedSlots'] == slots:
            return old
        if old:
            raise ValidationFailure("This local demonstration supports one immutable recall scope per database; use a new database for another affected lot")
        at = self.tick("2026-10-20T08:00:00Z")
        policy = dict(policyId=RECALL_ID+"/P1", recallId=RECALL_ID, version=(old["version"]+1 if old else 1),
                      announcedAt=at, affectedPart=PART, affectedLots=[affected_lot], affectedSlots=slots,
                      scopeDeclaration="ALL_COMPATIBLE_POSITIONS" if affected_slots is None else "EXPLICIT_POSITIONS",
                      exposureBasis="CURRENT_INSTALLATION", damageInspection=None)
        with self.db:
            self.db.execute("INSERT INTO recall_announcements VALUES(?,?,?)", (policy["version"], json.dumps(policy), digest(policy)))
        return policy

    def policy(self):
        row = self.db.execute("SELECT policy,hash FROM recall_announcements ORDER BY version DESC LIMIT 1").fetchone()
        if not row:
            return None
        policy = json.loads(row["policy"])
        if digest(policy) != row["hash"]:
            raise LedgerBlocked("Recall policy integrity mismatch")
        if 'scopeDeclaration' not in policy:
            raise LedgerBlocked('Legacy recall scope is not attested; historical replay remains available, current clearance requires an explicitly scoped new database')
        return policy

    def replace(self, motor, lot, slot="DE"):
        if slot not in ("DE", "NDE"):
            raise ValidationFailure("Slot must be DE or NDE")
        lot = self.lot(lot, "Replacement lot")
        events = self.events(motor)
        pending = lots.interrupted_operations(events)
        if pending:
            raise ValidationFailure("Interrupted operation " + pending[0]["workOrderId"] + " requires manual reconciliation; no further capture is accepted for this unit")
        ended = {e["payload"].get("endsInstallEventId") for e in events if e["eventType"] == "COMPONENT_REMOVED"}
        corrected = {e["supersedesEventId"] for e in events if e["supersedesEventId"]}
        installs = [e for e in events if e["eventType"] == "COMPONENT_INSTALLED" and e["payload"]["slot"] == slot and e["eventId"] not in ended|corrected]
        if len(installs) != 1:
            raise ValidationFailure(f"No unique recorded {slot} occupant; investigate evidence first")
        old = installs[0]; p = old["payload"]
        wo = f"RW-{motor}-{self.ledger.watermark(motor)[self.source('REWORK',motor)]+1}"
        self.event(motor, "WORK_ORDER_OPENED", "MES", dict(orderType="REWORK", expectedChanges=[dict(slot=slot, action="REPLACE")]), work_order=wo)
        observed = dict(componentType="BEARING", slot=slot, observedPart=p["part"], observedLot=p["lot"], identityGranularity=p["identityGranularity"], endsInstallEventId=old["eventId"])
        if p.get("serial"):
            observed["observedSerial"] = p["serial"]
        self.event(motor, "COMPONENT_REMOVED", "REWORK", observed, work_order=wo)
        serial = f"BRG-{motor}-{slot}-R{len(events)}" if p["identityGranularity"] == "SERIAL" else None
        made = self.manufacture(motor, lot, serial)
        payload = dict(componentType="BEARING", slot=slot, part=PART, lot=lot, identityGranularity=p["identityGranularity"], manufacturingEventId=made["eventId"])
        if serial:
            payload["serial"] = serial
        self.event(motor, "COMPONENT_INSTALLED", "REWORK", payload, work_order=wo)
        return self.event(motor, "WORK_ORDER_CLOSED", "MES", dict(disposition="COMPLETED"), work_order=wo)

    def observe(self, motor, lot, slot="DE"):
        """An operator sighting. ALWAYS an unverified, provisional claim: it never creates a component, lot, registry entry or exclusion.
        A registered lot is recorded canonical. A string the registry cannot establish is preserved raw (identity, source, time) as an UNVERIFIED sighting
        that holds the motor for investigation; it is never evidence of installation or of exclusion."""
        if slot not in ("DE", "NDE"):
            raise ValidationFailure("Slot must be DE or NDE")
        if self.integrity_interrupted(motor):
            raise ValidationFailure("Interrupted operation requires manual reconciliation; no further capture is accepted for this unit")
        if not isinstance(lot, str) or not lot.strip() or len(lot) > 80 or any(ord(c) < 32 for c in lot):
            raise ValidationFailure("Observed lot: a non-blank printable label of at most 80 characters is required")
        res = self.registry.resolve(lot, at=self.clock(), part=PART)
        recorded = res.canonical if res.ok else lot
        # A demo operator claim, explicitly untrusted. No trusted verifier is authored.
        return self.event(motor, "SLOT_STATE_VERIFIED", "HANDHELD", dict(
            componentType="BEARING", slot=slot, observedPart=PART, observedLot=recorded,
            identityGranularity="LOT", method="HANDHELD_LABEL_READ", provisional=True))

    def integrity_interrupted(self, motor):
        return bool(lots.interrupted_operations(self.events(motor)))

    def seed_demo(self):
        if self.db.execute("SELECT 1 FROM app_units LIMIT 1").fetchone():
            return
        specs = [("MTR-26001", "Serial-tracked assembly", "BR-204", "BR-310", "SERIAL", False),
                 ("MTR-26002", "Lot-level ambiguity", "BR-204", "BR-204", "LOT", False),
                 ("MTR-26003", "Unaffected supplier lot", "BR-310", "BR-312", "SERIAL", False),
                 ("MTR-26004", "Capture coverage gap", "BR-204", "BR-310", "SERIAL", True),
                 ("MTR-26005", "Untrusted affected-bearing observation", "BR-310", "BR-312", "SERIAL", False)]
        for serial, title, de, nde, identity, gap in specs:
            self.create_unit(serial, title, gap=gap); self.assemble(serial, de, nde, identity); self.record_historical_shipment_fixture(serial)
        self.announce("BR-204", ["DE"])
        self.snapshot()  # issue pre-rework records using the actual evaluator
        self.replace("MTR-26002", "BR-312")
        self.replace("MTR-26004", "BR-312")
        self.observe("MTR-26005", "BR-204")
        self.snapshot()

    def snapshot(self, *, trusted_anchor=None, ship_ticket=None):
        deadline=time.monotonic()+1.25 if trusted_anchor else None
        self.db.execute('BEGIN IMMEDIATE')
        self.audit._verified_token=None
        try:
            # Issuance, H2 verification and projection share one consistent cut.
            anchor=trusted_anchor.verify(self,deadline=deadline) if trusted_anchor else None
            binding=registry_binding.check(trusted_anchor.path,trusted_anchor.bytes,self.registry) if trusted_anchor else None
            verified_changes=self.db.total_changes
            result=self._snapshot(deadline,binding)
            if deadline is not None and time.monotonic()>=deadline:
                from .audit import Verifying
                raise Verifying()
            # Read-only polls reuse this request's proof under the same write
            # transaction. New publications require verification of the new cut.
            if trusted_anchor and self.db.total_changes!=verified_changes:
                anchor=trusted_anchor.verify(self,deadline=deadline)
            state=anchor['state'] if anchor else 'UNANCHORED'
            current=state=='ANCHORED_CURRENT'
            result['checkpoint']=dict(state=state,anchoredSequence=anchor['anchoredSequence'] if anchor else None,
                                      checkpointRequired=not current,h2=anchor['h2']['status'] if anchor else 'UNVERIFIED')
            pending={n['unitId'] for n in result['notifications']}
            # Never rewrite the immutable historical publication to fake clearance.
            result['eligibility']={u['unitId']:dict(currentReleaseEligible=current and u['unitId'] not in pending and
                bool(result['decisions'][u['unitId']]) and all(b['current']['operationalAction']=='RELEASE_ELIGIBLE'
                for b in result['decisions'][u['unitId']].values())) for u in result['units']}
            result['freshness'].update(status='VERIFIED_ANCHORED_SYNTHETIC' if current else 'VERIFIED_PREFIX_SYNTHETIC' if anchor else 'HISTORICAL_'+state,
                                       maxAgeSeconds=5 if anchor else 0)
            if not anchor:result['freshness']['verifiedAt']=''
            if ship_ticket is not None:
                self.db.execute("DELETE FROM app_ship_tickets WHERE motor=?", (ship_ticket,))
                if result['eligibility'].get(ship_ticket, {}).get('currentReleaseEligible'):
                    self.db.execute("INSERT INTO app_ship_tickets SELECT ?,(" + self.FINGERPRINT_SQL.removeprefix("SELECT ") + ")", (ship_ticket,))
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise
        finally:
            self.audit._verified_token=None

    def _snapshot(self,deadline=None,binding=None):
        # Raw publications remain historical without a trusted external prefix.
        anchor_status = None
        self.audit.verify(copy_records=False)
        policy = self.policy()
        units, components, lots_by_id, decisions, comparison, lineage, notifications = [], [], {}, {}, [], [], []
        recall_findings = lots.policy_findings(self.registry, policy, PART) if policy else []
        identity_motors, integrity_motors = {}, {}
        binding_findings = []
        if binding and binding["status"] != "OK":
            binding_findings = [dict(eventId=None, slot=None, lot=None, source="REGISTRY_BINDING", reason="REGISTRY_BINDING_" + binding["status"], detail=binding["detail"], resembles=[])]
        for unit in self.db.execute("SELECT serial,title FROM app_units ORDER BY serial").fetchall():
            if deadline is not None and time.monotonic()>=deadline:
                from .audit import Verifying
                raise Verifying()
            motor = unit["serial"]; wm = self.ledger.watermark(motor)
            case, manifest = self.ledger.snapshot(motor, wm)  # rejection/integrity failures propagate; never stale fallback
            events = case["events"]; by_id = {e["eventId"]:e for e in events}
            ui_events = copy.deepcopy(events)
            archived = {r["id"]: r for r in self.db.execute("SELECT e.id,e.hash,c.hash AS capture_sha256,c.received,e.epcis FROM events e JOIN captures c ON c.hash=e.capture WHERE e.motor=?", (motor,))}
            for e in ui_events:
                r = archived[e["eventId"]]
                e["repository"] = dict(captureSha256=r["capture_sha256"], eventChainHash=r["hash"], localReceivedAt=r["received"], recordTime=json.loads(r["epcis"])["recordTime"])
            shipped = [e for e in events if e["eventType"] == "MOTOR_SHIPPED"]
            shipment = None
            if shipped:
                e = shipped[-1]
                shipment = dict(e["payload"], shippedAt=e["occurredAt"], evidenceEventId=e["eventId"], backedByLedger=True, provenanceAssurance="SYNTHETIC_UNVERIFIED_CLAIM")
            units.append(dict(unitId=motor, motorSerial=motor, title=unit["title"], description="Synthetic electric-motor manufacturing history captured in the durable ledger.",
                              family="Electric motors · IE3", fixtureSet="LIVE_LEDGER_SYNTHETIC", shipment=shipment,
                              eventCount=len(events), events=ui_events, captureSessions=case["captureCoverage"]["sessions"], manifest=manifest))
            for e in events:
                p = e["payload"]
                if e["eventType"] == "BEARING_MANUFACTURED":
                    allocated = by_id[p["materialEventId"]]
                    lots_by_id[p["lot"]] = dict(lotId=p["lot"], part=p["part"], affected=bool(policy and p["lot"] in policy["affectedLots"]), supplier=allocated["payload"]["supplierName"], rawMaterialLot=p["rawMaterialLot"], evidenceEventId=e["eventId"], backedByLedger=True, provenanceAssurance="SYNTHETIC_UNVERIFIED_CLAIM")
                    lineage.append(dict(unitId=motor, **p, manufacturingEventId=e["eventId"], supplierName=allocated["payload"]["supplierName"], backedByLedger=True, provenanceAssurance="SYNTHETIC_UNVERIFIED_CLAIM"))
                if e["eventType"] == "COMPONENT_INSTALLED":
                    removal = next((x for x in events if x["eventType"] == "COMPONENT_REMOVED" and x["payload"].get("endsInstallEventId") == e["eventId"]), None)
                    correction = next((x for x in events if x["supersedesEventId"] == e["eventId"]), None)
                    components.append(dict(componentId=e["eventId"], unitId=motor, slot=p["slot"], part=p["part"], lot=p["lot"], serial=p.get("serial"),
                                           installedAt=e["occurredAt"], sourceId=e["sourceId"], removedAt=removal["occurredAt"] if removal else None,
                                           removalEventId=removal["eventId"] if removal else None, supersededBy=correction["eventId"] if correction else None, claimedBy=e["actorId"],
                                           registry=self.registry.resolve(p["lot"], at=e["occurredAt"], part=PART).public()))
            decisions[motor] = {}
            if policy:
                entry, history = self.audit.decide(motor, policy)
                found = binding_findings + recall_findings + lots.motor_findings(self.registry, events, policy, PART)
                broken = lots.integrity_findings(events)
                identity_motors[motor] = found
                integrity_motors[motor] = broken
                decisions[motor][policy["policyId"]] = dict(current=lots.guard_decision(copy.deepcopy(entry["decision"]), found, broken), history=history)
                legacy = engine_bridge.pramaan_recall.evaluate_series(case, policy, self.ledger._config(motor)["coverage"], [wm], engine_bridge.Config.legacy())[-1]
                if any(d["reasonCodes"] and "AMBIGUOUS_SLOT_ATTRIBUTION" in d["reasonCodes"] for d in history):
                    comparison.append(dict(unitId=motor, policyId=policy["policyId"], legacy=legacy, current=entry["decision"]))
        return dict(schemaVersion=1, provenance=dict(dataKind="LIVE_LEDGER_SYNTHETIC", adapter="BackendRecallDataSource → SQLite → actual v3",
                    engine=dict(version="phase1.2-untrusted-observation", semanticsProfile="UNTRUSTED_OBSERVATION_V3"),
                    comparisonEngine=dict(version="phase1-0.1", semanticsProfile="P1_LEGACY"), fixtureManifests={},
                    overlay=dict(file="none", sha256="", kind="NONE", covers="No shipment/supplier overlays"), oracleFilesRead=False),
                    recall=policy or dict(recallId=RECALL_ID, version=0, announcedAt=None, affectedPart=PART, affectedLots=[], affectedSlots=["DE"]),
                    policies=[dict(policyId=policy["policyId"], exposureBasis=policy["exposureBasis"], damageInspection=None)] if policy else [],
                    units=units, decisions=decisions, comparison=comparison, components=components, lots=[dict(l, registry=self.registry.resolve(l["lotId"], part=PART).public()) for l in lots_by_id.values()],
                    lineage=lineage, notifications=[dict(n,status='PENDING') for n in self.audit.outstanding()], recallAnnounced=bool(policy), lotIdentity=dict(registry=self.registry.meta(), motors=identity_motors, recallPolicyFindings=recall_findings, registryBinding=binding),
                    operationalIntegrity=dict(motors=integrity_motors),
                    freshness=dict(verifiedAt=self.ledger._now(), status="VERIFIED_ANCHORED_SYNTHETIC" if anchor_status else "HISTORICAL_UNANCHORED",
                                   maxAgeSeconds=5 if anchor_status else 0,
                                   archiveId=self.db.execute('SELECT archive_id FROM app_audit_head WHERE id=1').fetchone()[0],
                                   sequence=self.db.execute('SELECT count FROM app_audit_head WHERE id=1').fetchone()[0],
                                   headHash=self.db.execute('SELECT hash FROM app_audit_head WHERE id=1').fetchone()[0]))
