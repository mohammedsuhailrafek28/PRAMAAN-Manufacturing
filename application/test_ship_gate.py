"""Ordinary shipment gate (owner-approved P1 fix; synthetic, loopback only). Run: python -B -m unittest application.test_ship_gate -v
Set SHIP_GATE_EVIDENCE=<file> to write the measured results as JSON.

The ordinary ship operation records a shipment only while the motor holds a CURRENT trusted checkpoint AND current operational release eligibility, checked
inside the same ledger transaction cut as the write (a single-use ticket bound to the ledger state plus a connection-local insert guard). Historical shipment
fixtures go through Manufacturing.record_historical_shipment_fixture, which the HTTP server never references. Same-host custody is not independent verification.
"""
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from . import server as server_mod
from .anchors import TrustedAnchor, export_anchor, publish_candidate
from .service import Manufacturing, ShipmentRefused
from .test_lot_identity_ab import raw_assemble, RECALLED, SAFE
from .test_v11_hardening import base_doc, mutated, reg
from .test_stale_recovery import Client

E, X, P = "MTR-93001", "MTR-93002", "MTR-93003"       # E: eligible unshipped motor; X: a second motor used to move the ledger; P: problem motor
EVIDENCE = {}


def world(d, problem=None):
    """E (clean, unshipped), X (clean, shipped fixture) and optionally a problem motor P built by `problem(app)`; recall on BR-204 DE; checkpoint c0 current."""
    db, c0 = Path(d) / "g.sqlite", Path(d) / "c0.json"
    app = Manufacturing(db)
    app.create_unit(E); app.assemble(E, SAFE, "BR-312")
    app.create_unit(X); app.assemble(X, SAFE, "BR-312"); app.record_historical_shipment_fixture(X)
    if problem:
        app.create_unit(P); problem(app)
    app.announce(RECALLED, ["DE"]); app.snapshot()
    publish_candidate(c0, export_anchor(app)); app.close()
    return db, c0


def counts(db):
    app = Manufacturing(db)
    try:
        q = lambda sql: app.db.execute(sql).fetchone()[0]
        return dict(shipped=q("SELECT COUNT(*) FROM events WHERE json_extract(native,'$.eventType')='MOTOR_SHIPPED'"), rejections=q("SELECT COUNT(*) FROM rejections"),
                    tickets=q("SELECT COUNT(*) FROM app_ship_tickets"), events=q("SELECT COUNT(*) FROM events"))
    finally:
        app.close()


def attempt(db, anchor, motor=E, *, registry=None, hook=None):
    app = Manufacturing(db, lot_registry=reg(registry) if registry is not None else None)
    try:
        if hook:
            hook(app)
        return app.ship(motor, trusted_anchor=TrustedAnchor(anchor, None) if anchor is not None else None)
    finally:
        app.close()


class ShipGate(unittest.TestCase):
    def refused(self, db, anchor, label, **kw):
        before = counts(db)
        with self.assertRaises(ShipmentRefused, msg=label):
            attempt(db, anchor, **kw)
        after = counts(db)
        self.assertEqual(after["shipped"], before["shipped"], label)
        self.assertEqual(after["rejections"], before["rejections"], label)       # a refusal must not strand the unit with a rejection row
        self.assertEqual(after["events"], before["events"], label)
        self.assertEqual(after["tickets"], 0, label)
        EVIDENCE[label] = dict(refused=True, shipmentRecorded=False, rejectionRowsAdded=0)

    def test_normal_current_eligible_shipment_succeeds(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0 = world(d)
            event = attempt(db, c0)
            self.assertEqual(event["eventType"], "MOTOR_SHIPPED")
            c = counts(db)
            self.assertEqual((c["shipped"], c["rejections"], c["tickets"]), (2, 0, 0))   # X (fixture) + E; the single-use ticket is gone
            app = Manufacturing(db)
            try:
                self.assertEqual(app.db.execute("SELECT name FROM sqlite_temp_master WHERE type='trigger'").fetchall(), [])
                snap = app.snapshot(trusted_anchor=TrustedAnchor(c0, None))
            finally:
                app.close()
            self.assertEqual(snap["checkpoint"]["state"], "ANCHORED_PREFIX_ONLY")        # the shipment itself moved the ledger past the checkpoint: a new checkpoint cycle is required
            self.assertTrue(all(not v["currentReleaseEligible"] for v in snap["eligibility"].values()))
            EVIDENCE["currentEligibleShipment"] = dict(recorded=True, checkpointAfter=snap["checkpoint"]["state"])

    def test_a_shipment_that_succeeded_cannot_be_repeated(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0 = world(d)
            attempt(db, c0)
            with self.assertRaises(Exception):
                attempt(db, c0)
            self.assertEqual(counts(db)["shipped"], 2)

    def test_unanchored_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0 = world(d)
            self.refused(db, None, "unanchored")

    def test_prefix_only_checkpoint_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0 = world(d)
            app = Manufacturing(db); app.observe(X, "ZZ-9"); app.close()               # the ledger moves past the checkpoint
            self.refused(db, c0, "prefixOnly")

    def test_registry_discrepancy_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0 = world(d)
            doc = mutated(lambda r: r.__setitem__("note", "changed") if "note" in r else r.update(note="changed"))
            self.refused(db, c0, "registryDiscrepancy", registry=doc)

    def test_unresolved_lot_identity_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0 = world(d, problem=lambda a: raw_assemble(a, P, "UNKNOWN", SAFE))
            self.refused(db, c0, "unresolvedLotIdentity", motor=P)
            self.assertEqual(counts(db)["shipped"], 1)

    def test_unverified_sighting_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0 = world(d, problem=lambda a: (a.assemble(P, SAFE, "BR-312"), a.observe(P, "ZZ-9")))
            self.refused(db, c0, "unverifiedSighting", motor=P)

    def test_recall_hold_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0 = world(d, problem=lambda a: a.assemble(P, "BR-204", "BR-312"))
            self.refused(db, c0, "recallHold", motor=P)

    def test_ledger_change_between_the_eligibility_check_and_the_write_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0 = world(d)
            fired = []

            def hook(app):
                original = app.ledger.capture

                def capture(*a, **k):
                    if not fired:                                                       # a second connection appends to the ledger after the ticket was issued
                        fired.append(True)
                        other = Manufacturing(db); other.observe(X, "ZZ-9"); other.close()
                    return original(*a, **k)
                app.ledger.capture = capture
            before = counts(db)
            with self.assertRaises(ShipmentRefused):
                attempt(db, c0, hook=hook)
            after = counts(db)
            self.assertTrue(fired)
            self.assertEqual((after["shipped"], after["rejections"], after["tickets"]), (before["shipped"], before["rejections"], 0))
            self.assertEqual(after["events"], before["events"] + 1)                      # only the concurrent observation landed
            EVIDENCE["concurrentLedgerChange"] = dict(refused=True, shipmentRecorded=False, rejectionRowsAdded=0)

    def test_a_stale_ticket_cannot_authorize_a_later_state(self):
        """Tickets are bound to one ledger state: replaying an old ticket after the ledger moved is refused by the insert guard."""
        with tempfile.TemporaryDirectory() as d:
            db, c0 = world(d)
            app = Manufacturing(db)
            try:
                app.snapshot(trusted_anchor=TrustedAnchor(c0, None), ship_ticket=E)
                self.assertEqual(app.db.execute("SELECT COUNT(*) FROM app_ship_tickets").fetchone()[0], 1)
                app.observe(X, "ZZ-9")                                                  # ledger moves on; the ticket is now for a past state
                app.db.execute("CREATE TEMP TRIGGER g BEFORE INSERT ON main.events WHEN json_extract(NEW.native,'$.eventType')='MOTOR_SHIPPED' AND NOT EXISTS "
                               "(SELECT 1 FROM main.app_ship_tickets t WHERE t.motor=NEW.motor AND t.fingerprint=(%s)) BEGIN SELECT RAISE(IGNORE); END" % app.FINGERPRINT_SQL.removeprefix("SELECT "))
                app.event(E, *app._shipment(E))
                self.assertFalse(any(e["eventType"] == "MOTOR_SHIPPED" for e in app.events(E)))
            finally:
                app.close()

    def test_unauthenticated_ticket_free_shipment_is_only_possible_through_the_named_fixture_path(self):
        source = (Path(server_mod.__file__)).read_text(encoding="utf-8")
        self.assertNotIn("record_historical_shipment_fixture", source)
        self.assertNotIn("_shipment(", source)
        self.assertNotIn(".event(", source)                                              # the server has no generic event-writing route
        EVIDENCE["serverNeverReferencesFixturePath"] = True


class ShipGateHttp(unittest.TestCase):
    def serve(self, db, anchor):
        srv = server_mod.make_server(db, 0, trusted_anchor=anchor)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        return Client(srv)

    def test_direct_api_is_refused_when_the_ui_would_be_blocked_and_client_claims_change_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0 = world(d, problem=lambda a: a.assemble(P, "BR-204", "BR-312"))
            c = self.serve(db, c0)
            snap = c.call("/api/snapshot")[1]
            self.assertFalse(snap["eligibility"][P]["currentReleaseEligible"])
            claims = {"currentReleaseEligible": True, "eligibility": {P: {"currentReleaseEligible": True}}, "force": True, "trusted": True}
            s, body = c.call(f"/api/units/{P}/ship", claims)
            self.assertEqual((s, body.get("error")), (409, "SHIPMENT_REFUSED"))
            self.assertEqual(counts(db)["shipped"], 1)
            EVIDENCE["directApiRecallHold"] = dict(status=s)

    def test_direct_api_ships_a_current_eligible_motor(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0 = world(d)
            c = self.serve(db, c0)
            s, body = c.call(f"/api/units/{E}/ship", {})
            self.assertEqual(s, 200)
            self.assertEqual(body["snapshot"]["checkpoint"]["state"], "ANCHORED_PREFIX_ONLY")
            self.assertEqual(counts(db)["shipped"], 2)
            EVIDENCE["directApiEligible"] = dict(status=s)


def tearDownModule():
    out = os.environ.get("SHIP_GATE_EVIDENCE")
    if out:
        Path(out).write_text(json.dumps(EVIDENCE, indent=1, sort_keys=True, default=str), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
