"""Shared test helpers: fixture access and small history mutators."""
import copy
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pramaan_recall import Config, evaluate, evaluate_series, load_case, load_policies  # noqa: E402

FIX = os.path.join(ROOT, "fixtures", "pramaan-mfg-fixtures")
POLICIES, COVERAGE = load_policies(os.path.join(FIX, "policies.json"))
P1, P2 = "RC-009/P1", "RC-009/P2"
FMT = "%Y-%m-%dT%H:%M:%SZ"


def case(name):
    return copy.deepcopy(load_case(os.path.join(FIX, "cases", f"case-{name}.json")))


def policy(pid):
    return copy.deepcopy(POLICIES[pid])


def ev(c, etype, slot=None, source=None, wo=None):
    for e in c["events"]:
        if e["eventType"] == etype and (slot is None or e["payload"].get("slot") == slot) \
                and (source is None or e["sourceId"] == source) \
                and (wo is None or e.get("workOrderId") == wo):
            return e
    raise KeyError((etype, slot, source, wo))


def drop(c, e, renumber=True):
    c["events"] = [x for x in c["events"] if x["eventId"] != e["eventId"]]
    if renumber:
        n = {}
        for x in c["events"]:
            n[x["sourceId"]] = n.get(x["sourceId"], 0) + 1
            x["sourceSeq"] = n[x["sourceId"]]
    return c


def add_event(c, etype, source, occurred, actor, payload, wo=None, supersedes=None,
              session=None, recorded=None):
    seq = 1 + max([e["sourceSeq"] for e in c["events"] if e["sourceId"] == source], default=0)
    rec = recorded or (datetime.strptime(occurred, FMT) + timedelta(seconds=4)).strftime(FMT)
    e = dict(eventId=f"X-{len(c['events']) + 1:03d}", eventType=etype, schemaVersion=1,
             sourceId=source, sourceSeq=seq, motorSerial="M-042", workOrderId=wo, recallId=None,
             occurredAt=occurred, timeSource="DEVICE_SYNCED", recordedAt=rec, actorId=actor,
             evidenceRefs=[], supersedesEventId=supersedes, payload=payload)
    c["events"].append(e)
    if session:
        c["captureCoverage"]["sessions"].append(dict(sourceId=source, **{"from": session[0], "to": session[1]}))
    return e


def run(c, pid=P1, wm=None, cfg=None, pol=None):
    return evaluate(c, pol or policy(pid), COVERAGE, wm, cfg)


def codes(d):
    return set(d["reasonCodes"])


def empty_case():
    return dict(caseId="empty", events=[], captureCoverage=dict(coveragePolicy="COV-BEARING-v1", sessions=[]))
