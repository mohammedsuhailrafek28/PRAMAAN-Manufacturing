"""Fail-closed non-product A-K runner. No product files are patched or skipped."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.tmp-ci-results'
PINS=json.loads((ROOT/'ci/pins.json').read_text())
FROZEN=json.loads((ROOT/'ci/frozen-source.json').read_text())
PORTS=(4173,4182,4183,4184)


def terminal_text(output):
    """Normalize CSI terminal formatting for assertions; preserve raw evidence.

    Hosted Vitest emits SGR between 'Tests' and its count despite FORCE_COLOR=0.
    This changes presentation only, never command exit or expected test counts.
    """
    return re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',output)


def frozen(root=ROOT,files=None):
    files=FROZEN['files'] if files is None else files
    for name,sha in files.items():
        path=root/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
            raise RuntimeError(f'Frozen safety source differs: {name}')
    if root==ROOT:
        tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
        unexpected=[p for p in tracked if p and p not in files and not p.startswith(('ci/','.github/','docs/'))]
        if unexpected:raise RuntimeError(f'Unapproved tracked paths: {unexpected}')


def ports_free():
    for port in PORTS:
        with socket.socket() as sock:
            sock.settimeout(.2)
            if sock.connect_ex(('127.0.0.1',port))==0:raise RuntimeError(f'Expected isolated test port busy: {port}')


def command(name,args,cwd=ROOT,pattern=None):
    start=time.perf_counter()
    proc=subprocess.run(args,cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=300)
    output=proc.stdout+proc.stderr
    (OUT/f'{name}.txt').write_text(output,encoding='utf-8')
    if proc.returncode!=0:raise RuntimeError(f'{name} exit {proc.returncode}; see {name}.txt')
    if pattern and not re.search(pattern,terminal_text(output)):raise RuntimeError(f'{name}: expected test count missing')
    return dict(exitCode=proc.returncode,seconds=round(time.perf_counter()-start,3),command=args)


def main():
    OUT.mkdir(exist_ok=True)
    # Remove only the report's success state: old generated logs cannot count as
    # evidence. A new unique run ID binds this invocation to its summary.
    result=dict(status='FAILED',invocation=uuid.uuid4().hex,commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                python=sys.version,node=None,chrome=PINS['chrome']['version'],gates={})
    try:
        if platform.system()!='Windows' or platform.python_version()!=PINS['python']:raise RuntimeError('Pinned Windows/Python required')
        if subprocess.check_output(['node','--version'],text=True).strip()!=PINS['node']:raise RuntimeError('Wrong Node version')
        if subprocess.check_output(['npm.cmd','--version'],text=True).strip()!=PINS['npm']:raise RuntimeError('Wrong npm version')
        result['node']=PINS['node']
        frozen();ports_free()
        from prepare import TOOLS,check_file
        check_file(TOOLS/'chrome-win64.zip',PINS['chrome']['sha256'])
        gs1=TOOLS/'gs1'
        if subprocess.check_output(['git','-C',str(gs1),'rev-parse','HEAD'],text=True).strip()!=PINS['gs1']['commit']:raise RuntimeError('GS1 revision mismatch')
        for name,sha in PINS['gs1']['files'].items():check_file(gs1/name,sha)
        sys.path.insert(0,str(ROOT))
        from application.provenance import verify
        result['gates']['K']=verify(ROOT)
        py=sys.executable;npm='npm.cmd';ui=ROOT/'recall-ui'
        lock=json.loads((ROOT/'recall-ui/package-lock.json').read_text())
        if any(not p.get('integrity','').startswith('sha512-') for name,p in lock['packages'].items() if name):
            raise RuntimeError('npm dependency without locked SHA512 integrity')
        result['gates']['infra']=command('infra',[py,'-m','unittest','discover','-s','ci','-p','test_*.py','-v'],pattern=r'Ran 5 tests')
        result['gates']['A']=command('engine',[py,'-m','unittest','discover','-s','tests','-t','.','-v'],ROOT/'recall-engine',r'Ran 127 tests')
        result['gates']['B']=command('foundation',[py,'experiments/foundation/interop.py','--gs1-checkout',str(gs1),'--output',str(OUT/'foundation.json')])
        checks=json.loads((OUT/'foundation.json').read_text())['checks']
        if len(checks)!=21 or not all(checks.values()):raise RuntimeError('Foundation needs all 21 checks')
        result['gates']['C']=command('integration',[py,'-m','unittest','discover','-s','integration_tests','-t','.','-v'],ROOT/'integration',r'Ran 44 tests')
        result['gates']['D']={}
        for module,count in [('test_application',7),('test_remediation',16),('test_hardening',13)]:
            result['gates']['D'][module]=command(module,[py,'-m','unittest',f'application.{module}','-v'],pattern=f'Ran {count} tests')
        standards=command('standards-safety',[py,'ci/standards.py',str(gs1)])
        result['gates']['E']=standards;result['gates']['J']=standards
        result['gates']['F']=command('exporter',[py,'-m','unittest','discover','-s','recall-ui/tests','-p','test_*.py','-v'],pattern=r'Ran 7 tests')
        command('snapshot',[py,'recall-ui/tools/export_snapshot.py','--check'])
        command('typecheck',[npm,'run','typecheck'],ui)
        result['gates']['G']=command('build',[npm,'run','build'],ui)
        result['gates']['H']=command('vitest',[npm,'test'],ui,r'Tests\s+33 passed')
        chrome=TOOLS/'chrome-win64/chrome.exe'
        if not chrome.is_file():raise RuntimeError('Pinned Chrome missing')
        os.environ['PRAMAAN_CI_CHROME']=str(chrome)
        command('browser-version',['node',str(ROOT/'ci/browser_version.cjs'),str(chrome)],pattern=re.escape(PINS['chrome']['version']))
        result['gates']['I']=command('playwright',[npm,'run','test:e2e','--','--config',str(ROOT/'ci/playwright.config.ts')],ui,r'29 passed')
        ports_free();frozen();verify(ROOT)
        if not set('ABCDEFGHIJK')<=result['gates'].keys():raise RuntimeError('Required gate omitted')
        result['status']='PASSED'
    except Exception as exc:
        result['error']=repr(exc)
        raise
    finally:
        (OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
