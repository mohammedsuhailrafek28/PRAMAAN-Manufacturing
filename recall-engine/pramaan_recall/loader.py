"""Fixture/policy loading and watermark helpers (no decision logic)."""
import json


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_case(path):
    return _load(path)


def load_policies(path):
    """-> ({policyId: policy}, coveragePolicy)"""
    d = _load(path)
    return {p["policyId"]: p for p in d["recallPolicies"]}, d["coveragePolicy"]


def full_watermark(events):
    wm = {}
    for e in events:
        wm[e["sourceId"]] = max(wm.get(e["sourceId"], 0), e["sourceSeq"])
    return wm


def watermark_at(events, cutoff):
    """Per-source highest sourceSeq recorded at or before `cutoff` (ISO Z)."""
    return full_watermark([e for e in events if e["recordedAt"] <= cutoff])
