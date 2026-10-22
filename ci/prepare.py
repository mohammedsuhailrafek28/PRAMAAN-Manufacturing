"""Non-product Windows CI prerequisites. No fallback to system browser/artifacts."""
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PINS=json.loads((ROOT/'ci/pins.json').read_text())
TOOLS=ROOT/'.tmp-ci-tools'


def check_file(path,sha):
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
        raise RuntimeError(f'Pinned artifact missing or changed: {path}')


def main():
    TOOLS.mkdir(exist_ok=True)
    archive=TOOLS/'chrome-win64.zip'
    chrome=PINS['chrome']
    if not archive.exists():
        with urllib.request.urlopen(chrome['url'],timeout=90) as response,archive.open('xb') as output:
            while block:=response.read(1024*1024): output.write(block)
    check_file(archive,chrome['sha256'])
    # Re-extract from the pinned digest on every preparation; never trust
    # a stale extracted executable just because the ZIP is present.
    with zipfile.ZipFile(archive) as zipped:
        for name in zipped.namelist():
            if not (TOOLS/name).resolve().is_relative_to(TOOLS.resolve()):
                raise RuntimeError('Unsafe ZIP member')
        zipped.extractall(TOOLS)
    gs1=TOOLS/'gs1'
    if not gs1.exists():
        subprocess.run(['git','init',str(gs1)],check=True)
        subprocess.run(['git','-C',str(gs1),'fetch','--depth','1',PINS['gs1']['repository'],PINS['gs1']['commit']],check=True)
        subprocess.run(['git','-C',str(gs1),'checkout','--detach',PINS['gs1']['commit']],check=True)
    commit=subprocess.check_output(['git','-C',str(gs1),'rev-parse','HEAD'],text=True).strip()
    if commit!=PINS['gs1']['commit']: raise RuntimeError('Wrong GS1 checkout')
    for name,sha in PINS['gs1']['files'].items():check_file(gs1/name,sha)
    print(json.dumps(dict(chromeArchiveSha256=chrome['sha256'],gs1Commit=commit)))


if __name__=='__main__':main()
