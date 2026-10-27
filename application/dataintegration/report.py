"""Import preview / result report: accepted, rejected and unresolved records, conflicts, planned ledger events. Deterministic (no wall-clock fields)."""
import json
from collections import Counter
from typing import Any, Optional

import pandas as pd
from pydantic import BaseModel

from .canonical import NOT_ESTABLISHED, sha256_json
from .models import FileResult, Issue
from .planner import Plan

DISCLAIMER = ("Imported records are CLAIMS made by source systems. They are preserved with provenance, not independently authenticated physical facts. "
              "Importing never verifies a part, never grants release eligibility or recall clearance, and never changes the recall evaluator, the ledger rules, "
              "checkpoint freshness or the shipment gate. Any new ledger evidence ends current clearance until a new checkpoint is proposed and accepted.")

CATEGORY = {
    "duplicate": {"EXACT_DUPLICATE_IN_BATCH", "DUPLICATE_OF_LEDGER_RECORD"},
    "contradiction": {"CONTRADICTORY_DUPLICATE", "CONTRADICTORY_LOT", "CONTRADICTORY_SERIAL", "CONTRADICTORY_IDENTITY", "CONTRADICTS_PRIOR_IMPORT", "CONTRADICTS_REGISTRY",
                      "REMOVAL_MISMATCH", "SECOND_SHIPMENT", "WORK_ORDER_ID_REUSED", "PARTIAL_PRIOR_IMPORT"},
    "missing": {"MISSING_UPSTREAM", "MISSING_WORK_ORDER", "MISSING_ASSEMBLY", "MISSING_IDENTITY", "OBLIGATIONS_NOT_MET", "MISSING_REQUIRED", "MISSING_COLUMN", "UNKNOWN_MOTOR",
                "UNKNOWN_WORK_ORDER", "REMOVAL_REQUIRED", "NO_MATCHING_INSTALL"},
    "ordering": {"TIME_ORDER", "OUTSIDE_WORK_ORDER_WINDOW"},
    "identity": {"UNRESOLVED_LOT", "BAD_IDENTITY"},
    "held": {"WORK_ORDER_GROUP_HELD"},
}
CODE_CATEGORY = {code: cat for cat, codes in CATEGORY.items() for code in codes}


class RecordRow(BaseModel):
    system: str
    file: str
    row: int
    recordId: Optional[str]
    motor: Optional[str]
    kind: Optional[str]
    outcome: str
    disposition: str
    reason: Optional[str]
    issues: list[Issue]
    transformations: int
    ledgerEventIds: list[str]
    canonicalId: Optional[str]


class PlannedEventRow(BaseModel):
    eventId: str
    eventType: str
    motor: str
    role: str
    occurredAt: str
    canonicalId: str


class ImportReport(BaseModel):
    reportVersion: int = 1
    mode: str
    disclaimer: str = DISCLAIMER
    notEstablished: list[str] = list(NOT_ESTABLISHED)
    tools: dict[str, str]
    options: dict[str, Any]
    files: list[dict]
    summary: dict[str, Any]
    unitsToCreate: list[str]
    plannedLedgerEvents: list[PlannedEventRow]
    records: list[RecordRow]

    def digest(self) -> str:
        """Content digest; the tool versions are excluded so the same import gives the same digest on any machine."""
        return sha256_json({k: v for k, v in self.model_dump(mode="json").items() if k != "tools"})


def build(files: list[FileResult], plan: Plan, *, mode: str, tools: dict, run_events: Optional[list] = None) -> ImportReport:
    rows = []
    for f in files:
        for r in f.records:
            c = r.canonical
            rows.append(RecordRow(system=f.sourceSystem, file=f.name, row=r.rowIndex, recordId=r.sourceRecordId, motor=r.motor, kind=c.kind.value if c else None,
                                  outcome=r.outcome or "REJECTED", disposition=r.disposition or "UNDECIDED", reason=r.reason, issues=r.issues, transformations=len(r.steps),
                                  ledgerEventIds=r.ledgerEventIds, canonicalId=c.canonicalId if c else None))
    count = Counter((x.outcome, x.disposition if x.outcome == "ACCEPTED" else "") for x in rows)
    cats = Counter()
    for x in rows:
        for i in x.issues:
            cats[CODE_CATEGORY.get(i.code, "warning" if i.severity == "WARNING" else "validation")] += 1
    by_system = {}
    for x in rows:
        s = by_system.setdefault(x.system, Counter())
        s[x.outcome] += 1
    summary = dict(
        records=len(rows),
        accepted=sum(v for (o, _), v in count.items() if o == "ACCEPTED"),
        acceptedForLedgerCapture=count[("ACCEPTED", "CAPTURE")],
        acceptedStagedOnly=count[("ACCEPTED", "STAGE_ONLY")],
        acceptedAlreadyImported=count[("ACCEPTED", "ALREADY_IMPORTED")],
        rejected=sum(v for (o, _), v in count.items() if o == "REJECTED"),
        unresolved=sum(v for (o, _), v in count.items() if o == "UNRESOLVED"),
        issuesByCategory=dict(sorted(cats.items())),
        bySystem={k: dict(sorted(v.items())) for k, v in sorted(by_system.items())},
        ledgerEventsPlanned=len(plan.events), unitsToCreate=len(plan.creates))
    opts = plan.options
    return ImportReport(mode=mode, tools=tools, options=dict(createUnits=opts.create_units, historicalShipments=opts.historical_shipments),
                        files=[dict(name=f.name, system=f.sourceSystem, mapping=f.mappingId, mappingSha256=f.mappingSha256, sha256=f.sha256, bytes=f.bytes, format=f.format,
                                    rows=f.rows, blankRowsSkipped=f.blankRowsSkipped, fileIssues=[i.model_dump() for i in f.fileIssues]) for f in files],
                        summary=summary, unitsToCreate=list(plan.creates),
                        plannedLedgerEvents=[PlannedEventRow(eventId=e.event_id, eventType=e.kind, motor=e.motor, role=e.role, occurredAt=e.occurred, canonicalId=e.canonical_id) for e in plan.events],
                        records=rows)


def validation_table(report: ImportReport) -> pd.DataFrame:
    """One line per issue of any severity (field/format validation, identity, relationships)."""
    out = [dict(system=r.system, file=r.file, row=r.row, recordId=r.recordId, motor=r.motor, outcome=r.outcome, severity=i.severity, code=i.code, field=i.field, message=i.message)
           for r in report.records for i in r.issues]
    return pd.DataFrame(out, columns=["system", "file", "row", "recordId", "motor", "outcome", "severity", "code", "field", "message"])


def conflict_table(report: ImportReport) -> pd.DataFrame:
    """Duplicates, contradictions, missing records, time-order faults, held groups and warnings only, with the related record where known."""
    out = []
    for r in report.records:
        for i in r.issues:
            cat = CODE_CATEGORY.get(i.code) or ("warning" if i.severity == "WARNING" else None)
            if cat:
                out.append(dict(category=cat, severity=i.severity, code=i.code, system=r.system, file=r.file, row=r.row, recordId=r.recordId, motor=r.motor, outcome=r.outcome,
                                related=i.related, message=i.message))
    df = pd.DataFrame(out, columns=["category", "severity", "code", "system", "file", "row", "recordId", "motor", "outcome", "related", "message"])
    return df.sort_values(["category", "code", "motor", "system", "row"], na_position="last", kind="stable").reset_index(drop=True) if len(df) else df


def render_text(report: ImportReport, *, limit: int = 200) -> str:
    s = report.summary
    lines = [f"IMPORT {report.mode}", "=" * 72,
             f"records {s['records']}: ACCEPTED {s['accepted']} (ledger capture {s['acceptedForLedgerCapture']}, staged only {s['acceptedStagedOnly']}, "
             f"already imported {s['acceptedAlreadyImported']}) | REJECTED {s['rejected']} | UNRESOLVED {s['unresolved']}",
             f"ledger: {s['unitsToCreate']} unit(s) to register, {s['ledgerEventsPlanned']} event(s) to write via the EPCIS-compatible capture path"]
    for sysname, c in s["bySystem"].items():
        lines.append(f"  {sysname:<10} " + "  ".join(f"{k} {v}" for k, v in c.items()))
    for title, outcome in (("ACCEPTED", "ACCEPTED"), ("REJECTED", "REJECTED"), ("UNRESOLVED", "UNRESOLVED")):
        rows = [r for r in report.records if r.outcome == outcome]
        lines += ["", f"{title} ({len(rows)})", "-" * 72]
        for r in rows[:limit]:
            note = r.reason or "; ".join(f"{i.code}" for i in r.issues if i.severity == "WARNING")
            lines.append(f"  {r.system[:4]:<4} {r.file[:22]:<22} row {r.row:<3} {str(r.recordId):<16} {str(r.motor):<10} {r.disposition.split('_', 1)[1] if r.disposition.startswith(('UNRESOLVED_', 'REJECTED_')) else r.disposition:<28} {note[:90] if note else ''}")
        if len(rows) > limit:
            lines.append(f"  ... {len(rows) - limit} more (see the JSON report)")
    lines += ["", report.disclaimer]
    return "\n".join(lines)


def write_reports(report: ImportReport, outdir) -> dict:
    from pathlib import Path
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    paths = dict(json=out / "import_report.json", validation=out / "validation_report.csv", conflicts=out / "conflict_report.csv", text=out / "import_preview.txt")
    paths["json"].write_text(json.dumps(report.model_dump(mode="json"), indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    validation_table(report).to_csv(paths["validation"], index=False, lineterminator="\n", encoding="utf-8")
    conflict_table(report).to_csv(paths["conflicts"], index=False, lineterminator="\n", encoding="utf-8")
    paths["text"].write_text(render_text(report) + "\n", encoding="utf-8", newline="\n")
    return {k: str(v) for k, v in paths.items()}
