"""Unified-candidate regression tests for audit findings D2, D3, D4 and D7. Synthetic data only.

Each test names the original behavior, the unsafe or broken outcome it rejects, and the approved contract it keeps.
"""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from .anchors import TrustedAnchor, export_anchor, publish_candidate
from .audit import IntegrityFailure
from .server import make_server
from .service import Manufacturing

MOTOR = 'MTR-UNI-001'


def build(path):
    app = Manufacturing(path)
    app.create_unit(MOTOR); app.assemble(MOTOR, 'BR-310', 'BR-312'); app.ship(MOTOR)
    app.announce('BR-204', ['DE'])
    app.snapshot()
    return app


class ChainDepthTests(unittest.TestCase):
    """D4: export_anchor could not extend a chain past two links."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.dir = Path(self.tmp.name)
        self.app = build(self.dir / 'l.sqlite')

    def tearDown(self):
        self.app.close(); self.tmp.cleanup()

    def link(self, name, previous=None):
        self.app.snapshot()
        anchor = export_anchor(self.app, previous)
        publish_candidate(self.dir / name, anchor)
        return anchor

    def extend(self, lot):
        self.app.observe(MOTOR, lot); self.app.snapshot()

    def test_third_and_fourth_generation_export_and_activate(self):
        c0 = self.link('c0.json'); self.extend('BR-310')
        c1 = self.link('c1.json', c0); self.extend('BR-312')
        c2 = self.link('c2.json', c1)  # failed with PREFIX_MISMATCH before the fix
        self.extend('BR-310')
        c3 = self.link('c3.json', c2)
        snap = self.app.snapshot(trusted_anchor=TrustedAnchor(self.dir / 'c3.json', self.dir / 'c2.json'))
        self.assertEqual(snap['checkpoint']['state'], 'ANCHORED_CURRENT')
        self.assertTrue(c3['body']['previousCheckpointHash'])

    def test_negative_skip_link_and_missing_previous_still_rejected(self):
        c0 = self.link('c0.json'); self.extend('BR-310')
        c1 = self.link('c1.json', c0); self.extend('BR-312')
        self.link('c2.json', c1)
        for previous in (self.dir / 'c0.json', None):  # skipped link, or a successor without its predecessor
            with self.assertRaises(IntegrityFailure) as e:
                self.app.snapshot(trusted_anchor=TrustedAnchor(self.dir / 'c2.json', previous))
            self.assertEqual(e.exception.code, 'PREFIX_MISMATCH')

    def test_export_with_an_unrelated_previous_is_rejected(self):
        c0 = self.link('c0.json'); self.extend('BR-310')
        c1 = self.link('c1.json', c0)
        other = build(self.dir / 'other.sqlite')
        try:
            other_anchor = export_anchor(other)
        finally:
            other.close()
        with self.assertRaises(IntegrityFailure):
            export_anchor(self.app, other_anchor)
        self.assertIsNotNone(c1)


class LegacyRowTests(unittest.TestCase):
    """D3: a manifest-less EVALUATION followed by new evidence made /api/snapshot fail with KeyError('manifest')."""

    def test_legacy_row_stays_in_journal_and_new_evidence_still_publishes(self):
        with tempfile.TemporaryDirectory() as d:
            app = build(Path(d) / 'l.sqlite')
            try:
                records = app.audit.verify()
                entry = next(p for k, p in reversed(records) if k == 'EVALUATION')
                legacy = {k: v for k, v in entry.items() if k != 'manifest'}
                app.audit.append('EVALUATION', legacy); app.db.commit()
                before = [r for r in app.audit.verify()]
                app.observe(MOTOR, 'BR-310')
                snap = app.snapshot()  # must not raise
                self.assertIn(MOTOR, snap['decisions'])
                self.assertEqual(app.audit.verify()[:len(before)], before)  # historical rows untouched
                self.assertEqual(app.audit.verify_publications()['status'], 'HISTORICAL_UNVERIFIABLE')
            finally:
                app.close()

    def test_legacy_row_never_yields_current_clearance(self):
        with tempfile.TemporaryDirectory() as d:
            app = build(Path(d) / 'l.sqlite')
            try:
                entry = next(p for k, p in reversed(app.audit.verify()) if k == 'EVALUATION')
                app.audit.append('EVALUATION', {k: v for k, v in entry.items() if k != 'manifest'}); app.db.commit()
                anchor = Path(d) / 'a.json'; publish_candidate(anchor, export_anchor(app))
                snap = app.snapshot(trusted_anchor=TrustedAnchor(anchor))
                self.assertNotEqual(snap['checkpoint']['state'], 'ANCHORED_CURRENT')
                self.assertFalse(snap['eligibility'][MOTOR]['currentReleaseEligible'])
            finally:
                app.close()


class SubResourceTests(unittest.TestCase):
    """D2/D7: decision sub-resources carried no checkpoint state; internal read faults were reported as 400."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.dir = Path(self.tmp.name)
        self.db = self.dir / 'l.sqlite'
        app = build(self.db); app.close()
        app = Manufacturing(self.db)
        publish_candidate(self.dir / 'a.json', export_anchor(app)); app.close()
        self.server = make_server(self.db, 0, trusted_anchor=self.dir / 'a.json')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown(); self.thread.join(); self.server.server_close(); self.tmp.cleanup()

    def get(self, path):
        try:
            with urlopen(self.base + path) as r:
                return r.status, json.load(r)
        except HTTPError as e:
            return e.code, json.load(e)

    def external_capture(self):
        w = Manufacturing(self.db)
        try:
            w.observe(MOTOR, 'BR-310')
        finally:
            w.close()

    def test_current_state_travels_with_decisions_and_investigation(self):
        status, body = self.get(f'/api/motors/{MOTOR}/decisions')
        self.assertEqual(status, 200)
        self.assertEqual(body['checkpoint']['state'], 'ANCHORED_CURRENT')
        self.assertIn('currentReleaseEligible', body['eligibility'])
        status, body = self.get('/api/lots/BR-310/investigation')
        self.assertEqual((status, body['checkpoint']['state']), (200, 'ANCHORED_CURRENT'))
        self.assertIn(MOTOR, body['eligibility'])

    def test_prefix_only_withholds_decision_sub_resources(self):
        self.external_capture()
        self.assertEqual(self.get('/api/snapshot')[1]['checkpoint']['state'], 'ANCHORED_PREFIX_ONLY')
        for path in (f'/api/motors/{MOTOR}/decisions', '/api/lots/BR-310/investigation'):
            status, body = self.get(path)
            self.assertEqual(status, 409, path)
            self.assertEqual(body['error'], 'CHECKPOINT_REQUIRED')
            self.assertTrue(body['decisionsUnavailable'])
            self.assertNotIn('RELEASE_ELIGIBLE', json.dumps(body))  # the unsafe old behavior: a bare release label
            self.assertNotIn('decisions', body)

    def test_internal_read_fault_is_not_a_client_error(self):
        from unittest.mock import patch
        with patch('application.service.Manufacturing._snapshot', side_effect=KeyError('manifest')):
            status, body = self.get('/api/snapshot')
        self.assertEqual(status, 500)
        self.assertEqual(body['error'], 'SNAPSHOT_UNAVAILABLE')
        self.assertTrue(body['decisionsUnavailable'])
        self.assertNotIn('manifest', json.dumps(body))


if __name__ == '__main__':
    unittest.main()
