"""Independent full-evaluator replay, run in a SEPARATE interpreter process.

Reads only serialised artefacts: the frozen scenario JSON and a JSON list of added events/sessions. It shares no code with the search
(no import of ops/methods/sandbox): the pinned evaluator is loaded by its own path, the added events are appended with ~10 lines
of independent logic, and the decision summary is printed as JSON.
usage: python independent_replay.py <scenario.json> <added.json>
"""
import copy
import json
import os
import sys

root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(root, "recall-engine"))
from pramaan_recall import Config, evaluate, load_policies  # noqa: E402

_, COVERAGE = load_policies(os.path.join(root, "recall-engine", "fixtures", "v3", "policies.json"))
sc = json.load(open(sys.argv[1], encoding="utf-8"))
added = json.load(open(sys.argv[2], encoding="utf-8"))
case, wm = copy.deepcopy(sc["case"]), dict(sc["watermark"])
for s in added["sessions"]:
    if s not in case["captureCoverage"]["sessions"]:
        case["captureCoverage"]["sessions"].append(s)
nxt = {}
for e in case["events"]:
    nxt[e["sourceId"]] = max(nxt.get(e["sourceId"], 0), e["sourceSeq"])
for e in sorted(added["events"], key=lambda e: (e["sourceSeq"] is None, e["recordedAt"], e["eventId"])):
    e = copy.deepcopy(e)
    if e["sourceSeq"] is None:
        nxt[e["sourceId"]] = max(nxt.get(e["sourceId"], 0), wm.get(e["sourceId"], 0)) + 1
        e["sourceSeq"] = nxt[e["sourceId"]]
    wm[e["sourceId"]] = max(wm.get(e["sourceId"], 0), e["sourceSeq"])
    case["events"].append(e)
d = evaluate(case, copy.deepcopy(sc["policy"]), copy.deepcopy(COVERAGE), wm, Config.v3())
print(json.dumps(dict(finding=d["evidenceFinding"], reasons=d["reasonCodes"], flags=d["flags"])))
