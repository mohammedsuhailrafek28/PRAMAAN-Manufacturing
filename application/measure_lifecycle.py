"""Capture-to-visible-history latency for PS10 lifecycle events (synthetic, loopback, disposable database).
Run: python -B -m application.measure_lifecycle [--fleet 5 --fleet 50 --events 40] [--out file.json]

Two clocks are reported per fleet size, never mixed:
  inProcess  capture call -> the event appears in a freshly derived lifecycle view (Manufacturing.snapshot + lifecycle.view)
  http       POST /api/units/<m>/machine (anchored server; the response already carries the new snapshot) -> GET /api/motors/<m>/lifecycle shows the event
Visibility is verified by looking for the event id, not assumed from the status code.
"""
import argparse
import json
import statistics
import tempfile
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from . import lifecycle
from . import server as server_mod
from .anchors import export_anchor, publish_candidate
from .service import Manufacturing


def pct(v, q):
    v = sorted(v); k = (len(v) - 1) * q; lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def stats(ms):
    return dict(n=len(ms), p50Ms=round(pct(ms, .5), 2), p95Ms=round(pct(ms, .95), 2), maxMs=round(max(ms), 2))


def world(path, fleet):
    app = Manufacturing(path)
    for i in range(fleet):
        m = f"MTR-95{i:03d}"
        app.create_unit(m, lifecycle=True)
        s = app.machine(m, "SHAFT", f"SHAFT-{i}", "TURNING", "LATHE-02", "R10", "DWG-SH-100 rev C")
        app.inspect_quality(m, "DIMENSIONAL", [s["eventId"]], "QP-SHAFT-7", "PASS", ["DIMENSIONAL"])
        app.assemble(m, "BR-310", "BR-312"); app.record_historical_shipment_fixture(m)
    app.announce("BR-204", ["DE"]); app.snapshot()
    return app


def in_process(fleet, events):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        app = world(Path(d) / "m.sqlite", fleet)
        capture, visible = [], []
        target = "MTR-95000"
        for n in range(events):
            t0 = time.perf_counter()
            e = app.machine(target, "HOUSING", f"HOUSING-{n}", "BORING", "BORE-01", f"R{n}", "DWG-HS-200")
            t1 = time.perf_counter()
            unit = next(u for u in app.snapshot()["units"] if u["unitId"] == target)
            seen = any(r["eventId"] == e["eventId"] for r in lifecycle.view(unit["events"])["chronology"])
            t2 = time.perf_counter()
            assert seen, "captured event not visible in the derived lifecycle view"
            capture.append((t1 - t0) * 1000); visible.append((t2 - t0) * 1000)
        app.close()
    return dict(captureOnly=stats(capture), captureToVisibleInLifecycleView=stats(visible))


def http(fleet, events):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        db, cp = Path(d) / "m.sqlite", Path(d) / "c0.json"
        app = world(db, fleet)
        publish_candidate(cp, export_anchor(app)); app.close()
        srv = server_mod.make_server(db, 0, trusted_anchor=cp)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_port}"
        token = json.load(urlopen(base + "/api/session"))["token"]
        post_ms, read_ms, total_ms, errors = [], [], [], {}
        try:
            for n in range(events):
                body = json.dumps(dict(componentType="HOUSING", componentId=f"HOUSING-{n}", operation="BORING", machineId="BORE-01", routingStepId=f"R{n}", drawingRef="DWG-HS-200")).encode()
                t0 = time.perf_counter()
                try:
                    with urlopen(Request(base + "/api/units/MTR-95000/machine", body, {"Content-Type": "application/json", "X-Pramaan-Token": token})) as r:
                        r.read()
                except HTTPError as exc:
                    code = f"{exc.code}:{json.load(exc).get('error')}"
                    errors[code] = errors.get(code, 0) + 1; continue
                t1 = time.perf_counter()
                with urlopen(base + "/api/motors/MTR-95000/lifecycle") as r:
                    life = json.load(r)
                t2 = time.perf_counter()
                assert any(row["eventType"] == "MACHINING_RECORDED" and row.get("component", {}).get("id") == f"HOUSING-{n}" for row in life["chronology"]), "event not visible over HTTP"
                post_ms.append((t1 - t0) * 1000); read_ms.append((t2 - t1) * 1000); total_ms.append((t2 - t0) * 1000)
        finally:
            srv.shutdown(); srv.server_close()
        check = Manufacturing(db)
        landed = sum(1 for e in check.events("MTR-95000") if e["eventType"] == "MACHINING_RECORDED" and e["payload"]["componentType"] == "HOUSING")
        check.close()
    return dict(commandsSent=events, eventsActuallyInLedger=landed, postCommand=stats(post_ms) if post_ms else None, readLifecycle=stats(read_ms) if read_ms else None,
                captureToVisibleOverHttp=stats(total_ms) if total_ms else None, errors=errors)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--fleet", type=int, action="append"); ap.add_argument("--events", type=int, default=40); ap.add_argument("--out")
    a = ap.parse_args()
    out = {}
    for fleet in a.fleet or [5, 50]:
        out[f"fleet{fleet}"] = dict(motors=fleet, inProcess=in_process(fleet, a.events), http=http(fleet, a.events))
    out["note"] = "Loopback, single process, synthetic. Each HTTP read derives a full verified snapshot; cost grows with fleet size (see the core-performance audit)."
    text = json.dumps(out, indent=1)
    print(text)
    if a.out:
        Path(a.out).write_text(text)


if __name__ == "__main__":
    main()
