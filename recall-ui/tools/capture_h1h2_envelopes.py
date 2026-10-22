"""Capture REAL /api/snapshot envelopes from the H1/H2 backend (f9dcf56) for frontend contract tests.

Read-only use of the backend: it is imported from --backend (a separate checkout) and is neither
vendored, merged nor modified. Everything is synthetic and runs on a disposable database.

    python tools/capture_h1h2_envelopes.py --backend <path-to-h1h2-checkout> --out tests/fixtures/h1h2
"""
import argparse, json, sqlite3, sys, tempfile, threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

ap = argparse.ArgumentParser(); ap.add_argument("--backend", required=True, type=Path); ap.add_argument("--out", required=True, type=Path)
args = ap.parse_args()
sys.path.insert(0, str(args.backend.resolve())); sys.path.insert(0, str((args.backend / "integration").resolve()))
from application.service import Manufacturing  # noqa: E402
from application.anchors import export_anchor  # noqa: E402
from application.server import make_server  # noqa: E402


def serve(db, anchor):
    srv = make_server(db, 0, trusted_anchor=anchor) if anchor else make_server(db, 0)
    th = threading.Thread(target=srv.serve_forever, daemon=True); th.start()
    return srv, th, f"http://127.0.0.1:{srv.server_port}"


def get(base):
    try:
        with urlopen(base + "/api/snapshot", timeout=60) as r: return r.status, json.load(r)
    except HTTPError as e: return e.code, json.loads(e.read().decode())


def stop(srv, th): srv.shutdown(); srv.server_close(); th.join()


args.out.mkdir(parents=True, exist_ok=True)
saved = {}
with tempfile.TemporaryDirectory() as d:
    db = Path(d) / "l.sqlite"; anchor = Path(d) / "a.json"
    app = Manufacturing(db); app.seed_demo(); anchor.write_text(json.dumps(export_anchor(app))); app.close()
    srv, th, base = serve(db, anchor)
    try:
        saved["current"] = get(base)
        w = Manufacturing(db); w.observe("MTR-26001", "BR-204"); w.close()      # legitimate external capture
        saved["prefix_only"] = get(base)
        conn = sqlite3.connect(db); conn.execute("UPDATE app_audit_head SET archive_id='tampered'"); conn.commit(); conn.close()
        saved["anchor_invalid"] = get(base)
    finally: stop(srv, th)
with tempfile.TemporaryDirectory() as d:
    db = Path(d) / "u.sqlite"; app = Manufacturing(db); app.seed_demo(); app.close()
    srv, th, base = serve(db, None)
    try: saved["unanchored"] = get(base)
    finally: stop(srv, th)
saved["verifying"] = (503, {"error": "VERIFYING", "state": "VERIFYING", "decisionsUnavailable": True})   # shape from server.py:143
saved["invalid_request"] = (400, {"error": "INVALID_REQUEST"})                                            # shape from server.py:145
for name, (status, body) in saved.items():
    (args.out / f"{name}.json").write_text(json.dumps({"status": status, "body": body}, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    print(name, status, (body.get("checkpoint") or {}).get("state") if isinstance(body, dict) else None)
