"""Independent, disposable dependency probes; actual pinned application/evaluator."""
import copy,json,sys,tempfile,threading
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root))
from application.service import Manufacturing
from application.anchors import export_anchor,verify_anchor
from application.server import make_server
from application.audit import derive_publication,PROFILE
from pramaan_integration import engine_bridge
from pramaan_integration.profile import digest

def setup(path):
 app=Manufacturing(path)
 for m in ('MTR-DEPENDENCY-001','MTR-DEPENDENCY-002'):
  app.create_unit(m);app.assemble(m,'BR-310','BR-312')
 app.announce('BR-204',['DE']);app.snapshot();return app

def request(server,path):
 try:
  with urlopen(f'http://127.0.0.1:{server.server_port}'+path,timeout=4) as r:return r.status,json.load(r)
 except HTTPError as e:return e.code,json.load(e)

results={}
with tempfile.TemporaryDirectory(prefix='pramaan-independent-backend-') as temp:
 p=Path(temp);app=setup(p/'a.sqlite');anchor=p/'owner-test.json';anchor.write_text(json.dumps(export_anchor(app)))
 server=make_server(p/'a.sqlite',0,trusted_anchor=anchor);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  app.observe('MTR-DEPENDENCY-001','BR-204')
  before=app.db.execute('SELECT count(*) FROM app_audit').fetchone()[0]
  code,snap=request(server,'/api/snapshot')
  after=app.db.execute('SELECT count(*) FROM app_audit').fetchone()[0]
  results['D6']=dict(status=code,journalBefore=before,journalAfter=after)
  results['D2']={}
  for endpoint in ('/api/motors/MTR-DEPENDENCY-002/decisions','/api/lots/BR-310/investigation'):
   status,body=request(server,endpoint);serialized=json.dumps(body)
   results['D2'][endpoint]=dict(status=status,rawRelease='RELEASE_ELIGIBLE' in serialized,
    checkpoint='checkpoint' in serialized,currentEligibility='currentReleaseEligible' in serialized,
    wholeSnapshotState=snap.get('checkpoint',{}).get('state'))
  entry=copy.deepcopy([v for k,v in app.audit.verify() if k=='EVALUATION' and v['context']['motor']=='MTR-DEPENDENCY-001'][-1]);entry.pop('manifest')
  app.audit.append('EVALUATION',entry);app.db.commit();app.observe('MTR-DEPENDENCY-001','BR-310')
  status,body=request(server,'/api/snapshot');results['D3']=dict(status=status,error=body.get('error'))
 finally:server.shutdown();server.server_close();thread.join();app.close()
 app=setup(p/'b.sqlite')
 try:
  first=export_anchor(app);app.observe('MTR-DEPENDENCY-001','BR-310');app.snapshot()
  second=export_anchor(app,first);app.observe('MTR-DEPENDENCY-001','BR-310');app.snapshot()
  try:export_anchor(app,second);results['D4']=dict(thirdExport='SUCCEEDED')
  except Exception as e:results['D4']=dict(thirdExport='BLOCKED',code=getattr(e,'code',type(e).__name__))
  skipped=export_anchor(app,first)
  results['D8']=dict(skippedIntermediate=verify_anchor(app,skipped,first)['state'])
  policy=copy.deepcopy(app.policy());policy['policyId']='UNANNOUNCED-AUDIT-POLICY';policy['affectedLots']=['BR-999']
  motor='MTR-DEPENDENCY-002';wm=app.ledger.watermark(motor);case,manifest=app.ledger.snapshot(motor,wm)
  raw=engine_bridge.pramaan_recall.evaluate(case,copy.deepcopy(policy),app.ledger._config(motor)['coverage'],wm,engine_bridge.Config.v3())
  archive=app.db.execute('SELECT archive_id FROM app_audit_head').fetchone()[0]
  entry,ob,_=derive_publication(case,manifest,policy,raw,[],app.audit.outstanding(),archive)
  if ob:app.audit.append('OBLIGATION_CREATED',ob)
  app.audit.append('EVALUATION',entry);app.db.commit()
  results['D5']=dict(unannouncedPolicy=app.audit.verify_publications()['status'])
 finally:app.close()
 app=setup(p/'c.sqlite');anchor=p/'owner-history.json';anchor.write_text(json.dumps(export_anchor(app)))
 server=make_server(p/'c.sqlite',0,trusted_anchor=anchor);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  app.audit.append('OBLIGATION_RESOLVED',dict(obligationId='historical-only-claim'));app.db.commit()
  status,body=request(server,'/api/snapshot');results['D9']=dict(status=status,error=body.get('error'))
 finally:server.shutdown();server.server_close();thread.join();app.close()
print(json.dumps(results,indent=2))
