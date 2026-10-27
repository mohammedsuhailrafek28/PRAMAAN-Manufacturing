"""Legacy / v2 / v3 semantics compared as separate measurements (never one blended score).

Engines: E1 = P1_LEGACY, E2 = SLOT_ATTRIBUTION_V2, E3 = UNTRUSTED_OBSERVATION_V3
Oracles: O1 supplied (frozen), O2 oracle-v2, O3 oracle-v3.  Truth: synthetic, P1 only.

A correct newer engine is not penalised for disagreeing with an older oracle's known-unsafe
expectation: such disagreements are classified from the declared transition and the ground truth.

Run:  python harness/compare_profiles.py   -> reports/v1_v2_v3_comparison.{md,json}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle_harness import (AFF, EXCL, FIX2, FIX3, ROOT, UNRES, V1_CONFIG, V2_CONFIG, V3_CONFIG,  # noqa: E402
                            load_all, load_truth, run_behavioral, run_final, summarise_behavioral)
from pramaan_recall import replay  # noqa: E402

OUT = os.path.join(ROOT, "reports")
SHORT = {EXCL: "EXCLUDED", AFF: "AFFECTED", UNRES: "UNRESOLVED"}
P1 = "RC-009/P1"


def _bad(r):
    return bool(r["decisionDiffs"] or r["detailDiffs"] or r["flagDiffs"])


def _transition_declared():
    out = set()
    for d, name in ((FIX2, "VERSION_TRANSITION.json"),):
        with open(os.path.join(d, name), encoding="utf-8") as f:
            out |= {(c["caseId"], c["policyId"]) for c in json.load(f)["changedEvaluations"]}
    return out


def legacy_replay(engines):
    """Store each oracle evaluation's decision under its own profile, then replay the stored record."""
    out = {}
    for label, (cfg, version, pv) in engines.items():
        policies, coverage, cases, _ = load_all(version, pv)
        rows = run_behavioral(cfg, version, pv)
        same = 0
        for r in rows:
            rec = r["got"]
            again = replay(cases[r["caseId"]], policies[r["policyId"]], coverage, rec)
            keys = ("evidenceFinding", "operationalAction", "reviewRequired", "flags",
                    "semanticsProfile", "coverageDigest")
            # PRIOR_EXCLUSION_WITHDRAWN is added by the lifecycle after evaluation, not by evaluate()
            stored = [c for c in rec["reasonCodes"] if c != "PRIOR_EXCLUSION_WITHDRAWN"]
            same += all(again[k] == rec[k] for k in keys) and again["reasonCodes"] == stored
        out[label] = dict(records=len(rows), reproduced=same, profile=cfg.profile)
    return out


def compute(e3_config=V3_CONFIG):
    _, _, cases3, _ = load_all(3)
    truth = load_truth(cases3)
    declared = _transition_declared()

    runs = {"E1/O1": run_behavioral(V1_CONFIG, 1), "E2/O2": run_behavioral(V2_CONFIG, 2),
            "E3/O3": run_behavioral(e3_config, 3), "E3/O1": run_behavioral(e3_config, 1, 3),
            "E3/O2": run_behavioral(e3_config, 2, 3), "E2/O1": run_behavioral(V2_CONFIG, 1, 2),
            "E1/O2": run_behavioral(V1_CONFIG, 2, 1), "E1/O3": run_behavioral(V1_CONFIG, 3, 1),
            "E2/O3": run_behavioral(V2_CONFIG, 3, 2)}
    A = {k: summarise_behavioral(v) for k, v in runs.items()}
    div = []
    for key in ("E3/O1", "E3/O2"):
        for r in runs[key]:
            if _bad(r):
                k = (r["caseId"], r["policyId"])
                div.append(dict(against=key, caseId=k[0], policyId=k[1],
                                v_old=r["expected"]["evidenceFinding"], v_new=r["got"]["evidenceFinding"],
                                classification=("DECLARED_IN_V2_TRANSITION" if k in declared else "UNEXPLAINED")))
    A_extra = dict(native_disagreements={k: [f"{r['caseId']} {r['policyId'][-2:]}" for r in runs[k] if _bad(r)]
                                         for k in ("E1/O1", "E2/O2", "E3/O3")},
                   divergences=div)

    f1 = run_final(V1_CONFIG, version=3, policy_version=1)
    f2 = run_final(V2_CONFIG, version=3, policy_version=2)
    f3 = run_final(e3_config, version=3, policy_version=3)

    def false_rel(f):
        return sorted(f"{c} {p[-2:]}" for (c, p), d in f.items()
                      if p == P1 and truth.get(c) == AFF and d["evidenceFinding"] == EXCL)

    def rel(f, pol=None):
        return sorted(f"{c} {p[-2:]}" for (c, p), d in f.items()
                      if d["evidenceFinding"] == EXCL and (pol is None or p == pol))

    def unaff(f):
        out = dict(released=[], heldUnresolved=[], heldAffected=[])
        for c in sorted(t for t, v in truth.items() if v == "UNAFFECTED"):
            out[{EXCL: "released", UNRES: "heldUnresolved", AFF: "heldAffected"}[f[(c, P1)]["evidenceFinding"]]].append(c)
        return out

    B = dict(truthAffected=sorted(c for c, t in truth.items() if t == AFF), truthUnaffected=sorted(
        c for c, t in truth.items() if t == "UNAFFECTED"),
        false_releases={"E1": false_rel(f1), "E2": false_rel(f2), "E3": false_rel(f3)},
        releases_p1={"E1": rel(f1, P1), "E2": rel(f2, P1), "E3": rel(f3, P1)},
        releases_all={"E1": rel(f1), "E2": rel(f2), "E3": rel(f3)},
        unaffected={"E1": unaff(f1), "E2": unaff(f2), "E3": unaff(f3)},
        never_affected_from_untrusted_alone=sorted(
            k[0] for k, d in f3.items() if k[0].startswith("case-08") and k[1] == P1 and d["evidenceFinding"] == AFF))

    def moves(a, b):
        held, rel_more, other = [], [], []
        for k in sorted(a):
            x, y = a[k]["evidenceFinding"], b[k]["evidenceFinding"]
            if x == y:
                continue
            t = truth.get(k[0]) if k[1] == P1 else None
            row = dict(case=k[0], policy=k[1], before=x, after=y, truth=t)
            if x == EXCL:
                row["assessment"] = ("INTENDED (release was false)" if t == AFF else
                                     "USEFULNESS COST (truth UNAFFECTED, now held)" if t == "UNAFFECTED" else
                                     "release unverifiable against ground truth")
                held.append(row)
            elif y == EXCL:
                row["assessment"] = "NEW RELEASE"
                rel_more.append(row)
            else:
                other.append(row)
        return dict(released_now_held=held, held_now_released=rel_more, other=other)

    m23, m12 = moves(f2, f3), moves(f1, f2)
    safety_reg = sorted(f"{c} {p[-2:]}" for (c, p), d in f3.items() if p == P1 and truth.get(c) == AFF
                        and d["evidenceFinding"] == EXCL and f2[(c, p)]["evidenceFinding"] != EXCL)
    E = dict(v2_to_v3=m23, v1_to_v2=m12, safety_regressions_v3_vs_v2=safety_reg,
             behavioral_regressions_vs_o3=A_extra["native_disagreements"]["E3/O3"],
             unexplained=[d for d in div if d["classification"] == "UNEXPLAINED"])

    L = legacy_replay({"P1_LEGACY": (V1_CONFIG, 1, 1), "SLOT_ATTRIBUTION_V2": (V2_CONFIG, 2, 2),
                       "UNTRUSTED_OBSERVATION_V3": (e3_config, 3, 3)})
    gate = dict(zeroFalseReleases=not B["false_releases"]["E3"], releasesNonZero=bool(B["releases_p1"]["E3"]),
                noSafetyRegression=not safety_reg,
                noBehavioralRegression=not E["behavioral_regressions_vs_o3"] and not E["unexplained"],
                legacyReplayExact=all(v["records"] == v["reproduced"] for v in L.values()),
                legacyOraclesStillAgree=not A_extra["native_disagreements"]["E1/O1"]
                and not A_extra["native_disagreements"]["E2/O2"],
                untrustedNeverAffected=not B["never_affected_from_untrusted_alone"])
    gate["pass"] = all(gate.values())
    return dict(A=A, A_extra=A_extra, B=B, E=E, legacyReplay=L, gate=gate, truth=truth)


def pct(s):
    return f"{s['decisionAgree']}/{s['evaluations']} | {s['fullAgree']}/{s['evaluations']}"


def md(r):
    A, X, B, E, L, g = r["A"], r["A_extra"], r["B"], r["E"], r["legacyReplay"], r["gate"]
    ok = lambda b: "PASS" if b else "FAIL"
    f = B["false_releases"]
    Ls = ["# Legacy / v2 / v3 semantics comparison", "",
          "Separate measurements, no blended score. E = engine profile, O = oracle version. Ground truth is "
          "synthetic and covers P1 only.", "", "## Gates", "",
          f"- Zero false releases (v3): **{ok(g['zeroFalseReleases'])}** ({len(f['E3'])} against "
          f"{len(B['truthAffected'])} truth-AFFECTED cases; legacy {len(f['E1'])}, v2 {len(f['E2'])})",
          f"- Still releases motors: {ok(g['releasesNonZero'])} ({len(B['releases_p1']['E3'])} P1 releases, "
          f"{len(B['releases_all']['E3'])} overall)",
          f"- No safety regression v3 vs v2: {ok(g['noSafetyRegression'])}",
          f"- No behavioral regression / no unexplained disagreement: {ok(g['noBehavioralRegression'])}",
          f"- Legacy and v2 oracles still reproduced by their own profiles: {ok(g['legacyOraclesStillAgree'])}",
          f"- Stored decisions replay exactly under their own profile: {ok(g['legacyReplayExact'])}",
          f"- An untrusted observation alone never yields AFFECTED: {ok(g['untrustedNeverAffected'])}", "",
          "## 1. Behavioral agreement (decision-level | full)", "",
          "| Engine / oracle | Evaluations | Decision | Full |", "|---|---|---|---|"]
    for k in ("E1/O1", "E2/O2", "E3/O3", "E3/O2", "E3/O1", "E2/O1", "E1/O2", "E1/O3", "E2/O3"):
        s = A[k]
        Ls.append(f"| {k} | {s['evaluations']} | {s['decisionAgree']}/{s['evaluations']} | {s['fullAgree']}/{s['evaluations']} |")
    Ls += ["", "Disagreements of the v3 engine with older oracles (classified, not defects when declared):", ""]
    Ls += [f"- {d['against']} {d['caseId']} {d['policyId'][-2:]}: {SHORT[d['v_old']]} -> {SHORT[d['v_new']]} "
           f"- {d['classification']}" for d in X["divergences"]] or ["- none"]
    Ls += ["", "## 2. False releases against ground truth", "",
           f"Truth AFFECTED: {', '.join(B['truthAffected'])}", "", "| Engine | False releases |", "|---|---|"]
    Ls += [f"| {k} | {', '.join(v) or 'none'} ({len(v)}) |" for k, v in f.items()]
    Ls += ["", "## 3. Unaffected motors", "", f"Truth UNAFFECTED: {', '.join(B['truthUnaffected'])}", "",
           "| Engine | Correctly released | Held UNRESOLVED | Held AFFECTED |", "|---|---|---|---|"]
    for k, c in B["unaffected"].items():
        Ls.append(f"| {k} | {len(c['released'])}: {', '.join(c['released']) or '-'} | "
                  f"{len(c['heldUnresolved'])}: {', '.join(c['heldUnresolved']) or '-'} | "
                  f"{len(c['heldAffected'])}: {', '.join(c['heldAffected']) or '-'} |")
    Ls += ["", "## 4. Movements between profiles (full watermark)", ""]
    for name, m in (("legacy -> v2", E["v1_to_v2"]), ("v2 -> v3", E["v2_to_v3"])):
        Ls.append(f"**{name}** - released then held:")
        Ls += [f"- {x['case']} {x['policy'][-2:]}: {SHORT[x['before']]} -> {SHORT[x['after']]} - {x['assessment']}"
               for x in m["released_now_held"]] or ["- none"]
        Ls += ["", "newly released: " + (", ".join(f"{x['case']} {x['policy'][-2:]}" for x in m["held_now_released"]) or "none"),
               "other finding changes: " + (", ".join(f"{x['case']} {x['policy'][-2:]}" for x in m["other"]) or "none"), ""]
    Ls += ["## 5. Legacy replay", "", "| Profile | Stored decisions | Reproduced exactly |", "|---|---|---|"]
    Ls += [f"| {k} | {v['records']} | {v['reproduced']} |" for k, v in L.items()]
    Ls.append("")
    return "\n".join(Ls)


def main():
    r = compute()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "v1_v2_v3_comparison.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(md(r))
    with open(os.path.join(OUT, "v1_v2_v3_comparison.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(r, f, indent=2, default=str)
    print(json.dumps(r["gate"], indent=1))


if __name__ == "__main__":
    main()
