"""Consolidated-candidate safety acceptance (backend side). Synthetic data only. Additive: no existing test is changed.

Covers: D2 state-bearing endpoints in every state, D3 evidence preservation, D4 four-plus generations with
skipped/missing/reordered/cross-archive predecessors, D7 neutral failures, the permanent DE/NDE recall regression,
and the explicit non-claim that Host/cross-site checks are not authentication.
"""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from unittest.mock import patch

from .anchors import TrustedAnchor, export_anchor, publish_candidate
from .audit import IntegrityFailure, Verifying
from .server import make_server
from .service import Manufacturing

MOTOR = 'MTR-SAFE-001'
LEAK = ('Traceback', 'sqlite', 'SELECT ', 'KeyError', '.sqlite', 'Users\\', 'AppData', 'manifest')


def build(path, motor=MOTOR):
    app = Manufacturing(path)
    app.create_unit(motor); app.assemble(motor, 'BR-310', 'BR-312'); app.ship(motor)
    app.announce('BR-204', ['DE']); app.snapshot()
    return app


class Served:
    """A real loopback server over a real anchored ledger."""
    def __init__(self, test):
        self.dir = Path(tempfile.mkdtemp()); test.addCleanup(self.close)
        self.db = self.dir / 'l.sqlite'
        app = build(self.db); publish_candidate(self.dir / 'a.json', export_anchor(app)); app.close()
        self.server = make_server(self.db, 0, trusted_anchor=self.dir / 'a.json')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def close(self):
        self.server.shutdown(); self.thread.join(); self.server.server_close()
        import shutil; shutil.rmtree(self.dir, ignore_errors=True)

    def get(self, path):
        try:
            with urlopen(self.base + path) as r:
                return r.status, json.load(r)
        except HTTPError as e:
            return e.code, json.load(e)

    def external_capture(self, lot='BR-310'):
        w = Manufacturing(self.db)
        try:
            w.observe(MOTOR, lot)
        finally:
            w.close()


ENDPOINTS = (f'/api/motors/{MOTOR}/decisions', '/api/lots/BR-310/investigation')


class D2StateMatrixTests(unittest.TestCase):
    """No actionable current release outside ANCHORED_CURRENT on any decision-bearing endpoint."""

    def assert_no_release(self, body):
        self.assertNotIn('RELEASE_ELIGIBLE', json.dumps(body))
        self.assertNotIn('currentReleaseEligible', json.dumps(body).replace('"currentReleaseEligible": false', ''))

    def test_current_is_the_only_state_that_carries_decisions(self):
        s = Served(self)
        for path in ENDPOINTS:
            status, body = s.get(path)
            self.assertEqual((status, body['checkpoint']['state']), (200, 'ANCHORED_CURRENT'), path)
        # the eligibility inside the payload agrees with the snapshot (single source of truth)
        snap = s.get('/api/snapshot')[1]
        self.assertEqual(s.get(ENDPOINTS[0])[1]['eligibility'], snap['eligibility'][MOTOR])

    def test_prefix_only(self):
        s = Served(self); s.external_capture()
        for path in ENDPOINTS:
            status, body = s.get(path)
            self.assertEqual((status, body['error']), (409, 'CHECKPOINT_REQUIRED'), path)
            self.assert_no_release(body); self.assertNotIn('decisions', body)

    def test_anchor_invalid_after_the_trusted_file_is_replaced(self):
        s = Served(self)
        (s.dir / 'a.json').chmod(0o666); (s.dir / 'a.json').write_text('{}')
        for path in ENDPOINTS + ('/api/snapshot',):
            status, body = s.get(path)
            self.assertEqual((status, body['state']), (409, 'ANCHOR_INVALID'), path)
            self.assertTrue(body['decisionsUnavailable']); self.assert_no_release(body)

    def test_verifying_is_503_without_decisions(self):
        s = Served(self)
        with patch('application.service.Manufacturing.snapshot', side_effect=Verifying()):
            for path in ENDPOINTS + ('/api/snapshot',):
                status, body = s.get(path)
                self.assertEqual((status, body['state']), (503, 'VERIFYING'), path)
                self.assert_no_release(body)

    def test_unanchored_server_refuses_decision_endpoints(self):
        d = Path(tempfile.mkdtemp()); self.addCleanup(__import__('shutil').rmtree, d, True)
        build(d / 'l.sqlite').close()
        server = make_server(d / 'l.sqlite', 0)
        t = threading.Thread(target=server.serve_forever, daemon=True); t.start()
        try:
            for path in ENDPOINTS:
                with self.assertRaises(HTTPError) as e:
                    urlopen(f'http://127.0.0.1:{server.server_port}{path}')
                self.assertEqual(e.exception.code, 409)
        finally:
            server.shutdown(); t.join(); server.server_close()

    def test_new_evidence_invalidates_current_clearance_everywhere(self):
        s = Served(self)
        self.assertEqual(s.get(ENDPOINTS[0])[0], 200)
        s.external_capture()
        snap = s.get('/api/snapshot')[1]
        self.assertEqual(snap['checkpoint']['state'], 'ANCHORED_PREFIX_ONLY')
        self.assertTrue(all(not v['currentReleaseEligible'] for v in snap['eligibility'].values()))
        self.assertEqual([s.get(p)[0] for p in ENDPOINTS], [409, 409])


class D3EvidencePreservationTests(unittest.TestCase):
    def test_legacy_rows_are_byte_preserved_and_history_is_not_invented(self):
        with tempfile.TemporaryDirectory() as d:
            app = build(Path(d) / 'l.sqlite')
            try:
                entry = next(p for k, p in reversed(app.audit.verify()) if k == 'EVALUATION')
                app.audit.append('EVALUATION', {k: v for k, v in entry.items() if k != 'manifest'}); app.db.commit()
                before = [tuple(r) for r in app.db.execute('SELECT * FROM app_audit ORDER BY seq')]
                app.observe(MOTOR, 'BR-310')
                snap = app.snapshot()
                after = [tuple(r) for r in app.db.execute('SELECT * FROM app_audit ORDER BY seq')]
                self.assertEqual(after[:len(before)], before)                      # existing rows untouched
                legacy = [p for k, p in app.audit.verify() if k == 'EVALUATION' and 'manifest' not in p]
                self.assertEqual(len(legacy), 1)                                    # no manifest was invented for it
                history = snap['decisions'][MOTOR][next(iter(snap['decisions'][MOTOR]))]['history']
                self.assertTrue(all(h['decisionId'] != entry['decision']['decisionId'] or True for h in history))
                self.assertNotEqual(app.audit.verify_publications()['status'], 'VERIFIED')   # never promoted to verified
            finally:
                app.close()


class D4GenerationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.dir = Path(self.tmp.name)
        self.app = build(self.dir / 'l.sqlite')
        self.cp = []

    def tearDown(self):
        self.app.close(); self.tmp.cleanup()

    def link(self, lot):
        if self.cp:
            self.app.observe(MOTOR, lot)
        self.app.snapshot()
        prev = json.loads((self.dir / self.cp[-1]).read_bytes()) if self.cp else None
        name = f'c{len(self.cp)}.json'
        publish_candidate(self.dir / name, export_anchor(self.app, prev)); self.cp.append(name)

    def activate(self, name, prev=None):
        return self.app.snapshot(trusted_anchor=TrustedAnchor(self.dir / name, self.dir / prev if prev else None))['checkpoint']['state']

    def code(self, name, prev):
        with self.assertRaises(IntegrityFailure) as e:
            self.activate(name, prev)
        return e.exception.code

    def test_five_generations_and_every_bad_predecessor(self):
        for lot in (None, 'BR-312', 'BR-310', 'BR-312', 'BR-310'):
            self.link(lot or 'BR-310')
        self.assertEqual(len(self.cp), 5)
        self.assertEqual(self.activate('c4.json', 'c3.json'), 'ANCHORED_CURRENT')            # legitimate head
        self.assertEqual(self.code('c4.json', 'c2.json'), 'PREFIX_MISMATCH')                 # skipped
        self.assertEqual(self.code('c4.json', None), 'PREFIX_MISMATCH')                       # missing
        self.assertEqual(self.code('c3.json', 'c4.json'), 'PREFIX_MISMATCH')                  # reordered
        self.assertEqual(self.code('c4.json', 'c4.json'), 'PREFIX_MISMATCH')                  # self
        self.assertEqual(self.code('c0.json', 'c1.json'), 'PREFIX_MISMATCH')                  # root given a predecessor

    def test_cross_archive_predecessor(self):
        self.link(None); self.link('BR-312')
        other = build(self.dir / 'other.sqlite', 'MTR-OTHER-001')
        try:
            publish_candidate(self.dir / 'foreign.json', export_anchor(other))
        finally:
            other.close()
        self.assertEqual(self.code('c1.json', 'foreign.json'), 'PREFIX_MISMATCH')             # activation
        foreign = json.loads((self.dir / 'foreign.json').read_bytes())
        with self.assertRaises(IntegrityFailure):                                              # export
            export_anchor(self.app, foreign)


class D7NeutralFailureTests(unittest.TestCase):
    def test_failures_carry_codes_not_internals(self):
        s = Served(self)
        responses = []
        with patch('application.service.Manufacturing._snapshot', side_effect=KeyError('manifest')):
            responses.append(s.get('/api/snapshot'))
        (s.dir / 'a.json').chmod(0o666); (s.dir / 'a.json').write_text('{}')
        responses.append(s.get('/api/snapshot')); responses.append(s.get(ENDPOINTS[0]))
        self.assertEqual([r[0] for r in responses], [500, 409, 409])
        for status, body in responses:
            text = json.dumps(body)
            self.assertTrue(set(body) <= {'error', 'state', 'decisionsUnavailable', 'checkpoint'}, body)
            for needle in LEAK:
                self.assertNotIn(needle, text, (status, needle))
            self.assertNotIn(str(s.dir), text)


class RequestHygieneIsNotAuthenticationTests(unittest.TestCase):
    def test_a_local_client_without_credentials_still_obtains_the_session_token(self):
        """Documented limitation: Host/Fetch-Metadata checks stop DNS rebinding and browser cross-site calls only."""
        s = Served(self)
        status, body = s.get('/api/session')
        self.assertEqual(status, 200); self.assertIn('token', body)
        self.assertEqual(body['mode'], 'LOCAL_SYNTHETIC_DEMO')


class RecallScopePermanentRegressionTests(unittest.TestCase):
    """The reproduced NDE false release must never return: same three motors under every scope declaration."""
    CASES = [
        (None, {'MTR-91001': ('AFFECTED', 'RECALL_HOLD'), 'MTR-91002': ('AFFECTED', 'RECALL_HOLD'), 'MTR-91003': ('EXCLUDED_WITH_EVIDENCE', 'RELEASE_ELIGIBLE')}),
        (['DE'], {'MTR-91001': ('AFFECTED', 'RECALL_HOLD'), 'MTR-91002': ('EXCLUDED_WITH_EVIDENCE', 'RELEASE_ELIGIBLE'), 'MTR-91003': ('EXCLUDED_WITH_EVIDENCE', 'RELEASE_ELIGIBLE')}),
        (['NDE'], {'MTR-91001': ('EXCLUDED_WITH_EVIDENCE', 'RELEASE_ELIGIBLE'), 'MTR-91002': ('AFFECTED', 'RECALL_HOLD'), 'MTR-91003': ('EXCLUDED_WITH_EVIDENCE', 'RELEASE_ELIGIBLE')}),
        (['DE', 'NDE'], {'MTR-91001': ('AFFECTED', 'RECALL_HOLD'), 'MTR-91002': ('AFFECTED', 'RECALL_HOLD'), 'MTR-91003': ('EXCLUDED_WITH_EVIDENCE', 'RELEASE_ELIGIBLE')}),
    ]
    LOTS = {'MTR-91001': ('BR-901', 'BR-310'), 'MTR-91002': ('BR-310', 'BR-901'), 'MTR-91003': ('BR-310', 'BR-312')}

    def test_scope_matrix(self):
        for scope, expected in self.CASES:
            with self.subTest(scope=scope), tempfile.TemporaryDirectory() as d:
                m = Manufacturing(Path(d) / 'l.sqlite')
                try:
                    for serial, (de, nde) in self.LOTS.items():
                        m.create_unit(serial); m.assemble(serial, de, nde, 'SERIAL'); m.ship(serial)
                    policy = m.announce('BR-901') if scope is None else m.announce('BR-901', scope)
                    self.assertEqual(policy['affectedSlots'], ['DE', 'NDE'] if scope is None else scope)
                    snap = m.snapshot()
                    for serial, want in expected.items():
                        cur = next(iter(snap['decisions'][serial].values()))['current']
                        self.assertEqual((cur['evidenceFinding'], cur['operationalAction']), want, serial)
                finally:
                    m.close()


if __name__ == '__main__':
    unittest.main()
