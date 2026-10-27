import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from pramaan_integration import Ledger, LedgerBlocked, ValidationFailure, encode_document
from pramaan_integration import engine_bridge
from pramaan_integration.profile import decode, digest
from integration_tests.scenarios import Scenario, populated

EXCLUDED = "EXCLUDED_WITH_EVIDENCE"


class IntegrationTests(unittest.TestCase):
    def decision(self, scenario):
        ledger = populated(scenario)
        self.addCleanup(ledger.close)
        return ledger, ledger.decide(scenario.motor, scenario.policy, [ledger.watermark(scenario.motor)])[0]

    def assert_hold(self, bundle, reason=None):
        d = bundle["decision"]
        self.assertEqual(d["operationalAction"], "RECALL_HOLD")
        self.assertNotEqual(d["evidenceFinding"], EXCLUDED)
        if reason:
            self.assertIn(reason, d["reasonCodes"])

    def test_clean_replacement_actual_v3_excludes_with_evidence(self):
        s = Scenario()
        ledger, bundle = self.decision(s)
        d = bundle["decision"]
        self.assertEqual(d["evidenceFinding"], EXCLUDED)
        self.assertEqual(d["semanticsProfile"], "UNTRUSTED_OBSERVATION_V3")
        self.assertEqual(d["policyVersion"], 1)
        self.assertTrue(d["evidenceEventIds"])
        native, _ = ledger.snapshot(s.motor, ledger.watermark(s.motor))
        self.assertEqual(native, s.native_case())
        direct = engine_bridge.pramaan_recall.evaluate(s.native_case(), s.policy, s.coverage, ledger.watermark(s.motor), engine_bridge.Config.v3())
        self.assertEqual({key: d[key] for key in direct}, direct)

    def test_query_contains_both_slots_and_removal_reference(self):
        s = Scenario(); ledger, bundle = self.decision(s)
        history = ledger.genealogy(s.motor, bundle["manifest"]["watermark"])["relationships"]
        self.assertEqual(len(history), 4)
        self.assertEqual({r["slot"] for r in history}, {"DE", "NDE"})
        removal = next(r for r in history if r["action"] == "COMPONENT_REMOVED")
        self.assertEqual(removal["payload"]["endsInstallEventId"], s.original["eventId"])

    def test_missing_baseline_remains_unknown_held(self):
        _, b = self.decision(Scenario(baseline=False))
        self.assert_hold(b, "NO_TRUSTED_BASELINE")

    def test_double_install_is_recorded_and_held(self):
        s = Scenario()
        s.event("COMPONENT_INSTALLED", "REWORK", "2026-09-01T08:04:00Z", s.part("DE", "LOT-SAFE-2"), wo="REWORK")
        ledger, b = self.decision(s)
        self.assert_hold(b, "DOUBLE_OCCUPANCY")
        self.assertEqual(len(ledger.genealogy(s.motor, ledger.watermark(s.motor))["relationships"]), 5)

    def test_same_lot_ambiguity_held(self):
        _, b = self.decision(Scenario(same_lot=True))
        self.assert_hold(b, "AMBIGUOUS_SLOT_ATTRIBUTION")

    def test_label_session_identity_is_preserved_but_does_not_clear_ambiguity(self):
        _, b = self.decision(Scenario(same_lot=True, label=True))
        self.assert_hold(b, "AMBIGUOUS_SLOT_ATTRIBUTION")
        self.assertEqual(b["decision"]["slotAttribution"][0]["assurance"], "OBSERVED_SLOT_LABEL")

    def test_approved_independent_access_evidence_can_bound_candidate_set(self):
        _, b = self.decision(Scenario(same_lot=True, access=True))
        self.assertEqual(b["decision"]["evidenceFinding"], EXCLUDED)
        self.assertTrue(b["decision"]["slotAttribution"][0]["accessEvidenceEventId"])

    def test_missing_sibling_record_is_unknown_candidate_not_empty(self):
        s = Scenario()
        s.events[0]["payload"]["expectedChanges"] = [dict(slot="DE", action="INSTALL")]
        s.events = [e for e in s.events if not (e["eventType"] == "COMPONENT_INSTALLED" and e["payload"]["slot"] == "NDE")]
        _, b = self.decision(s)
        self.assert_hold(b, "AMBIGUOUS_SLOT_ATTRIBUTION")

    def test_empty_recall_scope_cannot_create_exclusion(self):
        s = Scenario(); ledger, _ = self.decision(s)
        s.policy["affectedSlots"] = []
        with self.assertRaises(LedgerBlocked):
            ledger.decide(s.motor, s.policy, [ledger.watermark(s.motor)])

    def test_independent_verification_resolves_current_state_only(self):
        s = Scenario(same_lot=True); s.verify()
        ledger, b = self.decision(s)
        self.assertEqual(b["decision"]["evidenceFinding"], EXCLUDED)
        self.assertTrue(any(v["assurance"] == "CORROBORATED_SLOT" for v in b["decision"]["slots"]["DE"]["verifications"]))
        self.assertTrue(all(a["cleared"] for a in b["decision"]["slotAttribution"]))
        p2 = copy.deepcopy(s.policy)
        p2.update(policyId="RECALL-DEMO/P2", exposureBasis="HISTORICAL_OPERATION",
                  damageInspection=dict(protocolId="DAMAGE", mustOccurAfter=s.policy["announcedAt"], requiredResult="PASS", inspectorQualification="DAMAGE"))
        self.assert_hold(ledger.decide(s.motor, p2, [ledger.watermark(s.motor)])[0])

    def test_derived_verification_cannot_clear_ambiguity(self):
        s = Scenario(same_lot=True)
        s.verify(derivedFromEventIds=[s.replacement["eventId"]])
        _, b = self.decision(s)
        self.assert_hold(b, "AMBIGUOUS_SLOT_ATTRIBUTION")

    def test_p2_inspector_qualification_metadata_reaches_actual_evaluator(self):
        s = Scenario(same_lot=True); s.verify()
        inspection = s.event("INSPECTION_RECORDED", "QA", "2026-10-02T12:00:00Z", dict(
            protocolId="DAMAGE", result="PASS", inspectorQualifiedFor=["DAMAGE"], scope=["DE-bearing"], provisional=True))
        ledger = populated(s); self.addCleanup(ledger.close)
        policy = copy.deepcopy(s.policy)
        policy.update(policyId="RECALL-DEMO/P2", exposureBasis="HISTORICAL_OPERATION",
                      damageInspection=dict(protocolId="DAMAGE", mustOccurAfter=s.policy["announcedAt"], requiredResult="PASS", inspectorQualification="DAMAGE"))
        bundle = ledger.decide(s.motor, policy, [ledger.watermark(s.motor)])[0]
        self.assertEqual(bundle["decision"]["evidenceFinding"], EXCLUDED)
        self.assertIn("DAMAGE_INSPECTION_PASSED", bundle["decision"]["reasonCodes"])
        self.assertIn(inspection, ledger.snapshot(s.motor, ledger.watermark(s.motor))[0]["events"])

    def test_untrusted_affected_observation_holds_not_affected(self):
        s = Scenario(); s.verify(trusted=False, lot="LOT-AFFECTED", at="2026-09-01T08:30:00Z")
        _, b = self.decision(s)
        self.assert_hold(b, "UNTRUSTED_AFFECTED_OBSERVATION")
        self.assertEqual(b["decision"]["evidenceFinding"], "UNRESOLVED")

    def test_later_independent_verifier_can_resolve_untrusted_observation(self):
        s = Scenario(); s.verify(trusted=False, lot="LOT-AFFECTED", at="2026-09-01T08:30:00Z"); s.verify()
        _, b = self.decision(s)
        self.assertEqual(b["decision"]["evidenceFinding"], EXCLUDED)

    def test_untrusted_unaffected_verification_never_resolves_ambiguity(self):
        s = Scenario(same_lot=True); s.verify(trusted=False)
        _, b = self.decision(s)
        self.assert_hold(b, "AMBIGUOUS_SLOT_ATTRIBUTION")

    def test_capture_gap_holds(self):
        s = Scenario(); s.gap()
        _, b = self.decision(s)
        self.assert_hold(b, "MATERIAL_CAPTURE_GAP")

    def test_correction_withdraws_prior_exclusion_and_replays(self):
        s = Scenario(); ledger = populated(s); self.addCleanup(ledger.close)
        before = ledger.watermark(s.motor)
        correction = s.correction(); s.ingest(ledger, [correction])
        decision_id = f"D-{s.motor}-P1-v1"
        bundles = ledger.decide(s.motor, s.policy, [before, ledger.watermark(s.motor)], communicated=[decision_id])
        first, second = [b["decision"] for b in bundles]
        self.assertEqual(first["evidenceFinding"], EXCLUDED)
        self.assertEqual(second["supersedesDecisionId"], first["decisionId"])
        self.assertEqual(second["triggerEventId"], correction["eventId"])
        self.assertTrue(second["precautionaryHold"])
        self.assertTrue(second["notificationObligation"]["communicated"])
        self.assert_hold(bundles[1], "PRIOR_EXCLUSION_WITHDRAWN")
        self.assertEqual(ledger.replay(s.motor, s.policy, bundles[0])["evidenceFinding"], EXCLUDED)
        self.assertNotEqual(ledger.replay(s.motor, s.policy, bundles[1])["evidenceFinding"], EXCLUDED)

    def test_replay_refuses_policy_drift(self):
        s = Scenario(); ledger, b = self.decision(s)
        policy = copy.deepcopy(s.policy); policy["version"] = 2
        with self.assertRaises(LedgerBlocked):
            ledger.replay(s.motor, policy, b)

    def test_separate_evaluations_persist_supersession_across_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            s = Scenario(); path = Path(directory) / "ledger.sqlite"
            ledger = populated(s, path)
            original = ledger.decide(s.motor, s.policy, [ledger.watermark(s.motor)])[0]
            ledger.close(); ledger = Ledger(path)
            try:
                correction = s.correction(); s.ingest(ledger, [correction])
                after = ledger.decide(s.motor, s.policy, [ledger.watermark(s.motor)], communicated=[original["decision"]["decisionId"]])[0]
                self.assertEqual(after["decision"]["supersedesDecisionId"], original["decision"]["decisionId"])
                self.assert_hold(after, "PRIOR_EXCLUSION_WITHDRAWN")
                self.assertEqual(ledger.replay(s.motor, s.policy, original)["evidenceFinding"], EXCLUDED)
            finally:
                ledger.close()

    def test_modified_semantics_profile_or_bundle_is_not_replayed(self):
        s = Scenario(same_lot=True); ledger, b = self.decision(s)
        b = copy.deepcopy(b); b["decision"]["semanticsProfile"] = "P1_LEGACY"
        with self.assertRaises(LedgerBlocked):
            ledger.replay(s.motor, s.policy, b)
        b["bundleDigest"] = digest({k:v for k,v in b.items() if k != "bundleDigest"})
        with self.assertRaises(LedgerBlocked):
            ledger.replay(s.motor, s.policy, b)

    def test_uncertain_clock_observation_is_not_silently_made_stale(self):
        s = Scenario()
        event = s.verify(trusted=False, lot="LOT-AFFECTED", at="2026-09-01T07:00:00Z")
        event["timeSource"] = "OPERATOR_ENTERED"
        _, b = self.decision(s)
        self.assert_hold(b, "UNTRUSTED_AFFECTED_OBSERVATION")

    def test_durable_close_reopen_and_no_engine_modification(self):
        with tempfile.TemporaryDirectory() as directory:
            s = Scenario(); path = Path(directory) / "ledger.sqlite"
            ledger = populated(s, path); wm = ledger.watermark(s.motor)
            first = ledger.decide(s.motor, s.policy, [wm]); ledger.close()
            reopened = Ledger(path)
            try:
                self.assertEqual(reopened.decide(s.motor, s.policy, [wm]), first)
            finally:
                reopened.close()

    def test_retry_identical_is_idempotent(self):
        s = Scenario(); ledger = populated(s); self.addCleanup(ledger.close)
        s.ingest(ledger)
        self.assertEqual(len(ledger.snapshot(s.motor, ledger.watermark(s.motor))[0]["events"]), 8)

    def rejected_wire(self, mutate, *, expected_hash=None):
        s = Scenario(); ledger = Ledger(":memory:"); self.addCleanup(ledger.close); s.provision(ledger)
        doc = encode_document([s.events[0]], "2026-10-21T10:00:00Z")
        mutate(doc)
        raw = json.dumps(doc).encode()
        with self.assertRaises(LedgerBlocked):
            ledger.capture(s.motor, raw, producer_source=s.events[0]["sourceId"], expected_sha256=expected_hash or hashlib.sha256(raw).hexdigest())
        with self.assertRaises(LedgerBlocked):
            ledger.decide(s.motor, s.policy, [ledger.watermark(s.motor)])
        self.assertEqual(ledger.db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)

    def test_noncontiguous_source_sequence_rejected_and_blocks_decision(self):
        self.rejected_wire(lambda d: d["epcisBody"]["eventList"][0]["trace"].update(sourceSeq=2))

    def test_boolean_sequence_rejected(self):
        self.rejected_wire(lambda d: d["epcisBody"]["eventList"][0]["trace"].update(sourceSeq=True))

    def test_invalid_calendar_timestamp_rejected(self):
        self.rejected_wire(lambda d: d["epcisBody"]["eventList"][0].update(eventTime="2026-02-30T08:00:00Z"))

    def test_fractional_timestamp_rejected_without_rounding(self):
        self.rejected_wire(lambda d: d["epcisBody"]["eventList"][0].update(eventTime="2026-08-01T08:00:00.001Z"))

    def test_recorded_before_occurred_rejected(self):
        self.rejected_wire(lambda d: d["epcisBody"]["eventList"][0]["trace"].update(recordedAt="2026-07-01T00:00:00Z"))

    def test_incorrect_transport_hash_rejected(self):
        self.rejected_wire(lambda d: None, expected_hash="0" * 64)

    def test_event_cannot_promote_its_own_trust(self):
        self.rejected_wire(lambda d: d["epcisBody"]["eventList"][0]["trace"]["payload"].update(trusted=True))

    def test_unauthorized_actor_rejected(self):
        self.rejected_wire(lambda d: d["epcisBody"]["eventList"][0]["trace"].update(actorId="FORGED-ACTOR"))

    def test_missing_session_rejected(self):
        self.rejected_wire(lambda d: d["epcisBody"]["eventList"][0]["trace"].pop("captureSessionId"))

    def test_conflicting_motor_core_rejected(self):
        self.rejected_wire(lambda d: d["epcisBody"]["eventList"][0].update(epcList=["urn:other:motor"]))

    def test_changed_event_same_id_blocks_prior_exclusion(self):
        s = Scenario(); ledger, _ = self.decision(s)
        changed = copy.deepcopy(s.replacement); changed["payload"]["lot"] = "LOT-CORRECTED"
        with self.assertRaises(LedgerBlocked):
            s.ingest(ledger, [changed])
        with self.assertRaises(LedgerBlocked):
            ledger.decide(s.motor, s.policy, [ledger.watermark(s.motor)])

    def test_missing_entire_source_prefix_refused(self):
        s = Scenario(); ledger, b = self.decision(s)
        wm = copy.deepcopy(b["decision"]["watermark"])
        # Engine output drops zero watermarks; integration requires them explicitly.
        wm = ledger.watermark(s.motor); wm[s.sources["QA"]] = 1
        with self.assertRaises(LedgerBlocked):
            ledger.decide(s.motor, s.policy, [wm])

    def test_watermark_hiding_reference_refused(self):
        s = Scenario(); ledger, _ = self.decision(s)
        wm = ledger.watermark(s.motor); wm[s.sources["ASSY"]] = 0
        with self.assertRaises(LedgerBlocked):
            ledger.decide(s.motor, s.policy, [wm])

    def test_append_only_trigger(self):
        s = Scenario(); ledger, _ = self.decision(s)
        with self.assertRaises(sqlite3.IntegrityError):
            ledger.db.execute("UPDATE events SET seq=99")

    def test_storage_corruption_detected_even_after_trigger_bypass(self):
        s = Scenario(); ledger, _ = self.decision(s)
        ledger.db.execute("DROP TRIGGER events_no_update")
        ledger.db.execute("UPDATE events SET native='{}' WHERE ordinal=1"); ledger.db.commit()
        with self.assertRaises((LedgerBlocked, ValidationFailure)):
            ledger.decide(s.motor, s.policy, [dict(s.seq, **{s.sources["QA"]: 0, s.sources["HANDHELD"]: 0})])

    def test_atomic_batch_rollback_when_second_event_conflicts(self):
        s = Scenario(); ledger = Ledger(":memory:"); self.addCleanup(ledger.close); s.provision(ledger)
        a = copy.deepcopy(s.events[0]); b = copy.deepcopy(a)
        b.update(eventId="urn:pramaan:conflict", sourceSeq=3, workOrderId="ANOTHER")
        raw = json.dumps(encode_document([a, b], "2026-10-21T10:00:00Z")).encode()
        with self.assertRaises(LedgerBlocked):
            ledger.capture(s.motor, raw, producer_source=a["sourceId"], expected_sha256=hashlib.sha256(raw).hexdigest())
        self.assertEqual(ledger.db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)

    def test_serial_identity_and_verification_metadata_preserved(self):
        s = Scenario()
        for event in s.events:
            p = event["payload"]
            if event["eventType"] == "COMPONENT_INSTALLED":
                p.update(identityGranularity="SERIAL", serial="SERIAL-" + p["slot"] + "-" + p["lot"])
            elif event["eventType"] == "COMPONENT_REMOVED":
                p.update(identityGranularity="SERIAL", observedSerial="SERIAL-DE-LOT-AFFECTED")
        s.verify(provisional=True, derivedFromEventIds=[])
        ledger, _ = self.decision(s)
        self.assertEqual(ledger.snapshot(s.motor, ledger.watermark(s.motor))[0]["events"], s.events)

    def test_core_trace_component_identity_contradiction_rejected(self):
        s = Scenario(); ledger = Ledger(":memory:"); self.addCleanup(ledger.close); s.provision(ledger); s.ingest(ledger, s.events[:1])
        doc = encode_document([s.events[1]], "2026-10-21T10:00:00Z")
        doc["epcisBody"]["eventList"][0]["childEPCs"] = ["urn:wrong:bearing"]
        raw = json.dumps(doc).encode()
        with self.assertRaises(LedgerBlocked):
            ledger.capture(s.motor, raw, producer_source=s.sources["ASSY"], expected_sha256=hashlib.sha256(raw).hexdigest())

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValidationFailure):
            decode(b'{"type":"EPCISDocument","type":"other"}')

    def test_unknown_slot_is_never_configured_out(self):
        s = Scenario(); s.coverage["slotAttribution"]["unknownSlotIsCandidate"] = False
        ledger = Ledger(":memory:"); self.addCleanup(ledger.close)
        with self.assertRaises(ValidationFailure):
            s.provision(ledger)

    def test_original_producer_timestamp_is_not_repository_record_time(self):
        s = Scenario(); ledger, _ = self.decision(s)
        row = ledger.db.execute("SELECT native,epcis FROM events WHERE id=?", (s.replacement["eventId"],)).fetchone()
        self.assertEqual(json.loads(row["native"])["recordedAt"], s.replacement["recordedAt"])
        self.assertNotEqual(json.loads(row["native"])["recordedAt"], json.loads(row["epcis"])["recordTime"])


if __name__ == "__main__":
    unittest.main()
