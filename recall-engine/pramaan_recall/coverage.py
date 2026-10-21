"""Capture-session coverage: mandatory-capture sources and source outages."""


def mandatory_sources(coverage, op):
    out = set()
    for m in coverage["mandatoryCapture"]:
        o = m["operation"]
        if o == op or (o.endswith("*") and op.startswith(o[:-1])):
            out.update(m["sources"])
    return out


def outages(sessions, coverage, horizon):
    """Gaps between consecutive capture sessions of a mandatory-capture source.

    Only outages that began at or before `horizon` (latest visible recordedAt)
    are reported. Any such outage may touch any slot (conservative).
    """
    if horizon is None:
        return []
    mand = {s for m in coverage["mandatoryCapture"] for s in m["sources"]}
    by = {}
    for s in sessions:
        if s["sourceId"] in mand:
            by.setdefault(s["sourceId"], []).append((s["from"], s["to"]))
    out = []
    for src, spans in by.items():
        spans.sort()
        for (_, a_to), (b_from, _) in zip(spans, spans[1:]):
            if b_from > a_to and a_to <= horizon:
                out.append({"sourceId": src, "from": a_to, "to": b_from})
    return out
