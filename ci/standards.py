"""Existing synthetic/conformance functions plus the verifier's live schema gate."""
import json
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'integration')]
import run_validation as baseline
from application.safety31 import run as expanded_safety
from application.service import Manufacturing
from jsonschema import Draft7Validator,FormatChecker

out=ROOT/'.tmp-ci-results';out.mkdir(exist_ok=True);baseline.REPORTS=out
gs1=Path(sys.argv[1])
conformance=baseline.external_conformance(gs1)
retained=baseline.safety()
expanded=expanded_safety()
assert retained['falseReleases']==0 and expanded['falseReleases']==0
schema=json.loads((gs1/'EPCIS-JSON-Schema.json').read_bytes())
validator=Draft7Validator(schema,format_checker=FormatChecker())
with tempfile.TemporaryDirectory(prefix='pramaan-ci-conformance-') as temp:
    app=Manufacturing(Path(temp)/'db.sqlite')
    try:
        app.seed_demo()
        documents=app.db.execute('SELECT raw FROM captures').fetchall()
        for row in documents:validator.validate(json.loads(row[0]))
        assert len(documents)==58
    finally:app.close()
result=dict(retained={k:v for k,v in retained.items() if k!='scenarios'},expanded=expanded,
            conformance=conformance,liveDocumentsValidated=len(documents))
(out/'standards-safety.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
