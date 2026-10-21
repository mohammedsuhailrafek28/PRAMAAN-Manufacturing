"""Mutation check for the v2/v3 safety logic.

Each mutant breaks one safety rule in a throw-away copy of the tree and runs the v2/v3 test
modules there. A mutant that the tests do not catch is a missing test. The mutants are
deliberately plain text substitutions so they are easy to audit.

Run: python harness/mutation_check.py [--quiet]   (exit 1 if any mutant survives)
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULES = ["tests.test_slot_attribution", "tests.test_untrusted_observation"]

MUTANTS = [
    ("v3 blocker removed", "pramaan_recall/policy.py",
     "if cfg.untrusted_observation and blocking_observations(policy, s):",
     "if False and blocking_observations(policy, s):"),
    ("unaffected untrusted observation blocks", "pramaan_recall/policy.py",
     'if not is_affected(policy, o["observed"]):\n        return "UNAFFECTED"',
     'if False:\n        return "UNAFFECTED"'),
    ("staleness ignores recordedAt", "pramaan_recall/ledger.py",
     'return d is not None and d > skew and x["rec"] > o["rec"]',
     'return d is not None and d > skew'),
    ("staleness ignores clock trust", "pramaan_recall/ledger.py",
     'if skew is None or x["ts"] not in trusted or o["ts"] not in trusted:',
     'if skew is None:'),
    ("clock-skew margin dropped", "pramaan_recall/ledger.py",
     'return d is not None and d > skew and', 'return d is not None and d > 0 and'),
    ("missing skew parameter assumed zero", "pramaan_recall/ledger.py",
     'skew, trusted = attr.get("observationClockSkewSeconds"), attr.get("trustedTimeSources", [])',
     'skew, trusted = attr.get("observationClockSkewSeconds", 0), attr.get("trustedTimeSources", ["DEVICE_SYNCED", "OPERATOR_ENTERED"])'),
    ("resolution ignores ordering", "pramaan_recall/ledger.py",
     'ver = [v for v in s.verifications if v["trusted"] and clearly_after(attr, v, o)]',
     'ver = [v for v in s.verifications if v["trusted"]]'),
    ("out-of-scope observation loses review", "pramaan_recall/policy.py",
     '_add(flags, "OUT_OF_SCOPE_UNTRUSTED_AFFECTED_OBSERVATION")\n                review = True',
     '_add(flags, "OUT_OF_SCOPE_UNTRUSTED_AFFECTED_OBSERVATION")'),
    ("other-motor observation attributed to a slot", "pramaan_recall/ledger.py",
     'if self.track_untrusted and (not p.get("slot") or e.get("motorSerial") != self.motor):',
     'if self.track_untrusted and (not p.get("slot")):'),
    ("history ignores untrusted sightings (P2)", "pramaan_recall/policy.py",
     'if cfg.untrusted_observation and any(is_affected(policy, o["observed"]) for o in s.untrusted_obs):',
     'if False:'),
    ("new evaluations default to legacy", "pramaan_recall/engine.py",
     "DEFAULT_PROFILE = V3", "DEFAULT_PROFILE = LEGACY"),
    ("replay ignores the stored profile", "pramaan_recall/replay.py",
     "Config.from_profile(profile)", "Config.default()"),
    ("replay ignores coverage drift", "pramaan_recall/replay.py",
     "if digest and digest !=", "if False and digest !="),
    ("label clears ambiguity", "pramaan_recall/ledger.py",
     "ambiguous=len(cands) >= 2 or", 'ambiguous=(len(cands) >= 2 and labels["slots"] != {s.name}) or'),
    ("verification independence not enforced", "pramaan_recall/ledger.py",
     'if fails:\n                v["trusted"], v["rejectedReasons"] = False, fails',
     'if False:\n                v["trusted"], v["rejectedReasons"] = False, fails'),
]


def run(name, rel, old, new):
    w = tempfile.mkdtemp()
    try:
        shutil.copytree(ROOT, os.path.join(w, "w"), ignore=shutil.ignore_patterns("__pycache__", ".git"))
        p = os.path.join(w, "w", rel)
        with open(p, encoding="utf-8") as f:
            s = f.read()
        if s.count(old) != 1:
            return "BROKEN", f"pattern found {s.count(old)} times"
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(s.replace(old, new))
        r = subprocess.run([sys.executable, "-m", "unittest", *MODULES], cwd=os.path.join(w, "w"),
                           capture_output=True, text=True, env=dict(os.environ, MUTATION_RUN="1"))
        return ("KILLED" if r.returncode else "SURVIVED"), r.stderr.strip().splitlines()[-1]
    finally:
        shutil.rmtree(w, ignore_errors=True)


def main():
    rows = [(n, *run(n, *rest)) for n, *rest in MUTANTS]
    killed = sum(1 for r in rows if r[1] == "KILLED")
    if "--quiet" not in sys.argv:
        for n, st, last in rows:
            print(f"{st:9} {n} | {last}")
    print(f"mutants: {len(rows)}  killed: {killed}  survived: {len(rows) - killed}")
    return 0 if killed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
