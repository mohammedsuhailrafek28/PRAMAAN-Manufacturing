"""Test harness: the ONLY place oracle.json is read. The engine never sees it.

Two independent measurements:
  behavioral - engine output vs the supplied expected outcomes (oracle.json)
  safety     - engine output vs independently recorded ground truth (case.groundTruth)
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from pramaan_recall import Config, evaluate, evaluate_series, load_case, load_policies  # noqa: E402

FIX = os.path.join(ROOT, "fixtures", "pramaan-mfg-fixtures")
EXCL, AFF, UNRES = "EXCLUDED_WITH_EVIDENCE", "AFFECTED", "UNRESOLVED"


def load_all():
    policies, coverage = load_policies(os.path.join(FIX, "policies.json"))
    cases = {}
    for p in sorted(glob.glob(os.path.join(FIX, "cases", "*.json"))):
        c = load_case(p)
        cases[c["caseId"]] = c
    with open(os.path.join(FIX, "oracle.json"), encoding="utf-8") as f:
        oracle = {o["caseId"]: o["evaluations"] for o in json.load(f)["cases"]}
    return policies, coverage, cases, oracle


# ------------------------------------------------------------- compare ----
def _gap_key(g):
    return (g.get("kind"), g.get("materiality"), g.get("sourceId"), g.get("from"),
            g.get("to"), g.get("eventId"), g.get("boundedByEventId"))


_CONFLICT_KEYS = ("occupiedBy", "supersededEventId", "correctionEventId",
                  "corroboratedByEventId", "verificationEventId", "recordedLot", "observedLot")


def compare_slots(exp, got):
    diffs = []
    if set(exp) != set(got):
        diffs.append(f"slot set expected {sorted(exp)} got {sorted(got)}")
    for name, e in exp.items():
        g = got.get(name)
        if g is None:
            continue
        for k in ("reconciliation", "baseline", "identityGranularity", "policyRelevance"):
            if e.get(k) != g.get(k):
                diffs.append(f"{name}.{k}: expected {e.get(k)} got {g.get(k)}")
        if e.get("currentLotPerRecords") != g.get("currentLotPerRecords"):
            diffs.append(f"{name}.currentLotPerRecords: expected {e.get('currentLotPerRecords')} "
                         f"got {g.get('currentLotPerRecords')}")
        eg = sorted(map(_gap_key, e.get("gaps", [])), key=str)
        gg = sorted(map(_gap_key, g.get("gaps", [])), key=str)
        if eg != gg:
            diffs.append(f"{name}.gaps: expected {eg} got {gg}")
        ec, gc = e.get("conflicts", []), g.get("conflicts", [])
        if sorted(c["kind"] for c in ec) != sorted(c["kind"] for c in gc):
            diffs.append(f"{name}.conflict kinds: expected {[c['kind'] for c in ec]} "
                         f"got {[c['kind'] for c in gc]}")
        else:
            for c in ec:
                if not any(x["kind"] == c["kind"] and all(
                        x.get(k) == c[k] for k in _CONFLICT_KEYS if k in c) for x in gc):
                    diffs.append(f"{name}.conflict {c['kind']} detail differs")
    return diffs


def compare(exp, got, exp_series, got_series):
    """-> (decision_diffs, detail_diffs, flag_diffs). Empty lists = agreement."""
    dec, det, flg = [], [], []
    for k, a, b in (("evidenceFinding", exp["evidenceFinding"], got["evidenceFinding"]),
                    ("operationalAction", exp["operationalAction"], got["operationalAction"]),
                    ("reviewRequired", exp["reviewRequired"], got["reviewRequired"])):
        if a != b:
            dec.append(f"{k}: expected {a} got {b}")
    if set(exp["reasonCodes"]) != set(got["reasonCodes"]):
        det.append(f"reasonCodes: expected {sorted(exp['reasonCodes'])} got {sorted(got['reasonCodes'])}")
    if exp["watermark"] != got["watermark"]:
        det.append(f"watermark: expected {exp['watermark']} got {got['watermark']}")
    det += compare_slots(exp["slots"], got["slots"])

    def idx(series, decision_id):
        return next((i for i, s in enumerate(series) if s["decisionId"] == decision_id), None)
    e_sup = idx(exp_series, exp.get("supersedesDecisionId")) if exp.get("supersedesDecisionId") else None
    g_sup = idx(got_series, got.get("supersedesDecisionId")) if got.get("supersedesDecisionId") else None
    if e_sup != g_sup:
        det.append(f"supersedes index: expected {e_sup} got {g_sup}")
    if exp.get("triggerEventId") != got.get("triggerEventId"):
        det.append(f"triggerEventId: expected {exp.get('triggerEventId')} got {got.get('triggerEventId')}")
    en, gn = exp.get("notificationObligation"), got.get("notificationObligation")
    if bool(en) != bool(gn) or (en and (en["required"] != gn["required"] or idx(
            exp_series, en["appliesIfDecisionCommunicated"]) != idx(
            got_series, gn["appliesIfDecisionCommunicated"]))):
        det.append(f"notificationObligation: expected {en} got {gn}")
    if set(exp.get("flags", [])) != set(got["flags"]):
        flg.append(f"flags: expected {sorted(exp.get('flags', []))} got {sorted(got['flags'])}")
    return dec, det, flg


# ----------------------------------------------------------------- runs ----
def run_behavioral(cfg=None):
    """Replay every oracle evaluation through the engine lifecycle."""
    policies, coverage, cases, oracle = load_all()
    rows = []
    for cid, evals in oracle.items():
        for pid in policies:
            exp = [e for e in evals if e["policyId"] == pid]
            if not exp:
                continue
            series = evaluate_series(cases[cid], policies[pid], coverage,
                                     [e["watermark"] for e in exp], cfg)
            for i, (e, g) in enumerate(zip(exp, series)):
                dec, det, flg = compare(e, g, exp, series)
                rows.append(dict(caseId=cid, policyId=pid, version=i + 1,
                                 expected=e, got=g, decisionDiffs=dec, detailDiffs=det,
                                 flagDiffs=flg))
    return rows


def run_final(cfg=None, drop_sources=()):
    """Engine finding at the full watermark per (case, policy); optionally ablate sources."""
    policies, coverage, cases, oracle = load_all()
    out = {}
    for cid, case in cases.items():
        wm = {}
        for e in case["events"]:
            wm[e["sourceId"]] = max(wm.get(e["sourceId"], 0), e["sourceSeq"])
        for s in drop_sources:
            if s in wm:
                wm[s] = 0
        for pid, pol in policies.items():
            out[(cid, pid)] = evaluate(case, pol, coverage, wm, cfg)
    return out


def oracle_final(oracle_evals, pid):
    return [e for e in oracle_evals if e["policyId"] == pid][-1]


def summarise_behavioral(rows):
    n = len(rows)
    dec = sum(1 for r in rows if not r["decisionDiffs"])
    full = sum(1 for r in rows if not r["decisionDiffs"] and not r["detailDiffs"])
    flags = sum(1 for r in rows if not r["flagDiffs"])
    by_pol = {}
    for r in rows:
        b = by_pol.setdefault(r["policyId"], dict(n=0, decision=0, full=0))
        b["n"] += 1
        b["decision"] += not r["decisionDiffs"]
        b["full"] += not r["decisionDiffs"] and not r["detailDiffs"]
    return dict(evaluations=n, decisionAgree=dec, fullAgree=full, flagAgree=flags, byPolicy=by_pol)
