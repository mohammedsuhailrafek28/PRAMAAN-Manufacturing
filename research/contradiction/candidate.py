"""B1: manufacturing-specific contradiction constraints plus an evidence-to-recall-decision dependency model.

Advisory only. Nothing here writes a decision: the as-recorded findings are re-derived by the pinned evaluator on deep copies, and every
alternative interpretation is an isolated replay of an edited COPY of one motor's history.

Declared physical/identity assumptions (each contradiction lists the ones it relied on):
  A1  a physical bearing is identified by (supplier, serial); the same serial from different suppliers is a collision, not a duplicate
  A2  a bearing occupies at most one (motor, slot) at a time
  A3  a bearing has exactly one lot
  A4  an open occupancy is only proof of overlap if the removal-capture source's sessions continuously cover the window in which a
      removal would have been recorded; otherwise an uncaptured removal could explain it (POSSIBLE)
  A5  a timestamp is only known to within its declared uncertainty (device-synced clocks: coverage skew; estimated: timeUncertaintySeconds)
  A6  superseded records make no claims
"""
import copy
import itertools
import random
from datetime import datetime

import sandbox

_TS = "%Y-%m-%dT%H:%M:%SZ"
INF = float("inf")
ATTR = sandbox.COVERAGE["slotAttribution"]
REMOVAL_SOURCES = sorted({s for m in sandbox.COVERAGE["mandatoryCapture"] if m["operation"] == "COMPONENT_REMOVED" for s in m["sources"]})


def _sec(ts):
    return datetime.strptime(ts, _TS).timestamp()


def uncertainty(e):
    if "timeUncertaintySeconds" in e["payload"]:
        return float(e["payload"]["timeUncertaintySeconds"])
    return float(ATTR["observationClockSkewSeconds"]) if e["timeSource"] in ATTR["trustedTimeSources"] else 86400.0


def covered(sessions, window):
    """Do the removal-capture sources' sessions continuously cover [a, b]? (union of their sessions)"""
    spans = sorted((_sec(s["from"]), _sec(s["to"])) for s in sessions if s["sourceId"] in REMOVAL_SOURCES)
    reach, a, b = None, window[0], window[1]
    for lo, hi in spans:
        if reach is None:
            if lo <= a:
                reach = hi
        elif lo <= reach:
            reach = max(reach, hi)
    return reach is not None and reach >= b


def extract_claims(f):
    sup = {e["supersedesEventId"] for e in f["events"] if e.get("supersedesEventId")}
    out = []
    for e in f["events"]:
        if e["eventId"] in sup:
            continue
        p = e["payload"]
        if e["eventType"] == "COMPONENT_INSTALLED" and p.get("serial"):
            out.append(dict(eventId=e["eventId"], kind="INSTALL", motor=e["motorSerial"], slot=p["slot"], serial=p["serial"], supplier=p.get("supplier"),
                            lot=p.get("lot"), t=_sec(e["occurredAt"]), u=uncertainty(e), ends=None))
        elif e["eventType"] == "COMPONENT_REMOVED" and p.get("observedSerial"):
            out.append(dict(eventId=e["eventId"], kind="REMOVE", motor=e["motorSerial"], slot=p["slot"], serial=p["observedSerial"],
                            supplier=p.get("observedSupplier"), lot=p.get("observedLot"), t=_sec(e["occurredAt"]), u=uncertainty(e),
                            ends=p.get("endsInstallEventId")))
    return out


def _compatible(a, b):
    """-> 'KNOWN' (same supplier), 'UNKNOWN' (a supplier is missing) or None (different suppliers: a collision, A1)."""
    if a["supplier"] and b["supplier"]:
        return "KNOWN" if a["supplier"] == b["supplier"] else None
    return "UNKNOWN"


def presences(claims):
    """Occupancy intervals from install claims (closed by a matching removal at the same place) plus removal-only point presences."""
    used, out = set(), []
    for c in sorted((c for c in claims if c["kind"] == "INSTALL"), key=lambda c: c["t"]):
        match = [r for r in claims if r["kind"] == "REMOVE" and r["eventId"] not in used and (r["motor"], r["slot"], r["serial"]) == (c["motor"], c["slot"], c["serial"])
                 and _compatible(c, r) and (r["ends"] == c["eventId"] or (r["ends"] is None and r["t"] >= c["t"]))]
        match.sort(key=lambda r: (r["ends"] != c["eventId"], r["t"]))
        end = match[0] if match else None
        if end:
            used.add(end["eventId"])
        out.append(dict(start=c, end=end, loc=(c["motor"], c["slot"]), serial=c["serial"], supplier=c["supplier"]))
    for r in claims:
        if r["kind"] == "REMOVE" and r["eventId"] not in used:
            out.append(dict(start=r, end=r, loc=(r["motor"], r["slot"]), serial=r["serial"], supplier=r["supplier"], point=True))
    return out


def _bounds(p, other_start, sessions):
    """-> (start lo/hi uncertainty, end for 'certain', end for 'possible') of a presence relative to the window it must hold over."""
    s, e = p["start"], p["end"]
    if e is None:
        window = (min(s["t"], other_start), max(s["t"], other_start))
        return s["t"], s["u"], (INF, 0.0) if covered(sessions, window) else (-INF, 0.0), (INF, 0.0)
    return s["t"], s["u"], (e["t"], e["u"]), (e["t"], e["u"])


def overlap_class(P, Q, sessions):
    """-> (relation, reason): relation in CERTAIN | POSSIBLE | NONE for the two presences overlapping in time."""
    sP, usP, ceP, peP = _bounds(P, Q["start"]["t"], sessions)
    sQ, usQ, ceQ, peQ = _bounds(Q, P["start"]["t"], sessions)
    certain = sP + usP <= ceQ[0] - ceQ[1] and sQ + usQ <= ceP[0] - ceP[1]
    possible = sP - usP <= peQ[0] + peQ[1] and sQ - usQ <= peP[0] + peP[1]
    if certain:
        return "CERTAIN", None
    if not possible:
        return "NONE", None
    unproven_open = (P["end"] is None and ceP[0] == -INF) or (Q["end"] is None and ceQ[0] == -INF)
    return "POSSIBLE", "MISSING_REMOVAL_EVIDENCE" if unproven_open else "ORDER_UNDETERMINABLE"


def _boundary(p):
    return [x["eventId"] for x in (p["start"], p["end"]) if x]


def detect(f):
    """-> list of contradictions: {id, cls, kind, eventIds, motors, assumptions, reason}."""
    claims = extract_claims(f)
    ps, found = presences(claims), []
    motors_of = {c["eventId"]: c["motor"] for c in claims}

    def add(cls, kind, ids, assumptions, reason=None):
        ids = sorted(set(ids))
        key = (kind, tuple(ids))
        if all((x["kind"], tuple(x["eventIds"])) != key for x in found):
            found.append(dict(cls=cls, kind=kind, eventIds=ids, motors=sorted({motors_of[i] for i in ids}), assumptions=assumptions, reason=reason))

    for P, Q in itertools.combinations(ps, 2):
        if P["serial"] != Q["serial"] or P["loc"] == Q["loc"]:
            continue
        scope = _compatible(P["start"], Q["start"])
        if scope is None:
            continue
        rel, why = overlap_class(P, Q, f["sessions"])
        if rel == "NONE":
            continue
        cls = "INSUFFICIENT" if scope == "UNKNOWN" else ("DEFINITE" if rel == "CERTAIN" else "POSSIBLE")
        add(cls, "EXCLUSIVE_OCCUPANCY", _boundary(P) + _boundary(Q), ["A1", "A2", "A4", "A5"],
            None if cls == "DEFINITE" else ("SUPPLIER_SCOPE_UNKNOWN" if cls == "INSUFFICIENT" else why))
    # A3: one lot per bearing
    by_serial = {}
    for c in claims:
        if c["lot"]:
            by_serial.setdefault(c["serial"], []).append(c)
    for serial, cs in sorted(by_serial.items()):
        known = {c["supplier"] for c in cs if c["supplier"]}
        for sup in sorted(known) or [None]:
            group = [c for c in cs if c["supplier"] in (sup, None)] if sup else cs
            if len({c["lot"] for c in group}) > 1:
                unknown = any(c["supplier"] is None for c in group)
                add("INSUFFICIENT" if unknown else "DEFINITE", "LOT_IDENTITY", [c["eventId"] for c in group], ["A1", "A3"],
                    "SUPPLIER_SCOPE_UNKNOWN" if unknown else None)
    # chronology: a linked removal that precedes the install it ends, beyond clock uncertainty
    for p in ps:
        if p.get("end") and p["end"] is not p["start"] and p["end"]["t"] + p["end"]["u"] < p["start"]["t"] - p["start"]["u"]:
            add("DEFINITE", "CHRONOLOGY", _boundary(p), ["A5"])
    for i, c in enumerate(sorted(found, key=lambda c: (c["kind"], c["eventIds"])), 1):
        c["id"] = f"{f['id']}-D{i}"
    return found


# ------------------------------------------------------------------------------------------------ interpretations
def interpretations(f, c):
    """Admissible alternative readings of one contradiction as event edits. (The as-recorded reading is the recorded finding itself.)"""
    by_id = {e["eventId"]: e for e in f["events"]}
    out = []
    if c["kind"] in ("EXCLUSIVE_OCCUPANCY", "CHRONOLOGY"):
        for i in c["eventIds"]:
            out.append(dict(name=("DROP:" if by_id[i]["eventType"] == "COMPONENT_INSTALLED" else "REDACT_REMOVAL:") + i,
                            edits=[("DROP" if by_id[i]["eventType"] == "COMPONENT_INSTALLED" else "REDACT_REMOVAL", i)]))
    if c["kind"] == "LOT_IDENTITY":
        lots = sorted({(by_id[i]["payload"].get("lot") or by_id[i]["payload"].get("observedLot")) for i in c["eventIds"]})
        for lot in lots:
            out.append(dict(name=f"ADOPT_LOT:{lot}", edits=[("SET_LOT", i, lot) for i in c["eventIds"]]))
    return out


def apply_edits(f, edits):
    """-> events of the fleet with the edits applied (deep copy; the fleet is untouched)."""
    evs = copy.deepcopy(f["events"])
    drop = {e[1] for e in edits if e[0] == "DROP"}
    for e in evs:
        for ed in edits:
            if ed[1] != e["eventId"]:
                continue
            if ed[0] == "REDACT_REMOVAL":
                e["payload"].update(observedSerial=None, observedSupplier=None, observedLot=None)
            elif ed[0] == "SET_LOT":
                e["payload"]["lot" if e["eventType"] == "COMPONENT_INSTALLED" else "observedLot"] = ed[2]
    return [e for e in evs if e["eventId"] not in drop]


def replay_motor(f, motor, events):
    import fleet
    d = sandbox.replay(fleet.motor_case(f, motor, events), f["policy"])
    return dict(finding=d["evidenceFinding"], action=d["operationalAction"], reasons=d["reasonCodes"], cited=d["evidenceEventIds"])


def dependency(f, found, budget=256, seed=0):
    """Per motor: recorded finding, finding under each admissible joint interpretation of the contradictions it takes part in.

    Joint interpretations are the product of the per-contradiction options restricted to the motor's own events; when the product exceeds
    `budget` a seeded sample is replayed and the result is flagged as sampled (no robustness claim)."""
    import fleet
    rng, out = random.Random(seed), {}
    contested = {i for c in found for i in c["eventIds"]}
    for m in fleet.motors(f):
        rec = replay_motor(f, m, f["events"])
        mine = [c for c in found if m in c["motors"]]
        owned = {e["eventId"] for e in f["events"] if e["motorSerial"] == m}
        options = []
        for c in mine:
            opts = []
            for it in interpretations(f, c):
                edits = [e for e in it["edits"] if e[1] in owned]
                if edits:
                    opts.append(dict(name=it["name"], edits=edits))
            if opts:                                              # every contradiction may also be left unedited in a joint reading
                options.append([dict(name="NOT_EDITED:" + c["id"], edits=[])] + opts)
        space = 1
        for o in options:
            space *= len(o)
        combos = itertools.product(*options) if options else iter(())
        sampled = space > budget
        if sampled:
            combos = (tuple(rng.choice(o) for o in options) for _ in range(budget))
        seen, results = {}, []
        for combo in combos:
            edits = [e for part in combo for e in part["edits"]]
            key = tuple(sorted(map(str, edits)))
            if key in seen or not edits:
                continue
            try:
                r = replay_motor(f, m, apply_edits(f, edits))
            except Exception as exc:                            # an evaluator error on an interpretation is itself reported
                r = dict(finding="EVALUATOR_ERROR:" + type(exc).__name__, action="RECALL_HOLD", reasons=[], cited=[])
            seen[key] = r
            results.append(dict(interpretation=[p["name"] for p in combo], edits=[list(e) for e in edits], finding=r["finding"], action=r["action"]))
        findings = sorted({r["finding"] for r in results} | {rec["finding"]})
        # diagnostic only (not part of sensitivity): does the evaluator read a contested install with an unknown lot as unaffected?
        diag = False
        for e in f["events"]:
            if e["motorSerial"] == m and e["eventId"] in contested and e["eventType"] == "COMPONENT_INSTALLED":
                try:
                    diag = diag or (replay_motor(f, m, apply_edits(f, [("SET_LOT", e["eventId"], None)]))["finding"] == "EXCLUDED_WITH_EVIDENCE"
                                    and rec["finding"] != "EXCLUDED_WITH_EVIDENCE")
                except Exception:
                    pass
        out[m] = dict(recorded=dict(finding=rec["finding"], action=rec["action"], reasons=rec["reasons"]),
                      contradictions=[c["id"] for c in mine], joint=dict(space=space, replayed=len(results), sampled=sampled),
                      findingsAcrossInterpretations=findings,
                      sensitive=any(r["finding"] != rec["finding"] for r in results),
                      releaseSensitive=any(r["action"] != rec["action"] for r in results),
                      staticTrace=bool(set(rec["cited"]) & contested), unknownIdentityReadAsUnaffected=diag, flips=[r for r in results if r["action"] != rec["action"]][:3],
                      results=results)
    return out
