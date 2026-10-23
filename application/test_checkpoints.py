"""Option A adversarial tests. All evidence and destructive edits are synthetic."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from contextlib import contextmanager
import os
from urllib.request import urlopen
from urllib.error import HTTPError
import unittest
from unittest.mock import patch

from .service import Manufacturing
from .anchors import (export_anchor,export_v1,verify_anchor,TrustedAnchor,
                      publish_candidate)
from .audit import IntegrityFailure,Verifying
from pramaan_integration.profile import digest


class StrictCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'ledger.sqlite'
        self.app=Manufacturing(self.path)
        self.motor='MTR-STRICT-001'
        self.app.create_unit(self.motor);self.app.assemble(self.motor,'BR-310','BR-312')
        self.app.announce('BR-204',['DE']);self.app.snapshot()
        self.anchor=export_anchor(self.app)
        self.file=Path(self.temp.name)/'owner.json'
        publish_candidate(self.file,self.anchor)

    def tearDown(self):
        self.app.close();self.temp.cleanup()

    def code(self,call,code):
        with self.assertRaises(IntegrityFailure) as cm:call()
        self.assertEqual(cm.exception.code,code)
        self.assertEqual(str(cm.exception),code)

    def backup(self):
        db=sqlite3.connect(':memory:');self.app.db.backup(db);return db

    def test_R1_in_process_rollback(self):
        old=self.backup();trusted=TrustedAnchor(self.file)
        self.app.snapshot(trusted_anchor=trusted)
        self.app.observe(self.motor,'BR-204');self.app.snapshot(trusted_anchor=trusted)
        old.backup(self.app.db);old.close()
        self.code(lambda:self.app.snapshot(trusted_anchor=trusted),'ROLLBACK_DETECTED')

    def test_R2_restart_latest_checkpoint_rejects_older_database(self):
        old=self.backup()
        self.app.observe(self.motor,'BR-204');self.app.snapshot()
        latest=export_anchor(self.app)
        old.backup(self.app.db);old.close()
        self.code(lambda:verify_anchor(self.app,latest),'PREFIX_MISMATCH')

    def test_R4_exact_checkpoint_restart_residual_is_undetectable(self):
        old=self.backup()
        self.app.observe(self.motor,'BR-204');self.app.snapshot()
        old.backup(self.app.db);old.close()
        self.app.close();self.app=Manufacturing(self.path)
        self.assertEqual(self.app.snapshot(trusted_anchor=TrustedAnchor(self.file))['checkpoint']['state'],'ANCHORED_CURRENT')

    def test_R3_intermediate_rollback_after_restart_is_prefix_only(self):
        self.app.observe(self.motor,'BR-310');self.app.snapshot()
        intermediate=self.backup()
        trusted=TrustedAnchor(self.file)
        self.app.observe(self.motor,'BR-204');self.app.snapshot(trusted_anchor=trusted)
        intermediate.backup(self.app.db);intermediate.close()
        self.code(lambda:self.app.snapshot(trusted_anchor=trusted),'ROLLBACK_DETECTED')
        self.app.close();self.app=Manufacturing(self.path)
        snap=self.app.snapshot(trusted_anchor=TrustedAnchor(self.file))
        self.assertEqual(snap['checkpoint']['state'],'ANCHORED_PREFIX_ONLY')
        self.assertFalse(snap['eligibility'][self.motor]['currentReleaseEligible'])

    def test_R5_capture_withholds_globally_holds_remain(self):
        self.app.observe(self.motor,'BR-204')
        snap=self.app.snapshot(trusted_anchor=TrustedAnchor(self.file))
        self.assertEqual(snap['checkpoint']['state'],'ANCHORED_PREFIX_ONLY')
        self.assertTrue(snap['checkpoint']['checkpointRequired'])
        self.assertFalse(snap['eligibility'][self.motor]['currentReleaseEligible'])
        self.assertEqual(next(iter(snap['decisions'][self.motor].values()))['current']['operationalAction'],'RECALL_HOLD')

    def forged(self,field):
        trusted=TrustedAnchor(self.file);trusted.verify(self.app)
        self.app.observe(self.motor,'BR-204');self.app.snapshot()
        entry=copy.deepcopy([p for k,p in self.app.audit.verify() if k=='EVALUATION'][-1])
        if field=='raw':entry['raw']['operationalAction']='RELEASE_ELIGIBLE';entry['raw']['reasonCodes']=[]
        else:entry['decision']['version']=42;entry['decision']['reasonCodes']=[]
        self.app.db.execute('DROP TRIGGER app_audit_no_update')
        self.app.db.execute('UPDATE app_audit SET payload=? WHERE seq=(SELECT MAX(seq) FROM app_audit)',(json.dumps(entry),))
        previous='GENESIS'
        for row in self.app.db.execute('SELECT * FROM app_audit ORDER BY seq').fetchall():
            hashed=digest(dict(seq=row['seq'],kind=row['kind'],payload=json.loads(row['payload']),previous=previous))
            self.app.db.execute('UPDATE app_audit SET previous=?,hash=? WHERE seq=?',(previous,hashed,row['seq']))
            previous=hashed
        self.app.db.execute('UPDATE app_audit_head SET hash=? WHERE id=1',(previous,));self.app.db.commit()
        self.code(lambda:trusted.verify(self.app),'EXTENSION_INVALID')

    def test_R6_forged_evaluation_rehashed(self):self.forged('raw')
    def test_R7_forged_derived_fields(self):self.forged('derived')

    def test_R8_orphan_obligation(self):
        self.app.audit.append('OBLIGATION_CREATED',dict(obligationId='forged',unitId=self.motor));self.app.db.commit()
        self.code(lambda:verify_anchor(self.app,self.anchor),'EXTENSION_INVALID')

    def test_unknown_journal_kind_rejected(self):
        self.app.audit.append('UNRECOGNIZED_EXTENSION',dict(claim='not authority'));self.app.db.commit()
        self.code(lambda:verify_anchor(self.app,self.anchor),'EXTENSION_INVALID')

    def test_shared_structural_byte_cache_does_not_trust_forged_publication(self):
        cache=dict(key=self.app.audit.journal_bytes_key())
        self.app.close();self.app=Manufacturing(self.path,journal_cache=cache)
        self.forged('derived')

    def test_R9_resolution_forbidden(self):
        self.app.audit.append('OBLIGATION_RESOLVED',dict(obligationId='forged'));self.app.db.commit()
        self.code(lambda:verify_anchor(self.app,self.anchor),'RESOLUTION_FORBIDDEN')

    def test_R10_unevaluated_capture(self):
        self.app.observe(self.motor,'BR-204')
        self.assertEqual(verify_anchor(self.app,self.anchor)['state'],'ANCHORED_PREFIX_ONLY')

    def test_R11_v1_never_current(self):
        self.assertEqual(verify_anchor(self.app,export_v1(self.app))['state'],'ANCHORED_PREFIX_ONLY')

    def test_R13_atomic_no_overwrite_and_interrupted_write(self):
        target=Path(self.temp.name)/'candidate.json'
        original=os.fdopen
        @contextmanager
        def partial(fd,mode):
            with original(fd,mode) as file:
                class Writer:
                    def write(self,data):
                        file.write(data[:len(data)//2]);file.flush()
                        raise OSError('secret host path SQL payload')
                yield Writer()
        with patch('application.anchors.os.fdopen',side_effect=partial):
            with self.assertRaises(OSError):publish_candidate(target,self.anchor)
        self.assertFalse(target.exists())
        self.assertEqual(list(target.parent.glob('.checkpoint-*')),[])
        with patch('application.anchors.os.fsync',side_effect=OSError('secret host path SQL payload')):
            with self.assertRaises(OSError):publish_candidate(target,self.anchor)
        self.assertFalse(target.exists())
        self.assertEqual(list(target.parent.glob('.checkpoint-*')),[])
        publish_candidate(target,self.anchor)
        before=target.read_bytes()
        with self.assertRaises(FileExistsError):publish_candidate(target,dict(fake=True))
        self.assertEqual(target.read_bytes(),before)

    def test_R12_export_racing_independent_writer(self):
        started=threading.Event();errors=[]
        def writer():
            try:
                app=Manufacturing(self.path)
                try:
                    started.set();app.observe(self.motor,'BR-204')
                finally:app.close()
            except Exception as exc:errors.append(type(exc).__name__)
        thread=threading.Thread(target=writer);thread.start();started.wait(5)
        candidate=export_anchor(self.app)
        thread.join(10)
        self.assertFalse(thread.is_alive());self.assertFalse(errors)
        self.assertIn(verify_anchor(self.app,candidate)['state'],('ANCHORED_CURRENT','ANCHORED_PREFIX_ONLY'))

    def test_R14_candidate_has_no_trust_effect(self):
        snap=self.app.snapshot()
        self.assertEqual(snap['checkpoint']['state'],'UNANCHORED')
        self.assertFalse(snap['eligibility'][self.motor]['currentReleaseEligible'])

    def test_R15_successor_requires_explicit_previous_link(self):
        self.app.observe(self.motor,'BR-204');self.app.snapshot()
        successor=export_anchor(self.app,self.anchor)
        self.code(lambda:verify_anchor(self.app,successor),'PREFIX_MISMATCH')
        self.assertEqual(verify_anchor(self.app,successor,self.anchor)['state'],'ANCHORED_CURRENT')
        successor['body']['previousCheckpointHash']='forged';successor['checksum']=digest(successor['body'])
        self.code(lambda:verify_anchor(self.app,successor,self.anchor),'PREFIX_MISMATCH')

    def test_R16_legacy_without_manifest_never_current(self):
        entry=copy.deepcopy(next(p for k,p in self.app.audit.verify() if k=='EVALUATION'));entry.pop('manifest')
        self.app.audit.append('EVALUATION',entry);self.app.db.commit()
        proof=self.app.audit.verify_publications()
        self.assertEqual(proof['status'],'HISTORICAL_UNVERIFIABLE')
        self.assertEqual(verify_anchor(self.app,export_anchor(self.app))['state'],'ANCHORED_PREFIX_ONLY')

    def test_R17_fixed_error_codes_only(self):
        self.file.write_text('secret host path SQL payload')
        self.code(lambda:TrustedAnchor(self.file).verify(self.app),'PREFIX_MISMATCH')

    def test_R17_http_integrity_availability_and_unexpected_errors_sanitized(self):
        from .server import make_server
        server=make_server(self.path,0,trusted_anchor=self.file)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}/api/snapshot'
        try:
            for target,error,expected,code in [
                ('application.audit.Audit.verify_publications',IntegrityFailure(),409,'EXTENSION_INVALID'),
                ('application.audit.Audit.verify_publications',Verifying(),503,'VERIFYING'),
                ('application.server.Manufacturing',sqlite3.DatabaseError('secret host path SQL payload'),500,None),
            ]:
                with patch(target,side_effect=error):
                    with self.assertRaises(HTTPError) as cm:urlopen(url)
                    body=cm.exception.read().decode()
                    self.assertEqual(cm.exception.code,expected)
                    if code:self.assertEqual(json.loads(body)['error'],code)
                    for secret in ('secret','SQL','payload',str(self.temp.name),'Traceback'):
                        self.assertNotIn(secret,body)
        finally:server.shutdown();server.server_close();thread.join()

    def test_R19_policy_after_empty_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            app=Manufacturing(Path(temp)/'empty.sqlite')
            try:
                before=export_anchor(app)
                app.announce('BR-204',['DE'])
                self.assertEqual(verify_anchor(app,before)['state'],'ANCHORED_PREFIX_ONLY')
            finally:app.close()

    def test_current_requires_no_obligation_and_verified_replay(self):
        snap=self.app.snapshot(trusted_anchor=TrustedAnchor(self.file))
        self.assertTrue(snap['eligibility'][self.motor]['currentReleaseEligible'])
        self.assertEqual(snap['checkpoint']['h2'],'VERIFIED')
        self.app.observe(self.motor,'BR-204');self.app.snapshot()
        newer=export_anchor(self.app,self.anchor)
        result=verify_anchor(self.app,newer,self.anchor)
        self.assertEqual(result['state'],'ANCHORED_CURRENT')
        self.assertEqual(len(self.app.audit.outstanding()),1)

    def test_owner_clarification_historical_resolution_preserved_export_blocked(self):
        self.app.audit.append('OBLIGATION_RESOLVED',dict(obligationId='historical-claim'))
        self.app.db.commit()
        before=[tuple(r) for r in self.app.db.execute('SELECT * FROM app_audit ORDER BY seq')]
        self.code(lambda:export_anchor(self.app),'RESOLUTION_FORBIDDEN')
        self.assertEqual([tuple(r) for r in self.app.db.execute('SELECT * FROM app_audit ORDER BY seq')],before)


if __name__=='__main__':unittest.main()
