"""Reproduce tests, demo, independent synthetic safety counts and latency results.

Ground truth/expected outcomes appear ONLY in this reporting harness and tests.
Production adapter/ledger/engine never imports this module or authored scenarios.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time

from pramaan_integration import engine_bridge
from pramaan_integration.profile import encode_document
from integration_tests.scenarios import Scenario, populated
from pramaan_integration import Ledger

ROOT = Path(__file__).resolve().parent.parent
REPORTS = Path(__file__).with_name("reports")


def save(name, data):
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def command(command, cwd, filename):
    start = time.perf_counter()
    proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=180)
    text = proc.stdout + proc.stderr
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / filename).write_text(text, encoding="utf-8")
    return dict(command=command, exitCode=proc.returncode, elapsedSeconds=round(time.perf_counter()-start, 3), output=filename)


# Source identity is pinned by git tree object id, which exists in every clone of this repository
# (unlike the originating commits 1620ed3 / bc68dc0, which live only in the research repository).
# Provenance: recall-engine == tree of 1620ed3a8c78d7ea41063107666d9482fd93dff9 (engine v3, 127 tests);
# experiments/foundation == tree of bc68dc0ca54f4e35b7e14c6ad09f7af28ab3b00c (21 checks). See docs/PHASE3_SOURCE_PROVENANCE.md.
PINNED_TREES = {"recall-engine": "22d205d5b2d42e609e8b872c564c7283ffd758e9",
                "experiments/foundation": "fe6f39294e10b077785ed3afb27806af51acc50c"}


def _git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def source_tree_identity(path, pinned):
    """Committed tree id must equal the pin AND the working tree must have no edits or extra files under it."""
    committed = _git("rev-parse", f"HEAD:{path}")
    diff = _git("diff", "HEAD", "--exit-code", "--quiet", "--", path)
    untracked = _git("ls-files", "--others", "--exclude-standard", "--", path)
    clean = diff.returncode == 0 and untracked.returncode == 0 and not untracked.stdout.strip()
    tree = committed.stdout.strip() if committed.returncode == 0 else None
    return dict(path=path, pinnedTree=pinned, committedTree=tree, workingTreeClean=clean, matches=tree == pinned and clean)


def verify_baselines(gs1):
    engine = command([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-v"], ROOT / "recall-engine", "engine-tests.txt")
    foundation = command([sys.executable, "experiments/foundation/interop.py", "--gs1-checkout", str(gs1.resolve()),
                          "--output", str((REPORTS / "foundation-results.json").resolve())], ROOT, "foundation-tests.txt")
    integration = command([sys.executable, "-m", "unittest", "discover", "-s", "integration_tests", "-t", ".", "-v"], ROOT / "integration", "integration-tests.txt")
    unchanged = source_tree_identity("recall-engine", PINNED_TREES["recall-engine"])
    research = source_tree_identity("experiments/foundation", PINNED_TREES["experiments/foundation"])
    result = dict(engine=engine, foundation=foundation, integration=integration,
                  engineTreeUnmodified=unchanged["matches"], foundationTreeUnmodified=research["matches"],
                  sourceTrees=dict(engine=unchanged, foundation=research))
    save("test-results.json", result)
    if not all(x["exitCode"] == 0 for x in (engine, foundation, integration)) or not result["engineTreeUnmodified"] or not result["foundationTreeUnmodified"]:
        raise AssertionError("Baseline or integration gate failed; see reports")
    return result


def demo():
    scenario = Scenario("M-DEMO")
    with tempfile.TemporaryDirectory(prefix="pramaan-phase2-demo-") as directory:
        path = Path(directory) / "ledger.sqlite"
        ledger = Ledger(path); scenario.provision(ledger)
        scenario.ingest(ledger, scenario.events[:4]); build_wm = ledger.watermark(scenario.motor)
        before = ledger.genealogy(scenario.motor, build_wm)
        scenario.ingest(ledger, scenario.events[4:]); final_wm = ledger.watermark(scenario.motor)
        after = ledger.genealogy(scenario.motor, final_wm)
        decisions = ledger.decide(scenario.motor, scenario.policy, [build_wm, final_wm])
        replayed = [ledger.replay(scenario.motor, scenario.policy, b) for b in decisions]
        native, _ = ledger.snapshot(scenario.motor, final_wm)
        rows = ledger.db.execute("SELECT hash,received FROM captures ORDER BY rowid").fetchall()
        result = dict(policy=scenario.policy, coverage=scenario.coverage,
                      genealogyBeforeReplacement=before, genealogyAfterReplacement=after,
                      decisions=decisions, replayFindings=[d["evidenceFinding"] for d in replayed],
                      nativeEngineInput=native,
                      captures=[dict(documentSha256=r["hash"], localRepositoryReceivedAt=r["received"]) for r in rows],
                      epcisExample=encode_document([scenario.events[1]], "2026-10-21T10:00:00Z"))
        ledger.close()
        reopened = Ledger(path)
        result["survivesDatabaseReopen"] = reopened.decide(scenario.motor, scenario.policy, [build_wm, final_wm]) == decisions
        reopened.close()
    save("demo.json", result)
    return result


def external_conformance(gs1):
    """External standards artifacts remain outside the repository/distribution."""
    from jsonschema import Draft7Validator, FormatChecker
    from pyld import jsonld
    from pramaan_integration.profile import CONTEXT
    schema_bytes = (gs1 / "EPCIS-JSON-Schema.json").read_bytes()
    context_bytes = (gs1 / "epcis-context.jsonld").read_bytes()
    validator = Draft7Validator(json.loads(schema_bytes), format_checker=FormatChecker())
    def loader(url, options=None):
        if url != CONTEXT[0]:
            raise ValueError("Unexpected remote context")
        return dict(contextUrl=None, documentUrl=url, document=json.loads(context_bytes))
    scenarios = [Scenario("M-CONFORM"), Scenario("M-CONFORM-SAME", same_lot=True)]
    scenarios[0].verify(trusted=False, lot="LOT-AFFECTED"); scenarios[0].verify(); scenarios[0].correction()
    documents, events = 0, 0
    for scenario in scenarios:
        doc = encode_document(scenario.events, "2026-10-21T10:00:00Z")
        validator.validate(doc)
        expanded = jsonld.expand(doc, options={"documentLoader": loader})
        compacted = jsonld.compact(expanded, CONTEXT, options={"documentLoader": loader})
        if [e["trace"] for e in compacted["epcisBody"]["eventList"]] != [e["trace"] for e in doc["epcisBody"]["eventList"]]:
            raise AssertionError("Profile loses trace metadata under JSON-LD expansion")
        documents += 1; events += len(scenario.events)
    result = dict(documents=documents, events=events, schemaPassed=True, jsonldTraceRoundtripPassed=True,
                  schemaSha256=hashlib.sha256(schema_bytes).hexdigest(), contextSha256=hashlib.sha256(context_bytes).hexdigest(),
                  scope="Two complete generated documents; no full repository runtime or complete EPCIS certification")
    save("external-conformance.json", result)
    return result


def safety():
    """Truth labels are authored independently of observed engine outcomes."""
    matrix = []

    def add(name, scenario, physically_unsafe, expected):
        ledger = populated(scenario)
        wm = ledger.watermark(scenario.motor)
        bundle = ledger.decide(scenario.motor, scenario.policy, [wm])[0]
        d = bundle["decision"]
        # Behavioral agreement is separate from truth-based release/hold counts.
        matrix.append(dict(scenario=name, syntheticUnsafe=physically_unsafe, expectedFinding=expected,
                           actualFinding=d["evidenceFinding"], operationalAction=d["operationalAction"],
                           behaviorMatches=d["evidenceFinding"] == expected,
                           falseRelease=physically_unsafe and d["operationalAction"] == "RELEASE_ELIGIBLE",
                           unnecessaryHold=not physically_unsafe and d["operationalAction"] == "RECALL_HOLD",
                           reasonCodes=d["reasonCodes"], supportingEventIds=d["evidenceEventIds"]))
        ledger.close()

    add("clean replacement", Scenario("M-CLEAN"), False, "EXCLUDED_WITH_EVIDENCE")
    add("missing baseline, physically safe", Scenario("M-NO-BASE", baseline=False), False, "UNRESOLVED")
    s = Scenario("M-DOUBLE"); s.event("COMPONENT_INSTALLED", "REWORK", "2026-09-01T08:04:00Z", s.part("DE", "LOT-AFFECTED"), wo="REWORK")
    add("double installation", s, True, "UNRESOLVED")
    add("same-lot wrong-slot physical removal", Scenario("M-WRONG", same_lot=True), True, "UNRESOLVED")
    add("same-lot correct physical removal, indistinguishable records", Scenario("M-CORRECT", same_lot=True), False, "UNRESOLVED")
    s = Scenario("M-VERIFIED", same_lot=True); s.verify()
    add("independently verified slot", s, False, "EXCLUDED_WITH_EVIDENCE")
    s = Scenario("M-DERIVED", same_lot=True); s.verify(derivedFromEventIds=[s.replacement["eventId"]])
    add("derived verification cannot settle wrong-slot risk", s, True, "UNRESOLVED")
    s = Scenario("M-OBS"); s.verify(trusted=False, lot="LOT-AFFECTED", at="2026-09-01T08:30:00Z")
    add("true affected-bearing untrusted observation", s, True, "UNRESOLVED")
    s = Scenario("M-FALSE-ALARM"); s.verify(trusted=False, lot="LOT-AFFECTED", at="2026-09-01T08:30:00Z")
    add("false affected-bearing untrusted observation", s, False, "UNRESOLVED")
    s = Scenario("M-RESOLVED"); s.verify(trusted=False, lot="LOT-AFFECTED", at="2026-09-01T08:30:00Z"); s.verify()
    add("observation resolved by later independent verification", s, False, "EXCLUDED_WITH_EVIDENCE")
    s = Scenario("M-GAP"); s.gap()
    add("unobserved affected component during capture gap", s, True, "UNRESOLVED")
    s = Scenario("M-CORRECTION"); s.correction()
    add("late correction reveals affected replacement", s, True, "UNRESOLVED")
    result = dict(scope="12 authored P1 synthetic histories; not factory evidence; truth not available to decision code",
                  scenarios=matrix, total=len(matrix), behaviorAgreements=sum(r["behaviorMatches"] for r in matrix),
                  unsafeScenarios=sum(r["syntheticUnsafe"] for r in matrix),
                  safeScenarios=sum(not r["syntheticUnsafe"] for r in matrix),
                  falseReleases=sum(r["falseRelease"] for r in matrix), unnecessaryHolds=sum(r["unnecessaryHold"] for r in matrix))
    save("safety.json", result)
    if result["behaviorAgreements"] != result["total"] or result["falseReleases"]:
        raise AssertionError("Integration safety/behavior gate failed")
    return result


def percentile(values, p):
    ordered = sorted(values)
    return ordered[min(len(ordered)-1, int((len(ordered)-1)*p))]


def performance(motors=100, samples=300):
    """Warm single-process file SQLite; no concurrent writes or cold-cache claim."""
    with tempfile.TemporaryDirectory(prefix="pramaan-phase2-bench-") as directory:
        ledger = Ledger(Path(directory) / "bench.sqlite")
        data = [Scenario(f"M-BENCH-{n:04}") for n in range(motors)]
        start = time.perf_counter()
        for scenario in data:
            scenario.provision(ledger); scenario.ingest(ledger)
        ingestion = time.perf_counter() - start
        workloads = [(s, ledger.watermark(s.motor)) for s in data]
        cached = [ledger.snapshot(s.motor, wm)[0] for s, wm in workloads]
        timings = {"genealogyWithValidation": [], "decisionWithValidation": [], "engineOnlyCachedInput": []}
        counts = Counter()
        for n in range(20 + samples):
            index = n % motors; scenario, wm = workloads[index]
            start = time.perf_counter_ns(); query = ledger.genealogy(scenario.motor, wm); a = time.perf_counter_ns()
            bundle = ledger.decide(scenario.motor, scenario.policy, [wm])[0]; b = time.perf_counter_ns()
            engine_bridge.pramaan_recall.evaluate(cached[index], scenario.policy, scenario.coverage, wm, engine_bridge.Config.v3()); c = time.perf_counter_ns()
            if n >= 20:
                for name, duration in zip(timings, (a-start, b-a, c-b)):
                    timings[name].append(duration / 1_000_000)
                counts[bundle["decision"]["evidenceFinding"]] += 1
            if len(query["relationships"]) != 4:
                raise AssertionError("Unexpected benchmark query cardinality")
        metrics = {name: dict(unit="ms", p50=percentile(v,.5), p95=percentile(v,.95), p99=percentile(v,.99), mean=statistics.mean(v), samples=len(v)) for name, v in timings.items()}
        ledger.close()
    result = dict(python=platform.python_version(), platform=platform.platform(), sqlite=__import__("sqlite3").sqlite_version,
                  dataset=dict(seed="deterministic motor index 0..99; no randomness", motors=motors, eventsPerMotor=8,
                               events=motors*8, captures=motors*8, relationshipsPerMotor=4),
                  methodology="20 warm-up iterations, then round-robin over 100 motors; sequential genealogy, decision, cached-engine; perf_counter_ns; file-backed SQLite WAL; schema/hash/original-byte validation included in first two; no concurrent writers; no cold-cache or production claim",
                  syntheticIngestionSeconds=ingestion, latency=metrics, decisionCounts=dict(counts))
    save("performance.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gs1-checkout", required=True, type=Path)
    args = parser.parse_args()
    tests = verify_baselines(args.gs1_checkout)
    conformance = external_conformance(args.gs1_checkout)
    demonstration = demo()
    behavior = safety()
    benchmark = performance()
    print(json.dumps(dict(tests=tests, conformance=conformance, demoFindings=[b["decision"]["evidenceFinding"] for b in demonstration["decisions"]],
                          safety={k:v for k,v in behavior.items() if k != "scenarios"}, latency=benchmark["latency"]), indent=2))
