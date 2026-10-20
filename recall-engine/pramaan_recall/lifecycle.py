"""Decision lifecycle across watermarks: versioning, supersession, hold, notification.

Operational action is derived from the finding, so a withdrawn exclusion is a
RECALL_HOLD the moment the superseding decision exists. Nothing here releases
anything: RELEASE_ELIGIBLE only means "no recall-relevant evidence to hold on".
"""
from .engine import Config, evaluate
from .policy import EXCL

_SKIP_TRIGGER = ("WORK_ORDER_OPENED", "WORK_ORDER_CLOSED")


def _signature(d):
    return ((d["evidenceFinding"], d["operationalAction"], d["reviewRequired"]),
            tuple(sorted(d["reasonCodes"])),
            tuple(sorted((n, s["reconciliation"], s.get("currentLotPerRecords"))
                         for n, s in d["slots"].items())))


def evaluate_series(case, policy, coverage, watermarks, config=None, communicated=()):
    """Evaluate one policy at successive watermarks (in the order given).

    Returns one entry per watermark. A new decision version is issued only when
    the outcome changes; unchanged entries point at the standing decision.
    Earlier decisions are never edited or removed.
    """
    cfg = config or Config()
    suffix = policy["policyId"].split("/")[-1]
    by_id = {e["eventId"]: e for e in case["events"]}
    out, prev, prev_wm, n = [], None, {}, 0
    for wm in watermarks:
        d = evaluate(case, policy, coverage, wm, cfg)
        if prev is not None and _signature(d) == _signature(prev):
            out.append(dict(prev, watermark=d["watermark"], unchanged=True))
            prev_wm = wm
            continue
        n += 1
        d["decisionId"] = f"D-{case['caseId']}-{suffix}-v{n}"
        d["version"], d["unchanged"] = n, False
        d["supersedesDecisionId"] = prev["decisionId"] if prev else None
        new = []
        if prev:
            new = [i for i in d["evidenceEventIds"]
                   if by_id[i]["sourceSeq"] > prev_wm.get(by_id[i]["sourceId"], 0)
                   and by_id[i]["eventType"] not in _SKIP_TRIGGER]
        d["triggerEventId"] = new[-1] if new else None
        if prev is not None and prev["evidenceFinding"] == EXCL and d["evidenceFinding"] != EXCL:
            d["reasonCodes"].append("PRIOR_EXCLUSION_WITHDRAWN")
            d["precautionaryHold"] = True
            d["notificationObligation"] = dict(
                required=True, reason="PRIOR_EXCLUSION_WITHDRAWN",
                appliesIfDecisionCommunicated=prev["decisionId"],
                communicated=(prev["decisionId"] in set(communicated)) if communicated else None)
        out.append(d)
        prev, prev_wm = d, wm
    return out
