import json
from pathlib import Path
import tempfile
import threading
import unittest
from application.service import Manufacturing, ShipmentRefused
from application.anchors import TrustedAnchor
from application.server import make_server
from review2.demo import prepare, stale, verify, AFFECTED, UNRESOLVED

class Review2Demo(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.d=Path(self.tmp.name)/'demo';self.result=prepare(self.d)
    def tearDown(self):self.tmp.cleanup()
    def test_import_repeat_and_native_lifecycle_share_one_ledger(self):
        self.assertEqual(self.result['imported']['ledgerEventsPlanned'],45)
        self.assertEqual(self.result['repeated']['ledgerEventsPlanned'],0)
        self.assertEqual(self.result['eventCount'],47)
        app=Manufacturing(self.d/'ledger.sqlite')
        try:
            events=app.events(AFFECTED)
            self.assertTrue(any(any(x.startswith('pramaan-import:') for x in e['evidenceRefs']) for e in events))
            self.assertEqual(sum(e['eventType']=='MACHINING_RECORDED' for e in events),1)
            self.assertEqual(sum(e['eventType']=='QUALITY_INSPECTION_RECORDED' for e in events),1)
        finally:app.close()
    def test_actual_evaluator_holds_affected_and_unresolved_despite_pass(self):
        self.assertEqual(self.result['recordedEvaluation'][AFFECTED],dict(finding='AFFECTED',action='RECALL_HOLD'))
        self.assertEqual(self.result['recordedEvaluation'][UNRESOLVED],dict(finding='UNRESOLVED',action='RECALL_HOLD'))
        app=Manufacturing(self.d/'ledger.sqlite')
        try:
            snap=app.snapshot(trusted_anchor=TrustedAnchor(self.d/'demo-reference.json',None))
            self.assertEqual(snap['checkpoint']['state'],'ANCHORED_CURRENT')
            for motor in (AFFECTED,UNRESOLVED):self.assertFalse(snap['eligibility'][motor]['currentReleaseEligible'])
        finally:app.close()
    def test_pass_is_a_claim_from_a_nontrusted_lifecycle_source(self):
        app=Manufacturing(self.d/'ledger.sqlite')
        try:
            q=next(e for e in app.events(AFFECTED) if e['eventType']=='QUALITY_INSPECTION_RECORDED')
            self.assertEqual(q['payload']['result'],'PASS')
            self.assertNotIn(q['sourceId'],app.ledger._config(AFFECTED)['coverage']['trustedVerifierSources'])
            self.assertNotIn('verified',q['payload']);self.assertNotIn('releaseEligible',q['payload'])
            self.assertEqual(q['payload']['subjectEventIds'],[self.result['machiningEventId']])
        finally:app.close()
    def test_reproducible_source_plan_and_evaluation_in_a_fresh_directory(self):
        second=prepare(Path(self.tmp.name)/'second')
        for key in ('imported','repeated','recordedEvaluation','eventCount'):self.assertEqual(self.result[key],second[key])
    def test_existing_evidence_is_never_reset(self):
        before=(self.d/'demo-reference.json').read_bytes()
        with self.assertRaises(ValueError):prepare(self.d)
        self.assertEqual((self.d/'demo-reference.json').read_bytes(),before)
    def test_stale_anchor_withholds_all_eligibility_and_refuses_shipping(self):
        before=(self.d/'demo-reference.json').read_bytes();result=stale(self.d)
        self.assertEqual(result['checkpoint']['state'],'ANCHORED_PREFIX_ONLY')
        self.assertEqual((self.d/'demo-reference.json').read_bytes(),before)
        app=Manufacturing(self.d/'ledger.sqlite')
        try:
            motor='MTR-R2-UNSHIPPED'
            app.create_unit(motor);app.assemble(motor,'BR-310','BR-312')
            with self.assertRaises(ShipmentRefused):app.ship(motor,trusted_anchor=TrustedAnchor(self.d/'demo-reference.json',None))
            self.assertFalse(any(e['eventType']=='MOTOR_SHIPPED' for e in app.events(motor)))
        finally:app.close()
    def test_real_http_current_then_stale_uses_same_ledger_and_reference(self):
        srv=make_server(self.d/'ledger.sqlite',0,trusted_anchor=self.d/'demo-reference.json')
        thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
        try:
            base=f'http://127.0.0.1:{srv.server_port}'
            current=verify(base);self.assertEqual(current['motors'][AFFECTED]['finding'],'AFFECTED')
            evidence=current['traceEvidence']
            self.assertTrue(evidence['materialEventId']);self.assertTrue(evidence['manufactureEventId'])
            self.assertTrue(evidence['installEventId']);self.assertTrue(evidence['shipmentEventIds'])
            self.assertIn('not the conservative recall candidate set',evidence['statement'])
            stale(self.d)
            historical=verify(base,'ANCHORED_PREFIX_ONLY');self.assertEqual(historical['currentDecisions'],'WITHHELD')
            self.assertNotIn('traceEvidence',historical)
        finally:srv.shutdown();srv.server_close();thread.join(5)
    def test_imported_quality_and_scada_are_not_promoted_to_trusted_ledger_events(self):
        app=Manufacturing(self.d/'ledger.sqlite')
        try:
            rows=app.db.execute('SELECT native FROM events').fetchall();events=[json.loads(r[0]) for r in rows]
            self.assertEqual(sum(e['eventType']=='QUALITY_INSPECTION_RECORDED' for e in events),1)
            self.assertFalse(any(e['eventType']=='PROCESS_SIGNAL' for e in events))
            self.assertGreater(self.result['imported']['acceptedStagedOnly'],0)
        finally:app.close()

if __name__=='__main__':unittest.main()
