"""Expanded synthetic safety reporting. Ground truth is outside the engine/app."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from .service import Manufacturing, ROOT


def run():
    results=[]
    def score(name,a,m,unsafe,expected):
        d=next(iter(a.snapshot()['decisions'][m].values()))['current']
        held=d['operationalAction']=='RECALL_HOLD'
        results.append(dict(case=name,syntheticUnsafe=unsafe,expectedFinding=expected,actualFinding=d['evidenceFinding'],
                            behaviorAgrees=d['evidenceFinding']==expected,falseRelease=unsafe and not held,unnecessaryHold=not unsafe and held,
                            decisionId=d['decisionId'],reasonCodes=d['reasonCodes']))
    for i,(de,nde,scope) in enumerate((d,n,s) for d in ('BR-204','BR-310') for n in ('BR-204','BR-310') for s in (None,['DE'],['NDE'],['DE','NDE'])):
        with TemporaryDirectory() as t:
            a=Manufacturing(Path(t)/'db')
            try:
                m=f'MTR-SAFETY-{i}';a.create_unit(m);a.assemble(m,de,nde);a.ship(m);a.announce('BR-204',scope)
                slots=scope if scope is not None else ['DE','NDE']
                unsafe=any(lot=='BR-204' and slot in slots for slot,lot in [('DE',de),('NDE',nde)])
                score(f'de={de};nde={nde};scope={scope}',a,m,unsafe,'AFFECTED' if unsafe else 'EXCLUDED_WITH_EVIDENCE')
            finally:a.close()
    with TemporaryDirectory() as t:
        a=Manufacturing(Path(t)/'db')
        try:
            a.seed_demo()
            for m,unsafe,expected in [('MTR-26001',True,'AFFECTED'),('MTR-26002',False,'UNRESOLVED'),('MTR-26003',False,'EXCLUDED_WITH_EVIDENCE'),('MTR-26004',False,'UNRESOLVED'),('MTR-26005',True,'UNRESOLVED')]:
                score('seed '+m,a,m,unsafe,expected)
            a.replace('MTR-26001','BR-312');score('clean replacement',a,'MTR-26001',False,'EXCLUDED_WITH_EVIDENCE')
            a.observe('MTR-26001','BR-204');score('late observation, actual unsafe synthetic truth',a,'MTR-26001',True,'UNRESOLVED')
            a.create_unit('MTR-UNKNOWN');score('missing baseline, physically safe but unknown to engine',a,'MTR-UNKNOWN',False,'UNRESOLVED')
            a.create_unit('MTR-DOUBLE');a.assemble('MTR-DOUBLE','BR-204','BR-310')
            a.event('MTR-DOUBLE','COMPONENT_INSTALLED','ASSY',dict(componentType='BEARING',slot='DE',part='BR-6205',lot='BR-310',serial='EXTRA-CLAIM',identityGranularity='SERIAL'),work_order='BUILD-MTR-DOUBLE')
            score('double installation, affected item physically remains',a,'MTR-DOUBLE',True,'UNRESOLVED')
        finally:a.close()
    report=dict(scope='25 authored local synthetic decisions; DE/NDE scope matrix plus ambiguity, gaps, observation, replacement, missing baseline and double installation. Physical truth is supplied only here, not to decision code. Not factory safety evidence.',
                total=len(results),unsafeCases=sum(r['syntheticUnsafe'] for r in results),safeCases=sum(not r['syntheticUnsafe'] for r in results),
                behaviorAgreements=sum(r['behaviorAgrees'] for r in results),falseReleases=sum(r['falseRelease'] for r in results),unnecessaryHolds=sum(r['unnecessaryHold'] for r in results),cases=results)
    target=ROOT/'docs/phase31-validation/expanded-safety.json';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if report['falseReleases'] or report['behaviorAgreements']!=report['total']:
        raise AssertionError('Expanded synthetic safety gate failed; see expanded-safety.json')
    return {k:v for k,v in report.items() if k!='cases'}


if __name__=='__main__': print(json.dumps(run(),indent=2))
