"""A7 judge demo (research prototype, about 60 s): builds a DISPOSABLE synthetic ledger with the ordinary service commands, shows the frozen product's
decision, runs the read-only ordering diagnostic on a copy, replays the counterexample through the frozen capture path into a separate scratch
ledger, and shows that the demo ledger is unchanged. Nothing here touches any other ledger, starts a server or sends anything.

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

BAR = "-" * 100


def files_of(directory):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(directory).iterdir() if p.is_file()}


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


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--keep", help="build the disposable ledger in this NEW directory instead of a temp directory")
    ap.add_argument("--json", help="also write the full diagnostic report here")
    a = ap.parse_args()
    base = Path(a.keep) if a.keep else Path(tempfile.mkdtemp(prefix="a7-demo-"))
    live = base / "demo-ledger"
    live.mkdir(parents=True, exist_ok=False)

    print(BAR); print("A7 EVENT-ORDERING DIAGNOSTIC - judge demo (research prototype; synthetic data; no server, no network)"); print(BAR)
    print(FW.NOTICE); print()
    db, snap, policy = build(live)
    print(f"1. Frozen product on the demo ledger  (checkpoint {snap['checkpoint']['state']})")
    for m in ("MTR-26100", "MTR-DEMO-1"):
        cur = snap["decisions"][m][policy]["current"]
        print(f"   {m}: {cur['operationalAction']:<16} releaseEligible={snap['eligibility'][m]['currentReleaseEligible']}")
    before = files_of(live)

    rep = FW.run(db, workdir=base / "diagnostic-copy")
    r, ctrl = rep["motors"]["MTR-26100"], rep["motors"]["MTR-DEMO-1"]
    print(); print(f"2. Diagnostic on a byte copy: MTR-26100 -> {r['classification']}")
    print(f"   declared clock profile: skew {r['skewSeconds']} s, trusted time sources {r['trustedTimeSources'] or 'none'} (all timestamps SYNTHETIC_SIMULATED)")
    c = r["counterexample"]
    print("   recorded timeline (as the product ordered it):")
    for e in r["original"]["timeline"]:
        if e["eventType"] in ("SLOT_STATE_VERIFIED", "COMPONENT_INSTALLED", "COMPONENT_REMOVED") and e["slot"] in (None, "DE"):
            print(f"      {e['occurredAt']}  {e['sourceId']:<22} #{e['sourceSeq']:<2} {e['eventType']:<20} {e['lot'] or ''}")
    print(f"   minimal admissible counterexample: offsets {c['offsets']} (the whole source shifts; its own sequence is preserved)")
    for ch in c["changed"]:
        print(f"      {ch['eventId']}: occurredAt {ch['occurredAt'][0]} -> {ch['occurredAt'][1]}")
    print(f"   -> the sighting is no longer strictly earlier than the replacement install, so the unchanged guard keeps it:")
    print(f"      {r['original']['decision']['operationalAction']} -> {c['decision']['operationalAction']} (identity {c['decision']['identityFindings']}); "
          f"frozen evaluator stays {c['decision']['evaluatorOperationalAction']}")

    events = FW.load_evidence(db, workdir=base / "replay-input")["motors"]["MTR-26100"]
    alt = RC.replay(events, FW.shift(events["case"]["events"], c["offsets"]), base / "replay-scratch")
    print(); print("3. Independent admissibility check: the shifted timeline replayed through the FROZEN capture path into a separate scratch ledger")
    print(f"   frozen capture accepted every event; checkpoint {alt['checkpoint']}; decision {alt['operationalAction']}; releaseEligible={alt['releaseEligible']}")

    print(); print(f"4. Contrast: MTR-DEMO-1 -> {ctrl['classification']} ({ctrl['ordersEvaluated']} orders evaluated).")
    print("   This is NOT a clearance: it means only that no counterexample was found in the modelled space.")
    after = files_of(live)
    print(); print(f"5. Demo ledger byte-identical after the diagnostic: {after == before and rep['sourceUnchanged']}")
    print("   The diagnostic has no write path to any ledger; it does NOT block shipment, does NOT provide clearance and changes no decision.")
    print("   Guard finding (lot_identity.py raw occurredAt comparison) is recorded as a P1 candidate for owner review; v1.2 is not modified.")
    print(BAR)
    if a.json:
        Path(a.json).write_text(json.dumps(dict(report=rep, frozenReplay=alt), indent=1, default=str), encoding="utf-8")
    return 0 if after == before and rep["sourceUnchanged"] and alt["operationalAction"] == "RECALL_HOLD" else 1


if __name__ == "__main__":
    sys.exit(main())
