"""Run the unmodified original application test modules with Manufacturing replaced by a candidate (regression impact).
usage: python -B run_original_suites.py A|B|BASELINE [OUT.json]   (from the repository root)
The candidate is bound BEFORE the test modules import `Manufacturing`, so every `from .service import Manufacturing` sees it.
"""
import io
import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "research" / "lot_identity"))
import application.service as service  # noqa: E402
import lotid  # noqa: E402

which = sys.argv[1]


class AFixture(lotid.StrategyA):
    """A with the one extra lot the original tests use as the recalled lot (BR-901) added to the registry: separates fixture data from logic."""
    def __init__(self, path, registry=None, **kw):
        reg = lotid.demo_registry()
        reg.entries["BR-901"] = lotid.LotEntry("BR-901", "LOCAL-MFG-REGISTRY", "SUP-KAV-02", "Kaveri Precision — synthetic supplier")
        super().__init__(path, reg, **kw)


if which != "BASELINE":
    service.Manufacturing = {"A": lotid.StrategyA, "A_FIXTURE": AFixture, "B": lotid.StrategyB}[which]
MODULES = ["test_application", "test_checkpoint_ops", "test_checkpoints", "test_consolidated_safety", "test_d5", "test_d6", "test_hardening", "test_remediation", "test_unified"]
result = {}
for m in MODULES:
    suite = unittest.defaultTestLoader.loadTestsFromName("application." + m)
    stream = io.StringIO()
    r = unittest.TextTestRunner(stream=stream, verbosity=0).run(suite)
    bad = [(str(t), tb.strip().splitlines()[-1][:160]) for t, tb in r.failures + r.errors]
    result[m] = dict(ran=r.testsRun, failures=len(r.failures), errors=len(r.errors), failing=bad)
    print(m, r.testsRun, "fail", len(r.failures), "err", len(r.errors), flush=True)
if len(sys.argv) > 2:
    Path(sys.argv[2]).write_text(json.dumps(result, indent=1, sort_keys=True))
