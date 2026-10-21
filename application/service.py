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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integration"))
from pramaan_integration import Ledger, LedgerBlocked, ValidationFailure, encode_document
from pramaan_integration.profile import digest
from pramaan_integration import engine_bridge

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


class Manufacturing:
    def __init__(self, path):
        self.ledger = Ledger(path)
        self.db = self.ledger.db
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS app_units(serial TEXT PRIMARY KEY, title TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS app_clock(id INTEGER PRIMARY KEY CHECK(id=1), at TEXT NOT NULL);
        INSERT OR IGNORE INTO app_clock VALUES(1,'2026-10-10T08:00:00Z');
        CREATE TABLE IF NOT EXISTS recall_announcements(version INTEGER PRIMARY KEY, policy TEXT NOT NULL, hash TEXT NOT NULL);
        """)
        for action in ("UPDATE", "DELETE"):
            self.db.execute(f"CREATE TRIGGER IF NOT EXISTS announcements_no_{action.lower()} BEFORE {action} ON recall_announcements BEGIN SELECT RAISE(ABORT,'immutable recall policy'); END")
        self.db.commit()

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
                trustedTimeSources=["DEVICE_SYNCED"]))
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
                     actorId=ROLES[role][0], timeSource="DEVICE_SYNCED", evidenceRefs=[f"demo-record:{motor}:{role}:{wm[source]+1}"],
                     workOrderId=work_order, recallId=None, supersedesEventId=supersedes,
                     captureSessionId=f"session:{source}", payload=payload)
        # Three distinct clocks: occurrence, producer record, simulated upstream
        # repository recordTime. SQLite additionally archives local wall-clock receipt.
        repository_time = (datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ")+timedelta(seconds=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
        raw = json.dumps(encode_document([event], repository_time), separators=(",", ":")).encode()
        self.ledger.capture(motor, raw, producer_source=source, expected_sha256=hashlib.sha256(raw).hexdigest())
        return event

    def manufacture(self, motor, lot, serial=None):
        allocated = self.event(motor, "MATERIAL_ALLOCATED", "MATERIAL", dict(
            rawMaterialLot="STEEL-26-410" if lot == "BR-204" else "STEEL-26-518",
            supplierId="SUP-NSB-01" if lot == "BR-204" else "SUP-KAV-02",
            supplierName="Northstar Bearings — synthetic supplier" if lot == "BR-204" else "Kaveri Precision — synthetic supplier"))
        return self.event(motor, "BEARING_MANUFACTURED", "MATERIAL", dict(
            rawMaterialLot=allocated["payload"]["rawMaterialLot"], supplierId=allocated["payload"]["supplierId"],
            part=PART, lot=lot, serial=serial, materialEventId=allocated["eventId"]))

    def assemble(self, motor, de_lot, nde_lot, identity="SERIAL"):
        events = self.events(motor)
        if any(e["eventType"] == "WORK_ORDER_OPENED" for e in events):
            raise ValidationFailure("This unit already has assembly evidence; use replacement")
        if identity not in ("LOT", "SERIAL") or any(not isinstance(x, str) or not x or len(x)>80 for x in (de_lot, nde_lot)):
            raise ValidationFailure("Explicit valid DE/NDE bearing lots and identity required")
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

    def ship(self, motor):
        events = self.events(motor)
        if any(e["eventType"] == "MOTOR_SHIPPED" for e in events):
            raise ValidationFailure("Shipment already recorded")
        closed = next((e for e in events if e["eventType"] == "WORK_ORDER_CLOSED" and e["workOrderId"] == f"BUILD-{motor}"), None)
        if not closed:
            raise ValidationFailure("Completed assembly evidence is required")
        return self.event(motor, "MOTOR_SHIPPED", "SHIP", dict(
            shipmentId=f"SHP-26-{motor.removeprefix('MTR-')}", customer="Aster Pump Systems — synthetic customer",
            destination="Coimbatore distribution centre", assemblyEventId=closed["eventId"]))

    def announce(self, affected_lot):
        if not isinstance(affected_lot, str) or not affected_lot or len(affected_lot)>80:
            raise ValidationFailure("An affected bearing lot is required")
        old = self.policy()
        if old and old["affectedLots"] == [affected_lot]:
            return old
        if old:
            raise ValidationFailure("This local demonstration supports one immutable recall scope per database; use a new database for another affected lot")
        at = self.tick("2026-10-20T08:00:00Z")
        policy = dict(policyId=RECALL_ID+"/P1", recallId=RECALL_ID, version=(old["version"]+1 if old else 1),
                      announcedAt=at, affectedPart=PART, affectedLots=[affected_lot], affectedSlots=["DE"],
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
        return policy

    def replace(self, motor, lot):
        if not isinstance(lot, str) or not lot or len(lot)>80:
            raise ValidationFailure("An explicit replacement lot is required")
        events = self.events(motor)
        ended = {e["payload"].get("endsInstallEventId") for e in events if e["eventType"] == "COMPONENT_REMOVED"}
        corrected = {e["supersedesEventId"] for e in events if e["supersedesEventId"]}
        installs = [e for e in events if e["eventType"] == "COMPONENT_INSTALLED" and e["payload"]["slot"] == "DE" and e["eventId"] not in ended|corrected]
        if len(installs) != 1:
            raise ValidationFailure("No unique recorded DE occupant; investigate evidence first")
        old = installs[0]; p = old["payload"]
        wo = f"RW-{motor}-{self.ledger.watermark(motor)[self.source('REWORK',motor)]+1}"
        self.event(motor, "WORK_ORDER_OPENED", "MES", dict(orderType="REWORK", expectedChanges=[dict(slot="DE", action="REPLACE")]), work_order=wo)
        observed = dict(componentType="BEARING", slot="DE", observedPart=p["part"], observedLot=p["lot"], identityGranularity=p["identityGranularity"], endsInstallEventId=old["eventId"])
        if p.get("serial"):
            observed["observedSerial"] = p["serial"]
        self.event(motor, "COMPONENT_REMOVED", "REWORK", observed, work_order=wo)
        serial = f"BRG-{motor}-DE-R{len(events)}" if p["identityGranularity"] == "SERIAL" else None
        made = self.manufacture(motor, lot, serial)
        payload = dict(componentType="BEARING", slot="DE", part=PART, lot=lot, identityGranularity=p["identityGranularity"], manufacturingEventId=made["eventId"])
        if serial:
            payload["serial"] = serial
        self.event(motor, "COMPONENT_INSTALLED", "REWORK", payload, work_order=wo)
        return self.event(motor, "WORK_ORDER_CLOSED", "MES", dict(disposition="COMPLETED"), work_order=wo)

    def observe(self, motor, lot):
        # A demo operator claim, explicitly untrusted. No trusted verifier is authored.
        return self.event(motor, "SLOT_STATE_VERIFIED", "HANDHELD", dict(
            componentType="BEARING", slot="DE", observedPart=PART, observedLot=lot,
            identityGranularity="LOT", method="HANDHELD_LABEL_READ", provisional=True))

    def seed_demo(self):
        if self.db.execute("SELECT 1 FROM app_units LIMIT 1").fetchone():
            return
        specs = [("MTR-26001", "Serial-tracked assembly", "BR-204", "BR-310", "SERIAL", False),
                 ("MTR-26002", "Lot-level ambiguity", "BR-204", "BR-204", "LOT", False),
                 ("MTR-26003", "Unaffected supplier lot", "BR-310", "BR-312", "SERIAL", False),
                 ("MTR-26004", "Capture coverage gap", "BR-204", "BR-310", "SERIAL", True),
                 ("MTR-26005", "Untrusted affected-bearing observation", "BR-310", "BR-312", "SERIAL", False)]
        for serial, title, de, nde, identity, gap in specs:
            self.create_unit(serial, title, gap=gap); self.assemble(serial, de, nde, identity); self.ship(serial)
        self.announce("BR-204")
        self.snapshot()  # issue pre-rework records using the actual evaluator
        self.replace("MTR-26002", "BR-312")
        self.replace("MTR-26004", "BR-312")
        self.observe("MTR-26005", "BR-204")
        self.snapshot()

    def snapshot(self):
        policy = self.policy()
        units, components, lots, decisions, comparison, lineage, notifications = [], [], {}, {}, [], [], []
        for unit in self.db.execute("SELECT serial,title FROM app_units ORDER BY serial").fetchall():
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
                shipment = dict(e["payload"], shippedAt=e["occurredAt"], evidenceEventId=e["eventId"], backedByLedger=True)
            units.append(dict(unitId=motor, motorSerial=motor, title=unit["title"], description="Synthetic electric-motor manufacturing history captured in the durable ledger.",
                              family="Electric motors · IE3", fixtureSet="LIVE_LEDGER_SYNTHETIC", shipment=shipment,
                              eventCount=len(events), events=ui_events, captureSessions=case["captureCoverage"]["sessions"], manifest=manifest))
            for e in events:
                p = e["payload"]
                if e["eventType"] == "BEARING_MANUFACTURED":
                    allocated = by_id[p["materialEventId"]]
                    lots[p["lot"]] = dict(lotId=p["lot"], part=p["part"], affected=bool(policy and p["lot"] in policy["affectedLots"]), supplier=allocated["payload"]["supplierName"], rawMaterialLot=p["rawMaterialLot"], evidenceEventId=e["eventId"], backedByLedger=True)
                    lineage.append(dict(unitId=motor, **p, manufacturingEventId=e["eventId"], supplierName=allocated["payload"]["supplierName"], backedByLedger=True))
                if e["eventType"] == "COMPONENT_INSTALLED":
                    removal = next((x for x in events if x["eventType"] == "COMPONENT_REMOVED" and x["payload"].get("endsInstallEventId") == e["eventId"]), None)
                    correction = next((x for x in events if x["supersedesEventId"] == e["eventId"]), None)
                    components.append(dict(componentId=e["eventId"], unitId=motor, slot=p["slot"], part=p["part"], lot=p["lot"], serial=p.get("serial"),
                                           installedAt=e["occurredAt"], sourceId=e["sourceId"], removedAt=removal["occurredAt"] if removal else None,
                                           removalEventId=removal["eventId"] if removal else None, supersededBy=correction["eventId"] if correction else None, claimedBy=e["actorId"]))
            decisions[motor] = {}
            if policy:
                # Read/display is not a delivered notification; communication remains unknown.
                bundle = self.ledger.decide(motor, policy, [wm])[0]
                stored = self.db.execute("SELECT payload FROM decision_runs WHERE motor=? AND policy_hash=? ORDER BY ordinal DESC LIMIT 1", (motor, digest(policy))).fetchone()
                history = [b["decision"] for b in json.loads(stored[0])["bundles"] if not b["decision"].get("unchanged")]
                decisions[motor][policy["policyId"]] = dict(current=bundle["decision"], history=history)
                if bundle["decision"].get("notificationObligation"):
                    notifications.append(dict(unitId=motor, decisionId=bundle["decision"]["decisionId"], **bundle["decision"]["notificationObligation"], deliveryStatus="NOT_SENT"))
                legacy = engine_bridge.pramaan_recall.evaluate_series(case, policy, self.ledger._config(motor)["coverage"], [wm], engine_bridge.Config.legacy())[-1]
                if any(d["reasonCodes"] and "AMBIGUOUS_SLOT_ATTRIBUTION" in d["reasonCodes"] for d in history):
                    comparison.append(dict(unitId=motor, policyId=policy["policyId"], legacy=legacy, current=bundle["decision"]))
        return dict(schemaVersion=1, provenance=dict(dataKind="LIVE_LEDGER_SYNTHETIC", adapter="BackendRecallDataSource → SQLite → actual v3",
                    engine=dict(version="phase1.2-untrusted-observation", semanticsProfile="UNTRUSTED_OBSERVATION_V3"),
                    comparisonEngine=dict(version="phase1-0.1", semanticsProfile="P1_LEGACY"), fixtureManifests={},
                    overlay=dict(file="none", sha256="", kind="NONE", covers="No shipment/supplier overlays"), oracleFilesRead=False),
                    recall=policy or dict(recallId=RECALL_ID, version=0, announcedAt=None, affectedPart=PART, affectedLots=[], affectedSlots=["DE"]),
                    policies=[dict(policyId=policy["policyId"], exposureBasis=policy["exposureBasis"], damageInspection=None)] if policy else [],
                    units=units, decisions=decisions, comparison=comparison, components=components, lots=list(lots.values()),
                    lineage=lineage, notifications=notifications, recallAnnounced=bool(policy))
