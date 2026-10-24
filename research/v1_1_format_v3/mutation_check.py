"""Sensitivity check for the FORMAT_V3 tests: each mutant removes one safety mechanism in-process (no file is changed); the tests must fail.
usage (repository root):  python -B research/v1_1_format_v3/mutation_check.py OUT.json
"""
import io
import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from application import lot_identity as L, registry_binding as RB, checkpoint_review as CR  # noqa: E402

orig = dict(check=RB.check, valid=RB.valid_block, regchg=CR.registry_change, find=L.motor_findings, diff=RB.diff)


def run():
    import application.test_format_v3 as A
    import application.test_v11_hardening as B
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(A), unittest.defaultTestLoader.loadTestsFromModule(B)])
    r = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return dict(ran=r.testsRun, failed=sorted({str(t).split(" ")[0] for t, _ in r.failures + r.errors}))


def restore():
    RB.check, RB.valid_block, CR.registry_change, L.motor_findings, RB.diff = orig["check"], orig["valid"], orig["regchg"], orig["find"], orig["diff"]


def m_binding_ignored():
    RB.check = lambda p, b, r: dict(orig["check"](p, b, r), status="OK", changes=[], detail="")


def m_legacy_format_grants_eligibility():
    RB.check = lambda p, b, r: (lambda x: dict(x, status="OK") if x["status"] == "UNBOUND_LEGACY_FORMAT" else x)(orig["check"](p, b, r))


def m_block_validation_off():
    RB.valid_block = lambda b: True


def m_legacy_prior_needs_no_acknowledgement():
    CR.registry_change = lambda app, path: (lambda x: dict(x, requiresAcknowledgement=False) if x.get("priorBinding") == "LEGACY_SIDECAR_UNVERIFIED" else x)(orig["regchg"](app, path))


def m_identity_findings_dropped():
    L.motor_findings = lambda reg, events, pol, part: []


def m_diff_blind():
    RB.diff = lambda old, new: []


results = dict(unmutated=run())
for name, fn in (("registry_binding_ignored", m_binding_ignored), ("legacy_format_grants_eligibility", m_legacy_format_grants_eligibility),
                 ("binding_block_validation_off", m_block_validation_off), ("legacy_prior_needs_no_acknowledgement", m_legacy_prior_needs_no_acknowledgement),
                 ("identity_findings_dropped", m_identity_findings_dropped), ("registry_diff_blind", m_diff_blind)):
    fn(); results[name] = run(); restore()
for k, v in results.items():
    print(k, v["ran"], "tests; failing:", len(v["failed"]), v["failed"])
Path(sys.argv[1]).write_text(json.dumps(results, indent=1, sort_keys=True))
