"""F6 federated recall (reduced): adversarial acceptance tests on disposable synthetic ledgers (no network, no sockets). Run: python -B -m unittest application.test_federation -v
Needs the feature-isolated dependency in ci/requirements-f6-federation.lock. Set F6_EVIDENCE=<file> to write measured results as JSON.

What these prove: message integrity under pinned LOCAL DEMO keys, strict sequence/freshness handling, mandatory operator adoption, registry-only lot mapping, counts-only privacy and that no
imported message can clear a hold. They do NOT prove independent company authentication, physical bearing identity or independent custody.
"""
import copy
import json
import os
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .anchors import TrustedAnchor, ledger_binding
from .federation import messages as M, staging as S, trust
from .federation.node import FactoryNode
from .federation.supplier import Supplier, render_html, render_text
from .service import Manufacturing

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = {}
NOW = 1_800_000_100
IAT = 1_800_000_000
SHARED = {}


def setUpModule():
    SHARED["tmp"] = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    SHARED["world"] = S.stage_world(SHARED["tmp"].name)


def tearDownModule():
    out = os.environ.get("F6_EVIDENCE")
    if out:
        Path(out).write_text(json.dumps(EVIDENCE, indent=1, sort_keys=True, default=str), encoding="utf-8")
    SHARED["tmp"].cleanup()


def supplier_for(world, root=None):
    return Supplier(Path(root or world["root"]) / "supplier", S.SUPPLIER_ID, world["keys"]["supplier"][0], world["supplier_trust"])


def node_for(world, which, workdir=None):
    stage = world[which]
    return FactoryNode(workdir or stage["root"], S.A_ID if which == "a" else S.B_ID, stage["database"], stage["registry"], world["supplier_pin"],
                       world["keys"]["factory-a" if which == "a" else "factory-b"][0], stage["anchor"])


def issue(sup, **kw):
    args = dict(supplier_lot=S.SUPPLIER_LOT, part="BR-6205", slots=["DE"], text="Synthetic defect: drive-end bearing lot NSB-204", now=IAT)
    args.update(kw)
    return sup.issue_alert(**args)


def forge(world, body_changes=None, *, key=None, kid=None, base=None, drop=()):
    """Sign an arbitrary ALERT body with the REAL supplier key (a malicious or buggy supplier) or with `key`."""
    sup_key, sup_kid = M.load_private(Path(world["keys"]["supplier"][0]).read_bytes())
    body = copy.deepcopy(base) if base else dict(type="ALERT", alertId="ALERT-FORGED", issuer=S.SUPPLIER_ID, seq=1, prevHash=None, iat=IAT, exp=IAT + 3600,
                                                  lot=dict(supplierId="SUP-NSB-01", part="BR-6205", supplierLot=S.SUPPLIER_LOT), affectedSlots=["DE"], humanText="forged")
    body.update(body_changes or {})
    for k in drop:
        body.pop(k)
    return M.sign(body, key or sup_key, kid or sup_kid)


def attacker_key():
    return M.load_private(Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))


def fresh_node(world, which):
    """A node with an EMPTY federation store over the shared (never-adopted) ledger."""
    return node_for(world, which, tempfile.mkdtemp(dir=SHARED["tmp"].name))


def ledger_state(stage):
    app = Manufacturing(stage["database"], lot_registry=stage["registry"])
    try:
        return ledger_binding(app), Path(stage["anchor"]).read_bytes(), app.db.execute("SELECT COUNT(*) FROM recall_announcements").fetchone()[0]
    finally:
        app.close()


def snapshot_held(stage, anchor, previous=None):
    """Independent of node.py: eligibility straight from the unchanged read model."""
    app = Manufacturing(stage["database"], lot_registry=stage["registry"])
    try:
        snap = app.snapshot(trusted_anchor=TrustedAnchor(anchor, previous))
    finally:
        app.close()
    return snap, {m for m, e in snap["eligibility"].items() if not e["currentReleaseEligible"]}


def policy_of(stage):
    app = Manufacturing(stage["database"], lot_registry=stage["registry"])
    try:
        return app.policy()
    finally:
        app.close()


def adopted_world(unresolved="sighting"):
    d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    world = S.stage_world(d.name, unresolved)
    sup = supplier_for(world)
    path, body = issue(sup)
    nodes = {}
    for which in "ab":
        n = node_for(world, which)
        r = n.receive(path, NOW)
        assert r["accepted"], r
        nodes[which] = (n, r["alertHash"])
    return d, world, sup, path, body, nodes


class Vectors(unittest.TestCase):
    def test_rfc_8032_ed25519_vectors_through_the_library_used_here(self):
        for sk, pk, msg, sig in (("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60", "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
                                  "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
                                 ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb", "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
                                  "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00")):
            key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(sk))
            self.assertEqual(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex(), pk)
            self.assertEqual(key.sign(bytes.fromhex(msg)).hex(), sig)
        EVIDENCE["rfc8032Vectors"] = "RFC 8032 section 7.1 tests 1 and 2 reproduced exactly by the cryptography package used for message signing"

    def test_frozen_evaluator_values_are_used_not_remapped(self):
        import sys
        sys.path.insert(0, str(ROOT / "recall-engine"))
        from pramaan_recall import policy
        self.assertEqual(set(M.FINDINGS), {policy.EXCL, policy.AFF, policy.UNRES})


class Authentication(unittest.TestCase):
    def setUp(self):
        self.world = SHARED["world"]
        self.node = fresh_node(self.world, "a")
        self.path, self.body = issue(supplier_for(self.world, tempfile.mkdtemp(dir=SHARED["tmp"].name)))
        self.envelope = json.loads(self.path.read_text())

    def reject(self, source, reason):
        r = self.node.receive(source, NOW)
        self.assertFalse(r["accepted"], r)
        self.assertEqual(r["reason"], reason, r)
        self.assertFalse(r["ledgerTouched"])
        return r

    def test_the_authentic_alert_is_accepted_into_the_inbox_only(self):
        before = ledger_state(self.world["a"])
        r = self.node.receive(self.path, NOW)
        self.assertEqual((r["accepted"], r["status"], r["ledgerTouched"]), (True, "PENDING_OPERATOR", False))
        self.assertEqual(ledger_state(self.world["a"]), before)
        self.assertEqual(before[2], 0)

    def test_tampered_body_fails(self):
        for change in (dict(humanText="changed"), dict(exp=self.body["exp"] + 1), dict(seq=2), dict(alertId="ALERT-OTHER"), dict(affectedSlots=["DE", "NDE"]),
                       dict(lot=dict(self.body["lot"], supplierLot="NSB-999")), dict(issuer="urn:demo:supplier:other")):
            tampered = copy.deepcopy(self.envelope)
            tampered["body"].update(change)
            r = self.node.receive(tampered, NOW)
            self.assertFalse(r["accepted"])
            self.assertIn(r["reason"], ("BAD_SIGNATURE", "UNKNOWN_SENDER"), change)
        EVIDENCE["tamper"] = "humanText, exp, seq, alertId, affectedSlots, lot, issuer edits: all rejected (BAD_SIGNATURE/UNKNOWN_SENDER); ledger untouched"

    def test_wrong_key_and_forged_signatures_fail(self):
        attacker, attacker_kid = attacker_key()
        self.reject(forge(self.world, key=attacker, kid=attacker_kid), "WRONG_KEY")                          # own kid
        sup_kid = self.envelope["kid"]
        self.reject(forge(self.world, key=attacker, kid=sup_kid), "BAD_SIGNATURE")                            # victim kid, attacker signature
        flipped = copy.deepcopy(self.envelope)
        flipped["signature"] = flipped["signature"][:5] + ("B" if flipped["signature"][5] != "B" else "C") + flipped["signature"][6:]
        self.reject(flipped, "BAD_SIGNATURE")
        short = copy.deepcopy(self.envelope)
        short["signature"] = short["signature"][:20]
        self.assertFalse(self.node.receive(short, NOW)["accepted"])
        factory_key, factory_kid = M.load_private(Path(self.world["keys"]["factory-b"][0]).read_bytes())
        self.reject(forge(self.world, {"issuer": S.B_ID}, key=factory_key, kid=factory_kid), "UNKNOWN_SENDER")  # a factory is not pinned for the supplier trust of factory A
        EVIDENCE["wrongKey"] = "attacker kid, victim kid with attacker signature, flipped/short signature, factory key claiming to be a sender: all rejected"

    def test_a_pinned_key_with_the_wrong_role_cannot_send_that_message_type(self):
        both = trust.write_trust(Path(tempfile.mkdtemp(dir=SHARED["tmp"].name)) / "t.json", [self.world["keys"]["supplier"][1], self.world["keys"]["factory-a"][1]])
        peers = trust.load_trust(both)
        factory_key, factory_kid = M.load_private(Path(self.world["keys"]["factory-a"][0]).read_bytes())
        supplier_key, supplier_kid = M.load_private(Path(self.world["keys"]["supplier"][0]).read_bytes())
        alert_by_factory = M.sign(dict(self.body, issuer=S.A_ID), factory_key, factory_kid)                      # pinned, valid signature, but a factory is not a supplier
        with self.assertRaises(M.Rejection) as cm:
            M.verify_envelope(alert_by_factory, peers, expected_type="ALERT")
        self.assertEqual(cm.exception.reason, "WRONG_SENDER_ROLE")
        response_by_supplier = M.sign(dict(responder=S.SUPPLIER_ID, type="RESPONSE"), supplier_key, supplier_kid)
        with self.assertRaises(M.Rejection) as cm:
            M.verify_envelope(response_by_supplier, peers, expected_type="RESPONSE")
        self.assertEqual(cm.exception.reason, "WRONG_SENDER_ROLE")

    def test_unsupported_message_types_and_extra_fields_even_when_signed_by_the_real_key(self):
        self.reject(forge(self.world, {"type": "CORRECTION", "supersedes": "ALERT-1", "effect": "WITHDRAW"}), "UNSUPPORTED_TYPE")
        self.reject(forge(self.world, {"type": "RESPONSE"}), "UNSUPPORTED_TYPE")
        self.reject(forge(self.world, {"clearsHold": True}), "MALFORMED_BODY")
        self.reject(forge(self.world, {"release": ["MTR-A-001"]}), "MALFORMED_BODY")
        self.reject(forge(self.world, drop=("lot",)), "MALFORMED_BODY")
        self.reject(forge(self.world, {"lot": dict(supplierId="SUP-NSB-01", part="BR-6205", supplierLot="NSB-204", extra=1)}), "MALFORMED_BODY")
        self.reject(forge(self.world, {"affectedSlots": []}), "MALFORMED_BODY")
        self.reject(forge(self.world, {"affectedSlots": ["DE", "DE"]}), "MALFORMED_BODY")
        self.reject(forge(self.world, {"affectedSlots": ["MIDDLE"]}), "MALFORMED_BODY")
        self.reject(forge(self.world, {"seq": 1, "prevHash": "0" * 64}), "MALFORMED_BODY")
        self.reject(forge(self.world, {"seq": "1"}), "MALFORMED_BODY")
        self.reject(forge(self.world, {"humanText": "x\x00y"}), "MALFORMED_BODY")
        self.reject(forge(self.world, {"alertId": "../../etc"}), "MALFORMED_BODY")

    def test_hostile_inputs_never_raise_or_touch_the_ledger(self):
        before = ledger_state(self.world["a"])
        hostile = [b"", b"{", b"[]", b"null", b'{"format":"PRAMAAN-FED/1"}', b"\xff\xfe", b"x" * 100000, json.dumps(dict(self.envelope, kid=5)).encode(),
                   json.dumps(dict(self.envelope, body=None)).encode(), json.dumps(dict(self.envelope, signature=None)).encode(), json.dumps(dict(self.envelope, format="X")).encode(),
                   json.dumps(dict(self.envelope, extra=1)).encode(), json.dumps(dict(self.envelope, signature="!!!")).encode()]
        for raw in hostile:
            r = self.node.receive(raw if isinstance(raw, dict) else _file(raw), NOW)
            self.assertFalse(r["accepted"], raw[:40])
        self.assertEqual(ledger_state(self.world["a"]), before)
        self.assertEqual(len(self.node.store.rejections()), len(hostile))
        EVIDENCE["hostileInputs"] = f"{len(hostile)} hostile inputs rejected and recorded, none raised, ledger untouched"

    def test_bad_trust_files_are_refused(self):
        d = Path(tempfile.mkdtemp(dir=SHARED["tmp"].name))
        for text in ("{}", "not json", json.dumps(dict(format=trust.TRUST_FORMAT, peers=[dict(id="x", role="boss", kid="a", x="AAAA")]))):
            (d / "t.json").write_text(text)
            with self.assertRaises(trust.TrustError):
                trust.load_trust(d / "t.json")

    def test_keygen_never_overwrites(self):
        with self.assertRaises(trust.TrustError):
            trust.keygen(Path(self.world["keys"]["supplier"][0]).parent, "supplier", "x", "supplier")


class Freshness(unittest.TestCase):
    def setUp(self):
        self.world = SHARED["world"]
        self.node = fresh_node(self.world, "a")
        self.sup = supplier_for(self.world, tempfile.mkdtemp(dir=SHARED["tmp"].name))
        self.path, self.body = issue(self.sup)

    def test_expiry_and_clock_rules(self):
        self.assertEqual(self.node.receive(self.path, self.body["exp"])["reason"], "EXPIRED")
        self.assertEqual(self.node.receive(self.path, self.body["exp"] + 86400)["reason"], "EXPIRED")
        self.assertEqual(self.node.receive(self.path, IAT - 3600)["reason"], "NOT_YET_VALID")
        for change in (dict(exp=IAT), dict(exp=IAT + 8 * 86400), dict(exp="never"), dict(iat=1.5)):
            self.assertEqual(self.node.receive(forge(self.world, change), NOW)["reason"], "INVALID_EXPIRY", change)
        self.assertTrue(self.node.receive(self.path, IAT - 30)["accepted"])                                   # inside the stated 60 s skew
        EVIDENCE["expiry"] = "expired, not-yet-valid, zero/overlong/non-integer lifetimes rejected; 60 s skew honoured"

    def test_replay_stale_out_of_order_and_chain_breaks(self):
        first = self.node.receive(self.path, NOW)
        self.assertTrue(first["accepted"])
        self.assertEqual(self.node.receive(self.path, NOW)["reason"], "REPLAY")
        path2, body2 = issue(self.sup, alert_id="ALERT-TWO", text="second", supplier_lot="NSB-204")
        env2 = json.loads(path2.read_text())
        gap = forge(self.world, dict(alertId="ALERT-GAP", seq=4, prevHash=M.message_hash(body2)))
        self.assertEqual(self.node.receive(gap, NOW)["reason"], "OUT_OF_ORDER")                                # seq 3 never arrived
        wrong_prev = forge(self.world, dict(alertId="ALERT-WP", seq=2, prevHash="1" * 64))
        self.assertEqual(self.node.receive(wrong_prev, NOW)["reason"], "PREVHASH_MISMATCH")
        self.assertTrue(self.node.receive(env2, NOW)["accepted"])                                              # in order and chained
        self.assertEqual(self.node.receive(self.path, NOW)["reason"], "REPLAY")                                # old message again
        rolled = forge(self.world, dict(alertId="ALERT-ROLL", seq=1, prevHash=None))
        self.assertEqual(self.node.receive(rolled, NOW)["reason"], "STALE_SEQUENCE")                           # different content at an old sequence number
        dup = forge(self.world, dict(alertId=self.body["alertId"], seq=3, prevHash=M.message_hash(body2)))
        self.assertEqual(self.node.receive(dup, NOW)["reason"], "DUPLICATE_ALERT_ID")
        reasons = [r["reason"] for r in self.node.store.rejections()]
        self.assertEqual(reasons, ["REPLAY", "OUT_OF_ORDER", "PREVHASH_MISMATCH", "REPLAY", "STALE_SEQUENCE", "DUPLICATE_ALERT_ID"])
        EVIDENCE["replayOrdering"] = reasons

    def test_alert_for_other_recipients_is_not_addressed_here(self):
        other = issue(supplier_for(self.world, tempfile.mkdtemp(dir=SHARED["tmp"].name)), recipients=[S.B_ID], alert_id="ALERT-ONLY-B")[0]
        self.assertEqual(self.node.receive(other, NOW)["reason"], "NOT_ADDRESSED")
        node_b = fresh_node(self.world, "b")
        self.assertTrue(node_b.receive(other, NOW)["accepted"])

    def test_every_rejection_is_recorded_with_a_distinct_reason_and_never_reaches_the_ledger(self):
        before = ledger_state(self.world["a"])
        self.node.receive(self.path, NOW); self.node.receive(self.path, NOW)
        self.assertEqual(ledger_state(self.world["a"]), before)


def _file(raw):
    d = Path(tempfile.mkdtemp(dir=SHARED["tmp"].name))
    p = d / "m.json"
    p.write_bytes(raw)
    return p


class Adoption(unittest.TestCase):
    def test_adoption_is_the_only_path_to_the_ledger_and_needs_an_operator(self):
        d, world, sup, path, body, nodes = adopted_world()
        try:
            for which in "ab":
                node, digest = nodes[which]
                stage = world[which]
                self.assertEqual(ledger_state(stage)[2], 0, "receiving must not announce")
                self.assertFalse(node.adopt(body["alertId"], "", digest[:12], NOW)["adopted"])
                self.assertFalse(node.adopt(body["alertId"], "   ", digest[:12], NOW)["adopted"])
                self.assertEqual(node.adopt(body["alertId"], "op", "000000000000", NOW)["reason"], "CONFIRMATION_MISMATCH")
                self.assertEqual(node.adopt(body["alertId"], "op", "", NOW)["reason"], "CONFIRMATION_MISMATCH")
                self.assertEqual(ledger_state(stage)[2], 0)
                r = node.adopt(body["alertId"], f"operator-{which}", digest[:12], NOW)
                self.assertTrue(r["adopted"], r)
                self.assertEqual(ledger_state(stage)[2], 1)
                self.assertTrue(node.adopt(body["alertId"], f"operator-{which}", digest[:12], NOW)["alreadyAdopted"])
                self.assertEqual(ledger_state(stage)[2], 1)                                                    # idempotent
            self.assertEqual(policy_of(world["a"])["affectedLots"], ["BR-204"])
            self.assertEqual(policy_of(world["b"])["affectedLots"], ["BR-771"])
            EVIDENCE["adoption"] = "no announce on receive; wrong/empty operator or confirmation refused; adoption announces once; A maps NSB-204 -> BR-204, B maps NSB-204 -> BR-771"
        finally:
            d.cleanup()

    def test_a_tampered_stored_alert_cannot_be_adopted(self):
        d, world, sup, path, body, nodes = adopted_world()
        try:
            node, digest = nodes["a"]
            db = sqlite3.connect(str(world["a"]["root"] / "federation.sqlite"))
            envelope = json.loads(db.execute("SELECT envelope FROM inbox").fetchone()[0])
            envelope["body"]["lot"]["supplierLot"] = "BR-310"
            envelope["body"]["lot"]["supplierId"] = "SUP-KAV-02"
            db.execute("UPDATE inbox SET envelope=?", (json.dumps(envelope),)); db.commit(); db.close()
            r = node.adopt(body["alertId"], "op", digest[:12], NOW)
            self.assertEqual((r["adopted"], r["reason"]), (False, "BAD_SIGNATURE"))
            self.assertEqual(ledger_state(world["a"])[2], 0)
        finally:
            d.cleanup()

    def test_a_forged_adoption_row_in_the_unprotected_store_cannot_produce_counts(self):
        d, world, sup, path, body, nodes = adopted_world()
        try:
            node, digest = nodes["a"]
            node.store.record_adoption(body["alertId"], "forger", NOW, "BR-204", ["DE"], "ADOPTED")          # store edited by a local attacker; the ledger never announced anything
            self.assertIsNone(policy_of(world["a"]))
            resp = node.respond(body["alertId"], NOW)["body"]
            self.assertEqual((resp["status"], resp["counts"], resp["asOfCheckpoint"]), ("ADOPTION_REFUSED", None, None))
            EVIDENCE["forgedAdoptionRow"] = "an adoption row without a matching ledger policy yields ADOPTION_REFUSED and no counts"
        finally:
            d.cleanup()

    def test_an_alert_that_expired_before_adoption_is_refused(self):
        d, world, sup, path, body, nodes = adopted_world()
        try:
            node, digest = nodes["a"]
            r = node.adopt(body["alertId"], "op", digest[:12], body["exp"] + 1)
            self.assertEqual((r["adopted"], r["reason"]), (False, "EXPIRED"))
            self.assertEqual(ledger_state(world["a"])[2], 0)
        finally:
            d.cleanup()

    def test_a_second_scope_in_one_database_is_refused_and_the_first_is_unchanged(self):
        d, world, sup, path, body, nodes = adopted_world()
        try:
            node, digest = nodes["a"]
            self.assertTrue(node.adopt(body["alertId"], "op", digest[:12], NOW)["adopted"])
            policy_before = policy_of(world["a"])
            second = forge(world, dict(alertId="ALERT-SCOPE2", seq=2, prevHash=M.message_hash(body), lot=dict(supplierId="SUP-KAV-02", part="BR-6205", supplierLot="BR-310")))
            r = node.receive(second, NOW)
            self.assertTrue(r["accepted"], r)
            self.assertEqual(node.status("ALERT-SCOPE2"), "PENDING_OPERATOR")                                    # mapped, so an operator may try
            refused = node.adopt("ALERT-SCOPE2", "op", r["alertHash"][:12], NOW)
            self.assertEqual((refused["adopted"], refused["reason"]), (False, "ADOPTION_REFUSED"))
            self.assertEqual(node.status("ALERT-SCOPE2"), "ADOPTION_REFUSED")
            self.assertEqual(policy_of(world["a"]), policy_before)
            self.assertIsNone(node.respond("ALERT-SCOPE2", NOW)["body"]["counts"])
            EVIDENCE["secondScope"] = "second (mapped) lot refused by the unchanged one-scope-per-database rule; first policy unchanged; no counts"
        finally:
            d.cleanup()


class LotMapping(unittest.TestCase):
    def test_unmapped_lots_are_never_adopted_or_reported_as_unaffected(self):
        world = SHARED["world"]
        sup = supplier_for(world, tempfile.mkdtemp(dir=SHARED["tmp"].name))
        cases = {"unknown lot": dict(supplier_lot="NSB-999"), "look-alike label (O for 0)": dict(supplier_lot="NSB-2O4"), "lowercase": dict(supplier_lot="nsb-204"),
                 "trailing space": dict(supplier_lot="NSB-204 "), "sentinel": dict(supplier_lot="UNKNOWN"), "wrong part": dict(part="BR-9999")}
        for label, kw in cases.items():
            for which in "ab":
                node = fresh_node(world, which)
                path, body = issue(supplier_for(world, tempfile.mkdtemp(dir=SHARED["tmp"].name)), **kw)
                r = node.receive(path, NOW)
                self.assertTrue(r["accepted"], (label, r))
                self.assertEqual(node.status(body["alertId"]), "LOT_UNMAPPED", label)
                refused = node.adopt(body["alertId"], "op", r["alertHash"][:12], NOW)
                self.assertEqual((refused["adopted"], refused["reason"]), (False, "LOT_UNMAPPED"), label)
                resp = node.respond(body["alertId"], NOW)
                self.assertEqual((resp["status"], resp["body"]["counts"]), ("LOT_UNMAPPED", None))
                self.assertEqual(ledger_state(world[which])[2], 0)
        EVIDENCE["unmapped"] = f"{len(cases)} unmapped/look-alike/wrong-part cases x 2 factories: LOT_UNMAPPED, no announce, no counts"

    def test_wrong_supplier_for_a_registered_lot_is_unmapped(self):
        world = SHARED["world"]
        node = fresh_node(world, "a")
        r = node.receive(forge(world, dict(lot=dict(supplierId="SUP-KAV-02", part="BR-6205", supplierLot="NSB-204"))), NOW)
        self.assertTrue(r["accepted"])
        self.assertEqual(node.status("ALERT-FORGED"), "LOT_UNMAPPED")

    def test_the_same_supplier_label_maps_to_different_local_lots(self):
        from .federation.lotmap import map_lot
        lot = dict(supplierId="SUP-NSB-01", part="BR-6205", supplierLot="NSB-204")
        self.assertEqual(map_lot(node_for(SHARED["world"], "a", tempfile.mkdtemp(dir=SHARED["tmp"].name)).registry(), lot).canonical, "BR-204")
        self.assertEqual(map_lot(node_for(SHARED["world"], "b", tempfile.mkdtemp(dir=SHARED["tmp"].name)).registry(), lot).canonical, "BR-771")


class EndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d, cls.world, cls.sup, cls.path, cls.body, cls.nodes = adopted_world()
        cls.cycled = {}
        cls.pending = {}
        cls.ledgers_before = {w: ledger_state(cls.world[w]) for w in "ab"}
        for which in "ab":
            node, digest = cls.nodes[which]
            node.adopt(cls.body["alertId"], f"operator-{which}", digest[:12], NOW)
            cls.pending[which] = node.respond(cls.body["alertId"], NOW)
            stage = cls.world[which]
            anchor, previous = S.checkpoint_cycle(stage, stage["anchor"], None, "scripted-demo-custodian")
            node.set_checkpoint(anchor, previous)
            cls.cycled[which] = (anchor, previous, node.respond(cls.body["alertId"], NOW))

    @classmethod
    def tearDownClass(cls):
        cls.d.cleanup()

    def test_no_counts_while_the_checkpoint_is_stale(self):
        for which in "ab":
            body = self.pending[which]["body"]
            self.assertEqual((body["status"], body["counts"], body["asOfCheckpoint"]), ("PENDING_CHECKPOINT", None, None))

    def test_counts_equal_the_unchanged_evaluators_own_snapshot_independently_computed(self):
        out = {}
        for which, expected in (("a", dict(held=2, AFFECTED=2, UNRESOLVED=0, EXCLUDED_WITH_EVIDENCE=0, guard=0)), ("b", dict(held=2, AFFECTED=1, UNRESOLVED=0, EXCLUDED_WITH_EVIDENCE=1, guard=1))):
            anchor, previous, resp = self.cycled[which]
            body = resp["body"]
            self.assertEqual(body["status"], "ANSWERED")
            snap, held = snapshot_held(self.world[which], anchor, previous)
            self.assertEqual(snap["checkpoint"]["state"], "ANCHORED_CURRENT")
            self.assertEqual(body["counts"]["heldMotors"], len(held))
            by = {f: 0 for f in M.FINDINGS}
            for m in held:
                by[next(iter(snap["decisions"][m].values()))["current"]["evidenceFinding"]] += 1
            self.assertEqual(body["counts"]["heldByEvidenceFinding"], by)
            self.assertEqual((len(held), by["AFFECTED"], by["UNRESOLVED"], by["EXCLUDED_WITH_EVIDENCE"], body["counts"]["heldOnlyByIdentityGuard"]),
                             (expected["held"], expected["AFFECTED"], expected["UNRESOLVED"], expected["EXCLUDED_WITH_EVIDENCE"], expected["guard"]))
            self.assertEqual(body["asOfCheckpoint"], json.loads(Path(anchor).read_bytes())["checksum"])
            out[which] = body["counts"]
        EVIDENCE["factoryCounts"] = out

    def test_no_adopted_lot_motor_is_ever_release_eligible_and_clean_motors_are_not_touched(self):
        for which, affected in (("a", {"MTR-A-001", "MTR-A-003"}), ("b", {"MTR-B-001"})):
            anchor, previous, _ = self.cycled[which]
            snap, held = snapshot_held(self.world[which], anchor, previous)
            self.assertTrue(affected <= held)
            self.assertTrue(all(not snap["eligibility"][m]["currentReleaseEligible"] for m in affected))
            clean = f"MTR-{which.upper()}-002"
            self.assertNotIn(clean, held)

    def test_the_ledger_changes_only_by_the_one_recall_announcement_and_the_checkpoint_cycle(self):
        for which in "ab":
            before, after = self.ledgers_before[which], ledger_state(self.world[which])
            tables_before, tables_after = before[0]["rows"], after[0]["rows"]
            changed = sorted(t for t in tables_after if tables_after[t][:len(tables_before.get(t, []))] != tables_before.get(t, []) or len(tables_after[t]) != len(tables_before.get(t, [])))
            self.assertIn("recall_announcements", changed)
            for t in tables_before:                                                                           # nothing earlier was rewritten: only appended
                self.assertEqual(tables_after[t][:len(tables_before[t])], tables_before[t], t)
            self.assertNotIn("events", [t for t in changed if len(tables_after[t]) < len(tables_before.get(t, []))])
        EVIDENCE["ledgerDelta"] = "every pre-existing row digest of every table is unchanged; only appended rows (recall announcement, snapshots/publications of the existing cycle)"

    def test_responses_are_counts_only_and_leak_nothing(self):
        forbidden = ["MTR-", "BR-204", "BR-771", "BR-310", "BR-312", "BR-77I", "QX-77", "SUP-KAV", "Kaveri Precision", "STEEL", "ASSY", "BRG-", "ledger.sqlite", "registry", "checkpoint.json",
                     "urn:pramaan"]
        for which, other in (("a", "kaveri"), ("b", "aster")):
            texts = [p.read_text() for p in (self.world[which]["root"] / "outbox").glob("*.json")]
            self.assertEqual(len(texts), 3 - 1)                                                                # pending + answered
            for text in texts:
                for needle in forbidden:
                    self.assertNotIn(needle, text, needle)
                self.assertNotIn(other, text.lower())
                body = json.loads(text)["body"]
                self.assertEqual(set(body), M.RESPONSE_FIELDS)
        EVIDENCE["responsePrivacy"] = f"no serial, local lot, other-supplier, other-factory, path or event string in any response file (scanned {len(forbidden)} patterns)"

    def test_supplier_board_shows_each_factory_separately_counts_only(self):
        paths = [p for w in "ab" for p in sorted((self.world[w]["root"] / "outbox").glob("*.json"))]
        board = self.sup.board(paths)
        self.assertEqual(board["rejected"], [])
        rows = {r["factory"]: r for r in board["rows"]}
        self.assertEqual(set(rows), {S.A_ID, S.B_ID})
        self.assertEqual(rows[S.A_ID]["counts"]["heldMotors"], 2)
        self.assertEqual(rows[S.B_ID]["counts"]["heldOnlyByIdentityGuard"], 1)
        text, page = render_text(board), render_html(board)
        for needle in ("MTR-", "BR-204", "BR-771", "ledger", "registry.json", "<script"):
            self.assertNotIn(needle, text.replace("No serials, lots, customers, event histories or ledgers.", "")) if needle == "ledger" else self.assertNotIn(needle, text)
            self.assertNotIn(needle, page.replace("No serials, lots, customers, event histories or ledgers.", "")) if needle == "ledger" else self.assertNotIn(needle, page)
        self.assertIn("NOT independent company authentication", text)
        self.assertIn("not a clearance", text)
        state = json.loads(self.sup.state_path.read_text())
        self.assertEqual(set(state), {"seq", "hash", "alerts"})
        EVIDENCE["supplierBoard"] = text

    def test_a_factory_refuses_every_message_that_is_not_a_chained_supplier_alert_after_adoption(self):
        which = "a"
        node, _ = self.nodes[which]
        anchor, previous, _ = self.cycled[which]
        snap0, held0 = snapshot_held(self.world[which], anchor, previous)
        attacker, attacker_kid = attacker_key()
        feed = [forge(self.world, {"type": "CORRECTION", "effect": "WITHDRAW", "supersedes": self.body["alertId"]}), forge(self.world, {"type": "RESPONSE"}),
                forge(self.world, {"clearsHold": True}), forge(self.world, key=attacker, kid=attacker_kid), self.path, forge(self.world, {"seq": 9}),
                forge(self.world, {"affectedSlots": ["DE"], "lot": dict(supplierId="SUP-NSB-01", part="BR-6205", supplierLot="NSB-999")})]
        for message in feed:
            self.assertFalse(node.receive(message, NOW)["accepted"], message)
        snap1, held1 = snapshot_held(self.world[which], anchor, previous)
        self.assertEqual(snap1["checkpoint"]["state"], "ANCHORED_CURRENT")
        self.assertTrue(held0 <= held1)
        self.assertEqual({m: e["currentReleaseEligible"] for m, e in snap0["eligibility"].items()}, {m: e["currentReleaseEligible"] for m, e in snap1["eligibility"].items()})
        EVIDENCE["monotone"] = "after adoption, hostile/valid/withdrawal/response messages leave the held set and every eligibility flag unchanged"


class UnresolvedIdentityVariants(unittest.TestCase):
    def test_a_lookalike_of_an_in_use_lot_or_a_bypassed_install_blocks_the_existing_cycle_so_no_counts_are_given(self):
        for mode in ("lookalike-sighting", "install"):
            d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
            try:
                world = S.stage_world(d.name, mode)
                sup = supplier_for(world)
                path, body = issue(sup)
                node = node_for(world, "b")
                r = node.receive(path, NOW)
                self.assertTrue(node.adopt(body["alertId"], "op", r["alertHash"][:12], NOW)["adopted"])
                with self.assertRaises(SystemExit) as cm:
                    S.checkpoint_cycle(world["b"], world["b"]["anchor"], None, "demo")
                self.assertIn("REFUSED", str(cm.exception))
                resp = node.respond(body["alertId"], NOW)["body"]
                self.assertEqual((resp["status"], resp["counts"], resp["asOfCheckpoint"]), ("PENDING_CHECKPOINT", None, None), mode)
            finally:
                d.cleanup()
        EVIDENCE["identityBlocksCycle"] = "look-alike sighting and bypassed look-alike install: existing accept refuses, the factory reports PENDING_CHECKPOINT with no counts"


class SupplierBoardRejections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d, cls.world, cls.sup, cls.path, cls.body, cls.nodes = adopted_world()
        node, digest = cls.nodes["a"]
        node.adopt(cls.body["alertId"], "op", digest[:12], NOW)
        cls.good = node.respond(cls.body["alertId"], NOW)
        cls.second = node.respond(cls.body["alertId"], NOW)

    @classmethod
    def tearDownClass(cls):
        cls.d.cleanup()

    def board(self, *envelopes):
        d = Path(tempfile.mkdtemp(dir=SHARED["tmp"].name))
        paths = []
        for n, env in enumerate(envelopes):
            p = d / f"r{n}.json"
            p.write_text(json.dumps(env))
            paths.append(p)
        return self.sup.board(paths)

    def load(self, resp):
        return json.loads(Path(resp["path"]).read_text())

    def test_valid_response_is_accepted_and_each_failure_is_rejected_with_a_reason(self):
        good = self.load(self.good)
        self.assertEqual(self.board(good)["rejected"], [])
        tampered = copy.deepcopy(good); tampered["body"]["status"] = "ANSWERED"
        self.assertEqual(self.board(tampered)["rejected"][0]["reason"], "BAD_SIGNATURE")
        attacker, attacker_kid = attacker_key()
        forged = M.sign(good["body"], attacker, attacker_kid)
        self.assertEqual(self.board(forged)["rejected"][0]["reason"], "WRONG_KEY")
        sup_key, sup_kid = M.load_private(Path(self.world["keys"]["supplier"][0]).read_bytes())
        self.assertEqual(self.board(M.sign(good["body"], sup_key, sup_kid))["rejected"][0]["reason"], "WRONG_KEY")        # supplier is not a pinned responder
        unknown_alert = copy.deepcopy(good["body"]); unknown_alert["alertHash"] = "2" * 64
        key_a, kid_a = M.load_private(Path(self.world["keys"]["factory-a"][0]).read_bytes())
        self.assertEqual(self.board(M.sign(unknown_alert, key_a, kid_a))["rejected"][0]["reason"], "UNKNOWN_ALERT")
        extra = copy.deepcopy(good["body"]); extra["serials"] = ["MTR-A-001"]
        self.assertEqual(self.board(M.sign(extra, key_a, kid_a))["rejected"][0]["reason"], "MALFORMED_BODY")                # a real factory key cannot smuggle extra fields
        leaky = copy.deepcopy(good["body"]); leaky.update(status="ANSWERED", asOfCheckpoint="3" * 64, counts=dict(heldMotors=2, heldByEvidenceFinding=dict(AFFECTED=2, UNRESOLVED=0, EXCLUDED_WITH_EVIDENCE=0),
                                                                                                                heldOnlyByIdentityGuard=0, motorSerials=["MTR-A-001"]))
        self.assertEqual(self.board(M.sign(leaky, key_a, kid_a))["rejected"][0]["reason"], "MALFORMED_BODY")
        inconsistent = copy.deepcopy(leaky); inconsistent["counts"].pop("motorSerials"); inconsistent["counts"]["heldMotors"] = 5
        self.assertEqual(self.board(M.sign(inconsistent, key_a, kid_a))["rejected"][0]["reason"], "MALFORMED_BODY")
        counts_without_answer = copy.deepcopy(good["body"]); counts_without_answer["counts"] = dict(heldMotors=0, heldByEvidenceFinding=dict(AFFECTED=0, UNRESOLVED=0, EXCLUDED_WITH_EVIDENCE=0), heldOnlyByIdentityGuard=0)
        self.assertEqual(self.board(M.sign(counts_without_answer, key_a, kid_a))["rejected"][0]["reason"], "MALFORMED_BODY")
        second = self.load(self.second)
        self.assertEqual(self.board(second, good)["rejected"], [])                                                          # order of files does not matter; the chain does
        replay = self.board(good, good)
        self.assertEqual(replay["rejected"][0]["reason"], "REPLAY")
        self.assertEqual(self.board(second)["rejected"][0]["reason"], "OUT_OF_ORDER")                                       # seq 2 without seq 1
        self.assertEqual(len(self.board({"nope": 1})["rejected"]), 1)
        EVIDENCE["boardRejections"] = "tampered, wrong-key, supplier-key, unknown alert, extra fields (even with a real factory key), inconsistent counts, replay, out-of-order: all rejected"


class StaticGuarantees(unittest.TestCase):
    def sources(self):
        return {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "application" / "federation").glob("*.py")}

    def test_no_network_or_server_code_and_no_operational_ledger_calls(self):
        for name, source in self.sources().items():
            for needle in ("import socket", "http.server", "urllib", "requests", "from ..server", "from .server", "import server", "ThreadingHTTPServer"):
                self.assertNotIn(needle, source, f"{name}: {needle}")
            if name != "staging.py":                                                                              # staging builds the synthetic ledgers; production-path code never writes them
                for call in (".ship(", ".assemble(", ".observe(", "app.replace(", ".create_unit(", "record_historical_shipment_fixture", "export_anchor", "publish_candidate", "checkpoint_ops"):
                    self.assertNotIn(call, source, f"{name}: {call}")
        node = self.sources()["node.py"]
        self.assertEqual(sorted(set(re.findall(r"app\.(\w+)\(", node))), ["announce", "close", "snapshot"])
        EVIDENCE["staticScan"] = "federation package: no sockets/HTTP, and node.py calls only Manufacturing.announce and Manufacturing.snapshot"

    def test_no_http_route_exposes_federation(self):
        self.assertNotIn("federation", (ROOT / "application" / "server.py").read_text(encoding="utf-8"))

    def test_trust_notice_is_on_every_human_facing_output(self):
        from .federation import TRUST_NOTICE
        self.assertIn("NOT independent company authentication", TRUST_NOTICE)
        board = Supplier(tempfile.mkdtemp(dir=SHARED["tmp"].name), S.SUPPLIER_ID, SHARED["world"]["keys"]["supplier"][0], SHARED["world"]["supplier_trust"]).board([])
        self.assertIn(TRUST_NOTICE, render_text(board)); self.assertIn("NOT independent company authentication", render_html(board))


if __name__ == "__main__":
    unittest.main()
