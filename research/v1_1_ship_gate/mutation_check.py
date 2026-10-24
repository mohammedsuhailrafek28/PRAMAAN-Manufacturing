"""Sensitivity check for the ordinary shipment gate: each mutant removes one safety mechanism in-process (no file is changed); the shipment-gate tests must fail.
usage (repository root):  python -B research/v1_1_ship_gate/mutation_check.py OUT.json [mutant names...]
"""
import io
import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from application import service as SVC  # noqa: E402

M = SVC.Manufacturing
orig = dict(ship=M.ship, snapshot=M.snapshot, fingerprint=M.FINGERPRINT_SQL)


def run():
    import application.test_ship_gate as A
    import application.test_stale_recovery as B
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromModule(A), unittest.defaultTestLoader.loadTestsFromModule(B)])
    r = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return dict(ran=r.testsRun, failed=sorted({str(t).split(" ")[0] for t, _ in r.failures + r.errors}))


def restore():
    M.ship, M.snapshot, M.FINGERPRINT_SQL = orig["ship"], orig["snapshot"], orig["fingerprint"]


def m_gate_disabled():
    M.ship = lambda self, motor, *, trusted_anchor=None: self.record_historical_shipment_fixture(motor)


def m_anchor_optional():
    def ship(self, motor, *, trusted_anchor=None):
        return orig["ship"](self, motor, trusted_anchor=trusted_anchor) if trusted_anchor is not None else self.record_historical_shipment_fixture(motor)
    M.ship = ship


def m_eligibility_ignored():
    def snapshot(self, *, trusted_anchor=None, ship_ticket=None):
        result = orig["snapshot"](self, trusted_anchor=trusted_anchor, ship_ticket=ship_ticket)
        if ship_ticket is not None:
            result["eligibility"][ship_ticket] = dict(currentReleaseEligible=True)
            with self.db:
                self.db.execute("DELETE FROM app_ship_tickets WHERE motor=?", (ship_ticket,))
                self.db.execute("INSERT INTO app_ship_tickets SELECT ?,(" + self.FINGERPRINT_SQL.removeprefix("SELECT ") + ")", (ship_ticket,))
        return result
    M.snapshot = snapshot


def m_fingerprint_constant():
    M.FINGERPRINT_SQL = "SELECT 'constant'"


MUTANTS = (("gate_disabled", m_gate_disabled), ("anchor_optional", m_anchor_optional),
           ("eligibility_ignored", m_eligibility_ignored), ("ticket_not_bound_to_ledger_state", m_fingerprint_constant))

if __name__ == "__main__":
    only = set(sys.argv[2:])
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
