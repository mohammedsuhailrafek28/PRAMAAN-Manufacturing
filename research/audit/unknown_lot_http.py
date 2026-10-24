"""Layer (a)-(e) over the real HTTP API (loopback, ephemeral port, disposable synthetic DB, in-process server).
Also tests near-miss spellings of the recalled lot. usage: python -B unknown_lot_http.py OUTFILE
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

CASES = [("UNKNOWN", "UNKNOWN"), ("unknown", "unknown"), ("N/A", "N/A"), ("whitespace", "   "), ("empty", ""), ("missing", None),
         ("known-unaffected", "BR-310"), ("known-recalled", "BR-204"),
         ("lowercase recalled", "br-204"), ("trailing space recalled", "BR-204 "), ("letter-O typo recalled", "BR-2O4"),
         ("en-dash recalled", "BR–204"), ("zero-width recalled", "BR-204​")]


def run(lot_case, lot, scope):
    with tempfile.TemporaryDirectory() as d:
        db, anchor = Path(d) / "h.sqlite", Path(d) / "a.json"
        app = Manufacturing(db); app.create_unit("MTR-90001"); app.close()
        app = Manufacturing(db); publish_candidate(anchor, export_anchor(app)); app.close()
        srv = make_server(db, 0, trusted_anchor=anchor)
        t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
        base = f"http://127.0.0.1:{srv.server_port}"
        try:
            token = json.load(urlopen(base + "/api/session"))["token"]

            def post(path, body):
                req = Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json", "X-Pramaan-Token": token})
                try:
                    with urlopen(req) as r:
                        return r.status, json.load(r)
                except HTTPError as e:
                    return e.code, json.load(e)
            body = {"deLot": lot, "ndeLot": "BR-310", "identity": "SERIAL"}
            if lot is None:
                del body["deLot"]
            s1, b1 = post("/api/units/MTR-90001/assemble", body)
            r = {"lotCase": lot_case, "lot": repr(lot), "recallScope": scope or "unspecified", "assembleStatus": s1}
            if s1 != 200:
                r["assembleError"] = b1
                r["unitEventsAfter"] = None
            post("/api/units/MTR-90001/ship", {})
            rb = {"lot": "BR-204"} | ({"affectedSlots": scope} if scope else {})
            s2, b2 = post("/api/recalls", rb)
            r["recallStatus"] = s2
            snap = b2.get("snapshot") or json.load(urlopen(base + "/api/snapshot"))
            cur = next(iter(snap["decisions"]["MTR-90001"].values()))["current"]
            r.update(checkpoint=snap["checkpoint"]["state"], eligibility=snap["eligibility"]["MTR-90001"]["currentReleaseEligible"],
                     evidenceFinding=cur["evidenceFinding"], operationalAction=cur["operationalAction"], reasonCodes=cur["reasonCodes"],
                     unitEventCount=next(u for u in snap["units"] if u["unitId"] == "MTR-90001")["eventCount"])
            return r
        finally:
            srv.shutdown(); t.join(); srv.server_close()


if __name__ == "__main__":
    out = []
    for scope in (["DE"], None):
        for name, lot in CASES:
            out.append(run(name, lot, scope))
            r = out[-1]
            print(f'{r["recallScope"]!s:12s} {name:24s} http={r["assembleStatus"]} {str(r.get("assembleError", ""))[:70]:70s} eventCount={r.get("unitEventCount")} {r.get("evidenceFinding")} {r.get("operationalAction")} {r.get("checkpoint")} eligible={r.get("eligibility")}')
    Path(sys.argv[1]).write_text(json.dumps(out, indent=1, sort_keys=True))
