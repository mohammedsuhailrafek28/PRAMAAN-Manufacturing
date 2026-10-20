"""Behavioral agreement with the supplied oracle, harness meta-tests, fixture preservation."""
import copy
import hashlib
import os
import re
import subprocess
import sys
import unittest

from tests import helpers as h
from harness import oracle_harness as H

FIXROOT = os.path.dirname(h.FIX)


class OracleAgreement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = H.run_behavioral()

    def test_all_oracle_evaluations_present(self):
        self.assertEqual(len(self.rows), 25)

    def test_decision_level_agreement(self):
        for r in self.rows:
            with self.subTest(case=r["caseId"], policy=r["policyId"], v=r["version"]):
                self.assertEqual(r["decisionDiffs"], [])

    def test_full_agreement_reasons_slots_lifecycle(self):
        for r in self.rows:
            with self.subTest(case=r["caseId"], policy=r["policyId"], v=r["version"]):
                self.assertEqual(r["detailDiffs"], [])

    def test_flag_agreement(self):
        for r in self.rows:
            with self.subTest(case=r["caseId"], policy=r["policyId"], v=r["version"]):
                self.assertEqual(r["flagDiffs"], [])

    def test_case_06_behaviorally_passes_but_is_a_safety_false_exclusion(self):
        r = next(r for r in self.rows if r["caseId"] == "case-06" and r["policyId"] == h.P1)
        self.assertEqual(r["got"]["evidenceFinding"], "EXCLUDED_WITH_EVIDENCE")
        self.assertIn("KNOWN_LIMITATION_LOT_LEVEL_SLOT_AMBIGUITY", r["got"]["flags"])
        truth = h.case("06")["groundTruth"]["trueP1Finding"]
        self.assertEqual(truth, "AFFECTED")
        info = __import__("harness.run_reports", fromlist=["x"]).build_safety(self.rows)
        self.assertIn("case-06 RC-009/P1", info["falseExcl"])


class HarnessMetaTests(unittest.TestCase):
    """A harness that cannot fail proves nothing."""

    def setUp(self):
        self.rows = H.run_behavioral()
        self.r = next(r for r in self.rows if r["caseId"] == "case-04" and r["policyId"] == h.P1)

    def test_detects_wrong_finding(self):
        exp = copy.deepcopy(self.r["expected"])
        exp["evidenceFinding"] = "AFFECTED"
        dec, _, _ = H.compare(exp, self.r["got"], [exp], [self.r["got"]])
        self.assertTrue(dec)

    def test_detects_wrong_reason_codes(self):
        exp = copy.deepcopy(self.r["expected"])
        exp["reasonCodes"] = exp["reasonCodes"] + ["SOMETHING_ELSE"]
        _, det, _ = H.compare(exp, self.r["got"], [exp], [self.r["got"]])
        self.assertTrue(det)

    def test_detects_wrong_slot_detail(self):
        exp = copy.deepcopy(self.r["expected"])
        exp["slots"]["DE"]["reconciliation"] = "CAPTURE_GAP"
        _, det, _ = H.compare(exp, self.r["got"], [exp], [self.r["got"]])
        self.assertTrue(det)

    def test_detects_missing_lifecycle_link(self):
        rs = [r for r in self.rows if r["caseId"] == "case-05" and r["policyId"] == h.P1]
        exp_series, got_series = [r["expected"] for r in rs], [r["got"] for r in rs]
        _, det, _ = H.compare(exp_series[1], got_series[1], exp_series, got_series)
        self.assertEqual(det, [])
        exp = copy.deepcopy(exp_series[1])
        exp.pop("supersedesDecisionId")
        _, det, _ = H.compare(exp, got_series[1], exp_series, got_series)
        self.assertTrue(det)


class EngineIsolation(unittest.TestCase):
    def test_engine_never_touches_oracle_or_ground_truth(self):
        pkg = os.path.join(h.ROOT, "pramaan_recall")
        for f in os.listdir(pkg):
            if f.endswith(".py"):
                with open(os.path.join(pkg, f), encoding="utf-8") as fh:
                    src = fh.read()
                for needle in ("oracle", "groundTruth", "urllib", "socket", "requests", "http"):
                    self.assertNotIn(needle, src, f"{f} mentions {needle}")

    def test_engine_has_no_case_specific_literals(self):
        pkg = os.path.join(h.ROOT, "pramaan_recall")
        for f in os.listdir(pkg):
            if f.endswith(".py"):
                with open(os.path.join(pkg, f), encoding="utf-8") as fh:
                    src = fh.read()
                self.assertIsNone(re.search(r"case-0|BR-\d|M-042|RC-009|C0\d-E", src), f)

    def test_ledger_is_policy_free(self):
        with open(os.path.join(h.ROOT, "pramaan_recall", "ledger.py"), encoding="utf-8") as fh:
            src = fh.read()
        for needle in ("affectedLots", "affectedPart", "affectedSlots", "import policy", "from .policy",
                       "exposureBasis"):
            self.assertNotIn(needle, src)


class FixturePreservation(unittest.TestCase):
    def test_fixtures_match_manifest_byte_for_byte(self):
        with open(os.path.join(FIXROOT, "MANIFEST.sha256"), encoding="utf-8") as m:
            lines = m.read().splitlines()
        for line in lines:
            digest, path = line.strip().split(" *", 1)
            if path.startswith("pramaan-mfg-fixtures.zip"):
                continue
            with open(os.path.join(h.FIX, path), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), digest, path)

    def test_original_validator_still_passes(self):
        out = subprocess.run([sys.executable, "-I", os.path.join(h.FIX, "validate.py")],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("OK: 10 cases, 25 evaluations consistent", out.stdout)


if __name__ == "__main__":
    unittest.main()
