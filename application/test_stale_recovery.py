"""Restricted stale-checkpoint recovery workflow (research prototype; owner decision 2 on FORMAT_V3). Disposable synthetic DBs, loopback only.
Run: python -B -m unittest application.test_stale_recovery -v     Set RECOVERY_EVIDENCE=<file> to write the measured results as JSON.

The recovery surface allows evidence capture, controlled replacement and the PROPOSAL of a successor checkpoint. It has no route for shipment, release,
announcement, unit creation, assembly, acceptance or activation, and it returns no decision or eligibility. These tests prove those properties at the HTTP
boundary; operator acceptance stays offline (checkpoint_ops.accept) and is not independent custody.
"""
import json
import os
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from . import checkpoint_ops
from . import server as server_mod
from .anchors import export_anchor, publish_candidate
from .service import Manufacturing
from .test_lot_identity_ab import decision, RECALLED, SAFE

A, S = "MTR-92001", "MTR-92002"
EVIDENCE = {}
FORBIDDEN_KEYS = {"operationalAction", "evaluatorOperationalAction", "evidenceFinding", "currentReleaseEligible", "eligibility", "decisions"}


def keys(obj, out=None):
    out = set() if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k); keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            keys(v, out)
    return out


def world(d):
    db, c0, custody = Path(d) / "r.sqlite", Path(d) / "c0.json", Path(d) / "custody"
    app = Manufacturing(db)
    for m in (A, S):
        app.create_unit(m); app.assemble(m, SAFE, "BR-312"); app.record_historical_shipment_fixture(m)
    app.announce(RECALLED, ["DE"]); app.snapshot()
    publish_candidate(c0, export_anchor(app)); app.close()
    return db, c0, custody


class Client:
    def __init__(self, srv):
        self.base = f"http://127.0.0.1:{srv.server_port}"

    def call(self, path, body=None, token=True):
        if body is None:
            req = Request(self.base + path)
        else:
            headers = {"Content-Type": "application/json"}
            if token:
                headers["X-Pramaan-Token"] = json.load(urlopen(self.base + "/api/session"))["token"]
            req = Request(self.base + path, json.dumps(body).encode(), headers)
        try:
            with urlopen(req) as r:
                return r.status, json.load(r)
        except HTTPError as e:
            return e.code, json.load(e)


@contextmanager
def serving(db, anchor, previous=None, custody=None):
    srv = server_mod.make_server(db, 0, trusted_anchor=anchor, previous_anchor=previous, custody_dir=custody)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield Client(srv)
    finally:
        srv.shutdown(); srv.server_close()


def journal(db):
    app = Manufacturing(db)
    try:
        return app.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    finally:
        app.close()


class Recovery(unittest.TestCase):
    def test_not_applicable_while_current_or_unanchored(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            with serving(db, c0, custody=custody) as c:
                self.assertEqual(c.call("/api/recovery")[1]["error"], "RECOVERY_NOT_APPLICABLE")
                n = journal(db)
                self.assertEqual(c.call("/api/recovery/observe", dict(motor=S, lot="ZZ-9"))[0], 409)
                self.assertEqual(journal(db), n)                                                       # nothing written
            srv = server_mod.make_server(db, 0)                                                         # no anchor at all
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                self.assertEqual(Client(srv).call("/api/recovery")[1]["error"], "RECOVERY_REQUIRES_ANCHOR")
            finally:
                srv.shutdown(); srv.server_close()

    def test_surface_is_whitelisted_and_leaks_no_decision_or_eligibility(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            with serving(db, c0, custody=custody) as c:
                self.assertEqual(c.call(f"/api/units/{S}/observe", dict(lot="ZZ-9"))[0], 200)            # ordinary capture moves the ledger past the checkpoint
                s, body = c.call("/api/recovery")
                self.assertEqual(s, 200); r = body["recovery"]
                self.assertEqual(r["checkpoint"]["state"], "ANCHORED_PREFIX_ONLY"); self.assertEqual(r["allowedActions"], ["observe", "replace", "propose"])
                self.assertEqual([h["motor"] for h in r["heldMotors"]], [S]); self.assertEqual(r["heldMotors"][0]["quarantine"]["clearance"], "NEVER_IMPLIED")
                self.assertEqual(keys(body) & FORBIDDEN_KEYS, set())
                n = journal(db)
                for action in ("ship", "announce", "create-unit", "assemble", "accept", "accept-checkpoint", "activate", "release", "authorize-shipment", ""):
                    self.assertEqual(c.call("/api/recovery/" + action, dict(motor=S, lot="BR-312"))[0], 404, action)
                self.assertEqual(c.call("/api/recovery/observe")[0], 404)                                # GET on an action
                self.assertEqual(c.call("/api/recovery/observe/extra", dict(motor=S, lot="x"))[0], 404)
                self.assertEqual(c.call("/api/recovery/observe", dict(motor=S, lot="ZZ-8"), token=False)[0], 403)   # same session-token guard as every mutation
                self.assertEqual(c.call("/api/recovery/observe", dict(motor="MTR-NOPE", lot="ZZ-8"))[0], 400)
                self.assertEqual(c.call("/api/recovery/observe", dict(motor=S, lot="x" * 90))[0], 400)
                self.assertEqual(journal(db), n)                                                         # every refused call wrote nothing
                EVIDENCE["whitelist"] = dict(refused=["ship", "announce", "create-unit", "assemble", "accept", "accept-checkpoint", "activate", "release", "authorize-shipment"], leakedKeys=[])

    def test_recovery_capture_and_proposal_never_make_anything_eligible_or_activate_anything(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            with serving(db, c0, custody=custody) as c:
                c.call(f"/api/units/{S}/observe", dict(lot="ZZ-9"))
                s, body = c.call("/api/recovery/replace", dict(motor=S, lot="BR-312", slot="DE"))        # reconciliation of the sighted slot
                self.assertEqual(s, 200); self.assertEqual(keys(body) & FORBIDDEN_KEYS, set())
                s, body = c.call("/api/recovery/propose", {})
                self.assertEqual(s, 200); self.assertEqual(body["proposal"]["status"], "CANDIDATE_PROPOSED_NOT_ACTIVATED")
                self.assertEqual(keys(body["recovery"]) & FORBIDDEN_KEYS, set())
                self.assertTrue(Path(body["proposal"]["candidate"]).is_file()); self.assertFalse((custody / "accepted").exists())
                snap = c.call("/api/snapshot")[1]                                                         # the running server is unchanged: still stale, nothing eligible
                self.assertEqual(snap["checkpoint"]["state"], "ANCHORED_PREFIX_ONLY")
                self.assertTrue(all(not v["currentReleaseEligible"] for v in snap["eligibility"].values()))
                self.assertEqual(c.call(f"/api/motors/{A}/decisions")[1]["error"], "CHECKPOINT_REQUIRED")
                EVIDENCE["proposalOnly"] = dict(status=body["proposal"]["status"], accepted=False, serverStillStale=True)

    def test_propose_needs_configured_custody(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, _ = world(d)
            with serving(db, c0, custody=None) as c:
                c.call(f"/api/units/{S}/observe", dict(lot="ZZ-9"))
                self.assertEqual(c.call("/api/recovery/propose", {}), (409, {"error": "CUSTODY_NOT_CONFIGURED", "decisionsUnavailable": True}))

    def test_full_recovery_cycle_restores_eligibility_only_through_operator_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            with serving(db, c0, custody=custody) as c:
                c.call(f"/api/units/{S}/observe", dict(lot="ZZ-9"))
                c.call("/api/recovery/replace", dict(motor=S, lot="BR-312", slot="DE"))
                prop = c.call("/api/recovery/propose", {})[1]["proposal"]
            self.assertEqual(prop["review"]["refusedForIdentity"], [])
            rec = checkpoint_ops.accept(db, c0, custody, Path(prop["candidate"]), "synthetic reviewer", prop["candidateSha256"], prop["review"]["requiresAcknowledgement"],
                                        acknowledge_registry=prop["review"]["registry"]["digest"] if prop["review"]["registryChange"]["requiresAcknowledgement"] else None)
            with serving(db, rec["accepted"], c0, custody) as c:
                snap = c.call("/api/snapshot")[1]
                self.assertEqual(snap["checkpoint"]["state"], "ANCHORED_CURRENT")
                self.assertEqual({m: v["currentReleaseEligible"] for m, v in snap["eligibility"].items()}, {A: True, S: True})     # superseded sighting: replaced bearing, reviewed checkpoint
                self.assertEqual(c.call("/api/recovery")[1]["error"], "RECOVERY_NOT_APPLICABLE")
            EVIDENCE["fullCycle"] = dict(eligibleOnlyAfterOperatorAcceptance=True)

    def test_recovery_cannot_release_a_motor_whose_sighting_is_still_open(self):
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            with serving(db, c0, custody=custody) as c:
                c.call(f"/api/units/{S}/observe", dict(lot="ZZ-9"))                                      # ordinary capture makes the checkpoint stale
                self.assertEqual(c.call("/api/recovery/observe", dict(motor=S, lot="ZZ-8"))[0], 200)       # a second sighting captured through the recovery surface
                prop = c.call("/api/recovery/propose", {})[1]["proposal"]
            self.assertEqual(prop["review"]["containedMotors"], [S])
            rec = checkpoint_ops.accept(db, c0, custody, Path(prop["candidate"]), "synthetic reviewer", prop["candidateSha256"], prop["review"]["requiresAcknowledgement"],
                                        acknowledge_registry=prop["review"]["registry"]["digest"] if prop["review"]["registryChange"]["requiresAcknowledgement"] else None)
            with serving(db, rec["accepted"], c0, custody) as c:
                snap = c.call("/api/snapshot")[1]
                self.assertEqual({m: v["currentReleaseEligible"] for m, v in snap["eligibility"].items()}, {A: True, S: False})
                self.assertEqual(decision(snap, S)["operationalAction"], "RECALL_HOLD")
                self.assertEqual(c.call(f"/api/motors/{S}/decisions")[1]["eligibility"]["currentReleaseEligible"], False)

    def test_the_ordinary_ship_route_refuses_while_the_checkpoint_is_stale(self):
        """Formerly a documented gap (the route recorded a shipment fact while stale). Owner-approved fix: the ordinary route is gated on a current checkpoint
        and current release eligibility; see test_ship_gate for the full matrix."""
        with tempfile.TemporaryDirectory() as d:
            db, c0, custody = world(d)
            app = Manufacturing(db); app.create_unit("MTR-92009"); app.assemble("MTR-92009", SAFE, "BR-312"); app.close()
            with serving(db, c0, custody=custody) as c:
                snap = c.call("/api/snapshot")[1]
                self.assertEqual(snap["checkpoint"]["state"], "ANCHORED_PREFIX_ONLY")
                self.assertFalse(snap["eligibility"]["MTR-92009"]["currentReleaseEligible"])
                s, body = c.call("/api/units/MTR-92009/ship", {})
                self.assertEqual(s, 409)                                                               # refused, not merely ungranted
                self.assertNotIn("snapshot", body)
                app = Manufacturing(db)
                try:
                    self.assertFalse(any(e["eventType"] == "MOTOR_SHIPPED" for e in app.events("MTR-92009")))
                finally:
                    app.close()
                EVIDENCE["shipRouteStale"] = dict(status=s, shipmentRecorded=False)


def tearDownModule():
    out = os.environ.get("RECOVERY_EVIDENCE")
    if out:
        Path(out).write_text(json.dumps(EVIDENCE, indent=1, sort_keys=True, default=str), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
