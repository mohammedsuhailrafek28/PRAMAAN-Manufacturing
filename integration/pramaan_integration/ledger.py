"""Local SQLite evidence ledger. No HTTP/auth server, migrations or engine changes.

The trusted caller provisions source capabilities, sessions and coverage once.
Rejected input leaves a durable motor block; this slice has no unblock shortcut.
"""
import copy
from functools import wraps
from datetime import datetime, timezone
import hashlib
import json
import sqlite3

from . import engine_bridge
from .profile import (PROFILE_VERSION, TYPES, ValidationFailure, decode, digest,
                      text, timestamp, validate_native, motor_uri, component_uri)


class LedgerBlocked(ValidationFailure):
    pass


def serialized_decision(function):
    @wraps(function)
    def call(self, *args, **kwargs):
        # Serialize issuance with capture and rejection writes, including other
        # SQLite connections, so a stale horizon cannot overwrite standing history.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            result = function(self, *args, **kwargs)
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise
    return call


class Ledger:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS motors(serial TEXT PRIMARY KEY, config TEXT NOT NULL, hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS captures(hash TEXT PRIMARY KEY, raw BLOB NOT NULL, received TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(
            ordinal INTEGER PRIMARY KEY, id TEXT UNIQUE NOT NULL, motor TEXT NOT NULL REFERENCES motors(serial),
            source TEXT NOT NULL, seq INTEGER NOT NULL, native TEXT NOT NULL, epcis TEXT NOT NULL,
            capture TEXT NOT NULL REFERENCES captures(hash), previous TEXT NOT NULL, hash TEXT NOT NULL,
            UNIQUE(motor,source,seq));
        CREATE INDEX IF NOT EXISTS motor_history ON events(motor,ordinal);
        CREATE TABLE IF NOT EXISTS rejections(
            ordinal INTEGER PRIMARY KEY, motor TEXT NOT NULL REFERENCES motors(serial),
            raw_hash TEXT NOT NULL, reason TEXT NOT NULL, received TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS decision_runs(
            ordinal INTEGER PRIMARY KEY, motor TEXT NOT NULL REFERENCES motors(serial),
            policy_hash TEXT NOT NULL, payload TEXT NOT NULL, hash TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS decision_history ON decision_runs(motor,policy_hash,ordinal);
        """)
        for table in ("motors", "captures", "events", "rejections", "decision_runs"):
            for action in ("UPDATE", "DELETE"):
                self.db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'append-only evidence'); END")
        self.db.commit()

    def close(self):
        self.db.close()

    def register_motor(self, serial, *, sources, sessions, coverage):
        """Trusted control-plane call. Each producer stream is motor-scoped."""
        text(serial, "motor serial")
        if not isinstance(sources, dict) or not sources:
            raise ValidationFailure("Explicit source registry required")
        for source, capability in sources.items():
            text(source, "sourceId")
            if capability.get("streamScope") != "MOTOR" or not capability.get("actors") or not capability.get("eventTypes") or not set(capability["eventTypes"]) <= TYPES:
                raise ValidationFailure("Motor-scoped sources, actors and event permissions required")
            for actor in capability["actors"]:
                text(actor, "authorized actor")
        ids = set()
        for s in sessions:
            text(s.get("sessionId"), "sessionId")
            if s["sessionId"] in ids or s.get("sourceId") not in sources or type(s.get("authenticated")) is not bool:
                raise ValidationFailure("Explicit unique source session required")
            ids.add(s["sessionId"])
            timestamp(s["from"]); timestamp(s["to"])
            if s["from"] > s["to"]:
                raise ValidationFailure("Reversed capture session")
        attr = coverage.get("slotAttribution", {})
        if {label.get("slot") for label in attr.get("slotLabels", []) if label.get("motorSerial") == serial} != {"DE", "NDE"}:
            raise ValidationFailure("Provision both DE/NDE position bindings; missing sibling is never absent")
        if attr.get("version") != 3 or attr.get("unknownSlotIsCandidate") is not True or type(attr.get("observationClockSkewSeconds")) is not int or attr["observationClockSkewSeconds"] < 300:
            raise ValidationFailure("v3 conservative attribution/time configuration required")
        if not 0 <= attr.get("labelAssociationWindowSeconds", 0) <= 60:
            raise ValidationFailure("Unsupported label association window")
        if not set(coverage.get("trustedVerifierSources", [])) <= set(sources):
            raise ValidationFailure("Unknown verifier source")
        if not coverage.get("coveragePolicyId") or not coverage.get("mandatoryCapture"):
            raise ValidationFailure("Explicit mandatory capture policy required")
        for rule in coverage["mandatoryCapture"]:
            if not set(rule["sources"]) <= set(sources):
                raise ValidationFailure("Unknown mandatory source")
        config = dict(sources=sources, sessions=sessions, coverage=coverage)
        with self.db:
            self.db.execute("INSERT INTO motors VALUES(?,?,?)", (serial, json.dumps(config, sort_keys=True), digest(config)))

    def _config(self, motor):
        row = self.db.execute("SELECT config,hash FROM motors WHERE serial=?", (motor,)).fetchone()
        if not row:
            raise ValidationFailure("Motor not provisioned")
        config = json.loads(row["config"])
        if digest(config) != row["hash"]:
            raise LedgerBlocked("Provisioned configuration changed")
        return config

    def _blocked(self, motor):
        if self.db.execute("SELECT 1 FROM rejections WHERE motor=? LIMIT 1", (motor,)).fetchone():
            raise LedgerBlocked("Rejected evidence exists; manual reconciliation required before evaluation")

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def capture(self, motor, raw, *, producer_source, expected_sha256):
        """Atomically capture original bytes from an already-authorized caller.

        expected_sha256 is a transport/content check, not source authentication.
        Domain-conflict claims are retained for the engine; malformed wire claims
        are rejected and block the entire motor, including earlier exclusions.
        """
        config = self._config(motor)
        raw_hash = hashlib.sha256(raw).hexdigest() if isinstance(raw, bytes) else "INVALID_BYTES"
        try:
            if not isinstance(expected_sha256, str) or raw_hash != expected_sha256:
                raise ValidationFailure("Document SHA-256 mismatch")
            doc, native = decode(raw)
            capability = config["sources"].get(producer_source)
            if not capability:
                raise ValidationFailure("Source not authorized for this motor")
            self.db.execute("BEGIN IMMEDIATE")
            existing = self._verified_rows(motor)
            known = {e["eventId"]: e for _, e in existing}
            seq = {source: 0 for source in config["sources"]}
            recorded = {}
            for _, e in existing:
                seq[e["sourceId"]] = max(seq[e["sourceId"]], e["sourceSeq"])
                recorded[e["sourceId"]] = max(recorded.get(e["sourceId"], ""), e["recordedAt"])
            previous = existing[-1][0]["hash"] if existing else "GENESIS"
            accepted = []
            for e, wire in zip(native, doc["epcisBody"]["eventList"]):
                if e["motorSerial"] != motor or e["sourceId"] != producer_source or e["actorId"] not in capability["actors"] or e["eventType"] not in capability["eventTypes"]:
                    raise ValidationFailure("Source/actor/motor/event capability mismatch")
                matching = [s for s in config["sessions"] if s["sessionId"] == e["captureSessionId"] and s["sourceId"] == producer_source and s["authenticated"] is True and s["from"] <= e["recordedAt"] <= s["to"]]
                if len(matching) != 1:
                    raise ValidationFailure("Missing authorized capture session")
                if e["eventId"] in known:
                    old = next((r for r, x in existing if x["eventId"] == e["eventId"]), None)
                    if known[e["eventId"]] != e or (old is not None and json.loads(old["epcis"]) != wire):
                        raise ValidationFailure("Event ID reused with different content")
                    continue
                if e["sourceSeq"] != seq[producer_source] + 1 or e["recordedAt"] < recorded.get(producer_source, ""):
                    raise ValidationFailure("Noncontiguous source sequence or recordedAt regression")
                for ref, event_type in ((e["supersedesEventId"], e["eventType"]),
                                        (e["payload"].get("endsInstallEventId"), "COMPONENT_INSTALLED"),
                                        (e["payload"].get("exceptionEventId"), "CAPTURE_EXCEPTION_RAISED"),
                                        (e["payload"].get("materialEventId"), "MATERIAL_ALLOCATED"),
                                        (e["payload"].get("manufacturingEventId"), "BEARING_MANUFACTURED"),
                                        (e["payload"].get("assemblyEventId"), "WORK_ORDER_CLOSED")):
                    if ref:
                        target = known.get(ref)
                        if not target or target["eventType"] != event_type or target["recordedAt"] > e["recordedAt"]:
                            raise ValidationFailure("Missing or incompatible event reference")
                        if ref in (e["supersedesEventId"], e["payload"].get("endsInstallEventId")) and e["payload"].get("slot") != target["payload"].get("slot"):
                            raise ValidationFailure("Cross-position reference")
                        if event_type == "BEARING_MANUFACTURED" and any(e["payload"].get(k) != target["payload"].get(k) for k in ("part", "lot", "serial")):
                            raise ValidationFailure("Manufactured bearing identity mismatch")
                        if event_type == "MATERIAL_ALLOCATED" and any(e["payload"].get(k) != target["payload"].get(k) for k in ("rawMaterialLot", "supplierId")):
                            raise ValidationFailure("Material provenance mismatch")
                        if e["eventType"] == "MOTOR_SHIPPED" and target["payload"].get("disposition") != "COMPLETED":
                            raise ValidationFailure("Shipment references incomplete assembly")
                if any(ref not in known for ref in e["payload"].get("derivedFromEventIds", [])):
                    raise ValidationFailure("Unknown verification provenance reference")
                if e["eventType"] != "WORK_ORDER_OPENED" and e["workOrderId"] is not None:
                    if not any(x["eventType"] == "WORK_ORDER_OPENED" and x["workOrderId"] == e["workOrderId"] for x in known.values()):
                        raise ValidationFailure("Unknown work order")
                if e["eventType"] == "WORK_ORDER_OPENED" and any(x["eventType"] == "WORK_ORDER_OPENED" and x["workOrderId"] == e["workOrderId"] for x in known.values()):
                    raise ValidationFailure("Work order reopened under a new event ID")
                entry_hash = digest(dict(previous=previous, native=e, epcis=wire, capture=raw_hash))
                accepted.append((e, wire, previous, entry_hash))
                previous = entry_hash
                known[e["eventId"]] = e
                seq[producer_source] = e["sourceSeq"]
                recorded[producer_source] = e["recordedAt"]
            with self.db:
                self.db.execute("INSERT OR IGNORE INTO captures VALUES(?,?,?)", (raw_hash, raw, self._now()))
                for e, wire, previous, entry_hash in accepted:
                    self.db.execute("INSERT INTO events(id,motor,source,seq,native,epcis,capture,previous,hash) VALUES(?,?,?,?,?,?,?,?,?)",
                                    (e["eventId"], motor, producer_source, e["sourceSeq"], json.dumps(e), json.dumps(wire), raw_hash, previous, entry_hash))
            return {"accepted": len(accepted), "documentSha256": raw_hash}
        except (ValidationFailure, sqlite3.IntegrityError) as exc:
            self.db.rollback()
            with self.db:
                self.db.execute("INSERT INTO rejections(motor,raw_hash,reason,received) VALUES(?,?,?,?)", (motor, raw_hash, str(exc), self._now()))
            raise LedgerBlocked(str(exc)) from exc

    def _verified_rows(self, motor):
        rows = self.db.execute("SELECT * FROM events WHERE motor=? ORDER BY ordinal", (motor,)).fetchall()
        result, previous, captures = [], "GENESIS", {}
        for row in rows:
            if row["capture"] not in captures:
                cap = self.db.execute("SELECT raw,received FROM captures WHERE hash=?", (row["capture"],)).fetchone()
                if not cap or hashlib.sha256(cap["raw"]).hexdigest() != row["capture"]:
                    raise LedgerBlocked("Original document integrity mismatch")
                doc, native = decode(cap["raw"])
                captures[row["capture"]] = {e["eventId"]: (e, w) for e, w in zip(native, doc["epcisBody"]["eventList"])}
            e, wire = json.loads(row["native"]), json.loads(row["epcis"])
            validate_native(e)
            if (e, wire) != captures[row["capture"]].get(e["eventId"]):
                raise LedgerBlocked("Derived/native event differs from original document")
            if e["motorSerial"] != motor or e["sourceId"] != row["source"] or e["sourceSeq"] != row["seq"] or e["eventId"] != row["id"]:
                raise LedgerBlocked("Ledger index differs from original identity")
            expected = digest(dict(previous=previous, native=e, epcis=wire, capture=row["capture"]))
            if row["previous"] != previous or row["hash"] != expected:
                raise LedgerBlocked("Event hash chain mismatch")
            previous = row["hash"]
            result.append((row, e))
        return result

    def watermark(self, motor):
        """Receipt positions only; caller must choose/attest the evaluation horizon."""
        config = self._config(motor)
        out = {source: 0 for source in config["sources"]}
        for _, event in self._verified_rows(motor):
            out[event["sourceId"]] = max(out[event["sourceId"]], event["sourceSeq"])
        return out

    def snapshot(self, motor, watermark):
        self._blocked(motor)
        config = self._config(motor)
        if not isinstance(watermark, dict) or set(watermark) != set(config["sources"]):
            raise LedgerBlocked("Explicit watermark for every provisioned source required")
        if any(type(n) is not int or not 0 <= n <= 1_000_000 for n in watermark.values()):
            raise LedgerBlocked("Invalid watermark")
        rows = [(r, e) for r, e in self._verified_rows(motor) if e["sourceSeq"] <= watermark[e["sourceId"]]]
        for source, highest in watermark.items():
            if sorted(e["sourceSeq"] for _, e in rows if e["sourceId"] == source) != list(range(1, highest + 1)):
                raise LedgerBlocked("Watermark prefix incomplete, including an absent source")
        visible = {e["eventId"] for _, e in rows}
        for _, e in rows:
            for ref in (e["supersedesEventId"], e["payload"].get("endsInstallEventId"), e["payload"].get("exceptionEventId"), e["payload"].get("materialEventId"), e["payload"].get("manufacturingEventId"), e["payload"].get("assemblyEventId")):
                if ref and ref not in visible:
                    raise LedgerBlocked("Watermark hides referenced evidence")
        manifest = [dict(eventId=e["eventId"], hash=r["hash"], captureSha256=r["capture"]) for r, e in rows]
        case = dict(caseId=motor, captureCoverage=dict(coveragePolicy=config["coverage"]["coveragePolicyId"], sessions=config["sessions"]), events=[e for _, e in rows])
        return case, dict(profile=PROFILE_VERSION, watermark=copy.deepcopy(watermark),
                          configurationDigest=digest(config), evidence=manifest,
                          evidenceSnapshotDigest=digest(manifest))

    def genealogy(self, motor, watermark):
        """Historical association claims. No independent safety/current-state inference."""
        case, manifest = self.snapshot(motor, watermark)
        rows = []
        for e in case["events"]:
            if e["eventType"] in ("COMPONENT_INSTALLED", "COMPONENT_REMOVED"):
                rows.append(dict(eventId=e["eventId"], action=e["eventType"], motorSerial=motor,
                                 parentID=motor_uri(motor), childID=component_uri(e["payload"], e["eventType"] == "COMPONENT_REMOVED"),
                                 slot=e["payload"]["slot"], occurredAt=e["occurredAt"],
                                 producerRecordedAt=e["recordedAt"], sourceId=e["sourceId"], sourceSeq=e["sourceSeq"],
                                 supersedesEventId=e["supersedesEventId"], payload=e["payload"]))
        return {"relationships": rows, "manifest": manifest}

    @serialized_decision
    def decide(self, motor, policy, watermarks, communicated=()):
        """Versioned v3 evaluation of complete snapshots; no outcome logic here."""
        if not watermarks:
            raise LedgerBlocked("Explicit decision watermarks required")
        for key in ("policyId", "recallId", "affectedPart"):
            text(policy.get(key), key)
        timestamp(policy.get("announcedAt"))
        if type(policy.get("version")) is not int or policy["version"] < 1 or not isinstance(policy.get("affectedLots"), list) or not policy["affectedLots"] or any(not isinstance(lot, str) or not lot for lot in policy["affectedLots"]):
            raise LedgerBlocked("Explicit policy version and affected lots required")
        if not isinstance(policy.get("affectedSlots"), list) or not policy["affectedSlots"] or not set(policy["affectedSlots"]) <= {"DE", "NDE"} or policy.get("exposureBasis") not in ("CURRENT_INSTALLATION", "HISTORICAL_OPERATION"):
            raise LedgerBlocked("Explicit supported policy scope required")
        if policy["exposureBasis"] == "HISTORICAL_OPERATION":
            inspection = policy.get("damageInspection")
            if not isinstance(inspection, dict) or inspection.get("requiredResult") != "PASS":
                raise LedgerBlocked("Historical policy requires an explicit PASS inspection protocol")
            for key in ("protocolId", "inspectorQualification"):
                text(inspection.get(key), key)
            timestamp(inspection.get("mustOccurAfter"))
            if inspection["mustOccurAfter"] < policy["announcedAt"]:
                raise LedgerBlocked("Inspection cannot predate recall announcement")
        config = self._config(motor)
        previous = self.db.execute("SELECT payload,hash FROM decision_runs WHERE motor=? AND policy_hash=? ORDER BY ordinal DESC LIMIT 1", (motor, digest(policy))).fetchone()
        old = json.loads(previous["payload"]) if previous else None
        if previous and digest(old) != previous["hash"]:
            raise LedgerBlocked("Stored decision history changed")
        history = copy.deepcopy(old["watermarks"]) if old else []
        positions = []
        for wm in watermarks:
            if wm in history:
                positions.append(history.index(wm))
            else:
                if history and any(wm.get(s, -1) < n for s, n in history[-1].items()):
                    raise LedgerBlocked("New decision watermark precedes standing decision")
                history.append(copy.deepcopy(wm)); positions.append(len(history)-1)
        communicated = sorted(set(communicated) | set(old["communicated"] if old else []))
        snapshots = [self.snapshot(motor, wm) for wm in history]
        for a, b in zip(watermarks, watermarks[1:]):
            if any(b[s] < a[s] for s in a):
                raise LedgerBlocked("Decision watermarks cannot regress")
        decisions = engine_bridge.evaluate_series(snapshots[-1][0], copy.deepcopy(policy), config["coverage"], history,
                                                  engine_bridge.Config.v3(), communicated=communicated)
        bundles = [dict(decision=d, manifest=m, policyDigest=digest(policy)) for d, (_, m) in zip(decisions, snapshots)]
        for bundle in bundles:
            bundle["bundleDigest"] = digest(bundle)
        payload = dict(watermarks=history, communicated=communicated, bundles=bundles)
        self._blocked(motor)
        if old != payload:
            self.db.execute("INSERT INTO decision_runs(motor,policy_hash,payload,hash) VALUES(?,?,?,?)", (motor, digest(policy), json.dumps(payload), digest(payload)))
        return [bundles[p] for p in positions]

    def replay(self, motor, policy, bundle):
        material = {k:v for k,v in bundle.items() if k != "bundleDigest"}
        if digest(material) != bundle.get("bundleDigest"):
            raise LedgerBlocked("Decision bundle changed")
        found = False
        for row in self.db.execute("SELECT payload,hash FROM decision_runs WHERE motor=? AND policy_hash=?", (motor, digest(policy))):
            payload = json.loads(row["payload"])
            if digest(payload) != row["hash"]:
                raise LedgerBlocked("Stored decision run integrity mismatch")
            found = found or bundle in payload["bundles"]
        if not found:
            raise LedgerBlocked("Decision was not issued by this ledger")
        case, manifest = self.snapshot(motor, bundle["manifest"]["watermark"])
        if manifest != bundle["manifest"] or digest(policy) != bundle["policyDigest"]:
            raise LedgerBlocked("Replay evidence/configuration/policy drift")
        return engine_bridge.replay(case, policy, self._config(motor)["coverage"], bundle["decision"])
