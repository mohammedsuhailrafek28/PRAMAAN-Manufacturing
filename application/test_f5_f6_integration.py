"""F5 + F6 interaction tests on one synthetic evidence set (disposable ledgers, no network). Run: python -B -m unittest application.test_f5_f6_integration -v
Needs ci/requirements-hackathon-crypto.lock. Set F56_EVIDENCE=<file> to write measured results as JSON.

Scenario: factory A has its OWN local recall for lot BR-204 (v1.1 behaviour); supplier S then sends a signed alert for its label NSB-204 to A and B (F6); the factories answer with counts;
and each factory issues recipient-scoped, informational evidence packages (F5) from the same ledgers. These tests look for shared state, contradictory semantics and unsafe interaction.
They prove nothing about independent organizations, physical bearing identity or independent custody.
"""
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from . import evidence_package as P, evidence_verify as V
from .anchors import ledger_binding
from .federation import messages as M, staging as S, trust
from .federation.node import FactoryNode
from .service import Manufacturing
from . import service as svc
from .test_federation import NOW, ledger_state, node_for, snapshot_held, supplier_for, issue as issue_alert

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = {}
CUSTOMER, SUPPLIER_R, AUDITOR = "urn:demo:customer:pumpco", "urn:demo:supplier:northstar-bearings", "urn:demo:auditor:regulator"
W = {}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def store_digest(stage):
    import sqlite3
    db = sqlite3.connect(str(stage["root"] / "federation.sqlite"))
    try:
        return {t: db.execute(f"SELECT * FROM {t} ORDER BY 1,2").fetchall() for t in ("inbox", "hwm", "rejections", "adoptions", "outbox")}
    finally:
        db.close()


def f5_issue(stage, anchor, previous, motor, recipient, profile, **kw):
    return P.issue(database=stage["database"], anchor=anchor, previous_anchor=previous, motor=motor, recipient=recipient, profile=profile, key_path=W["f5key"],
                   lot_registry=stage["registry"], **kw)


def setUpModule():
    W["tmp"] = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    w = W["world"] = S.stage_world(W["tmp"].name)
    A, B = w["a"], w["b"]
    private, public = P.keygen(Path(W["tmp"].name) / "f5keys")
    W.update(f5key=private, f5pub=public)
    app = Manufacturing(A["database"], lot_registry=A["registry"])                      # factory A's OWN recall, before any federation message exists
    try:
        app.announce("BR-204", ["DE"]); app.snapshot()
    finally:
        app.close()
    W["a_anchor"], W["a_prev"] = S.checkpoint_cycle(A, A["anchor"], None, "scripted-custodian")
    sup = W["sup"] = supplier_for(w)
    path, body = W["alert"] = issue_alert(sup)
    W["nodes"] = {k: node_for(w, k) for k in "ab"}
    W["nodes"]["a"].set_checkpoint(W["a_anchor"], W["a_prev"])
    W["digest"] = {}
    for k, node in W["nodes"].items():
        W["digest"][k] = node.receive(path, NOW)["alertHash"]
    W["a_ledger_before_adopt"] = ledger_state(A)[0]
    W["a_adopt"] = W["nodes"]["a"].adopt(body["alertId"], "op-a", W["digest"]["a"][:12], NOW)
    W["a_ledger_after_adopt"] = ledger_state(A)[0]
    W["b_adopt"] = W["nodes"]["b"].adopt(body["alertId"], "op-b", W["digest"]["b"][:12], NOW)
    try:                                                                                 # F5 against B while B's ledger is newer than its checkpoint
        f5_issue(B, B["anchor"], None, "MTR-B-001", CUSTOMER, "customer")
        W["b_stale_issue"] = None
    except P.IssuanceRefused as exc:
        W["b_stale_issue"] = str(exc)
    W["b_anchor"], W["b_prev"] = S.checkpoint_cycle(B, B["anchor"], None, "scripted-custodian")
    W["nodes"]["b"].set_checkpoint(W["b_anchor"], W["b_prev"])
    W["resp"] = {k: node.respond(body["alertId"], NOW) for k, node in W["nodes"].items()}


def tearDownModule():
    out = os.environ.get("F56_EVIDENCE")
    if out:
        Path(out).write_text(json.dumps(EVIDENCE, indent=1, sort_keys=True, default=str), encoding="utf-8")
    for node in W["nodes"].values():
        node.close()
    W["tmp"].cleanup()


def anchors(k):
    return (W["a_anchor"], W["a_prev"]) if k == "a" else (W["b_anchor"], W["b_prev"])


class Sequencing(unittest.TestCase):
    def test_a_local_recall_then_the_supplier_alert_is_adopted_without_changing_the_ledger(self):
        self.assertTrue(W["a_adopt"]["adopted"], W["a_adopt"])
        self.assertEqual(W["a_ledger_before_adopt"], W["a_ledger_after_adopt"])             # same lot and slots: the existing announce is idempotent, nothing written
        self.assertEqual(W["resp"]["a"]["status"], "ANSWERED")                              # A was already ANCHORED_CURRENT: no extra cycle was needed
        self.assertEqual(W["resp"]["a"]["body"]["counts"]["heldMotors"], 2)
        EVIDENCE["localRecallThenAlert"] = "A: local recall + checkpoint; alert adopted idempotently; ledger rows identical before/after adoption; counts answered without another cycle"

    def test_a_different_local_recall_refuses_the_alert_scope_and_keeps_its_own(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            w = S.stage_world(d)
            app = Manufacturing(w["a"]["database"], lot_registry=w["a"]["registry"])
            try:
                app.announce("BR-310", ["DE"]); app.snapshot()
            finally:
                app.close()
            anchor, prev = S.checkpoint_cycle(w["a"], w["a"]["anchor"], None, "scripted-custodian")
            path, body = issue_alert(supplier_for(w))
            node = node_for(w, "a"); node.set_checkpoint(anchor, prev)
            r = node.receive(path, NOW)
            out = node.adopt(body["alertId"], "op", r["alertHash"][:12], NOW)
            self.assertEqual((out["adopted"], out["reason"]), (False, "ADOPTION_REFUSED"))
            app = Manufacturing(w["a"]["database"], lot_registry=w["a"]["registry"])
            try:
                self.assertEqual(app.policy()["affectedLots"], ["BR-310"])
            finally:
                app.close()
            node.close()

    def test_f5_issuance_is_refused_while_the_ledger_is_newer_than_the_checkpoint_after_adoption(self):
        self.assertIn("ANCHORED_PREFIX_ONLY", W["b_stale_issue"] or "")
        for profile, recipient in (("customer", CUSTOMER), ("supplier", SUPPLIER_R)):
            token = f5_issue(W["world"]["b"], *anchors("b"), "MTR-B-001", recipient, profile)             # after the existing cycle it works
            self.assertTrue(V.verify(token, issuer_key=W["f5pub"], recipient=recipient)["accepted"])
        EVIDENCE["staleThenCurrent"] = W["b_stale_issue"]


class OneEvidenceSet(unittest.TestCase):
    def packages(self, k, motor):
        stage = W["world"][k]
        anchor, prev = anchors(k)
        out = {}
        for profile, recipient in (("customer", CUSTOMER), ("supplier", SUPPLIER_R), ("auditor", AUDITOR)):
            out[profile] = f5_issue(stage, anchor, prev, motor, recipient, profile, authorize_event_row=profile == "auditor")
        return out

    def test_f5_packages_for_the_same_motors_the_factories_counted(self):
        matrix = {}
        for k, motor, lot in (("a", "MTR-A-001", "BR-204"), ("b", "MTR-B-001", "BR-771")):
            tokens = self.packages(k, motor)
            anchor, _ = anchors(k)
            customer = V.verify(tokens["customer"], issuer_key=W["f5pub"], recipient=CUSTOMER)
            supplier = V.verify(tokens["supplier"], issuer_key=W["f5pub"], recipient=SUPPLIER_R)
            auditor = V.verify(tokens["auditor"], issuer_key=W["f5pub"], recipient=AUDITOR, checkpoint=anchor)
            for result in (customer, supplier, auditor):
                self.assertTrue(result["accepted"], result["failure"])
                self.assertEqual((result["clearance"], result["checks"]["physicalProductTruth"]), ("NONE", "UNVERIFIED"))
                self.assertEqual(result["claims"]["operationalAction"], "RECALL_HOLD")
            self.assertEqual(supplier["claims"]["lot"], lot)
            self.assertEqual(supplier["claims"]["supplierId"], W["alert"][1]["lot"]["supplierId"])        # the same supplier id the F6 alert carried
            self.assertNotIn("motorSerial", supplier["claims"])
            self.assertTrue(auditor["checks"]["checkpointBinding"].startswith("CLAIMS_BOUND_TO_CHECKPOINT_ROW"))
            matrix[k] = dict(customerClaims=sorted(customer["claims"]), supplierLot=supplier["claims"]["lot"], auditorBinding=auditor["checks"]["checkpointBinding"][:30])
        EVIDENCE["sameMotorsF5andF6"] = matrix

    def test_a_clean_motor_gets_no_package_and_no_message_creates_eligibility(self):
        for k, clean in (("a", "MTR-A-002"), ("b", "MTR-B-002")):
            with self.assertRaises(P.IssuanceRefused) as cm:
                f5_issue(W["world"][k], *anchors(k), clean, CUSTOMER, "customer")
            self.assertIn("RELEASE_ELIGIBLE", str(cm.exception))
            snap, held = snapshot_held(W["world"][k], *anchors(k))
            affected = {f"MTR-{k.upper()}-001"} | ({"MTR-A-003"} if k == "a" else set())
            self.assertTrue(affected <= held)
            self.assertTrue(all(not snap["eligibility"][m]["currentReleaseEligible"] for m in affected))

    def test_identity_guard_hold_is_reported_by_both_features_without_becoming_clearance(self):
        token = f5_issue(W["world"]["b"], *anchors("b"), "MTR-B-003", CUSTOMER, "customer")
        result = V.verify(token, issuer_key=W["f5pub"], recipient=CUSTOMER)
        self.assertTrue(result["accepted"])
        self.assertEqual(result["claims"]["operationalAction"], "RECALL_HOLD")
        self.assertEqual(W["resp"]["b"]["body"]["counts"]["heldOnlyByIdentityGuard"], 1)
        EVIDENCE["guardHeldMotorInF5"] = dict(evidenceFinding=result["claims"]["evidenceFinding"], operationalAction=result["claims"]["operationalAction"],
                                              note="F5 states the frozen finding; the guard override is visible only in F6's count and in the evaluator's own decision")
        with self.assertRaises(P.IssuanceRefused):
            f5_issue(W["world"]["b"], *anchors("b"), "MTR-B-003", SUPPLIER_R, "supplier")          # no verified lot claim for an unestablished identity

    def test_issuing_and_verifying_f5_changes_neither_ledgers_checkpoints_nor_federation_stores(self):
        before = {k: (ledger_state(W["world"][k])[0], sha(anchors(k)[0]), store_digest(W["world"][k])) for k in "ab"}
        for k, motor in (("a", "MTR-A-001"), ("b", "MTR-B-001")):
            for profile, recipient in (("customer", CUSTOMER), ("supplier", SUPPLIER_R), ("auditor", AUDITOR)):
                V.verify(f5_issue(W["world"][k], *anchors(k), motor, recipient, profile), issuer_key=W["f5pub"], recipient=recipient)
        self.assertEqual({k: (ledger_state(W["world"][k])[0], sha(anchors(k)[0]), store_digest(W["world"][k])) for k in "ab"}, before)

    def test_f6_operations_leave_f5_keys_and_packages_alone(self):
        key_before = sha(W["f5key"])
        token = f5_issue(W["world"]["a"], *anchors("a"), "MTR-A-001", CUSTOMER, "customer")
        for node in W["nodes"].values():
            node.respond(W["alert"][1]["alertId"], NOW)
            node.receive(W["alert"][0], NOW)                                                    # replay: rejected and recorded
        self.assertEqual(sha(W["f5key"]), key_before)
        self.assertTrue(V.verify(token, issuer_key=W["f5pub"], recipient=CUSTOMER)["accepted"])


class Privacy(unittest.TestCase):
    def test_f6_channel_never_carries_what_f5_recipients_receive_and_vice_versa(self):
        f5_strings = {"MTR-A-001", "MTR-B-001", "BR-204", "BR-771", "urn:pramaan:MTR-A-001", "SUP-NSB-01"}
        f6_text = "".join(p.read_text() for k in "ab" for p in (W["world"][k]["root"] / "outbox").glob("*.json")) + W["sup"].state_path.read_text()
        for needle in f5_strings:
            self.assertNotIn(needle, f6_text, needle)
        for profile, recipient in (("customer", CUSTOMER), ("supplier", SUPPLIER_R)):
            token = f5_issue(W["world"]["a"], *anchors("a"), "MTR-A-001", recipient, profile)
            self.assertNotIn(W["alert"][1]["alertId"], token)
            decoded = token + "".join(json.dumps(V.b64u_decode(d)) if False else V.b64u_decode(d).decode() for d in token[:-1].split("~")[1:])
            for needle in (W["alert"][1]["alertId"], "NSB-204", "heldMotors", "federation", W["digest"]["a"]):
                self.assertNotIn(needle, decoded, needle)
        EVIDENCE["channelSeparation"] = "F6 responses/state contain none of the F5-disclosed identifiers; F5 customer/supplier packages contain no alert id, supplier label, counts or alert hash"

    def test_the_f5_supplier_package_discloses_a_local_lot_that_f6_deliberately_withholds(self):
        """Documented P2: two explicit, separate channels with different purposes. A factory that wants F6's minimal disclosure toward the supplier must not ALSO issue F5 supplier packages."""
        token = f5_issue(W["world"]["b"], *anchors("b"), "MTR-B-001", SUPPLIER_R, "supplier")
        self.assertEqual(V.verify(token, issuer_key=W["f5pub"], recipient=SUPPLIER_R)["claims"]["lot"], "BR-771")
        self.assertNotIn("BR-771", W["resp"]["b"]["path"].read_text())
        EVIDENCE["p2ChannelDifference"] = "F5 supplier package: local lot BR-771; F6 response: no lot"


class TrustBoundaries(unittest.TestCase):
    def test_one_key_used_by_both_features_still_gives_no_cross_protocol_acceptance(self):
        """Operator error worst case: the SAME Ed25519 key is the F5 issuer key and a pinned F6 factory/supplier key."""
        pem = Path(W["f5key"]).read_bytes()
        key, kid = M.load_private(pem)
        raw = key.public_key().public_bytes(__import__("cryptography").hazmat.primitives.serialization.Encoding.Raw, __import__("cryptography").hazmat.primitives.serialization.PublicFormat.Raw)
        f5_pub = json.loads(Path(W["f5pub"]).read_text())
        self.assertEqual(f5_pub["x"], M.b64u(raw))                                          # confirm it really is the same key
        d = Path(tempfile.mkdtemp(dir=W["tmp"].name))
        (d / "p.json").write_text(json.dumps(dict(id=S.SUPPLIER_ID, role="supplier", kid=kid, x=f5_pub["x"])))
        pinned = trust.load_trust(trust.write_trust(d / "t.json", [d / "p.json"]))
        token = f5_issue(W["world"]["a"], *anchors("a"), "MTR-A-001", CUSTOMER, "customer")
        env = M.sign(dict(W["alert"][1]), key, kid)                                         # a perfectly valid F6 alert under the shared key
        M.verify_envelope(env, pinned, expected_type="ALERT")                               # accepted by F6 (as designed)
        self.assertFalse(V.verify(json.dumps(env) if False else (V.b64u(json.dumps(env["body"]).encode()) + "." + V.b64u(b"{}") + "." + env["signature"] + "~"), issuer_key=W["f5pub"])["accepted"])
        with self.assertRaises(M.Rejection):                                                # an F5 package pasted into F6 is no envelope
            M.verify_envelope({"format": M.FORMAT, "kid": kid, "body": {"type": "ALERT"}, "signature": token.split("~")[0].split(".")[2]}, pinned, expected_type="ALERT")
        jws_signature = token.split("~")[0].split(".")[2]
        self.assertNotEqual(jws_signature, env["signature"])
        EVIDENCE["crossProtocol"] = "same key in both roles: F6 envelopes are not F5 packages and F5 signatures are not F6 envelope signatures (domain-separated signing inputs)"

    def test_trust_roots_are_separate_files_with_separate_keys(self):
        w = W["world"]
        f6_keys = {json.loads(Path(p[1]).read_text())["x"] for p in w["keys"].values()}
        self.assertNotIn(json.loads(Path(W["f5pub"]).read_text())["x"], f6_keys)

    def test_neither_feature_imports_the_other_and_global_state_is_restored(self):
        app_dir = ROOT / "application"
        for name in ("evidence_package.py", "evidence_verify.py"):
            self.assertNotIn("federation", (app_dir / name).read_text(encoding="utf-8"), name)
        for path in (app_dir / "federation").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("evidence_package", text, path.name); self.assertNotIn("evidence_verify", text, path.name)
        self.assertIsNone(svc.DEFAULT_LOT_REGISTRY)                                         # F6 staging's temporary registry selector never leaks
        self.assertNotIn("federation", (app_dir / "server.py").read_text(encoding="utf-8"))
        self.assertNotIn("evidence_", (app_dir / "server.py").read_text(encoding="utf-8"))

    def test_the_only_ledger_write_in_either_feature_is_announce(self):
        import re
        calls = {}
        for path in [ROOT / "application" / "evidence_package.py", ROOT / "application" / "evidence_verify.py"] + sorted((ROOT / "application" / "federation").glob("*.py")):
            if path.name == "staging.py":
                continue
            for name in re.findall(r"\bapp\.(\w+)\(", path.read_text(encoding="utf-8")):
                calls.setdefault(name, set()).add(path.name)
        self.assertLessEqual(set(calls), {"announce", "clock", "close", "snapshot"})            # clock is a read-only getter used by F5 for registry resolution
        self.assertEqual(calls.get("announce"), {"node.py"})                                   # the single write path is F6's operator-gated adoption

    def test_f5_notices_and_f6_notices_both_deny_independent_authentication_and_clearance(self):
        from .federation import TRUST_NOTICE
        self.assertIn("NOT independent company authentication", TRUST_NOTICE)
        self.assertIn("Not a release clearance", V.NOTICE)
        self.assertEqual(V.ACTIONS_ISSUABLE, ("RECALL_HOLD",))
        self.assertEqual(set(M.FINDINGS), set(V.FINDINGS))                                  # both features use the same frozen evaluator vocabulary


if __name__ == "__main__":
    unittest.main()
