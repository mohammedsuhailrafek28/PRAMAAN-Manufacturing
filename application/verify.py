"""Run reproducibility gates into docs/phase3-validation, preserving source reports."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from .service import ROOT, Manufacturing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gs1-checkout", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT/"docs"/"phase3-validation",
                        help="where reports are written (default: docs/phase3-validation)")
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT/"integration"))
    import run_validation as baseline
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    baseline.REPORTS = out
    gates = baseline.verify_baselines(args.gs1_checkout)
    conformance = baseline.external_conformance(args.gs1_checkout)
    safety = baseline.safety()
    # Verify newly captured supplier, manufacturing and shipment documents too.
    from jsonschema import Draft7Validator, FormatChecker
    schema = json.loads((args.gs1_checkout/"EPCIS-JSON-Schema.json").read_bytes())
    validator = Draft7Validator(schema, format_checker=FormatChecker())
    with tempfile.TemporaryDirectory() as temp:
        service = Manufacturing(Path(temp)/"conformance.sqlite")
        try:
            service.seed_demo()
            raw_docs = service.db.execute("SELECT raw FROM captures").fetchall()
            for row in raw_docs:
                validator.validate(json.loads(row[0]))
            live_conformance = dict(documents=len(raw_docs), gs1SchemaPassed=True,
                                    scope="Generated supported-profile documents; not a full EPCIS repository certification")
        finally:
            service.close()
    def run(name, command, cwd=ROOT):
        start=time.perf_counter()
        result=subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=240)
        (out/f"{name}.txt").write_text(result.stdout+result.stderr, encoding="utf-8")
        if result.returncode:
            raise AssertionError(f"{name} failed: see {out/name}")
        return dict(exitCode=0, elapsedSeconds=round(time.perf_counter()-start,3))
    npm="npm.cmd" if os.name=="nt" else "npm"
    checks = {
        "application": run("application-tests", [sys.executable,"-m","unittest","application.test_application","application.test_remediation","-v"]),
        "exporter": run("exporter-tests", [sys.executable,"-m","unittest","discover","-s","recall-ui/tests","-p","test_*.py","-v"]),
        "snapshot": run("snapshot-check", [sys.executable,"recall-ui/tools/export_snapshot.py","--check"]),
        "ui": run("ui-tests", [npm,"test"], ROOT/"recall-ui"),
        "build": run("production-build", [npm,"run","build"], ROOT/"recall-ui"),
        "browser": run("browser-tests", [npm,"run","test:e2e"], ROOT/"recall-ui"),
    }
    result=dict(baselines=gates, checks=checks, liveConformance=live_conformance,
                retainedConformance=conformance, retainedSafety={k:v for k,v in safety.items() if k!="scenarios"})
    (out/"phase3-results.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
