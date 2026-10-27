"""Benchmark of the hybrid proof against the 864393d reader, and against that reader with only the mmap setting, on the same synthetic ledger.

Fixture: performance.benchmark.build (compact synthetic aggregator motors, NOT a real factory distribution). Truth is fixture intent; nothing here is a decision.
Measured per size: normal queries, cold rebuild, harmless-write recovery, evidence-change rejection, incremental rebuild, and queries under concurrent
evidence and harmless writers.

Usage (repository root, PYTHONPATH=.): python -B -m performance.benchmark_hybrid --sizes 100 1000 10000 --baseline OLD_impact_query.py --out DIR [--keep DIR]
"""
import argparse
import calendar
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import shutil
import sqlite3
import tempfile
import threading
import time

from application.service import Manufacturing, encode_document
from pramaan_integration import Ledger
from performance.benchmark import build
from performance.impact_query import ImpactQuery, ImpactUnavailable

LOTS = ("BR-204", "BR-310", "BR-2O4", "NSB-204")


def stats(samples):
    s = sorted(samples)

    def q(p):
        k = (len(s) - 1) * p; lo = math.floor(k); hi = math.ceil(k)
        return s[lo] + (s[hi] - s[lo]) * (k - lo)
    return dict(n=len(s), p50Ms=q(.5), p95Ms=q(.95), minMs=s[0], maxMs=s[-1])


def ms(fn):
    start = time.perf_counter(); result = fn()
    return (time.perf_counter() - start) * 1000, result


def load_legacy(path):
    spec = importlib.util.spec_from_file_location("legacy_impact_query", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


class Appender:
    """Appends a further look-alike sighting to a benchmark motor through the unchanged Ledger.capture (the same path every event takes)."""
    def __init__(self, path):
        self.path = path
        self.ledger = Ledger(path)
        self.count = 0

    def close(self):
        self.ledger.close()

    def append(self, motor):
        db = self.ledger.db
        rows = db.execute("SELECT source,max(seq) FROM events WHERE motor=? GROUP BY source", (motor,)).fetchall()
        wm = {r[0]: r[1] for r in rows}
        case, _ = self.ledger.snapshot(motor, wm)
        events = case["events"]
        last = [e for e in events if e["eventType"] == "SLOT_STATE_VERIFIED"][-1]
        e = copy.deepcopy(last)
        self.count += 1
        source = e["sourceId"]
        e["eventId"] = f"{last['eventId']}-bench{self.count}-{time.time_ns()}"
        e["sourceSeq"] = wm[source] + 1
        newest = max(x["recordedAt"] for x in events if x["sourceId"] == source)
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(calendar.timegm(time.strptime(newest, "%Y-%m-%dT%H:%M:%SZ")) + 30 + self.count))
        e["recordedAt"] = stamp
        e["evidenceRefs"] = [f"bench-append:{motor}:{self.count}"]
        raw = json.dumps(encode_document([e], "2026-12-31T23:59:59Z"), separators=(",", ":")).encode()
        self.ledger.capture(motor, raw, producer_source=source, expected_sha256=hashlib.sha256(raw).hexdigest())


def comparable(r):
    return {k: v for k, v in r.items() if k not in ("contentDigest", "evidenceGeneration", "integrity")}


def warm(reader, reps):
    samples, json_samples = [], []
    for _ in range(reps):
        samples.append(ms(lambda: reader.query("BR-204"))[0])
    first = ms(lambda: reader.query_json("BR-204"))[0]
    for _ in range(reps):
        json_samples.append(ms(lambda: reader.query_json("BR-204"))[0])
    return dict(query=stats(samples), readyJson=stats(json_samples), firstReadyJsonMs=first)


def mmap_baseline(module, path):
    """The 864393d reader with exactly the Codex change (connection-local mmap) and nothing else."""
    reader = module.ImpactQuery(path)
    reader.db.execute("PRAGMA mmap_size=1073741824")
    return reader


def refused(reader):
    try:
        reader.query("BR-204")
        return None
    except ImpactUnavailable as exc:
        return exc.code


def concurrent(path, truth, seconds, evidence_hz):
    """An evidence writer (look-alike sightings) and a harmless writer (clock ticks, application opens) run while the reader queries and rebuilds when told to."""
    motors = [m for m, t in truth.items() if t["scenario"] == "sighting"]
    reader = ImpactQuery(path)
    reader.rebuild()
    stop = threading.Event(); evidence, harmless, errors = [], [], []

    def evidence_writer():
        a = Appender(path)
        try:
            i = 0
            while not stop.is_set():
                a.append(motors[i % len(motors)]); i += 1; evidence.append(1)
                stop.wait(1.0 / evidence_hz)
        except Exception as exc:
            errors.append(repr(exc))
        finally:
            a.close()

    def harmless_writer():
        try:
            while not stop.is_set():
                app = Manufacturing(path); app.tick(); app.close(); harmless.append(1)
                stop.wait(0.5)
        except Exception as exc:
            errors.append(repr(exc))
    threads = [threading.Thread(target=evidence_writer), threading.Thread(target=harmless_writer)]
    for t in threads:
        t.start()
    served, refusals, rebuilds, rebuild_ms, counts, other, query_ms = 0, 0, 0, [], [], [], []
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        try:
            d, r = ms(lambda: reader.query("BR-204")); served += 1; counts.append(r["eventCount"]); query_ms.append(d)
        except ImpactUnavailable as exc:
            refusals += 1
            if exc.code in ("EVIDENCE_CHANGED_REBUILD_REQUIRED", "VERIFIED_INDEX_REQUIRED"):
                try:
                    d, info = ms(reader.rebuild); rebuilds += 1; rebuild_ms.append(d)
                except ImpactUnavailable as exc2:
                    other.append(exc2.code)
            else:
                other.append(exc.code)
    stop.set()
    for t in threads:
        t.join(120)
    try:
        final = reader.query("BR-204")
    except ImpactUnavailable:
        reader.rebuild(); final = reader.query("BR-204")
    con = sqlite3.connect(str(path)); events = con.execute("SELECT count(*) FROM events").fetchone()[0]; con.close()
    out = dict(seconds=seconds, evidenceWriterHz=evidence_hz, evidenceEventsAppended=len(evidence), harmlessWrites=len(harmless), queriesServed=served,
               queriesRefused=refusals, rebuilds=rebuilds, rebuildMs=stats(rebuild_ms) if rebuild_ms else None, servedQueryMs=stats(query_ms) if query_ms else None,
               reAnchors=reader.stats["reAnchors"], otherErrors=sorted(set(other)), writerErrors=errors,
               servedEventCountsNonDecreasing=all(a <= b for a, b in zip(counts, counts[1:])), everyServedCountWithinLedger=all(c <= events for c in counts),
               finalReaderEventsEqualLedger=final["eventCount"] == events)
    reader.close()
    return out


def measure(n, reps, out, keep, baseline_path, concurrent_seconds):
    with tempfile.TemporaryDirectory(prefix="pramaan-hybrid-bench-", ignore_cleanup_errors=True) as tmp:
        base = Path(keep) / f"n{n}" / "ledger.sqlite" if keep else Path(tmp) / "fixture" / "ledger.sqlite"
        base.parent.mkdir(parents=True, exist_ok=True)
        if base.exists() and keep:
            truth = json.loads(base.with_suffix(".truth.json").read_text())
        else:
            truth, _ = build(base, n)
            if keep:
                base.with_suffix(".truth.json").write_text(json.dumps(truth))
        path = Path(tmp) / "work.sqlite"
        shutil.copy(base, path)
        res = dict(motors=n, ledgerMB=path.stat().st_size / 1e6,
                   hardware=dict(python=platform.python_version(), platform=platform.platform(), sqlite=sqlite3.sqlite_version, processor=platform.processor()))
        legacy = load_legacy(baseline_path)
        sightings = [m for m, t in truth.items() if t["scenario"] == "sighting"]
        print(f"[{n}] fixture ready, {res['ledgerMB']:.1f} MB", flush=True)

        # ---- hybrid: cold, no-op, normal queries
        hy = ImpactQuery(path)
        cold, info = ms(hy.rebuild)
        res["hybrid"] = dict(coldRebuildMs=cold, coldInfo=info, noopRebuildMs=ms(hy.rebuild)[0], mmapBytes=hy._mmap_bytes)
        res["hybrid"]["normal"] = warm(hy, reps)
        answers = {lot: hy.query(lot) for lot in LOTS}
        h = res["hybrid"]["normal"]["readyJson"]
        print(f"[{n}] hybrid cold {cold:.0f} ms, normal json p50/p95 {h['p50Ms']:.1f}/{h['p95Ms']:.1f}", flush=True)

        # ---- baselines on the same ledger
        for name, make in (("baseline864393d", lambda: legacy.ImpactQuery(path)), ("baselinePlusMmap", lambda: mmap_baseline(legacy, path))):
            r = make()
            c, _ = ms(r.rebuild)
            w = warm(r, reps)
            res[name] = dict(coldRebuildMs=c, normal=w, equalToHybridAnswers=all(comparable(r.query(lot)) == comparable(answers[lot]) for lot in LOTS))
            r.close()
            j = w["readyJson"]
            print(f"[{n}] {name} cold {c:.0f} ms, normal json p50/p95 {j['p50Ms']:.1f}/{j['p95Ms']:.1f}, equal={res[name]['equalToHybridAnswers']}", flush=True)

        # ---- harmless-write recovery (hybrid) versus the baseline (which must rebuild)
        rec = {}
        for label, action in (("openClose", lambda: Manufacturing(path).close()),
                              ("clockTicks", lambda: (lambda a: (a.tick(), a.tick(), a.close()))(Manufacturing(path))),
                              ("announce", lambda: (lambda a: (a.announce("BR-204", ["DE"]), a.close()))(Manufacturing(path)))):
            action()
            first, r1 = ms(lambda: hy.query("BR-204"))
            second, _ = ms(lambda: hy.query("BR-204"))
            rec[label] = dict(firstQueryAfterWriteMs=first, nextQueryMs=second, reAnchorsSoFar=hy.stats["reAnchors"], served=True,
                              sameAnswerAsBefore=comparable(r1) == comparable(answers["BR-204"]))
        rb = legacy.ImpactQuery(path)
        rb.rebuild()
        Manufacturing(path).close()
        try:
            rb.query("BR-204")
            rec["baselineAfterOpenClose"] = "SERVED"
        except legacy.ImpactUnavailable as exc:
            rec["baselineAfterOpenClose"] = exc.code
        rb.close()
        res["harmlessWriteRecovery"] = rec
        print("[%d] recovery %s" % (n, json.dumps({k: (round(v["firstQueryAfterWriteMs"]), round(v["nextQueryMs"])) for k, v in rec.items() if isinstance(v, dict)})), flush=True)

        # ---- evidence change: rejection and incremental rebuild (hybrid), rejection and rebuild (baseline with mmap)
        a = Appender(path); a.append(sightings[0]); a.close()
        rejection_ms, code = ms(lambda: refused(hy))
        inc, infoi = ms(hy.rebuild)
        res["evidenceChange"] = dict(rejectionMs=rejection_ms, refusal=code, staleServed=code is None, incrementalRebuildMs=inc, incrementalInfo=infoi,
                                     normalAfter=warm(hy, 5)["readyJson"])
        b = mmap_baseline(legacy, path)
        b.rebuild()
        a = Appender(path); a.append(sightings[1]); a.close()
        try:
            b.query("BR-204")
            res["evidenceChange"]["baselineRejection"] = "SERVED"
        except legacy.ImpactUnavailable as exc:
            res["evidenceChange"]["baselineRejection"] = exc.code
        res["evidenceChange"]["baselineRebuildAfterOneEventMs"] = ms(b.rebuild)[0]
        b.close()
        print("[%d] evidence: rejection %.0f ms (%s), incremental %.0f ms verified=%d, baseline rebuild %.0f ms" % (
            n, rejection_ms, code, inc, infoi["motorsVerified"], res["evidenceChange"]["baselineRebuildAfterOneEventMs"]), flush=True)
        hy.close()

        if concurrent_seconds:
            res["concurrentWrites"] = concurrent(path, truth, concurrent_seconds, 4 if n <= 1000 else 1)
            print("[%d] concurrent %s" % (n, json.dumps(res["concurrentWrites"])), flush=True)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"hybrid-n{n}.json").write_text(json.dumps(res, indent=2), encoding="utf8")
        return res


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sizes", type=int, nargs="+", default=[100, 1000, 10000])
    p.add_argument("--reps", type=int, default=21)
    p.add_argument("--out", type=Path, default=Path("docs/ps10-performance/benchmarks"))
    p.add_argument("--keep", type=Path, default=None, help="directory holding reusable fixture ledgers")
    p.add_argument("--baseline", type=Path, required=True, help="path to the 864393d impact_query.py")
    p.add_argument("--concurrent-seconds", type=int, default=20)
    a = p.parse_args()
    for n in a.sizes:
        measure(n, a.reps, a.out, a.keep, a.baseline, a.concurrent_seconds)


if __name__ == "__main__":
    main()
