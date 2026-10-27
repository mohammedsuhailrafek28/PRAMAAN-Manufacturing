"""Underlying unchanged A-K commands plus focused checks; full runner stays fail-closed.

This does not grant a green required summary when the new paths lack reviewed inventory.
It records independent component results using original pinned tools and exact counts.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"ci"))
import run_gates as gates
from prepare import TOOLS,check_file

def main():
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument("--retry-incomplete",action="store_true");options=parser.parse_args()
 out=ROOT/"docs/ps10-performance/validation";out.mkdir(parents=True,exist_ok=True)
 pins=json.loads((ROOT/"ci/pins.json").read_text())
 import platform
 if platform.python_version()!=pins["python"]:raise RuntimeError("Wrong Python")
 if subprocess.check_output(["node","--version"],text=True).strip()!=pins["node"]:raise RuntimeError("Wrong Node")
 if subprocess.check_output(["npm.cmd","--version"],text=True).strip()!=pins["npm"]:raise RuntimeError("Wrong npm")
 check_file(TOOLS/"chrome-win64.zip",pins["chrome"]["sha256"])
 gs1=TOOLS/"gs1"
 assert subprocess.check_output(["git","-C",str(gs1),"rev-parse","HEAD"],text=True).strip()==pins["gs1"]["commit"]
 for name,sha in pins["gs1"]["files"].items():check_file(gs1/name,sha)
 os.environ["PRAMAAN_CI_CHROME"]=str(TOOLS/"chrome-win64/chrome.exe")
 results={"mode":"ORIGINAL_COMPONENT_CHECKS_NOT_REQUIRED_SUMMARY","base":"6709b0c6f521006cf6332caeecec6b08dbd44e84","sourceCommit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),"checks":{}}
 if options.retry_incomplete:
  results=json.loads((out/"components.json").read_text())
  results.setdefault("retryNotes",[]).append("Install existing hash-pinned crypto lock; rerun previously failed/unexecuted checks only; unchanged source checks retained")
 def run(name,args,cwd=ROOT,pattern=None,timeout=1800):
  if options.retry_incomplete and results["checks"].get(name,{}).get("passCheck"):return
  print("CHECK",name,flush=True);start=time.perf_counter()
  try:
   r=subprocess.run(args,cwd=cwd,capture_output=True,text=True,encoding="utf8",errors="replace",timeout=timeout)
   text=r.stdout+r.stderr;(out/(name+".txt")).write_text(text,encoding="utf8")
   countOk=pattern is None or __import__("re").search(pattern,gates.terminal_text(text)) is not None
   results["checks"][name]=dict(exit=r.returncode,countMatches=countOk,seconds=time.perf_counter()-start,passCheck=r.returncode==0 and countOk)
  except subprocess.TimeoutExpired:results["checks"][name]=dict(passCheck=False,error="TIMEOUT")
  (out/"components.json").write_text(json.dumps(results,indent=2),encoding="utf8")
 py=sys.executable;E=gates.EXPECTED
 run("infra",[py,"-m","unittest","discover","-s","ci","-p","test_*.py","-v"],pattern=f"Ran {E['infra']} tests")
 run("engine",[py,"-m","unittest","discover","-s","tests","-t",".","-v"],ROOT/"recall-engine",f"Ran {E['engine']} tests")
 run("integration",[py,"-m","unittest","discover","-s","integration_tests","-t",".","-v"],ROOT/"integration",f"Ran {E['integration']} tests")
 for module,count in E["application"].items():run(module,[py,"-m","unittest","application."+module,"-v"],pattern=f"Ran {count} tests")
 run("focused",[py,"-m","unittest","performance.test_impact_query","-v"],pattern="Ran 21 tests")
 run("standards-safety",[py,"ci/standards.py",str(gs1)])
 run("foundation",[py,"experiments/foundation/interop.py","--gs1-checkout",str(gs1),"--output",str(out/"foundation.json")])
 run("exporter",[py,"-m","unittest","discover","-s","recall-ui/tests","-p","test_*.py","-v"],pattern="Ran 7 tests")
 run("snapshot",[py,"recall-ui/tools/export_snapshot.py","--check"])
 run("typecheck",["npm.cmd","run","typecheck"],ROOT/"recall-ui")
 run("build",["npm.cmd","run","build"],ROOT/"recall-ui")
 run("vitest",["npm.cmd","test"],ROOT/"recall-ui",rf"Tests\s+{E['vitest']} passed")
 run("browser-version",["node","ci/browser_version.cjs",os.environ["PRAMAAN_CI_CHROME"]],pattern=__import__("re").escape(pins["chrome"]["version"]))
 # All original auxiliary ports remain reserved. Primary4173 is foreign-owned;
 # an isolated test wrapper uses4450 with the identical suite/timeout/browser.
 import socket
 busy=[]
 for port in tuple(p for p in gates.PORTS if p!=4173)+(4450,):
  with socket.socket() as sock:
   sock.settimeout(.2)
   if sock.connect_ex(("127.0.0.1",port))==0:busy.append(port)
 if busy:results["checks"]["playwright"]={"passCheck":False,"error":"PORTS_BUSY; no other process stopped","ports":busy}
 else:run("playwright",["npm.cmd","run","test:e2e","--","--config",str(ROOT/"performance/playwright.config.ts")],ROOT/"recall-ui",f"{E['playwright']} passed")
 results["browserIsolation"]={"primaryPort":4450,"excludedForeignPrimary":4173,"config":"performance/playwright.config.ts","originalAssertionsAndTimeoutsUnchanged":True}

 from application.provenance import verify
 results["sourceProvenance"]=verify(ROOT)
 pins=json.loads((ROOT/"ci/frozen-source.json").read_text())
 changed=[name for name,sha in pins["files"].items() if not (ROOT/name).is_file() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=sha]
 results["existingFrozenFilesChanged"]=changed
 results["allComponentChecksPass"]=all(v["passCheck"] for v in results["checks"].values()) and not changed
 (out/"components.json").write_text(json.dumps(results,indent=2),encoding="utf8")
 print(json.dumps(results,indent=2));sys.exit(0 if results["allComponentChecksPass"] else 1)
if __name__=="__main__":main()
