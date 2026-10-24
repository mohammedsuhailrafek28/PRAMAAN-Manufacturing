"""Adversarial isolation check for Experiment A.

1. Build a disposable synthetic ledger (SQLite + journal) and a checkpoint file; hash them and the whole frozen source tree.
2. Run the full experiment as a child process under the write guard (writes only to its results dir; no DB, socket or subprocess
   except the independent-replay interpreter), with the fixture present on disk.
3. Re-hash. Any difference fails.
4. Negative controls prove the guard really blocks what the claim depends on.
5. Static scan: the experiment modules must not import application/sqlite3/socket/network modules.

usage: python -B safety_check.py --out DIR
"""
import argparse
import ast
import json
import os
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import safety  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
FORBIDDEN = {"application", "sqlite3", "socket", "http", "urllib", "requests", "ftplib", "smtplib", "ssl"}
EXEMPT = {"build_fixture.py", "safety_check.py"}


def digests(fixture):
    d = {"fixture/" + n: safety.file_digest(os.path.join(fixture, n)) for n in sorted(os.listdir(fixture))}
    d.update({"tree/" + k: v for k, v in safety.tree_digest(ROOT, exclude_prefixes=("research/", ".git/", ".venv/", "node_modules/")).items()
              if "__pycache__" not in k})
    return d


def static_scan():
    bad = []
    for n in sorted(os.listdir(HERE)):
        if n.endswith(".py") and n not in EXEMPT:
            for node in ast.walk(ast.parse(open(os.path.join(HERE, n), encoding="utf-8").read())):
                mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                bad += [f"{n}: imports {m}" for m in mods if m.split(".")[0] in FORBIDDEN]
    return bad


def negative_controls(fixture, out):
    import sqlite3
    import socket
    import sandbox
    res = {}
    db = os.path.join(fixture, "ledger.sqlite")
    with safety.WriteGuard(out):
        for name, fn in {
            "append_to_ledger_file": lambda: open(db, "ab"),
            "sqlite_connect_ledger": lambda: sqlite3.connect(db),
            "write_into_frozen_source": lambda: open(os.path.join(ROOT, "app.py"), "ab"),
            "overwrite_checkpoint": lambda: open(os.path.join(fixture, "checkpoint-001.json"), "wb"),
            "delete_checkpoint": lambda: os.remove(os.path.join(fixture, "checkpoint-001.json")),
            "network_connect": lambda: socket.create_connection(("127.0.0.1", 9), timeout=0.2),
            "evaluator_given_a_database_path": lambda: sandbox.replay(db, {}),
        }.items():
            try:
                fn()
                res[name] = "NOT BLOCKED"
            except (PermissionError, TypeError) as exc:
                res[name] = "blocked: " + type(exc).__name__
            except OSError as exc:
                res[name] = "blocked by OS: " + type(exc).__name__
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    fixture = tempfile.mkdtemp(prefix="pramaan_safety_fixture_")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    subprocess.run([sys.executable, "-B", os.path.join(HERE, "build_fixture.py"), fixture], cwd=ROOT, env=env, check=True)
    before = digests(fixture)
    run = subprocess.run([sys.executable, "-B", os.path.join(HERE, "run_experiment.py"), "--out", os.path.join(out, "guarded_run"), "--guard", "--skip-scaling"],
                         cwd=ROOT, env=dict(env, PRAMAAN_DISPOSABLE_FIXTURE=fixture), capture_output=True, text=True)
    after = digests(fixture)
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    nc = negative_controls(fixture, out)
    after2 = digests(fixture)
    summary = json.load(open(os.path.join(out, "guarded_run", "summary.json")))
    report = dict(fixtureFiles=sorted(k for k in before if k.startswith("fixture/")), hashedFiles=len(before), experimentExit=run.returncode,
                  changedAfterExperiment=changed, changedAfterNegativeControls=sorted(k for k in set(after) | set(after2) if after.get(k) != after2.get(k)),
                  guardViolationsDuringExperiment=summary["guardViolations"], negativeControls=nc, forbiddenImports=static_scan(),
                  passed=(run.returncode == 0 and not changed and not summary["guardViolations"] and not static_scan()
                          and all(v.startswith("blocked") for v in nc.values()) and after == after2))
    with open(os.path.join(out, "safety.json"), "w", newline="\n") as f:
        json.dump(report, f, indent=1, sort_keys=True)
        f.write("\n")
    print(json.dumps(report, indent=1, sort_keys=True))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
