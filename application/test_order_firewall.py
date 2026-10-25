"""A7 ordering diagnostic (research prototype): adversarial and read-only tests. Synthetic, disposable ledgers; no network.
Run: python -B -m unittest application.test_order_firewall -v      Set A7_EVIDENCE=<file> to write measured results as JSON.
"""
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research" / "order_firewall"))
import firewall as FW  # noqa: E402
import replay_check as RC  # noqa: E402
from .anchors import TrustedAnchor, export_anchor, publish_candidate
from .service import Manufacturing

W, EVIDENCE = {}, {}


def files_of(directory):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(directory).iterdir() if p.is_file()}


def setUpModule():
    W["tmp"] = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    d = Path(W["tmp"].name) / "live"
    d.mkdir()
    db = W["db"] = d / "ledger.sqlite"
    app = Manufacturing(db)
    try:
        app.create_unit("MTR-26100"); app.assemble("MTR-26100", "BR-310", "BR-312")      # the demonstrated counterexample
        app.create_unit("MTR-DEMO-1"); app.assemble("MTR-DEMO-1", "BR-310", "BR-312")    # clean, built long before the announcement
        app.create_unit("MTR-26101"); app.assemble("MTR-26101", "BR-310", "BR-312")      # control: same commands in the opposite order
        app.announce("BR-204", ["DE"])
        app.observe("MTR-26100", "QX-77"); app.replace("MTR-26100", "BR-312")
        app.replace("MTR-26101", "BR-312"); app.observe("MTR-26101", "QX-77")
        app.create_unit("MTR-26102"); app.assemble("MTR-26102", "BR-310", "BR-312")      # clean, built right after the announcement
        app.snapshot()
        publish_candidate(d / "root.json", export_anchor(app))
        W["live_before"] = app.snapshot(trusted_anchor=TrustedAnchor(d / "root.json"))
    finally:
        app.close()
    W["dir_before"] = files_of(d)
    W["report"] = FW.run(db, cap=20000, workdir=Path(W["tmp"].name) / "copy1")
    W["ev"] = FW.load_evidence(db, workdir=Path(W["tmp"].name) / "copy2")["motors"]
    W["dir_after_diagnostic"] = files_of(d)          # taken before anything else touches the directory (the product's own snapshot writes audit rows)
    app = Manufacturing(db)
    try:
        W["live_after"] = app.snapshot(trusted_anchor=TrustedAnchor(d / "root.json"))
    finally:
        app.close()


def tearDownModule():
    out = os.environ.get("A7_EVIDENCE")
    if out:
        Path(out).write_text(json.dumps(EVIDENCE, indent=1, sort_keys=True, default=str), encoding="utf-8")
    W["tmp"].cleanup()


def ev(m):
    return copy.deepcopy(W["ev"][m]) if m != "MTR-26100" else W["ev"][m]


def with_profile(m, skew=None, trusted=None):
    e = copy.deepcopy({k: v for k, v in W["ev"][m].items() if k != "registry"}); e["registry"] = W["ev"][m]["registry"]
    a = e["coverage"]["slotAttribution"]
    if skew is not None:
        a["observationClockSkewSeconds"] = skew
    if trusted is not None:
        a["trustedTimeSources"] = trusted
    return e


class Counterexample(unittest.TestCase):
    def test_reproduces_the_demonstrated_counterexample_with_a_minimal_single_source_witness(self):
        r = W["report"]["motors"]["MTR-26100"]
        self.assertEqual(r["classification"], "ORDER_SENSITIVE")
        self.assertEqual(r["original"]["decision"]["operationalAction"], "RELEASE_ELIGIBLE")
        c = r["counterexample"]
        self.assertEqual(c["offsets"], {"HANDHELD:MTR-26100": 150})
        self.assertEqual((c["decision"]["operationalAction"], c["decision"]["identityFindings"]), ("RECALL_HOLD", ["UNREGISTERED"]))
        self.assertEqual(c["decision"]["evaluatorOperationalAction"], "RELEASE_ELIGIBLE")            # the frozen evaluator is order-robust here; the guard is not
        self.assertEqual([x["eventId"] for x in c["changed"]], ["urn:pramaan:MTR-26100:HANDHELD:1"])
        smaller = FW.shift(W["ev"]["MTR-26100"]["case"]["events"], {"HANDHELD:MTR-26100": 149})
        self.assertEqual(FW.decide(W["ev"]["MTR-26100"], smaller)["operationalAction"], "RELEASE_ELIGIBLE")   # 149 s does not flip: 150 is minimal
        EVIDENCE["counterexample"] = dict(offsets=c["offsets"], changed=c["changed"], original=r["original"]["decision"], alternative=c["decision"])

    def test_frozen_capture_accepts_the_witness_and_the_frozen_product_then_holds(self):
        e = W["ev"]["MTR-26100"]
        shifted = FW.shift(e["case"]["events"], W["report"]["motors"]["MTR-26100"]["counterexample"]["offsets"])
        self.assertEqual(FW.violations(e, W["report"]["motors"]["MTR-26100"]["counterexample"]["offsets"], shifted), [])
        alt = RC.replay(e, shifted, Path(W["tmp"].name) / "replay-witness")
        orig = RC.replay(e, e["case"]["events"], Path(W["tmp"].name) / "replay-original")
        self.assertEqual((orig["checkpoint"], orig["operationalAction"], orig["releaseEligible"]), ("ANCHORED_CURRENT", "RELEASE_ELIGIBLE", True))
        self.assertEqual((alt["checkpoint"], alt["operationalAction"], alt["releaseEligible"]), ("ANCHORED_CURRENT", "RECALL_HOLD", False))
        EVIDENCE["frozenReplay"] = dict(original=orig, witness=alt)

    def test_opposite_command_order_is_order_sensitive_in_the_other_direction(self):
        r = W["report"]["motors"]["MTR-26101"]
        self.assertEqual(r["original"]["decision"]["operationalAction"], "RECALL_HOLD")
        self.assertEqual(r["classification"], "ORDER_SENSITIVE")
        self.assertEqual(r["counterexample"]["decision"]["operationalAction"], "RELEASE_ELIGIBLE")
        EVIDENCE["oppositeDirection"] = dict(offsets=r["counterexample"]["offsets"])

    def test_decision_function_matches_the_live_product_for_every_motor(self):
        for m, e in W["ev"].items():
            mine = FW.decide(e, e["case"]["events"])
            live = W["live_before"]["decisions"][m]["RC-026-014/P1"]["current"]
            self.assertEqual((mine["operationalAction"], mine["evidenceFinding"], mine["reasonCodes"]),
                             (live["operationalAction"], live["evidenceFinding"], live["reasonCodes"]), m)


class SourceOrderAndClocks(unittest.TestCase):
    def test_constant_offsets_never_reorder_events_of_one_source(self):
        e = W["ev"]["MTR-26100"]
        for offs in ({"REWORK:MTR-26100": -300}, {"MES:MTR-26100": 300, "HANDHELD:MTR-26100": -300}):
            shifted = FW.shift(e["case"]["events"], offs)
            for s in {x["sourceId"] for x in shifted}:
                seq = [x for x in sorted(shifted, key=lambda x: x["occurredAt"]) if x["sourceId"] == s]
                self.assertEqual([x["sourceSeq"] for x in seq], sorted(x["sourceSeq"] for x in seq), s)

    def test_moving_one_event_of_a_source_alone_is_inadmissible(self):
        """The first (flawed) probe moved only the replacement install 151 s earlier; that reorders it before its own source's removal."""
        e = W["ev"]["MTR-26100"]
        events = copy.deepcopy(e["case"]["events"])
        inst = [x for x in events if x["eventType"] == "COMPONENT_INSTALLED" and x["sourceId"] == "REWORK:MTR-26100"][-1]
        for k in ("occurredAt", "recordedAt"):
            inst[k] = FW._s(FW._t(inst[k]) - FW.timedelta(seconds=151))
        self.assertTrue(any("regression" in v for v in FW.violations(e, {}, events)))

    def test_trusted_clocks_pin_every_source(self):
        e = with_profile("MTR-26100", trusted=["SYNTHETIC_SIMULATED"])
        self.assertEqual(FW.movable_sources(e), set())
        r = FW.analyse(e)
        self.assertIsNone(r["counterexample"])
        self.assertEqual(r["classification"], "NOT_EXHAUSTIVE")           # announcement within skew of an event: stated, never "no counterexample"
        self.assertTrue(FW.violations(e, {"HANDHELD:MTR-26100": 150}, FW.shift(e["case"]["events"], {"HANDHELD:MTR-26100": 150})))

    def test_simulated_timestamps_are_never_treated_as_trusted_by_default(self):
        self.assertEqual(W["report"]["motors"]["MTR-26100"]["trustedTimeSources"], [])
        self.assertIn("HANDHELD:MTR-26100", W["report"]["motors"]["MTR-26100"]["movableSources"])

    def test_skew_boundaries(self):
        """The decisive quantity is the RELATIVE shift between the sighting's and the install's sources (150 s reaches the tie)."""
        self.assertEqual(FW.analyse(with_profile("MTR-26100", skew=150))["counterexample"]["offsets"], {"HANDHELD:MTR-26100": 150})
        r149 = FW.analyse(with_profile("MTR-26100", skew=149))                # no single source can do it; two sources together can
        self.assertEqual(r149["classification"], "ORDER_SENSITIVE")
        offs = r149["counterexample"]["offsets"]
        self.assertGreaterEqual(len(offs), 2)
        self.assertTrue(all(abs(v) <= 149 for v in offs.values()))
        self.assertEqual(FW.violations(with_profile("MTR-26100", skew=149), offs, FW.shift(W["ev"]["MTR-26100"]["case"]["events"], offs)), [])
        r74 = FW.analyse(with_profile("MTR-26100", skew=74))                  # at most 148 s relative: the flip is out of reach
        self.assertIsNone(r74["counterexample"])
        self.assertNotEqual(r74["classification"], "ORDER_SENSITIVE")
        e = W["ev"]["MTR-26100"]
        self.assertTrue(any("exceeds declared skew" in v for v in FW.violations(e, {"HANDHELD:MTR-26100": 301}, FW.shift(e["case"]["events"], {"HANDHELD:MTR-26100": 301}))))
        with self.assertRaises(ValueError):
            bad = with_profile("MTR-26100"); bad["coverage"]["slotAttribution"].pop("observationClockSkewSeconds")
            FW.analyse(bad)
        EVIDENCE["skewBoundaries"] = dict(skew150={"HANDHELD:MTR-26100": 150}, skew149=offs, skew74=r74["classification"])

    def test_session_and_reference_constraints_reject_inadmissible_offsets(self):
        e = W["ev"]["MTR-26100"]
        offs = {"ASSY:MTR-26100": -300}                                       # installs recorded before the bearing records they reference
        v = FW.violations(e, offs, FW.shift(e["case"]["events"], offs))
        self.assertTrue(any("recorded later" in x for x in v), v)
        e2 = with_profile("MTR-26100"); e2["sessions"] = [dict(s, to="2026-10-20T08:02:00Z") if s["sourceId"] == "HANDHELD:MTR-26100" else s for s in e2["sessions"]]
        self.assertTrue(any("capture session" in x for x in FW.violations(e2, {"HANDHELD:MTR-26100": 150}, FW.shift(e2["case"]["events"], {"HANDHELD:MTR-26100": 150}))))


class ReplaySupersessionAndCap(unittest.TestCase):
    def test_superseding_record_cannot_be_moved_before_its_target(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            db = Path(d) / "l.sqlite"
            app = Manufacturing(db)
            try:
                app.create_unit("MTR-26200"); app.assemble("MTR-26200", "BR-310", "BR-312"); app.announce("BR-204", ["DE"])
                old = next(x for x in app.events("MTR-26200") if x["eventType"] == "COMPONENT_INSTALLED" and x["payload"]["slot"] == "DE")
                made = app.manufacture("MTR-26200", "BR-310", "BRG-MTR-26200-DE-C1")
                app.event("MTR-26200", "COMPONENT_INSTALLED", "REWORK", dict(old["payload"], serial="BRG-MTR-26200-DE-C1", manufacturingEventId=made["eventId"]),
                          work_order=old["workOrderId"], supersedes=old["eventId"], occurred=old["occurredAt"])
            finally:
                app.close()
            e = FW.load_evidence(db, workdir=Path(d) / "c")["motors"]["MTR-26200"]
            offs = {"REWORK:MTR-26200": -300}
            self.assertTrue(any("recorded later" in x for x in FW.violations(e, offs, FW.shift(e["case"]["events"], offs))))
            r = FW.analyse(e, cap=2000)
            self.assertIn(r["classification"], FW.CLASSES)
            if r["counterexample"]:
                self.assertEqual(FW.violations(e, r["counterexample"]["offsets"], FW.shift(e["case"]["events"], r["counterexample"]["offsets"])), [])
            EVIDENCE["supersession"] = dict(classification=r["classification"], original=r["original"]["decision"]["operationalAction"])

    def test_repeated_runs_are_deterministic_and_use_fresh_copies(self):
        again = FW.run(W["db"], cap=20000, workdir=Path(W["tmp"].name) / "copy3")
        strip = lambda rep: {m: {k: v for k, v in r.items()} for m, r in rep["motors"].items()}  # noqa: E731
        self.assertEqual(json.dumps(strip(again), sort_keys=True, default=str), json.dumps(strip(W["report"]), sort_keys=True, default=str))
        self.assertNotEqual(again["analysedCopy"], W["report"]["analysedCopy"])

    def test_capped_search_is_labelled_not_exhaustive(self):
        r = FW.analyse(ev("MTR-DEMO-1"), cap=1)
        self.assertEqual(r["classification"], "NOT_EXHAUSTIVE")
        self.assertTrue(any("cap" in n and "NOT examined" in n for n in r["notes"]))

    def test_no_counterexample_only_when_exhaustive_and_never_as_clearance(self):
        r = W["report"]["motors"]["MTR-DEMO-1"]
        self.assertEqual(r["classification"], "NO_COUNTEREXAMPLE_FOUND")
        self.assertLess(r["ordersEvaluated"], 20000)
        self.assertTrue(any("Not a clearance" in n for n in r["notes"]))
        near = with_profile("MTR-DEMO-1")
        near["policy"] = dict(near["policy"], announcedAt=near["case"]["events"][2]["occurredAt"])   # a fixed date the logic compares against, within the skew
        r2 = FW.analyse(near)
        self.assertEqual(r2["classification"], "NOT_EXHAUSTIVE")
        self.assertTrue(any("policy.announcedAt" in n for n in r2["notes"]))
        EVIDENCE["classes"] = {m: (r["classification"], r.get("ordersEvaluated"), r.get("singleSourceTimelinesEvaluated")) for m, r in W["report"]["motors"].items()}


class ReadOnlyAndBoundaries(unittest.TestCase):
    def test_live_ledger_directory_is_byte_identical_and_no_side_files_appear(self):
        self.assertTrue(W["report"]["sourceUnchanged"])
        self.assertEqual(W["dir_after_diagnostic"], W["dir_before"])

    def test_live_decisions_checkpoint_and_eligibility_are_unchanged(self):
        after = W["live_after"]
        for k in ("decisions", "eligibility"):
            self.assertEqual(json.dumps(after[k], sort_keys=True), json.dumps(W["live_before"][k], sort_keys=True), k)
        self.assertEqual(after["checkpoint"]["state"], "ANCHORED_CURRENT")

    def test_static_boundaries(self):
        src = (ROOT / "research" / "order_firewall" / "firewall.py").read_text(encoding="utf-8").split('if __name__ == "__main__":')[0]   # the CLI writes only its report file
        for forbidden in (".capture(", ".event(", "announce(", "replace(", "observe(", ".ship(", "publish_candidate", "checkpoint_ops",
                          "evidence_package", "evidence_verify", "federation", "server", "INSERT", "UPDATE ", "DELETE", "sqlite3.connect"):
            self.assertNotIn(forbidden, src, forbidden)
        self.assertIsNone(re.search(r"\bwrite_text\(|\bopen\([^)]*['\"]w", src.replace("copy_path.write_bytes", "")))
        replay = (ROOT / "research" / "order_firewall" / "replay_check.py").read_text(encoding="utf-8")
        self.assertIn("refuses to write into an existing ledger", replay)

    def test_frozen_components_are_byte_identical_to_the_frozen_manifest(self):
        manifest = json.loads((ROOT / "ci" / "frozen-source.json").read_text())["files"]
        for f in ("recall-engine/pramaan_recall/engine.py", "recall-engine/pramaan_recall/ledger.py", "recall-engine/pramaan_recall/policy.py",
                  "application/lot_identity.py", "application/service.py", "application/anchors.py", "application/checkpoint_ops.py",
                  "application/evidence_package.py", "application/evidence_verify.py", "application/federation/node.py", "integration/pramaan_integration/ledger.py"):
            self.assertEqual(hashlib.sha256((ROOT / f).read_bytes()).hexdigest(), manifest[f], f)

    def test_notice_and_vocabulary(self):
        self.assertIn("does NOT block shipment", FW.NOTICE)
        self.assertIn("does NOT provide clearance", FW.NOTICE)
        text = json.dumps(W["report"])
        for word in ("CLEARED", "SAFE_TO_SHIP", "VERIFIED_SAFE", "AUTHENTICATED_CLOCK"):
            self.assertNotIn(word, text)
        self.assertTrue(all(r["classification"] in FW.CLASSES for r in W["report"]["motors"].values()))


if __name__ == "__main__":
    unittest.main()
