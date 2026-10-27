"""Sensitivity check for scoped containment and the restricted recovery surface: each mutant removes one safety mechanism in-process (no file is changed);
the named tests must fail. The failing test names are recorded so each mutant is tied to a meaningful assertion, not to a crash.
usage (repository root):  python -B research/v1_1_scoped_containment/mutation_check.py OUT.json
"""
import io
import json
import shutil
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from application import checkpoint_ops as OPS, checkpoint_review as CR, lot_identity as L, server as SRV  # noqa: E402

orig = dict(containment=CR.containment, strings=CR._strings, sources=set(CR.CONTAINABLE_SOURCES), build=OPS.build_review, find=L.motor_findings,
            actions=SRV.RECOVERY_ACTIONS, status=SRV.recovery_status, propose=OPS.propose)


def run():
    import application.test_scoped_containment as A
    import application.test_stale_recovery as B
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(A), unittest.defaultTestLoader.loadTestsFromModule(B)])
    r = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return dict(ran=r.testsRun, failed=sorted({str(t).split(" ")[0] for t, _ in r.failures + r.errors}))


def restore():
    CR.containment, CR._strings, OPS.build_review, L.motor_findings = orig["containment"], orig["strings"], orig["build"], orig["find"]
    CR.CONTAINABLE_SOURCES.clear(); CR.CONTAINABLE_SOURCES.update(orig["sources"])
    SRV.RECOVERY_ACTIONS, SRV.recovery_status, OPS.propose = orig["actions"], orig["status"], orig["propose"]


def drop(name):
    def mutant():
        def f(*a, **k):
            ok, obs = orig["containment"](*a, **k)
            obs = [dict(o, holds=True) if o["obligation"] == name else o for o in obs]
            return all(o["holds"] for o in obs), obs
        CR.containment = f
    return mutant


def m_containment_always_true():
    CR.containment = lambda *a, **k: (True, [])


def m_shared_string_blind():
    CR._strings = lambda events: set()


def m_non_sighting_contained():
    CR.CONTAINABLE_SOURCES.update({"INSTALL", "REMOVAL", "RECALL_POLICY", "REGISTRY_BINDING", "OPERATION"})


def m_contained_needs_no_acknowledgement():
    def build(*a, **k):
        out = orig["build"](*a, **k)
        out["requiresAcknowledgement"] = [m for m in out["requiresAcknowledgement"] if m not in out["containedMotors"]]
        return out
    OPS.build_review = build          # checkpoint_ops imported the function by name, so that is the binding accept() and propose() use


def m_sighting_ignored_by_guard():
    L.motor_findings = lambda reg, events, pol, part: [f for f in orig["find"](reg, events, pol, part) if f["source"] != "OBSERVATION"]


def m_recovery_whitelist_widened():
    SRV.RECOVERY_ACTIONS = orig["actions"] + ("ship",)


def m_recovery_leaks_eligibility():
    SRV.recovery_status = lambda snap, custody: dict(orig["status"](snap, custody), eligibility=snap["eligibility"])


def m_proposal_activates_candidate():
    def propose(database, current, custody, previous=None):
        out = orig["propose"](database, current, custody, previous)
        if "candidate" in out:
            (Path(custody) / "accepted").mkdir(exist_ok=True); shutil.copy(out["candidate"], Path(custody) / "accepted" / "activated.json")
        return out
    OPS.propose = propose


MUTANTS = (("containment_always_true", m_containment_always_true), ("shared_string_blind", m_shared_string_blind),
           ("lookalike_rule_off", drop("NO_LOOKALIKE_OF_A_LOT_IN_USE_ELSEWHERE")), ("registry_binding_obligation_off", drop("REGISTRY_BINDING_OK")),
           ("recall_policy_obligation_off", drop("NO_RECALL_POLICY_FINDINGS")), ("integrity_obligation_off", drop("NO_INTEGRITY_FINDINGS_ON_MOTOR")),
           ("non_sighting_findings_contained", m_non_sighting_contained), ("contained_needs_no_acknowledgement", m_contained_needs_no_acknowledgement),
           ("sighting_ignored_by_guard", m_sighting_ignored_by_guard), ("recovery_whitelist_widened", m_recovery_whitelist_widened),
           ("recovery_leaks_eligibility", m_recovery_leaks_eligibility), ("proposal_activates_candidate", m_proposal_activates_candidate))

if __name__ == "__main__":
    only = set(sys.argv[2:])            # optional: run only the named mutants (the unmutated baseline always runs)
    results = dict(unmutated=run())
    for name, fn in MUTANTS:
        if only and name not in only:
            continue
        fn(); results[name] = run(); restore()
    for k, v in results.items():
        print(k, v["ran"], "tests; failing:", len(v["failed"]), v["failed"])
    Path(sys.argv[1]).write_text(json.dumps(results, indent=1, sort_keys=True))
    survivors = [k for k, v in results.items() if k != "unmutated" and not v["failed"]]
    sys.exit(1 if survivors or results["unmutated"]["failed"] else 0)
