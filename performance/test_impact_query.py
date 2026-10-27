"""Independent hand-authored input/expectation tests; no production oracle or evaluator edits."""
import json
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from application.service import Manufacturing, ShipmentRefused, digest
from performance.impact_query import ImpactQuery, ImpactUnavailable

class ImpactTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="pramaan-impact-test-")
        self.path=Path(self.temp.name)/"ledger.sqlite"
        self.app=Manufacturing(self.path)
        for m in ("MTR-IMPACT-001","MTR-IMPACT-002","MTR-IMPACT-003","MTR-IMPACT-004"):
            self.app.create_unit(m)
        for m,de in (("MTR-IMPACT-001","BR-204"),("MTR-IMPACT-002","BR-310"),("MTR-IMPACT-003","BR-310")):
            self.app.assemble(m,de,"BR-312");self.app.record_historical_shipment_fixture(m)
        self.app.observe("MTR-IMPACT-003","BR-2O4")
        self.reader=ImpactQuery(self.path);self.reader.rebuild()
    def tearDown(self):
        self.reader.close();self.app.close();self.temp.cleanup()
    def query(self):return self.reader.query("BR-204")
    def test_preserves_hit_unknown_sighting_and_unassembled_motor(self):
        r=self.query();self.assertEqual({m["motorSerial"] for m in r["motors"]},{"MTR-IMPACT-001","MTR-IMPACT-003","MTR-IMPACT-004"})
        sight=next(m for m in r["motors"] if m["motorSerial"]=="MTR-IMPACT-003")
        self.assertTrue(sight["observationEvidence"]);self.assertIn("OBSERVATION_REQUIRES_EVALUATION",sight["uncertaintyReasons"])
    def test_shipments_are_verified_recorded_claims_not_authorization(self):
        hit=next(m for m in self.query()["motors"] if m["motorSerial"]=="MTR-IMPACT-001")
        ship=hit["shipments"][0];self.assertEqual(ship["shipmentId"],"SHP-26-IMPACT-001")
        event=next(e for e in self.app.events(hit["motorSerial"]) if e["eventId"]==ship["evidence"]["eventId"])
        self.assertEqual(event["payload"]["shipmentId"],ship["shipmentId"])
        self.assertEqual(ship["shippedAt"],event["occurredAt"]);self.assertFalse(ship["releaseAuthorization"])
        self.assertEqual(self.query()["operationalClearance"],"NOT_ASSESSED")
        self.app.create_unit("MTR-IMPACT-005");self.app.assemble("MTR-IMPACT-005","BR-310","BR-312")
        with self.assertRaises(ShipmentRefused):self.app.ship("MTR-IMPACT-005")
    def test_unknown_query_includes_entire_fleet(self):
        r=self.reader.query("BR-2O4");self.assertEqual(len(r["motors"]),4)
        self.assertTrue(all("QUERY_LOT_IDENTITY_UNESTABLISHED" in m["uncertaintyReasons"] for m in r["motors"]))
    def test_new_evidence_cannot_use_old_index(self):
        self.app.observe("MTR-IMPACT-002","BR-204")
        with self.assertRaisesRegex(ImpactUnavailable,"EVIDENCE_CHANGED"):self.query()
        with self.assertRaisesRegex(ImpactUnavailable,"VERIFIED_INDEX_REQUIRED"):self.query()
        self.reader.rebuild();self.assertEqual(len(self.query()["motors"]),4)
    def test_raw_capture_mutation_same_heads_and_counts_is_detected(self):
        with self.app.db:self.app.db.execute("DROP TRIGGER captures_no_update")
        self.reader.rebuild()  # schema now unchanged across the actual raw-byte mutation
        with self.app.db:
            self.app.db.execute("UPDATE captures SET raw=replace(cast(raw as text),'BR-204','BR-999') WHERE hash=(SELECT capture FROM events WHERE motor='MTR-IMPACT-001' LIMIT 1)")
        with self.assertRaises(ImpactUnavailable):self.query()
        with self.assertRaisesRegex(ImpactUnavailable,"INPUT_VERIFICATION_FAILED"):self.reader.rebuild()
    def test_native_mutation_cannot_be_used_after_rebuild(self):
        with self.app.db:
            self.app.db.execute("DROP TRIGGER events_no_update")
            self.app.db.execute("UPDATE events SET native=replace(native,'BR-204','BR-999') WHERE motor='MTR-IMPACT-001'")
        with self.assertRaises(ImpactUnavailable):self.reader.rebuild()
        with self.assertRaisesRegex(ImpactUnavailable,"VERIFIED_INDEX_REQUIRED"):self.query()
    def test_rejection_blocks_even_with_prior_good_evidence(self):
        with self.app.db:self.app.db.execute("INSERT INTO rejections(motor,raw_hash,reason,received) VALUES(?,?,?,?)",("MTR-IMPACT-002","hash","rejected","2026-10-26T00:00:00Z"))
        with self.assertRaises(ImpactUnavailable):self.query()
        with self.assertRaises(ImpactUnavailable):self.reader.rebuild()
    def test_fleet_membership_changes_are_not_silently_omitted(self):
        self.app.create_unit("MTR-IMPACT-005")
        with self.assertRaises(ImpactUnavailable):self.query()
        self.reader.rebuild();self.assertIn("MTR-IMPACT-005",{m["motorSerial"] for m in self.query()["motors"]})
        with self.app.db:self.app.db.execute("DELETE FROM app_units WHERE serial='MTR-IMPACT-005'")
        with self.assertRaisesRegex(ImpactUnavailable,"FLEET_MEMBERSHIP_MISMATCH"):self.reader.rebuild()
    def test_warm_reuse_keeps_verification_content_bound(self):
        with patch.object(type(self.app.ledger),"_verified_rows",side_effect=AssertionError("no repeated decode")):
            self.query()
        with self.app.db:self.app.db.execute("DROP TRIGGER motors_no_update");self.app.db.execute("UPDATE motors SET hash='tampered' WHERE serial='MTR-IMPACT-001'")
        with self.assertRaises(ImpactUnavailable):self.query()
        with self.assertRaises(ImpactUnavailable):self.reader.rebuild()
    def test_response_cannot_mutate_cached_proof(self):
        r=self.query();r["motors"][0]["shipments"].clear();r["motors"].clear()
        self.assertEqual(len(self.query()["motors"]),3);self.assertTrue(self.query()["motors"][0]["shipments"])
    def test_read_only_no_publication_or_database_mutation(self):
        dump=lambda:list(self.app.db.iterdump())
        before=dump();self.query();self.reader.rebuild();self.assertEqual(before,dump())
        with self.assertRaises(sqlite3.OperationalError):self.reader.db.execute("DELETE FROM app_units")
    def test_registry_edit_invalidates_proof(self):
        path=Path(self.temp.name)/"registry.json";document=json.loads(Path("application/lot_registry.synthetic.json").read_text())
        path.write_text(json.dumps(document));other=ImpactQuery(self.path,registry=path)
        try:
            other.rebuild();document["version"]=999;path.write_text(json.dumps(document))
            with self.assertRaisesRegex(ImpactUnavailable,"EVIDENCE_CHANGED"):other.query("BR-204")
        finally:other.close()
    def test_transaction_linearization_against_concurrent_capture(self):
        original=self.reader._content_key
        def key(registry):
            result=original(registry)
            errors=[]
            def write():
                app=Manufacturing(self.path)
                try:app.observe("MTR-IMPACT-002","BR-204")
                except Exception as e:errors.append(e)
                finally:app.close()
            worker=threading.Thread(target=write);worker.start();worker.join(10)
            self.assertFalse(worker.is_alive());self.assertFalse(errors)
            return result
        with patch.object(self.reader,"_content_key",side_effect=key):
            self.assertEqual(len(self.query()["motors"]),3)  # snapshot preceded concurrent commit
        with self.assertRaisesRegex(ImpactUnavailable,"EVIDENCE_CHANGED"):self.query()
    def test_restart_requires_full_verification_and_errors_are_neutral(self):
        other=ImpactQuery(self.path)
        try:
            with self.assertRaisesRegex(ImpactUnavailable,"VERIFIED_INDEX_REQUIRED"):other.query("BR-204")
            other.close()
            with self.assertRaises(ImpactUnavailable) as ctx:other.query("BR-204")
            self.assertEqual(str(ctx.exception),"INPUT_VERIFICATION_FAILED")
            self.assertNotIn(str(self.path),str(ctx.exception))
        finally:other.close()
    def test_serialized_response_cache_is_immutable_and_still_rehashes(self):
        first=self.reader.query_json("BR-204");self.assertIsInstance(first,bytes)
        self.assertEqual(json.loads(first),self.query())
        self.assertIs(self.reader.query_json("BR-204"),first)
        self.app.observe("MTR-IMPACT-002","BR-204")
        with self.assertRaisesRegex(ImpactUnavailable,"EVIDENCE_CHANGED"):self.reader.query_json("BR-204")
    def test_rebuild_cannot_erase_known_fleet_members(self):
        with self.app.db:
            for t in ("events","motors"):
                self.app.db.execute("DROP TRIGGER "+t+"_no_delete")
            self.app.db.execute("DELETE FROM events WHERE motor='MTR-IMPACT-002'")
            self.app.db.execute("DELETE FROM motors WHERE serial='MTR-IMPACT-002'")
            self.app.db.execute("DELETE FROM app_units WHERE serial='MTR-IMPACT-002'")
        with self.assertRaisesRegex(ImpactUnavailable,"ROLLBACK_DETECTED"):self.reader.rebuild()
    def test_recomputed_configuration_hash_cannot_rewrite_accepted_provisioning(self):
        config=self.app.ledger._config("MTR-IMPACT-002");config["coverage"]["coveragePolicyId"]="REWRITTEN"
        with self.app.db:
            self.app.db.execute("DROP TRIGGER motors_no_update")
            self.app.db.execute("UPDATE motors SET config=?,hash=? WHERE serial='MTR-IMPACT-002'",(json.dumps(config),digest(config)))
        with self.assertRaisesRegex(ImpactUnavailable,"ROLLBACK_OR_CONFIGURATION_REWRITE"):self.reader.rebuild()
    def test_replacement_and_late_correction_keep_historical_exposure_and_sightings(self):
        self.app.replace("MTR-IMPACT-001","BR-310")
        old=next(e for e in self.app.events("MTR-IMPACT-003") if e["eventType"]=="SLOT_STATE_VERIFIED")
        payload=dict(old["payload"],observedLot="BR-310")
        self.app.event("MTR-IMPACT-003","SLOT_STATE_VERIFIED","HANDHELD",payload,supersedes=old["eventId"])
        with self.assertRaises(ImpactUnavailable):self.query()
        self.reader.rebuild();rows={m["motorSerial"]:m for m in self.query()["motors"]}
        self.assertIn("MTR-IMPACT-001",rows);self.assertIn("MTR-IMPACT-003",rows)
        kinds={e["eventType"] for e in rows["MTR-IMPACT-001"]["matchingEvidence"]}
        self.assertEqual(kinds,{"COMPONENT_INSTALLED","COMPONENT_REMOVED"})
        self.assertEqual(len(rows["MTR-IMPACT-003"]["observationEvidence"]),2)
        self.assertEqual(self.query()["operationalClearance"],"NOT_ASSESSED")
    def test_mapped_and_unmapped_reads_have_identical_proofs_and_payloads(self):
        self.reader.db.execute("PRAGMA mmap_size=0")
        baseline=self.reader.query_json("BR-204")
        self.reader.db.execute("PRAGMA mmap_size=1073741824")
        mapped=self.reader.query_json("BR-204")
        self.assertEqual(baseline,mapped)
        self.assertEqual(json.loads(baseline)["contentDigest"],self.reader._key)
        self.assertEqual(self.reader.db.execute("PRAGMA query_only").fetchone()[0],1)
    def test_wal_only_capture_invalidates_mapped_response_without_main_file_change(self):
        self.app.db.execute("PRAGMA wal_autocheckpoint=0")
        self.app.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self.reader.rebuild();self.reader.query_json("BR-204")
        before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.app.observe("MTR-IMPACT-002","BR-204")
        self.assertEqual(before,hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertGreater(Path(str(self.path)+"-wal").stat().st_size,0)
        with self.assertRaisesRegex(ImpactUnavailable,"EVIDENCE_CHANGED"):
            self.reader.query_json("BR-204")
        self.reader.rebuild();self.assertEqual(len(self.query()["motors"]),4)
    def test_invalid_query_never_returns_a_negative_result(self):
        for value in (None,"", "x"*81, "x\n"):
            with self.assertRaises(ImpactUnavailable):self.reader.query(value)
if __name__=="__main__":unittest.main()
