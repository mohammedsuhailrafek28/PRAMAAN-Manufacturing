"""A7 event-ordering ambiguity diagnostic (research prototype; read-only; synthetic data only).

Question: is a motor's current decision (frozen evaluator + frozen identity/integrity guard) the same in every timeline that the motor's OWN declared
clock-trust profile admits? It searches a bounded subset of those timelines (below); it does not decide anything, never writes, does not block shipment and is not a clearance.

Model (assumptions, all stated in docs/research/A7_ORDER_FIREWALL.md):
  M1 Each source's clock may be off by one unknown constant offset d_s (whole seconds), applied to both occurredAt and recordedAt of every event of
     that source (they come from the same producer clock). A constant per-source offset preserves the authoritative per-source sequence order.
  M2 |d_s| <= observationClockSkewSeconds from the motor's coverage. The frozen evaluator gives untrusted clocks NO bound at all (ledger.clearly_after
     is False unless both clocks are trusted), so this bound is a deliberate restriction: every counterexample found here is also admissible for the
     frozen model, and "no counterexample" covers only this restricted space.
  M3 Sources whose timeSource is listed in trustedTimeSources are never shifted (d_s = 0).
  M4 A shifted timeline is admissible only if every event still passes the frozen native validator (profile.validate_native) and the frozen capture
     rules that involve time: per-source recordedAt non-decreasing, referenced events recorded no later than the referrer, recordedAt inside the
     event's authenticated capture session (integration/pramaan_integration/ledger.py:151-176).
  M5 Phase 2 enumerates the cross-source orders of occurredAt that some offsets satisfying M2-M4 realize (difference constraints, Bellman-Ford)
     and evaluates ONE strict (gaps >= 1 s) and ONE tie (gaps may be 0 s) realization of each. Other realizations of the same order (other ties,
     gap sizes, cross-source recordedAt interleavings, which the evaluator also reads) are not evaluated, so NO_COUNTEREXAMPLE_FOUND is "none
     found among the evaluated realizations", never "none exists" and never exhaustive coverage. NOT_EXHAUSTIVE is reported when the cap
     is hit or a fixed date the decision logic compares against (policy announcement, registry effective dates) lies within the skew of an event.
Decision function: the same calls as application/service.py:404-409 (pramaan_recall.evaluate with Config.v3, lot_identity.policy_findings,
motor_findings, integrity_findings, guard_decision); registry-binding findings are omitted because they depend on the checkpoint, not on the timeline.
"""
import copy
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from application.service import Manufacturing, PART  # noqa: E402
from application import lot_identity as lots  # noqa: E402
from pramaan_integration import engine_bridge  # noqa: E402
from pramaan_integration.profile import ValidationFailure, validate_native  # noqa: E402

CLASSES = ("ORDER_SENSITIVE", "NO_COUNTEREXAMPLE_FOUND", "NOT_EXHAUSTIVE")
NOTICE = ("Research diagnostic on copied synthetic evidence. It does NOT block shipment, does NOT provide clearance and changes no decision. "
          "Timestamps are synthetic and untrusted; the clock bound used is the motor's declared skew, not an authenticated clock. "
          "NO_COUNTEREXAMPLE_FOUND means only that none was found among the evaluated realizations of a bounded search; it is not evidence of safety.")
F = "%Y-%m-%dT%H:%M:%SZ"
REFS = ("supersedesEventId", "endsInstallEventId", "exceptionEventId", "materialEventId", "manufacturingEventId", "assemblyEventId")


def _t(s):
    return datetime.strptime(s, F)


def _s(d):
    return d.strftime(F)


def sha256(path):
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def _fingerprint(db_path):
    return {suffix: sha256(str(db_path) + suffix) for suffix in ("", "-wal")}


# ------------------------------------------------------------------ evidence: copied, never the live ledger
def load_evidence(db_path, *, lot_registry=None, workdir=None):
    """Byte-copy the ledger (and its WAL, if present) and extract, per motor, the frozen inputs of the decision from the COPY.
    The live file is never opened by SQLite (even a read-only open of a WAL database creates side files); it is only read as bytes, and its
    bytes (and WAL) are hashed before and after and must be identical. The copy is then verified by the frozen ledger/audit code on open."""
    db_path = Path(db_path).resolve()
    before = _fingerprint(db_path)
    work = Path(workdir or tempfile.mkdtemp(prefix="a7-copy-"))
    work.mkdir(parents=True, exist_ok=True)
    copy_path = work / "evidence-copy.sqlite"
    copy_path.write_bytes(db_path.read_bytes())
    if Path(str(db_path) + "-wal").exists():
        Path(str(copy_path) + "-wal").write_bytes(Path(str(db_path) + "-wal").read_bytes())
    if _fingerprint(db_path) != before:
        raise RuntimeError("live ledger changed during the copy (a writer is active); aborting")
    app = Manufacturing(copy_path, lot_registry=lot_registry)
    try:
        policy = app.policy()
        recall_findings = lots.policy_findings(app.registry, policy, PART) if policy else []
        motors = {}
        for (motor,) in app.db.execute("SELECT serial FROM app_units ORDER BY serial").fetchall():
            wm = app.ledger.watermark(motor)
            case, _ = app.ledger.snapshot(motor, wm)
            motors[motor] = dict(motor=motor, case=copy.deepcopy(case), watermark=dict(wm), coverage=copy.deepcopy(app.ledger._config(motor)["coverage"]),
                                 sessions=copy.deepcopy(app.ledger._config(motor)["sessions"]), config=dict(sources=copy.deepcopy(app.ledger._config(motor)["sources"])),
                                 policy=copy.deepcopy(policy), registry=app.registry,
                                 recallFindings=recall_findings)
    finally:
        app.close()
    after = _fingerprint(db_path)
    if before != after:
        raise RuntimeError("live ledger bytes changed while copying; aborting")
    return dict(source=str(db_path), sourceFingerprint=before, copy=str(copy_path), motors=motors)


# ------------------------------------------------------------------ decision: frozen calls only
def decide(ev, events):
    case = dict(ev["case"], events=events)
    raw = engine_bridge.pramaan_recall.evaluate(copy.deepcopy(case), copy.deepcopy(ev["policy"]), ev["coverage"], ev["watermark"], engine_bridge.Config.v3())
    found = list(ev["recallFindings"]) + lots.motor_findings(ev["registry"], events, ev["policy"], PART)
    broken = lots.integrity_findings(events)
    g = lots.guard_decision(copy.deepcopy(raw), found, broken)
    return dict(operationalAction=g["operationalAction"], evaluatorOperationalAction=raw["operationalAction"], evidenceFinding=raw["evidenceFinding"],
                reasonCodes=list(raw["reasonCodes"]), identityFindings=sorted(f["reason"] for f in found), integrityFindings=sorted(f["reason"] for f in broken))


def _key(d):
    return (d["operationalAction"], d["evaluatorOperationalAction"], d["evidenceFinding"], tuple(sorted(d["reasonCodes"])), tuple(d["identityFindings"]), tuple(d["integrityFindings"]))


# ------------------------------------------------------------------ model
def profile_of(ev):
    attr = ev["coverage"].get("slotAttribution") or {}
    skew = attr.get("observationClockSkewSeconds")
    if not isinstance(skew, int) or skew < 0:
        raise ValueError("coverage declares no usable observationClockSkewSeconds; the model is undefined")
    return skew, set(attr.get("trustedTimeSources", []))


def movable_sources(ev):
    skew, trusted = profile_of(ev)
    by = {}
    for e in ev["case"]["events"]:
        by.setdefault(e["sourceId"], set()).add(e["timeSource"])
    return {s for s, ts in by.items() if not (ts & trusted)}     # a source with ANY trusted-clock event is pinned


def shift(events, offsets):
    out = []
    for e in events:
        d = offsets.get(e["sourceId"], 0)
        x = copy.deepcopy(e)
        if d:
            x["occurredAt"] = _s(_t(e["occurredAt"]) + timedelta(seconds=d))
            x["recordedAt"] = _s(_t(e["recordedAt"]) + timedelta(seconds=d))
        out.append(x)
    return out


def violations(ev, offsets, events):
    """Why a shifted timeline is NOT admissible (empty list = admissible)."""
    skew, _ = profile_of(ev)
    movable = movable_sources(ev)
    out = []
    for s, d in offsets.items():
        if d and s not in movable:
            out.append(f"{s}: trusted clock cannot be shifted")
        if abs(d) > skew:
            out.append(f"{s}: offset {d}s exceeds declared skew {skew}s")
    by_id = {e["eventId"]: e for e in events}
    last = {}
    for e in sorted(events, key=lambda e: (e["sourceId"], e["sourceSeq"])):
        native = {k: v for k, v in e.items() if k != "repository"}
        try:
            validate_native(native)
        except ValidationFailure as exc:
            out.append(f"{e['eventId']}: {exc}")
        if e["recordedAt"] < last.get(e["sourceId"], ""):
            out.append(f"{e['eventId']}: recordedAt regression within {e['sourceId']}")
        last[e["sourceId"]] = e["recordedAt"]
        for k in REFS:
            ref = e.get(k) if k == "supersedesEventId" else e["payload"].get(k)
            if ref and ref in by_id and by_id[ref]["recordedAt"] > e["recordedAt"]:
                out.append(f"{e['eventId']}: references {ref} recorded later")
        sess = [x for x in ev["sessions"] if x["sessionId"] == e["captureSessionId"] and x["sourceId"] == e["sourceId"] and x["authenticated"] is True]
        if not any(x["from"] <= e["recordedAt"] <= x["to"] for x in sess):
            out.append(f"{e['eventId']}: recordedAt outside its authenticated capture session")
    return out


def _breakpoints(ev, source, skew):
    """Offsets of one source at which some relative order (or tie) with another source's event changes, within +-skew, sorted by magnitude."""
    mine = [_t(e["occurredAt"]) for e in ev["case"]["events"] if e["sourceId"] == source]
    other = [_t(e["occurredAt"]) for e in ev["case"]["events"] if e["sourceId"] != source]
    cands = set()
    for a in mine:
        for b in other:
            d = int((b - a).total_seconds())
            for x in (d - 1, d, d + 1):
                if x and abs(x) <= skew:
                    cands.add(x)
    return sorted(cands, key=lambda x: (abs(x), x))


def _constants(ev):
    out = []
    if ev["policy"] and ev["policy"].get("announcedAt"):
        out.append(("policy.announcedAt", ev["policy"]["announcedAt"]))
    for entries in ev["registry"].by_lot.values():
        for e in entries:
            for k in ("effectiveFrom", "effectiveTo"):
                if e.get(k):
                    out.append((f"registry.{e['canonical']}.{k}", e[k] if "T" in e[k] else e[k] + "T00:00:00Z"))
    return out


def _capture_constraints(ev, events):
    """The time-related M4 capture rules as difference constraints on the offsets, so that the order search only keeps orders that SOME admissible
    realization satisfies (not just the one Bellman-Ford happens to return). Per-source rules are invariant under a constant offset."""
    out, by_id = [], {e["eventId"]: e for e in events}
    secs = lambda s: int(_t(s).timestamp())  # noqa: E731
    for e in events:
        rec = secs(e["recordedAt"])
        sess = [x for x in ev["sessions"] if x["sessionId"] == e["captureSessionId"] and x["sourceId"] == e["sourceId"] and x["authenticated"] is True]
        if len(sess) == 1:                                                    # from <= rec + d <= to
            out += [(e["sourceId"], "Z", secs(sess[0]["to"]) - rec), ("Z", e["sourceId"], rec - secs(sess[0]["from"]))]
        for k in REFS:
            ref = e.get(k) if k == "supersedesEventId" else e["payload"].get(k)
            if ref in by_id and by_id[ref]["sourceId"] != e["sourceId"]:     # rec_ref + d_ref <= rec + d
                out.append((by_id[ref]["sourceId"], e["sourceId"], rec - secs(by_id[ref]["recordedAt"])))
    return out


def _feasible(nodes, cons, skew, movable):
    """Difference constraints d_a - d_b <= w over nodes (+ zero node 'Z'); |d| <= skew; pinned nodes = 0. Returns offsets or None."""
    edges = list(cons)
    for n in nodes:
        lim = skew if n in movable else 0
        edges += [(n, "Z", lim), ("Z", n, lim)]          # d_n - d_Z <= lim ; d_Z - d_n <= lim
    dist = {n: 0 for n in list(nodes) + ["Z"]}
    allnodes = list(dist)
    for _ in range(len(allnodes)):
        changed = False
        for a, b, w in edges:                           # constraint d_a - d_b <= w  ->  edge b -> a weight w
            if dist[b] + w < dist[a]:
                dist[a] = dist[b] + w; changed = True
        if not changed:
            z = dist["Z"]
            return {n: dist[n] - z for n in nodes}
    return None


# ------------------------------------------------------------------ search
def analyse(ev, *, cap=20000):
    events = ev["case"]["events"]
    skew, trusted = profile_of(ev)
    movable = movable_sources(ev)
    base = decide(ev, events)
    report = dict(motor=ev["motor"], skewSeconds=skew, trustedTimeSources=sorted(trusted), movableSources=sorted(movable),
                  pinnedSources=sorted({e["sourceId"] for e in events} - movable), original=dict(decision=base, timeline=timeline(events)),
                  counterexample=None, notes=[], notice=NOTICE)
    tried = 0
    # Phase 1: single-source offsets in increasing magnitude -> minimal witness (fewest shifted sources, then smallest |offset|).
    for source in sorted(movable):
        for d in _breakpoints(ev, source, skew):
            shifted = shift(events, {source: d})
            if violations(ev, {source: d}, shifted):
                continue
            tried += 1
            res = decide(ev, shifted)
            if _key(res) != _key(base):
                cand = dict(offsets={source: d}, decision=res, timeline=timeline(shifted), changed=_changes(events, shifted))
                if report["counterexample"] is None or abs(d) < abs(next(iter(report["counterexample"]["offsets"].values()))):
                    report["counterexample"] = cand
                break
    report["singleSourceTimelinesEvaluated"] = tried
    if report["counterexample"]:
        report["classification"] = "ORDER_SENSITIVE"
        report["notes"].append("Witness is minimal among single-source shifts (smallest offset per source, smallest overall). It is a real admissible "
                               "timeline under the model; it does not say which timeline happened.")
        return report
    # Phase 2: enumerate the cross-source orders of occurredAt that some offsets satisfying M2-M4 realize; evaluate one strict and one tie
    # realization of each (bounded by cap). This is NOT exhaustive over all admissible timelines (see the NO_COUNTEREXAMPLE_FOUND note).
    near = [name for name, c in _constants(ev) if any(abs((_t(c) - _t(e["occurredAt"])).total_seconds()) <= skew for e in events)]
    order = sorted(range(len(events)), key=lambda i: (events[i]["sourceId"], events[i]["sourceSeq"]))
    t = {i: int(_t(events[i]["occurredAt"]).timestamp()) for i in range(len(events))}
    src = {i: events[i]["sourceId"] for i in range(len(events))}
    prev_same = {}
    for i in order:
        prev_same[i] = [j for j in order if src[j] == src[i] and events[j]["sourceSeq"] < events[i]["sourceSeq"]]
    nodes = sorted(set(src.values()))
    count, capped = [0], [False]

    def cons_for(a, b, gap):   # a before b by >= gap s:  t_a + d_A <= t_b + d_B - gap  ->  d_A - d_B <= t_b - t_a - gap   (same source: fixed)
        return None if src[a] == src[b] else (src[a], src[b], t[b] - t[a] - gap)

    def evaluate_realization(cons):
        offs = _feasible(nodes, cons, skew, movable)
        if offs is None:
            return
        offs = {k: v for k, v in offs.items() if v}
        key = tuple(sorted(offs.items()))
        if key in seen:
            return
        seen.add(key)
        shifted = shift(events, offs)
        if violations(ev, offs, shifted):
            return
        count[0] += 1
        if count[0] > cap:
            capped[0] = True
            return
        res = decide(ev, shifted)
        if _key(res) != _key(base) and report["counterexample"] is None:
            report["counterexample"] = dict(offsets=offs, decision=res, timeline=timeline(shifted), changed=_changes(events, shifted))

    def dfs(placed, cons, weak, used):
        if capped[0]:
            return
        if len(placed) == len(events):
            evaluate_realization(cons)          # the strict order (every cross-source gap >= 1 s)
            evaluate_realization(weak)          # one boundary realization of the same order (gaps may be 0 s: exact ties)
            return
        for k in range(len(events)):
            if k in used or any(j not in used for j in prev_same[k]):
                continue
            new = [c for c in (cons_for(k, u, 1) for u in range(len(events)) if u not in used and u != k) if c]
            new_weak = [c for c in (cons_for(k, u, 0) for u in range(len(events)) if u not in used and u != k) if c]
            if _feasible(nodes, weak + new_weak, skew, movable) is None:
                continue
            used.add(k)
            dfs(placed + [k], cons + new, weak + new_weak, used)
            used.discard(k)

    seen = set()
    base_cons = _capture_constraints(ev, events)
    dfs([], list(base_cons), list(base_cons), set())
    report["ordersEvaluated"] = min(count[0], cap)
    if report["counterexample"]:
        report["classification"] = "ORDER_SENSITIVE"
        report["notes"].append("Witness found by order enumeration (multi-source); offsets are one feasible realization, not necessarily minimal.")
    elif capped[0]:
        report["classification"] = "NOT_EXHAUSTIVE"
        report["notes"].append(f"Search stopped at the cap of {cap} evaluated realizations; the remaining space was NOT examined.")
    elif near:
        report["classification"] = "NOT_EXHAUSTIVE"
        report["notes"].append("A fixed date the decision logic compares against lies within the skew of an event (" + ", ".join(near) + "); orders relative to it were not enumerated.")
    else:
        report["classification"] = "NO_COUNTEREXAMPLE_FOUND"
        report["notes"].append("No counterexample among the evaluated realizations: one strict and one tie realization of each cross-source occurredAt order "
                               "realizable under the model. NOT exhaustive: other tie patterns, other gap sizes and cross-source recordedAt interleavings "
                               "within an order, clock drift, and offsets beyond the declared skew were not evaluated. Not a clearance.")
    return report


def timeline(events):
    return [dict(eventId=e["eventId"], eventType=e["eventType"], sourceId=e["sourceId"], sourceSeq=e["sourceSeq"], occurredAt=e["occurredAt"],
                 recordedAt=e["recordedAt"], timeSource=e["timeSource"], slot=e["payload"].get("slot"),
                 lot=e["payload"].get("lot") or e["payload"].get("observedLot"))
            for e in sorted(events, key=lambda e: (e["occurredAt"], e["recordedAt"], e["sourceId"], e["sourceSeq"]))]


def _changes(a, b):
    old = {e["eventId"]: e for e in a}
    return [dict(eventId=e["eventId"], sourceId=e["sourceId"], occurredAt=[old[e["eventId"]]["occurredAt"], e["occurredAt"]],
                 recordedAt=[old[e["eventId"]]["recordedAt"], e["recordedAt"]]) for e in b if e["occurredAt"] != old[e["eventId"]]["occurredAt"]]


def run(db_path, motors=None, *, cap=20000, lot_registry=None, workdir=None):
    evidence = load_evidence(db_path, lot_registry=lot_registry, workdir=workdir)
    reports = {m: analyse(ev, cap=cap) for m, ev in evidence["motors"].items() if motors is None or m in motors}
    after = _fingerprint(Path(db_path).resolve())
    return dict(format="PRAMAAN-A7-DIAGNOSTIC/0", notice=NOTICE, source=evidence["source"], sourceFingerprintBefore=evidence["sourceFingerprint"],
                sourceFingerprintAfter=after, sourceUnchanged=after == evidence["sourceFingerprint"], analysedCopy=evidence["copy"], motors=reports)


def render(report):
    lines = ["A7 EVENT-ORDERING DIAGNOSTIC (research prototype)", report["notice"], f"live ledger unchanged: {report['sourceUnchanged']}", ""]
    for m, r in report["motors"].items():
        o = r["original"]["decision"]
        lines.append(f"{m}: {r['classification']}   recorded-timeline decision: {o['operationalAction']} (evaluator {o['evaluatorOperationalAction']}/{o['evidenceFinding']}; identity {o['identityFindings'] or 'none'})")
        lines.append(f"   model: per-source constant clock offset |d| <= {r['skewSeconds']}s; trusted time sources {r['trustedTimeSources'] or 'none'}; movable sources {len(r['movableSources'])}")
        if r["counterexample"]:
            c = r["counterexample"]
            lines.append(f"   counterexample offsets: {c['offsets']}  ->  decision {c['decision']['operationalAction']} (identity {c['decision']['identityFindings'] or 'none'})")
            for ch in c["changed"]:
                lines.append(f"      {ch['eventId']}  occurredAt {ch['occurredAt'][0]} -> {ch['occurredAt'][1]}   recordedAt {ch['recordedAt'][0]} -> {ch['recordedAt'][1]}")
        for n in r["notes"]:
            lines.append("   note: " + n)
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="A7 read-only ordering diagnostic over a COPY of a synthetic ledger")
    ap.add_argument("ledger"); ap.add_argument("out_json"); ap.add_argument("--motor", action="append"); ap.add_argument("--cap", type=int, default=20000)
    a = ap.parse_args()
    rep = run(a.ledger, a.motor, cap=a.cap)
    Path(a.out_json).write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(render(rep))
    sys.exit(0 if rep["sourceUnchanged"] else 2)
