"""evaluate(): one policy, one motor history, one set of source watermarks."""
from dataclasses import dataclass

from . import coverage as cov
from . import integrity, ledger, policy as pol, workorders

ENGINE_VERSION = "phase1-0.1"
ENGINE_VERSION_SLOT_ATTRIBUTION = "phase1.1-slot-attribution"
ACTION = {pol.EXCL: "RELEASE_ELIGIBLE", pol.AFF: "RECALL_HOLD", pol.UNRES: "RECALL_HOLD"}


@dataclass(frozen=True)
class Config:
    # Treat an exclusion that rests on a LOT-level removal scan, while a sibling
    # slot holds the same lot, as UNRESOLVED. Off by default: the agreed
    # semantics (and the supplied expectations) accept lot-level identity.
    strict_lot_ambiguity: bool = False
    # Slot-attribution safety (opt-in; default keeps the original contract). Detects
    # AMBIGUOUS_SLOT_ATTRIBUTION, grades attribution assurance (claimed / observed
    # label / corroborated) and reasons over serial-to-slot associations. Supersedes
    # strict_lot_ambiguity when on. Parameters come from the coverage policy's
    # "slotAttribution" block; without it nothing can clear an ambiguity.
    slot_attribution: bool = False


def _clean(d):
    return {k: v for k, v in d.items() if v is not None}


def evaluate(case, policy, coverage, watermark=None, config=None):
    cfg = config or Config()
    events = case["events"]
    wm = dict(watermark) if watermark is not None else {}
    if watermark is None:
        for e in events:
            wm[e["sourceId"]] = max(wm.get(e["sourceId"], 0), e["sourceSeq"])
    visible = [e for e in events if e["sourceSeq"] <= wm.get(e["sourceId"], 0)]
    sessions = case["captureCoverage"]["sessions"]
    by_id = {e["eventId"]: e for e in visible}

    issues = integrity.check(visible, sessions, wm)

    # supersession: superseded evidence stays in by_id / output, leaves the replay
    superseded = {}
    for e in sorted(visible, key=lambda e: (e["recordedAt"], e["sourceId"], e["sourceSeq"])):
        t = e.get("supersedesEventId")
        if t in by_id:
            superseded[t] = e["eventId"]
    active = [e for e in visible if e["eventId"] not in superseded]

    wo = workorders.reconcile(active)
    mand = {op: cov.mandatory_sources(coverage, op)
            for op in ("COMPONENT_INSTALLED", "COMPONENT_REMOVED")}
    attr = coverage.get("slotAttribution", {}) if cfg.slot_attribution else None
    rp = ledger.Replay(by_id, superseded, mand, set(coverage["trustedVerifierSources"]),
                       wo["workOrders"], attr=attr, sessions=sessions)
    rp.run(active)

    resolved = {e["payload"].get("exceptionEventId") for e in active
                if e["eventType"] == "CAPTURE_EXCEPTION_RESOLVED"}
    exceptions = [e for e in active if e["eventType"] == "CAPTURE_EXCEPTION_RAISED"
                  and e["eventId"] not in resolved]
    for n in policy["affectedSlots"]:
        rp.slot(n)
    for x in exceptions:
        for n in x["payload"].get("scope", {}).get("slots", []):
            rp.slot(n)
    horizon = max((e["recordedAt"] for e in visible), default=None)
    ledger.apply_gaps(rp.slots, cov.outages(sessions, coverage, horizon), exceptions,
                      issues, wo, by_id)
    if cfg.slot_attribution:
        ledger.finalize_attribution(rp.slots)

    d = pol.decide(policy, rp.slots, active, cfg)
    return _assemble(case, policy, wm, visible, by_id, superseded, wo, rp, d, issues, cfg)


def _assemble(case, policy, wm, visible, by_id, superseded, wo, rp, d, issues, cfg):
    names = policy["affectedSlots"]
    rel = [rp.slots[n] for n in names]
    slots_out = {}
    for n, s in sorted(rp.slots.items()):
        relevant = n in names
        if not relevant and not s.gaps:
            continue
        slots_out[n] = _clean(dict(
            reconciliation=s.reconciliation(), baseline=s.baseline,
            identityGranularity=s.granularity(),
            policyRelevance="RELEVANT" if relevant else "NOT_IN_POLICY_SCOPE",
            currentLotPerRecords=s.record_lot(), state=s.state,
            gaps=[_clean(g) for g in s.gaps], conflicts=[dict(c) for c in s.conflicts],
            verifications=[_clean(v) for v in s.verifications]))

    ev = []
    for s in rel:
        ev += s.events
        for g in s.gaps:
            ev += [g.get("eventId"), g.get("boundedByEventId")]
        for lc in s.late_claims:
            ev += [lc["correctionEventId"], lc["supersededEventId"], lc["corroboratedBy"]]
        for a in s.ambiguities:
            ev += a["supportingEventIds"]
    ev += d["extraEvidence"]
    for w in wo["workOrders"].values():
        if any(o["slot"] in names for o in w["obligations"]):
            ev += w["eventIds"]
    ev = sorted({x for x in ev if x}, key=lambda i: (by_id[i]["recordedAt"], i))
    sup = [t for t in ev if t in superseded]
    refs = sorted({r for i in ev for r in by_id[i].get("evidenceRefs", [])})

    prov = [v["eventId"] for s in rel for v in s.verifications if v["trusted"] and v["provisional"]]
    warn = ["PROVISIONAL_VERIFICATION_USED:" + ",".join(prov)] if prov else []
    grans = {s.granularity() for s in rel}
    gran = "LOT" if "LOT" in grans else ("SERIAL" if grans == {"SERIAL"} else "UNKNOWN")

    return dict(
        caseId=case.get("caseId"), motorSerial=visible[0]["motorSerial"] if visible else None,
        policyId=policy["policyId"], policyVersion=policy["version"], recallId=policy["recallId"],
        engineVersion=ENGINE_VERSION_SLOT_ATTRIBUTION if cfg.slot_attribution else ENGINE_VERSION,
        watermark={k: v for k, v in sorted(wm.items()) if v > 0},
        evidenceFinding=d["finding"], operationalAction=ACTION[d["finding"]],
        reviewRequired=bool(d["review"]), reasonCodes=d["reasons"], flags=d["flags"],
        identityGranularity=gran, slots=slots_out,
        workOrders={k: dict(status=w["status"], disposition=w["disposition"],
                            reconciliation=w["reconciliation"], obligations=w["obligations"],
                            unexpectedEventIds=w["unexpected"])
                    for k, w in wo["workOrders"].items()},
        integrityIssues=issues, evidenceEventIds=ev, supersededEventIds=sup,
        evidenceRefs=refs, assuranceWarnings=warn,
        slotVerdicts={n: dict(finding=v["finding"], reasons=v["reasons"])
                      for n, v in d["perSlot"].items()},
        slotAttribution=[a for s in rel for a in s.attributions] if cfg.slot_attribution else [])
