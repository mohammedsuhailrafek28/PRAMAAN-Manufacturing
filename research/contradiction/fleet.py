"""Experiment B: 18 hand-authored synthetic fleets with authored ground truth. Every motor, serial, supplier, lot and actor is invented.

A fleet is {id, title, intent, policy, sessions, events, truth}. Events carry motorSerial; sourceSeq is assigned per motor view
(`motor_case`) because the pinned evaluator reads one motor's history at a time. The serial/supplier/timeUncertaintySeconds payload keys
are an experiment extension: the evaluator ignores unknown payload keys.

Ground truth (`truth`) was written from the physical story of each fleet, BEFORE detectors existed:
  contradictions      the physically incompatible claim groups: {id, cls DEFINITE|POSSIBLE|INSUFFICIENT, kind, eventIds, motors}
  sensitiveMotors     motors whose recall finding differs under at least one admissible interpretation of a contradiction
  releaseSensitive    motors for which some interpretation flips hold <-> release-eligible
"""
import copy
import hashlib
import json
import os

from sandbox import POLICIES

HERE = os.path.dirname(os.path.abspath(__file__))
AFF, OK, OK2 = "BR-204", "BR-310", "BR-312"
SESSIONS = [dict(sourceId="MES", **{"from": "2026-08-01T00:00:00Z", "to": "2026-10-31T00:00:00Z"}),
            dict(sourceId="ASSY-01", **{"from": "2026-08-01T00:00:00Z", "to": "2026-09-30T23:59:59Z"}),
            dict(sourceId="REWORK-03", **{"from": "2026-08-01T00:00:00Z", "to": "2026-09-30T23:59:59Z"})]


def _t(day, hms):
    return f"2026-{day}T{hms}Z"


def _rec(occ):
    return occ[:-3] + ("04" if occ[-3:-1] == "00" else "09") + "Z"


def E(eid, etype, src, occ, actor, motor, wo, payload, rec=None, sup=None, ts="DEVICE_SYNCED", refs=None):
    return dict(eventId=eid, eventType=etype, schemaVersion=1, sourceId=src, sourceSeq=None, motorSerial=motor, workOrderId=wo, recallId=None,
                occurredAt=occ, timeSource=ts, recordedAt=rec or _rec(occ), actorId=actor, evidenceRefs=refs or [], supersedesEventId=sup,
                payload=payload)


def _ident(lot, serial, supplier, lotlevel=False):
    if lotlevel:
        return dict(lot=lot, identityGranularity="LOT")
    return dict(lot=lot, serial=serial, supplier=supplier, identityGranularity="SERIAL")


def build(sid, m, day, de, nde=None, de_refs=None, open_at="09:30:00", de_at="10:00:00", close_at="11:00:00"):
    """BUILD order: DE (and optionally NDE) install from ASSY-01. de = (lot, serial, supplier) or (lot, None, None) for lot-level."""
    wo, lotlevel = f"MO-{m}", de[1] is None
    out = [E(f"{sid}-{m}-WO", "WORK_ORDER_OPENED", "MES", _t(day, open_at), "SYS-MES", m, wo,
             dict(orderType="BUILD", expectedChanges=[dict(slot="DE", action="INSTALL")] + ([dict(slot="NDE", action="INSTALL")] if nde else [])))]
    out.append(E(f"{sid}-{m}-DE", "COMPONENT_INSTALLED", "ASSY-01", _t(day, de_at), "EMP-009", m, wo,
                 dict(componentType="BEARING", slot="DE", part="BR-6205", **_ident(*de, lotlevel=lotlevel)), refs=de_refs))
    if nde:
        out.append(E(f"{sid}-{m}-NDE", "COMPONENT_INSTALLED", "ASSY-01", _t(day, "10:05:00"), "EMP-009", m, wo,
                     dict(componentType="BEARING", slot="NDE", part="BR-6205", **_ident(*nde))))
    out.append(E(f"{sid}-{m}-CL", "WORK_ORDER_CLOSED", "MES", _t(day, close_at), "SYS-MES", m, wo, dict(disposition="COMPLETED")))
    return out


def rework(sid, m, day, ends, removed, new=None, tag="", at="10:00:00", removed_ts="DEVICE_SYNCED", uncertainty=None, removed_rec=None,
           open_at="08:45:00", close_at="11:15:00"):
    """REWORK order on DE: removal observing `removed` (lot, serial, supplier), optional replacement install `new`."""
    wo = f"RW-{m}{tag}"
    obs = dict(componentType="BEARING", slot="DE", endsInstallEventId=ends, observedPart="BR-6205", observedLot=removed[0],
               observedSerial=removed[1], observedSupplier=removed[2], identityGranularity="SERIAL" if removed[1] else "LOT")
    if uncertainty:
        obs["timeUncertaintySeconds"] = uncertainty
    out = [E(f"{sid}-{m}-RW{tag}", "WORK_ORDER_OPENED", "MES", _t(day, open_at), "SYS-MES", m, wo,
             dict(orderType="REWORK", reason="NCR bearing noise", expectedChanges=[dict(slot="DE", action="REPLACE" if new else "REMOVE")])),
           E(f"{sid}-{m}-RM-DE{tag}", "COMPONENT_REMOVED", "REWORK-03", _t(day, at), "EMP-017", m, wo, obs, ts=removed_ts, rec=removed_rec)]
    if new:
        out.append(E(f"{sid}-{m}-RI-DE{tag}", "COMPONENT_INSTALLED", "REWORK-03", _t(day, "11:00:00"), "EMP-017", m, wo,
                     dict(componentType="BEARING", slot="DE", part="BR-6205", **_ident(*new))))
    out.append(E(f"{sid}-{m}-RC{tag}", "WORK_ORDER_CLOSED", "MES", _t(day, close_at), "SYS-MES", m, wo, dict(disposition="COMPLETED")))
    return out


def C(cid, cls, kind, event_ids, motors):
    return dict(id=cid, cls=cls, kind=kind, eventIds=sorted(event_ids), motors=sorted(motors))


def fleet(sid, title, intent, events, contradictions, sensitive, release, sessions=None, note=""):
    return dict(id=sid, title=title, intent=intent, policy=copy.deepcopy(POLICIES["RC-009/P1"]),
                sessions=[dict(s) for s in (sessions or SESSIONS)], events=events,
                truth=dict(contradictions=contradictions, sensitiveMotors=sorted(sensitive), releaseSensitiveMotors=sorted(release), note=note))


def make_all():
    F = []
    X = "SUP-X"
    # B01 one serialized bearing installed in two motors at once, both affected lots
    F.append(fleet("B01", "One serial installed in two motors simultaneously", "definite exclusive-occupancy conflict; both motors held either way",
                   build("B01", "M101", "08-12", (AFF, "SN-1001", X)) + build("B01", "M102", "08-13", (AFF, "SN-1001", X)),
                   [C("B01-C1", "DEFINITE", "EXCLUSIVE_OCCUPANCY", ["B01-M101-DE", "B01-M102-DE"], ["M101", "M102"])],
                   ["M101", "M102"], []))
    # B02 valid removal + reuse of the removed bearing in another motor
    F.append(fleet("B02", "Valid removal then reuse in another motor", "no contradiction (valid transition)",
                   build("B02", "M101", "08-12", (AFF, "SN-1002", X)) + rework("B02", "M101", "09-10", "B02-M101-DE", (AFF, "SN-1002", X), (OK2, "SN-2002", X))
                   + build("B02", "M102", "08-13", (OK, "SN-1102", X)) + rework("B02", "M102", "09-12", "B02-M102-DE", (OK, "SN-1102", X), (AFF, "SN-1002", X)),
                   [], [], []))
    # B03 same serial string from two suppliers: a collision, not a contradiction
    F.append(fleet("B03", "Supplier-scoped serial collision", "no contradiction (distinct items)",
                   build("B03", "M101", "08-12", (AFF, "SN-0123", "SUP-X")) + build("B03", "M102", "08-13", (OK, "SN-0123", "SUP-Y")),
                   [], [], []))
    # B04 approximate removal time: the later install may or may not overlap the earlier occupancy
    F.append(fleet("B04", "Removal time only approximately known", "possible conflict (order undeterminable)",
                   build("B04", "M101", "08-12", (AFF, "SN-1004", X))
                   + rework("B04", "M101", "08-12", "B04-M101-DE", (AFF, "SN-1004", X), None, at="12:00:00", removed_ts="OPERATOR_ESTIMATED",
                            uncertainty=7200, removed_rec=_t("09-10", "10:00:04"), open_at="11:30:00", close_at="14:30:00")
                   + build("B04", "M102", "08-12", (AFF, "SN-1004", X), open_at="12:30:00", de_at="13:00:00", close_at="13:30:00"),
                   [C("B04-C1", "POSSIBLE", "EXCLUSIVE_OCCUPANCY", ["B04-M101-DE", "B04-M101-RM-DE", "B04-M102-DE"], ["M101", "M102"])],
                   ["M101", "M102"], ["M101"]))
    # B05 conflicting lot identities for one serial across a valid removal/reinstall
    F.append(fleet("B05", "One serial recorded with two different lots", "definite lot-identity conflict; only the reinstalling motor depends on it",
                   build("B05", "M101", "08-12", (AFF, "SN-1005", X)) + rework("B05", "M101", "09-10", "B05-M101-DE", (AFF, "SN-1005", X), (OK2, "SN-2005", X))
                   + build("B05", "M102", "08-13", (OK2, "SN-1105", X)) + rework("B05", "M102", "09-12", "B05-M102-DE", (OK2, "SN-1105", X), (OK, "SN-1005", X)),
                   [C("B05-C1", "DEFINITE", "LOT_IDENTITY", ["B05-M101-DE", "B05-M101-RM-DE", "B05-M102-RI-DE"], ["M101", "M102"])],
                   ["M102"], ["M102"]))
    # B06 the apparent duplicate is superseded by a correction
    ev6 = build("B06", "M101", "08-12", (OK, "SN-1006", X)) + build("B06", "M102", "08-13", (OK, "SN-1006", X))
    ev6.append(E("B06-M102-DE-CORR", "COMPONENT_INSTALLED", "REWORK-03", _t("09-10", "09:00:00"), "EMP-017", "M102", "MO-M102",
                 dict(componentType="BEARING", slot="DE", part="BR-6205", **_ident(OK, "SN-1066", X)), sup="B06-M102-DE"))
    F.append(fleet("B06", "Apparent duplicate superseded by a correction", "no contradiction after the correction", ev6, [], [], []))
    # B07 the earlier occupant's removal could have gone uncaptured (rework station coverage gap in between)
    s7 = [dict(s) for s in SESSIONS if s["sourceId"] != "REWORK-03"] + [
        dict(sourceId="REWORK-03", **{"from": "2026-08-01T00:00:00Z", "to": "2026-09-02T00:00:00Z"}),
        dict(sourceId="REWORK-03", **{"from": "2026-09-05T00:00:00Z", "to": "2026-09-30T23:59:59Z"})]
    F.append(fleet("B07", "Possible uncaptured removal inside a coverage gap", "possible conflict (missing removal evidence)",
                   build("B07", "M101", "08-12", (AFF, "SN-1007", X)) + build("B07", "M102", "09-12", (AFF, "SN-1007", X)),
                   [C("B07-C1", "POSSIBLE", "EXCLUSIVE_OCCUPANCY", ["B07-M101-DE", "B07-M102-DE"], ["M101", "M102"])],
                   ["M101"], [], sessions=s7))
    # B08 definite conflict where both motors are currently excluded
    F.append(fleet("B08", "Excluded motors resting on contested claims", "definite conflict; both release decisions rest on contested evidence",
                   build("B08", "M101", "08-12", (OK, "SN-1008", X)) + build("B08", "M102", "08-13", (OK, "SN-1008", X)),
                   [C("B08-C1", "DEFINITE", "EXCLUSIVE_OCCUPANCY", ["B08-M101-DE", "B08-M102-DE"], ["M101", "M102"])],
                   ["M101", "M102"], ["M101", "M102"]))
    # B09 hash-valid but mutually contradictory
    def hashed(evs):
        for e in evs:
            e["evidenceRefs"] = ["sha256:" + hashlib.sha256(json.dumps(e["payload"], sort_keys=True).encode()).hexdigest()]
        return evs
    F.append(fleet("B09", "Every record hash-valid, claims mutually contradictory", "definite conflict that integrity checking cannot see",
                   hashed(build("B09", "M101", "08-12", (AFF, "SN-1009", X)) + build("B09", "M102", "08-13", (AFF, "SN-1009", X))
                          + build("B09", "M103", "08-14", (OK, "SN-1109", X))),
                   [C("B09-C1", "DEFINITE", "EXCLUSIVE_OCCUPANCY", ["B09-M101-DE", "B09-M102-DE"], ["M101", "M102"])],
                   ["M101", "M102"], []))
    # B10 overlap AND lot conflict, one held and one excluded motor
    F.append(fleet("B10", "Overlap and lot conflict between a held and an excluded motor", "two definite conflicts on the same claims",
                   build("B10", "M101", "08-12", (AFF, "SN-1010", X)) + build("B10", "M102", "08-13", (OK, "SN-1010", X)),
                   [C("B10-C1", "DEFINITE", "EXCLUSIVE_OCCUPANCY", ["B10-M101-DE", "B10-M102-DE"], ["M101", "M102"]),
                    C("B10-C2", "DEFINITE", "LOT_IDENTITY", ["B10-M101-DE", "B10-M102-DE"], ["M101", "M102"])],
                   ["M101", "M102"], ["M101", "M102"]))
    # B11 an unrelated conflict must not touch other motors that share the affected lot
    F.append(fleet("B11", "Unrelated conflict must not propagate", "conflict confined to two motors",
                   build("B11", "M101", "08-12", (AFF, "SN-1011", X)) + build("B11", "M102", "08-13", (AFF, "SN-1011", X))
                   + build("B11", "M103", "08-14", (AFF, "SN-1111", X)) + build("B11", "M104", "08-15", (OK, "SN-1211", X)),
                   [C("B11-C1", "DEFINITE", "EXCLUSIVE_OCCUPANCY", ["B11-M101-DE", "B11-M102-DE"], ["M101", "M102"])],
                   ["M101", "M102"], []))
    # B12 two interacting contradictions through M102
    F.append(fleet("B12", "Two interacting contradictions", "cluster of three motors",
                   build("B12", "M101", "08-12", (OK, "SN-1012", X)) + build("B12", "M102", "08-13", (OK, "SN-1112", X))
                   + rework("B12", "M102", "09-10", "B12-M102-DE", (OK, "SN-1112", X), (OK, "SN-1012", X)) + build("B12", "M103", "08-14", (OK, "SN-1112", X)),
                   [C("B12-C1", "DEFINITE", "EXCLUSIVE_OCCUPANCY", ["B12-M101-DE", "B12-M102-RI-DE"], ["M101", "M102"]),
                    C("B12-C2", "DEFINITE", "EXCLUSIVE_OCCUPANCY", ["B12-M102-DE", "B12-M102-RM-DE", "B12-M103-DE"], ["M102", "M103"])],
                   ["M101", "M102", "M103"], ["M101", "M102", "M103"]))
    # B13 removal dated before the install it ends
    F.append(fleet("B13", "Removal dated before the install it ends", "definite chronology contradiction in one motor",
                   build("B13", "M101", "08-12", (OK, "SN-1013", X)) + rework("B13", "M101", "08-12", "B13-M101-DE", (OK, "SN-1013", X), None, at="09:00:00",
                                                                           removed_rec=_t("09-10", "10:00:04")),
                   [C("B13-C1", "DEFINITE", "CHRONOLOGY", ["B13-M101-DE", "B13-M101-RM-DE"], ["M101"])],
                   [], [], note="author expected the hold to persist under every interpretation"))
    # B14 same serial in both slots of one motor
    F.append(fleet("B14", "Same serial in both slots of one motor", "definite conflict within a motor, only DE is in recall scope",
                   build("B14", "M101", "08-12", (OK, "SN-1014", X), nde=(OK, "SN-1014", X)),
                   [C("B14-C1", "DEFINITE", "EXCLUSIVE_OCCUPANCY", ["B14-M101-DE", "B14-M101-NDE"], ["M101"])],
                   ["M101"], ["M101"]))
    # B15 supplier missing on one claim: cannot tell duplicate from collision
    F.append(fleet("B15", "Supplier missing on one claim", "insufficient evidence to classify",
                   build("B15", "M101", "08-12", (AFF, "SN-1015", X)) + build("B15", "M102", "08-13", (OK, "SN-1015", None)),
                   [C("B15-C1", "INSUFFICIENT", "EXCLUSIVE_OCCUPANCY", ["B15-M101-DE", "B15-M102-DE"], ["M101", "M102"]),
                    C("B15-C2", "INSUFFICIENT", "LOT_IDENTITY", ["B15-M101-DE", "B15-M102-DE"], ["M101", "M102"])],
                   ["M101", "M102"], ["M101", "M102"]))
    # B16 serial transposition across two motors
    ev16 = build("B16", "M101", "08-12", (OK, "SN-1016A", X)) + build("B16", "M102", "08-13", (AFF, "SN-1016B", X))
    ev16 += rework("B16", "M101", "09-10", "B16-M101-DE", (AFF, "SN-1016B", X), None, at="10:00:00")
    ev16 += rework("B16", "M102", "09-10", "B16-M102-DE", (OK, "SN-1016A", X), None, at="10:30:00")
    F.append(fleet("B16", "Serial transposition between two motors", "two definite cross-motor conflicts",
                   ev16, [C("B16-C1", "DEFINITE", "EXCLUSIVE_OCCUPANCY", ["B16-M102-DE", "B16-M101-RM-DE"], ["M101", "M102"]),
                          C("B16-C2", "DEFINITE", "EXCLUSIVE_OCCUPANCY", ["B16-M101-DE", "B16-M102-RM-DE"], ["M101", "M102"])],
                   [], [], note="both motors are already UNRESOLVED from intra-motor removal mismatches"))
    # B17 lot-level identity only
    F.append(fleet("B17", "Lot-level records only", "no serials, so no identity contradictions",
                   build("B17", "M101", "08-12", (AFF, None, None)) + build("B17", "M102", "08-13", (AFF, None, None)) + build("B17", "M103", "08-14", (OK, None, None)),
                   [], [], []))
    # B18 valid cycle of one bearing through three installs
    ev18 = build("B18", "M101", "08-12", (OK, "SN-1018", X)) + build("B18", "M102", "08-13", (OK2, "SN-1118", X))
    ev18 += rework("B18", "M101", "09-10", "B18-M101-DE", (OK, "SN-1018", X), (OK2, "SN-2018", X), tag="a")
    ev18 += rework("B18", "M102", "09-11", "B18-M102-DE", (OK2, "SN-1118", X), (OK, "SN-1018", X), tag="a")
    ev18 += rework("B18", "M102", "09-15", "B18-M102-RI-DEa", (OK, "SN-1018", X), (OK2, "SN-1218", X), tag="b")
    ev18 += rework("B18", "M101", "09-16", "B18-M101-RI-DEa", (OK2, "SN-2018", X), (OK, "SN-1018", X), tag="b")
    F.append(fleet("B18", "Valid cycle of one bearing through two motors", "no contradiction", ev18, [], [], []))
    return F


def motor_case(f, motor, events=None, label=None):
    """Per-motor evaluator input: that motor's events with contiguous per-source sequence numbers."""
    evs = copy.deepcopy([e for e in (events if events is not None else f["events"]) if e["motorSerial"] == motor])
    evs.sort(key=lambda e: (e["recordedAt"], e["occurredAt"], e["eventId"]))
    seq = {}
    for e in evs:
        seq[e["sourceId"]] = seq.get(e["sourceId"], 0) + 1
        e["sourceSeq"] = seq[e["sourceId"]]
    return dict(caseId=f"{f['id']}-{motor}{'-' + label if label else ''}", events=evs,
                captureCoverage=dict(coveragePolicy="COV-BEARING-v1", sessions=copy.deepcopy(f["sessions"])))


def motors(f, events=None):
    return sorted({e["motorSerial"] for e in (events if events is not None else f["events"])})


def write_all(directory=None):
    d = directory or os.path.join(HERE, "fleets")
    os.makedirs(d, exist_ok=True)
    for f in make_all():
        with open(os.path.join(d, f["id"] + ".json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(f, fh, indent=1, sort_keys=True)
            fh.write("\n")


def load_all(directory=None):
    d = directory or os.path.join(HERE, "fleets")
    return [json.load(open(os.path.join(d, n), encoding="utf-8")) for n in sorted(os.listdir(d)) if n.startswith("B") and n.endswith(".json")]


if __name__ == "__main__":
    write_all()
