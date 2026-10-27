"""Review 2: one synthetic ledger, explicit demo reference, no custody/clearance claims."""
import argparse
import json
from pathlib import Path
from urllib.parse import quote
from urllib.error import HTTPError
from urllib.request import urlopen

from application.service import Manufacturing
from application.anchors import TrustedAnchor, export_anchor, publish_candidate
from application.server import make_server
from application.dataintegration.demo import BATCH1
from application.dataintegration.importer import run
from application.dataintegration.planner import Options
from application.dataintegration.report import write_reports

AFFECTED = "MTR-27002"
UNRESOLVED = "MTR-27003"
FORMAT = "SYNTHETIC_REVIEW2_SINGLE_LEDGER"


def paths(directory):
    d=Path(directory).resolve()
    return d,d/"ledger.sqlite",d/"staging.sqlite",d/"demo-reference.json"


def prepare(directory):
    d,db,staging,reference=paths(directory)
    if d.exists() and any(d.iterdir()):
        raise ValueError("Choose a new empty directory; existing evidence is never reset or overwritten")
    d.mkdir(parents=True,exist_ok=True)
    app=Manufacturing(db)
    try:app.create_unit(AFFECTED,lifecycle=True)
    finally:app.close()
    opts=Options(create_units=True,historical_shipments=True)  # explicitly labelled imported SHIPMENT HISTORY, not operational shipping
    preview,_,_=run(BATCH1,ledger=db,options=opts)
    report,_,_=run(BATCH1,ledger=db,staging=staging,options=opts,commit=True)
    repeat,_,_=run(BATCH1,ledger=db,staging=staging,options=opts,commit=True)
    assert repeat.summary['ledgerEventsPlanned']==0
    write_reports(preview,d/"reports/preview")
    write_reports(report,d/"reports/import")
    write_reports(repeat,d/"reports/repeat")
    app=Manufacturing(db)
    try:
        # Native lifecycle claims are deliberately separate from imported QUALITY/SCADA, which remain staged-only.
        machine=app.machine(AFFECTED,"SHAFT","SHAFT-27002","TURNING","LATHE-R2","R10","DWG-SHAFT-R2")
        inspection=app.inspect_quality(AFFECTED,"DIMENSIONAL",[machine['eventId']],"QP-R2","PASS",["DIMENSIONAL"])
        app.announce("BR-204",["DE"])
        snap=app.snapshot()
        outcomes={motor:dict(finding=next(iter(snap['decisions'][motor].values()))['current']['evidenceFinding'],
                              action=next(iter(snap['decisions'][motor].values()))['current']['operationalAction'])
                  for motor in (AFFECTED,UNRESOLVED)}
        assert outcomes[AFFECTED]['finding']=='AFFECTED'
        assert outcomes[UNRESOLVED]['finding']=='UNRESOLVED'
        assert all(v['action']=='RECALL_HOLD' for v in outcomes.values())
        # Export is a candidate only. The separate serve command requires an explicit demo-only reference acknowledgement.
        publish_candidate(reference,export_anchor(app))
        result=dict(format=FORMAT,notice="Synthetic claims; local self-custodied reference is NOT independently protected custody or release authorization",
                    database=str(db),staging=str(staging),reference=str(reference),
                    preview=preview.summary,imported=report.summary,repeated=repeat.summary,
                    policy=snap['policies'][0],recordedEvaluation=outcomes,
                    machiningEventId=machine['eventId'],inspectionEventId=inspection['eventId'],
                    eventCount=app.db.execute('SELECT count(*) FROM events').fetchone()[0])
        (d/'manifest.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        return result
    finally:app.close()


def stale(directory):
    d,db,_,reference=paths(directory)
    manifest=json.loads((d/'manifest.json').read_text(encoding='utf-8'))
    if manifest['format']!=FORMAT:raise ValueError('Not a Review 2 synthetic workspace')
    app=Manufacturing(db)
    try:
        event=app.observe(AFFECTED,'BR-204')
        snap=app.snapshot(trusted_anchor=TrustedAnchor(reference,None))
        assert snap['checkpoint']['state']=='ANCHORED_PREFIX_ONLY'
        assert not any(x['currentReleaseEligible'] for x in snap['eligibility'].values())
        return dict(evidenceEventId=event['eventId'],checkpoint=snap['checkpoint'],
                    currentDecisions='WITHHELD',notice='Reference unchanged; no automatic checkpoint export, acceptance or activation')
    finally:app.close()


def verify(base,expected='ANCHORED_CURRENT'):
    def get(path):
        try:
            with urlopen(base.rstrip('/')+path,timeout=10) as r:return r.status,json.load(r)
        except HTTPError as e:return e.code,json.load(e)
    status,snap=get('/api/snapshot')
    assert status==200,(status,snap.get('error'))
    assert snap['checkpoint']['state']==expected,snap['checkpoint']
    status,g=get('/api/motors/'+AFFECTED+'/genealogy');assert status==200
    assert any(c['slot']=='DE' and c['lot']=='BR-204' for c in g['relationships'])
    if expected=='ANCHORED_CURRENT':
        # Demonstrate existing bidirectional history APIs, not a second recall algorithm.
        status,history=get('/api/motors/'+AFFECTED+'/lifecycle');assert status==200
        assert history['checkpoint']['state']=='ANCHORED_CURRENT'
        bearing=next(b for b in history['backward']['bearings'] if b['slot']=='DE' and b['lot']=='BR-204')
        assert bearing['materialEventId'] and bearing['manufactureEventId'] and bearing['rawMaterialLot']
        status,trace=get('/api/trace/rawMaterialLot/'+quote(bearing['rawMaterialLot'],safe=''));assert status==200
        assert trace['checkpoint']['state']=='ANCHORED_CURRENT'
        match=next(m for m in trace['motors'] if m['motorSerial']==AFFECTED)
        assert bearing['materialEventId'] in match['matchedEventIds']
        shipments=history['backward']['shipments']
        assert shipments and {s['eventId'] for s in shipments}=={s['eventId'] for s in match['shipments']}
        assert all(s['historicalImport'] for s in shipments)
        trace_evidence=dict(rawMaterialLot=bearing['rawMaterialLot'],materialEventId=bearing['materialEventId'],
                            manufactureEventId=bearing['manufactureEventId'],installEventId=bearing['installEventId'],
                            shipmentEventIds=sorted(s['eventId'] for s in shipments),
                            statement='Recorded associations and historical shipments only; not the conservative recall candidate set or shipment authorization')
        outcomes={}
        for motor,want in [(AFFECTED,'AFFECTED'),(UNRESOLVED,'UNRESOLVED')]:
            status,b=get('/api/motors/'+motor+'/decisions');assert status==200
            decision=next(v['current'] for k,v in b.items() if k not in ('checkpoint','eligibility'))
            assert decision['evidenceFinding']==want
            assert decision['operationalAction']=='RECALL_HOLD'
            assert b['eligibility']['currentReleaseEligible'] is False
            outcomes[motor]=dict(finding=want,action=decision['operationalAction'],decisionId=decision['decisionId'],reasons=decision['reasonCodes'])
        return dict(checkpoint=snap['checkpoint'],motors=outcomes,traceEvidence=trace_evidence,notice='Configured synthetic reference only, not independent custody')
    assert not any(x['currentReleaseEligible'] for x in snap['eligibility'].values())
    status,b=get('/api/motors/'+AFFECTED+'/decisions');assert status==409 and b['error']=='CHECKPOINT_REQUIRED'
    return dict(checkpoint=snap['checkpoint'],currentDecisions='WITHHELD',genealogy='HISTORICAL_FACTS_ONLY')


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for name in ('prepare','serve','stale'):
        s=sub.add_parser(name);s.add_argument('--workdir',type=Path,required=True)
        if name=='serve':s.add_argument('--port',type=int,default=4400);s.add_argument('--demo-reference-only',action='store_true',required=True)
    s=sub.add_parser('verify');s.add_argument('--url',default='http://127.0.0.1:4400');s.add_argument('--expected',choices=['ANCHORED_CURRENT','ANCHORED_PREFIX_ONLY'],default='ANCHORED_CURRENT')
    a=p.parse_args()
    if a.command=='prepare':print(json.dumps(prepare(a.workdir),indent=2))
    elif a.command=='stale':print(json.dumps(stale(a.workdir),indent=2))
    elif a.command=='verify':print(json.dumps(verify(a.url,a.expected),indent=2))
    else:
        d,db,_,ref=paths(a.workdir)
        if json.loads((d/'manifest.json').read_text())['format']!=FORMAT:raise ValueError('Not Review 2')
        srv=make_server(db,a.port,trusted_anchor=ref)
        print(f'Review 2 synthetic local demo: http://127.0.0.1:{srv.server_port}; reference is NOT independent custody',flush=True)
        try:srv.serve_forever()
        finally:srv.server_close()

if __name__=='__main__':main()
