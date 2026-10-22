import sys, json, copy, threading
from pathlib import Path
ROOT=Path(sys.argv[1]); sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(ROOT/"integration")); sys.path.insert(0,str(Path(__file__).parent))
sys.argv=[sys.argv[0],sys.argv[1],"x.json"]
import adversarial_audit as A
from application.server import make_server
from urllib.request import urlopen
from urllib.error import HTTPError
def get(b,p):
    try:
        with urlopen(b+p,timeout=60) as r: return r.status,r.read().decode()
    except HTTPError as e: return e.code,e.read().decode()
def keys(o,a=None):
    a=set() if a is None else a
    if isinstance(o,dict):
        for k,v in o.items(): a.add(k); keys(v,a)
    elif isinstance(o,list):
        for v in o: keys(v,a)
    return a
w=A.World(); w.app.observe("MTR-AAA1","BR-204")
srv=make_server(w.path,0,trusted_anchor=w.c0_file); th=threading.Thread(target=srv.serve_forever,daemon=True); th.start(); b=f"http://127.0.0.1:{srv.server_port}"
for p in ("/api/motors/MTR-AAA2/decisions","/api/lots/BR-310/investigation"):
    st,t=get(b,p); k=keys(json.loads(t)); print(p,st,"checkpoint" in k,"eligibility" in k,"currentReleaseEligible" in k,sorted(k & {"state","freshness","provenance"}))
srv.shutdown(); srv.server_close(); th.join(); w.app.close()
# legacy then observe over HTTP
w2=A.World(); e=copy.deepcopy(next(p for k,p in w2.app.audit.verify() if k=="EVALUATION")); e.pop("manifest"); w2.app.audit.append("EVALUATION",e); w2.app.db.commit(); w2.app.observe("MTR-AAA1","BR-204"); w2.app.close()
srv=make_server(w2.path,0,trusted_anchor=w2.c0_file); th=threading.Thread(target=srv.serve_forever,daemon=True); th.start(); b=f"http://127.0.0.1:{srv.server_port}"
st,t=get(b,"/api/snapshot"); print("legacy+extension snapshot:",st,t[:160])
srv.shutdown(); srv.server_close(); th.join()
