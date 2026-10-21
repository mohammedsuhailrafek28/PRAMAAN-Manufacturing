"""Decision lifecycle v2: material revisions, no stale bodies, durable obligations.

The recall engine's own `evaluate_series` (lifecycle v1) keys a new version on finding, review,
reason codes and per-slot reconciliation only. It therefore (a) drops evidence, flag, attribution,
untrusted-observation and policy changes that leave those unchanged, (b) shows the previous body
under a newer watermark, and (c) compares the next evaluation with a version whose lifecycle-added
withdrawal markers the fresh evaluation can never have, which fabricates an identical version and
erases the precautionary hold and notification obligation.

This module keeps the engine untouched (the pure `evaluate` is called per watermark, so v1/v2/v3
semantics and replay are unchanged) and versions on a signature of everything the engine derived
from evidence, plus the policy identity. Issued versions are never recomputed.
"""
from . import engine_bridge
from .profile import digest

LIFECYCLE_VERSION = 2
EXCLUDED = "EXCLUDED_WITH_EVIDENCE"
_SKIP_TRIGGER = ("WORK_ORDER_OPENED", "WORK_ORDER_CLOSED")

# Everything the engine derived from evidence and configuration. Deliberately excluded:
# watermark, identifiers, version, supersession and trigger (lifecycle bookkeeping), and the
# lifecycle-added withdrawal markers (they describe a transition, not the evidence).
_MATERIAL = ("evidenceFinding", "operationalAction", "reviewRequired", "slots", "slotVerdicts", "slotAttribution",
             "untrustedObservations", "evidenceRefs", "integrityIssues", "assuranceWarnings", "identityGranularity",
             "workOrders", "policyId", "policyVersion", "recallId", "coverageDigest", "engineVersion", "semanticsProfile")
_SORTED = ("reasonCodes", "flags", "evidenceEventIds", "supersededEventIds")


def material_signature(decision, policy_digest):
    material = {k: decision.get(k) for k in _MATERIAL}
    material.update({k: sorted(decision.get(k) or []) for k in _SORTED})
    material["policyDigest"] = policy_digest
    return digest(material)


def obligation_id(motor, policy_digest, applies_to, created_by):
    return "OBL-" + digest(dict(motor=motor, policy=policy_digest, appliesTo=applies_to, createdBy=created_by))[:24]


def start_state(predecessor=None):
    """State carried between calls; stored with the series so issued versions are never recomputed."""
    return dict(standing=None, signature=None, previousWatermark={}, count=0, predecessor=predecessor)


def extend(case, policy, coverage, watermarks, config, state, *, policy_digest, revision=1, communicated=()):
    """Evaluate `watermarks` (oldest first) continuing `state`; returns (decisions, state).

    One decision per watermark. A watermark whose material signature equals the standing version's
    is reported with that version's identity but its own, freshly evaluated body and watermark
    (`unchanged`), so a current decision never shows stale evidence under a new watermark.
    """
    suffix = policy["policyId"].split("/")[-1]
    prefix = f"D-{case['caseId']}-{suffix}" + (f"-r{revision}" if revision > 1 else "")
    by_id = {e["eventId"]: e for e in case["events"]}
    state = dict(state)
    out = []
    for wm in watermarks:
        fresh = engine_bridge.evaluate(case, policy, coverage, wm, config)
        signature = material_signature(fresh, policy_digest)
        standing = state["standing"]
        if standing is not None and signature == state["signature"]:
            body = dict(fresh)
            body.update(decisionId=standing["decisionId"], version=standing["version"], unchanged=True,
                        supersedesDecisionId=standing["supersedesDecisionId"], triggerEventId=standing["triggerEventId"],
                        issuedAtWatermark=standing["watermark"], lifecycleVersion=LIFECYCLE_VERSION,
                        lifecycleSignature=signature)
            out.append(body)
            state["previousWatermark"] = wm
            continue
        before = standing or state["predecessor"]
        state["count"] += 1
        d = fresh
        d["decisionId"] = f"{prefix}-v{state['count']}"
        d["version"], d["unchanged"] = state["count"], False
        d["supersedesDecisionId"] = before["decisionId"] if before else None
        previous = state["previousWatermark"] if standing else {}
        new = [i for i in d["evidenceEventIds"]
               if by_id[i]["sourceSeq"] > previous.get(by_id[i]["sourceId"], 0)
               and by_id[i]["eventType"] not in _SKIP_TRIGGER] if before else []
        d["triggerEventId"] = new[-1] if new else None
        d["issuedAtWatermark"] = d["watermark"]
        d["lifecycleVersion"], d["lifecycleSignature"] = LIFECYCLE_VERSION, signature
        if before is not None and before["evidenceFinding"] == EXCLUDED and d["evidenceFinding"] != EXCLUDED:
            d["reasonCodes"].append("PRIOR_EXCLUSION_WITHDRAWN")
            d["precautionaryHold"] = True
            d["notificationObligation"] = dict(
                required=True, reason="PRIOR_EXCLUSION_WITHDRAWN",
                appliesIfDecisionCommunicated=before["decisionId"],
                communicated=(before["decisionId"] in set(communicated)) if communicated else None)
        out.append(d)
        state.update(standing=d, signature=signature, previousWatermark=wm)
    return out, state
