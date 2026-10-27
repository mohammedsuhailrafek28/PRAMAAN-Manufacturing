"""PS10 lifecycle read model: one chronology and forward/backward traceability over the verified event history.

PURE functions of recorded events. This module computes no recall decision, no release eligibility and no trust: every statement it makes is
a RECORDED CLAIM, and each inspection carries an `assurance` block that says exactly what was and was not independently established.
Inputs are the native events of a verified ledger snapshot (optionally with the `repository` block the snapshot adds to each event).
"""
CATEGORY = {
    "MATERIAL_ALLOCATED": "MATERIAL", "BEARING_MANUFACTURED": "MATERIAL",
    "MACHINING_RECORDED": "MACHINING", "QUALITY_INSPECTION_RECORDED": "INSPECTION", "INSPECTION_RECORDED": "INSPECTION",
    "WORK_ORDER_OPENED": "WORK_ORDER", "WORK_ORDER_CLOSED": "WORK_ORDER",
    "COMPONENT_INSTALLED": "ASSEMBLY", "COMPONENT_REMOVED": "REWORK",
    "SLOT_STATE_VERIFIED": "OBSERVATION", "SLOT_LABEL_SCANNED": "OBSERVATION", "SLOT_ACCESS_EVIDENCE": "OBSERVATION",
    "CAPTURE_EXCEPTION_RAISED": "EXCEPTION", "CAPTURE_EXCEPTION_RESOLVED": "EXCEPTION",
    "MOTOR_SHIPPED": "SHIPMENT",
}
# Payload keys that name another event, with the relation they express.
REFERENCES = (("supersedesEventId", "CORRECTS", True), ("endsInstallEventId", "ENDS_INSTALL", False), ("materialEventId", "FROM_MATERIAL", False),
              ("manufacturingEventId", "FROM_MANUFACTURE", False), ("assemblyEventId", "SHIPS_ASSEMBLY", False), ("exceptionEventId", "RESOLVES", False),
              ("previousOperationEventId", "FOLLOWS_OPERATION", False))
NOT_ESTABLISHED = ("physical correctness of the part", "that the measurement or visual check took place as described", "release eligibility",
                   "recall-evaluator trust (inspection is not a recall verification source)")


def _order(e):
    return (e["occurredAt"], e["recordedAt"], e["sourceId"], e["sourceSeq"])


def references(e):
    """[(relation, eventId)] this event makes to other events."""
    out = []
    for key, relation, top in REFERENCES:
        ref = e.get(key) if top else e["payload"].get(key)
        if isinstance(ref, str) and ref:
            out.append((relation, ref))
    if e["eventType"] == "QUALITY_INSPECTION_RECORDED":
        out += [("INSPECTS", r) for r in e["payload"].get("subjectEventIds", [])]
    return out


def assurance(e, by_id):
    """What an inspection record does and does not establish. Never 'verified': the strongest statement is that a different actor and source recorded it."""
    if e["eventType"] != "QUALITY_INSPECTION_RECORDED":
        return None
    subjects = [by_id[r] for r in e["payload"]["subjectEventIds"] if r in by_id]
    same_actor = any(s["actorId"] == e["actorId"] for s in subjects)
    same_source = any(s["sourceId"] == e["sourceId"] for s in subjects)
    return dict(level="RECORDED_CLAIM_DIFFERENT_ACTOR_AND_SOURCE" if subjects and not same_actor and not same_source else "RECORDED_CLAIM_SAME_ACTOR_OR_SOURCE" if subjects else "RECORDED_CLAIM_SUBJECT_NOT_VISIBLE",
                recordedResult=e["payload"]["result"], independentlyVerified=False, timeSource=e["timeSource"], trustedTime=False,
                inspectorQualificationIsClaimed=True, notEstablished=list(NOT_ESTABLISHED))


def summary(e):
    p, k = e["payload"], e["eventType"]
    if k == "MACHINING_RECORDED":
        return f"{p['operation'].title().replace('_', ' ')} of {p['componentType'].lower().replace('_', ' ')} {p['componentId']} on {p['machineId']} (step {p['routingStepId']})"
    if k == "QUALITY_INSPECTION_RECORDED":
        return f"{p['inspectionType'].title().replace('_', ' ')} inspection recorded as {p['result']} under {p['protocolId']} (a claim)"
    if k == "MATERIAL_ALLOCATED":
        return f"Raw-material lot {p['rawMaterialLot']} allocated (supplier claim: {p['supplierName']})"
    if k == "BEARING_MANUFACTURED":
        return f"Bearing lot {p['lot']} manufactured from raw-material lot {p['rawMaterialLot']}"
    if k == "COMPONENT_INSTALLED":
        return f"Bearing lot {p['lot']} installed in {p['slot']}"
    if k == "COMPONENT_REMOVED":
        return f"Bearing lot {p['observedLot']} removed from {p['slot']}"
    if k == "MOTOR_SHIPPED":
        return f"Shipment {p['shipmentId']} recorded"
    if k == "WORK_ORDER_OPENED":
        return f"{p['orderType'].title()} work order {e['workOrderId']} opened"
    if k == "WORK_ORDER_CLOSED":
        return f"Work order {e['workOrderId']} closed ({p['disposition']})"
    return k.replace("_", " ").capitalize()


def chronology(events):
    """Every recorded event, ordered by (occurredAt, recordedAt, source, sequence), with its references and ledger coordinates."""
    by_id = {e["eventId"]: e for e in events}
    rows = []
    for e in sorted(events, key=_order):
        repo = e.get("repository") or {}
        row = dict(eventId=e["eventId"], eventType=e["eventType"], category=CATEGORY.get(e["eventType"], "OTHER"), occurredAt=e["occurredAt"], recordedAt=e["recordedAt"],
                   sourceId=e["sourceId"], sourceSeq=e["sourceSeq"], actorId=e["actorId"], timeSource=e["timeSource"], summary=summary(e) if e["eventType"] in CATEGORY else e["eventType"],
                   references=[dict(relation=r, eventId=t, present=t in by_id) for r, t in references(e)],
                   ledger=dict(eventChainHash=repo.get("eventChainHash"), captureSha256=repo.get("captureSha256")))
        if e["eventType"] == "MACHINING_RECORDED":
            row["component"] = dict(type=e["payload"]["componentType"], id=e["payload"]["componentId"])
            row["machineId"] = e["payload"]["machineId"]
        a = assurance(e, by_id)
        if a:
            row["assurance"] = a
        rows.append(row)
    return rows


def violations(events):
    """Chronology faults visible in the recorded history itself (never a verdict about the product)."""
    by_id = {e["eventId"]: e for e in events}
    out = []
    for e in events:
        for relation, ref in references(e):
            t = by_id.get(ref)
            if t is None:
                out.append(dict(eventId=e["eventId"], kind="REFERENCE_NOT_VISIBLE", relation=relation, target=ref))
            elif t["occurredAt"] > e["occurredAt"] and relation not in ("CORRECTS",):
                out.append(dict(eventId=e["eventId"], kind="REFERENCE_OCCURS_LATER", relation=relation, target=ref))
        if e["recordedAt"] < e["occurredAt"]:
            out.append(dict(eventId=e["eventId"], kind="RECORDED_BEFORE_OCCURRED"))
    return out


def backward(events):
    """Motor -> what is recorded about how it was made, ordered by process stage: shipment <- assembly <- bearings <- manufacture <- material,
    plus machined components with their inspections. Each node lists the recorded event ids it rests on."""
    by_id = {e["eventId"]: e for e in events}
    ended = {e["payload"].get("endsInstallEventId") for e in events if e["eventType"] == "COMPONENT_REMOVED"}
    corrected = {e["supersedesEventId"] for e in events if e["supersedesEventId"]}
    inspections = [e for e in events if e["eventType"] == "QUALITY_INSPECTION_RECORDED"]
    components = {}
    for e in sorted((x for x in events if x["eventType"] == "MACHINING_RECORDED"), key=_order):
        c = components.setdefault(e["payload"]["componentId"], dict(componentId=e["payload"]["componentId"], componentType=e["payload"]["componentType"], operations=[]))
        insp = [dict(eventId=i["eventId"], recordedResult=i["payload"]["result"], inspectionType=i["payload"]["inspectionType"], assurance=assurance(i, by_id)["level"])
                for i in sorted(inspections, key=_order) if e["eventId"] in i["payload"]["subjectEventIds"]]
        c["operations"].append(dict(eventId=e["eventId"], operation=e["payload"]["operation"], machineId=e["payload"]["machineId"], at=e["occurredAt"], inspections=insp))
    bearings = []
    for e in sorted((x for x in events if x["eventType"] == "COMPONENT_INSTALLED"), key=_order):
        p = e["payload"]
        made = by_id.get(p.get("manufacturingEventId"))
        alloc = by_id.get((made or {}).get("payload", {}).get("materialEventId"))
        bearings.append(dict(installEventId=e["eventId"], slot=p["slot"], lot=p["lot"], serial=p.get("serial"), state="SUPERSEDED" if e["eventId"] in corrected else "REMOVED" if e["eventId"] in ended else "RECORDED_INSTALLED",
                             manufactureEventId=made["eventId"] if made else None, rawMaterialLot=(made or {}).get("payload", {}).get("rawMaterialLot"),
                             materialEventId=alloc["eventId"] if alloc else None, supplierClaim=(alloc or {}).get("payload", {}).get("supplierName")))
    closed = next((e for e in events if e["eventType"] == "WORK_ORDER_CLOSED" and (e["workOrderId"] or "").startswith("BUILD-")), None)
    shipped = [e for e in sorted(events, key=_order) if e["eventType"] == "MOTOR_SHIPPED"]
    return dict(machinedComponents=list(components.values()), bearings=bearings, assemblyClosedEventId=closed["eventId"] if closed else None,
                shipments=[dict(eventId=s["eventId"], shipmentId=s["payload"]["shipmentId"], assemblyEventId=s["payload"]["assemblyEventId"], at=s["occurredAt"], historicalImport=_historical(s)) for s in shipped])


def _historical(e):
    """True for a shipment imported as history (it carries the marker the data integration layer writes into the hashed event); never an authorization."""
    return "pramaan-import-historical-shipment:v1" in (e.get("evidenceRefs") or [])


KEYS = {"bearingLot": lambda e: e["payload"].get("lot") if e["eventType"] == "BEARING_MANUFACTURED" else None,
        "rawMaterialLot": lambda e: e["payload"].get("rawMaterialLot") if e["eventType"] in ("MATERIAL_ALLOCATED", "BEARING_MANUFACTURED") else None,
        "machineId": lambda e: e["payload"].get("machineId") if e["eventType"] == "MACHINING_RECORDED" else None,
        "componentId": lambda e: e["payload"].get("componentId") if e["eventType"] == "MACHINING_RECORDED" else None}


def forward(histories, kind, value):
    """Key (bearing lot, raw-material lot, machine, machined component) -> every motor whose recorded history names it, with the matching events,
    the inspection claims about them and the shipments of that motor. `histories` is {motorSerial: [events]}."""
    if kind not in KEYS:
        raise ValueError("unknown trace key")
    out = []
    for motor in sorted(histories):
        events = histories[motor]
        hits = [e for e in events if KEYS[kind](e) == value]
        if not hits:
            continue
        by_id = {e["eventId"]: e for e in events}
        ids = {e["eventId"] for e in hits}
        machining_ids = {e["eventId"] for e in hits if e["eventType"] == "MACHINING_RECORDED"}
        insp = [dict(eventId=i["eventId"], recordedResult=i["payload"]["result"], assurance=assurance(i, by_id)["level"]) for i in events
                if i["eventType"] == "QUALITY_INSPECTION_RECORDED" and machining_ids & set(i["payload"]["subjectEventIds"])]
        out.append(dict(motorSerial=motor, matchedEventIds=sorted(ids), inspections=insp,
                        shipments=[dict(eventId=s["eventId"], shipmentId=s["payload"]["shipmentId"], at=s["occurredAt"], historicalImport=_historical(s)) for s in sorted(events, key=_order) if s["eventType"] == "MOTOR_SHIPPED"]))
    return dict(key=kind, value=value, motors=out, statement="Recorded associations only. Not a recall decision and not a clearance; see the motor's decision for the evaluator's finding.")


def view(events):
    return dict(chronology=chronology(events), backward=backward(events), violations=violations(events), eventCount=len(events))
