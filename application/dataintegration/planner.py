"""Relationship validation and import planning: which canonical records become ledger events, which stay staged, which are held and why.

The planner is a PURE function of (parsed files, current ledger content, optional staging history, options). It never writes. Preview shows its result;
import executes exactly that result, so preview and import cannot disagree.

Rules that matter for safety:
  * Lot identity is resolved by the existing registry exactly (declared alias allowed); a look-alike string is never normalised into a registered lot.
  * A record whose upstream, order, identity, time order or content is missing/contradictory is UNRESOLVED and writes nothing.
  * A work order is captured as a whole: if one of its records cannot be accepted, none of its records are written (no half-built, 'interrupted' ledger state
    manufactured by a data defect).
  * Nothing here sets, infers or clears a verification, eligibility or recall decision. Quality and SCADA records are staged claims only.
"""
from dataclasses import dataclass, field
from typing import Optional

from ..service import PART, ROLES
from .canonical import CAPTURABLE, RANK, CanonicalEvent, Kind
from .capture import DEFAULT_CLOCK, DEFAULT_WINDOW, dry_run_problem, event_id, import_ref, parse_ref, session_window, time_problem
from .ingest import find_duplicates
from .mapping import Step
from .models import FileResult, Issue, RecordResult

CAP_KINDS = {Kind.BEARING_LOT_ISSUED, Kind.WORK_ORDER_OPENED, Kind.COMPONENT_INSTALLED, Kind.COMPONENT_REMOVED, Kind.WORK_ORDER_CLOSED, Kind.SHIPMENT_DISPATCHED}
EVENTS_PER_RECORD = {Kind.BEARING_LOT_ISSUED: 2, Kind.WORK_ORDER_OPENED: 1, Kind.COMPONENT_INSTALLED: 1, Kind.COMPONENT_REMOVED: 1, Kind.WORK_ORDER_CLOSED: 1, Kind.SHIPMENT_DISPATCHED: 1}
MES_KINDS = {Kind.WORK_ORDER_OPENED, Kind.COMPONENT_INSTALLED, Kind.COMPONENT_REMOVED, Kind.WORK_ORDER_CLOSED}


@dataclass
class Options:
    create_units: bool = False                 # register unknown motor serials named by capturable records (existing Manufacturing.create_unit)
    historical_shipments: bool = False         # allow logistics records to become MOTOR_SHIPPED history


@dataclass
class Planned:
    """One ledger event the import will write."""
    motor: str
    kind: str
    role: str
    payload: dict
    work_order: Optional[str]
    occurred: str
    event_id: str
    canonical_id: str
    content_sha256: str
    sort: tuple


@dataclass
class Decision:
    outcome: str
    disposition: str
    reason: Optional[str] = None
    issues: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    events: list = field(default_factory=list)


@dataclass
class Plan:
    files: list
    creates: list = field(default_factory=list)
    events: list = field(default_factory=list)              # in execution order
    options: Optional[Options] = None


# ------------------------------------------------------------------------------------------------------------------------------------ ledger view
class World:
    """Read-only view of the ledger (and optionally the staging history). `app=None` is an empty ledger (preview before any ledger exists)."""

    def __init__(self, registry, app=None, staging=None):
        self.registry, self.app, self.staging = registry, app, staging
        self._events, self._wm = {}, {}
        self._units = {r[0] for r in app.db.execute("SELECT serial FROM app_units")} if app else set()

    def clock(self):
        return self.app.clock() if self.app else DEFAULT_CLOCK

    def window(self, motor, role):
        """The capture session window of the motor's source: the ledger's own configuration, or the one `create_unit` will register for a new unit."""
        if motor not in self._units:
            return DEFAULT_WINDOW
        return session_window(self.app.ledger._config(motor), self.app.source(role, motor)) or ("9", "0")

    def unit_exists(self, motor):
        return motor in self._units

    def events(self, motor):
        if motor not in self._units:
            return []
        if motor not in self._events:
            self._events[motor] = self.app.events(motor)
        return self._events[motor]

    def next_seq(self, motor, role):
        if motor not in self._units:
            return 1
        if motor not in self._wm:
            self._wm[motor] = self.app.ledger.watermark(motor)
        return self._wm[motor][self.app.source(role, motor)] + 1

    def imported(self, motor):
        """{canonicalId: (content16, [ledger event ids])} for events this layer wrote earlier (from the hashed evidenceRefs)."""
        out = {}
        for e in self.events(motor):
            for ref in e.get("evidenceRefs", []):
                p = parse_ref(ref)
                if p:
                    cid, c16 = out.setdefault(p[0], (p[1], []))
                    out[p[0]][1].append(e["eventId"])
        return out

    def motors_for_work_order(self, wo):
        if not self.app:
            return set()
        return {r[0] for r in self.app.db.execute("SELECT DISTINCT motor FROM events WHERE json_extract(native,'$.workOrderId')=?", (wo,))}

    def quality(self, motor):
        return self.staging.accepted_quality(motor) if self.staging else []


# ------------------------------------------------------------------------------------------------------------------------------------ per-motor simulation
class Sim:
    """What the ledger will say about one motor as planned events are added: work orders, bearing occupants, manufacture records, shipment."""

    def __init__(self, motor, world):
        self.motor, self.world = motor, world
        self.seq = {role: world.next_seq(motor, role) for role in ROLES}
        self.wos, self.occupant, self.history, self.mfg, self.shipped = {}, {}, [], [], []
        self.planned_any = False
        for e in world.events(motor):
            self._ledger_event(e)

    def _ledger_event(self, e):
        p, k = e["payload"], e["eventType"]
        if k == "WORK_ORDER_OPENED":
            self.wos[e["workOrderId"]] = dict(type=p["orderType"], open_at=e["occurredAt"], closed=False, close_at=None, close_id=None, disposition=None,
                                              expected={c["slot"] for c in p["expectedChanges"]}, installed=set(), removed=set(), open_id=e["eventId"], last=e["occurredAt"])
        elif k == "COMPONENT_INSTALLED":
            self.occupant[p["slot"]] = dict(lot=p["lot"], serial=p.get("serial"), install_id=e["eventId"])
            self.history.append((p["slot"], p["lot"], p.get("serial")))
            wo = self.wos.get(e["workOrderId"])
            if wo:
                wo["installed"].add(p["slot"]); wo["last"] = max(wo["last"], e["occurredAt"])
            for m in self.mfg:
                if m["eventId"] == p.get("manufacturingEventId"):
                    m["used"] = True
        elif k == "COMPONENT_REMOVED":
            self.occupant = {s: o for s, o in self.occupant.items() if o["install_id"] != p.get("endsInstallEventId")}
            wo = self.wos.get(e["workOrderId"])
            if wo:
                wo["removed"].add(p["slot"]); wo["last"] = max(wo["last"], e["occurredAt"])
        elif k == "WORK_ORDER_CLOSED":
            wo = self.wos.get(e["workOrderId"])
            if wo:
                wo.update(closed=True, close_at=e["occurredAt"], close_id=e["eventId"], disposition=p["disposition"])
        elif k == "BEARING_MANUFACTURED":
            self.mfg.append(dict(lot=p["lot"], serial=p.get("serial"), eventId=e["eventId"], occurred=e["occurredAt"], used=False, cid=None, slot=None))
        elif k == "MOTOR_SHIPPED":
            self.shipped.append(dict(shipmentId=p["shipmentId"], at=e["occurredAt"]))

    def take(self, role):
        n = self.seq[role]
        self.seq[role] += 1
        return n


def _unresolved(code, message, related=None, c=None):
    return Decision("UNRESOLVED", "UNRESOLVED_" + code, message, [Issue(code=code, message=message, related=related)])


def _accepted(disposition, issues=(), steps=(), events=()):
    return Decision("ACCEPTED", disposition, None, list(issues), list(steps), list(events))


def _warn(code, message, related=None):
    return Issue(code=code, severity="WARNING", message=message, related=related)


# ------------------------------------------------------------------------------------------------------------------------------------ evaluation
def evaluate_motor(motor, cands, world, opts, held):
    """-> {canonicalId: Decision} for the motor's live records. `held` = {workOrderId: (source record id that blocks the group, canonical ids acceptable on their own that are held with it, {canonical id: its own unresolved decision})}."""
    sim = Sim(motor, world)
    reg = world.registry
    out: dict[str, Decision] = {}
    by_kind = lambda *kinds: sorted((c for c in cands if c.canonical.kind in kinds), key=lambda c: (c.canonical.occurredAt, RANK[c.canonical.kind], c.canonical.sourceRecordId))
    exists = lambda: world.unit_exists(motor) or sim.planned_any

    def resolve(c, raw):
        res = reg.resolve(raw, at=c.canonical.occurredAt, part=PART)
        return res

    def plan_events(c, specs):
        """specs = [(kind, role, payload, work_order)] -> list[Planned] or problem string. Commits sequence numbers only when every event passes the dry run."""
        seq, planned = dict(sim.seq), []
        for kind, role, payload, wo in specs:
            n = seq[role]; seq[role] += 1
            problem = dry_run_problem(motor, kind, role, payload, n, c.canonical.occurredAt, work_order=wo, evidence=[import_ref(c.canonical.canonicalId, c.canonical.contentSha256)],
                                      clock=world.clock(), window=world.window(motor, role))
            if problem:
                return f"{kind}: {problem}"
            planned.append(Planned(motor, kind, role, payload, wo, c.canonical.occurredAt, event_id(motor, role, n), c.canonical.canonicalId, c.canonical.contentSha256,
                                   (c.canonical.occurredAt, RANK[c.canonical.kind], c.canonical.sourceRecordId)))
        sim.seq = seq
        sim.planned_any = True
        return planned

    def unknown_motor(c):
        if not exists() and not opts.create_units:
            return _unresolved("UNKNOWN_MOTOR", f"motor {motor} is not registered in the ledger and unit creation was not enabled for this import")

    # -- pairing pre-pass: an ERP issue and an MES install for the same motor position that name different lots contradict each other
    contradict: dict[str, list[str]] = {}
    for slot in ("DE", "NDE"):
        E = [c for c in by_kind(Kind.BEARING_LOT_ISSUED) if c.canonical.attributes["slot"] == slot]
        I = [c for c in by_kind(Kind.COMPONENT_INSTALLED) if c.canonical.attributes["slot"] == slot]
        lotof = lambda c: (lambda r: r.canonical if r.ok else None)(resolve(c, c.canonical.attributes["lot"]))
        el = {lotof(c) for c in E} - {None}
        il = {lotof(c) for c in I} - {None}
        if el and il:
            for c in E:
                if lotof(c) and lotof(c) not in il:
                    contradict[c.canonical.canonicalId] = [i.canonical.sourceRecordId for i in I]
            for c in I:
                if lotof(c) and lotof(c) not in el:
                    contradict[c.canonical.canonicalId] = [e.canonical.sourceRecordId for e in E]

    def hold(c):
        wo = c.canonical.attributes.get("workOrderId")
        h = held.get(wo)
        if h and c.canonical.canonicalId in h[2]:
            return h[2][c.canonical.canonicalId]                      # unresolved on its own account: keep its own reason
        if h and c.canonical.canonicalId in h[1]:
            return _unresolved("WORK_ORDER_GROUP_HELD", f"work order {wo} is held as a whole because record {h[0]} in it cannot be accepted; nothing of it is written", h[0])

    # -- pass 1: ERP lot issues
    for c in by_kind(Kind.BEARING_LOT_ISSUED):
        a, cid = c.canonical.attributes, c.canonical.canonicalId
        d = unknown_motor(c)
        if not d:
            res = resolve(c, a["lot"])
            steps = [Step(field="lot", step="registry_resolve", before=a["lot"], after=res.canonical)] if res.ok and res.canonical != a["lot"] else []
            if not res.ok:
                d = _unresolved("UNRESOLVED_LOT", f"lot {a['lot']!r}: identity not established ({res.status}{': ' + res.detail if res.detail else ''}){' - resembles ' + ', '.join(res.resembles) if res.resembles else ''}")
            elif (a["rawMaterialLot"], a["supplierId"]) != (res.entry["rawMaterialLot"], res.entry["supplierId"]):
                d = _unresolved("CONTRADICTS_REGISTRY", f"ERP says raw lot {a['rawMaterialLot']} / supplier {a['supplierId']} but the lot registry declares "
                                                        f"{res.entry['rawMaterialLot']} / {res.entry['supplierId']} for {res.canonical}")
            elif cid in contradict:
                d = _unresolved("CONTRADICTORY_LOT", f"ERP issued {res.canonical} to {a['slot']} but MES record(s) {', '.join(contradict[cid])} installed a different lot there", contradict[cid][0])
            elif a.get("serial") and any(m["serial"] == a["serial"] and m["lot"] == res.canonical and not m["used"] for m in sim.mfg):
                d = _unresolved("DUPLICATE_OF_LEDGER_RECORD", f"an unused manufacture record for serial {a['serial']} already exists in the ledger for this motor")
            else:
                lot, ser = res.canonical, a.get("serial")
                material = dict(rawMaterialLot=a["rawMaterialLot"], supplierId=a["supplierId"], supplierName=a["supplierName"])
                seq0 = sim.seq["MATERIAL"]
                mid = event_id(motor, "MATERIAL", seq0)
                evs = plan_events(c, [("MATERIAL_ALLOCATED", "MATERIAL", material, None),
                                      ("BEARING_MANUFACTURED", "MATERIAL", dict(rawMaterialLot=a["rawMaterialLot"], supplierId=a["supplierId"], part=PART, lot=lot, serial=ser, materialEventId=mid), None)])
                if isinstance(evs, str):
                    d = _unresolved("PROFILE_REJECTED", evs)
                else:
                    sim.mfg.append(dict(lot=lot, serial=ser, eventId=evs[1].event_id, occurred=c.canonical.occurredAt, used=False, cid=cid, slot=a["slot"]))
                    d = _accepted("CAPTURE", steps=steps, events=evs)
        out[cid] = d

    # -- pass 2: MES work orders, installs, removals, closes
    for c in by_kind(*MES_KINDS):
        a, cid, k = c.canonical.attributes, c.canonical.canonicalId, c.canonical.kind
        d = hold(c) or unknown_motor(c)
        wo_id = a["workOrderId"]
        wo = sim.wos.get(wo_id)
        t = c.canonical.occurredAt
        if not d and k is Kind.WORK_ORDER_OPENED:
            if wo:
                d = _unresolved("WORK_ORDER_ID_REUSED", f"work order {wo_id} already exists for {motor}")
            elif any(not w["closed"] for w in sim.wos.values()):
                d = _unresolved("OVERLAPPING_WORK_ORDER", "another work order of this motor is still open; a motor can have one open order at a time")
            elif a["orderType"] == "BUILD" and any(w["type"] == "BUILD" for w in sim.wos.values()):
                d = _unresolved("BUILD_ALREADY_RECORDED", f"{motor} already has a build order; further changes need a rework order")
            elif a["orderType"] == "REWORK" and not any(w["type"] == "BUILD" and w["closed"] and w["disposition"] == "COMPLETED" for w in sim.wos.values()):
                d = _unresolved("REWORK_WITHOUT_BUILD", "rework order for a motor without a completed build order")
            elif any(w["last"] > t or (w["close_at"] or "") > t for w in sim.wos.values()):
                d = _unresolved("TIME_ORDER", "order opens before the previous order's last recorded event")
            else:
                act = "INSTALL" if a["orderType"] == "BUILD" else "REPLACE"
                evs = plan_events(c, [("WORK_ORDER_OPENED", "MES", dict(orderType=a["orderType"], expectedChanges=[dict(slot=s, action=act) for s in a["expectedSlots"]]), wo_id)])
                if isinstance(evs, str):
                    d = _unresolved("PROFILE_REJECTED", evs)
                else:
                    sim.wos[wo_id] = dict(type=a["orderType"], open_at=t, closed=False, close_at=None, close_id=None, disposition=None, expected=set(a["expectedSlots"]),
                                          installed=set(), removed=set(), open_id=evs[0].event_id, last=t)
                    d = _accepted("CAPTURE", events=evs)
        elif not d and wo is None:
            d = _unresolved("MISSING_WORK_ORDER", f"no work order {wo_id} is recorded for {motor} (and none is being imported with this record)")
        elif not d and wo["closed"]:
            d = _unresolved("WORK_ORDER_CLOSED", f"work order {wo_id} was already closed at {wo['close_at']}")
        elif not d and t < wo["open_at"]:
            d = _unresolved("TIME_ORDER", f"record is dated {t}, before work order {wo_id} opened at {wo['open_at']}")
        elif not d and t < wo["last"]:
            d = _unresolved("TIME_ORDER", f"record is dated {t}, before the order's latest recorded event at {wo['last']}")
        elif not d and k in (Kind.COMPONENT_INSTALLED, Kind.COMPONENT_REMOVED):
            slot = a["slot"]
            res = resolve(c, a["lot"])
            steps = [Step(field="lot", step="registry_resolve", before=a["lot"], after=res.canonical)] if res.ok and res.canonical != a["lot"] else []
            if slot not in wo["expected"]:
                d = _unresolved("UNEXPECTED_SLOT", f"work order {wo_id} does not cover position {slot}")
            elif not res.ok:
                d = _unresolved("UNRESOLVED_LOT", f"lot {a['lot']!r}: identity not established ({res.status}{': ' + res.detail if res.detail else ''}){' - resembles ' + ', '.join(res.resembles) if res.resembles else ''}")
            elif cid in contradict:
                d = _unresolved("CONTRADICTORY_LOT", f"MES installs {res.canonical} at {slot} but ERP record(s) {', '.join(contradict[cid])} issued a different lot", contradict[cid][0])
            elif k is Kind.COMPONENT_REMOVED:
                occ = sim.occupant.get(slot)
                if wo["type"] != "REWORK":
                    d = _unresolved("REMOVAL_OUTSIDE_REWORK", "removals are only recorded under a rework order")
                elif not occ or occ["lot"] != res.canonical or (a.get("serial") or occ["serial"]) != occ["serial"]:
                    d = _unresolved("REMOVAL_MISMATCH", f"record says {res.canonical}{'/' + a['serial'] if a.get('serial') else ''} was removed from {slot}; the ledger shows "
                                                         f"{(occ['lot'] + ('/' + occ['serial'] if occ['serial'] else '')) if occ else 'no recorded occupant'}")
                else:
                    payload = dict(componentType="BEARING", slot=slot, observedPart=PART, observedLot=res.canonical, identityGranularity="SERIAL" if occ["serial"] else "LOT",
                                   endsInstallEventId=occ["install_id"])
                    if occ["serial"]:
                        payload["observedSerial"] = occ["serial"]
                    evs = plan_events(c, [("COMPONENT_REMOVED", "REWORK", payload, wo_id)])
                    if isinstance(evs, str):
                        d = _unresolved("PROFILE_REJECTED", evs)
                    else:
                        sim.occupant.pop(slot); wo["removed"].add(slot); wo["last"] = t
                        d = _accepted("CAPTURE", steps=steps, events=evs)
            else:                                                             # install
                m = next((m for m in sim.mfg if m["lot"] == res.canonical and not m["used"]), None)
                if sim.occupant.get(slot):
                    d = _unresolved("SLOT_OCCUPIED", f"{slot} already holds {sim.occupant[slot]['lot']}; a removal must be recorded first")
                elif wo["type"] == "REWORK" and slot not in wo["removed"]:
                    d = _unresolved("REMOVAL_REQUIRED", f"rework install at {slot} without a recorded removal in {wo_id}")
                elif m is None:
                    d = _unresolved("MISSING_UPSTREAM", f"no ERP lot issue for {res.canonical} on {motor} is recorded or being imported, so there is no manufacture record to install from")
                elif m["occurred"] > t:
                    d = _unresolved("TIME_ORDER", f"ERP issued the lot at {m['occurred']}, after this install at {t}")
                elif bool(a.get("serial")) != bool(m["serial"]) or (a.get("serial") and a["serial"] != m["serial"]):
                    d = _unresolved("CONTRADICTORY_SERIAL", f"MES serial {a.get('serial')!r} differs from the serial {m['serial']!r} issued by ERP")
                else:
                    role = "ASSY" if wo["type"] == "BUILD" else "REWORK"
                    payload = dict(componentType="BEARING", slot=slot, part=PART, lot=res.canonical, identityGranularity="SERIAL" if m["serial"] else "LOT", manufacturingEventId=m["eventId"])
                    if m["serial"]:
                        payload["serial"] = m["serial"]
                    evs = plan_events(c, [("COMPONENT_INSTALLED", role, payload, wo_id)])
                    if isinstance(evs, str):
                        d = _unresolved("PROFILE_REJECTED", evs)
                    else:
                        m["used"] = True
                        sim.occupant[slot] = dict(lot=res.canonical, serial=m["serial"], install_id=evs[0].event_id)
                        sim.history.append((slot, res.canonical, m["serial"])); wo["installed"].add(slot); wo["last"] = t
                        d = _accepted("CAPTURE", steps=steps, events=evs)
        elif not d and k is Kind.WORK_ORDER_CLOSED:
            need = wo["expected"] - wo["installed"] if wo["type"] == "BUILD" else (wo["expected"] - wo["installed"]) | (wo["expected"] - wo["removed"])
            warn = []
            if a["disposition"] == "COMPLETED" and need:
                d = _unresolved("OBLIGATIONS_NOT_MET", f"work order {wo_id} cannot be completed: no accepted record for {', '.join(sorted(need))}")
            else:
                if need:
                    warn.append(_warn("CLOSED_CANCELLED_WITH_OPEN_OBLIGATIONS", f"closed CANCELLED with positions not done: {', '.join(sorted(need))}"))
                evs = plan_events(c, [("WORK_ORDER_CLOSED", "MES", dict(disposition=a["disposition"]), wo_id)])
                if isinstance(evs, str):
                    d = _unresolved("PROFILE_REJECTED", evs)
                else:
                    wo.update(closed=True, close_at=t, close_id=evs[0].event_id, disposition=a["disposition"])
                d = _accepted("CAPTURE", issues=warn, events=evs)
        out[cid] = d

    # -- pass 3: staged-only claims (quality inspections, SCADA samples)
    for c in by_kind(Kind.QUALITY_INSPECTION, Kind.PROCESS_SIGNAL):
        a, cid, k = c.canonical.attributes, c.canonical.canonicalId, c.canonical.kind
        t = c.canonical.occurredAt
        if not exists():
            out[cid] = _unresolved("UNKNOWN_MOTOR", f"motor {motor} has no ledger unit and no accepted capturable record in this import")
        elif k is Kind.PROCESS_SIGNAL and a.get("workOrderId"):
            wo = sim.wos.get(a["workOrderId"])
            if wo is None:
                out[cid] = _unresolved("UNKNOWN_WORK_ORDER", f"work order {a['workOrderId']} is not recorded for {motor}")
            elif t < wo["open_at"] or (wo["closed"] and t > wo["close_at"]):
                out[cid] = _unresolved("OUTSIDE_WORK_ORDER_WINDOW", f"sample at {t} is outside work order {a['workOrderId']} ({wo['open_at']} .. {wo['close_at'] or 'open'})")
            else:
                out[cid] = _accepted("STAGE_ONLY")
        else:
            warn = []
            if k is Kind.QUALITY_INSPECTION and a.get("lot") and not any(h[1] == a["lot"] and (not a.get("slot") or h[0] == a["slot"]) for h in sim.history):
                warn.append(_warn("INSPECTED_COMPONENT_NOT_RECORDED", f"inspection names lot {a['lot']}{' at ' + a['slot'] if a.get('slot') else ''} but no install of it is recorded for {motor}"))
            out[cid] = _accepted("STAGE_ONLY", issues=warn)

    # -- pass 4: logistics dispatches (historical shipment records)
    quality = [(q.canonical.occurredAt, q.canonical.attributes["result"], q.canonical.sourceRecordId) for q in by_kind(Kind.QUALITY_INSPECTION) if out[q.canonical.canonicalId].outcome == "ACCEPTED"]
    quality += [(q["occurredAt"], q["attributes"]["result"], q["sourceRecordId"]) for q in world.quality(motor)]
    for c in by_kind(Kind.SHIPMENT_DISPATCHED):
        a, cid, t = c.canonical.attributes, c.canonical.canonicalId, c.canonical.occurredAt
        d = unknown_motor(c)
        closed = [w for w in sim.wos.values() if w["type"] == "BUILD" and w["closed"] and w["disposition"] == "COMPLETED"]
        if d:
            pass
        elif not opts.historical_shipments:
            d = _unresolved("SHIPMENT_IMPORT_DISABLED", "importing shipment history is not enabled (mapping capture.historicalShipments or --historical-shipments)")
        elif sim.shipped:
            d = _unresolved("SECOND_SHIPMENT", f"{motor} already has shipment {sim.shipped[0]['shipmentId']} recorded; a motor is shipped once")
        elif not closed:
            d = _unresolved("MISSING_ASSEMBLY", f"no completed build order is recorded or being imported for {motor}, so there is nothing for the shipment to refer to")
        elif closed[0]["close_at"] > t:
            d = _unresolved("TIME_ORDER", f"dispatched at {t}, before the build order closed at {closed[0]['close_at']}")
        else:
            warn = []
            fails = [q for q in quality if q[1] == "FAIL" and q[0] < t]
            for f in fails:
                if not any(q[1] == "PASS" and f[0] < q[0] < t for q in quality):
                    warn.append(_warn("INSPECTION_FAILED_BEFORE_SHIPMENT", f"recorded FAIL inspection {f[2]} ({f[0]}) precedes this dispatch with no later recorded PASS", f[2]))
            evs = plan_events(c, [("MOTOR_SHIPPED", "SHIP", dict(shipmentId=a["shipmentId"], customer=a["customer"], destination=a["destination"], assemblyEventId=closed[0]["close_id"]), None)])
            if isinstance(evs, str):
                d = _unresolved("PROFILE_REJECTED", evs)
            else:
                sim.shipped.append(dict(shipmentId=a["shipmentId"], at=t))
                warn.append(_warn("HISTORICAL_SHIPMENT_RECORD", "recorded as historical evidence only: it does not authorize a shipment, no release eligibility or checkpoint was consulted, "
                                                                "and the ordinary shipment gate was not run"))
                d = _accepted("CAPTURE", issues=warn, events=evs)
        out[cid] = d

    for m in sim.mfg:                                                              # ERP issues nobody installed (yet)
        if m["cid"] and not m["used"] and out[m["cid"]].outcome == "ACCEPTED":
            out[m["cid"]].issues.append(_warn("NO_MATCHING_INSTALL", f"no install of {m['lot']} is recorded or being imported yet; the issue is captured on its own"))
    return out


def plan(files: list[FileResult], world: World, opts: Options) -> Plan:
    for f in files:
        for r in f.records:
            if r.canonical is not None:
                r.motor = r.canonical.motorSerial
    # Repeat-import checks come first: what the ledger / staging already holds for a record id decides whether a new copy is a repeat or a contradiction.
    for f in files:
        for r in f.records:
            c = r.canonical
            if c is None or r.outcome is not None:
                continue
            if c.kind in CAP_KINDS:
                prior = world.imported(r.motor).get(c.canonicalId)
                if not prior:
                    continue
                if prior[0] == c.contentSha256[:16] and len(prior[1]) != EVENTS_PER_RECORD[c.kind]:
                    _finish(r, _unresolved("PARTIAL_PRIOR_IMPORT", f"the ledger holds {len(prior[1])} of {EVENTS_PER_RECORD[c.kind]} events written for this record; "
                                                                 "an earlier import was interrupted and needs manual reconciliation"))
                elif prior[0] == c.contentSha256[:16]:
                    _finish(r, _accepted("ALREADY_IMPORTED"), ledger=prior[1])
                else:
                    _finish(r, _unresolved("CONTRADICTS_PRIOR_IMPORT", "this source record id was imported earlier with different content; the ledger is append-only, so the "
                                                                      "earlier record stands and this change needs review"))
            elif world.staging:
                prior = world.staging.latest_accepted(c.canonicalId)
                if prior and prior["content_sha256"] == c.contentSha256:
                    _finish(r, _accepted("ALREADY_IMPORTED"))
                elif prior:
                    _finish(r, _unresolved("CONTRADICTS_PRIOR_IMPORT", "this source record id was staged earlier with different content; the earlier record stands and this change needs review"))
    find_duplicates(files)
    # A source time the ledger cannot take (outside the capture session, years ahead of the application clock, malformed) is refused HERE, for every kind of record,
    # so nothing is captured and the shared application clock never moves for it. A ledger rejection would block the motor permanently.
    for f in files:
        for r in f.records:
            c = r.canonical
            if c is not None and r.outcome is None:
                problem = time_problem(c.occurredAt, world.clock(), world.window(c.motorSerial, "MES") if c.motorSerial else DEFAULT_WINDOW)
                if problem:
                    _finish(r, _unresolved("TIME_OUT_OF_WINDOW", problem))
    live = [r for f in files for r in f.records if r.canonical is not None and r.outcome is None]
    # A SCADA sample without a motor is tied to one through its work order (an MES record in this import, or the ledger).
    wo_motor: dict[str, set] = {}
    for r in live:
        if r.canonical.kind is Kind.WORK_ORDER_OPENED:
            wo_motor.setdefault(r.canonical.attributes["workOrderId"], set()).add(r.canonical.motorSerial)
    for r in live:
        a = r.canonical.attributes
        if r.canonical.kind is Kind.PROCESS_SIGNAL and a.get("workOrderId"):
            known = wo_motor.get(a["workOrderId"], set()) | world.motors_for_work_order(a["workOrderId"])
            if r.motor is None:
                if len(known) == 1:
                    r.motor = next(iter(known))
                    r.steps.append(Step(field="motorSerial", step="resolved_from_work_order", before=None, after=r.motor))
                else:
                    _finish(r, _unresolved("MISSING_IDENTITY", f"no motor on the sample and work order {a['workOrderId']} does not identify exactly one motor"))
            elif known and r.motor not in known:
                _finish(r, _unresolved("CONTRADICTORY_IDENTITY", f"sample names {r.motor} but work order {a['workOrderId']} belongs to {', '.join(sorted(known))}"))
        elif r.motor is None:
            _finish(r, _unresolved("MISSING_IDENTITY", "record names no motor"))
    cands = [r for r in live if r.outcome is None]
    by_motor: dict[str, list] = {}
    for r in cands:
        by_motor.setdefault(r.motor, []).append(r)
    result = Plan(files=files, options=opts)
    for motor in sorted(by_motor):
        group, held = by_motor[motor], {}
        for _ in range(6):
            decisions = evaluate_motor(motor, group, world, opts, held)
            groups: dict[str, list] = {}
            for r in group:
                if r.canonical.kind in MES_KINDS:
                    groups.setdefault(r.canonical.attributes["workOrderId"], []).append(r)
            new = {}
            for wo, members in groups.items():
                ok = [r for r in members if decisions[r.canonical.canonicalId].outcome == "ACCEPTED"]
                bad = [r for r in members if decisions[r.canonical.canonicalId].outcome != "ACCEPTED"]
                if ok and bad:                                   # all-or-nothing per work order
                    new[wo] = (bad[0].canonical.sourceRecordId, {r.canonical.canonicalId for r in ok}, {r.canonical.canonicalId: decisions[r.canonical.canonicalId] for r in bad})
            if not new:
                break
            held.update(new)
        for r in group:
            _finish(r, decisions[r.canonical.canonicalId])
        events = sorted((e for r in group for e in decisions[r.canonical.canonicalId].events), key=lambda e: (e.sort, e.event_id))
        if events:
            if not world.unit_exists(motor):
                result.creates.append(motor)
            result.events += events
    return result


def _finish(r: RecordResult, d: Decision, ledger=()):
    r.outcome, r.disposition, r.reason = d.outcome, d.disposition, d.reason
    r.issues += d.issues
    r.steps += d.steps
    r.ledgerEventIds = list(ledger) or [e.event_id for e in d.events]
