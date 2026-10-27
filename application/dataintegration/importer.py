"""Orchestration: parse -> validate -> plan (preview) -> capture + preserve (import).

`run(..., commit=False)` writes nothing anywhere. `run(..., commit=True)` executes exactly the plan the preview showed: first the append-only staging
store is given the originals and every transformation, then events go through the existing capture path, then dispositions are recorded.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .. import lot_identity as lots
from .. import service
from ..service import Manufacturing
from .capture import DEFAULT_WINDOW, capture_event, import_ref, session_window, time_problem
from .ingest import ingest
from .mapping import MAPPING_DIR, MappingConfig, load_mapping
from .planner import Options, Plan, World, plan as make_plan
from .report import ImportReport, build
from .staging import Staging, tool_versions

DEFAULT_MAPPINGS = {"ERP": "erp.lot_issue.v1.json", "MES": "mes.assembly.v1.json", "SCADA": "scada.station_signal.v1.json",
                    "QUALITY": "quality.inspection.v1.json", "LOGISTICS": "logistics.dispatch.v1.json"}


class CaptureMismatch(RuntimeError):
    """The ledger is not in the state the plan was made for; nothing further is written."""


@dataclass
class Source:
    system: str
    path: Path
    mapping: Optional[Path] = None

    def config(self) -> MappingConfig:
        cfg = load_mapping(self.mapping or MAPPING_DIR / DEFAULT_MAPPINGS[self.system.upper()])
        if cfg.sourceSystem.value != self.system.upper():
            raise ValueError(f"mapping {cfg.mappingId} is for {cfg.sourceSystem.value}, not {self.system}")
        return cfg


def ledger_head(app: Manufacturing):
    row = app.db.execute("SELECT hash FROM events ORDER BY ordinal DESC LIMIT 1").fetchone()
    return row[0] if row else None


def execute(plan: Plan, app: Manufacturing) -> None:
    for e in plan.events:                       # nothing is created or written unless every planned event is still safe to capture
        problem = time_problem(e.occurred, app.clock(), DEFAULT_WINDOW if e.motor in plan.creates else session_window(app.ledger._config(e.motor), app.source(e.role, e.motor)) or ("9", "0"))
        if problem:
            raise CaptureMismatch(f"{e.event_id}: {problem}")
    for motor in plan.creates:
        app.create_unit(motor, "Imported via the data integration layer")
    for e in plan.events:
        source = app.source(e.role, e.motor)
        expected = int(e.event_id.rsplit(":", 1)[1])
        if app.ledger.watermark(e.motor)[source] + 1 != expected:
            raise CaptureMismatch(f"{e.motor}/{e.role}: ledger is at sequence {app.ledger.watermark(e.motor)[source]}, plan expected {expected - 1}")
        written = capture_event(app, e.motor, e.kind, e.role, e.payload, work_order=e.work_order, occurred=e.occurred, evidence=[import_ref(e.canonical_id, e.content_sha256)])
        if written["eventId"] != e.event_id:
            raise CaptureMismatch(f"planned {e.event_id}, ledger wrote {written['eventId']}")


def run(sources: list[Source], *, ledger=None, staging=None, options: Options = Options(), commit: bool = False, lot_registry=None) -> tuple[ImportReport, Plan, list]:
    configs = [s.config() for s in sources]
    files = [ingest(s.path, cfg) for s, cfg in zip(sources, configs)]
    opts = Options(create_units=options.create_units or any(c.capture.createMissingUnits for c in configs),
                   historical_shipments=options.historical_shipments or any(c.capture.historicalShipments for c in configs))
    if commit and (ledger is None or staging is None):
        raise ValueError("an import needs both a ledger path and a staging path")
    app = Manufacturing(ledger, lot_registry=lot_registry) if ledger and (commit or Path(ledger).exists()) else None
    st = Staging(staging) if staging and (commit or Path(staging).exists()) else None
    try:
        registry = app.registry if app else lots.LotRegistry.load(lot_registry if lot_registry is not None else service.DEFAULT_LOT_REGISTRY)
        plan = make_plan(files, World(registry, app, st), opts)
        if not commit:
            return build(files, plan, mode="PREVIEW", tools=tool_versions()), plan, files
        before = ledger_head(app)
        run_id = st.begin_run("IMPORT", [dict(name=f.name, sha256=f.sha256, mapping=f.mappingId, mappingSha256=f.mappingSha256) for f in files],
                              dict(createUnits=opts.create_units, historicalShipments=opts.historical_shipments), before)
        st.preserve(files)
        try:
            execute(plan, app)
        except Exception as exc:
            st.end_run(run_id, "FAILED", ledger_head(app), None, f"{type(exc).__name__}: {exc}")
            raise
        st.record_dispositions(run_id, files)
        report = build(files, plan, mode="IMPORT", tools=tool_versions())
        st.end_run(run_id, "COMPLETED", ledger_head(app), report.digest())
        return report, plan, files
    finally:
        if st:
            st.close()
        if app:
            app.close()
