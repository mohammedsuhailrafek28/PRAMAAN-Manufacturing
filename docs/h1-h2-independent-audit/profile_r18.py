import cProfile, pstats, shutil, sys, time, io, json
from pathlib import Path
sys.path.insert(0, r"C:\Users\HAIL\AppData\Local\Temp\claude\C--Users-HAIL-documents-pramaan-manufacturing\c62f2fee-8f85-4474-86ce-f8aea199b730\scratchpad\aud")
sys.path.insert(0, r"C:\Users\HAIL\AppData\Local\Temp\claude\C--Users-HAIL-documents-pramaan-manufacturing\c62f2fee-8f85-4474-86ce-f8aea199b730\scratchpad\aud\integration")
from application.service import Manufacturing
from application.anchors import export_anchor, publish_candidate, TrustedAnchor, ledger_binding

work = Path(__file__).parent
src = work / "bench.sqlite"; db = work / "bench_copy.sqlite"
if not db.exists(): shutil.copy(src, db)
cp = work / "bench_checkpoint.json"
app = Manufacturing(db)
if not cp.exists():
    t = time.perf_counter(); cand = export_anchor(app); print("export_anchor s", round(time.perf_counter() - t, 2)); publish_candidate(cp, cand)
db_bytes = db.stat().st_size
rows = {t: app.db.execute(f"select count(*) from {t}").fetchone()[0] for t in ("motors","captures","events","rejections","decision_runs","app_units","recall_announcements","app_audit")}
print("db bytes", db_bytes, "rows", rows)
anchor = TrustedAnchor(cp)
t = time.perf_counter(); r = anchor.verify(app, deadline=float("inf")); print("COLD verify s", round(time.perf_counter() - t, 2), r["state"], r["h2"]["status"])
for i in range(3):
    t = time.perf_counter(); r = anchor.verify(app, deadline=float("inf")); print("WARM verify s", round(time.perf_counter() - t, 2), r["state"])
# part timings
t = time.perf_counter(); ledger_binding(app); print("ledger_binding s", round(time.perf_counter() - t, 2))
t = time.perf_counter(); app.audit.journal_bytes_key(); print("journal_bytes_key s", round(time.perf_counter() - t, 2))
app.db.execute("BEGIN IMMEDIATE")
pr = cProfile.Profile(); pr.enable(); anchor.verify(app, deadline=float("inf")); pr.disable()
app.db.rollback()
s = io.StringIO(); pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(14); print(s.getvalue()[:3500])
# a raw-file hash for comparison
import hashlib
t = time.perf_counter(); h = hashlib.sha256(db.read_bytes()).hexdigest(); print("sha256(db file) s", round(time.perf_counter() - t, 4))
app.close()
