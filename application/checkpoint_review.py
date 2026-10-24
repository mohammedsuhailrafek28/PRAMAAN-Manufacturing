"""Decision-change review shown before a checkpoint candidate can be accepted. Read-only: it never evaluates, never appends to the journal.

Uses the same identity semantics (application.lot_identity) as the capture commands, the snapshot/eligibility read model and the API.
Acknowledgement is an operator assertion on this host: NOT independent authentication, NOT proof of the physical identity of any bearing,
and not a trust anchor. Identity-unsafe exclusions are refused regardless of acknowledgement.
"""
from . import lot_identity as lots
from . import registry_binding

PART = "BR-6205"

# Scoped containment of an UNVERIFIED SIGHTING (research; owner decision 3). A sighting is a per-motor claim about the bearing in one slot. Its motor stays
# held (the identity guard never lets it be release-eligible). The candidate checkpoint may still be accepted for UNRELATED motors only when every rule below
# is established from the recorded events; if any rule cannot be established the whole candidate is refused, exactly as before.
CONTAINABLE_SOURCES = {"OBSERVATION"}                              # only a sighting; install/removal/policy/binding findings are never contained
CONTAINABLE_REASONS = {"UNREGISTERED", "SENTINEL", "MALFORMED"}    # not a conflicting, withdrawn, expired, wrong-part or alias string: those concern the registry
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


def _strings(events):
    """Every lot-like string a motor's events carry, in the comparison form used for look-alike detection."""
    out = set()
    for e in events:
        for key in ("lot", "observedLot"):
            v = e["payload"].get(key)
            if isinstance(v, str) and v.strip():
                out.add(lots._skeleton(v))
    return out


def containment(motor, found, broken, base, binding_ok, strings_by_motor, action_after_guard):
    """Decide whether this motor's identity findings are isolated to this motor. Returns (contained, obligations). Pure and conservative:
    every obligation is evaluated, a single failure means NOT contained (the wider refusal is preserved)."""
    ob = []

    def check(name, ok, detail=""):
        ob.append(dict(obligation=name, holds=bool(ok), detail=detail))

    check("HAS_FINDINGS_TO_CONTAIN", bool(found))
    check("ONLY_SIGHTING_FINDINGS", bool(found) and all(f["source"] in CONTAINABLE_SOURCES for f in found), sorted({f["source"] for f in found}))
    check("ONLY_UNESTABLISHED_STRINGS", bool(found) and all(f["reason"] in CONTAINABLE_REASONS for f in found), sorted({f["reason"] for f in found}))
    check("NO_INTEGRITY_FINDINGS_ON_MOTOR", not broken)
    check("NO_RECALL_POLICY_FINDINGS", not base)
    check("REGISTRY_BINDING_OK", binding_ok)
    own = {lots._skeleton(f["lot"]) for f in found if isinstance(f.get("lot"), str) and f["lot"].strip()}
    others = set().union(*[v for m, v in strings_by_motor.items() if m != motor]) if len(strings_by_motor) > 1 else set()
    shared = sorted(own & others)
    check("STRING_NOT_SHARED_WITH_ANOTHER_MOTOR", not shared, shared)
    near_in_use = sorted({r for f in found for r in f.get("resembles", []) if lots._skeleton(r) in others})
    check("NO_LOOKALIKE_OF_A_LOT_IN_USE_ELSEWHERE", not near_in_use, near_in_use)
    check("MOTOR_REMAINS_HELD", action_after_guard != RELEASE, action_after_guard)
    return all(o["holds"] for o in ob), ob


def build_review(app, prior_body, candidate_body, prior_path=None, candidate_binding=None):
    prior_doc = registry_binding.prior_registry(prior_path)[0] if prior_path is not None else None
    prior_registry = lots.LotRegistry(prior_doc) if prior_doc is not None else None
    regchg = registry_change(app, prior_path)
    records = app.audit.verify(copy_records=False)
    before, after = _published(records, prior_body["sequence"]), _published(records, candidate_body["sequence"])
    policy = app.policy()
    base = lots.policy_findings(app.registry, policy, PART) if policy else []
    rows = []
    strings_by_motor = {u["serial"]: _strings(app.ledger.snapshot(u["serial"], app.ledger.watermark(u["serial"]))[0]["events"])
                        for u in app.db.execute("SELECT serial FROM app_units")}
    for motor in sorted(after):
        d = after[motor]
        wm = app.ledger.watermark(motor)
        events = app.ledger.snapshot(motor, wm)[0]["events"]
        own_found = lots.motor_findings(app.registry, events, policy, PART)
        found = base + own_found
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
        contained, obligations = containment(motor, own_found, broken, base, bool(candidate_binding and candidate_binding.get("status") == "OK"), strings_by_motor, effective)
        row["containment"] = dict(contained=bool(row["identityUnsafeExclusion"] and contained), obligations=obligations,
                                  note="Contained means: this motor stays held and the candidate may still renew the checkpoint for unrelated motors. It is not clearance.")
        rows.append(row)
    return dict(
        trust="Acknowledgement is an operator assertion on this host. It is not independent authentication and not proof of the physical identity of any bearing.",
        registry=app.registry.meta(), registryChange=regchg, priorSequence=prior_body["sequence"], candidateSequence=candidate_body["sequence"], rows=rows,
        requiresAcknowledgement=[r["motor"] for r in rows if ((r["newlyExcluded"] or r["newlyReleaseEligible"] or r["identityResolvedByRegistryChange"]) and not r["identityUnsafeExclusion"]) or r["containment"]["contained"]],
        containedMotors=[r["motor"] for r in rows if r["containment"]["contained"]],
        refusedForIdentity=[r["motor"] for r in rows if r["identityUnsafeExclusion"] and not r["containment"]["contained"]])
