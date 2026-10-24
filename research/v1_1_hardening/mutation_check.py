"""Sensitivity check for the v1.1 hardening tests: each mutant removes one safety mechanism in-process (no file is changed); the tests must fail.
usage (repository root):  python -B research/v1_1_hardening/mutation_check.py OUT.json
"""
import io
import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from application import lot_identity as L, service as S, registry_binding as RB, checkpoint_review as CR  # noqa: E402

orig = dict(check=RB.check, diff=RB.diff, find=L.motor_findings, integ=L.integrity_findings, replace=S.Manufacturing.replace, regchg=CR.registry_change,
            observe=S.Manufacturing.observe)


def run():
    import application.test_v11_hardening as T
    r = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(unittest.defaultTestLoader.loadTestsFromModule(T))
    return dict(ran=r.testsRun, failed=sorted({str(t).split(" ")[0] for t, _ in r.failures + r.errors}))


def restore():
    RB.check, RB.diff, L.motor_findings, L.integrity_findings = orig["check"], orig["diff"], orig["find"], orig["integ"]
    S.Manufacturing.replace, CR.registry_change, S.Manufacturing.observe = orig["replace"], orig["regchg"], orig["observe"]


def m_binding_ignored():
    RB.check = lambda p, b, r: dict(orig["check"](p, b, r), status="OK", changes=[], detail="")


def m_missing_binding_tolerated():
    RB.check = lambda p, b, r: (lambda x: dict(x, status="OK") if x["status"] == "MISSING" else x)(orig["check"](p, b, r))


def m_diff_blind():
    RB.diff = lambda old, new: []


def m_review_needs_no_registry_ack():
    CR.registry_change = lambda app, path: dict(orig["regchg"](app, path), requiresAcknowledgement=False)


def m_integrity_guard_off():
    L.integrity_findings = lambda events: []


def m_sighting_ignored_by_guard():
    L.motor_findings = lambda reg, events, pol, part: [f for f in orig["find"](reg, events, pol, part) if f["source"] != "OBSERVATION"]


def m_replace_always_de():
    S.Manufacturing.replace = lambda self, motor, lot, slot="DE": orig["replace"](self, motor, lot, "DE")


results = dict(unmutated=run())
for name, fn in (("registry_binding_ignored", m_binding_ignored), ("missing_binding_tolerated", m_missing_binding_tolerated), ("registry_diff_blind", m_diff_blind),
                 ("review_needs_no_registry_ack", m_review_needs_no_registry_ack), ("integrity_guard_off", m_integrity_guard_off),
                 ("sighting_ignored_by_guard", m_sighting_ignored_by_guard), ("replace_always_de", m_replace_always_de)):
    fn(); results[name] = run(); restore()
for k, v in results.items():
    print(k, v["ran"], "tests; failing:", len(v["failed"]), v["failed"])
Path(sys.argv[1]).write_text(json.dumps(results, indent=1, sort_keys=True))
