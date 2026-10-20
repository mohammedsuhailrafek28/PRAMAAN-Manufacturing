"""Slot ledger: structural replay of component events into per-slot state.

Deliberately policy-free. It knows nothing about affected lots, recalls or
exposure; it only answers "what do the records say, how far can they be
trusted, and where do they contradict themselves or have holes".

Slot states: UNKNOWN (no usable evidence), EMPTY, OCCUPIED.
"""

HARD_CONFLICTS = {"DOUBLE_OCCUPANCY", "REMOVAL_OBSERVATION_MISMATCH",
                  "REMOVAL_LINK_MISMATCH", "REMOVAL_NOT_LINKED",
                  "REMOVAL_FROM_EMPTY", "VERIFIED_STATE_MISMATCH"}


class Slot:
    def __init__(self, name):
        self.name = name
        self.state = "UNKNOWN"
        self.occupant = None          # per records
        self.candidates = []          # occupants when records double-occupy
        self.double = False
        self.trusted = False          # lineage anchored in baseline/verification
        self.baseline = "UNKNOWN"
        self.exposures = []           # every affected-lot-capable sighting
        self.removals = []
        self.conflicts = []
        self.late_claims = []
        self.verifications = []
        self.verified = None          # latest trusted verification, still current
        self.gaps = []
        self.events = []              # record-event ids touching this slot
        self.actors = set()

    def note(self, e):
        self.events.append(e["eventId"])
        self.actors.add(e["actorId"])

    # -- views -----------------------------------------------------------
    def record_lot(self):
        if self.state == "OCCUPIED" and not self.double and self.occupant:
            return self.occupant["lot"]
        return None

    def reconciliation(self):
        if self.conflicts:
            return "CONFLICT"
        if any(g["materiality"] == "MATERIAL" for g in self.gaps):
            return "CAPTURE_GAP"
        if not self.trusted:
            return "INSUFFICIENT_EVIDENCE"
        return "CLEAN"

    def granularity(self):
        for o in (self.occupant, *(r for r in reversed(self.removals))):
            if o and o.get("granularity"):
                return o["granularity"]
        return "UNKNOWN"


def _occ(p, e, keys=("part", "lot", "serial")):
    return dict(part=p.get(keys[0]), lot=p.get(keys[1]), serial=p.get(keys[2]),
                granularity=p.get("identityGranularity", "LOT"),
                eventId=e["eventId"], source=e["sourceId"], trusted=False)


def same_item(a, b):
    """Do two sightings denote the same physical item at their granularity?"""
    if a.get("part") and b.get("part") and a["part"] != b["part"]:
        return False
    if "SERIAL" in (a.get("granularity"), b.get("granularity")):
        return bool(a.get("serial")) and a.get("serial") == b.get("serial")
    return a.get("lot") == b.get("lot")


class Replay:
    def __init__(self, by_id, superseded, mand, trusted_verifiers, wo):
        self.by_id, self.superseded = by_id, superseded
        self.mand, self.verifiers, self.wo = mand, trusted_verifiers, wo
        self.slots = {}

    def slot(self, name):
        if name not in self.slots:
            self.slots[name] = Slot(name)
        return self.slots[name]

    def canon(self, eid):
        while eid in self.superseded:
            eid = self.superseded[eid]
        return eid

    def _is_baseline(self, e):
        w = self.wo.get(e.get("workOrderId"))
        return bool(w and w["orderType"] == "BUILD" and w["status"] == "CLOSED"
                    and w["disposition"] == "COMPLETED")

    # -- handlers --------------------------------------------------------
    def install(self, e):
        p, s = e["payload"], self.slot(e["payload"]["slot"])
        src_ok = e["sourceId"] in self.mand["COMPONENT_INSTALLED"]
        occ = _occ(p, e)
        s.note(e)
        s.verified = None
        s.exposures.append(dict(kind="INSTALL", eventId=e["eventId"],
                                trusted=src_ok, **{k: occ[k] for k in
                                ("part", "lot", "serial", "granularity")}))
        trusted_before = s.trusted
        if s.state == "OCCUPIED":
            s.conflicts.append(dict(kind="DOUBLE_OCCUPANCY", at=e["occurredAt"],
                                    occupiedBy=s.occupant["eventId"] if s.occupant else None,
                                    candidateEventId=e["eventId"]))
            s.double = True
            occ["trusted"] = False
            s.candidates.append(occ)
            return
        if s.state == "UNKNOWN":
            if src_ok and self._is_baseline(e):
                s.trusted, s.baseline = True, "AS_BUILT_VALIDATED"
            else:
                s.trusted = False
        if not src_ok:
            s.trusted = False
        occ["trusted"] = s.trusted
        s.state, s.occupant, s.candidates = "OCCUPIED", occ, [occ]
        tgt = e.get("supersedesEventId")
        if tgt in self.by_id and self.by_id[tgt]["eventType"] == "COMPONENT_INSTALLED":
            # Every correction is a claim until independently verified, whatever its
            # source: a record rewritten after the fact must not quietly clear a hold.
            old = self.by_id[tgt]["payload"]
            c = dict(kind="LATE_CORRECTION", at=e["occurredAt"],
                     supersededEventId=tgt, correctionEventId=e["eventId"])
            s.conflicts.append(c)
            s.late_claims.append(dict(
                correctionEventId=e["eventId"], supersededEventId=tgt,
                claim=occ, superseded=_occ(old, self.by_id[tgt]),
                trustedBefore=trusted_before, corroboratedBy=None, conflict=c))

    def remove(self, e):
        p, s = e["payload"], self.slot(e["payload"]["slot"])
        src_ok = e["sourceId"] in self.mand["COMPONENT_REMOVED"]
        obs = dict(part=p.get("observedPart"), lot=p.get("observedLot"),
                   serial=p.get("observedSerial"),
                   granularity=p.get("identityGranularity", "LOT"))
        s.note(e)
        s.verified = None
        s.exposures.append(dict(kind="REMOVAL_OBSERVED", eventId=e["eventId"],
                                trusted=src_ok, **obs))
        ends = p.get("endsInstallEventId")
        at = e["occurredAt"]

        def conflict(kind, **kw):
            s.conflicts.append(dict(kind=kind, at=at, removalEventId=e["eventId"], **kw))

        if s.state == "OCCUPIED" and not s.double:
            occ = s.occupant
            if ends is None:
                conflict("REMOVAL_NOT_LINKED", occupiedBy=occ["eventId"])
            elif self.canon(ends) != self.canon(occ["eventId"]):
                conflict("REMOVAL_LINK_MISMATCH", occupiedBy=occ["eventId"], endsInstallEventId=ends)
            if not same_item(occ, obs):
                conflict("REMOVAL_OBSERVATION_MISMATCH", occupiedBy=occ["eventId"],
                         recordedLot=occ["lot"], observedLot=obs["lot"])
        elif s.state == "EMPTY":
            conflict("REMOVAL_FROM_EMPTY")
        elif s.state == "UNKNOWN" and ends is not None and ends not in self.by_id:
            conflict("REMOVAL_LINK_MISMATCH", endsInstallEventId=ends)
        s.removals.append(dict(eventId=e["eventId"], **obs))
        if not src_ok:
            s.trusted = False
        s.state, s.occupant, s.candidates, s.double = "EMPTY", None, [], False

    def verify(self, e):
        p, s = e["payload"], self.slot(e["payload"]["slot"])
        obs = _occ(p, e, ("observedPart", "observedLot", "observedSerial"))
        v = dict(obs, at=e["occurredAt"], actor=e["actorId"],
                 provisional=bool(p.get("provisional")),
                 trusted=(e["sourceId"] in self.verifiers
                          and e["actorId"] not in s.actors))
        v["trusted"] = bool(v["trusted"])
        s.verifications.append(v)
        if not v["trusted"]:
            return
        s.note(e)
        cur = s.occupant if (s.state == "OCCUPIED" and not s.double) else None
        if s.state == "UNKNOWN":
            s.state, s.occupant, s.candidates = "OCCUPIED", dict(obs, trusted=True), []
        elif cur is None or not same_item(cur, obs):
            s.conflicts.append(dict(kind="VERIFIED_STATE_MISMATCH", at=v["at"],
                                    verificationEventId=e["eventId"],
                                    recordedLot=s.record_lot(), observedLot=obs["lot"]))
        for lc in s.late_claims:
            if same_item(lc["claim"], obs):
                lc["corroboratedBy"] = e["eventId"]
                lc["conflict"]["corroboratedByEventId"] = e["eventId"]
        s.trusted, s.verified = True, v

    def run(self, active):
        order = sorted(active, key=lambda e: (e["occurredAt"], e["recordedAt"],
                                              e["sourceId"], e["sourceSeq"]))
        h = dict(COMPONENT_INSTALLED=self.install, COMPONENT_REMOVED=self.remove,
                 SLOT_STATE_VERIFIED=self.verify)
        for e in order:
            fn = h.get(e["eventType"])
            if fn:
                fn(e)
        # Superseded evidence leaves the replay but not the exposure history.
        for old_id in self.superseded:
            e = self.by_id[old_id]
            p = e["payload"]
            if e["eventType"] == "COMPONENT_INSTALLED":
                x = dict(part=p.get("part"), lot=p.get("lot"), serial=p.get("serial"),
                         trusted=e["sourceId"] in self.mand["COMPONENT_INSTALLED"])
            elif e["eventType"] == "COMPONENT_REMOVED":
                x = dict(part=p.get("observedPart"), lot=p.get("observedLot"),
                         serial=p.get("observedSerial"),
                         trusted=e["sourceId"] in self.mand["COMPONENT_REMOVED"])
            else:
                continue
            self.slot(p["slot"]).exposures.append(dict(
                x, kind="SUPERSEDED_" + e["eventType"], eventId=old_id,
                granularity=p.get("identityGranularity", "LOT")))


def apply_gaps(slots, outages, exceptions, issues, wo_info, by_id):
    """Attach capture gaps to slots and bound them by trusted verification.

    A trusted, independent SLOT_STATE_VERIFIED at/after a gap's end
    re-establishes the slot's *state*. It does not recover *history*; the
    policy layer decides whether that distinction matters (P2).
    """
    def bound(s, t_end):
        vs = [v for v in s.verifications if v["trusted"] and v["at"] >= t_end]
        return min(vs, key=lambda v: v["at"])["eventId"] if vs else None

    for s in slots.values():
        for o in outages:
            g = dict(kind="SOURCE_OUTAGE", sourceId=o["sourceId"], **{"from": o["from"], "to": o["to"]})
            b = bound(s, o["to"])
            g.update(materiality="BOUNDED" if b else "MATERIAL", boundedByEventId=b)
            s.gaps.append(g)
        for x in exceptions:
            sc = x["payload"].get("scope", {}).get("slots")
            if sc is not None and s.name not in sc:
                continue
            b = bound(s, x["occurredAt"])
            s.gaps.append(dict(kind="UNRESOLVED_EXCEPTION", eventId=x["eventId"],
                               materiality="BOUNDED" if b else "MATERIAL", boundedByEventId=b))
        for i in issues:
            s.gaps.append(dict(kind=i["kind"], detail=i["detail"], materiality="MATERIAL",
                               eventId=i.get("eventId"), unboundable=True))
        if any(c["kind"] in HARD_CONFLICTS for c in s.conflicts):
            continue  # a hard record conflict subsumes unmet obligations on that slot
        for w in wo_info["workOrders"].values():
            for ob in w["obligations"]:
                if ob["slot"] == s.name and ob["status"] != "MET":
                    t_end = w["closedAt"]
                    b = bound(s, t_end) if t_end else None
                    s.gaps.append(dict(kind="WORK_ORDER_OBLIGATION_UNMET",
                                       workOrderId=w["workOrderId"], action=ob["action"],
                                       materiality="BOUNDED" if b else "MATERIAL",
                                       boundedByEventId=b))
        for eid in wo_info["orphanEventIds"]:
            e = by_id[eid]
            if e["payload"].get("slot") == s.name:
                b = bound(s, e["occurredAt"])
                s.gaps.append(dict(kind="WORK_ORDER_MISSING", eventId=eid,
                                   materiality="BOUNDED" if b else "MATERIAL",
                                   boundedByEventId=b))
