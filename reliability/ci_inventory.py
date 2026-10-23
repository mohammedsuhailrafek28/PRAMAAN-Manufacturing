"""Read-only comparison to hosted-green CI; never regenerates its inventory."""
import argparse
import hashlib
import json
import io
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
CI='04d974fd6307fca1f129be6b5683f4468b5fcad7'
def blob(ref,name):
 p=subprocess.run(['git','show',f'{ref}:{name}'],cwd=ROOT,capture_output=True)
 return p.stdout if p.returncode==0 else None

def blobs(ref,names):
 out=subprocess.check_output(['git','cat-file','--batch'],input=''.join(f'{ref}:{n}\n' for n in names).encode(),cwd=ROOT)
 stream=io.BytesIO(out);result={}
 for name in names:
  header=stream.readline().decode().split()
  if header[-1]=='missing':result[name]=None;continue
  size=int(header[-1]);result[name]=stream.read(size)
  assert stream.read(1)==b'\n'
 return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 manifest=json.loads(blob(CI,'ci/frozen-source.json'))
 baseline_files=set(subprocess.check_output(['git','ls-tree','-r','--name-only',manifest['baseline']],cwd=ROOT,text=True).splitlines())
 result=dict(ci=CI,frozenBaseline=manifest['baseline'],frozenCount=len(manifest['files']),targets={})
 for ref in (manifest['baseline'],'73f3bdbd78ee8bdf4b323457ba2f036f16fb82d9','f9dcf56ae52b095a3af05b8fc45a2568cd5642fe'):
  changed=[]
  contents=blobs(ref,manifest['files'])
  for name,expected in manifest['files'].items():
   data=contents[name]
   if data is None or hashlib.sha256(data).hexdigest()!=expected:changed.append(name)
  files=subprocess.check_output(['git','ls-tree','-r','--name-only',ref],cwd=ROOT,text=True).splitlines()
  new=[n for n in files if n.startswith(('application/','recall-ui/','recall-engine/','integration/','experiments/')) and n not in manifest['files'] and n not in baseline_files]
  result['targets'][ref]=dict(changedFrozenFiles=changed,additionalPathsRequiringCoverageReview=new)
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
 print(json.dumps({k:len(v['changedFrozenFiles']) for k,v in result['targets'].items()}))
