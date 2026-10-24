"""Negative reproductions on the UNMODIFIED frozen v1.0 source (git archive of c25466c into a temp dir), then the same legacy database read by this candidate.
usage (repository root, with the project's Python):  python -B research/lot_identity_ab/reproduce_v1_0.py OUT.json
Needs the commit c25466c56e5724158d534ff7b59f01ac48643101 in the local git object store (the tag manufacturing-demo-v1.0 points to it). Loopback-free; disposable temp files only.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
FROZEN = "c25466c56e5724158d534ff7b59f01ac48643101"

OLD = r'''
import json, sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
from application.service import Manufacturing
from application.anchors import TrustedAnchor, export_anchor, publish_candidate
stage, db, work = sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4])
MOTORS = {"MTR-91001": ("UNKNOWN", "BR-310"), "MTR-91002": ("BR-310", "BR-2O4"), "MTR-91003": ("BR-310", "BR-312"),
          "MTR-91004": ("BR-204", "BR-310"), "MTR-91005": ("br-204", "BR-312"), "MTR-91006": ("BR-999", "BR-310")}
if stage == "init":
    a = Manufacturing(db)
    for m in MOTORS: a.create_unit(m)
    a.close(); a = Manufacturing(db); publish_candidate(work / "c0.json", export_anchor(a)); a.close()
elif stage == "populate":
    a = Manufacturing(db)
    for m, (de, nde) in MOTORS.items():
        a.assemble(m, de, nde); a.record_historical_shipment_fixture(m)
    a.announce("BR-204", ["DE"]); a.snapshot()
    publish_candidate(work / "c1.json", export_anchor(a, json.loads((work / "c0.json").read_bytes())))
    s = a.snapshot(trusted_anchor=TrustedAnchor(work / "c1.json", work / "c0.json")); a.close()
    print(json.dumps({"state": s["checkpoint"]["state"], "motors": {m: {"eligible": s["eligibility"][m]["currentReleaseEligible"],
          "finding": next(iter(s["decisions"][m].values()))["current"]["evidenceFinding"], "action": next(iter(s["decisions"][m].values()))["current"]["operationalAction"]} for m in MOTORS}}))
'''

NEW = r'''
import json, sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
from application.service import Manufacturing
from application.anchors import TrustedAnchor
from application import checkpoint_ops
db, work = Path(sys.argv[2]), Path(sys.argv[3])
a = Manufacturing(db)
s = a.snapshot(trusted_anchor=TrustedAnchor(work / "c1.json", work / "c0.json")); a.close()
out = {"state": s["checkpoint"]["state"], "motors": {}}
for m, v in s["decisions"].items():
    c = next(iter(v.values()))["current"]
    out["motors"][m] = {"eligible": s["eligibility"][m]["currentReleaseEligible"], "finding": c["evidenceFinding"], "evaluatorAction": c["evaluatorOperationalAction"],
                        "guardedAction": c["operationalAction"], "reasons": sorted({f["reason"] for f in c["identityGuard"]["findings"]})}
prop = checkpoint_ops.propose(db, work / "c0.json", work / "custody")
out["review"] = {"refusedForIdentity": prop["review"]["refusedForIdentity"], "requiresAcknowledgement": prop["review"]["requiresAcknowledgement"]}
try:
    checkpoint_ops.accept(db, work / "c0.json", work / "custody", Path(prop["candidate"]), "synthetic", prop["candidateSha256"], [r["motor"] for r in prop["review"]["rows"]])
    out["acceptWithEveryMotorAcknowledged"] = "ACCEPTED (unexpected)"
except SystemExit as e:
    out["acceptWithEveryMotorAcknowledged"] = str(e)[:160]
print(json.dumps(out))
'''


def main(out):
    py = sys.executable
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        frozen = t / "frozen"; frozen.mkdir()
        tar = subprocess.run(["git", "-C", str(ROOT), "archive", FROZEN], capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(frozen)], input=tar, check=True)
        work = t / "work"; work.mkdir(); db = t / "legacy.sqlite"
        (t / "old.py").write_text(OLD, encoding="utf-8"); (t / "new.py").write_text(NEW, encoding="utf-8")
        run = lambda script, root, *a: subprocess.run([py, "-B", str(t / script), str(root), *map(str, a)], capture_output=True, text=True, cwd=str(t), check=True).stdout.strip()
        run("old.py", frozen, "init", db, work)
        legacy = json.loads(run("old.py", frozen, "populate", db, work))
        candidate = json.loads(run("new.py", ROOT, db, work))
    res = dict(frozenCommit=FROZEN, v1_0_with_its_own_checkpoint=legacy, candidate_reading_same_database=candidate)
    Path(out).write_text(json.dumps(res, indent=1, sort_keys=True))
    print(json.dumps(res, indent=1, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1])
