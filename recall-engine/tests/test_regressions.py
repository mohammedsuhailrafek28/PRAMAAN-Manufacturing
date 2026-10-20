"""Regression tests: false exclusions, missing evidence, lifecycle, identity assurance.

Each mutates a supplied history (or builds one) to probe a rule the fixtures
only touch indirectly. The expectation in every test is derived from the stated
semantics, not from oracle.json.
"""
import copy
import random
import unittest

from tests.helpers import (COVERAGE, P1, P2, Config, add_event, case, codes, drop, empty_case,
                           ev, evaluate_series, policy, run)

EXCL, AFF, UNRES = "EXCLUDED_WITH_EVIDENCE", "AFFECTED", "UNRESOLVED"


class MissingEvidenceIsNotSafety(unittest.TestCase):
    def test_empty_history_is_unresolved_for_both_policies(self):
        for pid in (P1, P2):
            d = run(empty_case(), pid)
            self.assertEqual(d["evidenceFinding"], UNRES, pid)
            self.assertEqual(d["operationalAction"], "RECALL_HOLD")
            self.assertTrue(d["reviewRequired"])

    def test_removing_the_as_built_baseline_blocks_exclusion(self):
        c = case("01")
        drop(c, ev(c, "COMPONENT_INSTALLED", slot="DE", source="ASSY-01"))
        d = run(c, P1)
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertEqual(d["slots"]["DE"]["baseline"], "UNKNOWN")

    def test_dropped_event_is_a_sequence_gap_not_silence(self):
        c = case("01")
        drop(c, ev(c, "COMPONENT_REMOVED", slot="DE"), renumber=False)
        d1, d2 = run(c, P1), run(c, P2)
        self.assertEqual(d1["evidenceFinding"], UNRES)
        self.assertIn("SOURCE_SEQUENCE_GAP", codes(d1))
        self.assertIn("SOURCE_SEQUENCE_GAP", codes(d2))   # P2 stays held; gap stays visible
        self.assertEqual(d2["operationalAction"], "RECALL_HOLD")

    def test_watermark_claiming_unseen_events_is_a_gap(self):
        c = case("01")
        wm = {"MES": 4, "ASSY-01": 2, "REWORK-03": 5}     # claims seq 4,5 never delivered
        d = run(c, P1, wm)
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertIn("SOURCE_SEQUENCE_GAP", codes(d))

    def test_unresolved_exception_on_policy_slot_blocks_exclusion(self):
        c = case("01")
        ev(c, "CAPTURE_EXCEPTION_RAISED")["payload"]["scope"]["slots"] = ["DE"]
        d = run(c, P1)
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertIn("MATERIAL_CAPTURE_GAP", codes(d))

    def test_resolved_exception_no_longer_blocks(self):
        c = case("01")
        x = ev(c, "CAPTURE_EXCEPTION_RAISED")
        x["payload"]["scope"]["slots"] = ["DE"]
        add_event(c, "CAPTURE_EXCEPTION_RESOLVED", "REWORK-03", "2026-09-10T11:20:00Z", "EMP-017",
                  {"exceptionEventId": x["eventId"]}, wo="RW-192")
        self.assertEqual(run(c, P1)["evidenceFinding"], EXCL)

    def test_out_of_scope_exception_does_not_block(self):
        self.assertEqual(run(case("01"), P1)["evidenceFinding"], EXCL)

    def test_unmet_work_order_obligation_blocks_exclusion(self):
        c = case("01")
        drop(c, ev(c, "COMPONENT_INSTALLED", slot="DE", source="REWORK-03"))   # WO closed COMPLETED anyway
        d = run(c, P1)
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertIn("WORK_ORDER_UNRECONCILED", codes(d))
        self.assertEqual(d["workOrders"]["RW-192"]["reconciliation"], "UNRECONCILED")
        self.assertEqual(d["workOrders"]["RW-192"]["disposition"], "COMPLETED")  # disposition not trusted

    def test_open_work_order_is_pending_not_clean(self):
        c = case("01")
        drop(c, ev(c, "WORK_ORDER_CLOSED", wo="RW-192"))
        drop(c, ev(c, "COMPONENT_INSTALLED", slot="DE", source="REWORK-03"))
        d = run(c, P1)
        self.assertEqual(d["evidenceFinding"], UNRES)

    def test_event_recorded_before_it_occurred_is_integrity_failure(self):
        c = case("01")
        e = ev(c, "COMPONENT_INSTALLED", slot="DE", source="REWORK-03")
        e["recordedAt"] = "2026-09-10T10:00:00Z"
        e["occurredAt"] = "2026-09-10T11:00:00Z"
        d = run(c, P1)
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertIn("EVENT_ORDER_INTEGRITY", codes(d))

    def test_event_outside_capture_session_is_integrity_failure(self):
        c = case("01")
        c["captureCoverage"]["sessions"] = [s for s in c["captureCoverage"]["sessions"]
                                            if s["sourceId"] != "REWORK-03"]
        d = run(c, P1)
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertIn("EVENT_INTEGRITY_VIOLATION", codes(d))

    def test_p2_without_confirmed_exposure_needs_positive_evidence(self):
        d = run(empty_case(), P2)
        self.assertIn("EXPOSURE_UNKNOWN", codes(d))
        # a clean unaffected build is the only way to a P2 exclusion
        c = case("01")
        for e in c["events"]:
            if e["eventType"] == "COMPONENT_INSTALLED" and e["payload"]["lot"] == "BR-204":
                e["payload"]["lot"] = "BR-150"
            if e["eventType"] == "COMPONENT_REMOVED":
                e["payload"]["observedLot"] = "BR-150"
        drop(c, ev(c, "CAPTURE_EXCEPTION_RAISED"))
        d = run(c, P2)
        self.assertEqual(d["evidenceFinding"], EXCL)
        self.assertEqual(d["reasonCodes"], ["NO_HISTORICAL_EXPOSURE"])

    def test_p2_bounded_gap_does_not_prove_absence_of_historical_exposure(self):
        c = case("04")
        for e in c["events"]:
            if e["eventType"] == "COMPONENT_INSTALLED" and e["payload"]["lot"] == "BR-204":
                e["payload"]["lot"] = "BR-150"
            if e["eventType"] == "COMPONENT_REMOVED":
                e["payload"]["observedLot"] = "BR-150"
        d = run(c, P2)
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertIn("HISTORY_GAP_NOT_RECOVERED_BY_VERIFICATION", codes(d))
        self.assertEqual(run(c, P1)["evidenceFinding"], EXCL)   # state is re-established; history is not


class VerificationRules(unittest.TestCase):
    def test_untrusted_verifier_source_does_not_bound_outage(self):
        c = case("04")
        v = ev(c, "SLOT_STATE_VERIFIED")
        v["sourceId"] = "QA-99"
        for s in c["captureCoverage"]["sessions"]:
            if s["sourceId"] == "QA-02":
                s["sourceId"] = "QA-99"
        d = run(c, P1)
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertIn("MATERIAL_CAPTURE_GAP", codes(d))

    def test_non_independent_verifier_does_not_bound_outage(self):
        c = case("04")
        ev(c, "SLOT_STATE_VERIFIED")["actorId"] = "EMP-017"      # same person who did the rework
        self.assertEqual(run(c, P1)["evidenceFinding"], UNRES)

    def test_verification_can_support_p1_exclusion_without_baseline(self):
        c = case("02")
        add_event(c, "SLOT_STATE_VERIFIED", "QA-02", "2026-09-10T11:30:00Z", "EMP-031",
                  {"componentType": "BEARING", "slot": "DE", "observedPart": "BR-6205",
                   "observedLot": "BR-310", "provisional": True},
                  session=("2026-09-10T11:00:00Z", "2026-09-10T12:00:00Z"))
        d = run(c, P1)
        self.assertEqual(d["evidenceFinding"], EXCL)
        self.assertIn("PROVISIONAL_VERIFICATION_USED", d["assuranceWarnings"][0])

    def test_verification_never_releases_when_records_say_affected(self):
        c = case("03")                                           # records: BR-204 and BR-310 in DE
        add_event(c, "SLOT_STATE_VERIFIED", "QA-02", "2026-09-10T11:30:00Z", "EMP-031",
                  {"componentType": "BEARING", "slot": "DE", "observedPart": "BR-6205",
                   "observedLot": "BR-310", "provisional": True},
                  session=("2026-09-10T11:00:00Z", "2026-09-10T12:00:00Z"))
        d = run(c, P1)
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertTrue(d["reviewRequired"])
        self.assertIn("VERIFIED_STATE_MISMATCH_RISK_DECREASING", codes(d))

    def test_verified_affected_lot_overrides_clean_looking_records(self):
        d = run(case("06b"), P1)
        self.assertEqual(d["evidenceFinding"], AFF)
        self.assertEqual(d["slots"]["DE"]["currentLotPerRecords"], "BR-310")   # records unchanged
        self.assertEqual(d["slots"]["DE"]["conflicts"][0]["observedLot"], "BR-204")


class IdentityAssurance(unittest.TestCase):
    def test_strict_profile_refuses_the_lot_level_wrong_slot_exclusion(self):
        d = run(case("06"), P1, cfg=Config(strict_lot_ambiguity=True))
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertIn("LOT_LEVEL_SLOT_AMBIGUITY", codes(d))
        self.assertTrue(d["reviewRequired"])
        self.assertEqual(d["operationalAction"], "RECALL_HOLD")

    def test_strict_profile_leaves_unambiguous_exclusions_alone(self):
        for n in ("01", "04"):
            self.assertEqual(run(case(n), P1, cfg=Config(strict_lot_ambiguity=True))["evidenceFinding"], EXCL)

    def _serialize(self, c, observed_serial_on_removal):
        for e in c["events"]:
            p = e["payload"]
            if e["eventType"] == "COMPONENT_INSTALLED" and e["sourceId"] == "ASSY-01":
                p["identityGranularity"], p["serial"] = "SERIAL", "S-" + p["slot"]
            if e["eventType"] == "COMPONENT_INSTALLED" and e["sourceId"] == "REWORK-03":
                p["identityGranularity"], p["serial"] = "SERIAL", "S-NEW"
            if e["eventType"] == "COMPONENT_REMOVED":
                p["identityGranularity"], p["observedSerial"] = "SERIAL", observed_serial_on_removal
        return c

    def test_serialized_identity_catches_the_wrong_slot_scan(self):
        c = self._serialize(case("06"), "S-NDE")      # the unit actually pulled was the NDE one
        d = run(c, P1)
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertIn("REMOVAL_OBSERVATION_MISMATCH", codes(d))
        self.assertEqual(d["slots"]["DE"]["conflicts"][0]["kind"], "REMOVAL_OBSERVATION_MISMATCH")

    def test_serialized_correct_scan_excludes_without_ambiguity_flag(self):
        c = self._serialize(case("06"), "S-DE")
        d = run(c, P1)
        self.assertEqual(d["evidenceFinding"], EXCL)
        self.assertEqual(d["flags"], [])
        self.assertEqual(d["identityGranularity"], "SERIAL")

    def test_lot_level_removal_lot_mismatch_is_a_conflict(self):
        c = case("01")
        ev(c, "COMPONENT_REMOVED")["payload"]["observedLot"] = "BR-150"   # scan disagrees with install
        d = run(c, P1)
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertIn("REMOVAL_OBSERVATION_MISMATCH", codes(d))


class LateEvidenceAndLifecycle(unittest.TestCase):
    W1, W2 = "2026-10-11T23:59:59Z", "2026-10-12T23:59:59Z"

    def _wms(self, c):
        from pramaan_recall import watermark_at
        return [watermark_at(c["events"], self.W1), watermark_at(c["events"], self.W2)]

    def test_events_beyond_watermark_cannot_leak_into_a_decision(self):
        c = case("05")
        w1, w2 = self._wms(c)
        self.assertEqual(run(c, P1, w1)["evidenceFinding"], EXCL)
        self.assertEqual(run(c, P1, w2)["evidenceFinding"], UNRES)
        self.assertEqual(run(c, P1, w1)["watermark"], w1)

    def test_risk_increasing_late_claim_holds_immediately_and_needs_review(self):
        c = case("05")
        d = run(c, P1, self._wms(c)[1])
        self.assertEqual((d["evidenceFinding"], d["operationalAction"], d["reviewRequired"]),
                         (UNRES, "RECALL_HOLD", True))
        self.assertEqual(d["supersededEventIds"], [ev(c, "COMPONENT_INSTALLED", source="REWORK-03", slot="DE")["eventId"]])

    def test_lifecycle_preserves_history_and_records_notification(self):
        c = case("05")
        s = evaluate_series(c, policy(P1), COVERAGE, self._wms(c), communicated=("D-case-05-P1-v1",))
        v1_before = copy.deepcopy(s[0])
        self.assertEqual([x["version"] for x in s], [1, 2])
        self.assertEqual(s[1]["supersedesDecisionId"], s[0]["decisionId"])
        self.assertTrue(s[1]["precautionaryHold"])
        n = s[1]["notificationObligation"]
        self.assertEqual((n["required"], n["communicated"]), (True, True))
        self.assertIn("PRIOR_EXCLUSION_WITHDRAWN", s[1]["reasonCodes"])
        self.assertEqual(s[0], v1_before)                          # v1 untouched
        self.assertEqual(s[0]["evidenceFinding"], EXCL)

    def test_unchanged_evaluation_does_not_issue_a_new_version(self):
        c = case("05")
        w1 = self._wms(c)[0]
        s = evaluate_series(c, policy(P1), COVERAGE, [w1, w1])
        self.assertEqual([x["unchanged"] for x in s], [False, True])
        self.assertEqual(s[1]["decisionId"], s[0]["decisionId"])

    def test_risk_decreasing_late_claim_never_releases(self):
        c = case("05")
        inst = ev(c, "COMPONENT_INSTALLED", source="REWORK-03", slot="DE")
        inst["payload"]["lot"] = "BR-207"                       # original record: affected lot
        ev(c, "COMPONENT_INSTALLED", source="QUALITY-PORTAL")["payload"]["lot"] = "BR-310"   # claim: safe lot
        d = run(c, P1)
        self.assertEqual(d["evidenceFinding"], AFF)
        self.assertEqual(d["operationalAction"], "RECALL_HOLD")
        self.assertTrue(d["reviewRequired"])                     # claim is queued, not applied
        self.assertIn("LATE_CLAIM_RISK_DECREASING_NOT_APPLIED", codes(d))

    def test_risk_decreasing_claim_cannot_be_used_to_clear_p2_either(self):
        c = case("05")
        ev(c, "COMPONENT_INSTALLED", source="REWORK-03", slot="DE")["payload"]["lot"] = "BR-207"
        ev(c, "COMPONENT_INSTALLED", source="QUALITY-PORTAL")["payload"]["lot"] = "BR-310"
        self.assertEqual(run(c, P2)["evidenceFinding"], AFF)

    def test_corroborated_late_claim_becomes_affected_with_both_reasons(self):
        d = run(case("05b"), P1)
        self.assertEqual(d["evidenceFinding"], AFF)
        self.assertEqual(set(d["reasonCodes"]), {"VERIFIED_AFFECTED_LOT_PRESENT", "CORROBORATED_BY_VERIFICATION"})

    def test_late_claim_alone_is_the_only_p2_exposure_requires_review(self):
        c = case("05")
        for e in c["events"]:                                    # make the whole history unaffected
            if e["eventType"] == "COMPONENT_INSTALLED" and e["payload"]["lot"] == "BR-204":
                e["payload"]["lot"] = "BR-150"
            if e["eventType"] == "COMPONENT_REMOVED":
                e["payload"]["observedLot"] = "BR-150"
        d = run(c, P2)
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertTrue(d["reviewRequired"])
        self.assertIn("LATE_CLAIM_RISK_INCREASING", codes(d))


class CorrectionsNeverEraseOrQuietlyRelease(unittest.TestCase):
    def _decreasing(self, source):
        c = case("05")
        ev(c, "COMPONENT_INSTALLED", source="REWORK-03", slot="DE")["payload"]["lot"] = "BR-207"
        corr = ev(c, "COMPONENT_INSTALLED", source="QUALITY-PORTAL")
        corr["payload"]["lot"] = "BR-310"
        if source != "QUALITY-PORTAL":                   # same mandatory source rewrites its own record
            corr["sourceId"], corr["sourceSeq"] = source, 3
            for s in c["captureCoverage"]["sessions"]:
                if s["sourceId"] == source:
                    s["to"] = "2026-10-13T00:00:00Z"
        return c

    def test_risk_decreasing_correction_from_a_mandatory_source_is_still_only_a_claim(self):
        d = run(self._decreasing("REWORK-03"), P1)
        self.assertEqual((d["evidenceFinding"], d["operationalAction"]), (AFF, "RECALL_HOLD"))
        self.assertTrue(d["reviewRequired"])
        self.assertIn("LATE_CLAIM_RISK_DECREASING_NOT_APPLIED", codes(d))

    def test_correction_cannot_erase_p2_exposure(self):
        c = case("05")
        for e in c["events"]:                             # only the original install ever showed an affected lot
            if e["eventType"] == "COMPONENT_INSTALLED" and e["payload"]["lot"] == "BR-204":
                e["payload"]["lot"] = "BR-150"
            if e["eventType"] == "COMPONENT_REMOVED":
                e["payload"]["observedLot"] = "BR-150"
        ev(c, "COMPONENT_INSTALLED", source="REWORK-03", slot="DE")["payload"]["lot"] = "BR-207"
        ev(c, "COMPONENT_INSTALLED", source="QUALITY-PORTAL")["payload"]["lot"] = "BR-310"
        d = run(c, P2)
        self.assertEqual(d["evidenceFinding"], AFF)
        self.assertIn("HISTORICAL_EXPOSURE_CONFIRMED", codes(d))

    def test_superseded_events_stay_visible_as_evidence(self):
        c = case("05")
        d = run(c, P1)
        self.assertEqual(len(d["supersededEventIds"]), 1)
        self.assertIn(d["supersededEventIds"][0], d["evidenceEventIds"])


class PolicyTwoInspection(unittest.TestCase):
    def test_inspection_before_announcement_does_not_count(self):
        pol = policy(P2)
        pol["damageInspection"]["mustOccurAfter"] = "2026-10-06T00:00:00Z"   # after the 10-05 inspection
        d = run(case("04"), P2, pol=pol)
        self.assertEqual(d["evidenceFinding"], AFF)
        self.assertIn("DAMAGE_INSPECTION_MISSING", codes(d))

    def test_unqualified_inspector_does_not_count(self):
        c = case("04")
        ev(c, "INSPECTION_RECORDED")["payload"]["inspectorQualifiedFor"] = []
        d = run(c, P2)
        self.assertEqual(d["evidenceFinding"], AFF)
        self.assertIn("DAMAGE_INSPECTION_INVALID", codes(d))

    def test_failed_inspection_is_affected(self):
        c = case("04")
        ev(c, "INSPECTION_RECORDED")["payload"]["result"] = "FAIL"
        d = run(c, P2)
        self.assertEqual(d["evidenceFinding"], AFF)
        self.assertIn("DAMAGE_INSPECTION_FAILED", codes(d))

    def test_passed_inspection_does_not_remediate_a_component_still_in_doubt(self):
        d = run(case("04c"), P2)
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertIn("REMEDIATION_COMPLETENESS_UNCERTAIN", codes(d))


class StructureAndDeterminism(unittest.TestCase):
    def test_structural_consistency_is_independent_of_policy(self):
        for n in ("01", "03", "04", "06b"):
            a, b = run(case(n), P1), run(case(n), P2)
            for slot, s in a["slots"].items():
                self.assertEqual(s["reconciliation"], b["slots"][slot]["reconciliation"], (n, slot))

    def test_same_input_same_output(self):
        c = case("04")
        self.assertEqual(run(c, P2), run(copy.deepcopy(c), P2))

    def test_event_list_order_does_not_change_the_decision(self):
        for n in ("01", "04", "05b", "06b"):
            base = case(n)
            ref = run(base, P2)
            for seed in range(5):
                c = copy.deepcopy(base)
                random.Random(seed).shuffle(c["events"])
                d = run(c, P2)
                self.assertEqual(d["evidenceFinding"], ref["evidenceFinding"])
                self.assertEqual(set(d["reasonCodes"]), set(ref["reasonCodes"]))
                self.assertEqual(d["evidenceEventIds"], ref["evidenceEventIds"])

    def test_decision_carries_required_audit_fields(self):
        d = run(case("04"), P2)
        for k in ("policyVersion", "watermark", "identityGranularity", "reasonCodes",
                  "evidenceEventIds", "evidenceRefs", "operationalAction", "reviewRequired"):
            self.assertIn(k, d)
        self.assertEqual(d["policyVersion"], 1)
        self.assertEqual(d["identityGranularity"], "LOT")
        self.assertIn("C04-E002", d["evidenceEventIds"])
        self.assertIn("EV-REPORT-0402", d["evidenceRefs"])

    def test_finding_and_action_are_separate_fields(self):
        d = run(case("01"), P1)
        self.assertEqual((d["evidenceFinding"], d["operationalAction"]), (EXCL, "RELEASE_ELIGIBLE"))
        d = run(case("01"), P2)
        self.assertEqual((d["evidenceFinding"], d["operationalAction"]), (AFF, "RECALL_HOLD"))


if __name__ == "__main__":
    unittest.main()
