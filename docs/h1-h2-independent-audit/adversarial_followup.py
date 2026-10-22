"""Follow-up probes (disposable DBs). Usage: python -I adversarial_followup.py <repo_root> <out.json>"""
import copy, json, sys, threading, time
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError
ROOT = Path(sys.argv[1]).resolve(); OUT = Path(sys.argv[2])
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "integration"))
sys.path.insert(0, str(OUT.parent))
import adversarial_audit as A  # reuses World, attempt (script args identical)
from application.anchors import export_anchor, verify_anchor
from application.server import make_server

res = []
def rec(i, t, exp, obs, ok):
    res.append(dict(id=i, title=t, expected=exp, observed=obs, verdict=ok)); print(f"[{ok}] {i}: {t}\n   exp: {exp}\n   obs: {obs}", flush=True)

def keys(o, acc=None):
    acc = set() if acc is None else acc
    if isinstance(o, dict):
        for k, v in o.items(): acc.add(k); keys(v, acc)
    elif isinstance(o, list):
        for v in o: keys(v, acc)
    return acc

def serve(w):
    srv = make_server(w.path, 0, trusted_anchor=w.c0_file); th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
    return srv, th, f"http://127.0.0.1:{srv.server_port}"
def get(base, p):
    try:
        with urlopen(base + p, timeout=60) as r: return r.status, r.read().decode()
    except HTTPError as e: return e.code, e.read().decode()

# F-A: X4 benign check - are the 'CURRENT' mutants identical to the base?
w = A.World()
try:
    base = w.c0["body"]
    rec("F-A1", "tables with zero rows (dropping the last row is a no-op)", "rejections/decision_runs empty", {t: len(base["ledger"]["rows"][t]) for t in base["ledger"]["rows"]}, "info")
    rec("F-A2", "previousCheckpointHash None mutant identical to root", "True", base["previousCheckpointHash"] is None, "info")
finally: w.close()

# F-B: release-eligible decision while PREFIX_ONLY: which API surfaces carry a marker?
w = A.World()
try:
    w.app.observe("MTR-AAA1", "BR-204")         # unrelated motor; AAA2 stays excluded -> RELEASE_ELIGIBLE decision
    srv, th, base = serve(w)
    try:
        snap = json.loads(get(base, "/api/snapshot")[1])
        out = {"snapshot.state": snap["checkpoint"]["state"], "snapshot.elig": {k: v["currentReleaseEligible"] for k, v in snap["eligibility"].items()},
               "snapshot.A2.actions": [b["current"]["operationalAction"] for b in snap["decisions"]["MTR-AAA2"].values()]}
        for p in ("/api/motors/MTR-AAA2/decisions", "/api/lots/BR-310/investigation", "/api/lots/BR-312/investigation", "/api/motors", "/api/notifications"):
            st, b = get(base, p)
            try: j = json.loads(b); ks = keys(j)
            except Exception: ks = set()
            out[p] = dict(status=st, hasRELEASE_ELIGIBLE="RELEASE_ELIGIBLE" in b, hasStateKey=bool(ks & {"checkpoint", "eligibility", "currentReleaseEligible", "state"}), bytes=len(b))
        rec("F-B", "PREFIX_ONLY: API surfaces other than /api/snapshot with RELEASE_ELIGIBLE and no checkpoint/eligibility key", "every surface that reports RELEASE_ELIGIBLE carries state or withholds", json.dumps(out), "info")
    finally: srv.shutdown(); srv.server_close(); th.join()
finally: w.close()

# F-C: legacy row -> HTTP effect
w = A.World()
try:
    entry = copy.deepcopy(next(p for k, p in w.app.audit.verify() if k == "EVALUATION")); entry.pop("manifest")
    w.app.audit.append("EVALUATION", entry); w.app.db.commit(); w.app.close()
    try:
        srv, th, base = serve(w)
        try:
            st, b = get(base, "/api/snapshot"); rec("F-C", "legacy manifest-less EVALUATION row present, served over HTTP", "typed degrade (HISTORICAL) not generic 400", f"{st} {b[:200]}", "info")
        finally: srv.shutdown(); srv.server_close(); th.join()
    except Exception as e:
        rec("F-C", "legacy row present: server start", "?", f"{type(e).__name__}: {e}", "info")
finally: w.close()

# F-D: corruption of an UNBOUND table at runtime -> classification
for name, sql in [("app_clock-garbage", "UPDATE app_clock SET at='not-a-time'"), ("app_audit_head-count", "UPDATE app_audit_head SET count=999")]:
    w = A.World()
    try:
        srv, th, base = serve(w)
        try:
            a = get(base, "/api/snapshot")[0]
            import sqlite3
            c = sqlite3.connect(w.path)
            try: c.execute(sql); c.commit()
            except Exception as e: rec(f"F-D-{name}", "mutation", "-", str(e), "info"); c.close(); continue
            c.close()
            st, b = get(base, "/api/snapshot"); rec(f"F-D-{name}", "runtime corruption of unbound table; HTTP classification", "409/500 typed, never 400 INVALID_REQUEST", f"before={a} after={st} {b[:160]}", "info")
        finally: srv.shutdown(); srv.server_close(); th.join()
    finally: w.close()

# F-E: GET /api/snapshot writes (issuance on read) - journal count before/after a read against an extended archive
w = A.World()
try:
    w.app.observe("MTR-AAA2", "BR-204")
    n0 = w.app.db.execute("SELECT COUNT(*) FROM app_audit").fetchone()[0]
    srv, th, base = serve(w)
    try:
        get(base, "/api/snapshot"); get(base, "/api/snapshot")
    finally: srv.shutdown(); srv.server_close(); th.join()
    n1 = A.sqlite3.connect(w.path).execute("SELECT COUNT(*) FROM app_audit").fetchone()[0]
    rec("F-E", "GET /api/snapshot appends journal entries (write-on-read) against an evidence-extended archive", "read-only GET preferred", f"journal {n0} -> {n1}", "info")
finally: w.close()

OUT.write_text(json.dumps(res, indent=2))
