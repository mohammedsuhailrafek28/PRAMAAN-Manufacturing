"""Synthetic, disposable exact-backend latency observation, not a safety assertion."""
import json,sys,tempfile,threading,time
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root))
from application.service import Manufacturing
from application.anchors import export_anchor
from application.server import make_server
with tempfile.TemporaryDirectory(prefix="pramaan-rc-latency-") as tmp:
 p=Path(tmp);app=Manufacturing(p/"ledger.sqlite");app.seed_demo()
 anchor=p/"test-only-owner-custody.json";anchor.write_text(json.dumps(export_anchor(app)))
 start=time.perf_counter();server=make_server(p/"ledger.sqlite",0,trusted_anchor=anchor);activation=(time.perf_counter()-start)*1000
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 def get():
  start=time.perf_counter()
  try:
   with urlopen(f"http://127.0.0.1:{server.server_port}/api/snapshot",timeout=4) as r:status,snap=r.status,json.load(r)
  except HTTPError as e:status,snap=e.code,json.load(e)
  return dict(ms=(time.perf_counter()-start)*1000,status=status,state=snap.get("checkpoint",{}).get("state")),snap
 try:
  samples=[]
  for _ in range(5):
   sample,snap=get();samples.append(sample)
  motors=len(snap.get("units",[]));events=sum(len(u["events"]) for u in snap.get("units",[]))
  start=time.perf_counter();app.observe("MTR-26003","BR-204");capture=(time.perf_counter()-start)*1000
  after,snap=get()
  print(json.dumps(dict(kind="Synthetic local actual f9 backend; five serial HTTP samples, not production p95 or browser-visible latency",motors=motors,eventsBeforeCapture=events,activationMs=activation,snapshotSamples=samples,captureMs=capture,postCaptureSnapshot=after,postCaptureCurrentEligibility=snap.get("eligibility",{}).get("MTR-26003"),journalEntries=app.db.execute("select count(*) from app_audit").fetchone()[0]),indent=2))
 finally:server.shutdown();server.server_close();thread.join();app.close()
