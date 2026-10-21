"""Reproducible synthetic application benchmark; never imported by decision code."""
import json
from pathlib import Path
import platform
import statistics
import tempfile
import time

from .service import Manufacturing, ROOT


def stats(values):
    ordered = sorted(values)
    return {"samples": len(values), "p50Ms": round(statistics.median(values), 3),
            "p95Ms": round(ordered[int((len(ordered)-1)*.95)], 3), "maxMs": round(max(values),3)}


def main():
    with tempfile.TemporaryDirectory(prefix="pramaan-app-measure-") as temp:
        app = Manufacturing(Path(temp)/"measure.sqlite")
        try:
            app.seed_demo()
            # Fixed truth stays in the reporting harness, outside the evaluator.
            truth = {"MTR-26001": True, "MTR-26002": False, "MTR-26003": False, "MTR-26004": False, "MTR-26005": True}
            snap = app.snapshot()
            scores = []
            for motor, unsafe in truth.items():
                d = next(iter(snap["decisions"][motor].values()))["current"]
                held = d["operationalAction"] == "RECALL_HOLD"
                scores.append(dict(motor=motor, syntheticUnsafe=unsafe, action=d["operationalAction"],
                                   falseRelease=unsafe and not held, unnecessaryHold=not unsafe and held))
            app.create_unit("MTR-MEASURE"); app.assemble("MTR-MEASURE", "BR-204", "BR-310")
            app.snapshot()
            capture, query, evaluate = [], [], []
            for _ in range(3):
                app.snapshot()
            for i in range(20):
                start = time.perf_counter()
                app.replace("MTR-MEASURE", "BR-312" if i%2 == 0 else "BR-310")
                app.snapshot()
                capture.append((time.perf_counter()-start)*1000)
                start = time.perf_counter()
                app.ledger.genealogy("MTR-MEASURE", app.ledger.watermark("MTR-MEASURE"))
                query.append((time.perf_counter()-start)*1000)
                start = time.perf_counter()
                app.ledger.decide("MTR-MEASURE", app.policy(), [app.ledger.watermark("MTR-MEASURE")])
                evaluate.append((time.perf_counter()-start)*1000)
            count = app.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            report = dict(platform=platform.platform(), python=platform.python_version(),
                methodology="File-backed SQLite WAL; deterministic 5-motor seed plus 1 serial motor; 3 warm-up fleet snapshots; 20 sequential six-capture replacements followed by verified full-fleet snapshot/evaluation; perf_counter; no concurrent clients or production SLA claim. Motor ledger grows each iteration; query/evaluation samples use that growing motor.",
                motors=6, finalEvents=count, measuredReplacementEvents=120,
                captureToFleetDecision=stats(capture), validatedGenealogy=stats(query), persistedEvaluation=stats(evaluate),
                safetyScope="Five seeded synthetic histories, current DE policy only. Truth externally authored; assumed late observation describes an actually affected item. Manufacturing genealogy claims do not certify physical truth.",
                safetyCases=scores, falseReleases=sum(x["falseRelease"] for x in scores), unnecessaryHolds=sum(x["unnecessaryHold"] for x in scores))
        finally:
            app.close()
    target=ROOT/"docs"/"phase3-application-measurements.json"
    target.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
