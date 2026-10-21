"""Independent synthetic regression expectations, never imported by decision code."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from . import test_application as helpers
PID=helpers.PID
from .service import Manufacturing, ValidationFailure, LedgerBlocked, ROOT
from .provenance import verify


class RemediationTests(unittest.TestCase):
    setUp=helpers.ApplicationTests.setUp
    tearDown=helpers.ApplicationTests.tearDown
    current=helpers.ApplicationTests.current

    def test_scope_cartesian_regression(self):
        for i,(de,nde,scope) in enumerate((d,n,s) for d in ('BR-204','BR-310') for n in ('BR-204','BR-310') for s in (None,['DE'],['NDE'],['DE','NDE'])):
            with self.subTest(de=de,nde=nde,scope=scope), tempfile.TemporaryDirectory() as t:
                a=Manufacturing(Path(t)/'db')
                try:
                    m=f'MTR-SCOPE-{i}'; a.create_unit(m); a.assemble(m,de,nde); a.ship(m); a.announce('BR-204',scope)
                    slots=scope if scope is not None else ['DE','NDE']
                    unsafe=any(lot=='BR-204' and slot in slots for slot,lot in [('DE',de),('NDE',nde)])
                    decision=a.snapshot()['decisions'][m][PID]['current']
                    self.assertEqual(decision['evidenceFinding'],'AFFECTED' if unsafe else 'EXCLUDED_WITH_EVIDENCE')
                finally:a.close()

    def test_scope_invalid_and_immutable(self):
        for scope in ([],['OTHER'],['DE','DE'],'DE',{},[None],['DE',123]):
            with self.subTest(scope=scope), self.assertRaises(ValidationFailure): self.app.announce('BR-204',scope)
        self.app.announce('BR-204',['DE'])
        with self.assertRaises(ValidationFailure):self.app.announce('BR-204',['NDE'])

    def test_obligation_survives_unrelated_observation_and_reopen(self):
        self.app.seed_demo(); before=self.app.snapshot()['notifications']
        self.app.observe('MTR-26005','BR-310')
        self.assertEqual(before,self.app.snapshot()['notifications'])
        self.app.close();self.app=Manufacturing(self.path)
        self.assertEqual(before,self.app.snapshot()['notifications'])

    def test_material_observation_revision_and_replay(self):
        self.app.seed_demo();m='MTR-26001';before=self.current(m)
        self.app.observe(m,'BR-310');after=self.current(m)
        self.assertNotEqual(before['decisionId'],after['decisionId'])
        self.assertEqual(after['supersedesDecisionId'],before['decisionId'])
        self.assertEqual(after['untrustedObservations'][0]['observed']['lot'],'BR-310')
        entries=[p for k,p in self.app.audit.verify() if k=='EVALUATION' and p['context']['motor']==m]
        for e in entries:self.assertEqual(self.app.audit.replay(e),e['decision'])
        again=self.current(m);self.assertEqual(after,again)

    def test_irrelevant_capture_is_receipt_not_material_version(self):
        self.app.seed_demo();m='MTR-26005';before=self.current(m)
        self.app.event(m,'MATERIAL_ALLOCATED','MATERIAL',dict(rawMaterialLot='UNRELATED',supplierId='SYNTHETIC',supplierName='Synthetic'))
        after=self.current(m)
        self.assertEqual(before['decisionId'],after['decisionId'])
        self.assertNotEqual(before['watermark'],after['watermark'])
        self.assertTrue(after['precautionaryHold']); self.assertTrue(after['notificationObligation'])
        self.assertTrue(after['unchanged'])

    def test_authorized_resolution_is_explicit_and_audited_not_delivery(self):
        self.app.seed_demo();oid=self.app.snapshot()['notifications'][0]['obligationId']
        with self.assertRaises(PermissionError):self.app.audit.resolve(oid,principal='stranger',evidence_refs=['urn:evidence:1'],reason='reviewed')
        self.app.audit.resolve(oid,principal='test-authorized-owner',evidence_refs=['urn:pramaan:MTR-26005:HANDHELD:1'],reason='Owner resolution, not delivery',authorize=lambda p:p=='test-authorized-owner')
        self.assertEqual(self.app.snapshot()['notifications'],[])
        self.assertTrue(any(k=='OBLIGATION_RESOLVED' for k,_ in self.app.audit.verify()))
        self.assertEqual(self.current('MTR-26005')['operationalAction'],'RECALL_HOLD')

    def test_delete_all_history_detected_and_not_reset(self):
        self.app.seed_demo()
        self.app.db.execute('DROP TRIGGER app_audit_no_delete');self.app.db.execute('DELETE FROM app_audit');self.app.db.commit()
        with self.assertRaises(LedgerBlocked):self.app.snapshot()
        self.app.close()
        with self.assertRaises(LedgerBlocked):Manufacturing(self.path)
        # tearDown expects an open handle; restore a closed-safe disposable connection.
        self.app=Manufacturing(Path(self.tmp.name)/'unrelated.sqlite')

    def test_history_tamper_truncation_and_identity(self):
        self.app.seed_demo();m='MTR-26003';p=self.app.policy()
        first,_=self.app.audit.decide(m,p)
        changed=copy.deepcopy(p);changed['version']=2
        other,_=self.app.audit.decide(m,changed)
        self.assertNotEqual(first['decision']['decisionId'],other['decision']['decisionId'])
        self.app.db.execute('DROP TRIGGER app_audit_no_update'); self.app.db.execute("UPDATE app_audit SET payload='{}' WHERE seq=1");self.app.db.commit()
        with self.assertRaises(LedgerBlocked):self.app.audit.verify()

    def test_removing_journal_and_head_still_cannot_reset_history(self):
        self.app.seed_demo()
        self.app.db.execute('DROP TABLE app_audit');self.app.db.execute('DROP TABLE app_audit_head');self.app.db.commit();self.app.close()
        with self.assertRaises(LedgerBlocked):Manufacturing(self.path)
        self.app=Manufacturing(Path(self.tmp.name)/'unrelated.sqlite')

    def test_synthetic_clock_has_no_trust_attestation(self):
        self.app.create_unit('MTR-CLOCK');self.app.assemble('MTR-CLOCK','BR-310','BR-312')
        self.assertEqual(self.app.ledger._config('MTR-CLOCK')['coverage']['slotAttribution']['trustedTimeSources'],[])
        self.assertTrue(all(e['timeSource']=='SYNTHETIC_SIMULATED' for e in self.app.events('MTR-CLOCK')))

    def test_legacy_history_seal_detects_legacy_table_changes(self):
        # Even unrelated legacy inserts/deletes may not silently replace app history.
        self.app.create_unit('MTR-LEGACY')
        self.app.db.execute("INSERT INTO decision_runs(motor,policy_hash,payload,hash) VALUES('MTR-LEGACY','x','{}','x')");self.app.db.commit()
        with self.assertRaises(LedgerBlocked):self.app.audit.verify()

    def test_rejected_motor_blocks_fleet_explicitly_not_stale_release(self):
        self.app.seed_demo()
        with self.assertRaises(ValidationFailure):self.app.ledger.capture('MTR-26003',b'{}',producer_source='invalid',expected_sha256='wrong')
        with self.assertRaises(LedgerBlocked):self.app.snapshot()

    def test_pinned_provenance_no_git_dependency(self):
        self.assertTrue(verify(ROOT)['integrationTreeUnmodified'])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'application').mkdir()
            pin=json.loads((ROOT/'application/source-provenance.json').read_text(encoding='utf-8'))
            pin['roots']=['source'];pin['files']={'source/test.py':'incorrect'}
            (root/'application/source-provenance.json').write_text(json.dumps(pin));(root/'source').mkdir();(root/'source/test.py').write_text('changed')
            with self.assertRaises(AssertionError):verify(root)

    def test_legacy_bundle_replays_without_rewriting_rows_or_reinterpreting_scope(self):
        from integration_tests.scenarios import Scenario
        from pramaan_integration import Ledger
        from pramaan_integration.profile import digest
        path=Path(self.tmp.name)/'legacy.sqlite';scenario=Scenario('M-LEGACY')
        old=Ledger(path);scenario.provision(old);scenario.ingest(old,scenario.events)
        bundle=old.decide(scenario.motor,scenario.policy,[old.watermark(scenario.motor)])[0]
        before=[tuple(r) for r in old.db.execute('SELECT * FROM decision_runs')];old.close()
        app=Manufacturing(path)
        try:
            with app.db: app.db.execute('INSERT INTO recall_announcements VALUES(?,?,?)',(1,json.dumps(scenario.policy),digest(scenario.policy)))
            with self.assertRaises(LedgerBlocked):app.policy()
            replay=app.ledger.replay(scenario.motor,scenario.policy,bundle)
            self.assertEqual(replay['evidenceFinding'],bundle['decision']['evidenceFinding'])
            self.assertEqual([tuple(r) for r in app.db.execute('SELECT * FROM decision_runs')],before)
        finally:app.close()


class ScopeHttpTests(unittest.TestCase):
    setUp=helpers.HttpTests.setUp
    tearDown=helpers.HttpTests.tearDown
    request=helpers.HttpTests.request

    def test_notifications_endpoint_keeps_outstanding_obligation(self):
        before=self.request('/api/notifications')
        self.request('/api/units/MTR-26005/observe',{'lot':'BR-310'},self.token)
        self.assertEqual(before,self.request('/api/notifications'))

    def test_scope_contradictions_rejected_by_http(self):
        from urllib.error import HTTPError
        for body in ({'lot':'BR-204','affectedSlots':None},{'lot':'BR-204','scope':'NDE'},{'lot':'BR-204','affectedSlots':['NDE'],'slot':'DE'}):
            with self.subTest(body=body),self.assertRaises(HTTPError) as c:self.request('/api/recalls',body,self.token)
            self.assertEqual(c.exception.code,400)


if __name__=='__main__':unittest.main()
