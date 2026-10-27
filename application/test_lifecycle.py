"""PS10 manufacturing lifecycle completeness (synthetic). Run: python -B -m unittest application.test_lifecycle -v

Machining and quality-inspection events are recorded claims in the same hash-chained, checkpoint-covered ledger as every other event.
They carry identity, source, time and references, appear in one chronology and in forward/backward traces, are rejected when malformed, and do not
change what the recall evaluator decides. No test here grants, infers or verifies an inspection result or a clearance.
"""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from . import lifecycle
from .anchors import TrustedAnchor, export_anchor, publish_candidate
from .service import ALL_ROLES, ROLES, Manufacturing    # importing the service puts integration/ on sys.path
from .test_stale_recovery import serving
from pramaan_integration import LedgerBlocked, ValidationFailure   # noqa: E402
from pramaan_integration.profile import validate_native            # noqa: E402

A, B, C = "MTR-94001", "MTR-94002", "MTR-94003"


def build(app, motor, *, lots=("BR-310", "BR-312"), machine="LATHE-02", inspect=True, ship=True, result="PASS"):
    """Machine and inspect a shaft, assemble, optionally ship (synthetic fixture shipment)."""
    app.create_unit(motor, lifecycle=True)
    shaft = f"SHAFT-{motor[4:]}"
    m1 = app.machine(motor, "SHAFT", shaft, "TURNING", machine, "R10", "DWG-SH-100 rev C")
    m2 = app.machine(motor, "SHAFT", shaft, "GRINDING", "GRIND-01", "R20", "DWG-SH-100 rev C", previous=m1["eventId"])
    i = app.inspect_quality(motor, "DIMENSIONAL", [m2["eventId"]], "QP-SHAFT-7", result, ["DIMENSIONAL"]) if inspect else None
    app.assemble(motor, *lots)
    if ship:
        app.record_historical_shipment_fixture(motor)
    return m1, m2, i


def kernel(app, motor):
    """The evaluator's raw output for the motor, without its watermark (which legitimately differs when more sources have events)."""
    entry = [p for k, p in app.audit.verify() if k == "EVALUATION" and p["context"]["motor"] == motor][-1]
    return {k: v for k, v in entry["raw"].items() if k != "watermark"}


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Path(self.tmp.name) / "l.sqlite"
        self.app = Manufacturing(self.db)

    def tearDown(self):
        self.app.close(); self.tmp.cleanup()

    def rejections(self):
        return self.app.db.execute("SELECT COUNT(*) FROM rejections").fetchone()[0]

    # ---- identity, source, time, references
    def test_new_events_carry_identity_source_time_references_and_ledger_coverage(self):
        m1, m2, i = build(self.app, A)
        snap = self.app.snapshot()
        events = {e["eventId"]: e for e in next(u for u in snap["units"] if u["unitId"] == A)["events"]}
        for e in (m1, m2, i):
            got = events[e["eventId"]]
            self.assertTrue(got["eventId"].startswith(f"urn:pramaan:{A}:"))
            self.assertEqual(got["motorSerial"], A)
            self.assertTrue(got["sourceId"].endswith(f":{A}") and got["actorId"] in {a for a, _ in ALL_ROLES.values()})
            self.assertTrue(got["occurredAt"] <= got["recordedAt"] and got["timeSource"] == "SYNTHETIC_SIMULATED")
            self.assertTrue(got["evidenceRefs"])
            repo = got["repository"]
            self.assertEqual(len(repo["captureSha256"]), 64); self.assertEqual(len(repo["eventChainHash"]), 64)
        self.assertEqual(events[m2["eventId"]]["payload"]["previousOperationEventId"], m1["eventId"])
        self.assertEqual(events[i["eventId"]]["payload"]["subjectEventIds"], [m2["eventId"]])
        self.assertEqual(events[m1["eventId"]]["sourceId"], f"MACHINING:{A}")
        self.assertEqual(events[i["eventId"]]["sourceId"], f"QC:{A}")

    def test_tampering_with_a_lifecycle_event_is_detected(self):
        _, _, i = build(self.app, A)
        self.app.snapshot(); self.app.close()
        raw = sqlite3.connect(str(self.db))
        raw.execute("DROP TRIGGER events_no_update")          # the attacker removes the append-only trigger, then rewrites the recorded result
        native = json.loads(raw.execute("SELECT native FROM events WHERE id=?", (i["eventId"],)).fetchone()[0])
        native["payload"]["result"] = "FAIL"
        raw.execute("UPDATE events SET native=? WHERE id=?", (json.dumps(native), i["eventId"])); raw.commit(); raw.close()
        self.app = Manufacturing(self.db)
        with self.assertRaises(LedgerBlocked):
            self.app.snapshot()

    def test_checkpoint_covers_lifecycle_events(self):
        build(self.app, A)
        self.app.announce("BR-204", ["DE"]); self.app.snapshot()
        cp = Path(self.tmp.name) / "c0.json"
        publish_candidate(cp, export_anchor(self.app))
        self.assertEqual(TrustedAnchor(cp).verify(self.app)["state"], "ANCHORED_CURRENT")
        self.app.machine(A, "HOUSING", "HOUSING-94001", "BORING", "BORE-01", "R30", "DWG-HS-200 rev A")   # new evidence after the checkpoint
        self.assertEqual(TrustedAnchor(cp).verify(self.app)["state"], "ANCHORED_PREFIX_ONLY")           # the old checkpoint no longer covers current state
        cp2 = Path(self.tmp.name) / "c1.json"
        publish_candidate(cp2, export_anchor(self.app))
        self.assertEqual(TrustedAnchor(cp2).verify(self.app)["state"], "ANCHORED_CURRENT")

    # ---- chronology
    def test_complete_lifecycle_chronology(self):
        build(self.app, A)
        self.app.replace(A, "BR-312")                                       # supported rework still works after lifecycle events
        view = lifecycle.view(next(u for u in self.app.snapshot()["units"] if u["unitId"] == A)["events"])
        chron = view["chronology"]
        self.assertEqual([r["occurredAt"] for r in chron], sorted(r["occurredAt"] for r in chron))
        cats = [r["category"] for r in chron]
        first = {c: cats.index(c) for c in ("MACHINING", "INSPECTION", "MATERIAL", "ASSEMBLY", "SHIPMENT", "REWORK")}
        self.assertLess(first["MACHINING"], first["INSPECTION"]); self.assertLess(first["INSPECTION"], first["MATERIAL"])
        self.assertLess(first["MATERIAL"], first["ASSEMBLY"]); self.assertLess(first["ASSEMBLY"], first["SHIPMENT"]); self.assertLess(first["SHIPMENT"], first["REWORK"])
        self.assertEqual(len(chron), len({r["eventId"] for r in chron}))
        self.assertEqual(view["violations"], [])
        self.assertTrue(all(r["ledger"]["eventChainHash"] for r in chron))
        self.assertTrue(all(ref["present"] for r in chron for ref in r["references"]))

    def test_chronology_flags_a_reference_that_occurs_later(self):
        events = json.loads(json.dumps(next(u for u in (build(self.app, A), self.app.snapshot())[1]["units"] if u["unitId"] == A)["events"]))
        insp = next(e for e in events if e["eventType"] == "QUALITY_INSPECTION_RECORDED")
        insp["occurredAt"] = "2000-01-01T00:00:00Z"; insp["recordedAt"] = "2000-01-01T00:00:00Z"
        kinds = {v["kind"] for v in lifecycle.violations(events)}
        self.assertIn("REFERENCE_OCCURS_LATER", kinds)

    # ---- traceability
    def test_forward_and_backward_traceability_agree(self):
        build(self.app, A); build(self.app, B, lots=("BR-204", "BR-312")); build(self.app, C, lots=("BR-310", "BR-310"), machine="LATHE-07", ship=False)
        snap = self.app.snapshot()
        histories = {u["unitId"]: u["events"] for u in snap["units"]}
        by_machine = lifecycle.forward(histories, "machineId", "LATHE-02")
        self.assertEqual([m["motorSerial"] for m in by_machine["motors"]], [A, B])
        self.assertTrue(all(m["shipments"] for m in by_machine["motors"]))
        self.assertTrue(all(m["inspections"] == [] for m in by_machine["motors"]))        # the inspection concerns the later grinding step, not the turning step
        by_grinder = lifecycle.forward(histories, "machineId", "GRIND-01")
        self.assertEqual([m["motorSerial"] for m in by_grinder["motors"]], [A, B, C])
        self.assertTrue(all(m["inspections"][0]["assurance"] == "RECORDED_CLAIM_DIFFERENT_ACTOR_AND_SOURCE" and m["inspections"][0]["recordedResult"] == "PASS" for m in by_grinder["motors"]))
        by_lot = lifecycle.forward(histories, "bearingLot", "BR-204")
        self.assertEqual([m["motorSerial"] for m in by_lot["motors"]], [B])
        self.assertEqual([m["motorSerial"] for m in lifecycle.forward(histories, "machineId", "LATHE-07")["motors"]], [C])
        self.assertEqual(lifecycle.forward(histories, "machineId", "LATHE-07")["motors"][0]["shipments"], [])
        # backward from every motor found going forward names the key again
        for m in by_lot["motors"]:
            back = lifecycle.backward(histories[m["motorSerial"]])
            self.assertIn("BR-204", [b["lot"] for b in back["bearings"]])
            self.assertTrue(all(b["manufactureEventId"] and b["materialEventId"] for b in back["bearings"]))
            self.assertEqual(back["shipments"][0]["assemblyEventId"], back["assemblyClosedEventId"])
        self.assertEqual(lifecycle.forward(histories, "machineId", "NO-SUCH-MACHINE")["motors"], [])
        with self.assertRaises(ValueError):
            lifecycle.forward(histories, "customer", "x")
        back_a = lifecycle.backward(histories[A])["machinedComponents"][0]
        self.assertEqual([o["operation"] for o in back_a["operations"]], ["TURNING", "GRINDING"])
        self.assertEqual(back_a["operations"][1]["inspections"][0]["recordedResult"], "PASS")

    # ---- recorded versus verified
    def test_inspection_is_a_recorded_claim_and_never_verified_or_cleared(self):
        build(self.app, A, result="PASS")
        snap = self.app.snapshot()
        row = next(r for r in lifecycle.chronology(next(u for u in snap["units"] if u["unitId"] == A)["events"]) if r["category"] == "INSPECTION")
        a = row["assurance"]
        self.assertIs(a["independentlyVerified"], False); self.assertIs(a["trustedTime"], False); self.assertTrue(a["inspectorQualificationIsClaimed"])
        self.assertEqual(a["recordedResult"], "PASS"); self.assertIn("release eligibility", a["notEstablished"])
        self.assertFalse(any(v.get("currentReleaseEligible") for v in snap.get("eligibility", {}).values()))

    def test_same_actor_inspection_is_labelled_weaker(self):
        build(self.app, A)
        events = json.loads(json.dumps(next(u for u in self.app.snapshot()["units"] if u["unitId"] == A)["events"]))
        insp = next(e for e in events if e["eventType"] == "QUALITY_INSPECTION_RECORDED")
        insp["actorId"] = "OP-MACHINING-05"
        row = next(r for r in lifecycle.chronology(events) if r["eventId"] == insp["eventId"])
        self.assertEqual(row["assurance"]["level"], "RECORDED_CLAIM_SAME_ACTOR_OR_SOURCE")

    def test_failed_inspection_is_recorded_without_any_automatic_decision(self):
        build(self.app, A, result="FAIL")
        snap = self.app.snapshot()
        self.assertEqual(next(r for r in lifecycle.chronology(next(u for u in snap["units"] if u["unitId"] == A)["events"]) if r["category"] == "INSPECTION")["assurance"]["recordedResult"], "FAIL")

    # ---- evaluator isolation
    def test_lifecycle_events_do_not_change_the_evaluators_output(self):
        """Same motor, same recall, evaluated before and after machining and inspection evidence is added: the evaluator's raw output is identical."""
        self.app.create_unit(A, lifecycle=True)
        self.app.assemble(A, "BR-204", "BR-310"); self.app.record_historical_shipment_fixture(A)
        self.app.announce("BR-204", ["DE"]); self.app.snapshot()
        before = kernel(self.app, A)
        m = self.app.machine(A, "SHAFT", "SHAFT-1", "TURNING", "LATHE-02", "R10", "DWG rev C")
        self.app.inspect_quality(A, "VISUAL", [m["eventId"]], "QP-1", "PASS", ["VISUAL"])        # a recorded PASS must not move the decision
        self.app.snapshot()
        after = kernel(self.app, A)
        self.assertEqual(before["evidenceFinding"], "AFFECTED")
        self.assertEqual(json.dumps(before, sort_keys=True), json.dumps(after, sort_keys=True))
        decision = list(self.app.snapshot()["decisions"][A].values())[0]["current"]
        self.assertEqual((decision["evidenceFinding"], decision["operationalAction"]), ("AFFECTED", "RECALL_HOLD"))

    def test_recall_and_rework_semantics_are_preserved(self):
        build(self.app, A, lots=("BR-204", "BR-310"))
        self.app.announce("BR-204", ["DE"])
        before = list(self.app.snapshot()["decisions"][A].values())[0]["current"]
        self.assertEqual((before["evidenceFinding"], before["operationalAction"]), ("AFFECTED", "RECALL_HOLD"))
        self.app.replace(A, "BR-312")
        after = list(self.app.snapshot()["decisions"][A].values())[0]["current"]
        self.assertEqual((after["evidenceFinding"], after["operationalAction"], after["reasonCodes"]), ("EXCLUDED_WITH_EVIDENCE", "RELEASE_ELIGIBLE", ["REPLACED_WITH_UNAFFECTED_LOT"]))
        self.assertFalse(list(self.app.snapshot()["eligibility"].values())[0]["currentReleaseEligible"])   # no current checkpoint: still no clearance

    def test_legacy_units_are_unchanged(self):
        self.app.create_unit("MTR-94020")
        cfg = self.app.ledger._config("MTR-94020")
        self.assertEqual(set(cfg["sources"]), {f"{r}:MTR-94020" for r in ROLES})
        with self.assertRaises(ValidationFailure):
            self.app.machine("MTR-94020", "SHAFT", "SHAFT-1", "TURNING", "LATHE-02", "R10", "DWG rev C")
        self.assertEqual(self.rejections(), 0)                      # refused before capture: the motor is not blocked
        self.app.assemble("MTR-94020", "BR-310", "BR-312")           # and it still accepts ordinary capture

    # ---- malformed events
    def test_malformed_requests_are_refused_without_blocking_the_motor(self):
        self.app.create_unit(A, lifecycle=True)
        m = self.app.machine(A, "SHAFT", "SHAFT-1", "TURNING", "LATHE-02", "R10", "DWG rev C")
        bad = [lambda: self.app.machine(A, "WHEEL", "X", "TURNING", "L", "R", "D"),
               lambda: self.app.machine(A, "SHAFT", "X", "WELDING", "L", "R", "D"),
               lambda: self.app.machine(A, "SHAFT", "", "TURNING", "L", "R", "D"),
               lambda: self.app.machine(A, "SHAFT", "X", "TURNING", None, "R", "D"),
               lambda: self.app.machine(A, "SHAFT", "X", "TURNING", "L", "R", "   "),
               lambda: self.app.machine(A, "SHAFT", "SHAFT-2", "GRINDING", "L", "R", "D", previous=m["eventId"]),     # different component
               lambda: self.app.machine(A, "SHAFT", "SHAFT-1", "GRINDING", "L", "R", "D", previous="urn:pramaan:nope"),
               lambda: self.app.inspect_quality(A, "DIMENSIONAL", [m["eventId"]], "QP", None, []),                     # no result is ever defaulted
               lambda: self.app.inspect_quality(A, "DIMENSIONAL", [m["eventId"]], "QP", "APPROVED", []),
               lambda: self.app.inspect_quality(A, "DIMENSIONAL", [m["eventId"]], "QP", "pass", []),
               lambda: self.app.inspect_quality(A, "MAGIC", [m["eventId"]], "QP", "PASS", []),
               lambda: self.app.inspect_quality(A, "DIMENSIONAL", [], "QP", "PASS", []),
               lambda: self.app.inspect_quality(A, "DIMENSIONAL", ["urn:pramaan:unknown"], "QP", "PASS", []),
               lambda: self.app.inspect_quality(A, "DIMENSIONAL", [m["eventId"], m["eventId"]], "QP", "PASS", []),
               lambda: self.app.inspect_quality(A, "DIMENSIONAL", [m["eventId"]], "", "PASS", []),
               lambda: self.app.inspect_quality(A, "DIMENSIONAL", [m["eventId"]], "QP", "PASS", "DIMENSIONAL"),
               lambda: self.app.inspect_quality(A, "DIMENSIONAL", m["eventId"], "QP", "PASS", [])]
        for n, call in enumerate(bad):
            with self.assertRaises(ValidationFailure, msg=f"case {n}"):
                call()
        self.assertEqual(self.rejections(), 0)
        self.app.machine(A, "SHAFT", "SHAFT-1", "GRINDING", "L", "R", "D", previous=m["eventId"])   # the motor is still open for capture

    def test_profile_rejects_self_asserted_verification_clearance_slots_and_extra_fields(self):
        base = dict(eventId="urn:pramaan:M:MACHINING:1", eventType="MACHINING_RECORDED", schemaVersion=1, motorSerial="M", sourceId="MACHINING:M", sourceSeq=1,
                    occurredAt="2026-10-10T08:00:00Z", recordedAt="2026-10-10T08:00:04Z", actorId="a", timeSource="SYNTHETIC_SIMULATED", evidenceRefs=["r"],
                    workOrderId=None, recallId=None, supersedesEventId=None, captureSessionId="s",
                    payload=dict(componentType="SHAFT", componentId="S", operation="TURNING", machineId="L", routingStepId="R", drawingRef="D"))
        validate_native(base)
        for extra in ({"slot": "DE"}, {"verified": True}, {"independentlyVerified": True}, {"clearance": "OK"}, {"releaseEligible": True}, {"trusted": True}, {"result": "PASS"}):
            e = json.loads(json.dumps(base)); e["payload"].update(extra)
            with self.assertRaises(ValidationFailure, msg=str(extra)):
                validate_native(e)
        e = json.loads(json.dumps(base)); e["workOrderId"] = "BUILD-M"
        with self.assertRaises(ValidationFailure):
            validate_native(e)

    def test_ledger_rejects_bad_references_and_blocks_the_motor(self):
        """A reference that survives profile validation but names the wrong thing is rejected by the ledger (durable rejection, the existing semantics)."""
        self.app.create_unit(A, lifecycle=True)
        m = self.app.machine(A, "SHAFT", "SHAFT-1", "TURNING", "LATHE-02", "R10", "DWG rev C")
        with self.assertRaises(LedgerBlocked):
            self.app.event(A, "QUALITY_INSPECTION_RECORDED", "QC", dict(inspectionType="VISUAL", subjectEventIds=["urn:pramaan:MTR-94001:MACHINING:99"], protocolId="QP",
                                                                         result="PASS", inspectorQualifiedFor=[]))
        self.assertEqual(self.rejections(), 1)
        with self.assertRaises(LedgerBlocked):
            self.app.snapshot()                                    # blocked motor: no decision, existing fail-closed behaviour

    def test_ledger_rejects_references_to_other_event_types_and_other_motors(self):
        self.app.create_unit(A, lifecycle=True); self.app.create_unit(B, lifecycle=True)
        mb = self.app.machine(B, "SHAFT", "SHAFT-B", "TURNING", "LATHE-02", "R10", "DWG rev C")
        with self.assertRaises(LedgerBlocked):
            self.app.event(A, "QUALITY_INSPECTION_RECORDED", "QC", dict(inspectionType="VISUAL", subjectEventIds=[mb["eventId"]], protocolId="QP", result="PASS", inspectorQualifiedFor=[]))

    def test_source_not_provisioned_for_a_role_is_rejected_by_the_ledger(self):
        """The ledger, not only the service, enforces source capability: the machining source cannot write inspections."""
        self.app.create_unit(A, lifecycle=True)
        m = self.app.machine(A, "SHAFT", "SHAFT-1", "TURNING", "LATHE-02", "R10", "DWG rev C")
        with self.assertRaises(LedgerBlocked):
            self.app.event(A, "QUALITY_INSPECTION_RECORDED", "MACHINING", dict(inspectionType="VISUAL", subjectEventIds=[m["eventId"]], protocolId="QP", result="PASS", inspectorQualifiedFor=[]))

    # ---- read-only API
    def test_http_lifecycle_and_trace_routes_are_read_only_history(self):
        build(self.app, A); build(self.app, B, lots=("BR-204", "BR-312"))
        self.app.announce("BR-204", ["DE"]); self.app.snapshot()
        cp = Path(self.tmp.name) / "c0.json"
        publish_candidate(cp, export_anchor(self.app)); self.app.close()
        with serving(self.db, cp) as c:
            status, body = c.call(f"/api/motors/{A}/lifecycle")
            self.assertEqual(status, 200)
            self.assertEqual(set(body), {"chronology", "backward", "violations", "eventCount", "checkpoint", "motorSerial"})
            self.assertNotIn("decisions", body); self.assertNotIn("eligibility", body)
            self.assertEqual(body["checkpoint"]["state"], "ANCHORED_CURRENT")
            self.assertEqual([r["category"] for r in body["chronology"]][:3], ["MACHINING", "MACHINING", "INSPECTION"])
            status, body = c.call("/api/trace/machineId/LATHE-02")
            self.assertEqual((status, [m["motorSerial"] for m in body["motors"]]), (200, [A, B]))
            self.assertEqual(c.call("/api/trace/customer/x")[0], 404)
            self.assertEqual(c.call("/api/motors/MTR-NOPE/lifecycle")[0], 404)
            # command routes: refused input is a 400 and writes nothing
            before = c.call("/api/snapshot")[1]["freshness"]["sequence"]
            status, _ = c.call(f"/api/units/{A}/inspect", dict(inspectionType="VISUAL", subjectEventIds=["urn:nope"], protocolId="QP", result="PASS", qualifiedFor=[]))
            self.assertEqual(status, 400)
            status, _ = c.call(f"/api/units/{A}/machine", dict(componentType="SHAFT", componentId="S", operation="TURNING", machineId="L", routingStepId="R", drawingRef="D", extra=1))
            self.assertEqual(status, 400)
            self.assertEqual(c.call("/api/snapshot")[1]["freshness"]["sequence"], before)

    def test_http_capture_makes_history_visible_and_ends_clearance_currency(self):
        build(self.app, A, ship=False)
        self.app.announce("BR-204", ["DE"]); self.app.snapshot()
        cp = Path(self.tmp.name) / "c0.json"
        publish_candidate(cp, export_anchor(self.app)); self.app.close()
        with serving(self.db, cp) as c:
            self.assertEqual(c.call(f"/api/motors/{A}/decisions")[1]["eligibility"]["currentReleaseEligible"], True)
            status, body = c.call(f"/api/units/{A}/machine", dict(componentType="HOUSING", componentId="HOUSING-A", operation="BORING", machineId="BORE-01", routingStepId="R30", drawingRef="DWG-HS-200"))
            self.assertEqual(status, 200)
            status, life = c.call(f"/api/motors/{A}/lifecycle")
            self.assertTrue(any(r["eventType"] == "MACHINING_RECORDED" and r["machineId"] == "BORE-01" for r in life["chronology"]))
            # ANY new ledger evidence moves the ledger past the checkpoint: current clearance is withdrawn until a new checkpoint is accepted.
            self.assertEqual(life["checkpoint"]["state"], "ANCHORED_PREFIX_ONLY")
            self.assertEqual(c.call(f"/api/motors/{A}/decisions")[0], 409)


if __name__ == "__main__":
    unittest.main()
