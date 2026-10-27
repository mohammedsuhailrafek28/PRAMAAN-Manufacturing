"""D6: what a read may write. Synthetic data only.

Status: reduced, not eliminated. A read with unchanged evidence never touches the journal. The only write on the read path is the
one-time publication of decisions for evidence that arrived since the last publication (the journal record is what makes a decision
'issued' and replayable), and a read that fails rolls that write back. Removing even that write needs an explicit publisher process or
a pending-publication state, which changes operations; it is presented to the owner as an alternative, not applied here.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .anchors import TrustedAnchor, export_anchor, publish_candidate
from .audit import IntegrityFailure
from .service import Manufacturing

MOTOR = 'MTR-D6-001'


def journal(app):
    return [tuple(r) for r in app.db.execute('SELECT * FROM app_audit ORDER BY seq')]


class ReadPathWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); d = Path(self.tmp.name)
        self.app = Manufacturing(d / 'l.sqlite')
        self.app.create_unit(MOTOR); self.app.assemble(MOTOR, 'BR-310', 'BR-312'); self.app.record_historical_shipment_fixture(MOTOR)
        self.app.announce('BR-204', ['DE']); self.app.snapshot()
        publish_candidate(d / 'a.json', export_anchor(self.app)); self.trusted = TrustedAnchor(d / 'a.json')

    def tearDown(self):
        self.app.close(); self.tmp.cleanup()

    def test_reads_with_unchanged_evidence_leave_the_journal_byte_identical(self):
        before = journal(self.app)
        for _ in range(3):
            self.app.snapshot(trusted_anchor=self.trusted)
        self.assertEqual(journal(self.app), before)

    def test_only_new_evidence_causes_a_publication_and_it_happens_once(self):
        before = journal(self.app)
        self.app.observe(MOTOR, 'BR-204')                       # external evidence; no publication yet
        self.assertEqual(len(journal(self.app)), len(before))   # the capture itself does not write the audit journal
        self.app.snapshot(trusted_anchor=self.trusted)
        published = journal(self.app)
        self.assertGreater(len(published), len(before))
        self.assertEqual(published[:len(before)], before)       # append-only: earlier rows untouched
        self.app.snapshot(trusted_anchor=self.trusted)
        self.assertEqual(journal(self.app), published)          # second read writes nothing

    def test_a_failed_read_rolls_back_its_publication(self):
        self.app.observe(MOTOR, 'BR-204')
        before = journal(self.app)
        real = self.trusted.verify
        calls = {'n': 0}

        def flaky(app, **kw):
            calls['n'] += 1
            if calls['n'] > 1:                                  # fail AFTER the publication was written
                raise IntegrityFailure('PREFIX_MISMATCH')
            return real(app, **kw)
        with patch.object(self.trusted, 'verify', side_effect=flaky), self.assertRaises(IntegrityFailure):
            self.app.snapshot(trusted_anchor=self.trusted)
        self.assertEqual(journal(self.app), before)


if __name__ == '__main__':
    unittest.main()
