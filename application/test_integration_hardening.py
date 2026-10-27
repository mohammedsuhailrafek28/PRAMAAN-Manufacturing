"""PS10 integration hardening (lifecycle + data integration together). Run: python -B -m unittest application.test_integration_hardening -v

Adversarial regression tests for the three demonstrated or suspected interaction failures:
  1. a source time the ledger cannot take (2099, before the capture session, malformed, past the session end) must be refused or staged BEFORE capture:
     the shared application clock does not move and the motor is never blocked by a ledger rejection;
  2. ROLES versus ALL_ROLES: lifecycle machining / QC authorisation is checked against the motor's own source registry, and no existing permission broadens;
  3. imported shipment records are historical evidence: they never authorise a shipment and never bypass the ordinary shipment gate.
Also: duplicate imports, interrupted imports, and checkpoint freshness. SCADA and quality stay staged-only (no automatic lifecycle conversion).
"""
import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from . import lifecycle
from .anchors import TrustedAnchor, export_anchor, publish_candidate
from .dataintegration import capture, demo, importer
from .dataintegration.cli import main as cli_main
from .dataintegration.canonical import Kind
from .dataintegration.importer import CaptureMismatch, Source, run
from .dataintegration.planner import Options, Plan, Planned
from .dataintegration.staging import Staging
from .service import ALL_ROLES, LIFECYCLE_ROLES, ROLES, Manufacturing, ShipmentRefused
from pramaan_integration import LedgerBlocked, ValidationFailure   # noqa: E402

OPTS = Options(create_units=True, historical_shipments=True)
ERP_HEADER = "BELNR;POSNR;MOTOR_NO;POSITION;BEARING_LOT;BEARING_SERIAL;STEEL_LOT;VENDOR_ID;VENDOR_NAME;ISSUE_TS\n"
WINDOW_END = capture.DEFAULT_WINDOW[1]


def erp_file(dirpath, rows, name="erp.csv"):
    path = Path(dirpath) / name
    path.write_text(ERP_HEADER + "".join(f"{doc};10;{motor};DE;BR-310;;STEEL-26-518;SUP-KAV-02;Kaveri;{ts}\n" for doc, motor, ts in rows), encoding="utf-8", newline="\n")
    return path


def count(db, sql):
    con = sqlite3.connect(str(db))
    try:
        return con.execute(sql).fetchone()[0]
    finally:
        con.close()


def state(db):
    """(application clock, ledger events, ledger rejections, registered units)"""
    return (count(db, "SELECT at FROM app_clock"), count(db, "SELECT COUNT(*) FROM events"), count(db, "SELECT COUNT(*) FROM rejections"), count(db, "SELECT COUNT(*) FROM app_units"))


class Scratch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.dir = Path(self.tmp.name)
        self.ledger, self.staging = self.dir / "l.sqlite", self.dir / "s.sqlite"
        self.addCleanup(self.tmp.cleanup)

    def do_import(self, sources, **kw):
        return run(sources, ledger=self.ledger, staging=self.staging, options=kw.pop("options", OPTS), commit=True, **kw)


class SourceTimeBeforeCapture(Scratch):
    BAD = ["2099-01-01T10:00:00Z", "2028-01-01T00:00:00Z", "2025-12-31T23:59:59Z", "1999-12-31T00:00:00Z", "2026-10-10T08:00:01Z", "2026-10-11T08:00:00Z", "2026-10-01 00:00:00", "2026-10-01T00:00:00+05:30",
           "2026-10-01T00:00:00.5Z", "", None, "2026-13-01T00:00:00Z", "0000-00-00T00:00:00Z", 20261001, "9999-12-31T23:59:59Z"]

    def test_time_problem_table(self):
        clock = capture.DEFAULT_CLOCK
        for bad in self.BAD:
            self.assertIsNotNone(capture.time_problem(bad, clock), repr(bad))
        for good in ("2026-10-01T00:00:00Z", "2026-01-01T00:00:00Z", "2026-10-10T07:59:59Z", "2026-10-10T08:00:00Z"):         # anything up to the clock; never ahead of it
            self.assertIsNone(capture.time_problem(good, clock), good)

    def test_the_2099_record_is_refused_before_capture_and_nothing_moves(self):
        erp = erp_file(self.dir, [("4900000001", "MTR-9001", "01.01.2099 10:00:00")])
        preview, _, _ = run([Source("ERP", erp)], options=OPTS)
        report, plan, _ = self.do_import([Source("ERP", erp)])
        self.assertEqual(plan.events, [])
        self.assertEqual(plan.creates, [])
        for r in (preview, report):
            row = r.records[0]
            self.assertEqual(row.outcome, "UNRESOLVED")
            self.assertEqual(row.disposition, "UNRESOLVED_TIME_OUT_OF_WINDOW")
        self.assertEqual(state(self.ledger), ("2026-10-10T08:00:00Z", 0, 0, 0))                    # the shared clock never moved, no rejection, no unit
        app = Manufacturing(self.ledger)
        try:                                                                                           # nothing is blocked: a correct record for the same motor imports normally
            app.close()
            good = erp_file(self.dir, [("4900000002", "MTR-9001", "01.10.2026 10:00:00")], "good.csv")
            report, plan, _ = self.do_import([Source("ERP", good)])
            self.assertEqual(report.records[0].outcome, "ACCEPTED")
            self.assertEqual(count(self.ledger, "SELECT COUNT(*) FROM rejections"), 0)
        finally:
            pass
        app = Manufacturing(self.ledger)
        self.assertEqual(len(app.events("MTR-9001")), 2)
        app.close()

    def test_a_bad_time_next_to_good_records_does_not_disturb_them(self):
        erp = erp_file(self.dir, [("4900000001", "MTR-9001", "01.10.2026 10:00:00"), ("4900000002", "MTR-9001", "01.01.2099 10:00:00"), ("4900000003", "MTR-9002", "02.10.2026 10:00:00")])
        report, plan, _ = self.do_import([Source("ERP", erp)])
        self.assertEqual([r.outcome for r in report.records], ["ACCEPTED", "UNRESOLVED", "ACCEPTED"])
        clock, events, rejections, units = state(self.ledger)
        self.assertEqual((events, rejections, units), (4, 0, 2))
        self.assertLess(clock, "2026-10-11T00:00:00Z")                                                 # advanced by ticks only, never to 2099
        for motor in ("MTR-9001", "MTR-9002"):
            app = Manufacturing(self.ledger)
            self.assertTrue(app.events(motor))
            app.close()

    def test_capture_event_refuses_before_ticking_or_writing(self):
        app = Manufacturing(self.ledger)
        app.create_unit("MTR-9100")
        before = state(self.ledger)
        payload = dict(rawMaterialLot="STEEL-26-410", supplierId="SUP-NSB-01", supplierName="x")
        for bad in ("2099-01-01T10:00:00Z", "2025-01-01T00:00:00Z", "not a time", "2028-06-01T00:00:00Z"):
            with self.assertRaises(capture.CaptureRefused):
                capture.capture_event(app, "MTR-9100", "MATERIAL_ALLOCATED", "MATERIAL", payload, occurred=bad)
            self.assertEqual(state(self.ledger), before, bad)
        self.assertTrue(capture.capture_event(app, "MTR-9100", "MATERIAL_ALLOCATED", "MATERIAL", payload, occurred="2026-10-10T08:00:00Z"))
        self.assertEqual(len(app.events("MTR-9100")), 1)                                                # the motor still takes evidence
        app.close()

    def test_capture_window_edge_agrees_with_the_ledger(self):
        """The last clock value at which time_problem allows a capture must really be accepted by the ledger; one second later it must be refused by time_problem, not by the ledger."""
        app = Manufacturing(self.ledger)
        app.create_unit("MTR-9101")
        payload = dict(rawMaterialLot="STEEL-26-410", supplierId="SUP-NSB-01", supplierName="x")
        last, over = "2027-12-31T23:59:21Z", "2027-12-31T23:59:22Z"
        self.assertIsNone(capture.time_problem(last, last))
        self.assertIsNotNone(capture.time_problem(over, over))
        with app.db:
            app.db.execute("UPDATE app_clock SET at=?", (over,))
        before = state(self.ledger)
        with self.assertRaises(capture.CaptureRefused):
            capture.capture_event(app, "MTR-9101", "MATERIAL_ALLOCATED", "MATERIAL", payload, occurred=over)
        self.assertEqual(state(self.ledger), before)
        with app.db:
            app.db.execute("UPDATE app_clock SET at=?", (last,))
        event = capture.capture_event(app, "MTR-9101", "MATERIAL_ALLOCATED", "MATERIAL", payload, occurred=last)
        self.assertLessEqual(event["recordedAt"], WINDOW_END)
        self.assertEqual(count(self.ledger, "SELECT COUNT(*) FROM rejections"), 0)
        app.close()

    def test_default_window_is_what_create_unit_registers(self):
        app = Manufacturing(self.ledger)
        app.create_unit("MTR-9102")
        app.create_unit("MTR-9103", lifecycle=True)
        for motor in ("MTR-9102", "MTR-9103"):
            config = app.ledger._config(motor)
            for source in config["sources"]:
                self.assertEqual(capture.session_window(config, source), capture.DEFAULT_WINDOW)
        app.close()
        self.assertEqual(Manufacturing(self.dir / "fresh.sqlite").clock(), capture.DEFAULT_CLOCK)

    def test_execute_prechecks_every_event_before_creating_anything(self):
        app = Manufacturing(self.ledger)
        bad = Planned("MTR-9200", "MATERIAL_ALLOCATED", "MATERIAL", dict(rawMaterialLot="STEEL-26-410", supplierId="s", supplierName="n"), None, "2099-01-01T00:00:00Z",
                      "urn:pramaan:MTR-9200:MATERIAL:1", "0" * 32, "0" * 64, ("2099", 0, "x"))
        good = Planned("MTR-9201", "MATERIAL_ALLOCATED", "MATERIAL", dict(rawMaterialLot="STEEL-26-410", supplierId="s", supplierName="n"), None, "2026-10-10T08:00:00Z",
                       "urn:pramaan:MTR-9201:MATERIAL:1", "1" * 32, "1" * 64, ("2026", 0, "x"))
        before = state(self.ledger)
        with self.assertRaises(CaptureMismatch):
            importer.execute(Plan(files=[], creates=["MTR-9201", "MTR-9200"], events=[good, bad]), app)
        self.assertEqual(state(self.ledger), before)                                                    # not even the good event or the units
        app.close()

    def test_repeated_bad_imports_stay_inert(self):
        erp = erp_file(self.dir, [("4900000001", "MTR-9001", "01.01.2099 10:00:00")])
        digests = {self.do_import([Source("ERP", erp)])[0].digest() for _ in range(3)}
        self.assertEqual(len(digests), 1)
        self.assertEqual(state(self.ledger), ("2026-10-10T08:00:00Z", 0, 0, 0))

    def test_corrected_record_replaces_the_refused_one(self):
        erp = erp_file(self.dir, [("4900000001", "MTR-9001", "01.01.2099 10:00:00")])
        self.do_import([Source("ERP", erp)])
        fixed = erp_file(self.dir, [("4900000001", "MTR-9001", "01.10.2026 10:00:00")], "fixed.csv")        # same document id, corrected time
        report, _, _ = self.do_import([Source("ERP", fixed)])
        self.assertEqual(report.records[0].outcome, "ACCEPTED")
        self.assertEqual(count(self.ledger, "SELECT COUNT(*) FROM events"), 2)

    def test_staged_kinds_get_the_same_time_check(self):
        """Quality, SCADA and logistics records are staged (or captured) only if their time is plausible too."""
        work = self.dir / "b1"
        work.mkdir()
        for f in demo.B1.iterdir():
            text = f.read_text(encoding="utf-8")
            text = text.replace("2026-10-0", "2099-10-0").replace("0.10.2026", "0.10.2099").replace(".10.2026", ".10.2099")
            (work / f.name).write_text(text, encoding="utf-8", newline="\n")
        sources = [Source("ERP", work / "erp_lot_issue.csv"), Source("MES", work / "mes_assembly.csv"), Source("SCADA", work / "scada_signals.json"),
                   Source("QUALITY", work / "quality_inspections.tsv"), Source("LOGISTICS", work / "logistics_dispatch.json")]
        report, plan, _ = self.do_import(sources)
        accepted = [r for r in report.records if r.outcome == "ACCEPTED"]
        self.assertEqual(accepted, [], [(r.system, r.recordId, r.disposition) for r in accepted][:5])
        self.assertEqual(state(self.ledger)[1:], (0, 0, 0))
        self.assertEqual(count(self.staging, "SELECT COUNT(*) FROM dispositions WHERE outcome='ACCEPTED'"), 0)           # nothing staged as accepted either


class RolesAndAuthorisation(Scratch):
    EXPECTED_ROLES = {
        "MES": ("MES-SYSTEM", ["WORK_ORDER_OPENED", "WORK_ORDER_CLOSED"]), "ASSY": ("OP-ASSEMBLY-07", ["COMPONENT_INSTALLED"]),
        "REWORK": ("OP-REWORK-12", ["COMPONENT_REMOVED", "COMPONENT_INSTALLED"]), "QA": ("QA-INDEPENDENT-03", ["SLOT_STATE_VERIFIED", "SLOT_ACCESS_EVIDENCE", "INSPECTION_RECORDED"]),
        "HANDHELD": ("OP-OBSERVATION-21", ["SLOT_STATE_VERIFIED"]), "MATERIAL": ("SUPPLIER-INTAKE-04", ["MATERIAL_ALLOCATED", "BEARING_MANUFACTURED"]),
        "SHIP": ("DISPATCH-09", ["MOTOR_SHIPPED"])}

    def test_existing_permissions_are_exactly_what_they_were(self):
        self.assertEqual({k: (a, list(t)) for k, (a, t) in ROLES.items()}, {k: (a, list(t)) for k, (a, t) in self.EXPECTED_ROLES.items()})
        self.assertEqual(set(LIFECYCLE_ROLES), {"MACHINING", "QC"})
        self.assertEqual({k: v for k, v in ALL_ROLES.items() if k in ROLES}, dict(ROLES))
        self.assertEqual(ALL_ROLES["MACHINING"][1], ["MACHINING_RECORDED"])
        self.assertEqual(ALL_ROLES["QC"][1], ["QUALITY_INSPECTION_RECORDED"])
        self.assertNotIn("QUALITY_INSPECTION_RECORDED", sum((t for _, t in ROLES.values()), []))       # no old role gained a lifecycle permission
        self.assertNotIn("MACHINING_RECORDED", sum((t for _, t in ROLES.values()), []))

    def test_a_lifecycle_unit_grants_the_original_roles_the_same_permissions(self):
        app = Manufacturing(self.ledger)
        app.create_unit("MTR-9300")
        app.create_unit("MTR-9301", lifecycle=True)
        plain, life = app.ledger._config("MTR-9300"), app.ledger._config("MTR-9301")
        for role in ROLES:
            self.assertEqual(plain["sources"][f"{role}:MTR-9300"], life["sources"][f"{role}:MTR-9301"], role)
        self.assertEqual(set(life["sources"]) - {f"{r}:MTR-9301" for r in ROLES}, {"MACHINING:MTR-9301", "QC:MTR-9301"})
        self.assertEqual(life["coverage"]["trustedVerifierSources"], ["QA:MTR-9301"])                    # QC and MACHINING are never trusted verifiers
        app.close()

    def test_import_cannot_reach_lifecycle_roles_on_a_plain_unit(self):
        app = Manufacturing(self.ledger)
        app.create_unit("MTR-9302")
        before = state(self.ledger)
        payload = dict(componentType="SHAFT", componentId="SHAFT-1", operation="TURNING", machineId="LATHE-02", routingStepId="R10", drawingRef="DWG-1")
        with self.assertRaises(capture.CaptureRefused):
            capture.capture_event(app, "MTR-9302", "MACHINING_RECORDED", "MACHINING", payload, occurred="2026-10-10T08:00:00Z")
        self.assertEqual(state(self.ledger), before)                                                    # refused cleanly: no rejection, motor not blocked
        self.assertTrue(app.events("MTR-9302") == [])
        app.close()

    def test_lifecycle_unit_machining_through_the_import_path_only_with_the_machining_role(self):
        app = Manufacturing(self.ledger)
        app.create_unit("MTR-9303", lifecycle=True)
        payload = dict(componentType="SHAFT", componentId="SHAFT-1", operation="TURNING", machineId="LATHE-02", routingStepId="R10", drawingRef="DWG-1")
        for kind, role in (("MACHINING_RECORDED", "MES"), ("MACHINING_RECORDED", "QC"), ("MACHINING_RECORDED", "QA"), ("QUALITY_INSPECTION_RECORDED", "MACHINING"),
                           ("QUALITY_INSPECTION_RECORDED", "QA"), ("QUALITY_INSPECTION_RECORDED", "MES"), ("INSPECTION_RECORDED", "QC"), ("SLOT_STATE_VERIFIED", "QC"),
                           ("SLOT_STATE_VERIFIED", "MACHINING"), ("MACHINING_RECORDED", "NOPE")):
            self.assertIsNotNone(capture.dry_run_problem("MTR-9303", kind, role, payload, 1, "2026-10-10T08:00:00Z"), (kind, role))
            before = state(self.ledger)
            with self.assertRaises(capture.CaptureRefused):
                capture.capture_event(app, "MTR-9303", kind, role, payload, occurred="2026-10-10T08:00:00Z")
            self.assertEqual(state(self.ledger), before, (kind, role))
        self.assertIsNone(capture.dry_run_problem("MTR-9303", "MACHINING_RECORDED", "MACHINING", payload, 1, "2026-10-10T08:00:00Z"))
        written = capture.capture_event(app, "MTR-9303", "MACHINING_RECORDED", "MACHINING", payload, occurred="2026-10-10T08:00:00Z")
        self.assertEqual(written["actorId"], "OP-MACHINING-05")
        self.assertEqual(len(app.events("MTR-9303")), 1)
        app.close()

    def test_lifecycle_reference_keys_are_not_smuggled_into_other_event_types(self):
        """The pinned ledger applies the lifecycle reference rule to any payload carrying these keys; a bad reference is a permanent rejection. The import layer refuses them first."""
        base = dict(rawMaterialLot="STEEL-26-410", supplierId="SUP-NSB-01", supplierName="x")
        for key, value in (("subjectEventIds", ["urn:x:1"]), ("previousOperationEventId", "urn:x:1")):
            problem = capture.dry_run_problem("MTR-9400", "MATERIAL_ALLOCATED", "MATERIAL", {**base, key: value}, 1, "2026-10-10T08:00:00Z")
            self.assertIn("reserved for lifecycle", problem or "")
        self.assertIsNone(capture.dry_run_problem("MTR-9400", "MATERIAL_ALLOCATED", "MATERIAL", base, 1, "2026-10-10T08:00:00Z"))

    def test_the_import_planner_never_uses_a_lifecycle_or_verifier_role(self):
        report, plan, _ = self.do_import(demo.BATCH2)
        self.assertTrue({e.role for e in plan.events} <= {"MATERIAL", "MES", "ASSY", "REWORK", "SHIP"})
        self.assertFalse({e.kind for e in plan.events} & {"MACHINING_RECORDED", "QUALITY_INSPECTION_RECORDED", "INSPECTION_RECORDED", "SLOT_STATE_VERIFIED", "SLOT_ACCESS_EVIDENCE"})

    def test_lifecycle_and_import_share_a_ledger(self):
        """A lifecycle unit (machining + quality claims) and imported units live in one ledger; each keeps working and neither changes the other."""
        app = Manufacturing(self.ledger)
        app.create_unit("MTR-94001", lifecycle=True)
        m = app.machine("MTR-94001", "SHAFT", "SHAFT-94001", "TURNING", "LATHE-02", "R10", "DWG-SH-100 rev B")
        app.inspect_quality("MTR-94001", "DIMENSIONAL", [m["eventId"]], "QP-SHAFT-01", "PASS", ["SHAFT"])
        app.close()
        report, plan, _ = self.do_import(demo.BATCH1)
        self.assertEqual(count(self.ledger, "SELECT COUNT(*) FROM rejections"), 0)
        app = Manufacturing(self.ledger)
        self.assertEqual(len(app.events("MTR-94001")), 2)
        self.assertEqual(lifecycle.violations(app.events("MTR-94001")), [])
        for motor in [r[0] for r in app.db.execute("SELECT serial FROM app_units WHERE serial LIKE 'MTR-27%'")][:3]:
            self.assertTrue(app.events(motor))
        app.close()


class StagedOnlyStaysStaged(Scratch):
    def test_quality_and_scada_never_become_ledger_events(self):
        report, plan, _ = self.do_import(demo.BATCH2)
        quality = [r for r in report.records if r.system in ("QUALITY", "SCADA") and r.outcome == "ACCEPTED"]
        self.assertTrue(quality)
        self.assertTrue(all(r.disposition == "STAGE_ONLY" or "STAGE" in r.disposition for r in quality), {r.disposition for r in quality})
        kinds = {r[0] for r in sqlite3.connect(str(self.ledger)).execute("SELECT json_extract(native,'$.eventType') FROM events")}
        self.assertFalse(kinds & {"MACHINING_RECORDED", "QUALITY_INSPECTION_RECORDED", "INSPECTION_RECORDED", "SLOT_STATE_VERIFIED"})
        self.assertGreater(count(self.staging, "SELECT COUNT(*) FROM canonical_events"), 0)
        banned = ("QUALITY_INSPECTION_RECORDED", "MACHINING_RECORDED", "\"QC\"", "'QC'", "inspect_quality", ".machine(")
        for path in Path(capture.__file__).parent.glob("*.py"):
            if path.name == "capture.py":
                continue
            text = path.read_text(encoding="utf-8")
            for word in banned:
                self.assertNotIn(word, text, f"{path.name} mentions {word}")


class HistoricalShipments(Scratch):
    def setUp(self):
        super().setUp()
        self.report, self.plan, _ = self.do_import(demo.BATCH1)
        app = Manufacturing(self.ledger)
        self.shipped = [(m, [e for e in app.events(m) if e["eventType"] == "MOTOR_SHIPPED"]) for (m,) in app.db.execute("SELECT serial FROM app_units ORDER BY serial").fetchall()]
        self.shipped = [(m, e) for m, e in self.shipped if e]
        app.close()

    def test_imported_shipments_declare_themselves_historical(self):
        self.assertTrue(self.shipped)
        for motor, events in self.shipped:
            for e in events:
                self.assertIn(capture.HISTORICAL_SHIPMENT_REF, e["evidenceRefs"])
                self.assertTrue(any(capture.parse_ref(r) for r in e["evidenceRefs"]))
        rows = [r for r in self.report.records if r.system == "LOGISTICS" and r.outcome == "ACCEPTED" and r.ledgerEventIds]
        self.assertTrue(rows)
        for r in rows:
            self.assertIn("HISTORICAL_SHIPMENT_RECORD", {i.code for i in r.issues})
        app = Manufacturing(self.ledger)
        for motor, _ in self.shipped:
            for s in lifecycle.backward(app.events(motor))["shipments"]:
                self.assertTrue(s["historicalImport"])
        app.close()

    def test_an_imported_shipment_authorises_nothing(self):
        app = Manufacturing(self.ledger)
        try:
            self.assertEqual(count(self.ledger, "SELECT COUNT(*) FROM app_ship_tickets"), 0)
            for motor, _ in self.shipped:
                with self.assertRaises(ValidationFailure) as ctx:
                    app.ship(motor)                                                                        # the ordinary path still refuses: it is recorded already
                self.assertNotIsInstance(ctx.exception, ShipmentRefused)
            app.announce("BR-204", ["DE"])
            snap = app.snapshot()
            self.assertEqual(snap["checkpoint"]["state"], "UNANCHORED")
            self.assertFalse(any(v["currentReleaseEligible"] for v in snap["eligibility"].values()))
            self.assertEqual(count(self.ledger, "SELECT COUNT(*) FROM app_ship_tickets"), 0)
            shipped = {m for m, _ in self.shipped}
            others = [m for (m,) in app.db.execute("SELECT serial FROM app_units").fetchall() if m not in shipped]
            self.assertTrue(others)
            for motor in others:                                                                           # history elsewhere in the ledger opens no door for an unshipped motor
                with self.assertRaises(ValidationFailure):
                    app.ship(motor)
            self.assertEqual(count(self.ledger, "SELECT COUNT(*) FROM events WHERE json_extract(native,'$.eventType')='MOTOR_SHIPPED'"), len(self.shipped))
            self.assertEqual(count(self.ledger, "SELECT COUNT(*) FROM rejections"), 0)
        finally:
            app.close()

    def test_no_shipment_history_without_explicit_opt_in(self):
        """Disabled by default: the bundled mapping, the options and the CLI all leave logistics records unresolved."""
        self.tmp2 = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp2.cleanup)
        mapping = json.loads((importer.MAPPING_DIR / importer.DEFAULT_MAPPINGS["LOGISTICS"]).read_text(encoding="utf-8"))
        self.assertIs(mapping["capture"]["historicalShipments"], False)
        db, st = Path(self.tmp2.name) / "l.sqlite", Path(self.tmp2.name) / "s.sqlite"
        report, plan, _ = run(demo.BATCH1, ledger=db, staging=st, options=Options(create_units=True), commit=True)
        self.assertNotIn("MOTOR_SHIPPED", {e.kind for e in plan.events})
        self.assertEqual(count(db, "SELECT COUNT(*) FROM events WHERE json_extract(native,'$.eventType')='MOTOR_SHIPPED'"), 0)
        rows = [r for r in report.records if r.system == "LOGISTICS" and r.recordId in ("SHP-9001", "SHP-9002", "SHP-9008")]
        self.assertEqual({r.disposition for r in rows}, {"UNRESOLVED_SHIPMENT_IMPORT_DISABLED"})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            src = [f"--source={s.system}={s.path}" for s in demo.BATCH1]
            cli_main(["preview", *src, "--create-units"])
        self.assertIn("SHIPMENT_IMPORT_DISABLED", out.getvalue())
        self.assertTrue(demo.OPTIONS.historical_shipments)                                                  # only the synthetic demonstration opts in, explicitly

    def test_a_custom_mapping_can_opt_in_explicitly_and_still_grants_nothing(self):
        self.tmp2 = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp2.cleanup)
        mapping = json.loads((importer.MAPPING_DIR / importer.DEFAULT_MAPPINGS["LOGISTICS"]).read_text(encoding="utf-8"))
        mapping["capture"]["historicalShipments"] = True
        custom = Path(self.tmp2.name) / "logistics.optin.json"
        custom.write_text(json.dumps(mapping), encoding="utf-8")
        sources = [Source("LOGISTICS", s.path, custom) if s.system == "LOGISTICS" else s for s in demo.BATCH1]
        db, st = Path(self.tmp2.name) / "l.sqlite", Path(self.tmp2.name) / "s.sqlite"
        run(sources, ledger=db, staging=st, options=Options(create_units=True), commit=True)
        self.assertGreater(count(db, "SELECT COUNT(*) FROM events WHERE json_extract(native,'$.eventType')='MOTOR_SHIPPED'"), 0)
        self.assertEqual(count(db, "SELECT COUNT(*) FROM app_ship_tickets"), 0)

    def test_a_native_shipment_is_not_marked_historical(self):
        refs = {r for r in sum((e["evidenceRefs"] for _, es in self.shipped for e in es), [])}
        self.assertFalse({r for r in refs if r.startswith("demo-record:")})
        native = {"evidenceRefs": ["demo-record:MTR-1:SHIP:1"]}
        self.assertFalse(lifecycle._historical(native))
        self.assertFalse(lifecycle._historical({}))


class DuplicatesInterruptionsAndCheckpoints(Scratch):
    def test_duplicate_imports_write_nothing_and_stay_unblocked(self):
        first, _, _ = self.do_import(demo.BATCH2)
        before = state(self.ledger)
        for _ in range(2):
            again, plan, _ = self.do_import(demo.BATCH2)
            self.assertEqual(plan.events, [])
        self.assertEqual(state(self.ledger)[1:], before[1:])
        self.assertEqual(count(self.ledger, "SELECT COUNT(DISTINCT id) FROM events"), count(self.ledger, "SELECT COUNT(*) FROM events"))

    def test_contradicting_resend_is_refused_without_touching_the_ledger(self):
        erp = erp_file(self.dir, [("4900000001", "MTR-9001", "01.10.2026 10:00:00")])
        self.do_import([Source("ERP", erp)])
        before = state(self.ledger)
        changed = erp_file(self.dir, [("4900000001", "MTR-9001", "02.10.2026 10:00:00")], "changed.csv")
        report, plan, _ = self.do_import([Source("ERP", changed)])
        self.assertEqual(report.records[0].disposition, "UNRESOLVED_CONTRADICTS_PRIOR_IMPORT")
        self.assertEqual(state(self.ledger), before)

    def test_interrupted_import_resumes_without_duplicates_or_blocking(self):
        clean_db = self.dir / "clean.sqlite"
        run(demo.BATCH1, ledger=clean_db, staging=self.dir / "clean-s.sqlite", options=OPTS, commit=True)
        total = count(clean_db, "SELECT COUNT(*) FROM events")
        original = importer.capture_event
        for stop in (0, 1, 2, 5, total // 2, total - 1):
            db, st = self.dir / f"i{stop}.sqlite", self.dir / f"i{stop}-s.sqlite"
            calls = {"n": 0}

            def dying(*a, **k):
                if calls["n"] >= stop:
                    raise crash("simulated crash")
                calls["n"] += 1
                return original(*a, **k)
            crash = KeyboardInterrupt if stop % 2 == 0 else RuntimeError                                   # a killed process (no handler runs) and an ordinary failure
            with mock.patch.object(importer, "capture_event", dying):
                with self.assertRaises(crash):
                    run(demo.BATCH1, ledger=db, staging=st, options=OPTS, commit=True)
            self.assertEqual(count(db, "SELECT COUNT(*) FROM events"), stop)
            self.assertEqual(count(db, "SELECT COUNT(*) FROM rejections"), 0)
            for _ in range(2):                                                                             # resume twice: idempotent
                report, plan, _ = run(demo.BATCH1, ledger=db, staging=st, options=OPTS, commit=True)
            self.assertEqual(count(db, "SELECT COUNT(*) FROM rejections"), 0, stop)
            self.assertEqual(count(db, "SELECT COUNT(DISTINCT id) FROM events"), count(db, "SELECT COUNT(*) FROM events"), stop)
            self.assertLessEqual(count(db, "SELECT COUNT(*) FROM events"), total, stop)
            partial = [r for r in report.records if r.disposition == "UNRESOLVED_PARTIAL_PRIOR_IMPORT"]
            if not partial:                                                                                 # cut at a record boundary: resumes to exactly the clean result
                self.assertEqual(count(db, "SELECT COUNT(*) FROM events"), total, stop)
            if crash is RuntimeError:
                self.assertEqual(count(st, "SELECT status FROM run_results ORDER BY run_id LIMIT 1"), "FAILED", stop)
            else:                                                                                           # the killed run is visible as a run that never finished
                self.assertEqual(count(st, "SELECT COUNT(*) FROM runs r LEFT JOIN run_results x ON x.run_id=r.run_id WHERE x.run_id IS NULL"), 1, stop)
            self.assertEqual(count(st, "SELECT status FROM run_results ORDER BY run_id DESC LIMIT 1"), "COMPLETED", stop)
            app = Manufacturing(db)                                                                         # the hash chain still verifies and every motor reads
            for (m,) in app.db.execute("SELECT serial FROM app_units").fetchall():
                app.events(m)
            app.close()

    def test_interruption_after_unit_creation_before_any_event(self):
        original = importer.capture_event
        with mock.patch.object(importer, "capture_event", side_effect=KeyboardInterrupt("simulated crash")):
            with self.assertRaises(KeyboardInterrupt):
                run(demo.BATCH1, ledger=self.ledger, staging=self.staging, options=OPTS, commit=True)
        self.assertEqual(count(self.ledger, "SELECT COUNT(*) FROM events"), 0)
        self.assertGreater(count(self.ledger, "SELECT COUNT(*) FROM app_units"), 0)
        report, plan, _ = run(demo.BATCH1, ledger=self.ledger, staging=self.staging, options=OPTS, commit=True)
        self.assertEqual(plan.creates, [])                                                                 # units already exist; none created twice
        self.assertEqual(count(self.ledger, "SELECT COUNT(*) FROM rejections"), 0)
        self.assertGreater(count(self.ledger, "SELECT COUNT(*) FROM events"), 0)

    def test_checkpoint_freshness(self):
        self.do_import(demo.BATCH1)
        cp = self.dir / "c0.json"
        app = Manufacturing(self.ledger); app.announce("BR-204", ["DE"]); app.snapshot()
        publish_candidate(cp, export_anchor(app)); app.close()
        current = lambda: self._state(cp)
        self.assertEqual(current(), "ANCHORED_CURRENT")
        self.do_import(demo.BATCH1)                                                                         # a repeat writes nothing: the checkpoint stays current
        self.assertEqual(current(), "ANCHORED_CURRENT")
        bad = erp_file(self.dir, [("4900000099", "MTR-27001", "01.01.2099 10:00:00")])
        self.do_import([Source("ERP", bad)])                                                                # a refused record writes nothing either
        self.assertEqual(current(), "ANCHORED_CURRENT")
        self.assertEqual(count(self.ledger, "SELECT COUNT(*) FROM rejections"), 0)
        self.do_import(demo.BATCH2)                                                                         # genuinely new evidence ends it
        self.assertEqual(current(), "ANCHORED_PREFIX_ONLY")
        app = Manufacturing(self.ledger)
        try:
            snap = app.snapshot(trusted_anchor=TrustedAnchor(cp, None))
            self.assertFalse(any(v["currentReleaseEligible"] for v in snap["eligibility"].values()))
            with self.assertRaises(ValidationFailure):                                                      # a stale checkpoint opens no shipment
                app.ship(next(m for (m,) in app.db.execute("SELECT serial FROM app_units").fetchall() if not any(e["eventType"] == "MOTOR_SHIPPED" for e in app.events(m))), trusted_anchor=TrustedAnchor(cp, None))
        finally:
            app.close()

    def _state(self, cp):
        app = Manufacturing(self.ledger)
        try:
            return app.snapshot(trusted_anchor=TrustedAnchor(cp, None))["checkpoint"]["state"]
        finally:
            app.close()

    def test_interrupted_import_after_a_checkpoint_withdraws_it(self):
        self.do_import(demo.BATCH1)
        cp = self.dir / "c0.json"
        app = Manufacturing(self.ledger); app.announce("BR-204", ["DE"]); app.snapshot()
        publish_candidate(cp, export_anchor(app)); app.close()
        original = importer.capture_event
        calls = {"n": 0}

        def dying(*a, **k):
            if calls["n"] >= 1:
                raise KeyboardInterrupt("simulated crash")
            calls["n"] += 1
            return original(*a, **k)
        with mock.patch.object(importer, "capture_event", dying):
            with self.assertRaises(KeyboardInterrupt):
                run(demo.BATCH2, ledger=self.ledger, staging=self.staging, options=OPTS, commit=True)
        self.assertEqual(self._state(cp), "ANCHORED_PREFIX_ONLY")


class LedgerLifecycleReferenceScope(Scratch):
    """A3: the lifecycle reference rules apply to the two lifecycle event types only. Legacy types keep their baseline validation."""
    LEGACY = dict(rawMaterialLot="STEEL-26-410", supplierId="SUP-NSB-01", supplierName="x")

    def test_legacy_events_with_lifecycle_looking_keys_are_still_accepted(self):
        app = Manufacturing(self.ledger)
        for n, extra in enumerate(({"subjectEventIds": ["urn:x:1"]}, {"previousOperationEventId": "urn:x:1"}, {"subjectEventIds": "not-a-list"},
                                   {"subjectEventIds": [], "previousOperationEventId": 7})):
            motor = f"MTR-9{600 + n}"
            app.create_unit(motor)
            event = app.event(motor, "MATERIAL_ALLOCATED", "MATERIAL", {**self.LEGACY, **extra})
            self.assertEqual(app.events(motor)[0]["eventId"], event["eventId"])
        app.announce("BR-204", ["DE"])
        snap = app.snapshot()                                                                                 # the snapshot's watermark pass reads every motor without LedgerBlocked
        self.assertEqual(len(snap["decisions"]), 4)
        self.assertEqual(count(self.ledger, "SELECT COUNT(*) FROM rejections"), 0)
        app.close()

    def test_malformed_lifecycle_references_are_still_rejected(self):
        app = Manufacturing(self.ledger)
        machining = dict(componentType="SHAFT", componentId="SHAFT-1", operation="TURNING", machineId="LATHE-02", routingStepId="R10", drawingRef="DWG-1")
        inspection = dict(inspectionType="DIMENSIONAL", result="PASS", protocolId="QP-1", inspectorQualifiedFor=["SHAFT"])
        motors = [f"MTR-9{700 + n}" for n in range(8)]
        for motor in motors:
            app.create_unit(motor, lifecycle=True)
        m0, m1, m2, m3, m4, m5, m6, m7 = motors
        good = app.event(m1, "MACHINING_RECORDED", "MACHINING", machining)
        material = app.event(m2, "MATERIAL_ALLOCATED", "MATERIAL", self.LEGACY)
        bad = [(m0, "MACHINING_RECORDED", "MACHINING", {**machining, "previousOperationEventId": "urn:x:unknown"}),                  # unknown previous operation
               (m3, "QUALITY_INSPECTION_RECORDED", "QC", {**inspection, "subjectEventIds": ["urn:x:unknown"]}),                      # unknown inspected event
               (m2, "QUALITY_INSPECTION_RECORDED", "QC", {**inspection, "subjectEventIds": [material["eventId"]]}),                  # inspected event is not a machining operation
               (m4, "QUALITY_INSPECTION_RECORDED", "QC", {**inspection, "subjectEventIds": [good["eventId"]]}),                      # machining event of ANOTHER motor
               (m6, "MACHINING_RECORDED", "MACHINING", {**machining, "previousOperationEventId": good["eventId"]})]                  # previous operation of another motor
        for motor, kind, role, payload in bad:
            with self.assertRaises(ValidationFailure):
                app.event(motor, kind, role, payload)
        first = app.event(m5, "MACHINING_RECORDED", "MACHINING", machining)                                                          # a correct sequence on its own motor is accepted
        second = app.event(m5, "MACHINING_RECORDED", "MACHINING", {**machining, "operation": "GRINDING", "routingStepId": "R20", "previousOperationEventId": first["eventId"]})
        app.event(m5, "QUALITY_INSPECTION_RECORDED", "QC", {**inspection, "subjectEventIds": [second["eventId"]]})
        self.assertEqual(len(app.events(m5)), 3)
        first7 = app.event(m7, "MACHINING_RECORDED", "MACHINING", machining)
        with self.assertRaises(ValidationFailure):                                                                                    # one component per operation sequence
            app.event(m7, "MACHINING_RECORDED", "MACHINING", {**machining, "componentId": "SHAFT-2", "previousOperationEventId": first7["eventId"]})
        app.close()

    def test_ledger_helpers_ignore_references_of_legacy_types(self):
        from pramaan_integration import ledger as led
        legacy = dict(eventType="MATERIAL_ALLOCATED", payload=dict(subjectEventIds=["a"], previousOperationEventId="b"))
        self.assertEqual((led.previous_operation(legacy), led.lifecycle_refs(legacy)), (None, []))
        for kind in led.LIFECYCLE_TYPES:
            e = dict(eventType=kind, payload=dict(subjectEventIds=["a", 1], previousOperationEventId="b"))
            self.assertEqual((led.previous_operation(e), led.lifecycle_refs(e)), ("b", ["a"]))
        self.assertEqual(set(led.LIFECYCLE_TYPES), {"MACHINING_RECORDED", "QUALITY_INSPECTION_RECORDED"})


class NoClockRatchet(Scratch):
    def test_future_dated_imports_never_move_the_clock(self):
        for n in range(25):
            erp = erp_file(self.dir, [(f"49{n:08d}", "MTR-9001", "10.10.2026 13:30:01"), (f"48{n:08d}", "MTR-9002", "11.10.2026 13:30:00"),
                                      (f"47{n:08d}", "MTR-9003", "01.01.2027 00:00:00"), (f"46{n:08d}", "MTR-9004", "01.01.2099 00:00:00")], f"f{n}.csv")
            report, plan, _ = self.do_import([Source("ERP", erp)])
            self.assertEqual({r.disposition for r in report.records}, {"UNRESOLVED_TIME_OUT_OF_WINDOW"})
        self.assertEqual(state(self.ledger), ("2026-10-10T08:00:00Z", 0, 0, 0))

    def test_the_clock_moves_only_by_its_own_ticks(self):
        """Repeated and new imports advance the clock by exactly one 30 s tick per event written, whatever the source times say."""
        from datetime import datetime, timedelta
        fmt = "%Y-%m-%dT%H:%M:%SZ"
        at = lambda text: datetime.strptime(text, fmt)

        def clock_and_events():
            c = state(self.ledger)
            return c[0], c[1]
        self.do_import(demo.BATCH1)
        c1, e1 = clock_and_events()
        self.assertEqual(at(c1) - at(capture.DEFAULT_CLOCK), timedelta(seconds=30 * e1))
        for _ in range(5):
            self.do_import(demo.BATCH1)                                                                   # repeats write nothing and tick nothing
        self.assertEqual(clock_and_events(), (c1, e1))
        self.do_import(demo.BATCH2)
        c2, e2 = clock_and_events()
        self.assertEqual(at(c2) - at(c1), timedelta(seconds=30 * (e2 - e1)))
        self.assertLess(c2, "2026-10-11T00:00:00Z")

    def test_a_record_dated_exactly_at_the_clock_is_accepted_and_one_second_later_is_not(self):
        erp = erp_file(self.dir, [("4900000001", "MTR-9001", "10.10.2026 13:30:00"), ("4900000002", "MTR-9002", "10.10.2026 13:30:01")])
        report, plan, _ = self.do_import([Source("ERP", erp)])
        self.assertEqual([r.outcome for r in report.records], ["ACCEPTED", "UNRESOLVED"])
        self.assertEqual(report.records[1].disposition, "UNRESOLVED_TIME_OUT_OF_WINDOW")
        self.assertEqual(count(self.ledger, "SELECT COUNT(*) FROM rejections"), 0)

    def test_capture_event_never_asks_the_clock_to_jump(self):
        app = Manufacturing(self.ledger)
        app.create_unit("MTR-9800")
        seen = []
        real = app.tick
        app.tick = lambda minimum=None: (seen.append(minimum), real(minimum))[1]
        capture.capture_event(app, "MTR-9800", "MATERIAL_ALLOCATED", "MATERIAL", dict(rawMaterialLot="STEEL-26-410", supplierId="SUP-NSB-01", supplierName="x"), occurred="2026-10-01T00:00:00Z")
        self.assertEqual(seen, [None])
        app.close()


if __name__ == "__main__":
    unittest.main()
