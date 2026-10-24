"""End to end through the real operator path: HTTP capture -> checkpoint_ops propose -> accept -> restart with accepted checkpoint -> GET.
Loopback, disposable synthetic DB. usage: python -B unknown_lot_e2e.py OUTFILE
"""
import json
import sys
import tempfile
import threading
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from application.service import Manufacturing  # noqa: E402
from application.anchors import export_anchor, publish_candidate  # noqa: E402
from application.server import make_server  # noqa: E402
from application import checkpoint_ops  # noqa: E402

M = "MTR-90001"


def serve(db, anchor, previous=None):
    srv = make_server(db, 0, trusted_anchor=anchor, previous_anchor=previous)
    t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
    return srv, t, f"http://127.0.0.1:{srv.server_port}"


def post(base, token, path, body):
    req = Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json", "X-Pramaan-Token": token})
    try:
        with urlopen(req) as r:
            return r.status, json.load(r)
    except HTTPError as e:
        return e.code, json.load(e)


def run(label, lot):
    with tempfile.TemporaryDirectory() as d:
        d = Path(d); db, cur, custody = d / "e.sqlite", d / "c0.json", d / "custody"
        app = Manufacturing(db); app.create_unit(M); app.close()
        app = Manufacturing(db); publish_candidate(cur, export_anchor(app)); app.close()
        srv, t, base = serve(db, cur)
        out = {"case": label, "lot": repr(lot)}
        try:
            tok = json.load(urlopen(base + "/api/session"))["token"]
            out["assemble"] = post(base, tok, f"/api/units/{M}/assemble", {"deLot": lot, "ndeLot": "BR-310", "identity": "SERIAL"})[0]
            post(base, tok, f"/api/units/{M}/ship", {})
            post(base, tok, "/api/recalls", {"lot": "BR-204", "affectedSlots": ["DE"]})
            snap = json.load(urlopen(base + "/api/snapshot"))
            out["beforeCheckpoint"] = {"state": snap["checkpoint"]["state"], "eligible": snap["eligibility"][M]["currentReleaseEligible"]}
        finally:
            srv.shutdown(); t.join(); srv.server_close()
        prop = checkpoint_ops.propose(db, cur, custody)
        out["proposeStatus"] = prop["status"]
        out["proposeShowsToReviewer"] = prop["covers"]  # everything the reviewer is shown
        acc = checkpoint_ops.accept(db, cur, custody, prop["candidate"], "synthetic-custodian", prop["candidateSha256"])
        srv, t, base = serve(db, Path(acc["accepted"]), cur)
        try:
            snap = json.load(urlopen(base + "/api/snapshot"))
            dec = next(iter(snap["decisions"][M].values()))["current"]
            out["afterCheckpoint"] = {"state": snap["checkpoint"]["state"], "eligible": snap["eligibility"][M]["currentReleaseEligible"],
                                      "finding": dec["evidenceFinding"], "action": dec["operationalAction"], "reasonCodes": dec["reasonCodes"]}
            st, body = 0, None
            try:
                with urlopen(base + f"/api/motors/{M}/decisions") as r:
                    st, body = r.status, json.load(r)
            except HTTPError as e:
                st = e.code
            out["decisionsEndpoint"] = {"status": st, "eligibility": (body or {}).get("eligibility")}
        finally:
            srv.shutdown(); t.join(); srv.server_close()
        return out


if __name__ == "__main__":
    res = [run(n, l) for n, l in (("UNKNOWN", "UNKNOWN"), ("letter-O typo of recalled", "BR-2O4"), ("known-unaffected control", "BR-310"), ("recalled control", "BR-204"))]
    for r in res:
        print(json.dumps(r, sort_keys=True))
    Path(sys.argv[1]).write_text(json.dumps(res, indent=1, sort_keys=True))
