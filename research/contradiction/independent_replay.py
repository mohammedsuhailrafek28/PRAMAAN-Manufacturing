"""Independent evaluator replay in a SEPARATE interpreter: evaluates a JSON list of fully built motor cases and prints the findings.
It imports no experiment code; only the pinned evaluator, loaded by its own path.
usage: python -I -B independent_replay.py <job.json>   job = {"policy": {...}, "cases": [case, ...]}
"""
import copy
import json
import os
import sys

root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(root, "recall-engine"))
from pramaan_recall import Config, evaluate, load_policies  # noqa: E402

_, COVERAGE = load_policies(os.path.join(root, "recall-engine", "fixtures", "v3", "policies.json"))
job = json.load(open(sys.argv[1], encoding="utf-8"))
out = []
for case in job["cases"]:
    d = evaluate(copy.deepcopy(case), copy.deepcopy(job["policy"]), copy.deepcopy(COVERAGE), None, Config.v3())
    out.append(dict(finding=d["evidenceFinding"], reasons=d["reasonCodes"]))
print(json.dumps(out))
