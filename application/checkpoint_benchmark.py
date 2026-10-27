"""Disposable R18 synthetic workload; never a production dataset or oracle."""
import json
from pathlib import Path
import tempfile
import time
import statistics
import threading
import argparse
from urllib.request import urlopen
from urllib.error import HTTPError
from .service import Manufacturing
from .anchors import export_anchor,publish_candidate
from .server import make_server


def run(database=None):
    with tempfile.TemporaryDirectory() as temp:
        path=Path(database) if database else Path(temp)/'synthetic.sqlite'
        app=Manufacturing(path)
        if app.policy() is None:app.announce('BR-204',['DE'])
        existing={}
        for kind,p in app.audit.verify():
            if kind=='EVALUATION':existing.setdefault(p['context']['motor'],[]).append(p)
        for n in range(100):
            motor=f'MTR-BENCH-{n:03}'
            if not app.db.execute('SELECT 1 FROM motors WHERE serial=?',(motor,)).fetchone():
                app.create_unit(motor);app.assemble(motor,'BR-310','BR-312')
            issued=existing.get(motor,[])
            target=9 if n==99 else 10
            assert len(issued)<=target
            for revision in range(len(issued),target):
                if revision and app.ledger.watermark(motor)==issued[-1]['manifest']['watermark']:
                    app.observe(motor,'BR-310')
                entry,_=app.audit.decide(motor,app.policy())
                issued.append(entry)
        count=app.db.execute('SELECT count(*) FROM app_audit').fetchone()[0]
        assert count==1000,count
        candidate=export_anchor(app)
        anchor=Path(temp)/'test-owner-checkpoint.json';publish_candidate(anchor,candidate)
        app.close()
        activation_started=time.perf_counter()
        server=make_server(path,0,trusted_anchor=anchor)
        activation_ms=(time.perf_counter()-activation_started)*1000
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        samples=[]
        try:
            for n in range(12):
                started=time.perf_counter()
                try:
                    with urlopen(f'http://127.0.0.1:{server.server_port}/api/snapshot',timeout=4) as response:
                        status=response.status;body=json.load(response)
                except HTTPError as exc:
                    status=exc.code;body=json.load(exc)
                elapsed=(time.perf_counter()-started)*1000
                assert status in (200,503),(status,body)
                if status==503:assert body.get('error')=='VERIFYING' and body.get('decisionsUnavailable') is True
                samples.append(dict(request=n,status=status,milliseconds=round(elapsed,3)))
        finally:server.shutdown();server.server_close();thread.join()
        successes=[s['milliseconds'] for s in samples if s['status']==200]
        p95=statistics.quantiles(successes,n=20,method='inclusive')[18] if len(successes)>1 else successes[0] if successes else None
        return dict(motors=100,journalEntries=count,activationVerificationMs=round(activation_ms,3),samples=samples,successfulP95Ms=p95,
                    acceptance='SAFE_503_FALLBACK_ONLY' if p95 is None else 'PASS' if p95<1500 else 'FAIL',
                    caveat='503 is VERIFYING with eligibility withheld; absence of successful snapshots is an availability limitation.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,help='Optional disposable synthetic benchmark archive to retain/resume')
    args=parser.parse_args()
    print(json.dumps(run(args.database),indent=2))
