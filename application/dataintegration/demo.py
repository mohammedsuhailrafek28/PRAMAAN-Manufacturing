"""Reproducible end-to-end demonstration with the bundled SYNTHETIC exports of five systems.
Run: python -B -m application.dataintegration demo [--workdir DIR]

1. preview batch 1 (nothing exists yet; nothing is written)       4. import batch 2: the missing ERP record, a rework, a re-sent changed record
2. import batch 1 into a new ledger + staging store                5. read-only recall evaluation of the imported evidence (no checkpoint, no clearance)
3. import batch 1 again: no event is written twice                 6. repeat the whole run in a second directory: identical report digests
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

from ..service import Manufacturing
from .importer import Source, run
from .planner import Options
from .report import render_text, write_reports

SAMPLES = Path(__file__).with_name("samples")
B1, B2 = SAMPLES / "batch1", SAMPLES / "batch2"
BATCH1 = [Source("ERP", B1 / "erp_lot_issue.csv"), Source("MES", B1 / "mes_assembly.csv"), Source("SCADA", B1 / "scada_signals.json"),
          Source("QUALITY", B1 / "quality_inspections.tsv"), Source("LOGISTICS", B1 / "logistics_dispatch.json")]
BATCH2 = BATCH1 + [Source("ERP", B2 / "erp_lot_issue.csv"), Source("MES", B2 / "mes_assembly.csv")]
OPTIONS = Options(create_units=True, historical_shipments=True)


def evaluate(ledger) -> dict:
    """Announce a recall of lot BR-204 at the drive end (existing API) and read the evaluator's findings for the imported motors. Read-only: no checkpoint is supplied,
    so nothing can be eligible for release; the evaluator itself is untouched."""
    app = Manufacturing(ledger)
    try:
        app.announce("BR-204", ["DE"])
        snap = app.snapshot()
        out = {}
        for motor, policies in sorted(snap["decisions"].items()):
            cur = next(iter(policies.values()))["current"]
            out[motor] = dict(finding=cur["evidenceFinding"], action=cur["operationalAction"], reasons=cur["reasonCodes"],
                              releaseEligible=snap["eligibility"][motor]["currentReleaseEligible"])
        rejections = app.db.execute("SELECT COUNT(*) FROM rejections").fetchone()[0]
        events = app.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        return dict(motors=out, ledgerRejections=rejections, ledgerEvents=events, checkpointState=snap["checkpoint"]["state"])
    finally:
        app.close()


def scenario(workdir: Path, say=lambda *a: None) -> dict:
    workdir.mkdir(parents=True, exist_ok=True)
    ledger, staging = workdir / "ledger.sqlite", workdir / "staging.sqlite"
    steps = {}

    report, _, _ = run(BATCH1, options=OPTIONS)                                          # 1: preview, no ledger, no staging
    steps["1_preview_batch1"] = report
    say(render_text(report, limit=12))
    for name, sources, commit in (("2_import_batch1", BATCH1, True), ("3_repeat_batch1", BATCH1, True), ("4_import_batch2", BATCH2, True)):
        report, _, _ = run(sources, ledger=ledger, staging=staging, options=OPTIONS, commit=commit)
        steps[name] = report
        s = report.summary
        say(f"\n--- {name}: accepted {s['accepted']} (ledger {s['acceptedForLedgerCapture']}, staged {s['acceptedStagedOnly']}, already imported {s['acceptedAlreadyImported']}), "
            f"rejected {s['rejected']}, unresolved {s['unresolved']}; ledger events written {s['ledgerEventsPlanned']}, units {s['unitsToCreate']}")
    for name, report in steps.items():
        write_reports(report, workdir / "reports" / name)
    evaluation = evaluate(ledger)
    (workdir / "reports" / "recall_evaluation_readonly.json").write_text(json.dumps(evaluation, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return dict(digests={k: v.digest() for k, v in steps.items()}, summaries={k: v.summary for k, v in steps.items()}, evaluation=evaluation)


def main(workdir=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    base = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="pramaan-di-"))
    if base.exists() and any(base.iterdir()):
        raise SystemExit(f"{base} is not empty; choose a new directory")
    print(f"working directory: {base}\n")
    first = scenario(base / "run1", print)
    ev = first["evaluation"]
    print("\nRecall evaluation of the imported evidence (lot BR-204, drive end; read-only, no checkpoint):")
    for motor, d in ev["motors"].items():
        print(f"  {motor}  {d['finding']:<18} {d['action']:<14} releaseEligible={d['releaseEligible']}  {', '.join(d['reasons'])}")
    print(f"  ledger events {ev['ledgerEvents']}, ledger rejections {ev['ledgerRejections']}, checkpoint state {ev['checkpointState']}")
    second = scenario(base / "run2")
    same = first["digests"] == second["digests"]
    print("\nreport digests:", json.dumps(first["digests"], indent=1))
    print(f"reproduced in a second directory with identical digests: {same}")
    print(f"reports: {base / 'run1' / 'reports'}")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
