"""Experiment A driver. Everything runs in memory against frozen synthetic scenarios; the only writes go to --out.

python run_experiment.py --out results/run1 --seed 20261024 [--guard]
"""
import argparse
import copy
import json
import os
import platform
import random
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True      # never write .pyc next to the frozen sources
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import methods as M  # noqa: E402
import ops as O  # noqa: E402
import safety  # noqa: E402
import sandbox  # noqa: E402
import scenarios as S  # noqa: E402

K, BUDGET = 3, 5000
PRIMARY = "EXCLUDED_WITH_EVIDENCE"


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=1, sort_keys=True, default=list)
        f.write("\n")


def independent(sc_file, ops, tmp):
    """Replay the added events in a fresh interpreter that shares no code with the search."""
    added = dict(events=[e for o in ops for e in o["events"]], sessions=[s for o in ops for s in o["sessions"]])
    p = os.path.join(tmp, "added.json")
    json.dump(added, open(p, "w"))
    out = subprocess.run([sys.executable, "-I", "-B", os.path.join(HERE, "independent_replay.py"), sc_file, p], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(out.stderr[-500:])
    return json.loads(out.stdout)


def classify_a0(sc, a0_out, ev, oracle_min):
    ops = [o for o in O.catalog(sc) if o["id"] in a0_out["opIds"]]
    res = ev.run(ops) if ops else ev.run([])
    ok = res["finding"] == PRIMARY
    n = len(ops)
    asked = bool(a0_out["requests"] or a0_out["uninstantiable"])   # the static table asks for something, obtainable or not
    if oracle_min is None:
        kind = "false_promise" if asked else "correct_none"
    elif not a0_out["requests"]:
        kind = "missed"
    elif not ok:
        kind = "insufficient"
    else:
        kind = "correct_minimal" if n == oracle_min else "correct_nonminimal"
    needed = sum(1 for o in ops if ev.run([x for x in ops if x is not o])["finding"] != PRIMARY) if ok else 0
    return dict(kind=kind, size=n, unobtainableRequests=len(a0_out["uninstantiable"]), reachedPrimary=ok, resultFinding=res["finding"], requestsNecessary=needed, opIds=a0_out["opIds"])


def run_scenarios(out):
    rows, rep_mismatch, rep_total = [], 0, 0
    tmp = tempfile.mkdtemp(prefix="cfrep_")
    for sc in S.load_all():
        sc_file = os.path.join(S.HERE, "scenarios", sc["id"] + ".json")
        t0 = time.perf_counter()
        r = M.search(sc, K=K, budget=BUDGET)
        t_a1 = time.perf_counter() - t0
        base, ev, cat = r["baseline"], r["evaluator"], r["catalog"]
        found = {t: [frozenset(s) for s in v] for t, v in r["found"].items()}
        a1 = {t: M.minimal(v) for t, v in found.items()}
        # candidate: relevance-pruned variant guided by the baseline table
        classes = {M.A0_TABLE[x] for x in base["reasons"] if x in M.A0_TABLE} | {"ARCHIVE_ACCESS"}
        rp = M.search(sc, K=K, budget=BUDGET, op_filter=lambda o: o["cls"] in classes)
        ap = {t: M.minimal([frozenset(s) for s in v]) for t, v in rp["found"].items()}
        t0 = time.perf_counter()
        orc = M.brute_force_oracle(sc, K=K)
        t_orc = time.perf_counter() - t0
        om = {t: M.minimal([frozenset(s) for s in v]) for t, v in orc["minimal"].items()}
        orc_only = M.brute_force_oracle(sc, K=K, include_inadmissible=True)
        omi = {t: M.minimal([frozenset(s) for s in v]) for t, v in orc_only["minimal"].items()}
        match = all(a1[t][0] == om[t][0] and sorted(map(sorted, a1[t][1])) == sorted(map(sorted, om[t][1])) for t in om)
        match_p = all(ap[t][0] == om[t][0] and sorted(map(sorted, ap[t][1])) == sorted(map(sorted, om[t][1])) for t in om)
        # independent replay of every reported minimal solution (all targets)
        reps = []
        for t, (m, mins) in a1.items():
            for ids in mins:
                ops = [cat[i] for i in sorted(ids)]
                pred = ev.run(ops)
                got = independent(sc_file, ops, tmp)
                same = got["finding"] == pred["finding"] and got["reasons"] == pred["reasons"]
                rep_total += 1
                rep_mismatch += (not same)
                reps.append(dict(target=t, ids=sorted(ids), predicted=pred["finding"], independent=got["finding"], same=same))
        a0_out = M.a0(sc, base)
        a0c = classify_a0(sc, a0_out, ev, om[PRIMARY][0])
        x1 = M.explain_a1(sc, r, PRIMARY)
        x0 = M.explain_a0(sc, a0_out)
        rb1, rb0 = M.rubric_a1(x1), M.rubric_a0(x0)
        sol_ids = {i for s in x1["solutions"] for it in s["items"] for i in [it["opId"]]}
        row = dict(id=sc["id"], title=sc["title"], intent=sc["intent"], baseline=base,
                   catalogSize=r["catalogSize"], inadmissibleOnlyOps=sorted(o["id"] for o in O.catalog(sc, True) if O.violations(o, sc)),
                   a1=dict(complete=r["complete"], evals=r["evals"], seconds=round(t_a1, 4), skippedByDominance=r["skippedByDominance"],
                           minimum={t: a1[t][0] for t in a1}, minimal={t: [sorted(s) for s in a1[t][1]] for t in a1},
                           largerSubsetMinimal={t: len(found[t]) - len(a1[t][1]) for t in found}),
                   a1pruned=dict(evals=rp["evals"], catalogSize=rp["catalogSize"], minimum={t: ap[t][0] for t in ap},
                                 matchesOracle=match_p),
                   oracle=dict(evals=orc["evals"], seconds=round(t_orc, 4), minimum={t: om[t][0] for t in om},
                               minimal={t: [sorted(s) for s in om[t][1]] for t in om}),
                   oracleEvaluatorOnly=dict(minimum={t: omi[t][0] for t in omi}, minimal={t: [sorted(s) for s in omi[t][1]] for t in omi},
                                            inadmissibleAlternatives={t: [sorted(s) for s in omi[t][1] if sorted(s) not in [sorted(x) for x in om[t][1]]]
                                                                      for t in omi}),
                   a1MatchesOracle=match, independentReplay=reps, a0=a0c, a0Requests=a0_out,
                   explainA1=x1, explainA0=x0, rubricA1=rb1, rubricA0=rb0)
        rows.append(row)
        dump(os.path.join(out, "scenarios", sc["id"] + ".json"), row)
        print(f"{sc['id']} base={base['finding'][:4]} cat={r['catalogSize']} A1 min(EXCL)={a1.get(PRIMARY, (None,))[0]} oracle={om.get(PRIMARY, (None,))[0]} "
              f"match={match} A1p_match={match_p} A0={a0c['kind']} evals A1={r['evals']} oracle={orc['evals']}", flush=True)
    return rows, dict(total=rep_total, mismatches=rep_mismatch)


# -------------------------------------------------------------------------------------------- admissibility fuzzing
MUTATIONS = {
    "wrong_source": (("QA_VERIFY", "INSPECT", "ARCHIVE_ACCESS"), lambda e: e.update(sourceId="HANDHELD-09")),
    "unauthorized_actor": (("QA_VERIFY", "INSPECT", "ARCHIVE_ACCESS"), lambda e: e.update(actorId="EMP-099")),
    "non_independent_actor": (("QA_VERIFY", "INSPECT"), lambda e: e.update(actorId="EMP-009")),
    "backdated": (("QA_VERIFY", "INSPECT", "CORRECTION"), lambda e: e.update(occurredAt="2026-09-01T00:00:00Z", recordedAt="2026-09-01T00:00:04Z")),
    "recorded_before_occurred": (("QA_VERIFY", "INSPECT", "CORRECTION", "ARCHIVE_ACCESS"), lambda e: e.update(recordedAt="2020-01-01T00:00:00Z")),
    "wrong_motor": (("QA_VERIFY", "INSPECT", "CORRECTION", "ARCHIVE_ACCESS", "RECOVER_RECORD"), lambda e: e.update(motorSerial="M-043")),
    "lot_outside_domain": (("QA_VERIFY", "CORRECTION", "RECOVER_RECORD"),
                           lambda e: e["payload"].update({k: "BR-999" for k in ("observedLot", "lot") if k in e["payload"]})),
    "no_evidence_reference": (("QA_VERIFY", "INSPECT", "ARCHIVE_ACCESS"), lambda e: e.update(evidenceRefs=[])),
    "tampered_envelope": (("RECOVER_RECORD",), lambda e: e.update(sourceSeq=e["sourceSeq"] + 5)),
    "unapproved_method": (("QA_VERIFY",), lambda e: e["payload"].update(method="VISUAL_GUESS")),
    "wrong_protocol": (("INSPECT",), lambda e: e["payload"].update(protocolId="OTHER-PROTO")),
}


def fuzz(seed, n=400):
    rng, cases = random.Random(seed), []
    for sc in S.load_all():
        for o in O.catalog(sc):
            if O.violations(o, sc):
                continue
            for name, (classes, fn) in MUTATIONS.items():
                if o["cls"] in classes:
                    cases.append((sc, o, name, fn))
    clean = [(sc["id"], o["id"]) for sc in S.load_all() for o in O.catalog(sc) if not O.violations(o, sc)]
    rng.shuffle(cases)
    picked = cases[:n]
    missed, flagged, eval_accepts, per_mut = [], 0, 0, {}
    for sc, o, name, fn in picked:
        m = copy.deepcopy(o)
        for e in m["events"]:
            fn(e)
        v = O.violations(m, sc)
        per_mut.setdefault(name, [0, 0])[0] += 1
        if v:
            flagged += 1
            per_mut[name][1] += 1
        else:
            missed.append((sc["id"], o["id"], name))
        base = M.Evaluator(sc).run([])["finding"]
        try:
            f = M.Evaluator(sc).run([m])["finding"]
        except Exception as exc:                       # an evaluator crash on a malformed op is itself a finding
            f = "EVALUATOR_ERROR:" + type(exc).__name__
        if f == PRIMARY and base != PRIMARY:
            eval_accepts += 1
    return dict(seed=seed, applicableMutants=len(cases), tested=len(picked), flagged=flagged, missed=missed, perMutation=per_mut,
                cleanOps=len(clean),
                rejectedCatalogOps=sorted(f"{sc['id']}:{o['id']}:{','.join(O.violations(o, sc))}" for sc in S.load_all()
                                          for o in O.catalog(sc, True) if O.violations(o, sc)),
                mutantsTheEvaluatorAloneWouldAcceptAsClearing=eval_accepts)


# ------------------------------------------------------------------------------------------ randomised catalog ablation
def ablation(seed, variants=20):
    rng, rows, bad_a1, bad_p, total = random.Random(seed), [], 0, 0, 0
    for sc in S.load_all():
        full = [o["id"] for o in O.catalog(sc) if not O.violations(o, sc)]
        for v in range(variants):
            keep = {i for i in full if rng.random() < 0.7}
            r = M.search(sc, K=K, budget=BUDGET, op_filter=lambda o, keep=keep: o["id"] in keep)
            orc = M.brute_force_oracle(sc, K=K, keep=keep)
            a1 = {t: sorted(map(sorted, M.minimal([frozenset(s) for s in x])[1])) for t, x in r["found"].items()}
            om = {t: sorted(map(sorted, M.minimal([frozenset(s) for s in x])[1])) for t, x in orc["minimal"].items()}
            ok = a1 == om
            total += 1
            bad_a1 += (not ok)
            if not ok:
                rows.append(dict(id=sc["id"], keep=sorted(keep)))
    return dict(seed=seed, catalogs=total, a1DisagreesWithOracle=bad_a1, details=rows[:10])


# ---------------------------------------------------------------------------------------------------- scaling
def scaling():
    base = next(s for s in S.load_all() if s["id"] == "A18")
    rows = []
    for n in (6, 10, 14, 18, 22):
        sc = copy.deepcopy(base)
        extra = []
        for i in range(max(0, n - 4)):
            occ = O._ts(S.NOW, 200 + i)
            e = O._event(f"DIS{i}", "INSPECTION_RECORDED", O.VERIFIER, occ, O._ts(occ, 4), O.VERIFIER_ACTOR, None,
                         dict(protocolId=O.PROTOCOL, scope=["DE"], result="PASS", inspectorQualifiedFor=[O.PROTOCOL]), refs=[f"EVID-DIS{i}"])
            extra.append(O._op(f"DIS:{i}", "INSPECT", f"distractor:{i}", "PASS", [e], [O._session(O.VERIFIER)], "distractor", dict(slots=["DE"]), "synthetic distractor"))
        orig = O.catalog
        O.catalog = lambda s, include_inadmissible=False, orig=orig, extra=extra: orig(s, include_inadmissible) + copy.deepcopy(extra)
        try:
            for k in (2, 3, 4):
                for name, kw in (("exact+dominance", dict(dominance=True)), ("exhaustive (no dominance)", dict(dominance=False))):
                    if name.startswith("exhaustive") and k == 4 and n > 18:
                        continue
                    t0 = time.perf_counter()
                    r = M.search(sc, K=k, budget=10 ** 7, **kw)
                    rows.append(dict(catalog=r["catalogSize"], K=k, method=name, evals=r["evals"], skipped=r["skippedByDominance"],
                                     seconds=round(time.perf_counter() - t0, 3), complete=r["complete"],
                                     minimumExcl=M.minimal([frozenset(s) for s in r["found"].get(PRIMARY, [])])[0]))
                    print("scaling", rows[-1], flush=True)
        finally:
            O.catalog = orig
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=20261024)
    ap.add_argument("--guard", action="store_true")
    ap.add_argument("--skip-scaling", action="store_true")
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    root = sandbox.ROOT
    import manifest
    assert manifest.compute() == json.load(open(os.path.join(S.HERE, "scenarios", "MANIFEST.json"))), "scenario files changed since the manifest"
    meta = dict(python=sys.version, platform=platform.platform(), sourceSha=safety.git(root, "rev-parse", "HEAD"),
                dirtyOutsideResults=bool(safety.git(root, "status", "--porcelain", "--", ".", ":!research/counterfactual/results")),
                baselineTag=safety.git(root, "rev-parse", "manufacturing-demo-v1.0^{commit}"), seed=a.seed, K=K, budget=BUDGET,
                evaluatorHashes=sandbox.evaluator_hashes(), command=" ".join(sys.argv), dependencies="python stdlib only")
    dump(os.path.join(out, "env.json"), meta)
    guard = safety.WriteGuard(out, tempfile.gettempdir(), allow_subprocess=True) if a.guard else None
    if guard:
        guard.__enter__()
    try:
        rows, rep = run_scenarios(out)
        fz = fuzz(a.seed)
        ab = ablation(a.seed)
        sc_rows = [] if a.skip_scaling else scaling()
    finally:
        viol = []
        if guard:
            viol = list(safety._state["violations"])
            guard.__exit__()
    ex = lambda k: [r for r in rows if r["a0"]["kind"] == k]
    resolvable = [r for r in rows if r["oracle"]["minimum"].get(PRIMARY) is not None]
    summ = dict(
        scenarios=len(rows), resolvable=len(resolvable), unresolvable=len(rows) - len(resolvable),
        a1MatchesOracle=sum(r["a1MatchesOracle"] for r in rows), a1PrunedMatchesOracle=sum(r["a1pruned"]["matchesOracle"] for r in rows),
        independentReplay=rep, fuzz={k: v for k, v in fz.items() if k != "perMutation"}, fuzzPerMutation=fz["perMutation"], ablation=ab,
        a0=dict({k: len(ex(k)) for k in ("correct_minimal", "correct_nonminimal", "insufficient", "missed", "false_promise", "correct_none")},
                excessRequests=sum(r["a0"]["size"] - r["a0"]["requestsNecessary"] for r in rows if r["a0"]["reachedPrimary"])),
        evalsA1=sum(r["a1"]["evals"] for r in rows), evalsOracle=sum(r["oracle"]["evals"] for r in rows),
        secondsA1=round(sum(r["a1"]["seconds"] for r in rows), 3), secondsOracle=round(sum(r["oracle"]["seconds"] for r in rows), 3),
        rubricMeanA0=round(sum(sum(r["rubricA0"].values()) for r in rows) / len(rows), 2),
        rubricMeanA1=round(sum(sum(r["rubricA1"].values()) for r in rows) / len(rows), 2), rubricMax=len(M.RUBRIC),
        guardViolations=viol, sourceSha=meta["sourceSha"])
    dump(os.path.join(out, "summary.json"), summ)
    dump(os.path.join(out, "fuzz.json"), fz)
    dump(os.path.join(out, "ablation.json"), ab)
    dump(os.path.join(out, "scaling.json"), sc_rows)
    print(json.dumps(summ, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
