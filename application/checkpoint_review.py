"""Decision-change review shown before a checkpoint candidate can be accepted. Read-only: it never evaluates, never appends to the journal.

Uses the same identity semantics (application.lot_identity) as the capture commands, the snapshot/eligibility read model and the API.
Acknowledgement is an operator assertion on this host: NOT independent authentication, NOT proof of the physical identity of any bearing,
and not a trust anchor. Identity-unsafe exclusions are refused regardless of acknowledgement.
"""
from . import lot_identity as lots

PART = "BR-6205"
EXCLUDED = "EXCLUDED_WITH_EVIDENCE"
RELEASE = "RELEASE_ELIGIBLE"


def _published(records, upto):
    out = {}
    for n, (kind, p) in enumerate(records, 1):
        if n > upto:
            break
        if kind == "EVALUATION" and "decision" in p:
            out[p["context"]["motor"]] = p["decision"]
    return out


def build_review(app, prior_body, candidate_body):
    records = app.audit.verify(copy_records=False)
    before, after = _published(records, prior_body["sequence"]), _published(records, candidate_body["sequence"])
    policy = app.policy()
    base = lots.policy_findings(app.registry, policy, PART) if policy else []
    rows = []
    for motor in sorted(after):
        d = after[motor]
        wm = app.ledger.watermark(motor)
        events = app.ledger.snapshot(motor, wm)[0]["events"]
        found = base + lots.motor_findings(app.registry, events, policy, PART)
        old = before.get(motor)
        effective = "RECALL_HOLD" if (found and d["operationalAction"] == RELEASE) else d["operationalAction"]
        row = dict(motor=motor, evaluatorFinding=d["evidenceFinding"], evaluatorAction=d["operationalAction"], guardedAction=effective,
                   previousEvaluatorFinding=old and old["evidenceFinding"], previousEvaluatorAction=old and old["operationalAction"],
                   reasonCodes=d["reasonCodes"], evidenceEventIds=d["evidenceEventIds"], identityStatus="NOT_ESTABLISHED" if found else "ESTABLISHED_LOCAL_REGISTRY",
                   identityFindings=found)
        row["newlyExcluded"] = d["evidenceFinding"] == EXCLUDED and (old is None or old["evidenceFinding"] != EXCLUDED)
        row["newlyReleaseEligible"] = effective == RELEASE and (old is None or old["operationalAction"] != RELEASE)
        row["newlyHeld"] = effective != RELEASE and (old is None or old["operationalAction"] == RELEASE or old["evidenceFinding"] != d["evidenceFinding"])
        row["identityUnsafeExclusion"] = bool(found) and (d["evidenceFinding"] == EXCLUDED or d["operationalAction"] == RELEASE)
        rows.append(row)
    return dict(
        trust="Acknowledgement is an operator assertion on this host. It is not independent authentication and not proof of the physical identity of any bearing.",
        registry=app.registry.meta(), priorSequence=prior_body["sequence"], candidateSequence=candidate_body["sequence"], rows=rows,
        requiresAcknowledgement=[r["motor"] for r in rows if (r["newlyExcluded"] or r["newlyReleaseEligible"]) and not r["identityUnsafeExclusion"]],
        refusedForIdentity=[r["motor"] for r in rows if r["identityUnsafeExclusion"]])
