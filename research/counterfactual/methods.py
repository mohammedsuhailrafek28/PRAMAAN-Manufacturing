"""Baseline A0, candidate A1 (exact, dominance-pruned), A1p (relevance-pruned), and the independent brute-force oracle."""
import itertools
import time

import ops as O
import sandbox

TARGETS = ["EXCLUDED_WITH_EVIDENCE", "UNRESOLVED", "AFFECTED"]
FAVORABLE = {"QA_VERIFY": "U", "RECOVER_RECORD": "U", "ARCHIVE_ACCESS": "OUT", "INSPECT": "PASS", "CORRECTION": "U"}


class Evaluator:
    """Memoised sandbox replay of (scenario + op set). `evals` counts real evaluator runs."""

    def __init__(self, sc):
        self.sc, self.cache, self.evals, self.seconds = sc, {}, 0, 0.0

    def run(self, ops):
        key = frozenset(o["id"] for o in ops)
        if key not in self.cache:
            t0 = time.perf_counter()
            case, wm = O.apply_ops(self.sc, ops)
            self.cache[key] = sandbox.summary(sandbox.replay(case, self.sc["policy"], watermark=wm))
            self.seconds += time.perf_counter() - t0
            self.evals += 1
        return self.cache[key]


# --------------------------------------------------------------------------------------------------------------- A0
# Reason code -> predetermined evidence request class. Written from the reason-code definitions before A1 existed.
A0_TABLE = {
    "SOURCE_SEQUENCE_GAP": "RECOVER_RECORD", "WORK_ORDER_UNRECONCILED": "QA_VERIFY", "MATERIAL_CAPTURE_GAP": "QA_VERIFY",
    "EVENT_ORDER_INTEGRITY": "CORRECTION", "EVENT_INTEGRITY_VIOLATION": "CORRECTION",
    "NO_TRUSTED_BASELINE": "QA_VERIFY", "CURRENT_STATE_UNVERIFIED": "QA_VERIFY", "UNTRUSTED_SOURCE_CLAIM": "QA_VERIFY",
    "AMBIGUOUS_SLOT_ATTRIBUTION": "QA_VERIFY", "UNTRUSTED_AFFECTED_OBSERVATION": "QA_VERIFY",
    "LATE_CLAIM_RISK_INCREASING": "QA_VERIFY", "LATE_CLAIM_RISK_DECREASING_NOT_APPLIED": "QA_VERIFY",
    "DOUBLE_OCCUPANCY": "QA_VERIFY", "REMOVAL_OBSERVATION_MISMATCH": "QA_VERIFY", "REMOVAL_RECORD_INCONSISTENT": "QA_VERIFY",
    "VERIFIED_STATE_MISMATCH": "QA_VERIFY", "REMOVAL_SLOT_LABEL_MISMATCH": "QA_VERIFY", "REMOVAL_SERIAL_IN_OTHER_SLOT": "QA_VERIFY",
    "DAMAGE_INSPECTION_MISSING": "INSPECT", "DAMAGE_INSPECTION_INVALID": "INSPECT", "DAMAGE_INSPECTION_FAILED": "INSPECT",
    "EXPOSURE_UNKNOWN": "QA_VERIFY", "HISTORY_GAP_NOT_RECOVERED_BY_VERIFICATION": "QA_VERIFY",
    "REMEDIATION_COMPLETENESS_UNCERTAIN": "QA_VERIFY",
}
A0_NO_REQUEST = {"VERIFIED_AFFECTED_LOT_PRESENT", "HISTORICAL_EXPOSURE_CONFIRMED", "AFFECTED_LOT_INSTALLED", "CORROBORATED_BY_VERIFICATION"}


def a0(sc, baseline):
    """-> {requests:[{class,slot,text}], opIds:[...]} using only the baseline reason codes."""
    wanted = []
    for r in baseline["reasons"]:
        cls = A0_TABLE.get(r)
        if cls and cls not in [w[0] for w in wanted]:
            wanted.append((cls, r))
    requests, op_ids, cat = [], [], O.catalog(sc)
    slots = sc["policy"]["affectedSlots"]
    for cls, reason in wanted:
        want = FAVORABLE[cls]
        for o in cat:
            if o["cls"] == cls and o["hyp"] == want and (cls in ("RECOVER_RECORD", "ARCHIVE_ACCESS", "CORRECTION") or o["target"].split(":")[1] in slots):
                if cls == "CORRECTION" and o["target"].split(":")[1] not in slots:
                    continue
                if cls == "RECOVER_RECORD" and o["events"][0]["sourceId"] not in _sources_of_reason(baseline, sc):
                    continue
                op_ids.append(o["id"])
                requests.append(dict(reason=reason, **{"class": cls}, text=o["text"], opId=o["id"]))
    unobtainable = []
    for cls, reason in wanted:                      # the static table does not know obtainability: report requests it could not instantiate
        if not any(r["class"] == cls for r in requests):
            unobtainable.append(dict(reason=reason, **{"class": cls}))
    return dict(requests=requests, opIds=sorted(set(op_ids)), uninstantiable=unobtainable,
                noRequestReasons=[r for r in baseline["reasons"] if r in A0_NO_REQUEST])


def _sources_of_reason(baseline, sc):
    return {l["sourceId"] for l in sc["facts"]["lostRecords"]}


# --------------------------------------------------------------------------------------------------------------- A1
def search(sc, K=3, budget=5000, op_filter=None, order=None, dominance=True):
    """Exact level-wise search over subsets of the admissible catalog; sets are sets of op ids (never sequences).

    Reports, per target finding other than the baseline's, every subset-minimal admissible op set of size <= K, grouped by size.
    Complete only if all subsets up to K were enumerated within `budget` evaluator runs."""
    ev = Evaluator(sc)
    base = ev.run([])
    cat = [o for o in O.catalog(sc) if not O.violations(o, sc)]
    if op_filter:
        cat = [o for o in cat if op_filter(o)]
    if order:
        cat = [cat[i] for i in order(len(cat))]
    found = {t: [] for t in TARGETS if t != base["finding"]}
    complete, enumerated, skipped = True, 0, 0
    for k in range(1, K + 1):
        for combo in itertools.combinations(cat, k):
            if O.set_violations(combo, sc):
                continue
            ids = frozenset(o["id"] for o in combo)
            if dominance and found and all(any(s <= ids for s in found[t]) for t in found):
                skipped += 1
                continue
            if ev.evals >= budget:
                complete = False
                break
            enumerated += 1
            f = ev.run(combo)["finding"]
            if f in found and not any(s <= ids for s in found[f]):
                found[f].append(ids)
        if not complete:
            break
    return dict(baseline=base, catalogSize=len(cat), K=K, budget=budget, complete=complete, evals=ev.evals, enumerated=enumerated,
                skippedByDominance=skipped, seconds=round(ev.seconds, 4), found={t: [sorted(s) for s in v] for t, v in found.items()},
                evaluator=ev, catalog={o["id"]: o for o in cat})


def minimal(found_list):
    """-> (minimum size or None, [sets of that size])."""
    if not found_list:
        return None, []
    m = min(len(s) for s in found_list)
    return m, [s for s in found_list if len(s) == m]


# ------------------------------------------------------------------------------------------------------------ oracle
def brute_force_oracle(sc, K=3, include_inadmissible=False, keep=None):
    """Independent enumeration: every subset of size 1..K of the catalog, evaluated with no memo, no dominance, no early exit.
    Subset-minimality is computed afterwards. Shares only ops.apply_ops/violations (checked separately by independent replay)."""
    cat = [o for o in O.catalog(sc, include_inadmissible=include_inadmissible)
           if (include_inadmissible or not O.violations(o, sc)) and (keep is None or o["id"] in keep)]
    case0, wm0 = _apply(sc, [])
    base = sandbox.summary(sandbox.replay(case0, sc["policy"], watermark=wm0))
    sols = {t: [] for t in TARGETS if t != base["finding"]}
    evals = 0
    results = {}
    for k in range(1, K + 1):
        for combo in itertools.combinations(cat, k):
            if len({o["target"] for o in combo}) != len(combo):
                continue
            case, wm = _apply(sc, combo)
            f = sandbox.summary(sandbox.replay(case, sc["policy"], watermark=wm))["finding"]
            evals += 1
            results[frozenset(o["id"] for o in combo)] = f
    for ids, f in results.items():
        if f in sols and not any(other < ids and results[other] == f for other in results):
            sols[f].append(sorted(ids))
    return dict(baseline=base, catalogSize=len(cat), evals=evals, minimal={t: [sorted(s) for s in v] for t, v in sols.items()})


def _apply(sc, ops):
    return O.apply_ops(sc, list(ops))


# ------------------------------------------------------------------------------------------------------ explanations
def solution_report(sc, ev, cat, ids, base):
    """Structured counterfactual for one op set: items, predicted effect from a sandbox replay, leave-one-out necessity."""
    ops = [cat[i] for i in ids]
    after = ev.run(ops)
    items = [dict(opId=o["id"], what=o["text"], evidenceClass=o["cls"], hypothesis=o["hyp"],
                  issuer=sorted({e["sourceId"] for e in o["events"]}), actor=sorted({e["actorId"] for e in o["events"]}),
                  slots=o["addresses"].get("slots"), precondition=o["explanation"],
                  mustBeActuallyObtained=True) for o in ops]
    loo = {o["id"]: ev.run([x for x in ops if x is not o])["finding"] for o in ops} if len(ops) > 1 else {}
    return dict(items=items, hypotheticalFinding=after["finding"], reasonsRemoved=sorted(set(base["reasons"]) - set(after["reasons"])),
                reasonsAdded=sorted(set(after["reasons"]) - set(base["reasons"])), reasonsAfter=after["reasons"],
                leaveOneOut=loo, outcomeDependence="Holds only if the evidence, once actually obtained, shows the hypothesised content "
                "(for example the inspected bearing is not from an affected lot). Obtaining different content can change the finding differently.")


DISCLAIMER = ("HYPOTHETICAL. This is not evidence. No clearance or release eligibility exists unless the listed evidence is actually "
              "obtained, recorded through the authoritative channels and evaluated by the production evaluator.")


def explain_a1(sc, r, target="EXCLUDED_WITH_EVIDENCE"):
    base, ev = r["baseline"], r["evaluator"]
    sets = [frozenset(s) for s in r["found"].get(target, [])]
    m, mins = minimal(sets)
    alt = [solution_report(sc, ev, r["catalog"], sorted(s), base) for s in mins]
    return dict(question=f"minimum admissible additional evidence to move this motor from {base['finding']} to {target}",
                status=("NO_SOLUTION_IN_SEARCH_SPACE" if m is None and r["complete"] else "INCOMPLETE_SEARCH" if m is None else "MINIMAL_WITHIN_SEARCH_SPACE"),
                minimumSize=m, solutions=alt, equallyMinimalAlternatives=len(alt),
                searchScope=dict(admissibleOperations=r["catalogSize"], maxSetSize=r["K"], evaluatorRuns=r["evals"], complete=r["complete"],
                                 note="minimality is claimed only within this declared operation set and size bound"),
                disclaimer=DISCLAIMER)


def explain_a0(sc, a):
    return dict(requests=[dict(request=x["text"], class_=x["class"], because=x["reason"]) for x in a["requests"]])


RUBRIC = ["evidence_type_and_slot", "issuer_named", "preconditions", "outcome_dependence", "reason_diff", "scope_and_completeness",
          "alternatives", "non_evidence_disclaimer"]


def rubric_a1(x):
    sol = x["solutions"]
    return dict(evidence_type_and_slot=bool(sol) and all(i["evidenceClass"] and i["slots"] for s in sol for i in s["items"]),
                issuer_named=bool(sol) and all(i["issuer"] and i["actor"] for s in sol for i in s["items"]),
                preconditions=bool(sol) and all(i["precondition"] for s in sol for i in s["items"]),
                outcome_dependence=bool(sol) and all(s["outcomeDependence"] for s in sol),
                reason_diff=bool(sol) and all("reasonsRemoved" in s for s in sol),
                scope_and_completeness="searchScope" in x and "complete" in x["searchScope"],
                alternatives="equallyMinimalAlternatives" in x, non_evidence_disclaimer="HYPOTHETICAL" in x.get("disclaimer", ""))


def rubric_a0(x):
    rq = x["requests"]
    return dict(evidence_type_and_slot=bool(rq) and all(r["class_"] and r["request"] for r in rq), issuer_named=False, preconditions=False,
                outcome_dependence=False, reason_diff=False, scope_and_completeness=False, alternatives=False, non_evidence_disclaimer=False)
