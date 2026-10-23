"""Operator checkpoint workflow: a local candidate is never trust, and nothing is activated implicitly."""
import json
from pathlib import Path
import tempfile
import unittest

from .anchors import TrustedAnchor, export_anchor, publish_candidate
from .audit import IntegrityFailure
from . import checkpoint_ops as ops
from .service import Manufacturing

MOTOR = 'MTR-OPS-001'


class OperatorWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.dir = Path(self.tmp.name)
        self.db = self.dir / 'l.sqlite'; self.custody = self.dir / 'custody'; self.custody.mkdir()
        app = Manufacturing(self.db)
        app.create_unit(MOTOR); app.assemble(MOTOR, 'BR-310', 'BR-312'); app.ship(MOTOR); app.announce('BR-204', ['DE']); app.snapshot()
        self.c0 = self.custody / 'c0.json'; publish_candidate(self.c0, export_anchor(app)); app.close()

    def tearDown(self):
        self.tmp.cleanup()

    def capture(self, lot='BR-310'):
        app = Manufacturing(self.db); app.observe(MOTOR, lot); app.close()

    def state(self, anchor, previous=None):
        app = Manufacturing(self.db)
        try:
            return app.snapshot(trusted_anchor=TrustedAnchor(anchor, previous))['checkpoint']['state']
        finally:
            app.close()

    def test_full_cycle_candidate_is_inert_until_accepted_and_activated(self):
        self.assertEqual(ops.propose(self.db, self.c0, self.custody)['status'], 'NO_CANDIDATE_NEEDED')
        self.capture()
        self.assertEqual(self.state(self.c0), 'ANCHORED_PREFIX_ONLY')
        out = ops.propose(self.db, self.c0, self.custody)
        self.assertEqual(out['status'], ops.STATUS_PROPOSED)
        self.assertGreater(out['covers']['newJournalEntries'], 0)
        cand = Path(out['candidate'])
        # the candidate alone changes nothing: the running trust reference is still the old checkpoint
        self.assertEqual(self.state(self.c0), 'ANCHORED_PREFIX_ONLY')
        rec = ops.accept(self.db, self.c0, self.custody, cand, 'Test Custodian', out['candidateSha256'])
        self.assertEqual(rec['status'], ops.STATUS_ACCEPTED)
        self.assertIn('not independent custody', rec['note'])
        self.assertIn('--previous-anchor', rec['restart'])
        accepted = Path(rec['accepted'])
        self.assertEqual(self.state(accepted, self.c0), 'ANCHORED_CURRENT')
        self.assertFalse(accepted.stat().st_mode & 0o222)                      # read-only
        with self.assertRaises(IntegrityFailure) as e:                         # R15: a successor without its predecessor is invalid
            self.state(accepted)
        self.assertEqual(e.exception.code, 'PREFIX_MISMATCH')

    def test_three_generations_through_the_workflow(self):
        previous, prev_prev = self.c0, None
        for lot in ('BR-310', 'BR-312', 'BR-310'):
            self.capture(lot)
            out = ops.propose(self.db, previous, self.custody, prev_prev)
            rec = ops.accept(self.db, previous, self.custody, Path(out['candidate']), 'Test Custodian', out['candidateSha256'])
            previous, prev_prev = Path(rec['accepted']), previous
        self.assertEqual(self.state(previous, prev_prev), 'ANCHORED_CURRENT')

    def test_refusals(self):
        self.capture()
        out = ops.propose(self.db, self.c0, self.custody); cand = Path(out['candidate'])
        with self.assertRaises(SystemExit):                                     # wrong typed digest
            ops.accept(self.db, self.c0, self.custody, cand, 'Test Custodian', '0' * 64)
        with self.assertRaises(SystemExit):                                     # no named custodian
            ops.accept(self.db, self.c0, self.custody, cand, '  ', out['candidateSha256'])
        outside = self.dir / 'elsewhere.json'; outside.write_bytes(cand.read_bytes())
        with self.assertRaises(SystemExit):                                     # not a file this tool proposed
            ops.accept(self.db, self.c0, self.custody, outside, 'Test Custodian', ops.sha256_file(outside))
        self.capture('BR-312')                                                  # ledger moved after the proposal
        with self.assertRaises(SystemExit):
            ops.accept(self.db, self.c0, self.custody, cand, 'Test Custodian', out['candidateSha256'])
        self.assertFalse((self.custody / 'accepted').exists() and any((self.custody / 'accepted').iterdir()))

    def test_no_overwrite_of_an_accepted_checkpoint(self):
        self.capture()
        out = ops.propose(self.db, self.c0, self.custody)
        ops.accept(self.db, self.c0, self.custody, Path(out['candidate']), 'Test Custodian', out['candidateSha256'])
        with self.assertRaises(FileExistsError):
            ops.accept(self.db, self.c0, self.custody, Path(out['candidate']), 'Test Custodian', out['candidateSha256'])


if __name__ == '__main__':
    unittest.main()
