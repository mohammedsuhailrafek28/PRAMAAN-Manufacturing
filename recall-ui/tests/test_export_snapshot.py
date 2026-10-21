"""Exporter guarantees: the snapshot is the engine's real output, deterministic, and never touches oracle files.

Run: python -m unittest recall-ui/tests/test_export_snapshot.py   (from the repo root)
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))

import export_snapshot as ex  # noqa: E402
from pramaan_recall import Config, evaluate, load_policies  # noqa: E402


class ExportSnapshot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snap = ex.build()

    def test_deterministic(self):
        self.assertEqual(ex.dumps(self.snap), ex.dumps(ex.build()))

    def test_committed_snapshot_is_current(self):
        with open(ex.DEFAULT_OUT, encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), ex.dumps(self.snap), "run recall-ui/tools/export_snapshot.py")

    def test_never_reads_oracle_files(self):
        self.assertFalse(self.snap["provenance"]["oracleFilesRead"])
        opened = []
        real = open

        def spy(path, *a, **k):
            opened.append(str(path))
            return real(path, *a, **k)

        import builtins
        builtins.open = spy
        try:
            ex.build()
        finally:
            builtins.open = real
        self.assertEqual([p for p in opened if "oracle" in os.path.basename(p).lower()], [])

    def test_decisions_are_verbatim_engine_output(self):
        pols, cov = load_policies(os.path.join(ex.FIX[3], "policies.json"))
        cases = ex.load_cases()
        for cid in ("case-01", "case-06", "case-08"):
            case = cases[cid]["case"]
            for pid, pol in pols.items():
                snap_d = self.snap["decisions"][cid][pid]["current"]
                again = evaluate(case, pol, cov, snap_d["watermark"], Config.default())
                self.assertEqual(snap_d["evidenceFinding"], again["evidenceFinding"])
                self.assertEqual(snap_d["operationalAction"], again["operationalAction"])
                self.assertEqual(snap_d["reasonCodes"], again["reasonCodes"])

    def test_case06_original_vs_current(self):
        rows = {(c["unitId"], c["policyId"]): c for c in self.snap["comparison"]}
        c = rows[("case-06", "RC-009/P1")]
        self.assertEqual(c["legacy"]["evidenceFinding"], "EXCLUDED_WITH_EVIDENCE")
        self.assertEqual(c["current"]["evidenceFinding"], "UNRESOLVED")
        self.assertEqual(c["legacy"]["semanticsProfile"], "P1_LEGACY")

    def test_overlay_is_labelled_synthetic_and_outside_the_engine(self):
        self.assertEqual(self.snap["provenance"]["overlay"]["kind"], "SYNTHETIC_OVERLAY")
        dumped = json.dumps(self.snap["decisions"])
        self.assertNotIn("SHP-", dumped)

    def test_every_decision_is_internally_consistent(self):
        for per in self.snap["decisions"].values():
            for pd in per.values():
                for d in [pd["current"], *pd["history"]]:
                    self.assertEqual(d["operationalAction"] == "RELEASE_ELIGIBLE", d["evidenceFinding"] == "EXCLUDED_WITH_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
