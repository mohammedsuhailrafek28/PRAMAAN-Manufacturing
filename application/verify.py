"""Run Phase 3.1 gates into docs/phase31-validation, preserving source reports."""
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
    parser.add_argument("--gs1-checkout", type=Path, default=Path(os.environ.get('PRAMAAN_GS1_CHECKOUT', ROOT.parent/'gs1-epcis')))
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT/"integration"))
    import run_validation as baseline
    out = ROOT/"docs"/"phase31-validation"/"verification"
    out.mkdir(exist_ok=True)
    baseline.REPORTS = out
    from .provenance import verify
    provenance=verify(ROOT)
    if not (args.gs1_checkout/'EPCIS-JSON-Schema.json').is_file():
        raise AssertionError('External GS1 checkout required: set PRAMAAN_GS1_CHECKOUT or use --gs1-checkout; see README')
    import hashlib
    for name,pin in [('EPCIS-JSON-Schema.json','d5ca9b1cad2c403679d9b07fb768108142d73e1dd024198ed64774b56b62227b'),('epcis-context.jsonld','b5c7cc9367ab638ecb77feb0b9aea222a427d9740bf3dda1b183fc3d4390714f')]:
        if hashlib.sha256((args.gs1_checkout/name).read_bytes()).hexdigest()!=pin:
            raise AssertionError(f'External GS1 artifact differs from pinned baseline: {name}')
    gates=dict(provenance=provenance)
    for name, command, cwd in (
        ('engine',[sys.executable,'-m','unittest','discover','-s','tests','-t','.','-v'], ROOT/'recall-engine'),
        ('foundation',[sys.executable,'experiments/foundation/interop.py','--gs1-checkout',str(args.gs1_checkout.resolve()),'--output',str(out/'foundation-results.json')],ROOT),
        ('integration',[sys.executable,'-m','unittest','discover','-s','integration_tests','-t','.','-v'],ROOT/'integration')):
        gates[name]=baseline.command(command,cwd,f'{name}-tests.txt')
        if gates[name]['exitCode']:
            raise AssertionError(f'{name} baseline failed')
    conformance = baseline.external_conformance(args.gs1_checkout)
    safety = baseline.safety()
    from .safety31 import run as expanded_safety
    expanded=expanded_safety()
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
        "application": run("application-tests", [sys.executable,"-m","unittest","application.test_application","-v"]),
        "remediation": run("remediation-tests", [sys.executable,"-m","unittest","application.test_remediation","-v"]),
        "exporter": run("exporter-tests", [sys.executable,"-m","unittest","discover","-s","recall-ui/tests","-p","test_*.py","-v"]),
        "snapshot": run("snapshot-check", [sys.executable,"recall-ui/tools/export_snapshot.py","--check"]),
        "ui": run("ui-tests", [npm,"test"], ROOT/"recall-ui"),
        "build": run("production-build", [npm,"run","build"], ROOT/"recall-ui"),
        "browser": run("browser-tests", [npm,"run","test:e2e"], ROOT/"recall-ui"),
    }
    result=dict(baselines=gates, checks=checks, liveConformance=live_conformance,
                retainedConformance=conformance, retainedSafety={k:v for k,v in safety.items() if k!="scenarios"}, expandedSafety=expanded)
    (out/"phase31-results.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
