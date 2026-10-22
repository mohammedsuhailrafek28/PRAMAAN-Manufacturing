import cProfile, pstats, sys, time, io
from pathlib import Path
A = r"C:\Users\HAIL\AppData\Local\Temp\claude\C--Users-HAIL-documents-pramaan-manufacturing\c62f2fee-8f85-4474-86ce-f8aea199b730\scratchpad\aud"
sys.path.insert(0, A); sys.path.insert(0, A + r"\integration")
from application.service import Manufacturing
from application.anchors import TrustedAnchor
import application.service as S
work = Path(__file__).parent
db = work / "bench_copy.sqlite"; cp = work / "bench_checkpoint.json"
anchor = TrustedAnchor(cp)
app = Manufacturing(db); anchor.verify(app, deadline=float("inf")); app.close()   # activation
journal_cache = None
for i in range(3):
    t0 = time.perf_counter(); app = Manufacturing(db); t1 = time.perf_counter()
    # emulate server request but with unlimited deadline to measure true work
    app.db.execute("BEGIN IMMEDIATE"); app.audit._verified_token = None
    t2 = time.perf_counter(); a = anchor.verify(app, deadline=float("inf")); t3 = time.perf_counter()
    snap = app._snapshot(None); t4 = time.perf_counter()
    app.db.rollback(); app.close()
    print(f"req{i}: open={t1-t0:.2f}s verify={t3-t2:.2f}s _snapshot={t4-t3:.2f}s total={t4-t0:.2f}s state={a['state']}")
app = Manufacturing(db); app.db.execute("BEGIN IMMEDIATE")
pr = cProfile.Profile(); pr.enable(); app._snapshot(None); pr.disable(); app.db.rollback()
s = io.StringIO(); pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(16); print(s.getvalue()[:3800])
