"""Slot attribution safety (v2): ambiguity, assurance levels, serial conflicts, regressions.

Counterexample and mutation tests. Case, label and actor ids appear only here, as fixtures;
the engine package is checked below for hardcoded identifiers.
"""
import importlib.util
import json
import os
import random
import re
import unittest
from datetime import datetime, timedelta

from tests import helpers as h
from harness import oracle_harness as H
from harness import compare_versions as CV

EXCL, AFF, UNRES = "EXCLUDED_WITH_EVIDENCE", "AFFECTED", "UNRESOLVED"
AMB = "AMBIGUOUS_SLOT_ATTRIBUTION"
REM_AT = "2026-09-10T10:00:00Z"


def _builder():
    spec = importlib.util.spec_from_file_location("build_v2", os.path.join(h.FIX2, "build_v2.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def label_at(c, offset):
    """Move the label scan to the removal time + offset seconds."""
    t = datetime.strptime(REM_AT, h.FMT) + timedelta(seconds=offset)
    return h.move(c, h.by_type(c, "SLOT_LABEL_SCANNED"), t.strftime(h.FMT))


def verify_event(c, **over):
    e = h.by_type(c, "SLOT_STATE_VERIFIED")
    for k, v in over.items():
        if k in ("actorId", "sourceId", "evidenceRefs"):
            e[k] = v
        else:
            e["payload"][k] = v
    return e


class AmbiguityDetection(unittest.TestCase):
    def test_same_part_and_lot_in_two_slots_is_ambiguous_and_lists_interpretations(self):
        d = h.run2(h.case("06"))
        self.assertEqual((d["evidenceFinding"], d["operationalAction"], d["reviewRequired"]),
                         (UNRES, "RECALL_HOLD", True))
        self.assertEqual(d["reasonCodes"], [AMB])
        a = d["slotAttribution"][0]
        self.assertEqual([c["slot"] for c in a["candidates"]], ["DE", "NDE"])
        self.assertEqual(a["assurance"], "CLAIMED_SLOT")
        self.assertEqual({c["slot"]: c["supportingEventIds"] for c in a["candidates"]},
                         {"DE": ["C06-E002"], "NDE": ["C06-E003"]})
        for ref in ("C06-E006", "C06-E002", "C06-E003"):
            self.assertIn(ref, a["supportingEventIds"])
            self.assertIn(ref, d["evidenceEventIds"])

    def test_ambiguity_is_not_a_wrong_slot_conclusion(self):
        d = h.run2(h.case("06"))
        self.assertEqual(d["slots"]["DE"]["conflicts"], [])
        self.assertNotIn("REMOVAL_OBSERVATION_MISMATCH", d["reasonCodes"])
        self.assertEqual(d["slots"]["DE"]["reconciliation"], "AMBIGUOUS_ATTRIBUTION")

    def test_distinct_lots_are_not_ambiguous_and_still_release(self):
        d = h.run2(h.case2("07"))
        self.assertEqual(d["evidenceFinding"], EXCL)
        self.assertFalse(d["slotAttribution"][0]["ambiguous"])

    def test_default_config_keeps_phase1_behaviour(self):
        d = h.run(h.case("06"))
        self.assertEqual(d["evidenceFinding"], EXCL)
        self.assertEqual(d["slotAttribution"], [])
        self.assertEqual(d["engineVersion"], "phase1-0.1")

    def test_ambiguity_only_blocks_when_the_removed_lot_is_affected(self):
        c = h.case("06")
        for e in c["events"]:                       # same shape, nothing affected involved
            if e["eventType"] == "COMPONENT_INSTALLED" and e["payload"]["lot"] == "BR-204":
                e["payload"]["lot"] = "BR-500"
            if e["eventType"] == "COMPONENT_REMOVED":
                e["payload"]["observedLot"] = "BR-500"
        d = h.run2(c)
        self.assertEqual(d["evidenceFinding"], EXCL)
        self.assertTrue(d["slotAttribution"][0]["ambiguous"])          # still recorded
        self.assertNotIn(AMB, d["reasonCodes"])

    def test_gap_or_unknown_sibling_never_rules_an_alternative_out(self):
        c = h.case("06")
        h.add_event(c, "CAPTURE_EXCEPTION_RAISED", "MES", "2026-09-10T09:00:00Z", "SYS-MES",
                    {"scope": {"slots": ["NDE", "AUX"]}})
        h.renumber(c)
        d = h.run2(c)
        self.assertEqual(d["evidenceFinding"], UNRES)
        a = d["slotAttribution"][0]
        self.assertTrue(a["ambiguous"])
        self.assertEqual({x["slot"] for x in a["candidates"]}, {"DE", "NDE"})
        self.assertIn({"slot": "AUX", "reason": "STATE_UNKNOWN"}, a["unrulableAlternatives"])

    def _unknown_sibling_case(self):
        c = h.case("06")
        nde = next(e for e in c["events"]
                   if e["eventType"] == "COMPONENT_INSTALLED" and e["payload"]["slot"] == "NDE")
        return h.drop(c, nde)                        # NDE is expected by the build order but has no record

    def test_unknown_sibling_is_a_candidate_it_cannot_be_ruled_out(self):
        d = h.run2(self._unknown_sibling_case())
        a = d["slotAttribution"][0]
        self.assertTrue(a["ambiguous"])
        self.assertIn({"slot": "NDE", "basis": "STATE_UNKNOWN_NOT_RULED_OUT", "claimed": False,
                       "supportingEventIds": []}, a["candidates"])
        self.assertEqual(d["evidenceFinding"], UNRES)

    def test_unknown_sibling_behaviour_is_a_declared_policy_switch(self):
        cov = h.cov2()
        cov["slotAttribution"]["unknownSlotIsCandidate"] = False
        d = h.run2(self._unknown_sibling_case(), cov=cov)
        self.assertFalse(d["slotAttribution"][0]["ambiguous"])       # the less safe reading, opt-in only

    def test_decision_does_not_depend_on_ids_or_event_order(self):
        base = h.run2(h.case2("06c"))
        c = h.case2("06c")
        c["caseId"] = "anything-else"
        random.Random(7).shuffle(c["events"])
        d = h.run2(c)
        for k in ("evidenceFinding", "reasonCodes", "operationalAction", "reviewRequired"):
            self.assertEqual(d[k], base[k])
        self.assertEqual(json.dumps(d["slotAttribution"], sort_keys=True),
                         json.dumps(base["slotAttribution"], sort_keys=True))


class AssuranceLevels(unittest.TestCase):
    def test_claimed_slot_cannot_clear(self):
        d = h.run2(h.case("06"))
        self.assertEqual(d["slotAttribution"][0]["assurance"], "CLAIMED_SLOT")
        self.assertEqual(d["evidenceFinding"], UNRES)

    def test_valid_label_is_observed_but_cannot_clear(self):
        d = h.run2(h.case2("06c"))
        a = d["slotAttribution"][0]
        self.assertEqual(a["assurance"], "OBSERVED_SLOT_LABEL")
        self.assertTrue(a["ambiguous"] and not a["cleared"])
        self.assertEqual((d["evidenceFinding"], d["reasonCodes"]), (UNRES, [AMB]))
        self.assertIn(a["labelScans"][0]["eventId"], d["evidenceEventIds"])

    def test_window_is_inclusive_at_60_seconds_and_rejects_61(self):
        for off, expect in ((-60, "OBSERVED_SLOT_LABEL"), (60, "OBSERVED_SLOT_LABEL"),
                            (-61, "CLAIMED_SLOT"), (61, "CLAIMED_SLOT")):
            with self.subTest(offset=off):
                d = h.run2(label_at(h.case2("06c"), off))
                a = d["slotAttribution"][0]
                self.assertEqual(a["assurance"], expect)
                self.assertEqual(d["evidenceFinding"], UNRES)          # never released either way
                if expect == "CLAIMED_SLOT":
                    self.assertEqual(a["rejectedLabelScans"][0]["reason"], "OUTSIDE_ASSOCIATION_WINDOW")

    def test_window_is_a_parameter_not_a_constant(self):
        cov = h.cov2()
        cov["slotAttribution"]["labelAssociationWindowSeconds"] = 10
        d = h.run2(h.case2("06c"), cov=cov)                            # label is 20 s away
        self.assertEqual(d["slotAttribution"][0]["assurance"], "CLAIMED_SLOT")

    def _assurance(self, mutate=None, cov_mutate=None):
        c = h.case2("06c")
        if mutate:
            mutate(c)
        cov = h.cov2()
        if cov_mutate:
            cov_mutate(cov)
        d = h.run2(c, cov=cov)
        return d["slotAttribution"][0], d

    def test_invalid_label_bindings_give_no_assurance(self):
        label0 = lambda v: v["slotAttribution"]["slotLabels"][0]
        cases = {
            "unprovisioned label": (lambda c: h.by_type(c, "SLOT_LABEL_SCANNED")["payload"].update(
                labelId="LBL-NOPE"), None),
            "label bound to another motor": (None, lambda v: label0(v).update(motorSerial="M-999")),
            "revoked label": (None, lambda v: label0(v).update(revokedAt="2026-09-01T00:00:00Z")),
            "label not yet provisioned": (None, lambda v: label0(v).update(provisionedAt="2026-09-11T00:00:00Z")),
            "inactive label": (None, lambda v: label0(v).update(status="RETIRED")),
        }
        for name, (m, cm) in cases.items():
            with self.subTest(name):
                a, d = self._assurance(m, cm)
                self.assertEqual(a["assurance"], "CLAIMED_SLOT")
                self.assertEqual(a["rejectedLabelScans"][0]["reason"], "LABEL_BINDING_INVALID")
                self.assertEqual(d["evidenceFinding"], UNRES)

    def test_label_from_another_order_motor_source_or_session_gives_no_assurance(self):
        for upd in (dict(workOrderId="MO-042"), dict(motorSerial="M-777"), dict(sourceId="ASSY-01")):
            with self.subTest(upd):
                a, _ = self._assurance(lambda c: h.by_type(c, "SLOT_LABEL_SCANNED").update(upd))
                self.assertEqual(a["assurance"], "CLAIMED_SLOT")

        def split(c):
            for s in c["captureCoverage"]["sessions"]:
                if s["sourceId"] == "REWORK-03":
                    s["to"] = "2026-09-10T10:00:10Z"
            c["captureCoverage"]["sessions"].append(
                dict(sourceId="REWORK-03", **{"from": "2026-09-10T10:00:10Z", "to": "2026-09-10T18:00:00Z"}))
            h.move(c, h.by_type(c, "SLOT_LABEL_SCANNED"), "2026-09-10T10:00:30Z")
        a, _ = self._assurance(split)
        self.assertEqual(a["rejectedLabelScans"][0]["reason"], "DIFFERENT_SESSION")

        def unauth(c):
            for s in c["captureCoverage"]["sessions"]:
                if s["sourceId"] == "REWORK-03":
                    s["authenticated"] = False
        a, _ = self._assurance(unauth)
        self.assertEqual(a["rejectedLabelScans"][0]["reason"], "UNAUTHENTICATED_SESSION")

    def test_label_for_a_different_slot_is_a_conflict_not_comfort(self):
        c = h.case2("06c")
        h.by_type(c, "SLOT_LABEL_SCANNED")["payload"]["labelId"] = "LBL-M042-NDE"
        d = h.run2(c)
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertIn("REMOVAL_SLOT_LABEL_MISMATCH", d["reasonCodes"])
        self.assertEqual(d["slots"]["DE"]["reconciliation"], "CONFLICT")
        self.assertEqual(d["slotAttribution"][0]["assurance"], "CLAIMED_SLOT")


class CorroboratedSlot(unittest.TestCase):
    def test_independent_authorized_verification_clears_p1_only(self):
        c = h.case2("06f")
        p1, p2 = h.run2(c), h.run2(c, h.P2)
        self.assertEqual((p1["evidenceFinding"], p1["reasonCodes"]), (EXCL, ["REPLACED_WITH_UNAFFECTED_LOT"]))
        self.assertTrue(p1["slotAttribution"][0]["cleared"])
        self.assertEqual(p1["slots"]["DE"]["verifications"][0]["assurance"], "CORROBORATED_SLOT")
        self.assertEqual(p2["evidenceFinding"], AFF)                    # historical exposure remains
        self.assertIn("HISTORICAL_EXPOSURE_CONFIRMED", p2["reasonCodes"])

    def test_each_independence_failure_leaves_the_ambiguity_standing(self):
        cases = {
            "METHOD_NOT_APPROVED": lambda c: verify_event(c, method="SLOT_LABEL_SCAN"),
            "ACTOR_NOT_INDEPENDENT": lambda c: verify_event(c, actorId="EMP-017"),
            "ACTOR_NOT_AUTHORIZED": lambda c: verify_event(c, actorId="EMP-099"),
            "EVIDENCE_NOT_INDEPENDENT": lambda c: verify_event(c, evidenceRefs=["EV-LBL-0201"]),
            "DERIVED_FROM_OPERATOR_CLAIM": lambda c: verify_event(
                c, derivedFromEventIds=[h.by_type(c, "SLOT_LABEL_SCANNED")["eventId"]]),
        }
        for reason, mutate in cases.items():
            with self.subTest(reason):
                c = h.case2("06f")
                mutate(c)
                d = h.run2(c)
                self.assertEqual(d["evidenceFinding"], UNRES)
                self.assertEqual(d["reasonCodes"], [AMB])
                v = d["slots"]["DE"]["verifications"][0]
                self.assertFalse(v["trusted"])
                self.assertIn(reason, v["rejectedReasons"])

    def test_verifier_source_that_produced_the_claim_is_not_independent(self):
        c = h.case2("06f")
        cov = h.cov2()
        cov["trustedVerifierSources"].append("REWORK-03")
        verify_event(c, sourceId="REWORK-03")
        h.renumber(c)
        d = h.run2(c, cov=cov)
        self.assertIn("SOURCE_NOT_INDEPENDENT", d["slots"]["DE"]["verifications"][0]["rejectedReasons"])
        self.assertEqual(d["evidenceFinding"], UNRES)

    def test_untrusted_source_never_counts(self):
        c = h.case2("06f")
        verify_event(c, sourceId="ASSY-01")
        self.assertNotEqual(h.run2(h.renumber(c))["evidenceFinding"], EXCL)

    def test_verification_before_the_removal_cannot_clear_it(self):
        c = h.case2("06f")
        h.move(c, verify_event(c), "2026-09-10T09:50:00Z")
        verify_event(c, observedLot="BR-204")                  # consistent with the records at that time
        for s in c["captureCoverage"]["sessions"]:
            if s["sourceId"] == "QA-02":
                s["from"] = "2026-09-10T09:00:00Z"
        d = h.run2(c)
        self.assertEqual((d["evidenceFinding"], d["reasonCodes"]), (UNRES, [AMB]))

    def test_label_cannot_be_promoted_to_verification(self):
        c = h.case2("06f")
        verify_event(c, method="SLOT_LABEL_SCAN", evidenceRefs=["EV-LBL-0201"])
        self.assertEqual(h.run2(c)["evidenceFinding"], UNRES)

    def test_without_the_verification_a_correct_replacement_is_held_not_guessed(self):
        d = h.run2(h.case2("06f"), wm={"MES": 4, "ASSY-01": 2, "REWORK-03": 3})
        self.assertEqual(d["evidenceFinding"], UNRES)

    def test_verified_affected_lot_still_wins(self):
        d = h.run2(h.case("06b"))
        self.assertEqual((d["evidenceFinding"], d["reasonCodes"]), (AFF, ["VERIFIED_AFFECTED_LOT_PRESENT"]))

    def test_missing_slot_attribution_policy_fails_safe(self):
        cov = h.cov2()
        del cov["slotAttribution"]
        self.assertEqual(h.run2(h.case2("06f"), cov=cov)["evidenceFinding"], UNRES)   # nothing can clear
        self.assertEqual(h.run2(h.case("06"), cov=cov)["evidenceFinding"], UNRES)

    def test_lifecycle_release_arrives_only_with_the_corroboration(self):
        series = h.evaluate_series(h.case2("06f"), h.policy(h.P1), h.cov2(),
                                   [{"MES": 4, "ASSY-01": 2, "REWORK-03": 3},
                                    {"MES": 4, "ASSY-01": 2, "REWORK-03": 3, "QA-02": 1}], h.V2)
        self.assertEqual([d["evidenceFinding"] for d in series], [UNRES, EXCL])
        self.assertEqual(series[1]["supersedesDecisionId"], series[0]["decisionId"])
        self.assertNotIn("notificationObligation", series[1])            # nothing was withdrawn


class SerializedIdentity(unittest.TestCase):
    SER = dict(DE="SN-1", NDE="SN-2", REMOVED="SN-1", NEW="SN-9")

    def test_serial_found_in_another_slot_is_a_conflict(self):
        d = h.run2(h.case2("06d"))
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertIn("REMOVAL_SERIAL_IN_OTHER_SLOT", d["reasonCodes"])
        self.assertEqual(d["slots"]["DE"]["reconciliation"], "CONFLICT")
        kinds = {c["kind"]: c for c in d["slots"]["DE"]["conflicts"]}
        self.assertEqual(kinds["REMOVAL_SERIAL_IN_OTHER_SLOT"]["otherSlot"], "NDE")

    def test_conflict_is_reported_even_when_the_claimed_slot_has_no_record(self):
        c = h.case2("06d")
        de = next(e for e in c["events"] if e["eventType"] == "COMPONENT_INSTALLED"
                  and e["payload"]["slot"] == "DE" and e["workOrderId"] == "MO-042")
        c["events"] = [e for e in c["events"] if e["eventId"] != de["eventId"]]
        for e in c["events"]:
            if e["payload"].get("endsInstallEventId") == de["eventId"]:
                e["payload"]["endsInstallEventId"] = None
        h.renumber(c)
        self.assertIn("REMOVAL_SERIAL_IN_OTHER_SLOT", h.run2(c)["reasonCodes"])

    def test_matching_serial_is_not_ambiguous_and_does_not_conflict(self):
        d = h.run2(_builder().base("t", "T", "t", "t", serials=self.SER))
        self.assertEqual(d["evidenceFinding"], EXCL)
        self.assertFalse(d["slotAttribution"][0]["ambiguous"])
        self.assertEqual(d["slots"]["DE"]["conflicts"], [])

    def test_matching_serial_does_not_repair_an_untrusted_baseline(self):
        c = _builder().base("t", "T", "t", "t", serials=self.SER)
        for e in c["events"]:
            if e["eventType"] == "WORK_ORDER_CLOSED" and e["workOrderId"] == "MO-042":
                e["payload"]["disposition"] = "ABANDONED"               # build never completed
        d = h.run2(c)
        self.assertEqual(d["evidenceFinding"], UNRES)
        self.assertEqual(d["slots"]["DE"]["baseline"], "UNKNOWN")


class AccessEvidence(unittest.TestCase):
    def _case(self, source="QA-02", at="2026-09-10T09:30:00Z", actor="EMP-031", wo="RW-192", **payload):
        c = h.case("06")
        pl = {"accessibleSlots": ["DE"], "method": "DISASSEMBLY_RECORD"}
        pl.update(payload)
        h.add_event(c, "SLOT_ACCESS_EVIDENCE", source, at, actor, pl, wo=wo,
                    session=("2026-09-10T09:00:00Z", "2026-09-10T12:00:00Z") if source == "QA-02" else None)
        return h.renumber(c)

    def test_trustworthy_station_evidence_can_rule_a_slot_out(self):
        d = h.run2(self._case())
        a = d["slotAttribution"][0]
        self.assertEqual(a["ruledOutSlots"], ["NDE"])
        self.assertFalse(a["ambiguous"])
        self.assertEqual(d["evidenceFinding"], EXCL)

    def test_untrustworthy_access_evidence_rules_nothing_out(self):
        bad = {
            "source not approved": dict(source="ASSY-01", at="2026-09-10T09:30:00Z"),
            "method not approved": dict(method="OPERATOR_STATEMENT"),
            "same actor as the removal": dict(actor="EMP-017"),
            "after the removal": dict(at="2026-09-10T10:30:00Z"),
            "other work order": dict(wo="MO-042"),
        }
        for name, kw in bad.items():
            with self.subTest(name):
                try:
                    c = self._case(**kw)
                except Exception:        # an ASSY-01 event outside its session is itself invalid
                    continue
                d = h.run2(c)
                self.assertEqual(d["evidenceFinding"], UNRES)
                self.assertEqual(d["slotAttribution"][0]["ruledOutSlots"], [])


class VersionsAndComparison(unittest.TestCase):
    @staticmethod
    def _check_manifest(manifest, root, skip=()):
        import hashlib
        with open(manifest, encoding="utf-8") as m:
            for line in m.read().splitlines():
                digest, path = line.strip().split(" *", 1)
                if path.startswith(skip):
                    continue
                with open(os.path.join(root, path), "rb") as f:
                    assert hashlib.sha256(f.read()).hexdigest() == digest, path

    def test_v1_files_are_byte_identical_to_the_manifest(self):
        self._check_manifest(os.path.join(os.path.dirname(h.FIX), "MANIFEST.sha256"), h.FIX,
                             skip=("pramaan-mfg-fixtures.zip",))

    def test_v2_manifest_matches_and_builder_is_reproducible(self):
        self._check_manifest(os.path.join(h.FIX2, "MANIFEST.sha256"), h.FIX2)
        b = _builder()
        cases = b.build_cases()
        with open(os.path.join(h.FIX2, "oracle-v2.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), b.build_oracle(cases))
        for cid, c in cases.items():
            with open(os.path.join(h.FIX2, "cases", f"{cid}.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f), c)

    def test_every_v1_expectation_is_carried_over_except_the_declared_changes(self):
        def load(*p):
            with open(os.path.join(*p), encoding="utf-8") as f:
                return json.load(f)
        v1, v2 = load(h.FIX, "oracle.json"), load(h.FIX2, "oracle-v2.json")
        tr = load(h.FIX2, "VERSION_TRANSITION.json")
        declared = {(c["caseId"], c["policyId"]) for c in tr["changedEvaluations"]}
        self.assertEqual(declared, {("case-06", h.P1), ("case-06", h.P2)})
        self.assertEqual(v2["derivedFrom"]["sha256"], tr["v1"]["files"]["v1/oracle.json"])
        idx = {c["caseId"]: c for c in v2["cases"]}
        for c in v1["cases"]:
            for old, new in zip(c["evaluations"], idx[c["caseId"]]["evaluations"]):
                if (c["caseId"], old["policyId"]) not in declared:
                    self.assertEqual(old, new, (c["caseId"], old["policyId"]))
        self.assertEqual(tr["v2"]["changed"], 2)

    def test_v2_case_files_are_internally_consistent(self):
        for cid in ("06c", "06d", "06e", "06f", "07"):
            c = h.case2(cid)
            seqs, last = {}, {}
            for e in c["events"]:
                seqs.setdefault(e["sourceId"], []).append(e["sourceSeq"])
                self.assertGreaterEqual(e["recordedAt"], e["occurredAt"])
                self.assertGreaterEqual(e["recordedAt"], last.get(e["sourceId"], ""))
                last[e["sourceId"]] = e["recordedAt"]
                self.assertTrue(any(s["sourceId"] == e["sourceId"] and s["from"] <= e["recordedAt"] <= s["to"]
                                    for s in c["captureCoverage"]["sessions"]), (cid, e["eventId"]))
            for src, s in seqs.items():
                self.assertEqual(s, list(range(1, len(s) + 1)), (cid, src))

    def test_06c_and_06e_are_the_same_events_with_opposite_truth(self):
        strip = lambda c: json.dumps([{k: v for k, v in e.items() if k != "eventId"} for e in c["events"]]
                                     ).replace("C06C-", "X-").replace("C06E-", "X-")
        self.assertEqual(strip(h.case2("06c")), strip(h.case2("06e")))
        _, _, cases, _ = H.load_all(2)
        t = H.load_truth(cases)
        self.assertEqual((t["case-06c"], t["case-06e"]), ("AFFECTED", "UNAFFECTED"))
        self.assertEqual(h.run2(h.case2("06c"))["evidenceFinding"], h.run2(h.case2("06e"))["evidenceFinding"])

    def test_truth_sidecar_agrees_with_the_inline_ground_truth(self):
        _, _, cases, _ = H.load_all(2)
        self.assertEqual(H.load_truth(cases)["case-06"], "AFFECTED")

    def test_v2_engine_agrees_with_v2_oracle_and_only_declared_v1_differences(self):
        rows = H.run_behavioral(H.V2_CONFIG, 2)
        self.assertEqual(len(rows), 35)
        self.assertEqual([r for r in rows if r["decisionDiffs"] or r["detailDiffs"] or r["flagDiffs"]], [])
        old = H.run_behavioral(H.V2_CONFIG, 1, 2)
        self.assertEqual({(r["caseId"], r["policyId"]) for r in old if r["decisionDiffs"] or r["detailDiffs"]},
                         {("case-06", h.P1), ("case-06", h.P2)})
        self.assertEqual([r for r in H.run_behavioral(H.V1_CONFIG, 1) if r["decisionDiffs"] or r["detailDiffs"]], [])

    def test_gate_passes_and_a_planted_false_release_would_fail_it(self):
        r = CV.compute()
        self.assertTrue(r["gate"]["pass"])
        self.assertEqual(r["B"]["e2_false_releases"], [])
        self.assertGreater(len(r["B"]["e2_releases_p1"]), 0)
        self.assertEqual(r["B"]["e1_false_releases"], ["case-06 P1", "case-06c P1"])
        bad = CV.compute(e2_config=H.V1_CONFIG)                    # an engine that still releases 06 / 06c
        self.assertFalse(bad["gate"]["pass"])
        self.assertIn("case-06 P1", bad["B"]["e2_false_releases"])

    def test_disagreeing_with_a_known_unsafe_v1_expectation_is_not_a_defect(self):
        r = CV.compute()
        cls = {(d["caseId"], d["policyId"]): d["classification"] for d in r["A"]["e2_vs_o1_divergences"]}
        self.assertTrue(cls[("case-06", h.P1)].startswith("INTENDED_SAFETY_DIVERGENCE"))
        self.assertEqual(r["E"]["unexplained_vs_o1"], [])

    def test_engine_never_hardcodes_fixture_identifiers(self):
        pkg = os.path.join(h.ROOT, "pramaan_recall")
        for f in os.listdir(pkg):
            if f.endswith(".py"):
                with open(os.path.join(pkg, f), encoding="utf-8") as fh:
                    src = fh.read()
                self.assertIsNone(re.search(r"case-0|BR-\d|M-042|RC-009|C0\d[A-Z]?-E|LBL-|EMP-0|SN-\d", src), f)


if __name__ == "__main__":
    unittest.main()
