"""C1-C3 synthetic regressions; destructive operations use disposable archives."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from .service import Manufacturing, LedgerBlocked
from .audit import IntegrityFailure
from .anchors import export_anchor, verify_anchor, TrustedAnchor
from pramaan_integration.profile import digest


class AnchorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'archive.sqlite'
        self.app=Manufacturing(self.path)
        self.motor='MTR-ANCHOR-TEST'
        self.app.create_unit(self.motor); self.app.assemble(self.motor,'BR-310','BR-312')
        self.app.ship(self.motor); self.app.announce('BR-204',['DE']); self.app.snapshot()
        self.anchor=export_anchor(self.app)

    def tearDown(self):
        self.app.close(); self.temp.cleanup()

    def test_clean_prefix_extension_and_restart(self):
        first=verify_anchor(self.app,self.anchor)
        self.app.observe(self.motor,'BR-204'); snap=self.app.snapshot()
        self.assertEqual(snap['decisions'][self.motor]['RC-026-014/P1']['current']['operationalAction'],'RECALL_HOLD')
        self.assertEqual(len(snap['notifications']),1)
        extension=verify_anchor(self.app,self.anchor)
        self.assertGreater(extension['sequence'],first['sequence'])
        self.app.close(); self.app=Manufacturing(self.path)
        self.assertEqual(verify_anchor(self.app,self.anchor),extension)

    def test_cli_canonical_export_verify_and_no_overwrite(self):
        import subprocess
        import sys
        import rfc8785
        target=Path(self.temp.name)/'export.json'
        command=[sys.executable,'-m','application.anchors']
        args=['--database',str(self.path),'--anchor',str(target)]
        p=subprocess.run(command+['export']+args,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(target.read_bytes(),rfc8785.dumps(json.loads(target.read_bytes())))
        p=subprocess.run(command+['verify']+args,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertNotEqual(subprocess.run(command+['export']+args,capture_output=True).returncode,0)

    def test_old_valid_sqlite_backup_does_not_extend_latest_anchor(self):
        old=sqlite3.connect(str(Path(self.temp.name)/'older.sqlite'))
        self.app.db.backup(old)
        self.app.observe(self.motor,'BR-204'); self.app.snapshot(); latest=export_anchor(self.app)
        old.backup(self.app.db); old.close()
        with self.assertRaises(LedgerBlocked): verify_anchor(self.app,latest)

    def test_drop_journal_and_head_reset_schema_cannot_match_external_archive(self):
        self.app.db.executescript('DROP TABLE app_audit; DROP TABLE app_audit_head; PRAGMA user_version=0;')
        self.app.close(); self.app=Manufacturing(self.path)
        with self.assertRaises(LedgerBlocked): verify_anchor(self.app,self.anchor)

    def test_truncated_journal_fails_structural_checks(self):
        self.app.db.execute('DROP TRIGGER app_audit_no_delete')
        self.app.db.execute('DELETE FROM app_audit WHERE seq=(SELECT MAX(seq) FROM app_audit)'); self.app.db.commit()
        with self.assertRaises(LedgerBlocked): verify_anchor(self.app,self.anchor)

    def test_rewritten_journal_and_head_fail_anchored_prefix_even_if_locally_valid(self):
        self.app.db.execute('DROP TRIGGER app_audit_no_update')
        row=self.app.db.execute('SELECT * FROM app_audit ORDER BY seq DESC LIMIT 1').fetchone()
        payload=json.loads(row['payload']); payload['auditForgery']='changed'
        h=digest(dict(seq=row['seq'],kind=row['kind'],payload=payload,previous=row['previous']))
        self.app.db.execute('UPDATE app_audit SET payload=?,hash=? WHERE seq=?',(json.dumps(payload),h,row['seq']))
        self.app.db.execute('UPDATE app_audit_head SET hash=?',(h,)); self.app.db.commit()
        with self.assertRaises(LedgerBlocked): verify_anchor(self.app,self.anchor)

    def test_forged_resolution_extension_rejected(self):
        self.app.observe(self.motor,'BR-204'); self.app.snapshot(); anchor=export_anchor(self.app)
        oid=self.app.audit.outstanding()[0]['obligationId']
        self.app.audit.append('OBLIGATION_RESOLVED',dict(obligationId=oid,principal='self-declared'))
        self.app.db.commit()
        with self.assertRaises(LedgerBlocked): verify_anchor(self.app,anchor)

    def test_wrong_archive_tampered_checksum_and_recomputed_policy(self):
        for field in ('archiveId','policyDigest','headHash'):
            a=copy.deepcopy(self.anchor); a['body'][field]='forged'; a['checksum']=digest(a['body'])
            with self.subTest(field=field),self.assertRaises(LedgerBlocked): verify_anchor(self.app,a)
        a=copy.deepcopy(self.anchor); a['checksum']='bad'
        with self.assertRaises(LedgerBlocked):verify_anchor(self.app,a)

    def test_owner_file_missing_replaced_and_operational_enforcement(self):
        p=Path(self.temp.name)/'owner.json'
        with self.assertRaises(FileNotFoundError): TrustedAnchor(p)
        self.assertEqual(self.app.snapshot()['freshness']['status'],'HISTORICAL_UNANCHORED')
        p.write_text(json.dumps(self.anchor)); trusted=TrustedAnchor(p)
        self.assertEqual(self.app.snapshot(trusted_anchor=trusted)['freshness']['status'],'VERIFIED_ANCHORED_SYNTHETIC')
        p.write_text('{}')
        with self.assertRaises(LedgerBlocked):self.app.snapshot(trusted_anchor=trusted)

    def test_public_resolution_callback_cannot_authorize_and_obligation_persists(self):
        self.app.observe(self.motor,'BR-204'); self.app.snapshot()
        oid=self.app.audit.outstanding()[0]['obligationId']
        for principal in ('stranger','ROLE:QUALITY','owner'):
            with self.assertRaises(PermissionError):self.app.audit.resolve(oid,principal=principal,authorize=lambda p:True,evidence_refs=[],reason='claimed')
        self.app.observe(self.motor,'BR-310'); before=self.app.snapshot()['notifications']
        self.app.close(); self.app=Manufacturing(self.path)
        self.assertEqual(self.app.snapshot()['notifications'],before)

    def test_historical_resolution_entries_are_not_rewritten(self):
        # MIGRATED (owner decision D9, narrowly scoped test-contract migration; production behavior unchanged). Original body is kept in
        # docs/UNIFIED_TEST_MIGRATIONS.md (M20) and git history. The original expected export_anchor() to succeed over a historical
        # OBLIGATION_RESOLVED row; the approved contract is that such rows stay historical-only and export is FORBIDDEN. No xfail/skip.
        self.app.observe(self.motor,'BR-204'); self.app.snapshot()
        records=self.app.audit.verify(); entry=next(p for k,p in records if k=='EVALUATION')
        oid=self.app.audit.outstanding()[0]['obligationId']
        rows=lambda:[tuple(r) for r in self.app.db.execute('SELECT * FROM app_audit ORDER BY seq')]
        before=rows()
        # Simulate an old, independently reviewed archive; never a callable resolution workflow.
        self.app.audit.append('OBLIGATION_RESOLVED',dict(obligationId=oid,principal='legacy-unauthenticated-claim'))
        self.app.db.commit()
        archived=rows()
        self.assertEqual(archived[:len(before)],before)                 # 1/6: earlier rows byte-for-byte unchanged
        historical=archived[len(before):]
        self.assertEqual([r[1] for r in historical],['OBLIGATION_RESOLVED'])
        # 2: checkpoint export is rejected (the OLD test asserted export succeeded)
        with self.assertRaises(IntegrityFailure) as e:export_anchor(self.app)
        self.assertEqual(e.exception.code,'RESOLUTION_FORBIDDEN')
        # 3: never an authenticated current resolution: the follow-up stays outstanding and no resolve path authorizes it
        self.assertEqual([o['obligationId'] for o in self.app.audit.outstanding()],[oid])
        for principal in ('legacy-unauthenticated-claim','owner'):
            with self.assertRaises(PermissionError):self.app.audit.resolve(oid,principal=principal,authorize=lambda p:True,evidence_refs=[],reason='claimed')
        # 4: no operational clearance can be minted: unanchored => every motor ineligible and the obligation is still reported;
        #    with a previously valid trusted checkpoint the snapshot fails closed instead of reaching CURRENT
        snap=self.app.snapshot()
        self.assertEqual(snap['checkpoint']['state'],'UNANCHORED')
        self.assertTrue(all(not p['currentReleaseEligible'] for p in snap['eligibility'].values()))
        self.assertEqual([n['unitId'] for n in snap['notifications']],[self.motor])
        trusted_file=Path(self.temp.name)/'trusted.json'; trusted_file.write_text(json.dumps(self.anchor))
        with self.assertRaises(IntegrityFailure) as e:self.app.snapshot(trusted_anchor=TrustedAnchor(trusted_file))
        self.assertEqual(e.exception.code,'RESOLUTION_FORBIDDEN')
        # historical decision replay stays available (inspection only)
        self.assertEqual(self.app.audit.replay(entry),entry['decision'])
        # 6: nothing was rewritten, deleted or rehabilitated by any of the above
        self.assertEqual(rows(),archived)


class HttpHardeningTests(unittest.TestCase):
    from .test_application import HttpTests
    setUp=HttpTests.setUp
    tearDown=HttpTests.tearDown
    request=HttpTests.request

    def test_no_http_resolution_endpoint(self):
        from urllib.error import HTTPError
        with self.assertRaises(HTTPError) as e:
            self.request('/api/notifications/arbitrary/resolve',{'principal':'owner'},self.token)
        self.assertEqual(e.exception.code,404)

    def test_unanchored_http_only_serves_historical_envelope(self):
        import threading
        from urllib.error import HTTPError
        from .server import make_server
        server=make_server(Path(self.tmp.name)/'unanchored.sqlite',0,True)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        original=self.base; self.base=f'http://127.0.0.1:{server.server_port}'
        try:
            self.assertEqual(self.request('/api/snapshot')['freshness']['status'],'HISTORICAL_UNANCHORED')
            token=self.request('/api/session')['token']
            for path,body in (('/api/motors/MTR-26003/decisions',None),('/api/units',{'serial':'MTR-UNKNOWN'})):
                with self.assertRaises(HTTPError) as e:self.request(path,body,token)
                self.assertEqual(e.exception.code,409)
        finally:
            self.base=original;server.shutdown();thread.join();server.server_close()


if __name__=='__main__': unittest.main()
