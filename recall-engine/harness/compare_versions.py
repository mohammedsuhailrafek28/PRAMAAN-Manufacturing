"""v1 vs v2 comparison, kept as six separate measurements (never one blended score).

Engines:   E1 = Phase 1 semantics (Config()),   E2 = slot-attribution safety (Config(slot_attribution=True))
Oracles:   O1 = supplied expectations (frozen), O2 = oracle-v2 (O1 + declared transition + new cases)
Truth:     synthetic ground truth (inline groundTruth in case-06, v2 sidecar for the rest). P1 only.

A correct E2 result is NOT penalised for disagreeing with O1's known-unsafe expectation: such a
disagreement is classified from the declared transition and the ground truth, not counted as a defect.

Run:  python harness/compare_versions.py   -> reports/v1_v2_comparison.{md,json}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle_harness import (AFF, EXCL, FIX2, ROOT, UNRES, V1_CONFIG, V2_CONFIG, load_all,  # noqa: E402
                            load_truth, run_behavioral, run_final, summarise_behavioral)

OUT = os.path.join(ROOT, "reports")
SHORT = {EXCL: "EXCLUDED", AFF: "AFFECTED", UNRES: "UNRESOLVED"}
P1 = "RC-009/P1"


def _bad(r):
    return bool(r["decisionDiffs"] or r["detailDiffs"] or r["flagDiffs"])


def _key(r):
    return (r["caseId"], r["policyId"], r["version"])


def compute(e2_config=V2_CONFIG):
    with open(os.path.join(FIX2, "VERSION_TRANSITION.json"), encoding="utf-8") as f:
        transition = json.load(f)
    declared = {(c["caseId"], c["policyId"]): c["kind"] for c in transition["changedEvaluations"]}

    _, _, cases2, _ = load_all(2)
    truth = load_truth(cases2)

    e1o1 = run_behavioral(V1_CONFIG, 1)
    e2o1 = run_behavioral(e2_config, 1, 2)
    e2o2 = run_behavioral(e2_config, 2)
    e1o2 = run_behavioral(V1_CONFIG, 2, 1)

    # ---- A. behavioral agreement ------------------------------------------------
    o2_by = {_key(r): r for r in e2o2}
    div = []
    for r in e2o1:
        if not _bad(r):
            continue
        k = (r["caseId"], r["policyId"])
        o1_released = r["expected"]["evidenceFinding"] == EXCL
        known_unsafe = o1_released and truth.get(r["caseId"]) == AFF and r["policyId"] == P1
        explained = k in declared and not _bad(o2_by[_key(r)])
        cls = ("INTENDED_SAFETY_DIVERGENCE (v1 expectation is a false release against ground truth)"
               if known_unsafe and explained else
               "DECLARED_DETAIL_ONLY_CHANGE (decision unchanged)" if explained and not r["decisionDiffs"] else
               "UNEXPLAINED")
        div.append(dict(caseId=r["caseId"], policyId=r["policyId"], v1Expected=r["expected"]["evidenceFinding"],
                        v2Engine=r["got"]["evidenceFinding"], classification=cls,
                        diffs=r["decisionDiffs"] + r["detailDiffs"] + r["flagDiffs"]))
    A = dict(
        e1_vs_o1=summarise_behavioral(e1o1), e2_vs_o1=summarise_behavioral(e2o1),
        e2_vs_o2=summarise_behavioral(e2o2), e1_vs_o2=summarise_behavioral(e1o2),
        e1_vs_o2_disagreements=[f"{r['caseId']} {r['policyId'][-2:]}" for r in e1o2 if _bad(r)],
        e2_vs_o2_disagreements=[f"{r['caseId']} {r['policyId'][-2:]}" for r in e2o2 if _bad(r)],
        e2_vs_o1_divergences=div)

    # ---- full-watermark decisions for both engines over all v2 cases ------------
    f1 = run_final(V1_CONFIG, version=2, policy_version=1)
    f2 = run_final(e2_config, version=2, policy_version=2)

    def rows(f):
        return {k: d for k, d in f.items()}

    # ---- B. false releases ------------------------------------------------------
    def false_releases(f):
        return sorted(f"{c} {p[-2:]}" for (c, p), d in f.items()
                      if p == P1 and truth.get(c) == AFF and d["evidenceFinding"] == EXCL)

    def releases(f, pol=None):
        return sorted(f"{c} {p[-2:]}" for (c, p), d in f.items()
                      if d["evidenceFinding"] == EXCL and (pol is None or p == pol))

    B = dict(groundTruthAffectedCases=sorted(c for c, t in truth.items() if t == AFF),
             e1_false_releases=false_releases(f1), e2_false_releases=false_releases(f2),
             e1_releases_p1=releases(f1, P1), e2_releases_p1=releases(f2, P1),
             e1_releases_all=releases(f1), e2_releases_all=releases(f2),
             e2_releases_without_ground_truth=sorted(
                 f"{c} {p[-2:]}" for (c, p), d in f2.items()
                 if d["evidenceFinding"] == EXCL and (p != P1 or c not in truth)))

    # ---- C. unaffected motors ---------------------------------------------------
    def unaffected(f):
        out = dict(released=[], heldUnresolved=[], heldAffected=[])
        for c in sorted(t for t, v in truth.items() if v == "UNAFFECTED"):
            fd = f[(c, P1)]["evidenceFinding"]
            out[{EXCL: "released", UNRES: "heldUnresolved", AFF: "heldAffected"}[fd]].append(c)
        return out

    C = dict(unaffectedMotors=sorted(c for c, t in truth.items() if t == "UNAFFECTED"),
             e1=unaffected(f1), e2=unaffected(f2))

    # ---- D. case 06 before / after ---------------------------------------------
    def view(d):
        return dict(finding=d["evidenceFinding"], action=d["operationalAction"], review=d["reviewRequired"],
                    reasons=d["reasonCodes"], flags=d["flags"])

    D = [dict(caseId=c, policyId=P1, truth=truth.get(c), v1=view(f1[(c, P1)]), v2=view(f2[(c, P1)]))
         for c in ("case-06", "case-06b", "case-06c", "case-06d", "case-06e", "case-06f")]

    # ---- E. regressions ---------------------------------------------------------
    safety_reg = [f"{c} {p[-2:]}" for (c, p), d in f2.items()
                  if p == P1 and truth.get(c) == AFF and d["evidenceFinding"] == EXCL
                  and f1[(c, p)]["evidenceFinding"] != EXCL]
    held_more, released_more, other = [], [], []
    for k in sorted(f1):
        a, b = f1[k]["evidenceFinding"], f2[k]["evidenceFinding"]
        if a == b:
            if f1[k]["reasonCodes"] != f2[k]["reasonCodes"] or f1[k]["flags"] != f2[k]["flags"]:
                other.append(dict(case=k[0], policy=k[1], detail="same finding, reasons/flags differ",
                                  v1=f1[k]["reasonCodes"] + f1[k]["flags"], v2=f2[k]["reasonCodes"] + f2[k]["flags"]))
            continue
        t = truth.get(k[0]) if k[1] == P1 else None
        row = dict(case=k[0], policy=k[1], v1=a, v2=b, truth=t)
        if a == EXCL:
            row["assessment"] = ("INTENDED (v1 release was false)" if t == AFF else
                                 "USEFULNESS COST (truth UNAFFECTED, now held)" if t == "UNAFFECTED" else
                                 "v1 release unverifiable against ground truth")
            held_more.append(row)
        elif b == EXCL:
            row["assessment"] = "NEW RELEASE"
            released_more.append(row)
        else:
            other.append(dict(row, detail="non-release change"))
    E = dict(safety_regressions=safety_reg, released_in_v1_now_held=held_more,
             held_in_v1_now_released=released_more, other_differences=other,
             behavioral_regressions_vs_o2=A["e2_vs_o2_disagreements"],
             unexplained_vs_o1=[d for d in div if d["classification"] == "UNEXPLAINED"])

    gate = dict(zeroFalseReleases=not B["e2_false_releases"], releasesNonZero=bool(B["e2_releases_all"]),
                noSafetyRegression=not safety_reg, noBehavioralRegression=not A["e2_vs_o2_disagreements"]
                and not E["unexplained_vs_o1"])
    gate["pass"] = all(gate.values())
    return dict(A=A, B=B, C=C, D=D, E=E, gate=gate, truth=truth, transition=transition["v2"])


def pct(a, b):
    return f"{a}/{b}"


def md(r):
    A, B, C, D, E, g = r["A"], r["B"], r["C"], r["D"], r["E"], r["gate"]
    L = ["# v1 vs v2: slot attribution safety", "",
         "Six separate measurements. Nothing here is a blended score. E1 = Phase 1 engine, E2 = slot-attribution "
         "engine; O1 = supplied oracle (frozen), O2 = oracle-v2. Ground truth is synthetic and covers P1 only.", "",
         "## Gate", "",
         f"- **Zero false releases (E2): {'PASS' if g['zeroFalseReleases'] else 'FAIL'}** "
         f"({len(B['e2_false_releases'])} against {len(r['truth'])} cases with recorded truth)",
         f"- Releasing something at all: {'PASS' if g['releasesNonZero'] else 'FAIL'} "
         f"({len(B['e2_releases_all'])} EXCLUDED decisions, {len(B['e2_releases_p1'])} in P1)",
         f"- No safety regression vs E1: {'PASS' if g['noSafetyRegression'] else 'FAIL'}",
         f"- No behavioral regression (E2 vs O2 and no unexplained E2-vs-O1 difference): "
         f"{'PASS' if g['noBehavioralRegression'] else 'FAIL'}", "",
         "## 1. Behavioral oracle agreement", "",
         "| Engine vs oracle | Evaluations | Decision-level | Full (reasons, slots, lifecycle) |", "|---|---|---|---|"]
    for k, label in (("e1_vs_o1", "E1 vs O1 (Phase 1 contract)"), ("e2_vs_o1", "E2 vs O1 (v2 engine, old expectations)"),
                     ("e2_vs_o2", "E2 vs O2 (v2 engine, v2 expectations)"),
                     ("e1_vs_o2", "E1 vs O2 (v1 engine, v2 expectations)")):
        s = A[k]
        L.append(f"| {label} | {s['evaluations']} | {pct(s['decisionAgree'], s['evaluations'])} | "
                 f"{pct(s['fullAgree'], s['evaluations'])} |")
    L += ["", "E2 vs O1 disagreements, classified (not counted as implementation failures when declared):", ""]
    for d in A["e2_vs_o1_divergences"]:
        L.append(f"- {d['caseId']} {d['policyId'][-2:]}: O1 expected {SHORT[d['v1Expected']]}, E2 returns "
                 f"{SHORT[d['v2Engine']]} - **{d['classification']}**")
    L += ["", f"E1 vs O2 disagreements (what the v2 oracle adds): {', '.join(A['e1_vs_o2_disagreements']) or 'none'}", "",
          "## 2. False releases against synthetic ground truth", "",
          f"Cases with recorded truth AFFECTED: {', '.join(B['groundTruthAffectedCases'])}", "",
          "| Engine | False releases | Count |", "|---|---|---|",
          f"| E1 | {', '.join(B['e1_false_releases']) or 'none'} | {len(B['e1_false_releases'])} |",
          f"| E2 | {', '.join(B['e2_false_releases']) or 'none'} | {len(B['e2_false_releases'])} |", "",
          "Releases with no recorded ground truth are unverified, not known-good: "
          f"E2 {', '.join(B['e2_releases_without_ground_truth']) or 'none'}.", "",
          "## 3. Unaffected motors (truth UNAFFECTED)", "",
          f"Motors: {', '.join(C['unaffectedMotors'])}", "",
          "| Engine | Correctly released | Held UNRESOLVED | Held AFFECTED |", "|---|---|---|---|"]
    for k in ("e1", "e2"):
        c = C[k]
        L.append(f"| {k.upper()} | {', '.join(c['released']) or '-'} ({len(c['released'])}) | "
                 f"{', '.join(c['heldUnresolved']) or '-'} ({len(c['heldUnresolved'])}) | "
                 f"{', '.join(c['heldAffected']) or '-'} ({len(c['heldAffected'])}) |")
    L += ["", "## 4. Case 06 family, P1, before and after", "",
          "| Case | Truth | E1 (v1) | E2 (v2) | E2 reasons |", "|---|---|---|---|---|"]
    for d in D:
        L.append(f"| {d['caseId']} | {d['truth']} | {SHORT[d['v1']['finding']]} | {SHORT[d['v2']['finding']]} | "
                 f"{', '.join(d['v2']['reasons'])} |")
    L += ["", "case-06: E1 releases a motor whose DE still holds an affected bearing (false release). E2 holds it "
          "with AMBIGUOUS_SLOT_ATTRIBUTION. case-06c shows a valid slot-label scan does not change that. "
          "case-06e has identical events to 06c but the technician really replaced DE: it stays held, which is "
          "the price of not guessing. case-06f adds an independent QA check and is released.", "",
          "## 5. Regressions and differences between engines", "",
          f"- Safety regressions (E2 releases truth-AFFECTED that E1 did not): {len(E['safety_regressions'])}",
          f"- Behavioral regressions (E2 vs O2): {len(E['behavioral_regressions_vs_o2'])}",
          f"- Unexplained E2-vs-O1 differences: {len(E['unexplained_vs_o1'])}", "",
          "Released by E1, held by E2:", ""]
    for x in E["released_in_v1_now_held"]:
        L.append(f"- {x['case']} {x['policy'][-2:]}: {SHORT[x['v1']]} -> {SHORT[x['v2']]} - {x['assessment']}")
    L += ["", "Held by E1, released by E2: " + (", ".join(f"{x['case']} {x['policy'][-2:]}"
                                                     for x in E["held_in_v1_now_released"]) or "none"), "",
          "Other differences (same finding):", ""]
    for x in E["other_differences"]:
        L.append(f"- {x['case']} {x['policy'][-2:]}: {x['detail']}")
    if not E["other_differences"]:
        L.append("- none")
    L.append("")
    return "\n".join(L)


def main():
    r = compute()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "v1_v2_comparison.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(md(r))
    with open(os.path.join(OUT, "v1_v2_comparison.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(r, f, indent=2, default=str)
    print(json.dumps(dict(gate=r["gate"], e2_false=r["B"]["e2_false_releases"], e1_false=r["B"]["e1_false_releases"],
                          e2_releases=r["B"]["e2_releases_all"], unaffected=r["C"]), indent=1))


if __name__ == "__main__":
    main()
