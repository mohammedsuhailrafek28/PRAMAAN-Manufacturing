"""Evaluator observation 1: how does the pinned v3 evaluator treat an install whose lot is unknown? (read-only, in memory)
usage: python -B probe_unknown_lot.py
"""
import copy
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sandbox  # noqa: E402
import scenarios  # noqa: E402

sc = next(s for s in scenarios.load_all() if s["id"] == "A07")
for label, lot in (("lot=None", None), ("lot key missing", "DEL"), ("lot=''", ""), ("lot='UNKNOWN'", "UNKNOWN"), ("lot='BR-204' (control)", "BR-204")):
    c = copy.deepcopy(sc["case"])
    c["events"] = [e for e in c["events"] if e["eventId"] in ("S-01", "S-02", "S-03", "S-04")]
    for e in c["events"]:
        if e["eventId"] == "S-02":
            if lot == "DEL":
                del e["payload"]["lot"]
            else:
                e["payload"]["lot"] = lot
    wm = {}
    for e in c["events"]:
        wm[e["sourceId"]] = max(wm.get(e["sourceId"], 0), e["sourceSeq"])
    d = sandbox.replay(c, sc["policy"], watermark=wm)
    print(f"{label:24s} -> {d['evidenceFinding']} {d['reasonCodes']}")
