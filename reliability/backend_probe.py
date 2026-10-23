"""Run the original idempotence test unchanged with observable test-only clocks."""
import argparse
import copy
import json
from pathlib import Path
import statistics
import sys
import time
import unittest
from contextlib import nullcontext
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from application.service import Manufacturing
from application.test_application import ApplicationTests
from pramaan_integration import Ledger


def differences(a,b,path=''):
    if type(a)!=type(b):return [path]
    if isinstance(a,dict):
        if set(a)!=set(b):return [path+':keys']
        return [p for k in a for p in differences(a[k],b[k],path+'/'+k)]
    if isinstance(a,list):
        if len(a)!=len(b):return [path+':length']
        return [p for n,(x,y) in enumerate(zip(a,b)) for p in differences(x,y,path+'/'+str(n))]
    return [] if a==b else [path]


def run(count,mode):
    original=Manufacturing.snapshot
    rows=[]
    for n in range(count):
        snapshots=[]
        def observed(app,*args,**kwargs):
            if mode=='natural':result=original(app,*args,**kwargs)
            else:
                at='2026-10-22T00:00:01Z' if mode=='boundary' and len(snapshots)>=3 else '2026-10-22T00:00:00Z'
                with patch.object(Ledger,'_now',staticmethod(lambda:at)):
                    result=original(app,*args,**kwargs)
            snapshots.append(copy.deepcopy(result))
            return result
        case=ApplicationTests('test_seed_safety_cases_and_idempotence')
        result=unittest.TestResult();started=time.perf_counter()
        with nullcontext() if mode=='original' else patch.object(Manufacturing,'snapshot',observed):case.run(result)
        diff=None if mode=='original' else differences(snapshots[2],snapshots[3]) if len(snapshots)>=4 else ['missing comparison']
        rows.append(dict(run=n,passed=result.wasSuccessful(),errors=len(result.errors),
                         comparisonAssertionFailures=sum('self.assertEqual(initial, self.app.snapshot())' in trace for _,trace in result.failures),
                         milliseconds=round((time.perf_counter()-started)*1000,3),comparisonDifferences=diff))
    failed=sum(not r['passed'] for r in rows)
    return dict(mode=mode,runs=count,failures=failed,failureRate=failed/count,
                medianMs=statistics.median(r['milliseconds'] for r in rows),samples=rows,
                originalTestUnchanged=True,clockScope='none' if mode=='original' else 'snapshot calls in this disposable test process only')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--runs',type=int,default=30)
    p.add_argument('--mode',choices=['original','natural','boundary','fixed'],default='natural')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=run(a.runs,a.mode);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='samples'}))
    raise SystemExit(1 if result['failures'] else 0)
