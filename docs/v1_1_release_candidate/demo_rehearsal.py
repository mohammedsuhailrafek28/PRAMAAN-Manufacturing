"""Scripted rehearsal of the 5-minute live demo (loopback 127.0.0.1, disposable synthetic data, no network, no notification delivery).

    python -B docs/v1_1_release_candidate/demo_rehearsal.py [OUT.json] [--port 4290]

It builds a throw-away ledger and root checkpoint (test-style bootstrap; same-host custody, operator asserted, NOT independent), starts the real server, and drives the
same HTTP calls and checkpoint_ops steps the live demo uses, asserting each outcome. Exit code 0 only if every step behaves as the runbook says.
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from application.anchors import export_anchor, publish_candidate  # noqa: E402
from application.service import Manufacturing  # noqa: E402

PY = sys.executable
PORT = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 4290
positional = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and sys.argv[i - 1] != "--port"]
OUT = Path(positional[0]) if positional else None
LOG = []


class Stack:
    def __init__(self, d):
        self.dir = Path(d); self.db = self.dir / "demo.sqlite"; self.custody = self.dir / "custody"; self.custody.mkdir()
        self.current = self.custody / "root.json"; self.previous = None; self.proc = None; self.base = f"http://127.0.0.1:{PORT}"
        app = Manufacturing(self.db); app.seed_demo()
        publish_candidate(self.current, export_anchor(app)); app.close()

    def start(self):
        args = [PY, "-B", "app.py", "--database", str(self.db), "--port", str(PORT), "--custody-dir", str(self.custody), "--trusted-anchor", str(self.current)]
        if self.previous:
            args += ["--previous-anchor", str(self.previous)]
        self.proc = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                urlopen(self.base + "/api/session", timeout=1).read(); return
            except Exception:
                time.sleep(0.2)
        raise SystemExit("server did not start")

    def stop(self):
        if self.proc:
            self.proc.terminate(); self.proc.wait(10); self.proc = None

    def call(self, path, body=None):
        if body is None:
            req = Request(self.base + path)
        else:
            token = json.load(urlopen(self.base + "/api/session"))["token"]
            req = Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json", "X-Pramaan-Token": token, "Origin": self.base})
        try:
            with urlopen(req) as r:
                return r.status, json.load(r)
        except HTTPError as e:
            return e.code, json.load(e)

    def ops(self, op, *extra):
        cmd = [PY, "-B", "-m", "application.checkpoint_ops", op, "--database", str(self.db), "--current", str(self.current), "--custody-dir", str(self.custody)]
        if self.previous:
            cmd += ["--current-previous", str(self.previous)]
        r = subprocess.run(cmd + list(extra), cwd=ROOT, capture_output=True, text=True)
        if r.returncode:
            raise SystemExit(f"checkpoint_ops {op} failed: {r.stderr[-400:]}")
        return json.loads(r.stdout)

    def cycle(self):
        """Operator checkpoint cycle: stop, propose, accept (typed digest, per-motor acknowledgements), restart on the successor."""
        self.stop()
        p = self.ops("propose")
        acks = [x for m in p["review"]["requiresAcknowledgement"] for x in ("--acknowledge", m)]
        a = self.ops("accept", "--candidate", p["candidate"], "--custodian", "Demo operator (synthetic)", "--confirm-sha256", p["candidateSha256"],
                     "--registry-digest", p["review"]["registry"]["digest"], *acks)
        self.previous, self.current = self.current, Path(a["accepted"])
        self.start()
        return dict(contained=p["review"].get("containedMotors", []), acknowledged=p["review"]["requiresAcknowledgement"], status=a["status"])


def step(title, ok, detail):
    LOG.append(dict(step=title, ok=bool(ok), detail=detail))
    print(("PASS " if ok else "FAIL ") + title + " :: " + json.dumps(detail, default=str)[:300])
    if not ok:
        raise SystemExit(f"rehearsal step failed: {title}")


def eligible(stack):
    snap = stack.call("/api/snapshot")[1]
    return snap["checkpoint"]["state"], {m: v["currentReleaseEligible"] for m, v in snap["eligibility"].items()}


def main():
    with tempfile.TemporaryDirectory(prefix="pramaan-demo-") as d:
        s = Stack(d); s.start()
        try:
            state, el = eligible(s)
            step("1 seeded demo starts ANCHORED_CURRENT", state == "ANCHORED_CURRENT", dict(state=state, eligible=el))
            for serial, lots in (("MTR-DEMO-1", ("BR-310", "BR-312")), ("MTR-DEMO-2", ("BR-204", "BR-312"))):
                s.call("/api/units", dict(serial=serial)); code, _ = s.call(f"/api/units/{serial}/assemble", dict(deLot=lots[0], ndeLot=lots[1]))
                step(f"2 capture {serial} (DE {lots[0]})", code == 200, dict(status=code))
            state, el = eligible(s)
            step("3 capture moved the ledger past the checkpoint: nothing is current", state == "ANCHORED_PREFIX_ONLY" and not any(el.values()), dict(state=state))
            code, body = s.call("/api/units/MTR-DEMO-1/ship", {})
            step("4 shipping a clean motor while the checkpoint is stale is REFUSED", (code, body.get("error")) == (409, "SHIPMENT_REFUSED"), dict(status=code, body=body))
            step("5 restricted recovery surface has no ship route", s.call("/api/recovery/ship", dict(motor="MTR-DEMO-1"))[0] in (404, 409), {})
            cyc = s.cycle()
            state, el = eligible(s)
            step("6 operator checkpoint cycle renews: DEMO-1 eligible, DEMO-2 (recalled DE lot) held",
                 state == "ANCHORED_CURRENT" and el.get("MTR-DEMO-1") is True and el.get("MTR-DEMO-2") is False, dict(state=state, eligible=el, cycle=cyc))
            code, body = s.call("/api/units/MTR-DEMO-2/ship", dict(currentReleaseEligible=True, force=True))
            step("7 shipping the recall-held motor is REFUSED even with client-supplied eligibility claims", (code, body.get("error")) == (409, "SHIPMENT_REFUSED"), dict(status=code))
            code, body = s.call("/api/units/MTR-DEMO-1/ship", {})
            step("8 shipping the current, eligible motor succeeds", code == 200 and body["snapshot"]["units"] and any(u["unitId"] == "MTR-DEMO-1" and u["shipment"] for u in body["snapshot"]["units"]), dict(status=code))
            state, el = eligible(s)
            step("9 the shipment itself requires the next checkpoint cycle (nothing is current)", state == "ANCHORED_PREFIX_ONLY" and not any(el.values()), dict(state=state))
            s.call("/api/units/MTR-26003/observe", dict(lot="ZZ-9"))
            cyc = s.cycle()
            state, el = eligible(s)
            step("10 unverified sighting on MTR-26003: that motor stays held, the others renew", state == "ANCHORED_CURRENT" and el.get("MTR-26003") is False and "MTR-26003" in cyc["contained"], dict(state=state, eligible=el, cycle=cyc))
        finally:
            s.stop()
    if OUT:
        OUT.write_text(json.dumps(dict(allPassed=all(x["ok"] for x in LOG), steps=LOG), indent=1))
    print("REHEARSAL PASSED" if all(x["ok"] for x in LOG) else "REHEARSAL FAILED")


if __name__ == "__main__":
    main()
