"""Fixture-backed snapshot exporter for the Recall Investigation UI.

Runs the ACTUAL recall engine (current default semantics profile) over the synthetic
manufacturing fixtures and writes one JSON snapshot the UI loads through a typed adapter.

What is and is not in the snapshot
  * Decisions, reasons, gaps, ambiguity, history, notification obligations: engine output,
    copied verbatim. Nothing here assigns a verdict.
  * Genealogy components: read directly from install/removal events (record claims).
  * Shipments / suppliers: a clearly labelled SYNTHETIC OVERLAY (data/shipments.synthetic.json);
    the fixtures contain no shipment data.
  * Synthetic ground truth: copied from the fixtures for display of the case-06 safety story.
    The engine never sees it. The expected-outcome oracle files are NOT read.

Run:  python recall-ui/tools/export_snapshot.py [--out PATH] [--check]
"""
import argparse
import glob
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
ENGINE = os.path.join(REPO, "recall-engine")
sys.path.insert(0, ENGINE)

from pramaan_recall import Config, evaluate_series, load_case, load_policies  # noqa: E402
from pramaan_recall.engine import DEFAULT_PROFILE, ENGINE_VERSIONS  # noqa: E402

FIX = {1: os.path.join(ENGINE, "fixtures", "pramaan-mfg-fixtures"),
       2: os.path.join(ENGINE, "fixtures", "v2"),
       3: os.path.join(ENGINE, "fixtures", "v3")}
OVERLAY = os.path.join(REPO, "recall-ui", "data", "shipments.synthetic.json")
DEFAULT_OUT = os.path.join(REPO, "recall-ui", "public", "data", "snapshot.json")
DECISION_POINT_TYPES = {"WORK_ORDER_CLOSED", "SLOT_STATE_VERIFIED", "INSPECTION_RECORDED"}
FAMILY = {"case-01": "Replacement", "case-02": "Missing baseline", "case-03": "Install conflict",
          "case-04": "Capture outage", "case-05": "Late correction", "case-06": "Wrong-slot scan",
          "case-07": "Replacement", "case-08": "Untrusted observation"}


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def family(case_id):
    base = case_id[:7]
    return FAMILY.get(base, "Other")


def load_cases():
    cases = {}
    for v in (1, 2, 3):
        for p in sorted(glob.glob(os.path.join(FIX[v], "cases", "*.json"))):
            c = load_case(p)
            cases[c["caseId"]] = dict(case=c, fixtureSet=f"v{v}")
    return dict(sorted(cases.items()))


def load_truth(cases):
    side = {}
    for v in (2, 3):
        p = os.path.join(FIX[v], "ground-truth.json")
        if os.path.exists(p):
            side.update({k: x for k, x in read_json(p)["truths"].items()})
    out = {}
    for cid, c in cases.items():
        inline = (c["case"].get("groundTruth") or {}).get("trueP1Finding")
        if inline:
            out[cid] = dict(trueP1Finding=inline, basis="case file groundTruth")
        elif cid in side:
            out[cid] = dict(trueP1Finding=side[cid]["trueP1Finding"], basis=side[cid]["basis"])
    return out


def decision_watermarks(events, announced_at):
    """Ingestion points for decision versions. A recall decision cannot exist before the recall:
    the first is the state ingested by the announcement; later ones follow each event that can
    change a decision (work-order close, verification, inspection, correction), then the final state."""
    def wm_at(cut):
        wm = {}
        for e in events:
            if e["recordedAt"] <= cut:
                wm[e["sourceId"]] = max(wm.get(e["sourceId"], 0), e["sourceSeq"])
        return wm
    later = sorted({e["recordedAt"] for e in events if e["recordedAt"] > announced_at and (
        e["eventType"] in DECISION_POINT_TYPES or e.get("supersedesEventId"))})
    cuts = [announced_at] + later + [max(e["recordedAt"] for e in events)]
    out = []
    for cut in cuts:
        w = wm_at(cut)
        if w and (not out or w != out[-1]):
            out.append(w)
    return out


def genealogy(case_id, events):
    removed = {e["payload"].get("endsInstallEventId"): e for e in events if e["eventType"] == "COMPONENT_REMOVED"}
    superseded = {e["supersedesEventId"]: e["eventId"] for e in events if e.get("supersedesEventId")}
    comps = []
    for e in events:
        if e["eventType"] != "COMPONENT_INSTALLED":
            continue
        p, rm = e["payload"], removed.get(e["eventId"])
        comps.append(dict(
            componentId=e["eventId"], unitId=case_id, slot=p["slot"], part=p.get("part"), lot=p.get("lot"),
            serial=p.get("serial"), installedAt=e["occurredAt"], sourceId=e["sourceId"],
            removedAt=rm["occurredAt"] if rm else None, removalEventId=rm["eventId"] if rm else None,
            supersededBy=superseded.get(e["eventId"]), claimedBy="install record"))
    return comps


def public_event(e):
    keep = ("eventId", "eventType", "sourceId", "sourceSeq", "motorSerial", "workOrderId", "occurredAt",
            "recordedAt", "timeSource", "actorId", "evidenceRefs", "supersedesEventId", "payload")
    return {k: e.get(k) for k in keep}


def build():
    cases = load_cases()
    truth = load_truth(cases)
    overlay = read_json(OVERLAY)
    pol_cur, cov_cur = load_policies(os.path.join(FIX[3], "policies.json"))
    pol_old, cov_old = load_policies(os.path.join(FIX[1], "policies.json"))
    cur_cfg, old_cfg = Config.default(), Config.legacy()

    units, decisions, comparison, comps = [], {}, [], []
    for cid, row in cases.items():
        c = row["case"]
        ev = c["events"]
        wms = decision_watermarks(ev, next(iter(pol_cur.values()))["announcedAt"])
        decisions[cid] = {}
        for pid, pol in pol_cur.items():
            series = evaluate_series(c, pol, cov_cur, wms, cur_cfg)
            versions = [d for d in series if not d.get("unchanged")]
            decisions[cid][pid] = dict(current=series[-1], history=versions)
        units.append(dict(
            unitId=cid, motorSerial=ev[0]["motorSerial"], title=c["title"], description=c.get("description", ""),
            family=family(cid), fixtureSet=row["fixtureSet"], shipment=overlay["shipments"].get(cid),
            eventCount=len(ev), events=[public_event(e) for e in ev],
            captureSessions=c["captureCoverage"]["sessions"],
            syntheticGroundTruth=truth.get(cid)))
        comps += genealogy(cid, ev)
        if cid.startswith("case-06"):
            for pid in pol_cur:
                full = max((e["sourceSeq"] for e in ev), default=0)
                wm = decisions[cid][pid]["current"]["watermark"]
                legacy = evaluate_series(c, pol_old[pid], cov_old, [wm], old_cfg)[-1]
                comparison.append(dict(unitId=cid, policyId=pid, legacy=legacy,
                                       current=decisions[cid][pid]["current"], syntheticGroundTruth=truth.get(cid)))

    anyp = next(iter(pol_cur.values()))
    lots = sorted({(x["lot"], x["part"]) for x in comps if x["lot"]})
    snap = dict(
        schemaVersion=1,
        provenance=dict(
            dataKind="SYNTHETIC_FIXTURES",
            adapter="FixtureSnapshotSource (fixture-backed; replaceable)",
            engine=dict(semanticsProfile=DEFAULT_PROFILE, version=ENGINE_VERSIONS[DEFAULT_PROFILE]),
            comparisonEngine=dict(semanticsProfile="P1_LEGACY", version=ENGINE_VERSIONS["P1_LEGACY"]),
            fixtureManifests={"v1": sha256(os.path.join(os.path.dirname(FIX[1]), "MANIFEST.sha256")),
                              "v2": sha256(os.path.join(FIX[2], "MANIFEST.sha256")),
                              "v3": sha256(os.path.join(FIX[3], "MANIFEST.sha256"))},
            overlay=dict(file="recall-ui/data/shipments.synthetic.json", sha256=sha256(OVERLAY),
                         kind="SYNTHETIC_OVERLAY", covers="shipments and suppliers only"),
            oracleFilesRead=False),
        recall=dict(recallId=anyp["recallId"], version=anyp["version"], announcedAt=anyp["announcedAt"],
                    affectedPart=anyp["affectedPart"], affectedLots=anyp["affectedLots"],
                    affectedSlots=anyp["affectedSlots"]),
        policies=[dict(policyId=p["policyId"], exposureBasis=p["exposureBasis"],
                       damageInspection=p.get("damageInspection")) for p in pol_cur.values()],
        units=units, decisions=decisions, comparison=comparison, components=comps,
        lots=[dict(lotId=l, part=p, affected=(l in anyp["affectedLots"] and p == anyp["affectedPart"]),
                   supplier=overlay["suppliers"].get(l)) for l, p in lots])
    return snap


def dumps(snap):
    return json.dumps(snap, indent=1, sort_keys=True, default=str) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="fail if the committed snapshot is stale")
    a = ap.parse_args()
    text = dumps(build())
    if a.check:
        with open(a.out, encoding="utf-8", newline="") as f:
            if f.read() != text:
                print("STALE snapshot: run export_snapshot.py", file=sys.stderr)
                return 1
        print("snapshot is current")
        return 0
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote {a.out} ({len(text) // 1024} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
