"""Recall-policy exposure on top of the structural slot ledger.

P1 (CURRENT_INSTALLATION): is an affected bearing installed in a scoped slot now?
P2 (HISTORICAL_OPERATION): was one ever installed there, and has the required
post-recall damage inspection (and remediation) been completed?

Rule of thumb throughout: missing or unverifiable evidence never produces
EXCLUDED_WITH_EVIDENCE. Risk-increasing unverified claims hold; risk-decreasing
unverified claims are ignored (and queued for review).
"""
from .ledger import HARD_CONFLICTS, same_item

EXCL, AFF, UNRES = "EXCLUDED_WITH_EVIDENCE", "AFFECTED", "UNRESOLVED"
SEVERITY = {EXCL: 0, UNRES: 1, AFF: 2}

GAP_REASON = {
    "SOURCE_OUTAGE": "MATERIAL_CAPTURE_GAP", "UNRESOLVED_EXCEPTION": "MATERIAL_CAPTURE_GAP",
    "SOURCE_SEQUENCE_GAP": "SOURCE_SEQUENCE_GAP", "EVENT_ORDER": "EVENT_ORDER_INTEGRITY",
    "EVENT_INVALID": "EVENT_INTEGRITY_VIOLATION",
    "WORK_ORDER_OBLIGATION_UNMET": "WORK_ORDER_UNRECONCILED",
    "WORK_ORDER_MISSING": "WORK_ORDER_UNRECONCILED",
}
CONFLICT_REASON = {
    "DOUBLE_OCCUPANCY": "DOUBLE_OCCUPANCY",
    "REMOVAL_OBSERVATION_MISMATCH": "REMOVAL_OBSERVATION_MISMATCH",
    "REMOVAL_LINK_MISMATCH": "REMOVAL_RECORD_INCONSISTENT",
    "REMOVAL_NOT_LINKED": "REMOVAL_RECORD_INCONSISTENT",
    "REMOVAL_FROM_EMPTY": "REMOVAL_RECORD_INCONSISTENT",
    "VERIFIED_STATE_MISMATCH": "VERIFIED_STATE_MISMATCH",
    "REMOVAL_SLOT_LABEL_MISMATCH": "REMOVAL_SLOT_LABEL_MISMATCH",
    "REMOVAL_SERIAL_IN_OTHER_SLOT": "REMOVAL_SERIAL_IN_OTHER_SLOT",
}


def is_affected(policy, o):
    return bool(o) and o.get("part") == policy["affectedPart"] \
        and o.get("lot") in policy["affectedLots"]


def _add(lst, *codes):
    for c in codes:
        if c not in lst:
            lst.append(c)


def claim_direction(policy, lc):
    c, o = is_affected(policy, lc["claim"]), is_affected(policy, lc["superseded"])
    return "INCREASING" if c and not o else "DECREASING" if o and not c else "NEUTRAL"


def records_may_be_affected(policy, s):
    cands = list(s.candidates) + ([s.occupant] if s.occupant else [])
    cands += [lc["superseded"] for lc in s.late_claims]
    return any(is_affected(policy, o) for o in cands)


def material_gaps(s):
    return [g for g in s.gaps if g["materiality"] == "MATERIAL"]


def completeness_reasons(policy, s):
    """Evidence-completeness reasons (gaps, unverified late claims) for a slot."""
    r = []
    for g in material_gaps(s):
        _add(r, GAP_REASON[g["kind"]])
    if s.verified is None:
        for lc in s.late_claims:
            d = claim_direction(policy, lc)
            if d == "INCREASING":
                _add(r, "LATE_CLAIM_RISK_INCREASING")
            elif d == "DECREASING":
                _add(r, "LATE_CLAIM_RISK_DECREASING_NOT_APPLIED")
    return r


# ---------------------------------------------------------------- P1 -----
def p1_slot(policy, s, siblings, cfg):
    reasons, flags, review = [], [], False
    v = s.verified
    if v:
        if is_affected(policy, v):
            _add(reasons, "VERIFIED_AFFECTED_LOT_PRESENT")
            if any(lc["corroboratedBy"] == v["eventId"] for lc in s.late_claims):
                _add(reasons, "CORROBORATED_BY_VERIFICATION")
            return dict(finding=AFF, reasons=reasons, review=False, flags=flags)
        if records_may_be_affected(policy, s):
            return dict(finding=UNRES, review=True, flags=flags,
                        reasons=["VERIFIED_STATE_MISMATCH_RISK_DECREASING"])
        occ, trusted = v, True
        conflicts, claims = [], []          # settled by independent observation
    else:
        occ, trusted = s.occupant, s.trusted
        conflicts = [c for c in s.conflicts if c["kind"] in HARD_CONFLICTS]
        claims = s.late_claims

    blockers = []
    for c in conflicts:
        _add(blockers, CONFLICT_REASON[c["kind"]], "CURRENT_STATE_UNVERIFIED")
    for lc in claims:
        d = claim_direction(policy, lc)
        if d == "INCREASING":
            _add(blockers, "LATE_CLAIM_RISK_INCREASING")
            review = True
        else:                                # never release on an unverified claim
            occ, trusted = lc["superseded"], lc["trustedBefore"]
            if d == "DECREASING":
                _add(reasons, "LATE_CLAIM_RISK_DECREASING_NOT_APPLIED")
                review = True
    for g in material_gaps(s):
        _add(blockers, GAP_REASON[g["kind"]])
    if not blockers and not trusted:
        if s.baseline == "UNKNOWN":
            _add(blockers, "NO_TRUSTED_BASELINE", "CURRENT_STATE_UNVERIFIED")
        else:
            _add(blockers, "CURRENT_STATE_UNVERIFIED", "UNTRUSTED_SOURCE_CLAIM")
    if blockers:
        return dict(finding=UNRES, reasons=reasons + blockers, review=True, flags=flags)

    # An uncleared ambiguous attribution of an affected-lot removal claimed for this
    # slot means the affected part may still be in it. Only CORROBORATED_SLOT clears it.
    pending = [a for a in s.ambiguities if not a["cleared"] and is_affected(policy, a["observed"])]         if cfg.slot_attribution else []
    if s.state == "EMPTY" and v is None:
        if pending:
            return dict(finding=UNRES, review=True, flags=flags,
                        reasons=reasons + ["AMBIGUOUS_SLOT_ATTRIBUTION"])
        return dict(finding=EXCL, reasons=reasons + ["SLOT_EMPTY"], review=review, flags=flags)
    if is_affected(policy, occ):
        return dict(finding=AFF, reasons=reasons + ["AFFECTED_LOT_INSTALLED"],
                    review=review, flags=flags)
    if pending:
        return dict(finding=UNRES, review=True, flags=flags,
                    reasons=reasons + ["AMBIGUOUS_SLOT_ATTRIBUTION"])

    replaced = any(is_affected(policy, x) for x in s.removals) or \
        any(is_affected(policy, x) and x["kind"] == "REMOVAL_OBSERVED" for x in s.exposures)
    if replaced and not v and not cfg.slot_attribution and _lot_ambiguous(policy, s, siblings):
        if cfg.strict_lot_ambiguity:
            return dict(finding=UNRES, review=True, flags=flags,
                        reasons=reasons + ["LOT_LEVEL_SLOT_AMBIGUITY"])
        flags.append("KNOWN_LIMITATION_LOT_LEVEL_SLOT_AMBIGUITY")
    if replaced:
        _add(reasons, "REPLACED_WITH_UNAFFECTED_LOT")
    elif s.baseline == "AS_BUILT_VALIDATED":
        _add(reasons, "AS_BUILT_UNAFFECTED_LOT")
    else:
        _add(reasons, "VERIFIED_UNAFFECTED_LOT")
    if any(g["materiality"] == "BOUNDED" for g in s.gaps):
        _add(reasons, "GAP_BOUNDED_BY_VERIFICATION")
    return dict(finding=EXCL, reasons=reasons, review=review, flags=flags)


def _lot_ambiguous(policy, s, siblings):
    """Exclusion rests on a LOT-level removal scan whose slot attribution cannot be
    told apart from a sibling slot holding the same lot (no serial, no verification)."""
    for r in s.removals:
        if is_affected(policy, r) and r.get("granularity") != "SERIAL":
            for t in siblings:
                if t is not s and t.occupant and same_item(t.occupant, r):
                    return True
    return False


# ---------------------------------------------------------------- P2 -----
def inspection_status(policy, active, slot):
    di = policy.get("damageInspection")
    if not di:
        return None
    seen = []
    for e in active:
        p = e["payload"]
        if e["eventType"] != "INSPECTION_RECORDED" or p.get("protocolId") != di["protocolId"]:
            continue
        if e["occurredAt"] <= di["mustOccurAfter"]:
            continue
        if "scope" in p and not any(str(x).startswith(slot) for x in p["scope"]):
            continue
        qualified = di["inspectorQualification"] in p.get("inspectorQualifiedFor", [])
        if not qualified:
            seen.append((e["occurredAt"], "INVALID", e["eventId"]))
        elif p.get("result") == di["requiredResult"]:
            seen.append((e["occurredAt"], "PASSED", e["eventId"]))
        else:
            seen.append((e["occurredAt"], "FAILED", e["eventId"]))
    seen.sort()
    ids = [x[2] for x in seen]
    decisive = [x for x in seen if x[1] in ("PASSED", "FAILED")]
    if decisive:
        return dict(status=decisive[-1][1], eventIds=ids)
    return dict(status="INVALID" if seen else "MISSING", eventIds=ids)


def exposure_confirmed(policy, s):
    return any(is_affected(policy, x) and x["trusted"] for x in s.exposures) or \
        any(is_affected(policy, v) and v["trusted"] for v in s.verifications)


def p2_slot(policy, s, p1v, insp):
    ec = completeness_reasons(policy, s)
    if exposure_confirmed(policy, s):
        reasons = ["HISTORICAL_EXPOSURE_CONFIRMED"]
        st = insp["status"]
        if st in ("MISSING", "INVALID", "FAILED"):
            _add(reasons, {"MISSING": "DAMAGE_INSPECTION_MISSING",
                           "INVALID": "DAMAGE_INSPECTION_INVALID",
                           "FAILED": "DAMAGE_INSPECTION_FAILED"}[st], *ec)
            return dict(finding=AFF, reasons=reasons, review=False, flags=[], inspection=insp)
        _add(reasons, "DAMAGE_INSPECTION_PASSED")
        rest = [r for r in p1v["reasons"] if r != "REPLACED_WITH_UNAFFECTED_LOT"]
        if p1v["finding"] == EXCL:
            _add(reasons, "EXPOSURE_REMEDIATED", *rest)
            return dict(finding=EXCL, reasons=reasons, review=p1v["review"], flags=[], inspection=insp)
        if p1v["finding"] == AFF:
            _add(reasons, *rest)
            return dict(finding=AFF, reasons=reasons, review=False, flags=[], inspection=insp)
        _add(reasons, "REMEDIATION_COMPLETENESS_UNCERTAIN", *rest)
        return dict(finding=UNRES, reasons=reasons, review=True, flags=[], inspection=insp)

    # no confirmed exposure: an exclusion needs positive evidence of none
    claimed = any(is_affected(policy, x) for x in s.exposures) or \
        any(is_affected(policy, lc["claim"]) for lc in s.late_claims)
    if claimed:
        return dict(finding=UNRES, reasons=["LATE_CLAIM_RISK_INCREASING"], review=True, flags=[])
    if p1v["finding"] == EXCL and not s.gaps and s.trusted:
        return dict(finding=EXCL, reasons=["NO_HISTORICAL_EXPOSURE"], review=p1v["review"], flags=[])
    reasons = ["EXPOSURE_UNKNOWN"]
    if p1v["finding"] == EXCL:             # state re-established, history not recovered
        _add(reasons, "HISTORY_GAP_NOT_RECOVERED_BY_VERIFICATION")
    else:
        _add(reasons, *p1v["reasons"])
    return dict(finding=UNRES, reasons=reasons, review=True, flags=[])


# ------------------------------------------------------------ decision ---
def decide(policy, slots, active, cfg):
    names = policy["affectedSlots"]
    rel = [slots[n] for n in names]
    allslots = list(slots.values())
    per, evidence = {}, []
    for s in rel:
        p1v = p1_slot(policy, s, allslots, cfg)
        if policy["exposureBasis"] == "CURRENT_INSTALLATION":
            per[s.name] = p1v
        elif policy["exposureBasis"] == "HISTORICAL_OPERATION":
            insp = inspection_status(policy, active, s.name)
            per[s.name] = p2_slot(policy, s, p1v, insp)
            evidence += insp["eventIds"] if exposure_confirmed(policy, s) else []
        else:
            raise ValueError(f"unknown exposureBasis {policy['exposureBasis']}")

    finding = max((v["finding"] for v in per.values()), key=SEVERITY.get)
    reasons, flags, review = [], [], finding == UNRES
    for v in per.values():
        _add(reasons, *v["reasons"])
        _add(flags, *v["flags"])
        review = review or v["review"]
    if any(g["materiality"] == "MATERIAL" for s in allslots if s.name not in names for g in s.gaps) \
            and not any(material_gaps(s) for s in rel):
        _add(reasons, "IRRELEVANT_SLOT_GAP")
    for s in rel:
        if any(c["kind"] in HARD_CONFLICTS and CONFLICT_REASON[c["kind"]] not in reasons
               for c in s.conflicts):
            _add(flags, "SLOT_RECORD_CONFLICT")
    return dict(finding=finding, reasons=reasons, flags=flags, review=review,
                perSlot=per, extraEvidence=evidence)
