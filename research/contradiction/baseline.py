"""B0: the simple checks a data-quality script would run. No supplier scope, no coverage, no supersession, no time uncertainty."""
import hashlib
import json


def b0(f):
    """-> list of flagged groups {check, eventIds}. Naive on purpose: it is the baseline the candidate must beat."""
    events, groups = f["events"], []
    by_id = {e["eventId"]: e for e in events}
    # (a) duplicate serial: any serial that appears in more than one install event
    serials = {}
    for e in events:
        if e["eventType"] == "COMPONENT_INSTALLED" and e["payload"].get("serial"):
            serials.setdefault(e["payload"]["serial"], []).append(e["eventId"])
    for s, ids in sorted(serials.items()):
        if len(ids) > 1:
            groups.append(dict(check="DUPLICATE_SERIAL", eventIds=sorted(ids)))
    # (b) timestamps: recorded before it occurred; evidence digest that does not match its payload
    for e in events:
        if e["recordedAt"] < e["occurredAt"]:
            groups.append(dict(check="TIMESTAMP_ORDER", eventIds=[e["eventId"]]))
        for r in e.get("evidenceRefs", []):
            if r.startswith("sha256:") and r != "sha256:" + hashlib.sha256(json.dumps(e["payload"], sort_keys=True).encode()).hexdigest():
                groups.append(dict(check="HASH_MISMATCH", eventIds=[e["eventId"]]))
    # (c) genealogy: a removal must reference an existing install of the same motor and slot, observed serial must match it,
    #     and it cannot happen before that install
    for e in events:
        if e["eventType"] != "COMPONENT_REMOVED":
            continue
        p, tgt = e["payload"], by_id.get(e["payload"].get("endsInstallEventId"))
        if tgt is None:
            groups.append(dict(check="GENEALOGY_BROKEN_LINK", eventIds=[e["eventId"]]))
            continue
        if tgt["motorSerial"] != e["motorSerial"] or tgt["payload"].get("slot") != p.get("slot"):
            groups.append(dict(check="GENEALOGY_LOCATION", eventIds=sorted([e["eventId"], tgt["eventId"]])))
        elif p.get("observedSerial") and tgt["payload"].get("serial") and p["observedSerial"] != tgt["payload"]["serial"]:
            groups.append(dict(check="GENEALOGY_SERIAL", eventIds=sorted([e["eventId"], tgt["eventId"]])))
        elif e["occurredAt"] < tgt["occurredAt"]:
            groups.append(dict(check="GENEALOGY_ORDER", eventIds=sorted([e["eventId"], tgt["eventId"]])))
    return groups


def b0_impacted_motors(f, groups):
    """Baseline 'impact': every motor that owns a flagged event."""
    owner = {e["eventId"]: e["motorSerial"] for e in f["events"]}
    return sorted({owner[i] for g in groups for i in g["eventIds"]})
