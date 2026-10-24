"""Decision-change review shown before a checkpoint candidate can be accepted. Read-only: it never evaluates, never appends to the journal.

Uses the same identity semantics (application.lot_identity) as the capture commands, the snapshot/eligibility read model and the API.
Acknowledgement is an operator assertion on this host: NOT independent authentication, NOT proof of the physical identity of any bearing,
and not a trust anchor. Identity-unsafe exclusions are refused regardless of acknowledgement.
"""
from . import lot_identity as lots
from . import registry_binding

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


def registry_change(app, prior_path):
    """Registry review against the registry accepted with the CURRENT checkpoint. Only a V3 checkpoint's in-body digest is a verified basis;
    a legacy (V2/V1) checkpoint never verified any registry, so the whole live registry is unreviewed and acknowledgement is always required."""
    if prior_path is None:
        return dict(priorBinding="NOT_SUPPLIED", changes=[], requiresAcknowledgement=True, priorRegistry=None)
    doc, digest, basis = registry_binding.prior_registry(prior_path)
    if basis == "NONE":
        return dict(priorBinding="MISSING_OR_UNREADABLE", changes=[], requiresAcknowledgement=True, priorRegistry=None,
                    note="No registry was ever bound to the current checkpoint; the whole live registry is unreviewed.")
    changes = registry_binding.diff(doc, app.registry.document) if doc is not None else []
    legacy = basis == "LEGACY_SIDECAR_UNVERIFIED"
    out = dict(priorBinding=basis, changes=changes, requiresAcknowledgement=legacy or digest != app.registry.digest,
               priorRegistry=dict(digest=digest, **registry_binding._meta(doc)) if doc is not None else dict(digest=digest))
    if legacy:
        out["note"] = "The current checkpoint is a legacy format; its sidecar was never inside a verified boundary, so this difference is advisory and acknowledgement is required."
    elif doc is None:
        out["note"] = "Only the registry digest is verified for the current checkpoint; no document is available to show a field-level difference."
    return out


def build_review(app, prior_body, candidate_body, prior_path=None):
    prior_doc = registry_binding.prior_registry(prior_path)[0] if prior_path is not None else None
    prior_registry = lots.LotRegistry(prior_doc) if prior_doc is not None else None
    regchg = registry_change(app, prior_path)
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
        broken = lots.integrity_findings(events)
        under_prior = None
        if prior_registry is not None and policy:
            under_prior = lots.policy_findings(prior_registry, policy, PART) + lots.motor_findings(prior_registry, events, policy, PART)
        resolved_by_registry = bool(under_prior) and not found        # a registry change (e.g. retroactive registration) made the identity findings disappear
        if prior_registry is None and regchg["requiresAcknowledgement"] and not found and d["operationalAction"] == RELEASE:
            resolved_by_registry = True                                # prior registry unknown: cannot prove the registry did not create this eligibility, so it is acknowledged individually
        old = before.get(motor)
        effective = "RECALL_HOLD" if ((found or broken) and d["operationalAction"] == RELEASE) else d["operationalAction"]
        row = dict(motor=motor, evaluatorFinding=d["evidenceFinding"], evaluatorAction=d["operationalAction"], guardedAction=effective,
                   previousEvaluatorFinding=old and old["evidenceFinding"], previousEvaluatorAction=old and old["operationalAction"],
                   reasonCodes=d["reasonCodes"], evidenceEventIds=d["evidenceEventIds"], identityStatus="NOT_ESTABLISHED" if found else "ESTABLISHED_LOCAL_REGISTRY",
                   identityFindings=found, integrityStatus="OPERATION_INTERRUPTED" if broken else "OPERATIONALLY_CONSISTENT", integrityFindings=broken,
                   identityFindingsUnderPriorRegistry=under_prior, identityResolvedByRegistryChange=resolved_by_registry)
        row["newlyExcluded"] = d["evidenceFinding"] == EXCLUDED and (old is None or old["evidenceFinding"] != EXCLUDED)
        row["newlyReleaseEligible"] = effective == RELEASE and (old is None or old["operationalAction"] != RELEASE)
        row["newlyHeld"] = effective != RELEASE and (old is None or old["operationalAction"] == RELEASE or old["evidenceFinding"] != d["evidenceFinding"])
        row["identityUnsafeExclusion"] = bool(found or broken) and (d["evidenceFinding"] == EXCLUDED or d["operationalAction"] == RELEASE)
        rows.append(row)
    return dict(
        trust="Acknowledgement is an operator assertion on this host. It is not independent authentication and not proof of the physical identity of any bearing.",
        registry=app.registry.meta(), registryChange=regchg, priorSequence=prior_body["sequence"], candidateSequence=candidate_body["sequence"], rows=rows,
        requiresAcknowledgement=[r["motor"] for r in rows if (r["newlyExcluded"] or r["newlyReleaseEligible"] or r["identityResolvedByRegistryChange"]) and not r["identityUnsafeExclusion"]],
        refusedForIdentity=[r["motor"] for r in rows if r["identityUnsafeExclusion"]])
