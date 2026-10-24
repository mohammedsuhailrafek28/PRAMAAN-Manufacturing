"""The declared space of hypothetical evidence operations, their admissibility rules and their materialisation.

An op is a plain dict. It carries the concrete event(s) it would add, so admissibility is checked on the same parameters that are
replayed. Nothing here is evidence: every op is a *hypothesis about evidence that might be obtainable*.

Op classes (each declares issuer, chronology, identity, obtainability):
  QA_VERIFY       independent SLOT_STATE_VERIFIED from a trusted verifier source, by an authorised actor independent of the slot's
                  record-makers, at/after "now"; needs physical access to the slot.
  RECOVER_RECORD  restores a record known to have existed (its source high-water mark proves it) with its original envelope
                  (id, source, sequence, timestamps, actor); only its content is hypothesised; needs the original storage.
  ARCHIVE_ACCESS  late capture of station access evidence retrieved from a fixture archive: occurredAt may precede now, but only
                  inside the work order's window, recordedAt is now, issuer must be an access-evidence source.
  INSPECT         INSPECTION_RECORDED by a qualified inspector against the recall's protocol, at/after now (P2 only).
  CORRECTION      superseding COMPONENT_INSTALLED from a mandatory-capture source at now (opens a capture session there).
  RESOLVE_EXC     clerical CAPTURE_EXCEPTION_RESOLVED. The evaluator accepts it from anyone; the admissibility rules do NOT
                  (an exception may only be closed together with an independent verification of the excepted slot).
"""
import copy

from scenarios import A, NOW, U

PART = "BR-6205"
PROTOCOL = "RC-009-DMG-01"
VERIFIER, VERIFIER_ACTOR, SUPERVISOR = "QA-02", "EMP-031", "EMP-070"
OFFSET = dict(QA_VERIFY=600, INSPECT=300, CORRECTION=60, RESOLVE_EXC=120, ARCHIVE_ACCESS=30)
MANDATORY = {"ASSY-01", "REWORK-03", "MES"}


def _ts(base, seconds):
    from datetime import datetime, timedelta
    return (datetime.strptime(base, "%Y-%m-%dT%H:%M:%SZ") + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _event(op_id, etype, src, occ, rec, actor, wo, payload, sup=None, refs=None):
    return dict(eventId="H-" + op_id.replace(":", "-"), eventType=etype, schemaVersion=1, sourceId=src, sourceSeq=None, motorSerial="M-042",
                workOrderId=wo, recallId=None, occurredAt=occ, timeSource="DEVICE_SYNCED", recordedAt=rec, actorId=actor,
                evidenceRefs=refs or [], supersedesEventId=sup, payload=payload)


def _session(src, now=NOW):
    return dict(sourceId=src, **{"from": _ts(now, -1800), "to": _ts(now, 3600)})


def _op(op_id, cls, target, hyp, events, sessions, text, addresses, explanation):
    return dict(id=op_id, cls=cls, target=target, hyp=hyp, events=events, sessions=sessions, text=text, addresses=addresses,
                explanation=explanation)


def catalog(sc, include_inadmissible=False):
    """All instantiations the scenario's declared facts make *obtainable*; optionally the inadmissible evaluator-only ops too."""
    f, case, out = sc["facts"], sc["case"], []
    universe = ["DE", "NDE"]
    for slot in universe:
        if f["slotAccessible"].get(slot):
            for hyp, lot in (("U", U), ("A", A)):
                oid = f"QA:{slot}:{hyp}"
                occ = _ts(NOW, OFFSET["QA_VERIFY"])
                e = _event(oid, "SLOT_STATE_VERIFIED", VERIFIER, occ, _ts(occ, 4), VERIFIER_ACTOR, None,
                           dict(componentType="BEARING", slot=slot, observedPart=PART, observedLot=lot, method="DISASSEMBLY_INSPECTION"),
                           refs=["EVID-" + oid])
                out.append(_op(oid, "QA_VERIFY", "verify:" + slot, hyp, [e], [_session(VERIFIER)],
                               f"Independent QA disassembly verification of the {slot} bearing (hypothesised lot {lot})",
                               dict(slots=[slot]), "needs physical access to the slot and an authorised verifier independent of the record-makers"))
    if f["lostRecoverable"]:
        for l in f["lostRecords"]:
            hyps = ([("OUT", dict(l["payload"], accessibleSlots=["DE"])), ("BOTH", dict(l["payload"], accessibleSlots=["DE", "NDE"]))]
                    if l["eventType"] == "SLOT_ACCESS_EVIDENCE" else
                    [("U", dict(l["payload"], **{("lot" if l["eventType"] == "COMPONENT_INSTALLED" else "observedLot"): U})),
                     ("A", dict(l["payload"], **{("lot" if l["eventType"] == "COMPONENT_INSTALLED" else "observedLot"): A}))])
            for hyp, payload in hyps:
                oid = f"REC:{l['eventId']}:{hyp}"
                e = _event(oid, l["eventType"], l["sourceId"], l["occurredAt"], l["recordedAt"], l["actorId"], l["workOrderId"], payload)
                e["eventId"], e["sourceSeq"] = l["eventId"], l["sourceSeq"]        # original envelope is restored verbatim
                out.append(_op(oid, "RECOVER_RECORD", "record:" + l["eventId"], hyp, [e], [],
                               f"Recover lost {l['eventType']} record {l['eventId']} ({l['sourceId']} seq {l['sourceSeq']}) from original device storage",
                               dict(slots=[payload.get("slot")] if payload.get("slot") else ["DE", "NDE"], sources=[l["sourceId"]]),
                               "needs the original device storage; content is hypothesised, the envelope is the known one"))
    if f["accessEvidenceArchive"]:
        wo = next(e for e in case["events"] if e["eventType"] == "COMPONENT_REMOVED")
        for hyp, acc in (("OUT", ["DE"]), ("BOTH", ["DE", "NDE"])):
            oid = f"ARC:{hyp}"
            occ = _ts(wo["occurredAt"], -600)
            e = _event(oid, "SLOT_ACCESS_EVIDENCE", VERIFIER, occ, _ts(NOW, OFFSET["ARCHIVE_ACCESS"]), VERIFIER_ACTOR, wo["workOrderId"],
                       dict(method="STATION_FIXTURE_RECORD", accessibleSlots=acc), refs=["ARCHIVE-" + oid])
            out.append(_op(oid, "ARCHIVE_ACCESS", "access:" + wo["workOrderId"], hyp, [e], [_session(VERIFIER)],
                           "Retrieve the station fixture archive record of which slots were accessible during the removal",
                           dict(slots=["DE", "NDE"]), "needs the fixture archive; occurredAt precedes now but stays inside the work-order window"))
    if f["inspectionPossible"]:
        for slot in universe:
            if f["slotAccessible"].get(slot):
                for hyp, res in (("PASS", "PASS"), ("FAIL", "FAIL")):
                    oid = f"INS:{slot}:{hyp}"
                    occ = _ts(NOW, OFFSET["INSPECT"])
                    e = _event(oid, "INSPECTION_RECORDED", VERIFIER, occ, _ts(occ, 4), VERIFIER_ACTOR, None,
                               dict(protocolId=PROTOCOL, scope=[slot], result=res, inspectorQualifiedFor=[PROTOCOL]), refs=["EVID-" + oid])
                    out.append(_op(oid, "INSPECT", "inspect:" + slot, hyp, [e], [_session(VERIFIER)],
                                   f"Qualified post-recall damage inspection of {slot} (hypothesised result {res})",
                                   dict(slots=[slot]), "needs physical access and an inspector qualified for the recall protocol"))
    if f["correctionPossible"]:
        for slot in universe:
            tgt = [e for e in case["events"] if e["eventType"] == "COMPONENT_INSTALLED" and e["payload"]["slot"] == slot and not e.get("supersedesEventId")]
            if not tgt:
                continue
            for hyp, lot in (("U", U), ("A", A)):
                oid = f"COR:{slot}:{hyp}"
                occ = _ts(NOW, OFFSET["CORRECTION"])
                e = _event(oid, "COMPONENT_INSTALLED", "REWORK-03", occ, _ts(occ, 4), "EMP-017", tgt[-1]["workOrderId"],
                           dict(componentType="BEARING", slot=slot, part=PART, lot=lot, identityGranularity="LOT"), sup=tgt[-1]["eventId"])
                out.append(_op(oid, "CORRECTION", "correct:" + slot, hyp, [e], [_session("REWORK-03")],
                               f"Superseding correction of the {slot} install record (hypothesised lot {lot})", dict(slots=[slot]),
                               "issued by a mandatory-capture source; opens a capture session there"))
    if include_inadmissible:
        for xid in f["exceptionIds"]:
            oid = f"EXC:{xid}"
            occ = _ts(NOW, OFFSET["RESOLVE_EXC"])
            e = _event(oid, "CAPTURE_EXCEPTION_RESOLVED", "MES", occ, _ts(occ, 4), SUPERVISOR, None, dict(exceptionEventId=xid))
            out.append(_op(oid, "RESOLVE_EXC", "exception:" + xid, "RESOLVED", [e], [],
                           f"Mark capture exception {xid} resolved", dict(slots=["DE", "NDE"]), "clerical closure without re-verification"))
    return out


# ---------------------------------------------------------------------------------------------------- admissibility
def _slot_actors(sc, slot):
    return {e["actorId"] for e in sc["case"]["events"] if e["payload"].get("slot") == slot}


def violations(op, sc):
    """Op-level admissibility violations (empty = admissible). Operates on the concrete event parameters."""
    v, f, cov = [], sc["facts"], None
    from sandbox import COVERAGE
    cov = COVERAGE
    trusted = set(cov["trustedVerifierSources"])
    attr = cov["slotAttribution"]
    lost = {l["eventId"]: l for l in f["lostRecords"]}
    for e in op["events"]:
        cls = op["cls"]
        if e["motorSerial"] != sc["case"]["events"][0]["motorSerial"]:
            v.append("WRONG_MOTOR")
        if e["recordedAt"] < e["occurredAt"]:
            v.append("RECORDED_BEFORE_OCCURRED")
        if e["payload"].get("slot") and e["payload"]["slot"] not in ("DE", "NDE"):
            v.append("UNKNOWN_SLOT")
        lot = e["payload"].get("observedLot") or e["payload"].get("lot")
        if lot is not None and lot not in (U, A):
            v.append("LOT_OUTSIDE_DECLARED_DOMAIN")
        if cls in ("QA_VERIFY", "INSPECT", "ARCHIVE_ACCESS"):
            if e["sourceId"] not in trusted:
                v.append("ISSUER_NOT_TRUSTED")
            if e["actorId"] not in attr["authorizedVerifierActors"]:
                v.append("ACTOR_NOT_AUTHORIZED")
            slot = e["payload"].get("slot") or (e["payload"].get("scope") or [None])[0]
            if slot and e["actorId"] in _slot_actors(sc, slot):
                v.append("ACTOR_NOT_INDEPENDENT")
            if not e["evidenceRefs"]:
                v.append("NO_EVIDENCE_REFERENCE")
        if cls in ("QA_VERIFY", "INSPECT", "CORRECTION"):
            if e["occurredAt"] < NOW:
                v.append("BACKDATED_NEW_EVIDENCE")
            slot = e["payload"].get("slot") or (e["payload"].get("scope") or [None])[0]
            if cls != "CORRECTION" and not f["slotAccessible"].get(slot):
                v.append("SLOT_NOT_ACCESSIBLE")
        if cls == "QA_VERIFY" and e["payload"].get("method") not in attr["approvedVerificationMethods"]:
            v.append("METHOD_NOT_APPROVED")
        if cls == "INSPECT" and e["payload"].get("protocolId") != PROTOCOL:
            v.append("WRONG_PROTOCOL")
        if cls == "RECOVER_RECORD":
            l = lost.get(e["eventId"])
            if not f["lostRecoverable"]:
                v.append("ORIGINAL_STORAGE_UNAVAILABLE")
            if l is None:
                v.append("NOT_A_KNOWN_LOST_RECORD")
            elif (l["sourceId"], l["sourceSeq"], l["occurredAt"], l["recordedAt"], l["actorId"]) != (
                    e["sourceId"], e["sourceSeq"], e["occurredAt"], e["recordedAt"], e["actorId"]):
                v.append("ENVELOPE_NOT_ORIGINAL")
        if cls == "ARCHIVE_ACCESS":
            if not f["accessEvidenceArchive"]:
                v.append("NO_ARCHIVE")
            rem = [x for x in sc["case"]["events"] if x["eventType"] == "COMPONENT_REMOVED"]
            wo = [x for x in sc["case"]["events"] if x["workOrderId"] == e["workOrderId"]]
            if not rem or not wo or e["occurredAt"] > rem[0]["occurredAt"] or e["occurredAt"] < min(x["occurredAt"] for x in wo):
                v.append("OUTSIDE_WORK_ORDER_WINDOW")
            if e["recordedAt"] < NOW:
                v.append("ARCHIVE_RECORDED_IN_PAST")
        if cls == "CORRECTION":
            if e["sourceId"] not in MANDATORY:
                v.append("CORRECTION_ISSUER_NOT_RECORD_SOURCE")
            if not f["correctionPossible"]:
                v.append("CORRECTION_NOT_OBTAINABLE")
        if cls == "RESOLVE_EXC":
            v.append("CLERICAL_EXCEPTION_CLOSURE_REQUIRES_REVERIFICATION")
    return sorted(set(v))


def set_violations(ops, sc):
    """Set-level rules: one hypothesis per target; dependency rules."""
    v, seen = [], {}
    for o in ops:
        if o["target"] in seen:
            v.append("CONTRADICTORY_HYPOTHESES:" + o["target"])
        seen[o["target"]] = o["id"]
    return v


# ---------------------------------------------------------------------------------------------------- materialisation
def apply_ops(sc, ops):
    """-> (case, watermark): the scenario with the ops' events and sessions added. Pure; the scenario is not modified."""
    case, wm = copy.deepcopy(sc["case"]), dict(sc["watermark"])
    added = [copy.deepcopy(e) for o in ops for e in o["events"]]
    sessions = {(s["sourceId"], s["from"], s["to"]) for s in case["captureCoverage"]["sessions"]}
    for o in ops:
        for s in o["sessions"]:
            if (s["sourceId"], s["from"], s["to"]) not in sessions:
                case["captureCoverage"]["sessions"].append(copy.deepcopy(s)); sessions.add((s["sourceId"], s["from"], s["to"]))
    top = {}
    for e in case["events"]:
        top[e["sourceId"]] = max(top.get(e["sourceId"], 0), e["sourceSeq"])
    for e in sorted(added, key=lambda e: (e["sourceSeq"] is None, e["recordedAt"], e["eventId"])):
        if e["sourceSeq"] is None:                    # new evidence takes the next free sequence number of its source
            top[e["sourceId"]] = max(top.get(e["sourceId"], 0), wm.get(e["sourceId"], 0)) + 1
            e["sourceSeq"] = top[e["sourceId"]]
        wm[e["sourceId"]] = max(wm.get(e["sourceId"], 0), e["sourceSeq"])
        case["events"].append(e)
    return case, wm
