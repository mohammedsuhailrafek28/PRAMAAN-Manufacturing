"""Self-authored EPCIS 2.0-compatible manufacturing subset; no upstream code/schema.

The JSON literal trace extension preserves the native input envelope losslessly.
This is intentionally narrower than complete EPCIS. Unknown semantics fail closed.
"""
import copy
from datetime import datetime
import hashlib
import json
import re
from urllib.parse import quote

from jsonschema import Draft7Validator
import rfc8785

NS = "https://example.org/pramaan/phase2/"
CONTEXT = ["https://ref.gs1.org/standards/epcis/epcis-context.jsonld", {
    "pramaan": NS, "trace": {"@id": NS + "trace", "@type": "@json"}}]
PROFILE_VERSION = "pramaan-bearing-epcis/1"
FIELDS = {"eventType", "schemaVersion", "sourceId", "sourceSeq", "motorSerial",
          "workOrderId", "recallId", "recordedAt", "timeSource", "actorId",
          "evidenceRefs", "supersedesEventId", "captureSessionId", "payload"}
TYPES = {"WORK_ORDER_OPENED", "WORK_ORDER_CLOSED", "COMPONENT_INSTALLED",
         "COMPONENT_REMOVED", "SLOT_STATE_VERIFIED", "SLOT_LABEL_SCANNED",
         "SLOT_ACCESS_EVIDENCE", "CAPTURE_EXCEPTION_RAISED", "CAPTURE_EXCEPTION_RESOLVED",
         "INSPECTION_RECORDED", "MATERIAL_ALLOCATED", "BEARING_MANUFACTURED", "MOTOR_SHIPPED"}
# Only shape validation for the supported wire profile. Semantics are checked below.
SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["@context", "type", "schemaVersion", "creationDate", "epcisBody"],
          "properties": {"@context": {"const": CONTEXT}, "type": {"const": "EPCISDocument"},
                         "schemaVersion": {"const": "2.0"}, "creationDate": {"type": "string"},
                         "epcisBody": {"type": "object", "additionalProperties": False,
                                       "required": ["eventList"], "properties": {"eventList": {
                                           "type": "array", "minItems": 1, "maxItems": 1000,
                                           "items": {"type": "object"}}}}}}
VALIDATOR = Draft7Validator(SCHEMA)


class ValidationFailure(ValueError):
    pass


def digest(value):
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value):
        raise ValidationFailure("Timestamp must be explicit whole-second UTC")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ValidationFailure("Invalid calendar timestamp") from exc
    return value


def text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise ValidationFailure(f"Missing/invalid {name}")
    return value


def uri(value):
    text(value, "URI")
    if not re.match(r"^(https://[^\s]+|urn:[^\s]+)$", value):
        raise ValidationFailure("Expected an absolute HTTPS or URN identity")
    return value


def motor_uri(serial):
    return NS + "motor/" + quote(serial, safe="")


def component_uri(payload, observed=False):
    part, lot, serial = (("observedPart", "observedLot", "observedSerial") if observed
                         else ("part", "lot", "serial"))
    result = NS + "part/" + quote(text(payload.get(part), part), safe="")
    result += "/lot/" + quote(text(payload.get(lot), lot), safe="")
    granularity = payload.get("identityGranularity")
    if granularity not in ("LOT", "SERIAL"):
        raise ValidationFailure("Explicit LOT/SERIAL identity granularity required")
    if granularity == "SERIAL":
        result += "/serial/" + quote(text(payload.get(serial), serial), safe="")
    elif payload.get(serial) is not None:
        raise ValidationFailure("Serial supplied with LOT identity")
    return result


def validate_native(e):
    if set(e) != FIELDS | {"eventId", "occurredAt"}:
        raise ValidationFailure("Native envelope fields missing or unsupported")
    uri(e["eventId"])
    if e["eventType"] not in TYPES or type(e["schemaVersion"]) is not int or e["schemaVersion"] != 1:
        raise ValidationFailure("Unsupported native event type/schema")
    for key in ("sourceId", "motorSerial", "actorId", "timeSource", "captureSessionId"):
        text(e[key], key)
    if type(e["sourceSeq"]) is not int or not 1 <= e["sourceSeq"] <= 1_000_000:
        raise ValidationFailure("Invalid producer sequence")
    for key in ("workOrderId", "recallId", "supersedesEventId"):
        if e[key] is not None:
            text(e[key], key)
    if e["supersedesEventId"]:
        uri(e["supersedesEventId"])
    timestamp(e["occurredAt"]); timestamp(e["recordedAt"])
    if e["recordedAt"] < e["occurredAt"]:
        raise ValidationFailure("Producer recordedAt precedes occurredAt")
    if not isinstance(e["evidenceRefs"], list) or any(not isinstance(r, str) or not r for r in e["evidenceRefs"]):
        raise ValidationFailure("Invalid evidence references")
    p, kind = e["payload"], e["eventType"]
    if not isinstance(p, dict):
        raise ValidationFailure("Payload must be an object")
    if any(k in p for k in ("trusted", "authorized", "semanticsProfile", "coveragePolicy")):
        raise ValidationFailure("Event cannot self-assert trust/configuration")
    if kind in ("COMPONENT_INSTALLED", "COMPONENT_REMOVED", "SLOT_STATE_VERIFIED"):
        if p.get("componentType") != "BEARING" or p.get("slot") not in ("DE", "NDE"):
            raise ValidationFailure("Explicit bearing position required")
        component_uri(p, kind != "COMPONENT_INSTALLED")
    if kind in ("WORK_ORDER_OPENED", "WORK_ORDER_CLOSED", "COMPONENT_INSTALLED", "COMPONENT_REMOVED"):
        text(e["workOrderId"], "workOrderId")
    if kind == "COMPONENT_REMOVED":
        uri(p.get("endsInstallEventId"))
    if kind == "WORK_ORDER_OPENED":
        if p.get("orderType") not in ("BUILD", "REWORK") or not isinstance(p.get("expectedChanges"), list) or not p["expectedChanges"]:
            raise ValidationFailure("Explicit work-order obligations required")
        for c in p["expectedChanges"]:
            if c.get("slot") not in ("DE", "NDE") or c.get("action") not in ("INSTALL", "REMOVE", "REPLACE", "INSPECT"):
                raise ValidationFailure("Invalid work-order obligation")
    if kind == "WORK_ORDER_CLOSED" and p.get("disposition") not in ("COMPLETED", "CANCELLED"):
        raise ValidationFailure("Explicit close disposition required")
    if kind == "SLOT_STATE_VERIFIED":
        text(p.get("method"), "verification method")
        if "derivedFromEventIds" in p and (not isinstance(p["derivedFromEventIds"], list) or any(not isinstance(x, str) for x in p["derivedFromEventIds"])):
            raise ValidationFailure("Invalid verification provenance")
    if kind == "SLOT_LABEL_SCANNED":
        text(p.get("labelId"), "label binding")
    if kind == "SLOT_ACCESS_EVIDENCE":
        text(p.get("method"), "access evidence method")
        if not isinstance(p.get("accessibleSlots"), list) or any(x not in ("DE", "NDE") for x in p["accessibleSlots"]):
            raise ValidationFailure("Explicit accessible slots required")
    if kind == "CAPTURE_EXCEPTION_RAISED":
        if not isinstance(p.get("scope"), dict) or not isinstance(p["scope"].get("slots"), list) or not p["scope"]["slots"] or any(x not in ("DE", "NDE") for x in p["scope"]["slots"]):
            raise ValidationFailure("Capture exception requires explicit slot scope")
    if kind == "CAPTURE_EXCEPTION_RESOLVED":
        uri(p.get("exceptionEventId"))
    if kind == "INSPECTION_RECORDED":
        for key in ("protocolId", "result"):
            text(p.get(key), key)
        if not isinstance(p.get("inspectorQualifiedFor"), list) or any(not isinstance(x, str) or not x for x in p["inspectorQualifiedFor"]):
            raise ValidationFailure("Explicit inspector qualification list required")
        if not isinstance(p.get("scope"), list) or not p["scope"]:
            raise ValidationFailure("Inspection scope required")
    if kind == "MATERIAL_ALLOCATED":
        for key in ("rawMaterialLot", "supplierId", "supplierName"):
            text(p.get(key), key)
    if kind == "BEARING_MANUFACTURED":
        for key in ("rawMaterialLot", "supplierId", "part", "lot"):
            text(p.get(key), key)
        uri(p.get("materialEventId"))
    if kind == "MOTOR_SHIPPED":
        for key in ("shipmentId", "customer", "destination"):
            text(p.get(key), key)
        uri(p.get("assemblyEventId"))
    return e


def encode_event(native, record_time):
    validate_native(native); timestamp(record_time)
    event = dict(type="ObjectEvent", eventID=native["eventId"], eventTime=native["occurredAt"],
                 eventTimeZoneOffset="+00:00", recordTime=record_time, action="OBSERVE",
                 epcList=[motor_uri(native["motorSerial"])], bizStep=NS + "event/" + native["eventType"],
                 trace={k: copy.deepcopy(v) for k, v in native.items() if k not in ("eventId", "occurredAt")})
    if native["eventType"] in ("COMPONENT_INSTALLED", "COMPONENT_REMOVED"):
        removed = native["eventType"] == "COMPONENT_REMOVED"
        event.pop("epcList")
        event.update(type="AssociationEvent", parentID=motor_uri(native["motorSerial"]),
                     childEPCs=[component_uri(native["payload"], removed)],
                     action="DELETE" if removed else "ADD", bizStep="disassembling" if removed else "assembling")
    return event


def encode_document(events, record_time):
    return {"@context": copy.deepcopy(CONTEXT), "type": "EPCISDocument", "schemaVersion": "2.0",
            "creationDate": record_time, "epcisBody": {"eventList": [encode_event(e, record_time) for e in events]}}


def decode(raw):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= 2_000_000:
        raise ValidationFailure("Expected bounded original document bytes")
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValidationFailure("Duplicate JSON key")
            out[key] = value
        return out
    try:
        doc = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValidationFailure("Nonfinite JSON")))
        VALIDATOR.validate(doc)
        timestamp(doc["creationDate"])
        native = []
        for event in doc["epcisBody"]["eventList"]:
            if not isinstance(event.get("trace"), dict):
                raise ValidationFailure("Missing private trace profile")
            e = copy.deepcopy(event["trace"])
            e.update(eventId=event.get("eventID"), occurredAt=event.get("eventTime"))
            validate_native(e)
            if event != encode_event(e, event.get("recordTime")):
                raise ValidationFailure("Contradictory or unsupported EPCIS core/trace representation")
            native.append(e)
        if len({e["eventId"] for e in native}) != len(native):
            raise ValidationFailure("Duplicate event ID in document")
        return doc, native
    except ValidationFailure:
        raise
    except Exception as exc:
        # Boundary guarantees a typed rejection, never a partially accepted document.
        raise ValidationFailure(f"Invalid EPCIS profile: {type(exc).__name__}") from exc
