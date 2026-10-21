"""Disposable feasibility probe, NOT an EPCIS server or recall implementation.

Only synthetic data. External schema/context are read from a pinned GS1 checkout.
No production engine import, fixture import, HTTP server, or persistent database.
"""
import argparse
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sqlite3

from jsonschema import Draft7Validator, FormatChecker, ValidationError
from pyld import jsonld
import rfc8785

NS = "https://example.org/pramaan/research/"
MOTOR = "https://example.org/motors/RESEARCH-M001"
COMPONENT = "https://example.org/bearings/RESEARCH-B001"
CONTEXT = ["https://ref.gs1.org/standards/epcis/epcis-context.jsonld", {
    "pramaan": NS,
    "trace": {"@id": NS + "trace", "@type": "@json"},
}]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def native(seq, kind, minute, payload):
    """Independently authored synthetic instances of the documented v1 envelope."""
    return dict(eventId=f"https://example.org/events/research-{seq}",
                eventType=kind, schemaVersion=1, sourceId="RESEARCH-STATION",
                sourceSeq=seq, motorSerial="RESEARCH-M001", workOrderId="RESEARCH-WO1",
                recallId=None, occurredAt=f"2026-10-21T08:{minute:02}:00Z",
                timeSource="DEVICE_SYNCED", recordedAt=f"2026-10-21T08:{minute:02}:04Z",
                actorId="RESEARCH-OPERATOR", evidenceRefs=[f"research-scan-{seq}"],
                supersedesEventId=None, payload=payload)


def sample():
    events = [
        native(1, "WORK_ORDER_OPENED", 0, dict(orderType="BUILD", expectedChanges=[
            dict(slot="DE", action="INSTALL")])),
        native(2, "COMPONENT_INSTALLED", 1, dict(componentType="BEARING", slot="DE",
            part="RESEARCH-6205", lot="RESEARCH-LOT-A", serial="RESEARCH-B001",
            identityGranularity="SERIAL")),
        native(3, "WORK_ORDER_CLOSED", 2, dict(disposition="COMPLETED")),
        native(4, "WORK_ORDER_OPENED", 3, dict(orderType="REWORK", expectedChanges=[
            dict(slot="DE", action="REMOVE")])),
        native(5, "COMPONENT_REMOVED", 4, dict(componentType="BEARING", slot="DE",
            observedPart="RESEARCH-6205", observedLot="RESEARCH-LOT-A",
            observedSerial="RESEARCH-B001", identityGranularity="SERIAL",
            endsInstallEventId="https://example.org/events/research-2")),
        native(6, "WORK_ORDER_CLOSED", 5, dict(disposition="COMPLETED")),
    ]
    for event in events[3:]:
        event["workOrderId"] = "RESEARCH-WO2"
    return events


def to_epcis(e):
    event = dict(type="ObjectEvent", eventID=e["eventId"], eventTime=e["occurredAt"],
                 eventTimeZoneOffset="+00:00", recordTime="2026-10-21T09:00:00Z",
                 action="OBSERVE", epcList=[MOTOR], trace={
                     k: copy.deepcopy(v) for k, v in e.items()
                     if k not in ("eventId", "occurredAt", "payload")})
    p = e["payload"]
    if e["eventType"] in ("COMPONENT_INSTALLED", "COMPONENT_REMOVED"):
        event.pop("epcList")
        event.update(type="AssociationEvent", parentID=MOTOR, childEPCs=[COMPONENT],
                     action="ADD" if e["eventType"] == "COMPONENT_INSTALLED" else "DELETE",
                     bizStep="assembling" if e["eventType"] == "COMPONENT_INSTALLED" else "disassembling")
    event["trace"]["payload"] = copy.deepcopy(p)
    return event


def from_epcis(e):
    """Fail closed on missing manufacturing metadata or conflicting core fields."""
    if "trace" not in e:
        raise ValueError("Missing PRAMAAN provenance profile; cannot infer slot or sequence")
    t = copy.deepcopy(e["trace"])
    required = ("schemaVersion", "sourceId", "sourceSeq", "motorSerial", "recordedAt",
                "timeSource", "actorId", "evidenceRefs", "supersedesEventId", "eventType", "payload")
    if any(k not in t for k in required):
        raise ValueError("Incomplete native input contract")
    if not isinstance(t["sourceSeq"], int) or isinstance(t["sourceSeq"], bool) or t["sourceSeq"] < 1:
        raise ValueError("Invalid producer sequence")
    t.update(eventId=e["eventID"], occurredAt=e["eventTime"])
    if t["motorSerial"] != "RESEARCH-M001":
        raise ValueError("Unknown motor identity mapping")
    if t["eventType"] in ("COMPONENT_INSTALLED", "COMPONENT_REMOVED"):
        action = "ADD" if t["eventType"] == "COMPONENT_INSTALLED" else "DELETE"
        if e["type"] != "AssociationEvent" or e["action"] != action or e["parentID"] != MOTOR or e["childEPCs"] != [COMPONENT]:
            raise ValueError("Core/extension identity or action conflict")
        if t["payload"].get("slot") not in ("DE", "NDE"):
            raise ValueError("Missing or invalid slot")
        if t["eventType"] == "COMPONENT_REMOVED" and not t["payload"].get("endsInstallEventId"):
            raise ValueError("Removal has no installation reference")
    return t


class ProbeStore:
    def __init__(self, validator, context_digest):
        self.validator = validator
        self.context_digest = context_digest
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE events(id TEXT PRIMARY KEY, source TEXT, seq INTEGER, raw BLOB, digest TEXT, jcs TEXT, UNIQUE(source,seq))")

    def capture(self, doc):
        self.validator.validate(doc)
        if doc["@context"] != CONTEXT:
            raise ValueError("Unapproved context")
        # Validate the whole batch before starting the transaction.
        for e in doc["epcisBody"]["eventList"]:
            from_epcis(e)
        with self.db:
            for e in doc["epcisBody"]["eventList"]:
                raw = json.dumps(e, ensure_ascii=False, separators=(",", ":")).encode()
                canonical = rfc8785.dumps({"@context": CONTEXT, "event": e,
                                         "contextSha256": self.context_digest})
                t = e["trace"]
                old = self.db.execute("SELECT raw FROM events WHERE id=?", (e["eventID"],)).fetchone()
                if old:
                    if old[0] == raw:
                        continue
                    raise ValueError("Event ID collision with different content")
                self.db.execute("INSERT INTO events VALUES(?,?,?,?,?,?)",
                                (e["eventID"], t["sourceId"], t["sourceSeq"], raw, sha(raw), sha(canonical)))

    def events(self):
        result = []
        for raw, digest in self.db.execute("SELECT raw,digest FROM events ORDER BY source,seq"):
            if sha(raw) != digest:
                raise ValueError("Stored bytes failed integrity check")
            result.append(json.loads(raw))
        return result

    def genealogy(self, component):
        # Historical association events, not an inference that absence proves removal.
        return [e for e in self.events() if component in e.get("childEPCs", [])]


def document(events):
    return {"@context": CONTEXT, "type": "EPCISDocument", "schemaVersion": "2.0",
            "creationDate": "2026-10-21T09:00:00Z", "epcisBody": {"eventList": events}}


def run(gs1):
    schema_path = gs1 / "EPCIS-JSON-Schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    context_path = gs1 / "epcis-context.jsonld"
    validator = Draft7Validator(schema, format_checker=FormatChecker())
    Draft7Validator.check_schema(schema)
    store = ProbeStore(validator, sha(context_path.read_bytes()))
    source = sample()
    epcis = [to_epcis(e) for e in source]
    checks = {}

    def check(name, value):
        if not value:
            raise AssertionError(name)
        checks[name] = True

    def rejected(name, fn):
        try:
            fn()
        except (ValueError, sqlite3.IntegrityError, ValidationError):
            checks[name] = True
        else:
            raise AssertionError(name)

    store.capture(document(epcis))
    check("all_events_validate_and_capture", len(store.events()) == 6)
    def loader(url, options=None):
        if url != CONTEXT[0]:
            raise ValueError("Network context resolution forbidden in probe")
        return {"contextUrl": None, "documentUrl": url,
                "document": json.loads(context_path.read_text(encoding="utf-8"))}
    expanded = jsonld.expand(document(epcis), options={"documentLoader": loader})
    compacted = jsonld.compact(expanded, CONTEXT, options={"documentLoader": loader})
    check("jsonld_expansion_retains_private_metadata", NS + "trace" in json.dumps(expanded))
    check("jsonld_expand_compact_preserves_trace_values", compacted["epcisBody"]["eventList"][1]["trace"] == epcis[1]["trace"])
    retrieved = store.genealogy(COMPONENT)
    check("component_to_motor_install_remove_history", [e["action"] for e in retrieved] == ["ADD", "DELETE"] and all(e["parentID"] == MOTOR for e in retrieved))
    check("exact_native_roundtrip_including_slot_source_sequence_times_and_evidence", [from_epcis(e) for e in store.events()] == source)
    check("repository_record_time_does_not_replace_source_recorded_at", from_epcis(retrieved[0])["recordedAt"] != retrieved[0]["recordTime"])
    check("removal_preserves_install_reference", from_epcis(retrieved[1])["payload"]["endsInstallEventId"] == source[1]["eventId"])
    store.capture(document(epcis))
    check("identical_retry_is_idempotent", len(store.events()) == 6)
    altered = copy.deepcopy(epcis[1]); altered["trace"]["payload"]["slot"] = "NDE"
    rejected("same_id_changed_slot_is_rejected", lambda: store.capture(document([altered])))
    bare = copy.deepcopy(epcis[1]); bare.pop("trace")
    check("base_schema_allows_missing_manufacturing_profile", validator.is_valid(document([bare])))
    rejected("bare_epcis_cannot_invent_slot_or_provenance", lambda: store.capture(document([bare])))
    wrong = copy.deepcopy(epcis[1]); wrong["action"] = "DELETE"
    rejected("conflicting_action_is_rejected", lambda: store.capture(document([wrong])))
    missing_slot = copy.deepcopy(epcis[1]); missing_slot["trace"]["payload"].pop("slot")
    rejected("missing_slot_rejected", lambda: store.capture(document([missing_slot])))
    duplicate_seq = copy.deepcopy(epcis[1]); duplicate_seq["eventID"] += "-other"
    rejected("duplicate_source_sequence_rejected", lambda: store.capture(document([duplicate_seq])))
    unbound = copy.deepcopy(epcis[4]); unbound["trace"]["payload"].pop("endsInstallEventId")
    rejected("unbound_removal_rejected", lambda: store.capture(document([unbound])))
    bad_time = copy.deepcopy(epcis[1]); bad_time["eventTime"] = "not-a-timestamp"
    rejected("invalid_epcis_timestamp_rejected", lambda: store.capture(document([bad_time])))
    check("failed_capture_leaves_original_history_intact", [from_epcis(e) for e in store.events()] == source)
    check("jcs_key_order_invariance", rfc8785.dumps(epcis[1]) == rfc8785.dumps(dict(reversed(list(epcis[1].items())))))
    check("jcs_detects_slot_change", sha(rfc8785.dumps(epcis[1])) != sha(rfc8785.dumps(altered)))
    sequence_changed = copy.deepcopy(epcis[1]); sequence_changed["trace"]["sourceSeq"] = 99
    check("jcs_detects_source_sequence_change", sha(rfc8785.dumps(epcis[1])) != sha(rfc8785.dumps(sequence_changed)))
    adapted = [from_epcis(e) for e in store.events()]
    integrity_metadata = [dict(eventId=i, rawSha256=raw, contextBoundJcsSha256=jcs)
                          for i, raw, jcs in store.db.execute("SELECT id,digest,jcs FROM events ORDER BY source,seq")]
    store.db.execute("UPDATE events SET raw=? WHERE seq=2", (b"{}",))
    rejected("stored_byte_mutation_detected", store.events)
    return {
        "scope": "Synthetic profile validation, in-memory SQLite capture/query, native-contract adapter; no production engine execution",
        "schemaSha256": sha(schema_path.read_bytes()), "contextSha256": sha(context_path.read_bytes()),
        "packages": {p: importlib.metadata.version(p) for p in ("jsonschema", "rfc8785", "PyLD")},
        "checks": checks, "passed": len(checks),
        "genealogyEvents": retrieved,
        "engineInput": {"caseId": "foundation-research-only", "captureCoverage": {
            "coveragePolicy": "RESEARCH-COVERAGE", "sessions": [{"sourceId": "RESEARCH-STATION",
                "from": "2026-10-21T08:00:00Z", "to": "2026-10-21T08:10:00Z"}]}, "events": adapted},
        "integrityMetadata": integrity_metadata,
        "integrity": {"raw": "SHA-256 exact event bytes", "canonical": "RFC8785 over event + approved context + pinned context digest", "gs1CbvHash": "NOT implemented or claimed", "signatures": "NOT verified or claimed"},
        "limitations": ["No recall decisions; documented input contract only", "One fixed motor/component identity map", "No quantity, transformation, concurrency or fleet benchmark", "No upstream service executed", "No absence/completeness claim from filtered genealogy", "Source metadata are claims, not authenticated facts", "JCS is not JSON-LD/RDF or GS1 CBV canonicalization"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gs1-checkout", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("results.json"))
    args = parser.parse_args()
    result = run(args.gs1_checkout)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{result['passed']} feasibility checks passed; {args.output}")
