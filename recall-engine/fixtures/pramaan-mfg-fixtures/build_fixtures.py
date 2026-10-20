"""Generates Manufacturing PRAMAAN recall test fixtures + oracle."""
import json, os
from datetime import datetime, timedelta

OUT = os.path.dirname(os.path.abspath(__file__))
RECALL_ID = "RC-009"
RECALL_AT = "2026-10-01T00:00:00Z"
FMT = "%Y-%m-%dT%H:%M:%SZ"


def plus(ts, seconds):
    return (datetime.strptime(ts, FMT) + timedelta(seconds=seconds)).strftime(FMT)


def comp(slot, lot, **extra):
    d = {"componentType": "BEARING", "slot": slot, "part": "BR-6205",
         "lot": lot, "identityGranularity": "LOT"}
    d.update(extra)
    return d


class Case:
    def __init__(self, cid, title, description):
        self.cid, self.title, self.description = cid, title, description
        self.events, self.sessions, self.seq, self.n = [], [], {}, 0
        self.ground_truth, self.notes = None, []
        self.session("MES", "2026-08-01T00:00:00Z", "2026-10-31T00:00:00Z")

    def session(self, source, start, end):
        self.sessions.append({"sourceId": source, "from": start, "to": end})

    def ev(self, etype, source, occurred, actor, wo=None, payload=None,
           recorded=None, recall=None, evidence=None, supersedes=None,
           time_source="DEVICE_SYNCED"):
        self.seq[source] = self.seq.get(source, 0) + 1
        self.n += 1
        eid = f"{self.cid.upper().replace('CASE-', 'C')}-E{self.n:03d}"
        e = {
            "eventId": eid, "eventType": etype, "schemaVersion": 1,
            "sourceId": source, "sourceSeq": self.seq[source],
            "motorSerial": "M-042", "workOrderId": wo, "recallId": recall,
            "occurredAt": occurred, "timeSource": time_source,
            "recordedAt": recorded or plus(occurred, 4),
            "actorId": actor, "evidenceRefs": evidence or [],
            "supersedesEventId": supersedes, "payload": payload or {},
        }
        self.events.append(e)
        return eid

    def watermark(self, cutoff=None):
        wm = {}
        for e in self.events:
            if cutoff is None or e["recordedAt"] <= cutoff:
                wm[e["sourceId"]] = max(wm.get(e["sourceId"], 0), e["sourceSeq"])
        return wm

    def dump(self):
        return {
            "caseId": self.cid, "title": self.title,
            "description": self.description,
            "captureCoverage": {
                "coveragePolicy": "COV-BEARING-v1",
                "sessions": self.sessions,
            },
            "events": self.events,
            **({"groundTruth": self.ground_truth} if self.ground_truth else {}),
            **({"notes": self.notes} if self.notes else {}),
        }


# ---------- shared history builders ----------

def as_built(c, de_lot="BR-204", nde_lot="BR-150"):
    c.session("ASSY-01", "2026-08-12T08:00:00Z", "2026-08-12T18:00:00Z")
    c.ev("WORK_ORDER_OPENED", "MES", "2026-08-12T09:30:00Z", "SYS-MES", "MO-042",
         {"orderType": "BUILD", "expectedChanges": [
             {"slot": "DE", "action": "INSTALL"}, {"slot": "NDE", "action": "INSTALL"}]})
    de = c.ev("COMPONENT_INSTALLED", "ASSY-01", "2026-08-12T10:00:00Z", "EMP-009",
              "MO-042", comp("DE", de_lot), evidence=["EV-SCAN-0101"])
    nde = c.ev("COMPONENT_INSTALLED", "ASSY-01", "2026-08-12T10:05:00Z", "EMP-009",
               "MO-042", comp("NDE", nde_lot), evidence=["EV-SCAN-0102"])
    c.ev("WORK_ORDER_CLOSED", "MES", "2026-08-12T11:00:00Z", "SYS-MES", "MO-042",
         {"disposition": "COMPLETED"})
    return de, nde


def open_rework(c, wo="RW-192", slot="DE"):
    c.ev("WORK_ORDER_OPENED", "MES", "2026-09-10T08:45:00Z", "SYS-MES", wo,
         {"orderType": "REWORK", "reason": "NCR-0771 bearing noise",
          "expectedChanges": [{"slot": slot, "action": "REPLACE"}]})


def close_rework(c, wo="RW-192"):
    c.ev("WORK_ORDER_CLOSED", "MES", "2026-09-10T11:15:00Z", "SYS-MES", wo,
         {"disposition": "COMPLETED"})


def remove_de(c, ends, observed_lot="BR-204", wo="RW-192"):
    return c.ev("COMPONENT_REMOVED", "REWORK-03", "2026-09-10T10:00:00Z", "EMP-017",
                wo, {"componentType": "BEARING", "slot": "DE",
                     "endsInstallEventId": ends, "observedPart": "BR-6205",
                     "observedLot": observed_lot, "identityGranularity": "LOT"},
                evidence=["EV-SCAN-0201"])


def install_de(c, lot="BR-310", wo="RW-192"):
    return c.ev("COMPONENT_INSTALLED", "REWORK-03", "2026-09-10T11:00:00Z", "EMP-017",
                wo, comp("DE", lot), evidence=["EV-SCAN-0202"])


def verify_de(c, observed_lot, when="2026-09-10T11:30:00Z"):
    c.session("QA-02", plus(when, -1800), plus(when, 1800))
    return c.ev("SLOT_STATE_VERIFIED", "QA-02", when, "EMP-031", None,
                {"componentType": "BEARING", "slot": "DE",
                 "observedPart": "BR-6205", "observedLot": observed_lot,
                 "method": "LOT_LABEL_AND_MARKING_VISUAL", "provisional": True},
                evidence=["EV-PHOTO-0301"])


def damage_inspection(c):
    c.session("INSP-01", "2026-10-05T08:00:00Z", "2026-10-05T18:00:00Z")
    c.ev("WORK_ORDER_OPENED", "MES", "2026-10-05T09:00:00Z", "SYS-MES", "RRO-007",
         {"orderType": "RECALL_REMEDIATION",
          "expectedChanges": [{"slot": "DE", "action": "INSPECT"}]}, recall=RECALL_ID)
    eid = c.ev("INSPECTION_RECORDED", "INSP-01", "2026-10-05T10:00:00Z", "EMP-052",
               "RRO-007", {"protocolId": "RC-009-DMG-01",
                           "scope": ["DE_SHAFT", "DE_HOUSING", "DE_SEAL"],
                           "result": "PASS",
                           "inspectorQualifiedFor": ["RC-009-DMG-01"],
                           "identifiesInstalledComponent": False,
                           "provisional": True},
               recall=RECALL_ID, evidence=["EV-PHOTO-0401", "EV-REPORT-0402"])
    c.ev("WORK_ORDER_CLOSED", "MES", "2026-10-05T11:00:00Z", "SYS-MES", "RRO-007",
         {"disposition": "COMPLETED"}, recall=RECALL_ID)
    return eid


REWORK_FULL = ("REWORK-03", "2026-09-10T08:00:00Z", "2026-09-10T18:00:00Z")

# ---------- cases ----------
cases, oracle = [], []


def expect(case, policy, finding, action, reasons, slots, watermark=None,
           decision_id=None, supersedes=None, trigger=None, flags=None,
           notes=None, notification=None):
    d = {"policyId": policy,
         "watermark": watermark or case.watermark(),
         "decisionId": decision_id or f"D-{case.cid}-{policy.split('/')[1]}",
         "evidenceFinding": finding, "operationalAction": action,
         "reviewRequired": finding == "UNRESOLVED",
         "reasonCodes": reasons, "slots": slots}
    if supersedes: d["supersedesDecisionId"] = supersedes
    if trigger: d["triggerEventId"] = trigger
    if flags: d["flags"] = flags
    if notification: d["notificationObligation"] = notification
    if notes: d["notes"] = notes
    return d


def slot(recon, baseline, current=None, gaps=None, relevance="RELEVANT"):
    s = {"reconciliation": recon, "baseline": baseline,
         "identityGranularity": "LOT", "policyRelevance": relevance}
    if current: s["currentLotPerRecords"] = current
    if gaps: s["gaps"] = gaps
    return s


def add(case, *evals):
    cases.append(case)
    oracle.append({"caseId": case.cid, "evaluations": list(evals)})


# Case 1 — complete DE replacement, unrelated NDE gap
c = Case("case-01", "Complete DE replacement, unrelated NDE gap",
         "Validated as-built baseline. DE bearing from affected lot replaced during "
         "rework. A slot-scoped missed scan affects NDE only.")
de, nde = as_built(c); c.session(*REWORK_FULL); open_rework(c)
remove_de(c, de)
exc = c.ev("CAPTURE_EXCEPTION_RAISED", "REWORK-03", "2026-09-10T10:30:00Z", "EMP-017",
           "RW-192", {"exceptionType": "MISSED_SCAN", "scope": {"slots": ["NDE"]},
                      "detail": "NDE end-cap handled without scan"})
install_de(c); close_rework(c)
nde_gap = slot("CAPTURE_GAP", "AS_BUILT_VALIDATED", "BR-150",
               [{"kind": "UNRESOLVED_EXCEPTION", "eventId": exc, "materiality": "MATERIAL"}],
               relevance="NOT_IN_POLICY_SCOPE")
de_ok = slot("CLEAN", "AS_BUILT_VALIDATED", "BR-310")
add(c,
    expect(c, "RC-009/P1", "EXCLUDED_WITH_EVIDENCE", "RELEASE_ELIGIBLE",
           ["REPLACED_WITH_UNAFFECTED_LOT", "IRRELEVANT_SLOT_GAP"],
           {"DE": de_ok, "NDE": nde_gap}),
    expect(c, "RC-009/P2", "AFFECTED", "RECALL_HOLD",
           ["HISTORICAL_EXPOSURE_CONFIRMED", "DAMAGE_INSPECTION_MISSING",
            "IRRELEVANT_SLOT_GAP"], {"DE": de_ok, "NDE": nde_gap}))

# Case 2 — missing DE baseline
c = Case("case-02", "Missing DE baseline",
         "No as-built capture exists. First DE record is a removal scanning the "
         "affected lot, then an install of an unaffected lot.")
c.session(*REWORK_FULL); open_rework(c)
remove_de(c, None); install_de(c); close_rework(c)
de_unk = slot("INSUFFICIENT_EVIDENCE", "UNKNOWN", "BR-310")
add(c,
    expect(c, "RC-009/P1", "UNRESOLVED", "RECALL_HOLD",
           ["NO_TRUSTED_BASELINE", "CURRENT_STATE_UNVERIFIED"], {"DE": de_unk},
           notes="Decision 2 (strict): removal + install claims do not establish current "
                 "DE contents without a trusted starting state. A SLOT_STATE_VERIFIED "
                 "event could support P1 exclusion."),
    expect(c, "RC-009/P2", "AFFECTED", "RECALL_HOLD",
           ["HISTORICAL_EXPOSURE_CONFIRMED", "DAMAGE_INSPECTION_MISSING"], {"DE": de_unk},
           notes="Exposure evidence is the removal scan's observedLot, subject to that "
                 "scan's authenticity."))

# Case 3 — double installation
c = Case("case-03", "Install into occupied slot",
         "Validated as-built baseline with DE = BR-204. Rework installs BR-310 into DE "
         "with no recorded removal.")
de, nde = as_built(c); c.session(*REWORK_FULL); open_rework(c, wo="RW-193")
install_de(c, wo="RW-193")
c.ev("WORK_ORDER_CLOSED", "MES", "2026-09-10T11:15:00Z", "SYS-MES", "RW-193",
     {"disposition": "COMPLETED"})
de_conf = slot("CONFLICT", "AS_BUILT_VALIDATED")
de_conf["conflicts"] = [{"kind": "DOUBLE_OCCUPANCY", "occupiedBy": de}]
add(c,
    expect(c, "RC-009/P1", "UNRESOLVED", "RECALL_HOLD",
           ["DOUBLE_OCCUPANCY", "CURRENT_STATE_UNVERIFIED"], {"DE": de_conf}),
    expect(c, "RC-009/P2", "AFFECTED", "RECALL_HOLD",
           ["HISTORICAL_EXPOSURE_CONFIRMED", "DAMAGE_INSPECTION_MISSING"],
           {"DE": de_conf}, flags=["SLOT_RECORD_CONFLICT"]))


# Case 4 family — station-wide outage during rework
def case4(cid, title, desc, verify, inspect):
    c = Case(cid, title, desc)
    de, nde = as_built(c)
    c.session("REWORK-03", "2026-09-10T08:00:00Z", "2026-09-10T10:15:00Z")
    c.session("REWORK-03", "2026-09-10T10:45:00Z", "2026-09-10T18:00:00Z")
    open_rework(c); remove_de(c, de); install_de(c)
    v = verify_de(c, "BR-310") if verify else None
    close_rework(c)
    i = damage_inspection(c) if inspect else None
    return c, v, i


OUTAGE = {"kind": "SOURCE_OUTAGE", "sourceId": "REWORK-03",
          "from": "2026-09-10T10:15:00Z", "to": "2026-09-10T10:45:00Z"}
nde_outage = slot("CAPTURE_GAP", "AS_BUILT_VALIDATED", "BR-150",
                  [dict(OUTAGE, materiality="MATERIAL")], relevance="NOT_IN_POLICY_SCOPE")

c, v, i = case4("case-04", "DE outage bounded by independent verification",
                "Station-wide outage while DE was empty. Independent QA verification "
                "after install; post-recall damage inspection passed.", True, True)
de_b = slot("CLEAN", "AS_BUILT_VALIDATED", "BR-310",
            [dict(OUTAGE, materiality="BOUNDED", boundedByEventId=v)])
add(c,
    expect(c, "RC-009/P1", "EXCLUDED_WITH_EVIDENCE", "RELEASE_ELIGIBLE",
           ["REPLACED_WITH_UNAFFECTED_LOT", "GAP_BOUNDED_BY_VERIFICATION",
            "IRRELEVANT_SLOT_GAP"], {"DE": de_b, "NDE": nde_outage}),
    expect(c, "RC-009/P2", "EXCLUDED_WITH_EVIDENCE", "RELEASE_ELIGIBLE",
           ["HISTORICAL_EXPOSURE_CONFIRMED", "DAMAGE_INSPECTION_PASSED",
            "EXPOSURE_REMEDIATED", "GAP_BOUNDED_BY_VERIFICATION", "IRRELEVANT_SLOT_GAP"],
           {"DE": de_b, "NDE": nde_outage},
           notes=f"Requires inspection {i}: protocol RC-009-DMG-01, after recall "
                 "announcement, qualified inspector, PASS."))

c, _, _ = case4("case-04b", "DE outage, no verification, no inspection",
                "Same outage as case-04 with neither slot verification nor damage "
                "inspection.", False, False)
de_g = slot("CAPTURE_GAP", "AS_BUILT_VALIDATED", "BR-310",
            [dict(OUTAGE, materiality="MATERIAL")])
add(c,
    expect(c, "RC-009/P1", "UNRESOLVED", "RECALL_HOLD", ["MATERIAL_CAPTURE_GAP"],
           {"DE": de_g, "NDE": nde_outage}),
    expect(c, "RC-009/P2", "AFFECTED", "RECALL_HOLD",
           ["HISTORICAL_EXPOSURE_CONFIRMED", "DAMAGE_INSPECTION_MISSING",
            "MATERIAL_CAPTURE_GAP"], {"DE": de_g, "NDE": nde_outage},
           notes="Historical BR-204 exposure is established by the baseline; the gap "
                 "does not erase it."))

c, _, i = case4("case-04c", "DE outage, inspection passed, no verification",
                "Same outage as case-04. Damage inspection passed, but it does not "
                "identify the installed bearing, so current DE contents stay unverified.",
                False, True)
add(c,
    expect(c, "RC-009/P1", "UNRESOLVED", "RECALL_HOLD", ["MATERIAL_CAPTURE_GAP"],
           {"DE": de_g, "NDE": nde_outage}),
    expect(c, "RC-009/P2", "UNRESOLVED", "RECALL_HOLD",
           ["HISTORICAL_EXPOSURE_CONFIRMED", "DAMAGE_INSPECTION_PASSED",
            "REMEDIATION_COMPLETENESS_UNCERTAIN", "MATERIAL_CAPTURE_GAP"],
           {"DE": de_g, "NDE": nde_outage},
           notes="Damage risk is addressed, but the unbounded gap leaves the "
                 "component-replacement half of remediation uncertain."))


# Case 5 family — late risk-increasing correction
def case5(cid, title, desc, corroborate):
    c = Case(cid, title, desc)
    de, nde = as_built(c); c.session(*REWORK_FULL); open_rework(c)
    remove_de(c, de); inst = install_de(c); close_rework(c)
    c.session("QUALITY-PORTAL", "2026-10-12T00:00:00Z", "2026-10-13T00:00:00Z")
    corr = c.ev("COMPONENT_INSTALLED", "QUALITY-PORTAL", "2026-09-10T11:00:00Z",
                "EMP-044", "RW-192", comp("DE", "BR-207",
                                          correctionReason="Lot label misread at rework"),
                recorded="2026-10-12T14:20:00Z", supersedes=inst,
                time_source="OPERATOR_ENTERED", evidence=["EV-NOTE-0501"])
    v = None
    if corroborate:
        c.sessions = [s for s in c.sessions if s["sourceId"] != "QA-02"]
        v = verify_de(c, "BR-207", when="2026-10-13T10:00:00Z")
    return c, inst, corr, v


W1 = "2026-10-11T23:59:59Z"
W2 = "2026-10-12T23:59:59Z"


def case5_evals(c, inst, corr):
    de_w1 = slot("CLEAN", "AS_BUILT_VALIDATED", "BR-310")
    de_w2 = slot("CONFLICT", "AS_BUILT_VALIDATED", "BR-207")
    de_w2["conflicts"] = [{"kind": "LATE_CORRECTION", "supersededEventId": inst,
                           "correctionEventId": corr}]
    p1 = f"D-{c.cid}-P1"
    return [
        expect(c, "RC-009/P1", "EXCLUDED_WITH_EVIDENCE", "RELEASE_ELIGIBLE",
               ["REPLACED_WITH_UNAFFECTED_LOT"], {"DE": de_w1},
               watermark=c.watermark(W1), decision_id=p1 + "-v1"),
        expect(c, "RC-009/P1", "UNRESOLVED", "RECALL_HOLD",
               ["LATE_CLAIM_RISK_INCREASING", "PRIOR_EXCLUSION_WITHDRAWN"], {"DE": de_w2},
               watermark=c.watermark(W2), decision_id=p1 + "-v2",
               supersedes=p1 + "-v1", trigger=corr,
               notification={"required": True, "reason": "PRIOR_EXCLUSION_WITHDRAWN",
                             "appliesIfDecisionCommunicated": p1 + "-v1"},
               notes="Decision 3: risk-increasing late evidence acts immediately "
                     "(hold) but is not treated as confirmed exposure until reviewed "
                     "or corroborated."),
        expect(c, "RC-009/P2", "AFFECTED", "RECALL_HOLD",
               ["HISTORICAL_EXPOSURE_CONFIRMED", "DAMAGE_INSPECTION_MISSING"],
               {"DE": de_w1}, watermark=c.watermark(W1), decision_id=f"D-{c.cid}-P2-v1"),
        expect(c, "RC-009/P2", "AFFECTED", "RECALL_HOLD",
               ["HISTORICAL_EXPOSURE_CONFIRMED", "DAMAGE_INSPECTION_MISSING",
                "LATE_CLAIM_RISK_INCREASING"], {"DE": de_w2},
               watermark=c.watermark(W2), decision_id=f"D-{c.cid}-P2-v2",
               supersedes=f"D-{c.cid}-P2-v1", trigger=corr,
               notes="Finding unchanged; reasons updated so the late claim stays visible."),
    ]


c, inst, corr, _ = case5("case-05", "Late risk-increasing correction",
                         "Case-01 history (without the NDE exception), excluded at W1. "
                         "A post-recall correction claims the replacement was BR-207, "
                         "which is in recall scope.", False)
add(c, *case5_evals(c, inst, corr))

c, inst, corr, v = case5("case-05b", "Late correction, then corroborated",
                         "As case-05, followed by independent QA verification observing "
                         "BR-207 in DE.", True)
ev5b = case5_evals(c, inst, corr)
de_w3 = slot("CONFLICT", "AS_BUILT_VALIDATED", "BR-207")
de_w3["conflicts"] = [{"kind": "LATE_CORRECTION", "supersededEventId": inst,
                       "correctionEventId": corr, "corroboratedByEventId": v}]
ev5b.insert(2, expect(c, "RC-009/P1", "AFFECTED", "RECALL_HOLD",
                      ["VERIFIED_AFFECTED_LOT_PRESENT", "CORROBORATED_BY_VERIFICATION"],
                      {"DE": de_w3}, decision_id=f"D-{c.cid}-P1-v3",
                      supersedes=f"D-{c.cid}-P1-v2", trigger=v))
add(c, *ev5b)

# Case 6 family — lot-level identity cannot detect a wrong-slot scan
c = Case("case-06", "Wrong-slot scan, lot-level identity (undetected)",
         "Both slots hold lot BR-204. Technician physically replaces NDE but scans "
         "the removal and install as DE. Records are internally consistent.")
de, nde = as_built(c, nde_lot="BR-204"); c.session(*REWORK_FULL); open_rework(c)
remove_de(c, de); install_de(c); close_rework(c)
c.ground_truth = {"DE": "BR-204", "NDE": "BR-310",
                  "trueP1Finding": "AFFECTED",
                  "knownLimitation": "LOT_LEVEL_SLOT_AMBIGUITY"}
de_ok = slot("CLEAN", "AS_BUILT_VALIDATED", "BR-310")
add(c,
    expect(c, "RC-009/P1", "EXCLUDED_WITH_EVIDENCE", "RELEASE_ELIGIBLE",
           ["REPLACED_WITH_UNAFFECTED_LOT"], {"DE": de_ok},
           flags=["KNOWN_LIMITATION_LOT_LEVEL_SLOT_AMBIGUITY"],
           notes="Expected SYSTEM output, which is wrong against ground truth. This "
                 "case documents an assurance limit; it must not be 'fixed' by tuning "
                 "the engine to pass it."),
    expect(c, "RC-009/P2", "AFFECTED", "RECALL_HOLD",
           ["HISTORICAL_EXPOSURE_CONFIRMED", "DAMAGE_INSPECTION_MISSING"], {"DE": de_ok}))

c = Case("case-06b", "Wrong-slot scan, caught by verification",
         "As case-06, plus independent QA verification observing BR-204 still in DE.")
de, nde = as_built(c, nde_lot="BR-204"); c.session(*REWORK_FULL); open_rework(c)
remove_de(c, de); install_de(c)
v = verify_de(c, "BR-204"); close_rework(c)
de_c = slot("CONFLICT", "AS_BUILT_VALIDATED", "BR-310")
de_c["conflicts"] = [{"kind": "VERIFIED_STATE_MISMATCH", "verificationEventId": v,
                      "recordedLot": "BR-310", "observedLot": "BR-204"}]
add(c,
    expect(c, "RC-009/P1", "AFFECTED", "RECALL_HOLD",
           ["VERIFIED_AFFECTED_LOT_PRESENT"], {"DE": de_c},
           flags=["SLOT_RECORD_CONFLICT"]),
    expect(c, "RC-009/P2", "AFFECTED", "RECALL_HOLD",
           ["HISTORICAL_EXPOSURE_CONFIRMED", "DAMAGE_INSPECTION_MISSING"], {"DE": de_c},
           flags=["SLOT_RECORD_CONFLICT"]))

# ---------- policies ----------
base_policy = {"recallId": RECALL_ID, "version": 1, "announcedAt": RECALL_AT,
               "affectedPart": "BR-6205", "affectedLots": ["BR-204", "BR-207"],
               "affectedSlots": ["DE"]}
policies = [
    dict(base_policy, policyId="RC-009/P1", exposureBasis="CURRENT_INSTALLATION",
         damageInspection=None),
    dict(base_policy, policyId="RC-009/P2", exposureBasis="HISTORICAL_OPERATION",
         damageInspection={"protocolId": "RC-009-DMG-01",
                           "mustOccurAfter": RECALL_AT,
                           "requiredResult": "PASS",
                           "inspectorQualification": "RC-009-DMG-01"}),
]
coverage_policy = {"coveragePolicyId": "COV-BEARING-v1",
                   "mandatoryCapture": [
                       {"operation": "COMPONENT_INSTALLED", "sources": ["ASSY-01", "REWORK-03"]},
                       {"operation": "COMPONENT_REMOVED", "sources": ["REWORK-03"]},
                       {"operation": "WORK_ORDER_*", "sources": ["MES"]}],
                   "trustedVerifierSources": ["QA-02"],
                   "rule": "A source outage is a gap for every slot it could affect "
                           "unless a later trusted SLOT_STATE_VERIFIED re-establishes "
                           "that slot's state."}

os.makedirs(f"{OUT}/cases", exist_ok=True)
for c in cases:
    with open(f"{OUT}/cases/{c.cid}.json", "w") as f:
        json.dump(c.dump(), f, indent=2)
with open(f"{OUT}/policies.json", "w") as f:
    json.dump({"recallPolicies": policies, "coveragePolicy": coverage_policy}, f, indent=2)
with open(f"{OUT}/oracle.json", "w") as f:
    json.dump({"oracleVersion": 1, "cases": oracle}, f, indent=2)
print(f"{len(cases)} cases, {sum(len(o['evaluations']) for o in oracle)} evaluations")
