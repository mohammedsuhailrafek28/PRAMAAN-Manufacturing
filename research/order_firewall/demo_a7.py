"""A7 judge demo (research prototype, about 60 s): builds a DISPOSABLE synthetic ledger with the ordinary service commands, shows the frozen product's
decision, runs the read-only ordering diagnostic on a copy, replays the counterexample through the frozen capture path into a separate scratch
ledger, and shows that the demo ledger is unchanged. Nothing here touches any other ledger, starts a server or sends anything. It is not connected
to the operational UI or the shipment gate.

usage: python -B research/order_firewall/demo_a7.py [--keep DIR] [--json OUT.json]
"""
import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import firewall as FW  # noqa: E402
import replay_check as RC  # noqa: E402
from application.anchors import TrustedAnchor, export_anchor, publish_candidate  # noqa: E402

BAR = "=" * 100
WARNING = "[RESEARCH ONLY - synthetic data - does NOT block shipment - NOT a clearance - not connected to the product UI or shipment gate]"
WITNESS_TYPES = ("SLOT_STATE_VERIFIED", "COMPONENT_REMOVED", "COMPONENT_INSTALLED")


def files_of(directory):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(directory).iterdir() if p.is_file()}


def section(title):
    print(); print(WARNING); print(title)


def build(d):
    db = d / "ledger.sqlite"
    app = FW.Manufacturing(db)
    try:
        app.create_unit("MTR-26100"); app.assemble("MTR-26100", "BR-310", "BR-312")
        app.create_unit("MTR-DEMO-1"); app.assemble("MTR-DEMO-1", "BR-310", "BR-312")
        app.announce("BR-204", ["DE"])
        app.observe("MTR-26100", "QX-77")              # operator reports an unregistered label on the DE bearing ...
        app.replace("MTR-26100", "BR-312")             # ... and the DE bearing is replaced (a different, untrusted source clock)
        app.snapshot()
        publish_candidate(d / "root.json", export_anchor(app))
        snap = app.snapshot(trusted_anchor=TrustedAnchor(d / "root.json"))
        policy = app.policy()["policyId"]
    finally:
        app.close()
    return db, snap, policy


def witness_rows(timeline, changed):
    moved = {c["eventId"] for c in changed}
    for e in timeline:
        if e["eventType"] in WITNESS_TYPES and e["slot"] == "DE" and e["occurredAt"] >= "2026-10-20":
            mark = "  <- shifted" if e["eventId"] in moved else ""
            print(f"      {e['occurredAt']}  rec {e['recordedAt']}  {e['sourceId']:<20} #{e['sourceSeq']}  {e['eventType']:<20} {e['lot'] or '':<7}{mark}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--keep", help="build the disposable ledger in this NEW directory instead of a temp directory")
    ap.add_argument("--json", help="also write the full diagnostic report here")
    a = ap.parse_args()
    base = Path(a.keep) if a.keep else Path(tempfile.mkdtemp(prefix="a7-demo-"))
    live = base / "demo-ledger"
    live.mkdir(parents=True, exist_ok=False)

    print(BAR); print("A7 EVENT-ORDERING DIAGNOSTIC - judge demo (research prototype; no server, no network)"); print(WARNING); print(BAR)
    print(FW.NOTICE)
    db, snap, policy = build(live)
    section(f"1. RECORDED: the frozen product on the demo ledger (checkpoint {snap['checkpoint']['state']})")
    for m in ("MTR-26100", "MTR-DEMO-1"):
        cur = snap["decisions"][m][policy]["current"]
        print(f"   {m}: {cur['operationalAction']:<16} releaseEligible={snap['eligibility'][m]['currentReleaseEligible']}")
    before = files_of(live)

    rep = FW.run(db, workdir=base / "diagnostic-copy")
    r, ctrl = rep["motors"]["MTR-26100"], rep["motors"]["MTR-DEMO-1"]
    c = r["counterexample"]
    section("2. TIME ASSUMPTIONS (the motor's own declared profile; nothing here is an authenticated clock)")
    print(f"   * every timestamp is SYNTHETIC_SIMULATED; trusted time sources: {r['trustedTimeSources'] or 'none'}")
    print(f"   * each source's clock may be off by ONE constant offset, |offset| <= declared skew {r['skewSeconds']} s (an assumption; the frozen")
    print("     evaluator itself gives untrusted clocks no bound at all)")
    print("   * a source's own sequence order is authoritative and kept; recordedAt >= occurredAt, capture sessions and references must still hold")
    print("   * an admissible REPORTED timeline is not the physical history: on this host the commands really ran sighting -> replacement")

    section(f"3. COUNTEREXAMPLE: MTR-26100 -> {r['classification']}   witness offsets {c['offsets']}")
    print("   recorded timeline (DE slot, 20 Oct):"); witness_rows(r["original"]["timeline"], [])
    print(f"   admissible alternative (HANDHELD clock {c['offsets']['HANDHELD:MTR-26100']:+d} s, all its events shift together):"); witness_rows(c["timeline"], c["changed"])
    print("   the sighting is no longer strictly earlier than the replacement install, so the UNCHANGED identity guard keeps it:")
    print(f"      {r['original']['decision']['operationalAction']} -> {c['decision']['operationalAction']} (identity {c['decision']['identityFindings']}); "
          f"frozen evaluator stays {c['decision']['evaluatorOperationalAction']}")
    print("   150 s is the smallest single-source shift (149 s does not flip it); +151 s to +300 s (sighting strictly later) also hold,")
    print("   so the result does not depend on how a same-second tie is treated")

    events = FW.load_evidence(db, workdir=base / "replay-input")["motors"]["MTR-26100"]
    alt = RC.replay(events, FW.shift(events["case"]["events"], c["offsets"]), base / "replay-scratch")
    section("4. ADMISSIBILITY CHECK: the alternative timeline replayed through the FROZEN capture path into a separate scratch ledger")
    print(f"   frozen capture accepted every event; checkpoint {alt['checkpoint']}; decision {alt['operationalAction']}; releaseEligible={alt['releaseEligible']}")

    section(f"5. CONTRAST: MTR-DEMO-1 -> {ctrl['classification']} ({ctrl['ordersEvaluated']} realizations evaluated)")
    print("   NOT A CLEARANCE: no counterexample was found among the evaluated realizations; the search is bounded, not exhaustive.")
    after = files_of(live)
    section(f"6. READ-ONLY: demo ledger byte-identical after the diagnostic: {after == before and rep['sourceUnchanged']}")
    print("   The diagnostic has no write path to any ledger; it does NOT block shipment, does NOT provide clearance and changes no decision.")
    print("   Guard finding (lot_identity.py raw occurredAt comparison) is recorded as a P1 candidate for owner review; v1.2 is not modified.")
    print(BAR); print(WARNING); print(BAR)
    if a.json:
        Path(a.json).write_text(json.dumps(dict(report=rep, frozenReplay=alt), indent=1, default=str), encoding="utf-8")
    return 0 if after == before and rep["sourceUnchanged"] and alt["operationalAction"] == "RECALL_HOLD" else 1


if __name__ == "__main__":
    sys.exit(main())
