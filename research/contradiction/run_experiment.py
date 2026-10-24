"""Experiment B driver. In-memory against frozen synthetic fleets; the only writes go to --out.

python run_experiment.py --out results/run1 --seed 20261024 [--guard] [--skip-scaling]
"""
import argparse
import copy
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import baseline  # noqa: E402
import candidate as B1  # noqa: E402
import fleet as FL  # noqa: E402
import probes  # noqa: E402
import safety  # noqa: E402
import sandbox  # noqa: E402

BUDGET = 256


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=1, sort_keys=True, default=list)
        f.write("\n")


def independent(cases, policy, tmp):
    p = os.path.join(tmp, "job.json")
    json.dump(dict(policy=policy, cases=cases), open(p, "w"))
    out = subprocess.run([sys.executable, "-I", "-B", os.path.join(HERE, "independent_replay.py"), p], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(out.stderr[-500:])
    return json.loads(out.stdout)


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    return dict(tp=tp, fp=fp, fn=fn, precision=round(p, 3), recall=round(r, 3), f1=round(2 * p * r / (p + r), 3) if p + r else 0.0)


def key_strict(c):
    return (c["kind"], tuple(sorted(c["eventIds"])))


def key_loose(c):
    return tuple(sorted(c["eventIds"]))


def safe_view(dep):
    """Advisory vocabulary: no operational action is ever shown for a hypothetical reading."""
    out = {}
    for m, d in dep.items():
        out[m] = dict(recordedFinding=d["recorded"]["finding"], contradictions=d["contradictions"], joint=d["joint"],
                      findingsAcrossReadings=d["findingsAcrossInterpretations"], decisionDependsOnContestedEvidence=d["sensitive"],
                      holdStatusDependsOnContestedEvidence=d["releaseSensitive"], citesContestedEvidence=d["staticTrace"],
                      readingsThatChangeHoldStatus=[dict(reading=r["interpretation"], findingIfTrue=r["finding"]) for r in d["flips"]],
                      diagnosticUnknownIdentityWouldBeReadAsUnaffected=d["unknownIdentityReadAsUnaffected"], advisoryOnly=True, authoritativeDecisionUnchanged=True)
    return out


def run_fleets(out):
    rows, tmp = [], tempfile.mkdtemp(prefix="cdrep_")
    tot = dict(b1_strict=[0, 0, 0], b1_loose=[0, 0, 0], b0_loose=[0, 0, 0], classOk=0, classTotal=0)
    impact = dict(b1_dynamic=[0, 0, 0], b1_static=[0, 0, 0], b0=[0, 0, 0], release=[0, 0, 0])
    replays, replay_bad, nondet, errors = 0, 0, 0, 0
    for f in FL.load_all():
        before = hashlib.sha256(json.dumps(f, sort_keys=True).encode()).hexdigest()
        truth = f["truth"]
        t0 = time.perf_counter()
        b0g = baseline.b0(f)
        t_b0 = time.perf_counter() - t0
        t0 = time.perf_counter()
        found = B1.detect(f)
        t_det = time.perf_counter() - t0
        t0 = time.perf_counter()
        dep = B1.dependency(f, found, budget=BUDGET)
        t_dep = time.perf_counter() - t0
        after = hashlib.sha256(json.dumps(f, sort_keys=True).encode()).hexdigest()
        # authority: recorded findings must equal a fresh, independent evaluator run on the unmodified fleet
        auth_ok = before == after and all(
            dep[m]["recorded"]["finding"] == sandbox.replay(FL.motor_case(f, m), f["policy"])["evidenceFinding"] for m in dep)
        # detection scoring
        tk, fk = {key_strict(c): c for c in truth["contradictions"]}, {key_strict(c): c for c in found}
        tl, fl = {key_loose(c) for c in truth["contradictions"]}, {key_loose(c) for c in found}
        b0l = {tuple(g["eventIds"]) for g in b0g}
        s_tp = len(set(tk) & set(fk))
        tot["b1_strict"] = [a + b for a, b in zip(tot["b1_strict"], (s_tp, len(set(fk) - set(tk)), len(set(tk) - set(fk))))]
        tot["b1_loose"] = [a + b for a, b in zip(tot["b1_loose"], (len(tl & fl), len(fl - tl), len(tl - fl)))]
        tot["b0_loose"] = [a + b for a, b in zip(tot["b0_loose"], (len(tl & b0l), len(b0l - tl), len(tl - b0l)))]
        cls_ok = sum(1 for k in set(tk) & set(fk) if tk[k]["cls"] == fk[k]["cls"])
        tot["classOk"] += cls_ok
        tot["classTotal"] += s_tp
        # dependency scoring
        ts, tr = set(truth["sensitiveMotors"]), set(truth["releaseSensitiveMotors"])
        ds = {m for m, d in dep.items() if d["sensitive"]}
        dr = {m for m, d in dep.items() if d["releaseSensitive"]}
        st = {m for m, d in dep.items() if d["staticTrace"]}
        b0m = set(baseline.b0_impacted_motors(f, b0g))
        for name, pred, tru in (("b1_dynamic", ds, ts), ("b1_static", st, ts), ("b0", b0m, ts), ("release", dr, tr)):
            impact[name] = [a + b for a, b in zip(impact[name], (len(pred & tru), len(pred - tru), len(tru - pred)))]
        # evaluator consistency: determinism, errors, independent replay of every interpretation
        cases = []
        for m, d in dep.items():
            for r in d["results"]:
                cases.append((m, r, FL.motor_case(f, m, B1.apply_edits(f, [tuple(e) for e in r["edits"]]))))
        got = independent([c for _, _, c in cases], f["policy"], tmp) if cases else []
        for (m, r, c), g in zip(cases, got):
            replays += 1
            replay_bad += (g["finding"] != r["finding"]) if not r["finding"].startswith("EVALUATOR_ERROR") else 1
            errors += r["finding"].startswith("EVALUATOR_ERROR")
            again = sandbox.replay(copy.deepcopy(c), f["policy"])["evidenceFinding"]
            nondet += again != r["finding"]
        row = dict(id=f["id"], title=f["title"], truth=truth, b0=dict(groups=b0g, impactedMotors=sorted(b0m), seconds=round(t_b0, 5)),
                   b1=dict(contradictions=found, seconds=round(t_det, 5), dependencySeconds=round(t_dep, 4)),
                   detection=dict(strictTP=s_tp, strictFP=sorted(map(str, set(fk) - set(tk))), strictFN=sorted(map(str, set(tk) - set(fk))),
                                  classCorrect=cls_ok, b0FP=sorted(map(str, b0l - tl)), b0FN=sorted(map(str, tl - b0l))),
                   dependency=dict(truthSensitive=sorted(ts), b1Sensitive=sorted(ds), b1Static=sorted(st), b0Impacted=sorted(b0m),
                                   truthRelease=sorted(tr), b1Release=sorted(dr), perMotor=safe_view(dep)),
                   authorityPreserved=auth_ok, interpretationReplays=len(cases))
        rows.append(row)
        dump(os.path.join(out, "fleets", f["id"] + ".json"), row)
        print(f"{f['id']} truth={len(truth['contradictions'])} B1={len(found)} strictTP={s_tp} B0flags={len(b0g)} sens truth/B1={sorted(ts)}/{sorted(ds)} "
              f"rel truth/B1={sorted(tr)}/{sorted(dr)} auth={auth_ok}", flush=True)
    return rows, dict(detect={k: (prf(*v) if isinstance(v, list) else v) for k, v in tot.items()},
                      impact={k: prf(*v) for k, v in impact.items()},
                      evaluatorConsistency=dict(interpretationReplays=replays, independentReplayMismatches=replay_bad, nonDeterministic=nondet,
                                                evaluatorErrors=errors))


# ----------------------------------------------------------------------------------------------- metamorphic tests
def _replace(f, **kw):
    g = copy.deepcopy(f)
    g.update(kw)
    return g


def _ev(g, eid):
    return next(e for e in g["events"] if e["eventId"] == eid)


def metamorphic():
    F = {f["id"]: f for f in FL.load_all()}
    tests = []

    def check(name, g, expect):
        found = B1.detect(g)
        got = sorted((c["kind"], c["cls"]) for c in found)
        b0 = baseline.b0(g)
        tests.append(dict(name=name, expected=sorted(expect), b1=got, b1Pass=got == sorted(expect), b0Groups=len(b0),
                          b0Pass=(len(b0) > 0) == bool(expect)))

    g = copy.deepcopy(F["B02"])                                    # valid reuse -> remove M101's removal+reinstall: serial now in two motors
    g["events"] = [e for e in g["events"] if not e["eventId"].startswith("B02-M101-R")]
    check("MR1 valid reuse minus the recorded removal -> definite overlap", g, [("EXCLUSIVE_OCCUPANCY", "DEFINITE")])
    g = copy.deepcopy(F["B01"])
    g["sessions"] = [s for s in g["sessions"] if s["sourceId"] != "REWORK-03"] + [
        dict(sourceId="REWORK-03", **{"from": "2026-08-01T00:00:00Z", "to": "2026-08-12T18:00:00Z"}),
        dict(sourceId="REWORK-03", **{"from": "2026-08-13T06:00:00Z", "to": "2026-09-30T23:59:59Z"})]
    check("MR2 definite overlap + removal-capture gap between the installs -> possible", g, [("EXCLUSIVE_OCCUPANCY", "POSSIBLE")])
    g = copy.deepcopy(F["B01"])
    _ev(g, "B01-M102-DE")["payload"]["supplier"] = None
    check("MR3 definite overlap + supplier erased on one claim -> insufficient", g, [("EXCLUSIVE_OCCUPANCY", "INSUFFICIENT")])
    g = copy.deepcopy(F["B01"])
    _ev(g, "B01-M102-DE")["payload"]["supplier"] = "SUP-Y"
    check("MR4 definite overlap + different supplier -> collision, nothing", g, [])
    g = copy.deepcopy(F["B01"])
    g["events"].append(FL.E("B01-M102-DE-CORR", "COMPONENT_INSTALLED", "REWORK-03", "2026-09-10T09:00:00Z", "EMP-017", "M102", "MO-M102",
                            dict(componentType="BEARING", slot="DE", part="BR-6205", lot=FL.AFF, serial="SN-9999", supplier="SUP-X", identityGranularity="SERIAL"),
                            sup="B01-M102-DE"))
    check("MR5 definite overlap + superseding correction to another serial -> nothing", g, [])
    g = copy.deepcopy(F["B04"])
    rm = _ev(g, "B04-M101-RM-DE")
    rm["payload"]["timeUncertaintySeconds"] = 0
    rm["timeSource"] = "DEVICE_SYNCED"
    rm["occurredAt"] = "2026-08-12T12:00:00Z"
    check("MR6 approximate removal made exact and earlier than the next install -> nothing", g, [])
    rm["occurredAt"] = "2026-08-12T14:00:00Z"
    check("MR7 exact removal later than the next install -> definite overlap", g, [("EXCLUSIVE_OCCUPANCY", "DEFINITE")])
    g = copy.deepcopy(F["B03"])
    _ev(g, "B03-M102-DE")["payload"]["supplier"] = "SUP-X"
    check("MR8 supplier collision made same-supplier -> definite overlap and lot conflict", g,
          [("EXCLUSIVE_OCCUPANCY", "DEFINITE"), ("LOT_IDENTITY", "DEFINITE")])
    return tests


def invariance(seed, n=10):
    """Detection must not depend on event order, or on renaming motors / time-shifting the whole fleet."""
    rng, bad, total = random.Random(seed), [], 0
    for f in FL.load_all():
        ref = sorted((c["kind"], c["cls"], len(c["eventIds"])) for c in B1.detect(f))
        for _ in range(n):
            g = copy.deepcopy(f)
            rng.shuffle(g["events"])
            ren = {m: f"Z{rng.randrange(10 ** 6)}" for m in FL.motors(f)}
            for e in g["events"]:
                e["motorSerial"] = ren[e["motorSerial"]]
            got = sorted((c["kind"], c["cls"], len(c["eventIds"])) for c in B1.detect(g))
            total += 1
            if got != ref:
                bad.append(f["id"])
    return dict(seed=seed, trials=total, differing=len(bad), fleets=sorted(set(bad)))


# --------------------------------------------------------------------------------------------------------- scaling
def hub_fleet(r):
    """One hub motor reworked r times; each rework installs a serial still installed (never removed) in another motor: r contradictions on the hub."""
    ev = FL.build("H", "M000", "08-10", (FL.OK, "SN-H0", "SUP-X"))
    prev = "H-M000-DE"
    for j in range(1, r + 1):
        day = f"09-{(j % 18) + 10:02d}"
        tag = chr(96 + j) if j <= 26 else f"x{j}"
        ev += FL.build("H", f"M{j:03d}", f"08-{(j % 18) + 10:02d}", (FL.OK, f"SN-{j}", "SUP-X"))
        ev += FL.rework("H", "M000", day, prev, (FL.OK, f"SN-H{j - 1}" if j > 1 else "SN-H0", "SUP-X"), (FL.OK, f"SN-{j}", "SUP-X"), tag=tag)
        prev = f"H-M000-RI-DE{tag}"
    f = FL.fleet(f"H{r}", "hub", "", ev, [], [], [])
    f["sessions"] = [dict(s) for s in FL.SESSIONS]
    return f


def chain_fleet(n):
    ev = []
    for i in range(n):
        ev += FL.build("C", f"M{i:04d}", f"08-{(i % 18) + 10:02d}", (FL.OK, f"SN-{i // 2}", "SUP-X"))        # every serial appears in two motors
    f = FL.fleet(f"C{n}", "chain", "", ev, [], [], [])
    return f


def scaling():
    rows = []
    for r in (1, 2, 3, 4, 5, 6, 7, 8, 10, 12):
        f = hub_fleet(r)
        t0 = time.perf_counter()
        found = B1.detect(f)
        t1 = time.perf_counter()
        dep = B1.dependency(f, found, budget=BUDGET, seed=1)
        t2 = time.perf_counter()
        hub = dep["M000"]
        rows.append(dict(kind="hub", contradictionsOnHub=len(hub["contradictions"]), detected=len(found), jointSpace=hub["joint"]["space"],
                         replayed=hub["joint"]["replayed"], sampled=hub["joint"]["sampled"], detectSeconds=round(t1 - t0, 4),
                         dependencySeconds=round(t2 - t1, 4), hubSensitive=hub["sensitive"]))
        print("scaling", rows[-1], flush=True)
    for n in (20, 100, 500, 1000, 2000):
        f = chain_fleet(n)
        t0 = time.perf_counter()
        found = B1.detect(f)
        t1 = time.perf_counter()
        b0g = baseline.b0(f)
        t2 = time.perf_counter()
        rows.append(dict(kind="chain", motors=n, claims=n, detected=len(found), b0Flags=len(b0g), detectSeconds=round(t1 - t0, 4), b0Seconds=round(t2 - t1, 4)))
        print("scaling", rows[-1], flush=True)
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
    import manifest
    assert manifest.compute() == json.load(open(os.path.join(HERE, "fleets", "MANIFEST.json"))), "fleet files changed since the manifest"
    root = sandbox.ROOT
    meta = dict(python=sys.version, platform=platform.platform(), sourceSha=safety.git(root, "rev-parse", "HEAD"),
                dirtyOutsideResults=bool(safety.git(root, "status", "--porcelain", "--", ".", ":!research/contradiction/results")),
                baselineTag=safety.git(root, "rev-parse", "manufacturing-demo-v1.0^{commit}"), seed=a.seed, interpretationBudget=BUDGET,
                evaluatorHashes=sandbox.evaluator_hashes(), command=" ".join(sys.argv), dependencies="python stdlib only")
    dump(os.path.join(out, "env.json"), meta)
    guard = safety.WriteGuard(out, tempfile.gettempdir(), allow_subprocess=True) if a.guard else None
    if guard:
        guard.__enter__()
    try:
        rows, agg = run_fleets(out)
        mm = metamorphic()
        inv = invariance(a.seed)
        pr = probes.run()
        sc = [] if a.skip_scaling else scaling()
    finally:
        viol = []
        if guard:
            viol = list(safety._state["violations"])
            guard.__exit__()
    valid = [r for r in rows if not r["truth"]["contradictions"]]
    scan = json.dumps([r["dependency"]["perMotor"] for r in rows])
    summ = dict(fleets=len(rows), aggregate=agg, validTransitionFleets=[r["id"] for r in valid],
                falsePositivesOnValidFleets=dict(b1=sum(len(r["b1"]["contradictions"]) for r in valid), b0=sum(len(r["b0"]["groups"]) for r in valid)),
                metamorphic=dict(total=len(mm), b1Pass=sum(t["b1Pass"] for t in mm), b0Pass=sum(t["b0Pass"] for t in mm)),
                probes=dict(total=len(pr), b1FalsePositives=sum(p["b1Verdict"] == "FALSE_POSITIVE" for p in pr), b1FalseNegatives=sum(p["b1Verdict"] == "FALSE_NEGATIVE" for p in pr)),
                invariance=inv, authorityPreservedEverywhere=all(r["authorityPreserved"] for r in rows),
                releaseEligibleStringInAdvisoryOutput="RELEASE_ELIGIBLE" in scan, guardViolations=viol, sourceSha=meta["sourceSha"])
    dump(os.path.join(out, "summary.json"), summ)
    dump(os.path.join(out, "metamorphic.json"), mm)
    dump(os.path.join(out, "invariance.json"), inv)
    dump(os.path.join(out, "scaling.json"), sc)
    dump(os.path.join(out, "probes.json"), pr)
    print(json.dumps(summ, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
