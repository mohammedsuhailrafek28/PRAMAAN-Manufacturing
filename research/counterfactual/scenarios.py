"""Experiment A: 18 hand-authored synthetic scenarios (no randomness). Every motor, lot, actor and source is invented.

A scenario is {id, title, intent, policy, case, watermark, facts}. `facts` declares what is physically/organisationally
obtainable; the hypothetical-evidence catalog (ops.py) is derived from it. `intent` is the author's expectation, written
BEFORE any candidate ran; it is compared with the pinned evaluator's baseline (it is not a target the candidates are tuned to).
"""
import copy
import json
import os

from sandbox import POLICIES

NOW = "2026-10-15T09:00:00Z"
HERE = os.path.dirname(os.path.abspath(__file__))
U, A = "BR-310", "BR-204"        # hypothesis lots: an unaffected lot / an affected lot (policy RC-009 affects BR-204, BR-207)

SESSIONS = [dict(sourceId="MES", **{"from": "2026-08-01T00:00:00Z", "to": "2026-10-31T00:00:00Z"}),
            dict(sourceId="ASSY-01", **{"from": "2026-08-12T08:00:00Z", "to": "2026-08-12T18:00:00Z"}),
            dict(sourceId="REWORK-03", **{"from": "2026-09-10T08:00:00Z", "to": "2026-09-10T18:00:00Z"})]
QA_2026_09_10 = dict(sourceId="QA-02", **{"from": "2026-09-10T09:00:00Z", "to": "2026-09-10T12:00:00Z"})
HH_2026_09_10 = dict(sourceId="HANDHELD-09", **{"from": "2026-09-10T11:00:00Z", "to": "2026-09-10T12:00:00Z"})


def ev(eid, etype, src, seq, occ, rec, actor, wo, payload, sup=None, ts="DEVICE_SYNCED", refs=None):
    return dict(eventId=eid, eventType=etype, schemaVersion=1, sourceId=src, sourceSeq=seq, motorSerial="M-042", workOrderId=wo,
                recallId=None, occurredAt=occ, timeSource=ts, recordedAt=rec, actorId=actor, evidenceRefs=refs or [],
                supersedesEventId=sup, payload=payload)


def t(hms, day="2026-08-12"):
    return f"{day}T{hms}Z"


def build(de_lot=A, nde_lot="BR-150", de=True, nde=True):
    """BUILD work order MO-042: installs recorded from ASSY-01, closed COMPLETED."""
    out = [ev("S-01", "WORK_ORDER_OPENED", "MES", 1, t("09:30:00"), t("09:30:04"), "SYS-MES", "MO-042",
              dict(orderType="BUILD", expectedChanges=[dict(slot="DE", action="INSTALL"), dict(slot="NDE", action="INSTALL")]))]
    n = 0
    if de:
        n += 1
        out.append(ev("S-02", "COMPONENT_INSTALLED", "ASSY-01", n, t("10:00:00"), t("10:00:04"), "EMP-009", "MO-042",
                      dict(componentType="BEARING", slot="DE", part="BR-6205", lot=de_lot, identityGranularity="LOT")))
    if nde:
        n += 1
        out.append(ev("S-03", "COMPONENT_INSTALLED", "ASSY-01", n, t("10:05:00"), t("10:05:04"), "EMP-009", "MO-042",
                      dict(componentType="BEARING", slot="NDE", part="BR-6205", lot=nde_lot, identityGranularity="LOT")))
    out.append(ev("S-04", "WORK_ORDER_CLOSED", "MES", 2, t("11:00:00"), t("11:00:04"), "SYS-MES", "MO-042", dict(disposition="COMPLETED")))
    return out


def rework(removed_lot=A, new_lot="BR-312", removed=True, installed=True, slot="DE", ends="S-02", rseq=1):
    day = "2026-09-10"
    out = [ev("S-05", "WORK_ORDER_OPENED", "MES", 3, t("08:45:00", day), t("08:45:04", day), "SYS-MES", "RW-192",
              dict(orderType="REWORK", reason="NCR-0771 bearing noise", expectedChanges=[dict(slot=slot, action="REPLACE")]))]
    n = rseq
    if removed:
        out.append(ev("S-06", "COMPONENT_REMOVED", "REWORK-03", n, t("10:00:00", day), t("10:00:04", day), "EMP-017", "RW-192",
                      dict(componentType="BEARING", slot=slot, endsInstallEventId=ends, observedPart="BR-6205", observedLot=removed_lot,
                           identityGranularity="LOT")))
        n += 1
    if installed:
        out.append(ev("S-07", "COMPONENT_INSTALLED", "REWORK-03", n, t("11:00:00", day), t("11:00:04", day), "EMP-017", "RW-192",
                      dict(componentType="BEARING", slot=slot, part="BR-6205", lot=new_lot, identityGranularity="LOT")))
    out.append(ev("S-08", "WORK_ORDER_CLOSED", "MES", 4, t("11:15:00", day), t("11:15:04", day), "SYS-MES", "RW-192",
                  dict(disposition="COMPLETED")))
    return out


def handheld(eid, lot, slot="DE"):
    return ev(eid, "SLOT_STATE_VERIFIED", "HANDHELD-09", 1, t("11:30:00", "2026-09-10"), t("11:30:04", "2026-09-10"), "EMP-050", None,
              dict(componentType="BEARING", slot=slot, observedPart="BR-6205", observedLot=lot, method="LOT_LABEL_AND_MARKING_VISUAL"))


def lost(eid, etype, src, seq, occ, rec, actor, wo, payload):
    """Envelope of a record known to have existed (its source high-water mark proves it) but whose content is lost."""
    return dict(eventId=eid, eventType=etype, sourceId=src, sourceSeq=seq, occurredAt=occ, recordedAt=rec, actorId=actor, workOrderId=wo, payload=payload)


def lost_install_de():
    return lost("S-02", "COMPONENT_INSTALLED", "ASSY-01", 1, t("10:00:00"), t("10:00:04"), "EMP-009", "MO-042",
                dict(componentType="BEARING", slot="DE", part="BR-6205", identityGranularity="LOT"))


def mk(sid, title, intent, events, policy="RC-009/P1", sessions=None, lost_records=None, facts=None, policy_edit=None):
    case = dict(caseId=sid, events=events, captureCoverage=dict(coveragePolicy="COV-BEARING-v1",
                sessions=[dict(s) for s in SESSIONS] + [dict(s) for s in (sessions or [])]))
    wm = {}
    for e in list(events) + list(lost_records or []):
        wm[e["sourceId"]] = max(wm.get(e["sourceId"], 0), e["sourceSeq"])
    pol = copy.deepcopy(POLICIES[policy])
    if policy_edit:
        pol.update(policy_edit)
    f = dict(slots=list(pol["affectedSlots"]), slotAccessible=dict(DE=True, NDE=True), lostRecords=lost_records or [], lostRecoverable=True,
             inspectionPossible=False, correctionPossible=False, accessEvidenceArchive=False, exceptionIds=[])
    f.update(facts or {})
    return dict(id=sid, title=title, intent=intent, policy=pol, case=case, watermark=wm, facts=f)


def renumber_source(events, src):
    for i, e in enumerate(sorted([x for x in events if x["sourceId"] == src], key=lambda x: x["recordedAt"]), 1):
        e["sourceSeq"] = i


def make_all():
    S = []
    # A01 lost install record (sequence gap): only recovering the record can clear it
    e = [x for x in build() if x["eventId"] != "S-02"]
    S.append(mk("A01", "Lost DE install record (source sequence gap)", "UNRESOLVED; clearable only by recovering the record",
                e, lost_records=[lost_install_de()]))
    for x in e:
        if x["eventId"] == "S-03":
            x["sourceSeq"] = 2
    # A02 identity never captured (no gap, no record): physical verification can re-establish the state
    S.append(mk("A02", "DE install never captured, no sequence gap", "UNRESOLVED; clearable by independent verification", build(de=False)))
    # A03 conflicting lot info: install says BR-310, removal observed BR-204
    S.append(mk("A03", "Install says BR-310, removal observed BR-204, DE re-installed BR-312", "UNRESOLVED hard conflict",
                build(de_lot="BR-310") + rework(removed_lot=A)))
    # A04 DE/NDE ambiguity: both ends BR-204, removal claimed DE, observed BR-204
    S.append(mk("A04", "DE/NDE ambiguity: both ends BR-204, removal claimed DE",
                "UNRESOLVED (ambiguous slot attribution); a verification or archive-retrieved access evidence clears it",
                build(de_lot=A, nde_lot=A) + rework(removed_lot=A), facts=dict(accessEvidenceArchive=True)))
    # A05 P2: exposure confirmed, damage inspection missing
    S.append(mk("A05", "Historical exposure confirmed, damage inspection missing (P2)", "AFFECTED; clearable by a qualified passing inspection",
                build(de_lot=A) + rework(removed_lot=A), policy="RC-009/P2", facts=dict(inspectionPossible=True)))
    # A06 corrected installation record claims BR-310 over BR-204 (risk decreasing)
    corr = ev("S-09", "COMPONENT_INSTALLED", "REWORK-03", 1, t("09:00:00", "2026-09-10"), t("09:00:04", "2026-09-10"), "EMP-017", "MO-042",
              dict(componentType="BEARING", slot="DE", part="BR-6205", lot="BR-310", identityGranularity="LOT"), sup="S-02")
    S.append(mk("A06", "Correction record claims BR-310 over a recorded BR-204 (risk decreasing)", "UNRESOLVED (correction not applied); corroboration may clear",
                build(de_lot=A) + [corr], facts=dict(correctionPossible=True)))
    # A07 untrusted observation of an affected lot (supplier/handheld claim)
    S.append(mk("A07", "Untrusted handheld sighting of BR-204 in DE, records say BR-312", "UNRESOLVED; a later trusted verification clears",
                build(de_lot="BR-310") + rework(removed_lot="BR-310") + [handheld("S-10", A)], sessions=[HH_2026_09_10]))
    # A08 invalid chronology: an event recorded before it occurred
    bad = build(de_lot="BR-310")
    bad[1]["recordedAt"] = t("09:00:00")
    S.append(mk("A08", "DE install recorded before it occurred (invalid chronology)", "UNRESOLVED; no additional evidence can repair it", bad))
    # A09 unresolved capture exception on DE
    exc = ev("S-11", "CAPTURE_EXCEPTION_RAISED", "REWORK-03", 2, t("10:30:00", "2026-09-10"), t("10:30:04", "2026-09-10"), "EMP-017", "RW-192",
             dict(exceptionType="MISSED_SCAN", scope=dict(slots=["DE"]), detail="DE handled without scan"))
    r9 = rework(removed_lot="BR-310")
    r9[2]["sourceSeq"] = 3          # the exception sits between the removal (seq 1) and the re-install
    S.append(mk("A09", "Unresolved capture exception on DE",
                "UNRESOLVED; verification bounds it; a clerical resolve is evaluator-accepted but inadmissible",
                build(de_lot="BR-310") + r9[:3] + [exc] + r9[3:], facts=dict(exceptionIds=["S-11"])))
    # A10 verified affected lot installed
    ver_aff = ev("S-12", "SLOT_STATE_VERIFIED", "QA-02", 1, t("09:00:00", "2026-10-05"), t("09:00:04", "2026-10-05"), "EMP-031", None,
                 dict(componentType="BEARING", slot="DE", observedPart="BR-6205", observedLot=A, method="DISASSEMBLY_INSPECTION"))
    S.append(mk("A10", "Independent verification confirms BR-204 installed in DE", "AFFECTED; no evidence can legitimately clear it",
                build(de_lot=A) + [ver_aff], sessions=[dict(sourceId="QA-02", **{"from": "2026-10-05T08:00:00Z", "to": "2026-10-05T18:00:00Z"})]))
    # A11 sealed, shipped motor: the slot cannot be inspected
    S.append(mk("A11", "DE install never captured and motor sealed (no physical access)", "UNRESOLVED; no obtainable evidence",
                build(de=False), facts=dict(slotAccessible=dict(DE=False, NDE=False))))
    # A12 lost record AND untrusted sighting: needs both
    e = [x for x in build(de_lot="BR-310") if x["eventId"] != "S-02"]
    for x in e:
        if x["eventId"] == "S-03":
            x["sourceSeq"] = 2
    S.append(mk("A12", "Lost DE install record plus untrusted BR-204 sighting", "UNRESOLVED; two independent defects, two pieces of evidence",
                e + [handheld("S-10", A)], lost_records=[lost_install_de()], sessions=[HH_2026_09_10]))
    # A13 lost record, original device storage destroyed
    e = [x for x in build() if x["eventId"] != "S-02"]
    for x in e:
        if x["eventId"] == "S-03":
            x["sourceSeq"] = 2
    S.append(mk("A13", "Lost DE install record, device storage destroyed", "UNRESOLVED; nothing obtainable clears it",
                e, lost_records=[lost_install_de()], facts=dict(lostRecoverable=False)))
    # A14 replacement recorded without the removal -> double occupancy; the removal record was lost
    S.append(mk("A14", "Replacement install recorded, removal record lost (double occupancy)",
                "UNRESOLVED; verification cannot clear a record conflict, recovering the removal can",
                build(de_lot=A) + rework(removed=False, installed=True, rseq=2),
                lost_records=[lost("S-06", "COMPONENT_REMOVED", "REWORK-03", 1, t("10:00:00", "2026-09-10"), t("10:00:04", "2026-09-10"),
                                   "EMP-017", "RW-192", dict(componentType="BEARING", slot="DE", endsInstallEventId="S-02",
                                                             observedPart="BR-6205", identityGranularity="LOT"))]))
    # A15 P2: lost rework install record AND missing damage inspection -> two pieces
    ev15 = [x for x in build(de_lot=A) + rework(removed_lot=A) if x["eventId"] != "S-07"]
    S.append(mk("A15", "Historical exposure, inspection missing and a lost rework install record", "AFFECTED; needs inspection and the record",
                ev15, policy="RC-009/P2", facts=dict(inspectionPossible=True),
                lost_records=[lost("S-07", "COMPONENT_INSTALLED", "REWORK-03", 2, t("11:00:00", "2026-09-10"), t("11:00:04", "2026-09-10"),
                                   "EMP-017", "RW-192", dict(componentType="BEARING", slot="DE", part="BR-6205", identityGranularity="LOT"))]))
    # A16 P2: inspection exists but inspector not qualified
    insp = ev("S-13", "INSPECTION_RECORDED", "QA-02", 1, t("09:00:00", "2026-10-06"), t("09:00:04", "2026-10-06"), "EMP-031", None,
              dict(protocolId="RC-009-DMG-01", scope=["DE"], result="PASS", inspectorQualifiedFor=[]))
    S.append(mk("A16", "Damage inspection recorded by an unqualified inspector (P2)", "AFFECTED; a qualified re-inspection clears",
                build(de_lot=A) + rework(removed_lot=A) + [insp], policy="RC-009/P2", facts=dict(inspectionPossible=True),
                sessions=[dict(sourceId="QA-02", **{"from": "2026-10-06T08:00:00Z", "to": "2026-10-06T18:00:00Z"})]))
    # A17 risk-increasing correction (claims BR-204 over BR-310)
    corr17 = ev("S-09", "COMPONENT_INSTALLED", "REWORK-03", 1, t("09:00:00", "2026-09-10"), t("09:00:04", "2026-09-10"), "EMP-017", "MO-042",
                dict(componentType="BEARING", slot="DE", part="BR-6205", lot=A, identityGranularity="LOT"), sup="S-02")
    S.append(mk("A17", "Correction record claims BR-204 over a recorded BR-310 (risk increasing)", "UNRESOLVED; the claim may not be clearable by evidence",
                build(de_lot="BR-310") + [corr17], facts=dict(correctionPossible=True)))
    # A18 two-slot recall scope, neither slot's install captured
    S.append(mk("A18", "Two-slot scope (DE+NDE), neither install captured", "UNRESOLVED; one verification per slot",
                build(de=False, nde=False), policy_edit=dict(affectedSlots=["DE", "NDE"], policyId="RC-009/P1-2SLOT")))
    return S


def write_all(directory=None):
    d = directory or os.path.join(HERE, "scenarios")
    os.makedirs(d, exist_ok=True)
    for s in make_all():
        with open(os.path.join(d, s["id"] + ".json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(s, f, indent=1, sort_keys=True)
            f.write("\n")


def load_all(directory=None):
    d = directory or os.path.join(HERE, "scenarios")
    return [json.load(open(os.path.join(d, n), encoding="utf-8")) for n in sorted(os.listdir(d)) if n.startswith("A") and n.endswith(".json")]


if __name__ == "__main__":
    write_all()
