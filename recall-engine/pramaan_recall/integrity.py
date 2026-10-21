"""Source-sequence validation and event-order integrity.

Every issue becomes an unboundable material gap on every slot: missing or
disordered evidence is never read as evidence of safety.
"""
import re

_TS = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

REASON = {
    "SOURCE_SEQUENCE_GAP": "SOURCE_SEQUENCE_GAP",
    "EVENT_ORDER": "EVENT_ORDER_INTEGRITY",
    "EVENT_INVALID": "EVENT_INTEGRITY_VIOLATION",
}


def check(visible, sessions, watermark):
    """-> list of {kind, detail, ...}; kind is a key of REASON."""
    issues = []

    def add(kind, detail, **kw):
        issues.append(dict(kind=kind, detail=detail, **kw))

    by_id, per_source = {}, {}
    for e in visible:
        eid = e["eventId"]
        if eid in by_id:
            add("EVENT_INVALID", "duplicate eventId", eventId=eid)
        by_id[eid] = e
        for f in ("occurredAt", "recordedAt"):
            if not _TS.match(str(e.get(f))):
                add("EVENT_INVALID", f"malformed {f}", eventId=eid)
        per_source.setdefault(e["sourceId"], []).append(e)

    for src, evs in per_source.items():
        seqs = [e["sourceSeq"] for e in evs]
        if len(seqs) != len(set(seqs)):
            add("EVENT_INVALID", "duplicate sourceSeq", sourceId=src)
        missing = sorted(set(range(1, watermark.get(src, 0) + 1)) - set(seqs))
        if missing:
            add("SOURCE_SEQUENCE_GAP", f"missing seq {missing}", sourceId=src)
        ordered = sorted(evs, key=lambda e: e["sourceSeq"])
        for a, b in zip(ordered, ordered[1:]):
            if b["recordedAt"] < a["recordedAt"]:
                add("EVENT_ORDER", "recordedAt decreases with sourceSeq",
                    sourceId=src, eventId=b["eventId"])

    spans = {}
    for s in sessions:
        spans.setdefault(s["sourceId"], []).append((s["from"], s["to"]))
    for e in visible:
        if e["recordedAt"] < e["occurredAt"]:
            add("EVENT_ORDER", "recordedAt before occurredAt", eventId=e["eventId"])
        if not any(a <= e["recordedAt"] <= b for a, b in spans.get(e["sourceId"], [])):
            add("EVENT_INVALID", "recorded outside any capture session",
                eventId=e["eventId"], sourceId=e["sourceId"])
        t = e.get("supersedesEventId")
        if t:
            tgt = by_id.get(t)
            if tgt is None:
                add("EVENT_INVALID", f"supersedes unknown event {t}", eventId=e["eventId"])
            elif tgt["recordedAt"] > e["recordedAt"]:
                add("EVENT_ORDER", f"supersedes later-recorded event {t}",
                    eventId=e["eventId"])
    return issues
