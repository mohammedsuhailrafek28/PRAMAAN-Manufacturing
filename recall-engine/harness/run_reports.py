"""Generate the two separate Phase 1 reports (behavioral, safety) into reports/.

Run from anywhere:  python recall-engine/harness/run_reports.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle_harness import (AFF, EXCL, ROOT, UNRES, Config, load_all, oracle_final,  # noqa: E402
                            run_behavioral, run_final, summarise_behavioral)

OUT = os.path.join(ROOT, "reports")
SHORT = {EXCL: "EXCLUDED", AFF: "AFFECTED", UNRES: "UNRESOLVED"}


def pct(a, b):
    return f"{a}/{b} ({100 * a / b:.1f}%)" if b else "n/a"


def behavioral_md(rows, s, strict_rows, strict_s):
    L = ["# Behavioral agreement report: engine vs supplied expected outcomes", "",
         "Measures only whether the engine reproduces `oracle.json`. **This is not a safety measure.** "
         "Case 06 passes here by design and is a false exclusion in the safety report.", "",
         "## Summary", "",
         f"- Evaluations compared: **{s['evaluations']}** (10 cases, both policies, every decision version)",
         f"- Decision-level pass (finding + operational action + reviewRequired): **{pct(s['decisionAgree'], s['evaluations'])}**",
         f"- Full pass (decision + reason codes + watermark + per-slot reconciliation, gaps, conflicts, "
         f"supersession link, trigger, notification): **{pct(s['fullAgree'], s['evaluations'])}**",
         f"- Flag agreement (informational flags compared separately): {pct(s['flagAgree'], s['evaluations'])}", "",
         "## By recall policy", "",
         "| Policy | Evaluations | Decision-level pass | Full pass |", "|---|---|---|---|"]
    for p, b in sorted(s["byPolicy"].items()):
        L.append(f"| {p} | {b['n']} | {pct(b['decision'], b['n'])} | {pct(b['full'], b['n'])} |")
    L += ["", "## Every evaluation", "",
          "| Case | Policy | Ver | Expected (finding / action / review) | Engine | Decision | Full |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        e, g = r["expected"], r["got"]
        f = lambda d: f"{SHORT[d['evidenceFinding']]} / {d['operationalAction']} / {str(d['reviewRequired']).lower()}"
        L.append(f"| {r['caseId']} | {r['policyId'][-2:]} | v{r['version']} | {f(e)} | {f(g)} | "
                 f"{'pass' if not r['decisionDiffs'] else 'FAIL'} | "
                 f"{'pass' if not r['decisionDiffs'] and not r['detailDiffs'] else 'FAIL'} |")
    bad = [r for r in rows if r["decisionDiffs"] or r["detailDiffs"] or r["flagDiffs"]]
    L += ["", "## Disagreements", ""]
    if not bad:
        L.append("None.")
    for r in bad:
        L.append(f"- {r['caseId']} {r['policyId']} v{r['version']}: "
                 f"{r['decisionDiffs'] + r['detailDiffs'] + r['flagDiffs']}")
    L += ["", "## Strict lot-ambiguity profile (optional `Config(strict_lot_ambiguity=True)`)", "",
          f"- Decision-level pass: {pct(strict_s['decisionAgree'], strict_s['evaluations'])}; "
          f"full pass: {pct(strict_s['fullAgree'], strict_s['evaluations'])}",
          "- Disagreements with the supplied expectations under this profile:"]
    for r in strict_rows:
        if r["decisionDiffs"] or r["detailDiffs"]:
            L.append(f"  - {r['caseId']} {r['policyId']} v{r['version']}: "
                     f"{r['decisionDiffs'] + r['detailDiffs']}")
    L += ["", "The default profile follows the agreed lot-level semantics. The strict profile is the "
          "engine declining to exclude when a lot-level scan cannot be told apart from a sibling slot "
          "holding the same lot; it is the only expectation it breaks (see safety report).", ""]
    return "\n".join(L)


def safety_md(info):
    L = ["# Safety agreement report: engine vs independently recorded ground truth", "",
         "Compares the engine's final finding (full watermark) with `groundTruth` recorded in the case "
         "files, **not** with `oracle.json`. Only case-06 carries a `groundTruth` block "
         "(`trueP1Finding` = AFFECTED, P1 only). Everywhere else no independent truth exists, so the "
         "table says so rather than assuming the oracle is right.", "",
         "## Headline", "",
         f"- Final decisions evaluated: **{info['n']}** (10 cases x 2 policies)",
         f"- Decisions with independently recorded ground truth: **{info['withTruth']}**",
         f"- **Safety false exclusions (default profile): {len(info['falseExcl'])}**"
         + (" - " + ", ".join(info["falseExcl"]) if info["falseExcl"] else ""),
         f"- Safety false exclusions (strict lot-ambiguity profile): {len(info['falseExclStrict'])}",
         f"- Total EXCLUDED_WITH_EVIDENCE decisions: {info['exclTotal']}; of which backed by recorded "
         f"ground truth: {info['exclWithTruth']} (the rest are unverified against reality)",
         f"- Unresolved classifications: **{info['unres']}** of {info['n']} "
         f"(P1 {info['unresByPol'].get('RC-009/P1', 0)}, P2 {info['unresByPol'].get('RC-009/P2', 0)})",
         "- Case 06 is **not** counted as a safety success. The behavioral pass for case 06 is the "
         "documented unsafe exclusion: lot-level identity cannot tell a wrong-slot scan from a correct one.", "",
         "## Final decision per case and policy", "",
         "| Case | Policy | Engine | Oracle (final) | Ground truth | Safety verdict |", "|---|---|---|---|---|---|"]
    for r in info["rows"]:
        L.append(f"| {r['caseId']} | {r['policy']} | {SHORT[r['engine']]} | {SHORT[r['oracle']]} | "
                 f"{SHORT.get(r['truth'], '- (none recorded)')} | {r['verdict']} |")
    L += ["", "## Differences by recall policy", "",
          "| Policy | Engine EXCLUDED | AFFECTED | UNRESOLVED | Oracle EXCLUDED | AFFECTED | UNRESOLVED | Engine≠oracle (final) |",
          "|---|---|---|---|---|---|---|---|"]
    for p, c in sorted(info["byPolicy"].items()):
        L.append(f"| {p} | {c['e'][EXCL]} | {c['e'][AFF]} | {c['e'][UNRES]} | "
                 f"{c['o'][EXCL]} | {c['o'][AFF]} | {c['o'][UNRES]} | {c['diff']} |")
    L += ["", "P1 and P2 differ because P2 adds historical exposure + damage-inspection requirements: "
          "any history that touched an affected lot is AFFECTED unless a valid post-recall PASS inspection "
          "*and* verified remediation exist. P2 exclusions therefore require strictly more evidence than P1's.",
          "", "## Effects of slot verification (ablation: QA-02 events not ingested)", "",
          "| Case | Policy | With verification | Without | Effect |", "|---|---|---|---|---|"]
    for r in info["verifAblation"]:
        L.append(f"| {r['caseId']} | {r['policy']} | {SHORT[r['with']]} | {SHORT[r['without']]} | {r['effect']} |")
    L += ["", "Verification both *releases* (04 P1/P2: bounds the outage gap) and *catches* (06b, 05b: "
          "observes an affected lot the records hid). Without it, 06b degrades to exactly case 06's "
          "unsafe exclusion.", "",
          "## Effects of late corrections (ablation: QUALITY-PORTAL events not ingested)", "",
          "| Case | Policy | With correction | Without | Effect |", "|---|---|---|---|---|"]
    for r in info["lateAblation"]:
        L.append(f"| {r['caseId']} | {r['policy']} | {SHORT[r['with']]} | {SHORT[r['without']]} | {r['effect']} |")
    L += ["", "### Exclusions invalidated by later evidence (lifecycle)", ""]
    for t in info["withdrawn"]:
        L.append(f"- {t}")
    L += ["", "In both cases the earlier exclusion was a valid output *for the evidence ingested at the "
          "time* (P1 v1 EXCLUDED at watermark W1). The late claim withdrew it, applied RECALL_HOLD immediately, "
          "kept v1 in history, and recorded a notification obligation. Whether v1 was a true or false "
          "exclusion depends on whether the late claim is correct, which no ground truth in the archive "
          "settles.", "",
          "## Known unsafe case", "",
          "- **case-06 / RC-009/P1**: engine returns EXCLUDED (RELEASE_ELIGIBLE); ground truth AFFECTED. "
          "Technician replaced NDE but scanned DE; both slots hold lot BR-204 and the records are "
          "internally consistent. The engine emits flag `KNOWN_LIMITATION_LOT_LEVEL_SLOT_AMBIGUITY`. "
          "A scan-consistent record cannot be distinguished from reality at lot granularity without "
          "serials or independent verification (case 06b shows verification catches it; "
          "`tests/test_regressions.py` shows serial identity catches it).",
          "- Optional `strict_lot_ambiguity` profile returns UNRESOLVED for case 06 and removes the "
          "false exclusion at the cost of one behavioral disagreement. Whether to make it the default "
          "is a product decision, not something to tune away silently.", ""]
    return "\n".join(L)


def build_safety(rows_default):
    policies, coverage, cases, oracle = load_all()
    final = run_final()
    final_strict = run_final(Config(strict_lot_ambiguity=True))
    no_ver = run_final(drop_sources=("QA-02",))
    no_late = run_final(drop_sources=("QUALITY-PORTAL",))
    rows, falsex, falsex_s, by_pol = [], [], [], {}
    unres_by = {}
    for (cid, pid), d in sorted(final.items()):
        o = oracle_final(oracle[cid], pid)["evidenceFinding"]
        gt = cases[cid].get("groundTruth") or {}
        truth = gt.get("trueP1Finding") if pid.endswith("P1") else None
        if truth is None:
            verdict = "no ground truth" + (" (exclusion unverified)" if d["evidenceFinding"] == EXCL else "")
        elif d["evidenceFinding"] == EXCL and truth == AFF:
            verdict = "**FALSE EXCLUSION**"
            falsex.append(f"{cid} {pid}")
        elif d["evidenceFinding"] == truth:
            verdict = "agrees with truth"
        else:
            verdict = f"over-cautious ({SHORT[d['evidenceFinding']]} vs truth {SHORT[truth]})"
        if truth == AFF and final_strict[(cid, pid)]["evidenceFinding"] == EXCL:
            falsex_s.append(f"{cid} {pid}")
        rows.append(dict(caseId=cid, policy=pid, engine=d["evidenceFinding"], oracle=o,
                         truth=truth, verdict=verdict))
        b = by_pol.setdefault(pid, dict(e={EXCL: 0, AFF: 0, UNRES: 0}, o={EXCL: 0, AFF: 0, UNRES: 0}, diff=0))
        b["e"][d["evidenceFinding"]] += 1
        b["o"][o] += 1
        b["diff"] += d["evidenceFinding"] != o
        if d["evidenceFinding"] == UNRES:
            unres_by[pid] = unres_by.get(pid, 0) + 1

    def abl(other):
        out = []
        for k, d in sorted(final.items()):
            w = other[k]["evidenceFinding"]
            if w != d["evidenceFinding"]:
                eff = ("loses exclusion (more cautious)" if d["evidenceFinding"] == EXCL else
                       "hides risk: finding becomes EXCLUDED" if w == EXCL else
                       "loses information, still held")
                out.append(dict(caseId=k[0], policy=k[1], **{"with": d["evidenceFinding"], "without": w},
                                effect=eff))
        return out

    withdrawn = []
    for r in rows_default:
        g = r["got"]
        if g.get("notificationObligation"):
            n = g["notificationObligation"]
            withdrawn.append(f"{r['caseId']} {r['policyId']}: {g['supersedesDecisionId']} (EXCLUDED) superseded by "
                             f"{g['decisionId']} ({SHORT[g['evidenceFinding']]}, {g['operationalAction']}, "
                             f"reviewRequired={str(g['reviewRequired']).lower()}); notification obligation: "
                             f"{n['reason']} if {n['appliesIfDecisionCommunicated']} was communicated")
    return dict(
        n=len(final), withTruth=sum(1 for r in rows if r["truth"]), rows=rows,
        falseExcl=falsex, falseExclStrict=falsex_s,
        exclTotal=sum(1 for r in rows if r["engine"] == EXCL),
        exclWithTruth=sum(1 for r in rows if r["engine"] == EXCL and r["truth"]),
        unres=sum(unres_by.values()), unresByPol=unres_by, byPolicy=by_pol,
        verifAblation=abl(no_ver), lateAblation=abl(no_late), withdrawn=withdrawn)


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = run_behavioral()
    s = summarise_behavioral(rows)
    srows = run_behavioral(Config(strict_lot_ambiguity=True))
    ss = summarise_behavioral(srows)
    info = build_safety(rows)
    with open(os.path.join(OUT, "behavioral_report.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(behavioral_md(rows, s, srows, ss))
    with open(os.path.join(OUT, "safety_report.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(safety_md(info))
    slim = [dict(caseId=r["caseId"], policyId=r["policyId"], version=r["version"],
                 expected={k: r["expected"].get(k) for k in
                           ("decisionId", "evidenceFinding", "operationalAction", "reviewRequired", "reasonCodes")},
                 engine={k: r["got"].get(k) for k in
                         ("decisionId", "evidenceFinding", "operationalAction", "reviewRequired",
                          "reasonCodes", "flags", "evidenceEventIds", "identityGranularity",
                          "policyVersion", "watermark", "supersedesDecisionId", "triggerEventId")},
                 decisionDiffs=r["decisionDiffs"], detailDiffs=r["detailDiffs"], flagDiffs=r["flagDiffs"])
            for r in rows]
    with open(os.path.join(OUT, "behavioral_results.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(dict(summary=s, strictSummary=ss, results=slim), f, indent=2)
    with open(os.path.join(OUT, "safety_results.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({k: v for k, v in info.items()}, f, indent=2)
    print(json.dumps(dict(behavioral=s, strict=ss, falseExclusions=info["falseExcl"],
                          falseExclusionsStrict=info["falseExclStrict"], unresolved=info["unres"]), indent=1))


if __name__ == "__main__":
    main()
