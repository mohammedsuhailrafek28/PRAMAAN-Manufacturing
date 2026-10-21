"""Checks fixture internal consistency (not engine correctness).
Run: python validate.py"""
import json, glob, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
errors = []


def err(msg):
    errors.append(msg)


policies = json.load(open(os.path.join(HERE, "policies.json")))
policy_ids = {p["policyId"] for p in policies["recallPolicies"]}
oracle = json.load(open(os.path.join(HERE, "oracle.json")))
cases = {}
for path in sorted(glob.glob(os.path.join(HERE, "cases", "*.json"))):
    c = json.load(open(path))
    cases[c["caseId"]] = c

for cid, c in cases.items():
    evs = c["events"]
    ids = [e["eventId"] for e in evs]
    if len(ids) != len(set(ids)):
        err(f"{cid}: duplicate eventIds")
    by_id, seen = {e["eventId"]: e for e in evs}, set()
    seqs = {}
    for e in evs:
        seqs.setdefault(e["sourceId"], []).append(e["sourceSeq"])
        if e["recordedAt"] < e["occurredAt"]:
            err(f"{cid}/{e['eventId']}: recordedAt before occurredAt")
        sess = [s for s in c["captureCoverage"]["sessions"] if s["sourceId"] == e["sourceId"]]
        if not any(s["from"] <= e["recordedAt"] <= s["to"] for s in sess):
            err(f"{cid}/{e['eventId']}: recorded outside any capture session of {e['sourceId']}")
        for ref_key, src in (("supersedesEventId", e),
                             ("endsInstallEventId", e["payload"])):
            ref = src.get(ref_key)
            if ref is None:
                continue
            if ref not in seen:
                err(f"{cid}/{e['eventId']}: {ref_key} -> {ref} not an earlier event")
            elif ref_key == "endsInstallEventId":
                tgt = by_id[ref]
                if tgt["eventType"] != "COMPONENT_INSTALLED" or \
                        tgt["payload"]["slot"] != e["payload"]["slot"]:
                    err(f"{cid}/{e['eventId']}: removal links to non-matching install")
        seen.add(e["eventId"])
    for src, s in seqs.items():
        if s != list(range(1, len(s) + 1)):
            err(f"{cid}: source {src} sequence not gap-free from 1: {s}")

oracle_ids = set()
for oc in oracle["cases"]:
    cid = oc["caseId"]
    oracle_ids.add(cid)
    if cid not in cases:
        err(f"oracle: unknown case {cid}"); continue
    c = cases[cid]
    ev_ids = {e["eventId"] for e in c["events"]}
    dec_ids = set()
    for ev in oc["evaluations"]:
        if ev["policyId"] not in policy_ids:
            err(f"oracle/{cid}: unknown policy {ev['policyId']}")
        for src, hw in ev["watermark"].items():
            if not any(e["sourceId"] == src and e["sourceSeq"] == hw for e in c["events"]):
                err(f"oracle/{cid}: watermark {src}:{hw} matches no event")
        if ev.get("supersedesDecisionId") and ev["supersedesDecisionId"] not in dec_ids:
            err(f"oracle/{cid}: supersedes unknown/later decision {ev['supersedesDecisionId']}")
        if ev.get("triggerEventId") and ev["triggerEventId"] not in ev_ids:
            err(f"oracle/{cid}: trigger {ev['triggerEventId']} not in case")
        if (ev["evidenceFinding"] in ("AFFECTED", "UNRESOLVED")) != \
                (ev["operationalAction"] == "RECALL_HOLD"):
            err(f"oracle/{cid}: finding/action mismatch in {ev['decisionId']}")
        if ev["decisionId"] in dec_ids:
            err(f"oracle/{cid}: duplicate decisionId {ev['decisionId']}")
        dec_ids.add(ev["decisionId"])

for cid in set(cases) - oracle_ids:
    err(f"case {cid} has no oracle entry")

if errors:
    print("\n".join(errors)); sys.exit(1)
print(f"OK: {len(cases)} cases, "
      f"{sum(len(o['evaluations']) for o in oracle['cases'])} evaluations consistent")
