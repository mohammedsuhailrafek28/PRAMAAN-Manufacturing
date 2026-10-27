"""Latency cost of the guard: snapshot() on the seeded demo, candidate vs frozen v1.0 source (git archive of c25466c). Single machine, indicative only.
usage: python -B timing.py OUT.json (repo root)"""
import json, statistics, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
SNIP = r'''
import sys, time, tempfile, json, statistics
from pathlib import Path
sys.path.insert(0, sys.argv[1]); sys.dont_write_bytecode = True
from application.service import Manufacturing
with tempfile.TemporaryDirectory() as d:
    a = Manufacturing(Path(d) / "m.sqlite"); a.seed_demo(); t = []
    for _ in range(15):
        s = time.perf_counter(); a.snapshot(); t.append((time.perf_counter() - s) * 1000)
    a.close()
print(json.dumps(dict(medianMs=statistics.median(t), minMs=min(t), maxMs=max(t))))
'''
with tempfile.TemporaryDirectory() as t:
    t = Path(t); (t / "s.py").write_text(SNIP); fz = t / "f"; fz.mkdir()
    tar = subprocess.run(["git", "-C", str(ROOT), "archive", "c25466c56e5724158d534ff7b59f01ac48643101"], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(fz)], input=tar, check=True)
    out = {}
    for name, root in (("frozen_v1_0", fz), ("candidate_A_plus_B", ROOT)):
        runs = [json.loads(subprocess.run([sys.executable, "-B", str(t / "s.py"), str(root)], capture_output=True, text=True, check=True).stdout) for _ in range(3)]
        out[name] = dict(medianOfMediansMs=statistics.median(r["medianMs"] for r in runs), runs=runs)
Path(sys.argv[1]).write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))
