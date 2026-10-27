"""PS10 data integration layer (synthetic exports only). Run: python -B -m unittest application.test_data_integration -v

Covers: mappings and transformations, CSV/JSON parsing, field/identity/timestamp validation, duplicate / missing / contradictory detection, provenance and
transformation history, preview == import, repeatable imports, the existing EPCIS-compatible capture path, and the safety properties (no clearance,
no evaluator / gate / checkpoint change, no imported claim treated as verification).
"""
import contextlib
import hashlib
import io
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from . import server as server_mod                                  # noqa: F401  (import check only)
from .anchors import TrustedAnchor, export_anchor, publish_candidate
from .dataintegration import capture, demo, report as report_mod
from .dataintegration.canonical import CanonicalEvent, Kind, SourceSystem, build_event
from .dataintegration.cli import main as cli_main
from .dataintegration.importer import CaptureMismatch, Source, execute, run
from .dataintegration.ingest import ingest
from .dataintegration.mapping import MAPPING_DIR, MappingConfig, TimestampSpec, load_mapping, parse_timestamp
from .dataintegration.planner import Options, World, plan as make_plan
from .dataintegration.samples import generate
from .dataintegration.staging import Staging
from .service import Manufacturing
from . import lot_identity as lots

SAMPLES = Path(demo.__file__).with_name("samples")
B1, B2 = SAMPLES / "batch1", SAMPLES / "batch2"
OPTS = Options(create_units=True, historical_shipments=True)
ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(demo.__file__).parent


def by_id(report_or_files, system, record_id):
    """The one record row for a system and source record id (first occurrence)."""
    rows = report_or_files.records
    return next(r for r in rows if r.system == system and r.recordId == record_id)


def ledger_events(path, motor=None):
    app = Manufacturing(path)
    try:
        motors = [motor] if motor else [r[0] for r in app.db.execute("SELECT serial FROM app_units ORDER BY serial")]
        return {m: app.events(m) for m in motors}
    finally:
        app.close()


def count(path, sql):
    db = sqlite3.connect(str(path))
    try:
        return db.execute(sql).fetchone()[0]
    finally:
        db.close()


class Fixture(unittest.TestCase):
    """Batch 1 imported once into a scratch directory shared by the read-only tests."""
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls.dir = Path(cls.tmp.name)
        cls.preview, cls.preview_plan, _ = run(demo.BATCH1, options=OPTS)
        cls.report, cls.plan, cls.files = run(demo.BATCH1, ledger=cls.dir / "l.sqlite", staging=cls.dir / "s.sqlite", options=OPTS, commit=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def disposition(self, system, record_id):
        return by_id(self.report, system, record_id).disposition

    def codes(self, system, record_id):
        return {i.code for i in by_id(self.report, system, record_id).issues}


class MappingAndTransforms(unittest.TestCase):
    def test_bundled_mappings_load_and_are_stable(self):
        names = sorted(p.name for p in MAPPING_DIR.glob("*.json"))
        self.assertEqual(len(names), 5)
        for n in names:
            cfg = load_mapping(n)
            self.assertEqual(cfg.sha256(), load_mapping(MAPPING_DIR / n).sha256())

    def test_unknown_transform_adapter_mismatch_and_bad_zone_are_refused(self):
        base = json.loads((MAPPING_DIR / "erp.lot_issue.v1.json").read_text(encoding="utf-8"))
        bad = json.loads(json.dumps(base)); bad["fields"]["lot"]["transforms"] = ["shout"]
        with self.assertRaises(ValidationError):
            MappingConfig.model_validate(bad)
        bad = json.loads(json.dumps(base)); bad["timestamps"]["timezone"] = "Mars/Olympus"
        with self.assertRaises(ValidationError):
            MappingConfig.model_validate(bad)
        bad = json.loads(json.dumps(base)); bad["extra"] = 1
        with self.assertRaises(ValidationError):
            MappingConfig.model_validate(bad)
        wrong = json.loads(json.dumps(base)); wrong["sourceSystem"] = "MES"
        with self.assertRaises(ValueError):
            ingest(None, MappingConfig.model_validate(wrong), data=b"x")

    def test_timestamps_are_read_in_the_declared_zone_and_every_step_is_recorded(self):
        spec = TimestampSpec(timezone="Asia/Kolkata", formats=["%d.%m.%Y %H:%M:%S"])
        out, steps = parse_timestamp("01.10.2026 09:00:00", spec)
        self.assertEqual(out, "2026-10-01T03:30:00Z")
        self.assertEqual([s.step for s in steps], ["assume_zone:Asia/Kolkata", "to_utc"])
        iso = TimestampSpec(timezone="UTC", formats=["iso"])
        self.assertEqual(parse_timestamp("2026-10-01T09:00:00+05:30", iso)[0], "2026-10-01T03:30:00Z")
        out, steps = parse_timestamp("2026-10-01T03:30:00.987Z", iso)
        self.assertEqual(out, "2026-10-01T03:30:00Z")
        self.assertIn("truncate_subsecond", [s.step for s in steps])
        for bad in ("31.02.2026 10:00:00", "", "tomorrow"):
            with self.assertRaises(ValueError):
                parse_timestamp(bad, spec)

    def test_column_mapping_is_configurable_and_gives_identical_canonical_content(self):
        cfg = json.loads((MAPPING_DIR / "erp.lot_issue.v1.json").read_text(encoding="utf-8"))
        renames = {"BELNR": "DOC", "POSNR": "ITEM", "MOTOR_NO": "SERIAL_NO", "POSITION": "POS", "BEARING_LOT": "LOT", "BEARING_SERIAL": "BSN", "STEEL_LOT": "HEAT",
                   "VENDOR_ID": "VID", "VENDOR_NAME": "VNAME", "ISSUE_TS": "WHEN"}
        for spec in cfg["fields"].values():
            spec["source"] = [renames[s] for s in spec["source"]] if isinstance(spec["source"], list) else renames[spec["source"]]
        text = (B1 / "erp_lot_issue.csv").read_text(encoding="utf-8")
        head, _, rest = text.partition("\n")
        for old, new in renames.items():
            head = head.replace(old, new)
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            (Path(d) / "m.json").write_text(json.dumps(cfg), encoding="utf-8")
            data = (head + "\n" + rest).encode("utf-8")
            a = ingest(None, load_mapping(Path(d) / "m.json"), data=data)
        b = ingest(B1 / "erp_lot_issue.csv", load_mapping("erp.lot_issue.v1.json"))
        self.assertEqual([r.canonical.contentSha256 if r.canonical else None for r in a.records], [r.canonical.contentSha256 if r.canonical else None for r in b.records])
        self.assertNotEqual(a.mappingSha256, b.mappingSha256)

    def test_value_maps_never_pass_unmapped_values_through(self):
        f = ingest(B1 / "mes_assembly.csv", load_mapping("mes.assembly.v1.json"))
        row = next(r for r in f.records if r.sourceRecordId == "MES-000134")
        self.assertEqual(row.errors[0].code, "BAD_VALUE")
        self.assertIsNone(row.canonical)


class Parsing(unittest.TestCase):
    def mes(self, text, **kw):
        return ingest(None, load_mapping("mes.assembly.v1.json"), data=text.encode(kw.get("enc", "utf-8")), name="x.csv")

    HEAD = "EVENT_ID,MOTOR_SERIAL,EVENT_TIME,EVENT_CODE,ORDER_NO,ORDER_TYPE,SLOTS,SLOT,LOT,SERIAL,DISPOSITION,STATION,OPERATOR\n"

    def test_csv_structure_problems_are_reported_not_hidden(self):
        f = self.mes(self.HEAD + "E1,MTR-1001,2026-10-01T05:00:00Z,OPEN,WO-1,BUILD,DE;NDE,,,,,,\n\nE2,short\n")
        self.assertEqual(f.rows, 2)
        self.assertEqual(f.blankRowsSkipped, 1)
        self.assertEqual([r.outcome for r in f.records], [None, "REJECTED"])
        self.assertEqual(f.records[1].issues[0].code, "MALFORMED_ROW")
        self.assertIn("2 cells", f.records[1].issues[0].message)

    def test_missing_required_column_rejects_the_whole_file(self):
        f = self.mes("EVENT_ID,MOTOR_SERIAL,EVENT_TIME\nE1,MTR-1001,2026-10-01T05:00:00Z\n")
        self.assertTrue(any(i.code == "MISSING_COLUMN" for i in f.fileIssues))
        self.assertEqual(f.records, [])

    def test_unreadable_files_are_rejected_with_a_reason(self):
        self.assertEqual(self.mes("")  .fileIssues[0].code, "FILE_UNREADABLE")
        self.assertEqual(ingest(None, load_mapping("mes.assembly.v1.json"), data=b"\xff\xfe\x00bad").fileIssues[0].code, "FILE_UNREADABLE")
        self.assertEqual(self.mes("A,A\n1,2\n").fileIssues[0].code, "FILE_UNREADABLE")                       # duplicate header

    def test_utf8_bom_is_accepted(self):
        f = self.mes("﻿" + self.HEAD + "E1,MTR-1001,2026-10-01T05:00:00Z,OPEN,WO-1,BUILD,DE;NDE,,,,,,\n")
        self.assertEqual(f.fileIssues, [])
        self.assertIsNotNone(f.records[0].canonical)

    def test_json_problems(self):
        cfg = load_mapping("logistics.dispatch.v1.json")
        self.assertEqual(ingest(None, cfg, data=b'{"shipments": [{"a": 1, "a": 2}]}').fileIssues[0].code, "FILE_UNREADABLE")     # duplicate key
        self.assertEqual(ingest(None, cfg, data=b'{"shipments": [NaN]}').fileIssues[0].code, "FILE_UNREADABLE")
        self.assertEqual(ingest(None, cfg, data=b'{"other": []}').fileIssues[0].code, "FILE_UNREADABLE")
        good = {"shipment": {"id": "S1", "dispatchedAt": "2026-10-02T04:00:00Z"}, "unit": {"serial": "MTR-1001"}, "consignee": {"name": "c", "destination": "d"}}
        f = ingest(None, cfg, data=json.dumps({"shipments": [1, good]}).encode())
        self.assertEqual(f.records[0].issues[0].code, "MALFORMED_ROW")
        self.assertIsNotNone(f.records[1].canonical)
        missing = ingest(None, cfg, data=b'{"shipments": [{"shipment": {"id": "S1"}}]}')                       # a required path is absent from every record
        self.assertEqual(missing.fileIssues[0].code, "MISSING_COLUMN")

    def test_nested_json_paths_and_decimal_comma(self):
        f = ingest(B1 / "scada_signals.json", load_mapping("scada.station_signal.v1.json"))
        row = next(r for r in f.records if r.sourceRecordId == "S-00002")
        self.assertEqual(row.canonical.attributes["value"], 112.5)
        self.assertIn("decimal_comma", [s.step for s in row.steps])
        self.assertIsNone(row.canonical.motorSerial)

    def test_scada_range_unit_and_quality_checks(self):
        f = ingest(B1 / "scada_signals.json", load_mapping("scada.station_signal.v1.json"))
        self.assertEqual(next(r for r in f.records if r.sourceRecordId == "S-00004").errors[0].code, "BAD_VALUE")
        self.assertEqual(next(r for r in f.records if r.sourceRecordId == "S-00005").errors[0].code, "BAD_SIGNAL_QUALITY")

    def test_motor_serial_is_normalised_by_a_recorded_step_and_bad_serials_are_rejected(self):
        f = ingest(B1 / "erp_lot_issue.csv", load_mapping("erp.lot_issue.v1.json"))
        row = next(r for r in f.records if r.sourceRecordId == "4500014/10")
        self.assertEqual(row.canonical.motorSerial, "MTR-27009")
        self.assertIn(("motorSerial", "motor_serial"), [(s.field, s.step) for s in row.steps])
        bad = ingest(None, load_mapping("mes.assembly.v1.json"), data=(Parsing.HEAD + "E1,PUMP-7,2026-10-01T05:00:00Z,OPEN,WO-1,BUILD,DE,,,,,,\n").encode())
        self.assertEqual(bad.records[0].errors[0].code, "BAD_IDENTITY")


class Canonical(unittest.TestCase):
    def test_forbidden_assertions_cannot_enter_a_canonical_event(self):
        attrs = dict(shipmentId="S", customer="c", destination="d")
        ok = build_event(SourceSystem.LOGISTICS, "S", Kind.SHIPMENT_DISPATCHED, "MTR-1001", "2026-10-01T00:00:00Z", attrs)
        self.assertFalse(ok.independentlyVerified)
        for key in ("verified", "trusted", "clearance", "releaseEligible", "recallStatus", "currentReleaseEligible"):
            with self.assertRaises(ValidationError, msg=key):
                build_event(SourceSystem.LOGISTICS, "S", Kind.SHIPMENT_DISPATCHED, "MTR-1001", "2026-10-01T00:00:00Z", {**attrs, key: True})
        with self.assertRaises(ValidationError):
            CanonicalEvent(**{**ok.model_dump(), "independentlyVerified": True})
        with self.assertRaises(ValidationError):
            CanonicalEvent(**{**ok.model_dump(), "motorSerial": "PUMP-9"})

    def test_content_hash_changes_with_content_and_id_does_not(self):
        a = build_event(SourceSystem.LOGISTICS, "S", Kind.SHIPMENT_DISPATCHED, "MTR-1001", "2026-10-01T00:00:00Z", dict(shipmentId="S", customer="c", destination="d"))
        b = build_event(SourceSystem.LOGISTICS, "S", Kind.SHIPMENT_DISPATCHED, "MTR-1001", "2026-10-01T00:00:00Z", dict(shipmentId="S", customer="c", destination="e"))
        self.assertEqual(a.canonicalId, b.canonicalId)
        self.assertNotEqual(a.contentSha256, b.contentSha256)


class Outcomes(Fixture):
    """The batch-1 synthetic exports: every deliberate defect lands in the right bucket."""

    def test_summary_counts(self):
        s = self.report.summary
        self.assertEqual((s["records"], s["accepted"], s["acceptedForLedgerCapture"], s["acceptedStagedOnly"], s["rejected"], s["unresolved"]), (73, 37, 32, 5, 8, 28))
        self.assertEqual((s["ledgerEventsPlanned"], s["unitsToCreate"]), (45, 9))
        self.assertEqual(s["accepted"] + s["rejected"] + s["unresolved"], s["records"])

    def test_clean_motors_are_fully_accepted(self):
        for rid in ("MES-000101", "MES-000102", "MES-000103", "MES-000104"):
            self.assertEqual(self.disposition("MES", rid), "CAPTURE", rid)
        self.assertEqual(self.disposition("LOGISTICS", "SHP-9001"), "CAPTURE")
        self.assertEqual(self.disposition("QUALITY", "QI-00701"), "STAGE_ONLY")

    def test_declared_alias_resolves_but_a_lookalike_is_never_normalised(self):
        alias = next(r for r in self.files[0].records if r.sourceRecordId == "4500003/10")
        self.assertEqual(alias.outcome, "ACCEPTED")
        self.assertIn(("lot", "registry_resolve"), [(s.field, s.step) for s in alias.steps])
        self.assertIn("UNRESOLVED_LOT", self.codes("ERP", "4500015/10"))                    # 'br-310 ' is not BR-310
        self.assertEqual(self.disposition("ERP", "4500015/10"), "UNRESOLVED_UNRESOLVED_LOT")

    def test_unregistered_lot_leaves_erp_and_mes_unresolved_and_the_order_held(self):
        self.assertIn("UNRESOLVED_LOT", self.codes("ERP", "4500007/10"))
        self.assertIn("UNRESOLVED_LOT", self.codes("MES", "MES-000114"))
        for rid in ("MES-000113", "MES-000115"):
            self.assertIn("WORK_ORDER_GROUP_HELD", self.codes("MES", rid))
        self.assertIn("OBLIGATIONS_NOT_MET", self.codes("MES", "MES-000116"))

    def test_cross_source_lot_contradiction(self):
        self.assertIn("CONTRADICTORY_LOT", self.codes("ERP", "4500005/10"))
        self.assertIn("CONTRADICTORY_LOT", self.codes("MES", "MES-000110"))
        self.assertEqual(self.disposition("LOGISTICS", "SHP-9003"), "UNRESOLVED_MISSING_ASSEMBLY")

    def test_missing_upstream_record(self):
        self.assertIn("MISSING_UPSTREAM", self.codes("MES", "MES-000119"))

    def test_duplicates_exact_and_contradictory(self):
        erp = [r for r in self.files[0].records if r.sourceRecordId == "4500101/10"]
        self.assertEqual([r.disposition for r in erp], ["CAPTURE", "REJECTED_EXACT_DUPLICATE_IN_BATCH"])
        conflicting = [r for r in self.files[0].records if r.sourceRecordId == "4500102/20"]
        self.assertEqual({r.disposition for r in conflicting}, {"UNRESOLVED_CONTRADICTORY_DUPLICATE"})
        ship = [r for r in self.files[4].records if r.sourceRecordId == "SHP-9010"]
        self.assertEqual({r.disposition for r in ship}, {"UNRESOLVED_CONTRADICTORY_DUPLICATE"})

    def test_time_order_and_work_order_window(self):
        self.assertEqual(self.disposition("LOGISTICS", "SHP-9007"), "UNRESOLVED_TIME_ORDER")
        self.assertEqual(self.disposition("SCADA", "S-00007"), "UNRESOLVED_OUTSIDE_WORK_ORDER_WINDOW")

    def test_scada_identity_through_work_order_and_unknown_order(self):
        tied = next(r for r in self.files[2].records if r.sourceRecordId == "S-00002")
        self.assertEqual((tied.outcome, tied.motor), ("ACCEPTED", "MTR-27001"))
        self.assertIn(("motorSerial", "resolved_from_work_order"), [(s.field, s.step) for s in tied.steps])
        self.assertEqual(self.disposition("SCADA", "S-00006"), "UNRESOLVED_MISSING_IDENTITY")

    def test_unknown_motor_in_a_staged_only_record(self):
        self.assertEqual(self.disposition("QUALITY", "QI-00703"), "UNRESOLVED_UNKNOWN_MOTOR")

    def test_recorded_fail_before_shipment_is_a_warning_not_a_block(self):
        row = by_id(self.report, "LOGISTICS", "SHP-9008")
        self.assertEqual(row.outcome, "ACCEPTED")
        self.assertEqual([(i.code, i.severity) for i in row.issues], [("INSPECTION_FAILED_BEFORE_SHIPMENT", "WARNING"), ("HISTORICAL_SHIPMENT_RECORD", "WARNING")])

    def test_rejections_carry_field_level_reasons(self):
        self.assertEqual(self.disposition("ERP", "4500016/10"), "REJECTED_BAD_TIMESTAMP")
        self.assertEqual(self.disposition("MES", "MES-000133"), "REJECTED_MISSING_REQUIRED")
        self.assertEqual(self.disposition("MES", "MES-000134"), "REJECTED_BAD_VALUE")
        self.assertEqual(sum(1 for r in self.report.records if r.disposition == "REJECTED_MALFORMED_ROW"), 1)

    def test_every_record_has_exactly_one_outcome(self):
        self.assertTrue(all(r.outcome in ("ACCEPTED", "REJECTED", "UNRESOLVED") and r.disposition for r in self.report.records))


class PreviewAndImport(Fixture):
    def test_preview_writes_nothing(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            run(demo.BATCH1, ledger=Path(d) / "l.sqlite", staging=Path(d) / "s.sqlite", options=OPTS)
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_preview_against_an_existing_ledger_changes_neither_store(self):
        def state():
            app = Manufacturing(self.dir / "l.sqlite")
            try:
                ledger = app.db.execute(Manufacturing.FINGERPRINT_SQL).fetchone()[0]
            finally:
                app.close()
            db = sqlite3.connect(str(self.dir / "s.sqlite"))
            try:
                return ledger, [db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("source_files", "source_records", "transformations", "canonical_events", "runs", "dispositions")]
            finally:
                db.close()
        before = state()
        run(demo.BATCH2, ledger=self.dir / "l.sqlite", staging=self.dir / "s.sqlite", options=OPTS)
        self.assertEqual(before, state())

    def test_import_does_exactly_what_the_preview_showed(self):
        self.assertEqual([e.eventId for e in self.preview.plannedLedgerEvents], [e.eventId for e in self.report.plannedLedgerEvents])
        self.assertEqual([(r.disposition, r.ledgerEventIds) for r in self.preview.records], [(r.disposition, r.ledgerEventIds) for r in self.report.records])
        written = {m: [e["eventId"] for e in evs] for m, evs in ledger_events(self.dir / "l.sqlite").items()}
        planned = {}
        for e in self.report.plannedLedgerEvents:
            planned.setdefault(e.motor, []).append(e.eventId)
        self.assertEqual({m: sorted(v) for m, v in written.items()}, {m: sorted(v) for m, v in planned.items()})
        self.assertEqual(sum(len(v) for v in written.values()), 45)

    def test_ledger_accepted_everything_through_its_own_validation(self):
        self.assertEqual(count(self.dir / "l.sqlite", "SELECT COUNT(*) FROM rejections"), 0)
        self.assertEqual(count(self.dir / "l.sqlite", "SELECT COUNT(*) FROM events"), 45)
        app = Manufacturing(self.dir / "l.sqlite")
        try:
            app.snapshot()                                                               # re-verifies every hash chain and the capture documents
        finally:
            app.close()

    def test_unit_creation_and_shipment_import_are_opt_in(self):
        report, plan, _ = run(demo.BATCH1, options=Options())
        by = {r.recordId: r for r in report.records if r.system == "MES"}
        self.assertEqual(by["MES-000101"].disposition, "UNRESOLVED_UNKNOWN_MOTOR")
        self.assertEqual((plan.creates, plan.events), ([], []))
        cfg = json.loads((MAPPING_DIR / "logistics.dispatch.v1.json").read_text(encoding="utf-8"))
        cfg["capture"] = {}
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            (Path(d) / "m.json").write_text(json.dumps(cfg), encoding="utf-8")
            report, _, _ = run(demo.BATCH1[:2] + [Source("LOGISTICS", B1 / "logistics_dispatch.json", Path(d) / "m.json")], options=Options(create_units=True))
        self.assertEqual(by_id(report, "LOGISTICS", "SHP-9001").disposition, "UNRESOLVED_SHIPMENT_IMPORT_DISABLED")

    def test_work_orders_are_all_or_nothing(self):
        events = ledger_events(self.dir / "l.sqlite")
        for motor in ("MTR-27003", "MTR-27004", "MTR-27005", "MTR-27006"):
            kinds = {e["eventType"] for e in events[motor]}
            self.assertEqual(kinds, {"MATERIAL_ALLOCATED", "BEARING_MANUFACTURED"}, motor)          # only the ERP issues; no half-built order
        self.assertIn("WORK_ORDER_CLOSED", {e["eventType"] for e in events["MTR-27001"]})

    def test_imported_events_carry_a_provenance_reference_and_the_original_work_order_id(self):
        events = ledger_events(self.dir / "l.sqlite", "MTR-27001")["MTR-27001"]
        self.assertTrue(all(capture.parse_ref(e["evidenceRefs"][0]) for e in events))
        self.assertEqual({e["workOrderId"] for e in events if e["workOrderId"]}, {"WO-5001"})
        self.assertEqual(next(e for e in events if e["eventType"] == "WORK_ORDER_OPENED")["occurredAt"], "2026-10-01T05:00:00Z")      # the source's time, not a demo clock

    def test_staged_only_records_never_become_ledger_events(self):
        kinds = {e["eventType"] for evs in ledger_events(self.dir / "l.sqlite").values() for e in evs}
        self.assertFalse(kinds & {"INSPECTION_RECORDED", "SLOT_STATE_VERIFIED", "SLOT_ACCESS_EVIDENCE"})
        self.assertEqual(sum(1 for r in self.report.records if r.disposition == "STAGE_ONLY"), 5)


class Repeatability(Fixture):
    def fresh_copy(self):
        d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(d.cleanup)
        for n in ("l.sqlite", "s.sqlite"):
            shutil.copy(self.dir / n, Path(d.name) / n)
        return Path(d.name)

    def test_reimporting_the_same_files_writes_no_event_twice(self):
        d = self.fresh_copy()
        before = count(d / "l.sqlite", "SELECT COUNT(*) FROM events")
        report, plan, _ = run(demo.BATCH1, ledger=d / "l.sqlite", staging=d / "s.sqlite", options=OPTS, commit=True)
        self.assertEqual(count(d / "l.sqlite", "SELECT COUNT(*) FROM events"), before)
        self.assertEqual((len(plan.events), plan.creates, report.summary["acceptedAlreadyImported"]), (0, [], 38))
        self.assertEqual(count(d / "s.sqlite", "SELECT COUNT(*) FROM source_files"), 5)           # originals are not stored twice either
        self.assertEqual(count(d / "s.sqlite", "SELECT COUNT(*) FROM runs"), 2)                    # but the second run is on record

    def test_idempotency_survives_losing_the_staging_store(self):
        d = self.fresh_copy()
        (d / "s.sqlite").unlink()
        before = count(d / "l.sqlite", "SELECT COUNT(*) FROM events")
        _, plan, _ = run(demo.BATCH1, ledger=d / "l.sqlite", staging=d / "s2.sqlite", options=OPTS, commit=True)
        self.assertEqual((len(plan.events), count(d / "l.sqlite", "SELECT COUNT(*) FROM events")), (0, before))      # the references inside the ledger events decide

    def test_a_repeated_source_record_with_changed_content_is_a_contradiction_not_an_update(self):
        d = self.fresh_copy()
        report, plan, _ = run([Source("ERP", B1 / "erp_lot_issue.csv"), Source("MES", B1 / "mes_assembly.csv"), Source("MES", B2 / "mes_assembly.csv")],
                              ledger=d / "l.sqlite", staging=d / "s.sqlite", options=OPTS)
        resent = next(r for r in report.records if r.file == "mes_assembly.csv" and r.recordId == "MES-000102" and r.disposition != "ALREADY_IMPORTED")
        self.assertEqual(resent.disposition, "UNRESOLVED_CONTRADICTS_PRIOR_IMPORT")
        self.assertTrue(any(r.recordId == "MES-000102" and r.disposition == "ALREADY_IMPORTED" for r in report.records))

    def test_batch_two_completes_what_batch_one_could_not(self):
        d = self.fresh_copy()
        report, plan, _ = run(demo.BATCH2, ledger=d / "l.sqlite", staging=d / "s.sqlite", options=OPTS, commit=True)
        self.assertEqual(report.summary["ledgerEventsPlanned"], 12)
        events = ledger_events(d / "l.sqlite")
        self.assertEqual({e["eventType"] for e in events["MTR-27005"]} >= {"WORK_ORDER_CLOSED", "COMPONENT_INSTALLED"}, True)
        rework = [e for e in events["MTR-27001"] if e["workOrderId"] == "WO-5101"]
        self.assertEqual([e["eventType"] for e in rework], ["WORK_ORDER_OPENED", "COMPONENT_REMOVED", "COMPONENT_INSTALLED", "WORK_ORDER_CLOSED"])
        removal = next(e for e in rework if e["eventType"] == "COMPONENT_REMOVED")
        original = next(e for e in events["MTR-27001"] if e["eventType"] == "COMPONENT_INSTALLED" and e["payload"]["slot"] == "DE" and e["workOrderId"] == "WO-5001")
        self.assertEqual(removal["payload"]["endsInstallEventId"], original["eventId"])
        self.assertEqual(count(d / "l.sqlite", "SELECT COUNT(*) FROM rejections"), 0)

    def test_interrupted_earlier_import_is_detected_not_papered_over(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            app = Manufacturing(Path(d) / "l.sqlite")
            app.create_unit("MTR-27001")
            f = ingest(B1 / "erp_lot_issue.csv", load_mapping("erp.lot_issue.v1.json"))
            c = f.records[0].canonical
            capture.capture_event(app, "MTR-27001", "MATERIAL_ALLOCATED", "MATERIAL", dict(rawMaterialLot="STEEL-26-410", supplierId="SUP-NSB-01", supplierName="x"),
                                  occurred=c.occurredAt, evidence=[capture.import_ref(c.canonicalId, c.contentSha256)])             # only the first of the record's two events
            app.close()
            report, _, _ = run([Source("ERP", B1 / "erp_lot_issue.csv")], ledger=Path(d) / "l.sqlite", options=OPTS)
            self.assertEqual(by_id(report, "ERP", "4500001/10").disposition, "UNRESOLVED_PARTIAL_PRIOR_IMPORT")

    def test_a_plan_is_refused_if_the_ledger_moved_after_it_was_made(self):
        d = self.fresh_copy()
        src = [Source("ERP", B1 / "erp_lot_issue.csv"), Source("MES", B1 / "mes_assembly.csv"), Source("ERP", B2 / "erp_lot_issue.csv")]
        _, plan, _ = run(src, ledger=d / "l.sqlite", staging=d / "s.sqlite", options=OPTS)
        self.assertTrue(plan.events)
        other = Manufacturing(d / "l.sqlite")
        first = plan.events[0]
        capture.capture_event(other, first.motor, first.kind, first.role, first.payload, work_order=first.work_order, occurred=first.occurred)    # somebody else wrote first
        other.close()
        app = Manufacturing(d / "l.sqlite")
        try:
            before = app.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            with self.assertRaises(CaptureMismatch):
                execute(plan, app)
            self.assertEqual(app.db.execute("SELECT COUNT(*) FROM events").fetchone()[0], before)                                         # refused before writing
        finally:
            app.close()


class Provenance(Fixture):
    def test_original_bytes_rows_and_transformations_are_preserved(self):
        db = sqlite3.connect(str(self.dir / "s.sqlite"))
        try:
            for f in self.files:
                stored, sha, name = db.execute("SELECT content, sha256, name FROM source_files WHERE sha256=?", (f.sha256,)).fetchone()
                self.assertEqual(hashlib.sha256(stored).hexdigest(), sha)
                self.assertEqual(stored, next(s.path for s in demo.BATCH1 if s.path.name == name).read_bytes())
            self.assertEqual(db.execute("SELECT COUNT(*) FROM source_records").fetchone()[0], sum(f.rows for f in self.files))
            row = db.execute("SELECT raw_json FROM source_records WHERE file_sha256=? AND row_index=18", (self.files[0].sha256,)).fetchone()[0]
            self.assertIn("mtr 27009", row)                                                       # the verbatim original, before normalisation
            steps = db.execute("SELECT step, before, after FROM transformations WHERE file_sha256=? AND row_index=18 AND field='motorSerial'", (self.files[0].sha256,)).fetchall()
            self.assertEqual(steps, [("motor_serial", '"mtr 27009"', '"MTR-27009"')])
            canon = db.execute("SELECT canonical_json FROM canonical_events WHERE source_record_id='4500014/10'").fetchone()[0]
            self.assertEqual(json.loads(canon)["independentlyVerified"], False)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM dispositions").fetchone()[0], 73)
            self.assertEqual(db.execute("SELECT status FROM run_results").fetchone()[0], "COMPLETED")
        finally:
            db.close()

    def test_staging_is_append_only(self):
        st = Staging(self.dir / "s.sqlite")
        try:
            for table in ("source_files", "source_records", "transformations", "canonical_events", "runs", "run_results", "dispositions"):
                with self.assertRaises(sqlite3.DatabaseError, msg=table):
                    st.db.execute(f"DELETE FROM {table}")
                with self.assertRaises(sqlite3.DatabaseError, msg=table):
                    st.db.execute(f"UPDATE {table} SET rowid=rowid")
        finally:
            st.close()

    def test_ledger_event_ids_in_the_report_match_the_ledger(self):
        ids = {e["eventId"] for evs in ledger_events(self.dir / "l.sqlite").values() for e in evs}
        reported = {i for r in self.report.records for i in r.ledgerEventIds}
        self.assertEqual(reported, ids)

    def test_reports_are_written_as_json_and_csv(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            paths = report_mod.write_reports(self.report, d)
            data = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
            self.assertEqual(data["summary"]["records"], 73)
            self.assertIn("claims", data["disclaimer"].lower())
            conflicts = Path(paths["conflicts"]).read_text(encoding="utf-8")
            for word in ("CONTRADICTORY_LOT", "EXACT_DUPLICATE_IN_BATCH", "MISSING_UPSTREAM", "TIME_ORDER", "INSPECTION_FAILED_BEFORE_SHIPMENT"):
                self.assertIn(word, conflicts)
            self.assertGreater(len(Path(paths["validation"]).read_text(encoding="utf-8").splitlines()), 20)


class Safety(Fixture):
    def test_capture_is_byte_identical_to_the_existing_service_path(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            a, b = Manufacturing(Path(d) / "a.sqlite"), Manufacturing(Path(d) / "b.sqlite")
            for app in (a, b):
                app.create_unit("MTR-27001")
            payload = dict(rawMaterialLot="STEEL-26-410", supplierId="SUP-NSB-01", supplierName="x")
            via_service = a.event("MTR-27001", "MATERIAL_ALLOCATED", "MATERIAL", payload)
            via_layer = capture.capture_event(b, "MTR-27001", "MATERIAL_ALLOCATED", "MATERIAL", payload, evidence=["demo-record:MTR-27001:MATERIAL:1"])
            self.assertEqual(via_service, via_layer)
            self.assertEqual(a.db.execute("SELECT hash FROM events").fetchone()[0], b.db.execute("SELECT hash FROM events").fetchone()[0])
            a.close(); b.close()

    def test_the_dry_run_refuses_what_the_ledger_would_reject(self):
        self.assertIsNotNone(capture.dry_run_problem("MTR-27001", "MATERIAL_ALLOCATED", "MATERIAL", dict(rawMaterialLot="", supplierId="s", supplierName="n"), 1, "2026-10-01T00:00:00Z"))
        self.assertIsNotNone(capture.dry_run_problem("MTR-27001", "MOTOR_SHIPPED", "MES", {}, 1, "2026-10-01T00:00:00Z"))                # role may not record this type
        self.assertIsNotNone(capture.dry_run_problem("MTR-27001", "MATERIAL_ALLOCATED", "MATERIAL", dict(rawMaterialLot="a", supplierId="s", supplierName="n", trusted=True), 1, "2026-10-01T00:00:00Z"))
        self.assertIsNone(capture.dry_run_problem("MTR-27001", "MATERIAL_ALLOCATED", "MATERIAL", dict(rawMaterialLot="a", supplierId="s", supplierName="n"), 1, "2026-10-01T00:00:00Z"))

    def test_the_layer_never_uses_a_trusted_verification_or_the_ship_operation(self):
        used = {e.role for e in self.plan.events}
        self.assertTrue(used <= {"MATERIAL", "MES", "ASSY", "REWORK", "SHIP"})                    # never QA / HANDHELD (the trusted-verifier and observation sources)
        self.assertFalse({e.kind for e in self.plan.events} & {"SLOT_STATE_VERIFIED", "SLOT_ACCESS_EVIDENCE", "INSPECTION_RECORDED", "CAPTURE_EXCEPTION_RESOLVED"})
        self.assertEqual(count(self.dir / "l.sqlite", "SELECT COUNT(*) FROM app_ship_tickets"), 0)
        banned = ("record_historical_shipment_fixture", ".ship(", "TrustedAnchor", "export_anchor", "publish_candidate", ".snapshot(")
        for path in PACKAGE.glob("*.py"):
            if path.name == "demo.py":
                continue
            text = path.read_text(encoding="utf-8")
            for word in banned:
                self.assertNotIn(word, text, f"{path.name} mentions {word}")

    def test_imported_evidence_grants_no_clearance(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            shutil.copy(self.dir / "l.sqlite", Path(d) / "l.sqlite")
            evaluation = demo.evaluate(Path(d) / "l.sqlite")
        self.assertEqual(evaluation["ledgerRejections"], 0)
        self.assertEqual(evaluation["checkpointState"], "UNANCHORED")
        self.assertFalse(any(m["releaseEligible"] for m in evaluation["motors"].values()))
        self.assertEqual(evaluation["motors"]["MTR-27002"]["action"], "RECALL_HOLD")               # lot NSB-204 (alias of the recalled BR-204) installed at DE
        self.assertEqual(evaluation["motors"]["MTR-27008"]["action"], "RECALL_HOLD")               # shipped after a recorded FAIL; held by the recalled lot, not by the FAIL claim
        self.assertEqual(evaluation["motors"]["MTR-27003"]["action"], "RECALL_HOLD")               # incomplete / contradictory evidence stays held

    def test_new_imported_evidence_ends_a_current_checkpoint(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            db, cp = Path(d) / "l.sqlite", Path(d) / "c0.json"
            run(demo.BATCH1, ledger=db, staging=Path(d) / "s.sqlite", options=OPTS, commit=True)
            app = Manufacturing(db); app.announce("BR-204", ["DE"]); app.snapshot()
            publish_candidate(cp, export_anchor(app)); app.close()
            app = Manufacturing(db)
            self.assertEqual(app.snapshot(trusted_anchor=TrustedAnchor(cp, None))["checkpoint"]["state"], "ANCHORED_CURRENT")
            app.close()
            run(demo.BATCH2, ledger=db, staging=Path(d) / "s.sqlite", options=OPTS, commit=True)      # imports more evidence
            app = Manufacturing(db)
            try:
                snap = app.snapshot(trusted_anchor=TrustedAnchor(cp, None))
                self.assertEqual(snap["checkpoint"]["state"], "ANCHORED_PREFIX_ONLY")
                self.assertTrue(all(not v["currentReleaseEligible"] for v in snap["eligibility"].values()))
            finally:
                app.close()

    def test_an_erp_only_import_writes_material_events_and_nothing_else(self):
        registry = lots.LotRegistry.load(None)
        plan = make_plan([ingest(B1 / "erp_lot_issue.csv", load_mapping("erp.lot_issue.v1.json"))], World(registry), OPTS)
        self.assertTrue(all(e.role == "MATERIAL" for e in plan.events))                              # an ERP-only import writes material events and nothing else


class Cli(unittest.TestCase):
    def test_preview_then_import_through_the_command_line(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            src = [x for s in demo.BATCH1 for x in ("--source", f"{s.system}={s.path}")]
            quiet = contextlib.redirect_stdout(io.StringIO()); quiet.__enter__(); self.addCleanup(quiet.__exit__, None, None, None)
            self.assertEqual(cli_main(["preview", *src, "--create-units", "--historical-shipments", "--out", str(Path(d) / "p")]), 0)
            self.assertTrue((Path(d) / "p" / "import_report.json").is_file())
            self.assertFalse((Path(d) / "l.sqlite").exists())
            self.assertEqual(cli_main(["import", *src, "--create-units", "--historical-shipments", "--ledger", str(Path(d) / "l.sqlite"), "--staging", str(Path(d) / "s.sqlite"),
                                       "--out", str(Path(d) / "i")]), 0)
            self.assertEqual(count(Path(d) / "l.sqlite", "SELECT COUNT(*) FROM events"), 45)
            self.assertEqual(json.loads((Path(d) / "i" / "import_report.json").read_text(encoding="utf-8"))["mode"], "IMPORT")
            with self.assertRaises(SystemExit):
                cli_main(["import", *src])                                                   # an import needs a ledger and a staging path
            with self.assertRaises(SystemExit):
                cli_main(["preview", "--source", "PLM=x.csv"])


class Samples(unittest.TestCase):
    def test_committed_samples_are_exactly_what_the_generator_produces(self):
        for batch, files in generate.generate().items():
            for name, text in files.items():
                self.assertEqual((SAMPLES / batch / name).read_bytes(), text.encode("utf-8"), f"{batch}/{name}")

    def test_demo_is_reproducible_and_ends_in_the_expected_state(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            a = demo.scenario(Path(d) / "a")
            b = demo.scenario(Path(d) / "b")
            self.assertEqual(a["digests"], b["digests"])
            s = a["summaries"]
            self.assertEqual((s["2_import_batch1"]["ledgerEventsPlanned"], s["3_repeat_batch1"]["ledgerEventsPlanned"], s["4_import_batch2"]["ledgerEventsPlanned"]), (45, 0, 12))
            self.assertEqual(a["evaluation"]["ledgerEvents"], 57)
            self.assertEqual(a["evaluation"]["ledgerRejections"], 0)
            self.assertEqual(a["evaluation"]["motors"]["MTR-27001"]["reasons"], ["REPLACED_WITH_UNAFFECTED_LOT"])


if __name__ == "__main__":
    unittest.main()
