"""Clean-checkout reproduction: clone the pushed branch into an empty directory and rerun the candidate's Python evidence there.
usage: python -B clean_checkout.py REMOTE_URL BRANCH OUT.txt   (UI/browser suites need npm and are not part of this script)"""
import subprocess, sys, tempfile
from pathlib import Path
url, branch, out = sys.argv[1:4]
lines = []
with tempfile.TemporaryDirectory() as t:
    dest = Path(t) / "clone"
    subprocess.run(["git", "clone", "-q", "--branch", branch, url, str(dest)], check=True)
    subprocess.run(["git", "-C", str(dest), "fetch", "-q", "origin", "tag", "manufacturing-demo-v1.0"], check=False)
    head = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    lines.append(f"clone HEAD {head}; branch {branch}; python {sys.version.split()[0]}")
    mods = ["test_application", "test_checkpoint_ops", "test_checkpoints", "test_consolidated_safety", "test_d5", "test_d6", "test_hardening", "test_remediation", "test_unified", "test_lot_identity_ab", "test_v11_hardening"]
    for m in mods:
        r = subprocess.run([sys.executable, "-B", "-m", "unittest", f"application.{m}"], cwd=dest, capture_output=True, text=True)
        tail = [l for l in r.stderr.splitlines() if l.startswith(("Ran", "OK", "FAILED"))]
        lines.append(f"application.{m}: " + " | ".join(tail))
    r = subprocess.run([sys.executable, "-B", "research/lot_identity_ab/reproduce_v1_0.py", str(Path(t) / "repro.json")], cwd=dest, capture_output=True, text=True)
    import json
    d = json.loads((Path(t) / "repro.json").read_text()) if r.returncode == 0 else {}
    c = d.get("candidate_reading_same_database", {})
    lines.append("reproduce_v1_0 exit " + str(r.returncode) + "; v1.0 eligible: " + str(sorted(k for k, v in d.get("v1_0_with_its_own_checkpoint", {}).get("motors", {}).items() if v["eligible"])))
    lines.append("candidate eligible: " + str(sorted(k for k, v in c.get("motors", {}).items() if v["eligible"])) + "; refusedForIdentity: " + str(c.get("review", {}).get("refusedForIdentity")))
Path(out).write_text("\n".join(lines) + "\n"); print("\n".join(lines))
