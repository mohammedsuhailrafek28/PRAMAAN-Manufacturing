"""Synthetic ground truth is confined to tests, never imported by the application."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from application.service import Manufacturing, ValidationFailure, LedgerBlocked, RECALL_ID
from application.server import make_server
from unittest.mock import patch
from pramaan_integration import encode_document, Ledger

PID = RECALL_ID + "/P1"


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "app.sqlite"
        self.app = Manufacturing(self.path)

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def current(self, motor):
        return self.app.snapshot()["decisions"][motor][PID]["current"]

    def test_full_manufacturing_flow_and_reopen(self):
        m = "MTR-TEST-001"
        self.app.create_unit(m)
        self.app.announce("BR-204")
        self.assertEqual(self.current(m)["operationalAction"], "RECALL_HOLD")
        self.app.assemble(m, "BR-204", "BR-310")
        self.app.record_historical_shipment_fixture(m)
        before = self.current(m)
        self.assertEqual(before["evidenceFinding"], "AFFECTED")
        snap = self.app.snapshot()
        self.assertEqual(len(snap["lineage"]), 2)
        self.assertTrue(snap["units"][0]["shipment"]["backedByLedger"])
        self.assertTrue(all(e["repository"]["captureSha256"] for e in snap["units"][0]["events"]))
        self.assertTrue(all(e["occurredAt"] < e["recordedAt"] < e["repository"]["recordTime"] for e in snap["units"][0]["events"]))
        self.app.replace(m, "BR-312")
        after = self.current(m)
        self.assertEqual(after["evidenceFinding"], "EXCLUDED_WITH_EVIDENCE")
        self.assertEqual(after["supersedesDecisionId"], before["decisionId"])
        self.assertTrue(after["coverageDigest"])
        self.app.close(); self.app = Manufacturing(self.path)
        self.assertEqual(self.current(m), after)
        self.app.observe(m, "BR-204")
        late = self.current(m)
        self.assertEqual(late["operationalAction"], "RECALL_HOLD")
        self.assertIn("PRIOR_EXCLUSION_WITHDRAWN", late["reasonCodes"])
        self.assertTrue(late["precautionaryHold"])
        self.assertIsNone(late["notificationObligation"]["communicated"])
        self.assertEqual(late["notificationObligation"]["appliesIfDecisionCommunicated"], after["decisionId"])
        self.assertEqual(len(self.app.snapshot()["notifications"]), 1)

    def test_seed_safety_cases_and_idempotence(self):
        self.app.seed_demo()
        # RELIABILITY FIX (from research/phase31-reliability-audit@6d177e8, scoped): `freshness.verifiedAt` is the wall clock to whole
        # seconds, so two identical snapshots straddling a second boundary differed ONLY at /freshness/verifiedAt (observed in ~20-45% of
        # natural runs). The clock is fixed for these two snapshot calls only; capture timestamps and every assertion are unchanged, and
        # production clock semantics are not touched. Lease expiry/skew tests keep their own controlled clocks.
        with patch.object(Ledger, '_now', staticmethod(lambda: '2026-10-22T00:00:00Z')):
            initial = self.app.snapshot()
            self.app.seed_demo()
            repeated = self.app.snapshot()
        self.assertEqual(initial, repeated)
        expected = {"MTR-26001": "AFFECTED", "MTR-26002": "UNRESOLVED", "MTR-26003": "EXCLUDED_WITH_EVIDENCE", "MTR-26004": "UNRESOLVED", "MTR-26005": "UNRESOLVED"}
        for m, finding in expected.items():
            self.assertEqual(self.current(m)["evidenceFinding"], finding)
        self.assertIn("AMBIGUOUS_SLOT_ATTRIBUTION", self.current("MTR-26002")["reasonCodes"])
        self.assertIn("UNTRUSTED_AFFECTED_OBSERVATION", self.current("MTR-26005")["reasonCodes"])
        self.assertTrue(initial["comparison"])
        self.assertFalse(any("syntheticGroundTruth" in u for u in initial["units"]))

    def test_unknown_is_not_empty_and_no_phantom_shipment(self):
        self.app.create_unit("MTR-UNKNOWN")
        snap = self.app.snapshot()
        self.assertEqual(snap["policies"], [])
        self.assertIsNone(snap["units"][0]["shipment"])
        with self.assertRaises(ValidationFailure):
            self.app.record_historical_shipment_fixture("MTR-UNKNOWN")
        self.app.announce("BR-204")
        d = self.current("MTR-UNKNOWN")
        self.assertEqual(d["operationalAction"], "RECALL_HOLD")
        self.assertNotEqual(d["evidenceFinding"], "EXCLUDED_WITH_EVIDENCE")

    def test_manufactured_identity_mismatch_is_blocked(self):
        m = "MTR-MISMATCH"
        self.app.create_unit(m); self.app.assemble(m, "BR-204", "BR-310")
        old = next(e for e in self.app.events(m) if e["eventType"] == "COMPONENT_INSTALLED")
        event = copy.deepcopy(old)
        event.update(eventId="urn:test:bad", sourceSeq=3)
        event["payload"]["serial"] = "WRONG-PHYSICAL-ITEM"
        raw = json.dumps(encode_document([event], event["recordedAt"])).encode()
        with self.assertRaises(ValidationFailure):
            self.app.ledger.capture(m, raw, producer_source=event["sourceId"], expected_sha256=hashlib.sha256(raw).hexdigest())
        with self.assertRaises(LedgerBlocked):
            self.app.snapshot()

    def test_append_only_material_and_policy(self):
        self.app.create_unit("MTR-IMMUTABLE")
        self.app.assemble("MTR-IMMUTABLE", "BR-310", "BR-312")
        self.app.announce("BR-204")
        with self.assertRaises(ValidationFailure):
            self.app.announce("DIFFERENT-SCOPE")
        self.assertEqual(self.app.policy()["affectedLots"], ["BR-204"])
        import sqlite3
        for sql in ("UPDATE events SET native='{}'", "DELETE FROM recall_announcements"):
            with self.assertRaises(sqlite3.IntegrityError):
                self.app.db.execute(sql)
            self.app.db.rollback()


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from .anchors import export_anchor
        database=Path(self.tmp.name)/'http.sqlite'
        seed=Manufacturing(database); seed.seed_demo()
        anchor=Path(self.tmp.name)/'owner-anchor.json'
        anchor.write_text(json.dumps(export_anchor(seed))); seed.close()
        self.server = make_server(database, 0, trusted_anchor=anchor)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.token = self.request("/api/session")["token"]

    def tearDown(self):
        self.server.shutdown(); self.thread.join(); self.server.server_close(); self.tmp.cleanup()

    def request(self, path, body=None, token=None, origin=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Pramaan-Token"] = token
        if origin:
            headers["Origin"] = origin
        req = Request(self.base+path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        with urlopen(req) as res:
            return json.load(res)

    def test_api_reads_provenance_genealogy_decisions_and_obligations(self):
        self.assertEqual(len(self.request("/api/motors")), 5)
        self.assertEqual(len(self.request("/api/motors/MTR-26001/genealogy")["lineage"]), 2)
        self.assertTrue(self.request("/api/motors/MTR-26001/provenance")[0]["hash"])
        self.assertIn(PID, self.request("/api/motors/MTR-26001/decisions"))
        self.assertTrue(self.request("/api/lots/BR-204/investigation")["components"])
        self.assertEqual(self.request("/api/notifications")[0]["deliveryStatus"], "NOT_SENT")

    def test_commands_require_local_token_and_no_cross_origin(self):
        for token, origin in ((None,None), (self.token,"https://example.com")):
            with self.assertRaises(HTTPError) as ctx:
                self.request("/api/units", {"serial":"MTR-HTTP-001"}, token, origin)
            self.assertEqual(ctx.exception.code, 403)
        result = self.request("/api/units", {"serial":"MTR-HTTP-001"}, self.token, self.base)
        self.assertGreater(result["captureToDecisionMs"], 0)
        d = result["snapshot"]["decisions"]["MTR-HTTP-001"][PID]["current"]
        self.assertEqual(d["operationalAction"], "RECALL_HOLD")
        with self.assertRaises(HTTPError) as ctx:
            self.request("/api/units/MTR-HTTP-001/verify", {}, self.token)
        self.assertEqual(ctx.exception.code,404)


if __name__ == "__main__":
    unittest.main()
