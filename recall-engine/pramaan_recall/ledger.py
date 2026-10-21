"""Slot ledger: structural replay of component events into per-slot state.

Deliberately policy-free. It knows nothing about affected lots, recalls or
exposure; it only answers "what do the records say, how far can they be
trusted, and where do they contradict themselves or have holes".

Slot states: UNKNOWN (no usable evidence), EMPTY, OCCUPIED.

Slot attribution (opt-in: `attr` is the coverage policy's slot-attribution block;
None keeps the original semantics). Assurance of "which slot was this removal
from", weakest first:
  CLAIMED_SLOT        operator-selected position; clears nothing.
  OBSERVED_SLOT_LABEL provisioned motor+slot label scanned in the same motor/order/
                      capture session within the association window; clears nothing.
  CORROBORATED_SLOT   independent, authorized SLOT_STATE_VERIFIED using an approved
                      method, after the removal; the only thing that clears ambiguity.
"""
from datetime import datetime

HARD_CONFLICTS = {"DOUBLE_OCCUPANCY", "REMOVAL_OBSERVATION_MISMATCH",
                  "REMOVAL_LINK_MISMATCH", "REMOVAL_NOT_LINKED",
                  "REMOVAL_FROM_EMPTY", "VERIFIED_STATE_MISMATCH",
                  "REMOVAL_SLOT_LABEL_MISMATCH", "REMOVAL_SERIAL_IN_OTHER_SLOT"}
_TS = "%Y-%m-%dT%H:%M:%SZ"


def _secs(a, b):
    """Absolute seconds between two ISO timestamps; None if either is malformed."""
    try:
        return abs((datetime.strptime(a, _TS) - datetime.strptime(b, _TS)).total_seconds())
    except (TypeError, ValueError):
        return None


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
        self.claims = []              # operator-originated events a verifier must be independent of
        self.attributions = []        # one per removal (attribution mode only)
        self.untrusted_obs = []       # observations of this slot that were not trusted (v3 only)

    def note(self, e):
        self.events.append(e["eventId"])
        self.actors.add(e["actorId"])

    def claim(self, e):
        self.claims.append(dict(eventId=e["eventId"], source=e["sourceId"], actor=e["actorId"],
                                refs=set(e.get("evidenceRefs") or []), kind=e["eventType"],
                                at=e["occurredAt"], rec=e["recordedAt"], ts=e.get("timeSource")))

    @property
    def ambiguities(self):
        return [a for a in self.attributions if a["ambiguous"]]

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
        if any(not a["cleared"] for a in self.ambiguities):
            return "AMBIGUOUS_ATTRIBUTION"
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
    def __init__(self, by_id, superseded, mand, trusted_verifiers, wo, attr=None, sessions=(),
                 motor=None, track_untrusted=False):
        self.motor, self.track_untrusted = motor, track_untrusted
        self.unattributed_obs = []    # untrusted observations not tied to this motor / a slot
        self.by_id, self.superseded = by_id, superseded
        self.mand, self.verifiers, self.wo = mand, trusted_verifiers, wo
        self.attr, self.sessions = attr, list(sessions)
        self.active = []
        self.universe = set()         # every slot the motor is known to have
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
        s.claim(e)
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
        s.claim(e)
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
        if self.attr is not None:
            self._attribute(e, obs, s, conflict)
        s.removals.append(dict(eventId=e["eventId"], **obs))
        if not src_ok:
            s.trusted = False
        s.state, s.occupant, s.candidates, s.double = "EMPTY", None, [], False

    def verify(self, e):
        p = e["payload"]
        if self.track_untrusted and (not p.get("slot") or e.get("motorSerial") != self.motor):
            self.unattributed_obs.append(dict(
                eventId=e["eventId"], slot=p.get("slot"), motorSerial=e.get("motorSerial"),
                observed=dict(part=p.get("observedPart"), lot=p.get("observedLot"),
                              serial=p.get("observedSerial")),
                reason="NO_SLOT" if not p.get("slot") else "MOTOR_NOT_THIS_HISTORY"))
            return
        s = self.slot(p["slot"])
        obs = _occ(p, e, ("observedPart", "observedLot", "observedSerial"))
        v = dict(obs, at=e["occurredAt"], rec=e["recordedAt"], ts=e.get("timeSource"), actor=e["actorId"],
                 provisional=bool(p.get("provisional")),
                 trusted=(e["sourceId"] in self.verifiers
                          and e["actorId"] not in s.actors))
        v["trusted"] = bool(v["trusted"])
        if self.attr is not None:
            fails = self._independence_failures(e, s)
            if fails:
                v["trusted"], v["rejectedReasons"] = False, fails
            else:
                v["assurance"] = "CORROBORATED_SLOT"
        s.verifications.append(v)
        if not v["trusted"]:
            if self.track_untrusted:
                s.untrusted_obs.append(dict(
                    eventId=e["eventId"], at=v["at"], rec=v["rec"], ts=v["ts"],
                    observed=dict(part=v.get("part"), lot=v.get("lot"), serial=v.get("serial")),
                    reasons=v.get("rejectedReasons") or ["UNTRUSTED"], staleBy=None, resolvedBy=None))
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

    # -- slot attribution ------------------------------------------------
    @staticmethod
    def _occupants(t):
        if t.double:
            return list(t.candidates)
        return [t.occupant] if t.state == "OCCUPIED" and t.occupant else []

    def _independence_failures(self, e, s):
        """Why a trusted-source verification is not CORROBORATED_SLOT (empty = it is)."""
        a, p, fails = self.attr, e["payload"], []
        if e["sourceId"] not in self.verifiers:
            fails.append("SOURCE_NOT_TRUSTED")
        if e["actorId"] in s.actors:
            fails.append("ACTOR_NOT_INDEPENDENT")
        if p.get("method") not in a.get("approvedVerificationMethods", []):
            fails.append("METHOD_NOT_APPROVED")
        auth = a.get("authorizedVerifierActors")
        if auth is not None and e["actorId"] not in auth:
            fails.append("ACTOR_NOT_AUTHORIZED")
        if any(c["source"] == e["sourceId"] for c in s.claims):
            fails.append("SOURCE_NOT_INDEPENDENT")
        if set(e.get("evidenceRefs") or []) & {r for c in s.claims for r in c["refs"]}:
            fails.append("EVIDENCE_NOT_INDEPENDENT")
        if set(p.get("derivedFromEventIds") or []) & {c["eventId"] for c in s.claims}:
            fails.append("DERIVED_FROM_OPERATOR_CLAIM")
        return fails

    def _binding(self, label_id, motor, at):
        for b in self.attr.get("slotLabels", []):
            if b["labelId"] == label_id:
                ok = (b.get("motorSerial") == motor and b.get("status") == "ACTIVE"
                      and b.get("provisionedAt", "") <= at
                      and (b.get("revokedAt") is None or b["revokedAt"] > at))
                return b if ok else None
        return None

    def label(self, e):
        b = self._binding(e["payload"].get("labelId"), e["motorSerial"], e["occurredAt"])
        if b:
            s = self.slot(b["slot"])
            s.note(e)
            s.claim(e)

    def _same_session(self, a, b):
        for ss in self.sessions:
            if ss["sourceId"] == a["sourceId"] == b["sourceId"] and all(
                    ss["from"] <= x["occurredAt"] <= ss["to"] for x in (a, b)):
                return "OK" if ss.get("authenticated", True) is not False else "UNAUTHENTICATED_SESSION"
        return "DIFFERENT_SESSION"

    def _label_association(self, e):
        win = self.attr.get("labelAssociationWindowSeconds", 0)
        out = dict(slots=set(), accepted=[], rejected=[])
        for x in self.active:
            if x["eventType"] != "SLOT_LABEL_SCANNED" or x.get("workOrderId") != e.get("workOrderId") \
                    or x["motorSerial"] != e["motorSerial"]:
                continue
            why = None
            b = self._binding(x["payload"].get("labelId"), x["motorSerial"], x["occurredAt"])
            dt = _secs(x["occurredAt"], e["occurredAt"])
            if x["sourceId"] not in self.attr.get("labelScanSources", []):
                why = "SOURCE_NOT_LABEL_SCANNER"
            elif b is None:
                why = "LABEL_BINDING_INVALID"
            elif dt is None or dt > win:
                why = "OUTSIDE_ASSOCIATION_WINDOW"
            else:
                sess = self._same_session(x, e)
                why = None if sess == "OK" else sess
            if why:
                out["rejected"].append(dict(eventId=x["eventId"], reason=why))
            else:
                out["slots"].add(b["slot"])
                out["accepted"].append(dict(eventId=x["eventId"], labelId=b["labelId"],
                                            slot=b["slot"], deltaSeconds=dt))
        return out

    def _ruled_out(self, e, others):
        """Slots proven inaccessible by trustworthy station evidence. Absence of
        evidence, unknown state and coverage gaps never rule a slot out."""
        a = self.attr
        ev = [x for x in self.active if x["eventType"] == "SLOT_ACCESS_EVIDENCE"
              and x["sourceId"] in a.get("accessEvidenceSources", [])
              and x["payload"].get("method") in a.get("approvedAccessMethods", [])
              and e.get("workOrderId") and x.get("workOrderId") == e["workOrderId"]
              and x["occurredAt"] <= e["occurredAt"] and x["actorId"] != e["actorId"]]
        if not ev:
            return set(), None
        latest = max(ev, key=lambda x: (x["occurredAt"], x["recordedAt"]))
        acc = set(latest["payload"].get("accessibleSlots", []))
        return {n for n in others if n not in acc}, latest["eventId"]

    def _attribute(self, e, obs, s, conflict):
        """Record the assurance of one removal's slot attribution; flag ambiguity/conflict."""
        matches = {}
        if obs.get("lot") or obs.get("serial"):
            for name, t in self.slots.items():
                hit = [o["eventId"] for o in self._occupants(t) if same_item(o, obs)]
                if hit:
                    matches[name] = hit
        # A slot whose state is unknown cannot be ruled out as the real location.
        unknown = set()
        if self.attr.get("unknownSlotIsCandidate", True):
            unknown = {n for n in self.universe - {s.name}
                       if n not in self.slots or self.slots[n].state == "UNKNOWN"}
        out, access_ev = self._ruled_out(e, (set(matches) | unknown) - {s.name})
        cands = {n: h for n, h in matches.items() if n not in out}
        unknown -= out
        labels = self._label_association(e)
        if labels["slots"] - {s.name}:
            conflict("REMOVAL_SLOT_LABEL_MISMATCH", labelledSlots=sorted(labels["slots"]),
                     labelEventIds=[x["eventId"] for x in labels["accepted"]])
        if obs.get("serial"):
            for name, t in self.slots.items():
                for o in self._occupants(t):
                    if name != s.name and o.get("serial") == obs["serial"] and (
                            not o.get("part") or not obs.get("part") or o["part"] == obs["part"]):
                        conflict("REMOVAL_SERIAL_IN_OTHER_SLOT", otherSlot=name,
                                 installEventId=o["eventId"])
        rec = dict(
            removalEventId=e["eventId"], claimedSlot=s.name, at=e["occurredAt"],
            observed=dict(part=obs.get("part"), lot=obs.get("lot"), serial=obs.get("serial"),
                          granularity=obs.get("granularity")),
            assurance="OBSERVED_SLOT_LABEL" if labels["slots"] == {s.name} else "CLAIMED_SLOT",
            labelScans=labels["accepted"], rejectedLabelScans=labels["rejected"],
            candidates=[dict(slot=n, basis="RECORDED_OCCUPANT_MATCH", claimed=n == s.name,
                             supportingEventIds=h) for n, h in sorted(cands.items())]
            + [dict(slot=n, basis="STATE_UNKNOWN_NOT_RULED_OUT", claimed=False, supportingEventIds=[])
               for n in sorted(unknown)],
            ruledOutSlots=sorted(out), accessEvidenceEventId=access_ev if out else None,
            ambiguous=len(cands) >= 2 or (s.name in cands and bool(unknown)), cleared=False, clearedBy=None, unrulableAlternatives=[])
        rec["supportingEventIds"] = sorted(
            {e["eventId"], rec["accessEvidenceEventId"],
             *(i for c in rec["candidates"] for i in c["supportingEventIds"]),
             *(x["eventId"] for x in labels["accepted"])} - {None})
        s.attributions.append(rec)

    def run(self, active):
        self.active = active
        self.universe = {e["payload"]["slot"] for e in active if e["payload"].get("slot")}
        for e in active:
            if e["eventType"] == "WORK_ORDER_OPENED":
                self.universe |= {c["slot"] for c in e["payload"].get("expectedChanges", [])}
        if self.attr is not None:
            motors = {e["motorSerial"] for e in active}
            self.universe |= {b["slot"] for b in self.attr.get("slotLabels", []) if b.get("motorSerial") in motors}
        order = sorted(active, key=lambda e: (e["occurredAt"], e["recordedAt"],
                                              e["sourceId"], e["sourceSeq"]))
        h = dict(COMPONENT_INSTALLED=self.install, COMPONENT_REMOVED=self.remove,
                 SLOT_STATE_VERIFIED=self.verify)
        if self.attr is not None:
            h["SLOT_LABEL_SCANNED"] = self.label
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


def finalize_attribution(slots):
    """After gaps are applied: clear ambiguity only through CORROBORATED_SLOT, and
    list the alternatives that cannot be ruled out because their state is unknown
    or their coverage has a material gap (they stay possible, never evidence)."""
    for s in slots.values():
        for a in s.ambiguities:
            vs = [v for v in s.verifications if v["trusted"] and v["at"] > a["at"]]
            if vs:
                v = min(vs, key=lambda v: v["at"])
                a["cleared"], a["clearedBy"] = True, v["eventId"]
                a["supportingEventIds"] = sorted(set(a["supportingEventIds"]) | {v["eventId"]})
            named = {c["slot"] for c in a["candidates"]} | set(a["ruledOutSlots"])
            for name, t in sorted(slots.items()):
                if name in named:
                    continue
                if t.state == "UNKNOWN":
                    a["unrulableAlternatives"].append(dict(slot=name, reason="STATE_UNKNOWN"))
                elif any(g["materiality"] == "MATERIAL" for g in t.gaps):
                    a["unrulableAlternatives"].append(dict(slot=name, reason="UNRESOLVED_COVERAGE_GAP"))


def _delta(a, b):
    """Signed seconds a - b; None if either timestamp is malformed."""
    try:
        return (datetime.strptime(a, _TS) - datetime.strptime(b, _TS)).total_seconds()
    except (TypeError, ValueError):
        return None


def clearly_after(attr, x, o):
    """Is x certainly later than o? Requires both orderings (occurredAt beyond the clock-skew
    margin AND recordedAt) and clocks we trust for both events. Anything less is 'not
    provably later', which keeps a risk open rather than closing it."""
    skew, trusted = attr.get("observationClockSkewSeconds"), attr.get("trustedTimeSources", [])
    if skew is None or x["ts"] not in trusted or o["ts"] not in trusted:
        return False
    d = _delta(x["at"], o["at"])
    return d is not None and d > skew and x["rec"] > o["rec"]


def finalize_observations(slots, attr):
    """Mark each untrusted observation stale (a later install replaced the contents) or
    resolved (a later CORROBORATED_SLOT verification), judged conservatively."""
    for s in slots.values():
        for o in s.untrusted_obs:
            inst = [c for c in s.claims if c["kind"] == "COMPONENT_INSTALLED" and clearly_after(attr, c, o)]
            ver = [v for v in s.verifications if v["trusted"] and clearly_after(attr, v, o)]
            if inst:
                o["staleBy"] = min(inst, key=lambda c: c["at"])["eventId"]
            if ver:
                o["resolvedBy"] = min(ver, key=lambda v: v["at"])["eventId"]
