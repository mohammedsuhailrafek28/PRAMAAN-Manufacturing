"""Isolated, in-memory replay of synthetic cases through the pinned v3 evaluator. No database, no network.

Only plain dicts go in and out. The evaluator is imported from the in-tree recall-engine; its source hashes are
checked against the hashes recorded at the frozen baseline so a modified evaluator cannot be used silently.
"""
import copy
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENGINE = os.path.join(ROOT, "recall-engine")
sys.path.insert(0, ENGINE)
import pramaan_recall  # noqa: E402
from pramaan_recall import Config, evaluate, load_policies  # noqa: E402

if os.path.dirname(os.path.abspath(pramaan_recall.__file__)) != os.path.join(ENGINE, "pramaan_recall"):
    raise RuntimeError("unexpected evaluator location")

FIXTURES = os.path.join(ENGINE, "fixtures", "v3")
POLICIES, COVERAGE = load_policies(os.path.join(FIXTURES, "policies.json"))
CONFIG = Config.v3()


def evaluator_hashes():
    d = os.path.join(ENGINE, "pramaan_recall")
    return {f: hashlib.sha256(open(os.path.join(d, f), "rb").read()).hexdigest()
            for f in sorted(os.listdir(d)) if f.endswith(".py")}


def sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def replay(case, policy, coverage=None, watermark=None):
    """Evaluate deep copies; the caller's objects are never touched. `policy` is a policy dict. Returns the decision dict."""
    if not isinstance(case, dict) or not isinstance(policy, dict):
        raise TypeError("case and policy must be in-memory dicts, not paths or database handles")
    return evaluate(copy.deepcopy(case), copy.deepcopy(policy),
                    copy.deepcopy(coverage if coverage is not None else COVERAGE),
                    dict(watermark) if watermark is not None else None, CONFIG)


def summary(d):
    return dict(finding=d["evidenceFinding"], action=d["operationalAction"], reasons=list(d["reasonCodes"]),
                flags=list(d["flags"]), review=d["reviewRequired"],
                gaps=sorted({g["kind"] + ":" + g["materiality"] for s in d["slots"].values() for g in s["gaps"]}))
