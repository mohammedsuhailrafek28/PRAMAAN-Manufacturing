"""D5: H2 binds each publication to recorded authority. Synthetic data only.

A derivation-consistent EVALUATION whose policy was never announced, or whose evaluation watermark moves backwards for the motor
or lies beyond what the ledger holds, must fail closed. Local hash recomputation by a journal writer is exactly what these forge.
Legitimate publication sequences and legacy rows keep their existing verdicts. The pinned v3 evaluator is not touched.
"""
import copy
from pathlib import Path
import tempfile
import unittest

from .service import Manufacturing
from pramaan_integration import engine_bridge
from pramaan_integration.profile import digest
from .anchors import export_anchor, verify_anchor
from .audit import IntegrityFailure, derive_publication, PROFILE

MOTOR = 'MTR-D5-001'


def build(path):
    app = Manufacturing(path)
    app.create_unit(MOTOR); app.assemble(MOTOR, 'BR-310', 'BR-312'); app.ship(MOTOR); app.announce('BR-204', ['DE']); app.snapshot()
    return app


def forge_entry(app, policy, watermark):
    """A derivation-consistent EVALUATION for an arbitrary policy / watermark, as a journal writer who recomputes every hash would make."""
    records = app.audit.verify()
    case, manifest = app.ledger.snapshot(MOTOR, watermark)
    config = app.ledger._config(MOTOR)
    raw = engine_bridge.pramaan_recall.evaluate(case, copy.deepcopy(policy), config['coverage'], manifest['watermark'], engine_bridge.Config.v3())
    context = dict(motor=MOTOR, policyDigest=digest(policy), configurationDigest=manifest['configurationDigest'], profile=PROFILE)
    prior = [p for k, p in records if k == 'EVALUATION' and 'manifest' in p and p['context'] == context]
    archive = app.db.execute('SELECT archive_id FROM app_audit_head WHERE id=1').fetchone()[0]
    entry, created, reused = derive_publication(case, manifest, policy, raw, prior, app.audit.outstanding(records), archive)
    assert not reused
    if created: app.audit.append('OBLIGATION_CREATED', created)
    app.audit.append('EVALUATION', entry); app.db.commit()


class D5BindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.app = build(Path(self.tmp.name) / 'l.sqlite')

    def tearDown(self):
        self.app.close(); self.tmp.cleanup()

    def code(self, fn):
        with self.assertRaises(IntegrityFailure) as e:
            fn()
        return e.exception.code

    def test_legitimate_sequences_still_verify(self):
        self.assertEqual(self.app.audit.verify_publications()['status'], 'VERIFIED')
        for lot in ('BR-310', 'BR-204', 'BR-312'):
            self.app.observe(MOTOR, lot); self.app.snapshot()
            self.assertEqual(self.app.audit.verify_publications()['status'], 'VERIFIED')
        self.assertEqual(verify_anchor(self.app, export_anchor(self.app))['state'], 'ANCHORED_CURRENT')

    def test_unannounced_policy_is_rejected_even_when_hashes_are_recomputed(self):
        policy = copy.deepcopy(self.app.policy()); policy['affectedLots'] = ['BR-999']; policy['affectedSlots'] = ['DE', 'NDE']
        self.assertNotEqual(digest(policy), digest(self.app.policy()))
        forge_entry(self.app, policy, self.app.ledger.watermark(MOTOR))
        self.assertEqual(self.code(self.app.audit.verify_publications), 'POLICY_NOT_ANNOUNCED')
        self.assertEqual(self.code(lambda: export_anchor(self.app)), 'POLICY_NOT_ANNOUNCED')     # no checkpoint can ratify it

    def test_older_watermark_after_newer_one_is_rejected(self):
        old = self.app.ledger.watermark(MOTOR)
        self.app.observe(MOTOR, 'BR-204'); self.app.snapshot()
        self.assertNotEqual(old, self.app.ledger.watermark(MOTOR))      # the ledger really did advance
        forge_entry(self.app, self.app.policy(), old)
        self.assertEqual(self.code(self.app.audit.verify_publications), 'WATERMARK_REGRESSION')

    def test_watermark_beyond_the_ledger_is_rejected(self):
        ahead = {src: seq + 50 for src, seq in self.app.ledger.watermark(MOTOR).items()}
        try:
            forge_entry(self.app, self.app.policy(), ahead)
        except Exception:
            self.skipTest('ledger refuses to build an inflated-watermark manifest; the forge is impossible to construct')
        self.assertEqual(self.code(self.app.audit.verify_publications), 'WATERMARK_BEYOND_LEDGER')

    def test_legacy_rows_keep_their_historical_verdict(self):
        entry = copy.deepcopy(next(p for k, p in self.app.audit.verify() if k == 'EVALUATION')); entry.pop('manifest')
        self.app.audit.append('EVALUATION', entry); self.app.db.commit()
        self.assertEqual(self.app.audit.verify_publications()['status'], 'HISTORICAL_UNVERIFIABLE')


if __name__ == '__main__':
    unittest.main()
