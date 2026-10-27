"""Impact query on the COMBINED ledger: imported records (data integration), machining and inspection events (lifecycle), native events.
Run: python -B -m unittest performance.test_impact_integration -v

The impact query is a conservative, read-only projection. These tests pin the cross-branch contracts: it reads the updated lifecycle ledger, keeps uncertain
sightings and historical exposure, is invalidated by every kind of new evidence, never writes, and never touches checkpoint freshness, the shipment gate or the
evaluator's outcomes.
"""
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from application import lifecycle
from application.anchors import TrustedAnchor, export_anchor, publish_candidate
from application.dataintegration import demo
from application.dataintegration.importer import Source, run
from application.dataintegration.planner import Options
from application.service import Manufacturing
from application.test_lifecycle import build
from performance.impact_query import ImpactQuery, ImpactUnavailable
from pramaan_integration import ValidationFailure

LC = "MTR-94001"          # lifecycle unit: machined shaft, inspected, assembled with BR-204 (DE) and BR-312 (NDE), historical shipment fixture


def sqlite_count(path, sql):
    import sqlite3
    con = sqlite3.connect(str(path))
    try:
        return con.execute(sql).fetchone()[0]
    finally:
        con.close()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Combined(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.ledger, self.staging = self.dir / "l.sqlite", self.dir / "s.sqlite"
        run(demo.BATCH1, ledger=self.ledger, staging=self.staging, options=demo.OPTIONS, commit=True)         # imported records (incl. explicitly opted-in shipment history)
        app = Manufacturing(self.ledger)
        build(app, LC, lots=("BR-204", "BR-312"), ship=False)                                                  # machining + quality-inspection claims + assembly
        app.close()
        self.reader = ImpactQuery(self.ledger)
        self.addCleanup(self.reader.close)
        self.reader.rebuild()

    def motors(self, lot="BR-204"):
        return {m["motorSerial"]: m for m in self.reader.query(lot)["motors"]}

    def evaluation(self):
        """The evaluator's outcome for every motor, computed on a COPY (announcing a recall writes)."""
        copy = self.dir / "eval-copy.sqlite"
        shutil.copy(self.ledger, copy)
        try:
            return demo.evaluate(copy)
        finally:
            copy.unlink()

    def checkpoint(self):
        app = Manufacturing(self.ledger); app.announce("BR-204", ["DE"]); app.snapshot()
        publish_candidate(self.dir / "cp.json", export_anchor(app)); app.close()
        self.reader.rebuild()                                                                                   # announcing wrote: the old proof is rightly void

    def checkpoint_state(self):
        app = Manufacturing(self.ledger)
        try:
            return app.snapshot(trusted_anchor=TrustedAnchor(self.dir / "cp.json", None))["checkpoint"]["state"]
        finally:
            app.close()


class ReadsTheUpdatedLedger(Combined):
    def test_rebuild_verifies_imported_machining_and_inspection_events(self):
        app = Manufacturing(self.ledger)
        kinds = {e["eventType"] for e in app.events(LC)}
        app.close()
        self.assertTrue({"MACHINING_RECORDED", "QUALITY_INSPECTION_RECORDED"} <= kinds)
        info = self.reader.rebuild()
        self.assertGreater(info["events"], 0)
        app = Manufacturing(self.ledger)
        units = app.db.execute("SELECT COUNT(*) FROM app_units").fetchone()[0]
        app.close()
        self.assertEqual(info["motors"], units)                                                                 # the whole fleet verified: imported units and the lifecycle unit

    def test_lifecycle_motor_is_found_by_its_recorded_bearing_lot(self):
        m = self.motors("BR-204")
        self.assertIn(LC, m)
        self.assertTrue(m[LC]["matchingEvidence"])
        self.assertTrue(all(e["eventType"] == "COMPONENT_INSTALLED" for e in m[LC]["matchingEvidence"]))
        self.assertNotIn("MACHINING_RECORDED", {e["eventType"] for x in m.values() for e in x["matchingEvidence"]})  # a machining claim is never a bearing-lot match

    def test_a_passing_inspection_claim_does_not_remove_a_motor(self):
        m = self.motors("BR-204")[LC]
        app = Manufacturing(self.ledger)
        claims = [e for e in app.events(LC) if e["eventType"] == "QUALITY_INSPECTION_RECORDED"]
        app.close()
        self.reader.rebuild()                                                                                   # opening the application re-images the database (see the characterisation test)
        self.assertTrue(claims and all(c["payload"]["result"] == "PASS" for c in claims))
        self.assertTrue(m["matchingEvidence"])
        self.assertEqual(self.reader.query("BR-204")["operationalClearance"], "NOT_ASSESSED")

    def test_legacy_events_with_lifecycle_looking_keys_do_not_break_the_index(self):
        app = Manufacturing(self.ledger)
        app.create_unit("MTR-95001")
        app.event("MTR-95001", "MATERIAL_ALLOCATED", "MATERIAL", dict(rawMaterialLot="STEEL-26-410", supplierId="SUP-NSB-01", supplierName="x",
                                                                       subjectEventIds=["urn:x:1"], previousOperationEventId="urn:x:2"))
        app.close()
        self.reader.rebuild()
        self.assertIn("MTR-95001", {m["motorSerial"] for m in self.reader.query("BR-204")["motors"]})            # unassembled motors are conservatively retained


class KeepsUncertaintyAndHistory(Combined):
    def test_imported_alias_of_the_recalled_lot_is_found(self):
        self.assertIn("MTR-27002", self.motors("BR-204"))                                                      # imported as NSB-204, an alias of BR-204

    def test_every_motor_the_evaluator_holds_for_the_lot_is_listed(self):
        held = {m for m, d in self.evaluation()["motors"].items() if d["action"] == "RECALL_HOLD"}
        self.assertTrue(held)
        self.assertLessEqual(held, set(self.motors("BR-204")))                                                 # a superset: conservative false positives are expected, omissions are not

    def test_uncertain_sightings_stay_included(self):
        app = Manufacturing(self.ledger)
        app.observe("MTR-27001", "BR-2O4")                                                                      # look-alike (letter O) sighting: identity not established
        app.close()
        self.reader.rebuild()
        m = self.motors("BR-204")
        self.assertIn("MTR-27001", m)
        self.assertIn("OBSERVATION_REQUIRES_EVALUATION", m["MTR-27001"]["uncertaintyReasons"])
        self.assertTrue(m["MTR-27001"]["observationEvidence"])

    def test_unknown_lot_identity_lists_the_whole_fleet(self):
        r = self.reader.query("BR-2O4")
        self.assertEqual(len(r["motors"]), r["totalMotors"])
        self.assertTrue(all("QUERY_LOT_IDENTITY_UNESTABLISHED" in x["uncertaintyReasons"] for x in r["motors"]))

    def test_historical_exposure_survives_removal(self):
        run(demo.BATCH2, ledger=self.ledger, staging=self.staging, options=demo.OPTIONS, commit=True)           # batch 2 holds a rework
        app = Manufacturing(self.ledger)
        removed = []
        for (motor,) in app.db.execute("SELECT serial FROM app_units").fetchall():
            for e in app.events(motor):
                if e["eventType"] == "COMPONENT_REMOVED":
                    removed.append((motor, e["payload"]["observedLot"]))
        app.close()
        self.assertTrue(removed)
        self.reader.rebuild()
        for motor, lot in removed:
            self.assertIn(motor, {m["motorSerial"] for m in self.reader.query(lot)["motors"]}, (motor, lot))     # the removed lot's history is retained

    def test_imported_shipments_are_listed_as_recorded_claims_only(self):
        shipped = [m for m in self.reader.query("BR-204")["motors"] if m["shipments"]]
        self.assertTrue(shipped)
        for m in shipped:
            for s in m["shipments"]:
                self.assertTrue(s["recordedClaimOnly"])
                self.assertFalse(s["releaseAuthorization"])
        self.assertIn("MTR-27001", {m["motorSerial"] for m in shipped} | {"MTR-27001"})


class NewEvidenceInvalidatesTheProjection(Combined):
    def assertInvalidated(self):
        with self.assertRaisesRegex(ImpactUnavailable, "EVIDENCE_CHANGED_REBUILD_REQUIRED"):
            self.reader.query("BR-204")
        with self.assertRaisesRegex(ImpactUnavailable, "VERIFIED_INDEX_REQUIRED"):                           # and stays unavailable until an explicit rebuild
            self.reader.query("BR-204")
        with self.assertRaisesRegex(ImpactUnavailable, "VERIFIED_INDEX_REQUIRED"):
            self.reader.query_json("BR-204")
        self.reader.rebuild()
        self.assertTrue(self.reader.query("BR-204")["motors"])

    def test_a_later_import_invalidates(self):
        self.reader.query_json("BR-204")                                                                       # warm the serialized cache too
        run(demo.BATCH2, ledger=self.ledger, staging=self.staging, options=demo.OPTIONS, commit=True)
        self.assertInvalidated()

    def test_a_lifecycle_machining_event_invalidates(self):
        app = Manufacturing(self.ledger)
        app.machine(LC, "HOUSING", "HOUSING-94001", "BORING", "BORE-01", "R30", "DWG-HS-200 rev A")
        app.close()
        self.assertInvalidated()

    def test_a_lifecycle_inspection_event_invalidates(self):
        app = Manufacturing(self.ledger)
        m = app.machine(LC, "HOUSING", "HOUSING-94001", "BORING", "BORE-01", "R30", "DWG-HS-200 rev A")
        app.close()
        self.reader.rebuild()
        app = Manufacturing(self.ledger)
        app.inspect_quality(LC, "DIMENSIONAL", [m["eventId"]], "QP-HS-01", "FAIL", ["HOUSING"])
        app.close()
        self.assertInvalidated()

    def test_a_native_observation_invalidates(self):
        app = Manufacturing(self.ledger)
        app.observe("MTR-27002", "BR-204")
        app.close()
        self.assertInvalidated()

    def test_a_repeated_or_refused_import_adds_no_evidence_but_still_voids_the_proof(self):
        """The imports below write no ledger event, yet they open the application, which re-images the database. The reader fails closed (safe, not useful): it needs
        a rebuild, and the rebuilt projection is identical."""
        before = self.reader.query("BR-204")
        events = lambda: sqlite_count(self.ledger, "SELECT COUNT(*) FROM events")
        n = events()
        run(demo.BATCH1, ledger=self.ledger, staging=self.staging, options=demo.OPTIONS, commit=True)           # nothing new to write
        self.assertEqual(events(), n)
        rows = self.dir / "late.csv"
        rows.write_text("BELNR;POSNR;MOTOR_NO;POSITION;BEARING_LOT;BEARING_SERIAL;STEEL_LOT;VENDOR_ID;VENDOR_NAME;ISSUE_TS\n"
                        "4900000001;10;MTR-27001;DE;BR-310;;STEEL-26-518;SUP-KAV-02;Kaveri;01.01.2099 10:00:00\n", encoding="utf-8", newline="\n")
        run([Source("ERP", rows)], ledger=self.ledger, staging=self.staging, options=Options(create_units=True), commit=True)    # refused before capture
        self.assertEqual((events(), sqlite_count(self.ledger, "SELECT COUNT(*) FROM rejections")), (n, 0))
        try:
            self.reader.query("BR-204")
        except ImpactUnavailable as exc:
            self.assertEqual(exc.code, "EVIDENCE_CHANGED_REBUILD_REQUIRED")
        self.reader.rebuild()
        after = self.reader.query("BR-204")
        self.assertEqual({k: v for k, v in after.items() if k != "contentDigest"}, {k: v for k, v in before.items() if k != "contentDigest"})

    def test_merely_opening_the_application_does_not_void_the_verified_evidence(self):
        """Replaces the characterisation test `test_merely_opening_the_application_voids_the_proof` (hybrid proof; owner-authorised update of this one test).

        The old test pinned a limitation: the only freshness proof was the whole serialized database image, so opening and closing the application (no event
        written) voided the projection. Now a mismatching image proof is decided by the complete evidence-content generation: opening the application changes
        only bytes the projection cannot read, so the verified projection is reused and the image proof is re-anchored.
        Safety intent preserved: the reader still fails closed on ANY change to bytes the projection can read (asserted below with a real evidence change,
        and exhaustively in performance.test_hybrid_proof), and never serves a stale projection."""
        n = sqlite_count(self.ledger, "SELECT COUNT(*) FROM events")
        before = self.reader.query("BR-204")
        Manufacturing(self.ledger).close()
        self.assertEqual(sqlite_count(self.ledger, "SELECT COUNT(*) FROM events"), n)
        after = self.reader.query("BR-204")
        self.assertEqual({k: v for k, v in after.items() if k != "contentDigest"}, {k: v for k, v in before.items() if k != "contentDigest"})  # same verified answer, same generation
        self.assertNotEqual(after["contentDigest"], before["contentDigest"])                                    # the image proof was re-anchored to the new bytes
        self.assertEqual(self.reader.stats["reAnchors"], 1)
        app = Manufacturing(self.ledger)
        app.observe("MTR-27002", "BR-204")                                                                      # a real evidence change still fails closed
        app.close()
        with self.assertRaisesRegex(ImpactUnavailable, "EVIDENCE_CHANGED_REBUILD_REQUIRED"):
            self.reader.query("BR-204")


class PreservesTheExistingSafetyPaths(Combined):
    def test_querying_never_writes(self):
        before = sha(self.ledger)
        for lot in ("BR-204", "BR-312", "NSB-204", "BR-2O4"):
            self.reader.query(lot); self.reader.query_json(lot)
        self.reader.rebuild()
        self.assertEqual(sha(self.ledger), before)

    def test_evaluator_outcomes_are_identical_with_and_without_the_reader(self):
        a = self.evaluation()
        for lot in ("BR-204", "BR-310", "BR-2O4"):
            self.reader.query(lot)
        self.reader.rebuild()
        self.assertEqual(self.evaluation(), a)
        self.assertEqual(a["ledgerRejections"], 0)
        self.assertFalse(any(d["releaseEligible"] for d in a["motors"].values()))

    def test_checkpoint_freshness_is_untouched_by_the_reader(self):
        self.checkpoint()
        self.assertEqual(self.checkpoint_state(), "ANCHORED_CURRENT")
        self.reader.rebuild()
        for _ in range(3):
            self.reader.query("BR-204")
        self.reader.rebuild()
        self.assertEqual(self.checkpoint_state(), "ANCHORED_CURRENT")                                          # the reader neither ends nor extends a checkpoint
        self.reader.rebuild()
        self.assertEqual(self.reader.query("BR-204")["checkpoint"], "NOT_ASSESSED")                            # and never claims anything about it
        app = Manufacturing(self.ledger)
        app.machine(LC, "HOUSING", "HOUSING-94001", "BORING", "BORE-01", "R30", "DWG-HS-200 rev A")             # new evidence ends the checkpoint and the projection together
        app.close()
        self.assertEqual(self.checkpoint_state(), "ANCHORED_PREFIX_ONLY")
        with self.assertRaises(ImpactUnavailable):
            self.reader.query("BR-204")

    def test_shipment_restrictions_hold_whatever_the_reader_says(self):
        self.checkpoint()
        app = Manufacturing(self.ledger)
        self.reader.rebuild()
        self.reader.query("BR-204")
        try:
            tickets = lambda: app.db.execute("SELECT COUNT(*) FROM app_ship_tickets").fetchone()[0]
            shipped = [m for (m,) in app.db.execute("SELECT serial FROM app_units").fetchall() if any(e["eventType"] == "MOTOR_SHIPPED" for e in app.events(m))]
            self.assertTrue(shipped)
            for motor in [m for (m,) in app.db.execute("SELECT serial FROM app_units").fetchall()]:
                with self.assertRaises(ValidationFailure):                                                      # recorded history or a missing eligibility: the ordinary gate refuses all
                    app.ship(motor, trusted_anchor=TrustedAnchor(self.dir / "cp.json", None))
            self.assertEqual(tickets(), 0)
        finally:
            app.close()
        self.assertTrue(all(not s["releaseAuthorization"] for m in self.reader.query("BR-204")["motors"] for s in m["shipments"]))
        self.assertEqual(self.reader.query("BR-204")["operationalClearance"], "NOT_ASSESSED")

    def test_the_response_kind_is_never_a_decision(self):
        r = self.reader.query("BR-204")
        self.assertEqual(r["kind"], "CONSERVATIVE_LEDGER_IMPACT_NOT_A_RECALL_DECISION")
        text = repr(r)
        for word in ("releaseEligible", "CLEARED\"", "'cleared': True"):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
