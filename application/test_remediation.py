"""Phase 3 safety-remediation regressions. Each test names the audit finding it closes (see docs/PHASE3_REMEDIATION.md)."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from application.service import Manufacturing, ValidationFailure, LedgerBlocked, RECALL_ID
from pramaan_integration import Ledger
from pramaan_integration.profile import digest

PID = RECALL_ID + "/P1"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "app.sqlite"
        self.app = Manufacturing(self.path)

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def current(self, motor):
        return self.app.snapshot()["decisions"][motor][PID]["current"]

    def history(self, motor):
        return self.app.snapshot()["decisions"][motor][PID]["history"]

    def fleet(self):
        """DE-only defective, NDE-only defective, and an unaffected control."""
        for m, de, nde in (("MTR-DEONLY", "BR-204", "BR-310"), ("MTR-NDEONLY", "BR-310", "BR-204"),
                           ("MTR-BOTH", "BR-204", "BR-204"), ("MTR-CLEAN", "BR-310", "BR-312")):
            self.app.create_unit(m); self.app.assemble(m, de, nde, "SERIAL"); self.app.ship(m)


class RecallScope(Base):
    """F-1 (P0): hardcoded DE-only scope released an NDE-only recalled lot."""

    def outcomes(self, slots):
        self.fleet()
        self.app.announce("BR-204", slots)
        return {m: self.current(m) for m in ("MTR-DEONLY", "MTR-NDEONLY", "MTR-BOTH", "MTR-CLEAN")}

    def test_nde_only_recalled_lot_is_held_under_nde_scope(self):
        d = self.outcomes(["NDE"])
        self.assertEqual(d["MTR-NDEONLY"]["evidenceFinding"], "AFFECTED")
        self.assertEqual(d["MTR-NDEONLY"]["operationalAction"], "RECALL_HOLD")
        self.assertEqual(d["MTR-DEONLY"]["evidenceFinding"], "EXCLUDED_WITH_EVIDENCE")
        self.assertEqual(d["MTR-BOTH"]["operationalAction"], "RECALL_HOLD")

    def test_nde_only_recalled_lot_is_held_under_both_slot_scope(self):
        d = self.outcomes(["DE", "NDE"])
        for m in ("MTR-DEONLY", "MTR-NDEONLY", "MTR-BOTH"):
            self.assertEqual(d[m]["operationalAction"], "RECALL_HOLD", m)
        self.assertEqual(d["MTR-CLEAN"]["evidenceFinding"], "EXCLUDED_WITH_EVIDENCE")

    def test_explicit_de_only_scope_is_preserved(self):
        d = self.outcomes(["DE"])
        self.assertEqual(d["MTR-DEONLY"]["operationalAction"], "RECALL_HOLD")
        self.assertEqual(d["MTR-BOTH"]["operationalAction"], "RECALL_HOLD")
        self.assertEqual(d["MTR-NDEONLY"]["evidenceFinding"], "EXCLUDED_WITH_EVIDENCE")  # explicitly out of scope
        self.assertEqual(self.app.policy()["affectedSlots"], ["DE"])

    def test_missing_or_unsupported_scope_fails_closed(self):
        self.fleet()
        for bad in (None, [], "DE", ["ROTOR"], ["DE", "DE"], ["de"], [1], {"DE": True}, ["DE", None]):
            with self.assertRaises(ValidationFailure, msg=repr(bad)):
                self.app.announce("BR-204", bad)
        with self.assertRaises(ValidationFailure):
            self.app.announce("BR-204")  # no default scope
        self.assertIsNone(self.app.policy())
        self.assertEqual(self.app.snapshot()["policies"], [])
        # No policy means nothing is released: unknown is not empty.
        self.assertNotIn(PID, self.app.snapshot()["decisions"]["MTR-NDEONLY"])

    def test_unsupported_scope_in_a_stored_policy_blocks_instead_of_releasing(self):
        self.fleet()
        policy = self.app.announce("BR-204", ["DE"])
        for slots in ([], ["ROTOR"], None):
            bad = dict(policy, affectedSlots=slots)
            with self.assertRaises(LedgerBlocked):
                self.app.ledger.decide("MTR-NDEONLY", bad, [self.app.ledger.watermark("MTR-NDEONLY")])

    def test_different_scope_for_same_lot_is_not_silently_accepted(self):
        self.app.announce("BR-204", ["DE"])
        with self.assertRaises(ValidationFailure):
            self.app.announce("BR-204", ["NDE"])
        self.assertEqual(self.app.announce("BR-204", ["DE"])["affectedSlots"], ["DE"])


class ObligationPersistence(Base):
    """F-2 (P0): the notification obligation vanished on the next evaluation."""

    def withdraw(self, m="MTR-OBL"):
        self.app.create_unit(m); self.app.announce("BR-204", ["DE"])
        self.app.assemble(m, "BR-204", "BR-310"); self.app.ship(m)
        self.current(m)
        self.app.replace(m, "BR-312")
        excluded = self.current(m)
        self.assertEqual(excluded["evidenceFinding"], "EXCLUDED_WITH_EVIDENCE")
        self.app.observe(m, "BR-204")
        return m, excluded

    def open_obligations(self, m=None):
        return [n for n in self.app.snapshot()["notifications"] if n["status"] == "OPEN" and (m is None or n["unitId"] == m)]

    def test_obligation_survives_repeated_evaluation_and_reopen(self):
        m, excluded = self.withdraw()
        first = self.open_obligations(m)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["appliesIfDecisionCommunicated"], excluded["decisionId"])
        for _ in range(3):
            self.app.snapshot()
        self.app.close(); self.app = Manufacturing(self.path)
        self.assertEqual(self.open_obligations(m), first)

    def test_obligation_survives_an_unrelated_later_event_that_keeps_the_hold(self):
        m, _ = self.withdraw()
        before = self.open_obligations(m)
        self.app.observe(m, "BR-310")  # another untrusted observation; the hold remains
        self.assertEqual(self.current(m)["operationalAction"], "RECALL_HOLD")
        self.assertEqual(self.open_obligations(m), before)

    def test_resolution_is_explicit_audited_and_not_a_delivery_acknowledgement(self):
        m, _ = self.withdraw()
        ob = self.open_obligations(m)[0]
        resolved = self.app.resolve_notification(ob["obligationId"], "CORRECTION_COMMUNICATED_ATTESTED", "Customer phoned 2026-10-21")
        self.assertEqual(resolved["status"], "RESOLVED")
        self.assertFalse(resolved["resolution"]["deliveryAcknowledged"])
        self.assertEqual(self.open_obligations(m), [])
        note = next(n for n in self.app.snapshot()["notifications"] if n["obligationId"] == ob["obligationId"])
        self.assertEqual(note["deliveryStatus"], "NOT_SENT")  # nothing was sent by this system
        with self.assertRaises(ValidationFailure):
            self.app.resolve_notification(ob["obligationId"], "CORRECTION_COMMUNICATED_ATTESTED", "again")
        self.app.snapshot()
        self.assertEqual(self.open_obligations(m), [])  # does not reappear
        log = self.app.db.execute("SELECT kind FROM obligation_events ORDER BY ordinal").fetchall()
        self.assertEqual([r["kind"] for r in log], ["CREATED", "RESOLVED"])

    def test_invalid_resolutions_are_refused(self):
        m, _ = self.withdraw()
        oid = self.open_obligations(m)[0]["obligationId"]
        for args in (("NOPE", "x"), ("CORRECTION_COMMUNICATED_ATTESTED", ""), ("CORRECTION_COMMUNICATED_ATTESTED", None)):
            with self.assertRaises(ValidationFailure):
                self.app.resolve_notification(oid, *args)
        with self.assertRaises(ValidationFailure):
            self.app.resolve_notification("OBL-unknown", "CORRECTION_COMMUNICATED_ATTESTED", "x")
        self.assertEqual(len(self.open_obligations(m)), 1)

    def test_obligation_log_is_append_only_and_hash_chained(self):
        self.withdraw()
        self.app.snapshot()
        for sql in ("UPDATE obligation_events SET kind='RESOLVED'", "DELETE FROM obligation_events"):
            with self.assertRaises(sqlite3.IntegrityError):
                self.app.db.execute(sql)
            self.app.db.rollback()
        for t in ("obligation_events_no_update", "obligation_events_no_delete"):
            self.app.db.execute(f"DROP TRIGGER {t}")
        self.app.db.execute("UPDATE obligation_events SET body=replace(body,'PRIOR_EXCLUSION_WITHDRAWN','TAMPERED')")
        self.app.db.commit()
        with self.assertRaises(LedgerBlocked):
            self.app.snapshot()


class DecisionRevisions(Base):
    """F-3 (P0): evidence/reason changes under an unchanged headline were dropped; stale bodies carried new watermarks."""

    def setUp(self):
        super().setUp()
        self.m = "MTR-REV"
        self.app.create_unit(self.m); self.app.announce("BR-204", ["DE"])
        self.app.assemble(self.m, "BR-204", "BR-310"); self.app.ship(self.m)

    def test_identical_repeated_evaluation_adds_no_version_or_run(self):
        self.current(self.m)
        runs = lambda: self.app.db.execute("SELECT count(*) FROM decision_runs").fetchone()[0]
        versions, count = len(self.history(self.m)), runs()
        for _ in range(4):
            self.app.snapshot()
        self.assertEqual((len(self.history(self.m)), runs()), (versions, count))

    def test_material_evidence_change_without_outcome_change_is_a_new_version(self):
        before = self.current(self.m)
        self.app.observe(self.m, "BR-204")  # untrusted claim: finding/action unchanged, evidence changed
        after = self.current(self.m)
        self.assertEqual((after["evidenceFinding"], after["operationalAction"]), (before["evidenceFinding"], before["operationalAction"]))
        self.assertNotEqual(after["decisionId"], before["decisionId"])
        self.assertEqual(after["supersedesDecisionId"], before["decisionId"])
        self.assertEqual(after["version"], before["version"] + 1)
        self.assertTrue(after["untrustedObservations"])
        self.assertEqual(len(self.history(self.m)), after["version"])

    def test_current_snapshot_content_matches_its_watermark(self):
        self.current(self.m)
        self.app.observe(self.m, "BR-310")  # unrelated claim; decide at the new watermark
        current = self.current(self.m)
        wm = self.app.ledger.watermark(self.m)
        bundle = self.app.ledger.decide(self.m, self.app.policy(), [wm])[0]
        fresh = self.app.ledger.snapshot(self.m, wm)[0]
        from pramaan_integration import engine_bridge
        direct = engine_bridge.evaluate(fresh, self.app.policy(), self.app.ledger._config(self.m)["coverage"], wm, engine_bridge.Config.v3())
        self.assertEqual(current["watermark"], direct["watermark"])
        for key in ("watermark", "evidenceEventIds", "evidenceRefs", "flags", "reasonCodes", "slots", "untrustedObservations"):
            self.assertEqual(bundle["decision"][key], direct[key], key)

    def test_issued_versions_replay_and_match_their_stored_outcome(self):
        self.current(self.m)
        self.app.observe(self.m, "BR-204")
        policy = self.app.policy()
        stored = json.loads(self.app.db.execute("SELECT payload FROM decision_runs WHERE motor=? ORDER BY ordinal DESC LIMIT 1", (self.m,)).fetchone()[0])
        for b in stored["bundles"]:
            replayed = self.app.ledger.replay(self.m, policy, b)
            for key in ("evidenceFinding", "operationalAction", "reviewRequired", "reasonCodes", "slots", "evidenceEventIds"):
                self.assertEqual(replayed[key], b["decision"][key], key)

    def test_policy_identity_change_is_not_merged_into_the_old_series(self):
        self.current(self.m)
        policy = self.app.policy()
        both = dict(policy, version=2, affectedSlots=["DE", "NDE"])
        wm = self.app.ledger.watermark(self.m)
        a = self.app.ledger.decide(self.m, policy, [wm])[0]["decision"]
        b = self.app.ledger.decide(self.m, both, [wm])[0]["decision"]
        self.assertNotEqual(a["lifecycleSignature"], b["lifecycleSignature"])


class HistoryIntegrity(Base):
    """F-3 (P0): whole-history deletion silently recreated v1."""

    def setUp(self):
        super().setUp()
        self.m = "MTR-HIST"
        self.app.create_unit(self.m); self.app.announce("BR-204", ["DE"])
        self.app.assemble(self.m, "BR-204", "BR-310"); self.app.ship(self.m)
        self.app.replace(self.m, "BR-312"); self.current(self.m)
        self.app.observe(self.m, "BR-204"); self.current(self.m)

    def strip(self, *tables):
        for t in tables:
            for a in ("update", "delete"):
                self.app.db.execute(f"DROP TRIGGER IF EXISTS {t}_no_{a}")

    def test_deleting_the_whole_decision_history_is_detected_not_recreated(self):
        self.strip("decision_runs")
        self.app.db.execute("DELETE FROM decision_runs"); self.app.db.commit()
        with self.assertRaises(LedgerBlocked):
            self.app.snapshot()
        self.assertEqual(self.app.db.execute("SELECT count(*) FROM decision_runs").fetchone()[0], 0)  # nothing recreated

    def test_editing_a_stored_run_is_detected(self):
        self.strip("decision_runs")
        self.app.db.execute("UPDATE decision_runs SET payload=replace(payload,'RECALL_HOLD','RELEASE_ELIGIBLE')"); self.app.db.commit()
        with self.assertRaises(LedgerBlocked):
            self.app.snapshot()

    def test_deleting_run_and_chain_is_caught_by_the_external_anchor(self):
        anchor = self.app.ledger.anchor()
        self.assertTrue(self.app.ledger.verify_anchor(anchor))
        self.strip("decision_runs", "decision_chain")
        self.app.db.execute("DELETE FROM decision_runs"); self.app.db.execute("DELETE FROM decision_chain"); self.app.db.commit()
        self.app.ledger.verify_decision_history()  # internally consistent (empty) ...
        with self.assertRaises(LedgerBlocked):      # ... but not an extension of what was anchored
            self.app.ledger.verify_anchor(anchor)

    def test_anchor_accepts_legitimate_growth(self):
        anchor = self.app.ledger.anchor()
        self.app.observe(self.m, "BR-310"); self.current(self.m)
        self.assertTrue(self.app.ledger.verify_anchor(anchor))

    def test_pre_chain_database_is_adopted_and_its_bundles_stay_replayable(self):
        policy = self.app.policy()
        stored = json.loads(self.app.db.execute("SELECT payload FROM decision_runs ORDER BY ordinal DESC LIMIT 1").fetchone()[0])
        self.strip("decision_chain")
        self.app.db.execute("DELETE FROM decision_chain"); self.app.db.commit()
        self.app.close(); self.app = Manufacturing(self.path)  # reopen adopts existing runs
        self.assertEqual(self.app.ledger.anchor()["links"], self.app.db.execute("SELECT count(*) FROM decision_runs").fetchone()[0])
        self.app.ledger.replay(self.m, policy, stored["bundles"][-1])


class LegacyLifecycle(Base):
    """F-3: a standing lifecycle-v1 run stays replayable as issued; v2 continues it as a new revision."""

    def test_v1_run_is_preserved_and_superseded_by_revision_2(self):
        from pramaan_integration import engine_bridge
        m = "MTR-LEG"
        self.app.create_unit(m); self.app.announce("BR-204", ["DE"])
        self.app.assemble(m, "BR-204", "BR-310"); self.app.ship(m)
        policy, ledger = self.app.policy(), self.app.ledger
        wm = ledger.watermark(m)
        case, manifest = ledger.snapshot(m, wm)
        legacy = engine_bridge.evaluate_series(case, policy, ledger._config(m)["coverage"], [wm], engine_bridge.Config.v3())
        bundles = [dict(decision=d, manifest=manifest, policyDigest=digest(policy)) for d in legacy]
        for b in bundles:
            b["bundleDigest"] = digest(b)
        payload = dict(watermarks=[wm], communicated=[], bundles=bundles)
        ledger.db.execute("INSERT INTO decision_runs(motor,policy_hash,payload,hash) VALUES(?,?,?,?)", (m, digest(policy), json.dumps(payload), digest(payload)))
        ledger._chain(m, digest(policy), ledger.db.execute("SELECT max(ordinal) FROM decision_runs").fetchone()[0], digest(payload))
        ledger.db.commit()
        issued = bundles[0]
        self.app.observe(m, "BR-204")
        current = self.current(m)
        self.assertEqual(current["lifecycleVersion"], 2)
        self.assertIn("-r2-", current["decisionId"])
        revision = self.app.snapshot()["decisions"][m][PID]["history"]
        self.assertEqual(revision[0]["supersedesDecisionId"], issued["decision"]["decisionId"])
        self.assertEqual(current["supersedesDecisionId"], revision[0]["decisionId"])
        ledger.replay(m, policy, issued)  # historical record untouched
        row = ledger.db.execute("SELECT payload FROM decision_runs ORDER BY ordinal LIMIT 1").fetchone()
        self.assertEqual(json.loads(row[0])["bundles"][0], issued)


class HttpRemediation(unittest.TestCase):
    def setUp(self):
        import threading
        from application.server import make_server
        self.tmp = tempfile.TemporaryDirectory()
        self.server = make_server(Path(self.tmp.name) / "http.sqlite", 0, False)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.token = ""
        self.token = self.call("/api/session")[1]["token"]

    def tearDown(self):
        self.server.shutdown(); self.thread.join(); self.server.server_close(); self.tmp.cleanup()

    def call(self, path, body=None):
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen
        req = Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                      headers={"Content-Type": "application/json", "X-Pramaan-Token": self.token, "Origin": self.base})
        try:
            with urlopen(req) as res:
                return res.status, json.load(res)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def test_recall_without_or_with_bad_scope_is_rejected_over_http_and_nothing_is_announced(self):
        for body in ({"lot": "BR-204"}, {"lot": "BR-204", "slots": []}, {"lot": "BR-204", "slots": ["ROTOR"]}, {"lot": "BR-204", "slots": "DE"}):
            status, result = self.call("/api/recalls", body)
            self.assertEqual(status, 400, body)
        self.assertEqual(self.call("/api/snapshot")[1]["recallAnnounced"], False)

    def test_nde_scope_over_http_holds_the_nde_only_motor(self):
        self.call("/api/units", {"serial": "MTR-HTTP-NDE"})
        self.call("/api/units/MTR-HTTP-NDE/assemble", {"deLot": "BR-310", "ndeLot": "BR-204", "identity": "SERIAL"})
        status, result = self.call("/api/recalls", {"lot": "BR-204", "slots": ["NDE"]})
        self.assertEqual(status, 200)
        d = result["snapshot"]["decisions"]["MTR-HTTP-NDE"][PID]["current"]
        self.assertEqual((d["evidenceFinding"], d["operationalAction"]), ("AFFECTED", "RECALL_HOLD"))
        self.assertEqual(result["snapshot"]["recall"]["affectedSlots"], ["NDE"])

    def test_heartbeat_integrity_and_snapshot_head_agree(self):
        status, beat = self.call("/api/heartbeat")
        self.assertEqual((status, beat["status"]), (200, "OK"))
        status, integ = self.call("/api/integrity")
        self.assertEqual((status, integ["status"]), (200, "VERIFIED"))
        snap = self.call("/api/snapshot")[1]
        self.assertEqual(snap["ledgerHead"], beat["ledgerHead"])
        self.assertTrue(snap["generatedAt"])

    def test_unknown_obligation_cannot_be_resolved(self):
        status, _ = self.call("/api/notifications/OBL-nope/resolve", {"resolution": "CORRECTION_COMMUNICATED_ATTESTED", "note": "x"})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
