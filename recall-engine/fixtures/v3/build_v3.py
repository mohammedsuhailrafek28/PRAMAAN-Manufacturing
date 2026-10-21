"""Builds the version-3 fixture set (untrusted affected-bearing observations).

Run: python build_v3.py     (writes cases/, policies.json, oracle-v3.json, ground-truth.json,
                             VERSION_TRANSITION.json/.md, MANIFEST.sha256 next to this file)

v1 (../pramaan-mfg-fixtures/) and v2 (../v2/) are read, never written. v3 expectations for the
new cases are written by hand below, not derived from engine output.
"""
import copy
import datetime
import glob
import importlib.util
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
V2DIR = os.path.join(HERE, "..", "v2")
spec = importlib.util.spec_from_file_location("build_v2", os.path.join(V2DIR, "build_v2.py"))
b2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b2)

P1, P2 = b2.P1, b2.P2
SRC = "HANDHELD-09"          # an unverified handheld: not a trusted verifier source


def plus4(ts):
    t = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ") + datetime.timedelta(seconds=4)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def dump(name, obj):
    b2.dump(os.path.join(HERE, name), obj)


def build_policies():
    d = copy.deepcopy(b2.load(os.path.join(V2DIR, "policies.json")))
    sa = d["coveragePolicy"]["slotAttribution"]
    sa["version"] = 3
    sa["observationClockSkewSeconds"] = 300
    sa["trustedTimeSources"] = ["DEVICE_SYNCED"]
    return d


# ---------------------------------------------------------------- cases ----
def with_obs(case, prefix, lot, slot="DE", at="2026-09-10T11:30:00Z", rec=None, time_source="DEVICE_SYNCED",
             motor="M-042", verifier=None, session=("2026-09-10T11:00:00Z", "2026-09-10T12:00:00Z")):
    """Add an untrusted handheld observation (and optionally a later independent QA check)."""
    case["_prefix"] = prefix
    rec = rec or plus4(at)
    e = b2.ev(prefix, 90, "SLOT_STATE_VERIFIED", SRC, at, rec, "EMP-050",
              dict(componentType="BEARING", slot=slot, observedPart="BR-6205", observedLot=lot,
                   method="LOT_LABEL_AND_MARKING_VISUAL"), refs=["EV-HH-0901"])
    e["timeSource"], e["motorSerial"] = time_source, motor
    if slot is None:
        del e["payload"]["slot"]
    case["events"].append(e)
    if not any(s["sourceId"] == SRC for s in case["captureCoverage"]["sessions"]):
        case["captureCoverage"]["sessions"].append(dict(sourceId=SRC, **{"from": session[0], "to": session[1]}))
    if verifier:
        case["captureCoverage"]["sessions"].append(
            dict(sourceId="QA-02", **{"from": "2026-09-10T11:45:00Z", "to": "2026-09-10T13:00:00Z"}))
        case["events"].append(b2.ev(prefix, 91, "SLOT_STATE_VERIFIED", "QA-02", "2026-09-10T12:00:00Z",
                                    "2026-09-10T12:00:04Z", "EMP-031",
                                    dict(componentType="BEARING", slot="DE", observedPart="BR-6205",
                                         observedLot=verifier, method="LOT_LABEL_AND_MARKING_VISUAL"),
                                    refs=["EV-PHOTO-0312"]))
    return b2.finish(case)


def clean(cid, prefix, title, desc):
    return b2.base(cid, prefix, title, desc, lots=("BR-204", "BR-310"), new_lot="BR-312")


def truth(c, t, note):
    c["groundTruth"] = {"trueP1Finding": t, "note": note}
    return c


def build_cases():
    c = {}
    d = ("Clean replacement (distinct lots) and an unverified handheld later reports BR-204 in DE. ")
    c["case-08"] = truth(with_obs(clean("case-08", "C08", "Untrusted observation of an affected lot in DE",
                                        d + "The reading is correct: DE still holds the affected bearing."),
                                  "C08", "BR-204"), "AFFECTED", "the handheld reading is right")
    c["case-08e"] = truth(with_obs(clean("case-08e", "C08E", "Same events, handheld misread",
                                         d + "Events identical to case-08 but the reading was a scanner error."),
                                   "C08E", "BR-204"), "UNAFFECTED", "scanner error; DE holds BR-312")
    c["case-08f"] = truth(with_obs(clean("case-08f", "C08F", "Untrusted observation answered by a later independent check",
                                         d + "A later independent QA check finds BR-312."),
                                   "C08F", "BR-204", verifier="BR-312"), "UNAFFECTED", "QA check agrees with the records")
    c["case-08g"] = truth(with_obs(clean("case-08g", "C08G", "Untrusted observation predating the replacement",
                                         "The handheld read BR-204 in DE at 09:00, before the 11:00 replacement."),
                                   "C08G", "BR-204", at="2026-09-10T09:00:00Z",
                                   session=("2026-09-10T08:00:00Z", "2026-09-10T12:00:00Z")),
                         "UNAFFECTED", "the old bearing was replaced afterwards")
    c["case-08h"] = truth(with_obs(clean("case-08h", "C08H", "Untrusted affected-lot observation outside the policy scope",
                                         "The handheld reports BR-204 in NDE (out of scope for this recall policy)."),
                                   "C08H", "BR-204", slot="NDE"), "UNAFFECTED", "DE is clean; NDE is not in scope")
    c["case-08i"] = truth(with_obs(b2.base("case-08i", "C08I", "Untrusted unaffected-lot observation cannot release",
                                           "As case-06c (ambiguous removal). The handheld reports BR-310 in DE.",
                                           label=(20, "LBL-M042-DE")),
                                   "C08I", "BR-310"), "AFFECTED", "label scan was valid but the removal was from NDE")
    c["case-08j"] = truth(with_obs(clean("case-08j", "C08J", "Untrusted observation with an unreliable clock",
                                         "As case-08g, but the handheld time is operator-entered, so it cannot be placed "
                                         "before the replacement."),
                                   "C08J", "BR-204", at="2026-09-10T09:00:00Z", time_source="OPERATOR_ENTERED",
                                   session=("2026-09-10T08:00:00Z", "2026-09-10T12:00:00Z")),
                         "UNAFFECTED", "the observation really was old; the engine cannot prove it")
    c["case-08k"] = truth(with_obs(clean("case-08k", "C08K", "Untrusted observation that arrives late",
                                         "As case-08g, but the reading was recorded at 11:30, after the replacement "
                                         "was recorded: occurredAt alone says old, recordedAt does not."),
                                   "C08K", "BR-204", at="2026-09-10T09:00:00Z", rec="2026-09-10T11:30:04Z",
                                   session=("2026-09-10T08:00:00Z", "2026-09-10T12:00:00Z")),
                         "UNAFFECTED", "the observation really was old; the engine cannot prove it")
    c["case-08l"] = truth(with_obs(clean("case-08l", "C08L", "Observation attributed to another motor",
                                         "A handheld reading for motor M-999 sits in this history."),
                                   "C08L", "BR-204", motor="M-999"), "UNAFFECTED", "belongs to another motor")
    return c


# --------------------------------------------------- hand-written oracle ----
ORDER = ["MES", "ASSY-01", "REWORK-03", "QA-02", SRC]


def wm(case, drop=()):
    out = {}
    for e in case["events"]:
        if e["sourceId"] not in drop:
            out[e["sourceId"]] = max(out.get(e["sourceId"], 0), e["sourceSeq"])
    return dict(sorted(out.items(), key=lambda kv: ORDER.index(kv[0])))


def entry(case, pid, finding, review, reasons, slots, flags=None, note=None, decision=None, drop=()):
    d = dict(policyId=pid, watermark=wm(case, drop), decisionId=decision or f"D-{case['caseId']}-{pid[-2:]}",
             evidenceFinding=finding,
             operationalAction="RELEASE_ELIGIBLE" if finding == "EXCLUDED_WITH_EVIDENCE" else "RECALL_HOLD",
             reviewRequired=review, reasonCodes=reasons, slots=slots)
    if flags:
        d["flags"] = flags
    if note:
        d["notes"] = note
    return d


UAO = "UNTRUSTED_AFFECTED_OBSERVATION"
SUPERSEDED = "UNTRUSTED_AFFECTED_OBSERVATION_SUPERSEDED"
OUT = "OUT_OF_SCOPE_UNTRUSTED_AFFECTED_OBSERVATION"
UNATTR = "UNATTRIBUTABLE_UNTRUSTED_AFFECTED_OBSERVATION"


def oracle_entries(cases):
    sl = lambda lot="BR-312", rec="CLEAN": b2.slot(rec, lot)
    p2 = lambda c, flags=None, review=False, lot="BR-312", rec="CLEAN": entry(
        c, P2, "AFFECTED", review, b2.P2_REASONS, sl(lot, rec), flags=flags)
    out = {}
    # case-08: late arrival after a release -> two P1 versions
    c = cases["case-08"]
    v1 = entry(c, P1, "EXCLUDED_WITH_EVIDENCE", False, ["REPLACED_WITH_UNAFFECTED_LOT"], sl(),
               decision="D-case-08-P1-v1", drop=(SRC,),
               note="Before the handheld reading arrives the motor is releasable.")
    obs_id = next(e["eventId"] for e in c["events"] if e["sourceId"] == SRC)
    v2 = entry(c, P1, "UNRESOLVED", True, [UAO, "PRIOR_EXCLUSION_WITHDRAWN"], sl(),
               decision="D-case-08-P1-v2",
               note="Late untrusted affected-lot observation: hold, not AFFECTED; exclusion withdrawn.")
    v2.update(supersedesDecisionId="D-case-08-P1-v1", triggerEventId=obs_id,
              notificationObligation=dict(required=True, reason="PRIOR_EXCLUSION_WITHDRAWN",
                                          appliesIfDecisionCommunicated="D-case-08-P1-v1"))
    out["case-08"] = [v1, v2, p2(c)]
    c = cases["case-08e"]
    out["case-08e"] = [entry(c, P1, "UNRESOLVED", True, [UAO], sl()), p2(c)]
    c = cases["case-08f"]
    out["case-08f"] = [entry(c, P1, "EXCLUDED_WITH_EVIDENCE", False, ["REPLACED_WITH_UNAFFECTED_LOT"], sl(),
                             flags=[SUPERSEDED], note="Answered by a later CORROBORATED_SLOT check."),
                       p2(c, flags=[SUPERSEDED])]
    c = cases["case-08g"]
    out["case-08g"] = [entry(c, P1, "EXCLUDED_WITH_EVIDENCE", False, ["REPLACED_WITH_UNAFFECTED_LOT"], sl(),
                             flags=[SUPERSEDED], note="Provably older than the replacement."),
                       p2(c, flags=[SUPERSEDED])]
    c = cases["case-08h"]
    out["case-08h"] = [entry(c, P1, "EXCLUDED_WITH_EVIDENCE", True, ["REPLACED_WITH_UNAFFECTED_LOT"], sl(),
                             flags=[OUT], note="Out of scope: does not block, stays visible and flagged for review."),
                       p2(c, flags=[OUT], review=True)]
    c = cases["case-08i"]
    out["case-08i"] = [entry(c, P1, "UNRESOLVED", True, ["AMBIGUOUS_SLOT_ATTRIBUTION"],
                             b2.slot("AMBIGUOUS_ATTRIBUTION", "BR-310"),
                             note="An untrusted observation of an unaffected lot releases nothing."),
                       p2(c, lot="BR-310", rec="AMBIGUOUS_ATTRIBUTION")]
    for cid in ("case-08j", "case-08k"):
        c = cases[cid]
        out[cid] = [entry(c, P1, "UNRESOLVED", True, [UAO], sl(),
                          note="Time cannot be shown to precede the replacement: hold."), p2(c)]
    c = cases["case-08l"]
    out["case-08l"] = [entry(c, P1, "EXCLUDED_WITH_EVIDENCE", True, ["REPLACED_WITH_UNAFFECTED_LOT"], sl(),
                             flags=[UNATTR], note="Not attributable to this motor: visible, does not block."),
                       p2(c, flags=[UNATTR], review=True)]
    return out


def build_oracle(cases):
    v2 = b2.load(os.path.join(V2DIR, "oracle-v2.json"))
    o = dict(oracleVersion=3,
             derivedFrom=dict(oracleVersion=2, file="../v2/oracle-v2.json",
                              sha256=b2.sha(os.path.join(V2DIR, "oracle-v2.json"))),
             cases=copy.deepcopy(v2["cases"]))
    for cid, evs in oracle_entries(cases).items():
        o["cases"].append(dict(caseId=cid, evaluations=evs))
    return o


def build_transition(v2, v3, cases):
    carried = sum(1 for c in v2["cases"] for e in c["evaluations"]
                  if e in next(x for x in v3["cases"] if x["caseId"] == c["caseId"])["evaluations"])
    total2 = sum(len(c["evaluations"]) for c in v2["cases"])
    added = [dict(caseId=c["caseId"], policyId=e["policyId"], decisionId=e["decisionId"],
                  finding=e["evidenceFinding"], reasonCodes=e["reasonCodes"], flags=e.get("flags", []))
             for c in v3["cases"] if c["caseId"] in cases for e in c["evaluations"]]
    return dict(
        transition="oracle v2 -> oracle v3",
        v2=dict(evaluations=total2, sha256=b2.sha(os.path.join(V2DIR, "oracle-v2.json")),
                note="Unmodified; v1 is likewise untouched."),
        v3=dict(evaluations=sum(len(c["evaluations"]) for c in v3["cases"]), carriedUnchanged=carried,
                changed=total2 - carried, added=len(added)),
        addedEvaluations=added, newCases=sorted(cases),
        vocabularyAdditions=dict(
            reasonCodes=[UAO],
            flags=[SUPERSEDED, OUT, UNATTR],
            semanticsProfiles=["P1_LEGACY", "SLOT_ATTRIBUTION_V2", "UNTRUSTED_OBSERVATION_V3"],
            decisionFields=["semanticsProfile", "coverageDigest", "untrustedObservations"],
            coveragePolicy=["slotAttribution.observationClockSkewSeconds", "slotAttribution.trustedTimeSources"],
            engineConfig=["Config(untrusted_observation=True) == Config.v3()"]),
        defaultProfileForNewEvaluations="UNTRUSTED_OBSERVATION_V3",
        legacyReplay="replay(case, policy, coverage, record) uses record.semanticsProfile (absent = P1_LEGACY)",
        parameters=dict(observationClockSkewSeconds=300, trustedTimeSources=["DEVICE_SYNCED"],
                        status="prototype parameters, not a proven safety standard"))


def transition_md(t):
    L = ["# Oracle version transition: v2 -> v3", "",
         f"- v2 ({t['v2']['evaluations']} evaluations, sha256 `{t['v2']['sha256'][:12]}...`) is unmodified; so is v1.",
         f"- v3: {t['v3']['evaluations']} evaluations = {t['v3']['carriedUnchanged']} carried over unchanged + "
         f"{t['v3']['changed']} changed + {t['v3']['added']} added.",
         "- No existing decision changes: the new blocker only fires on untrusted affected-lot observations, "
         "which no v1/v2 fixture contains.", "",
         "## Added evaluations", "", "| Case | Policy | Finding | Reasons | Flags |", "|---|---|---|---|---|"]
    for a in t["addedEvaluations"]:
        L.append(f"| {a['caseId']} | {a['decisionId'][-5:] if '-v' in a['decisionId'] else a['policyId'][-2:]} | "
                 f"{a['finding']} | {', '.join(a['reasonCodes'])} | {', '.join(a['flags'])} |")
    L += ["", "## Vocabulary, parameters, defaults", "", "```json",
          json.dumps(dict(vocabulary=t["vocabularyAdditions"], parameters=t["parameters"],
                          defaultProfileForNewEvaluations=t["defaultProfileForNewEvaluations"],
                          legacyReplay=t["legacyReplay"]), indent=2), "```", ""]
    return "\n".join(L)


def main():
    cases = build_cases()
    for cid, c in cases.items():
        dump(os.path.join("cases", f"{cid}.json"), c)
    dump("policies.json", build_policies())
    v2 = b2.load(os.path.join(V2DIR, "oracle-v2.json"))
    v3 = build_oracle(cases)
    dump("oracle-v3.json", v3)
    dump("ground-truth.json", {
        "note": "Synthetic ground truth for the v3 cases. Used by the harness only.",
        "truths": {cid: {"trueP1Finding": c["groundTruth"]["trueP1Finding"],
                         "basis": "v3 synthetic: " + c["groundTruth"]["note"]} for cid, c in cases.items()}})
    t = build_transition(v2, v3, cases)
    dump("VERSION_TRANSITION.json", t)
    with open(os.path.join(HERE, "VERSION_TRANSITION.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(transition_md(t))
    names = ("policies.json", "oracle-v3.json", "ground-truth.json", "VERSION_TRANSITION.json", "VERSION_TRANSITION.md")
    lines = [f"{b2.sha(p)} *./{os.path.relpath(p, HERE).replace(os.sep, '/')}"
             for p in sorted(glob.glob(os.path.join(HERE, "cases", "*.json"))) + [os.path.join(HERE, n) for n in names]]
    with open(os.path.join(HERE, "MANIFEST.sha256"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print(json.dumps(t["v3"]))


if __name__ == "__main__":
    main()
