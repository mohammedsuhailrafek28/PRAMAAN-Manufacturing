"""Sensitivity check: do the A+B tests fail when a safety mechanism is removed? Mutants are applied in-process only (no file is changed).
usage: python -B research/lot_identity_ab/mutation_check.py OUT.json   (from the repository root)
"""
import io
import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from application import lot_identity as L, service as S, checkpoint_ops as OPS, checkpoint_review as CR  # noqa: E402

orig = dict(guard=L.guard_decision, lot=S.Manufacturing.lot, build=CR.build_review, interrupted=L.interrupted_operations, find=L.motor_findings)


def run():
    import application.test_lot_identity_ab as T
    suite = unittest.defaultTestLoader.loadTestsFromModule(T)
    r = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return dict(ran=r.testsRun, failed=sorted({str(t).split(" ")[0] for t, _ in r.failures + r.errors}))


def restore():
    L.guard_decision, S.Manufacturing.lot = orig["guard"], orig["lot"]
    CR.build_review = OPS.build_review = orig["build"]
    L.interrupted_operations, L.motor_findings = orig["interrupted"], orig["find"]


def m_no_guard():
    L.guard_decision = lambda cur, found, broken=(): dict(cur, evaluatorOperationalAction=cur.get("operationalAction"), identityGuard=dict(status="IDENTITY_ESTABLISHED_LOCAL_REGISTRY", findings=[]), integrityGuard=dict(status="OPERATIONALLY_CONSISTENT", findings=[]), quarantine=None)


def m_permissive_capture():
    S.Manufacturing.lot = lambda self, raw, what, dated=True: raw if isinstance(raw, str) and raw.strip() else (_ for _ in ()).throw(S.ValidationFailure("x"))


def m_review_ignores_identity():
    def build(app, a, b, c=None):
        r = orig["build"](app, a, b, c); r["refusedForIdentity"] = []; return r
    CR.build_review = OPS.build_review = build


def m_no_interrupted():
    L.interrupted_operations = lambda events: []


def m_lookalike_reclassifies_registered():
    def find(registry, events, policy, part):
        out = orig["find"](registry, events, policy, part)
        for e in events:
            if e["eventType"] == "COMPONENT_INSTALLED" and e["payload"]["lot"] in ("BR-205", "BR-311"):
                out.append(dict(eventId=e["eventId"], slot=e["payload"]["slot"], lot=e["payload"]["lot"], source="INSTALL", reason="NEAR_MISS_OF_RECALLED_LOT", detail="", resembles=[]))
        return out
    L.motor_findings = find


results = dict(unmutated=run())
for name, fn in (("guard_disabled", m_no_guard), ("capture_validation_permissive", m_permissive_capture), ("review_ignores_identity", m_review_ignores_identity),
                 ("interrupted_ops_ignored", m_no_interrupted), ("lookalike_holds_registered_adjacent_lots", m_lookalike_reclassifies_registered)):
    fn(); results[name] = run(); restore()
for k, v in results.items():
    print(k, v["ran"], "tests; failing:", len(v["failed"]), v["failed"])
Path(sys.argv[1]).write_text(json.dumps(results, indent=1, sort_keys=True))
