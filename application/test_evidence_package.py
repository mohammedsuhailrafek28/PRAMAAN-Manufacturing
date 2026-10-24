"""F5 portable evidence packages: adversarial acceptance tests (synthetic ledgers, loopback-free, disposable). Run: python -B -m unittest application.test_evidence_package -v
Needs the feature-isolated dependency in ci/requirements-f5-evidence.lock. Set F5_EVIDENCE=<file> to write the measured disclosure matrix and results as JSON.

These tests prove cryptographic and disclosure properties of the package. They do not (and cannot) prove physical bearing identity, independent custody, freshness or that a
package was never revoked; the verifier reports those as UNVERIFIED / UNKNOWN and the tests assert that it does.
"""
import base64
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from . import evidence_package as P
from . import evidence_verify as V
from .anchors import export_anchor, ledger_binding, publish_candidate
from .service import Manufacturing
from .test_lot_identity_ab import raw_assemble

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = {}
CUSTOMER, SUPPLIER, AUDITOR = "urn:demo:customer:pumpco", "urn:demo:supplier:northstar", "urn:demo:auditor:regulator"
AFFECTED, CLEAN, UNRESOLVED, LOOKALIKE = "MTR-DEMO-2", "MTR-DEMO-1", "MTR-26005", "MTR-DEMO-4"
FIXTURE = {}


def build_world(d):
    d = Path(d)
    db, anchor = d / "ledger.sqlite", d / "checkpoint.json"
    app = Manufacturing(db)
    app.seed_demo()                                                       # MTR-26005 carries an untrusted observation of the affected lot (UNRESOLVED)
    for serial, de in ((CLEAN, "BR-310"), (AFFECTED, "BR-204")):
        app.create_unit(serial); app.assemble(serial, de, "BR-312")
    app.create_unit(LOOKALIKE); raw_assemble(app, LOOKALIKE, "BR-2O4", "BR-312")      # a look-alike of the recalled lot: identity not established
    app.snapshot()
    publish_candidate(anchor, export_anchor(app))
    app.close()
    private, public = P.keygen(d / "keys")
    return db, anchor, private, public


def setUpModule():
    FIXTURE["tmp"] = tempfile.TemporaryDirectory()
    db, anchor, private, public = build_world(FIXTURE["tmp"].name)
    FIXTURE.update(db=db, anchor=anchor, private=private, public=public)
    FIXTURE["attacker"] = P.keygen(Path(FIXTURE["tmp"].name) / "attacker")
    FIXTURE["tokens"] = {}
    for profile, recipient in (("customer", CUSTOMER), ("supplier", SUPPLIER), ("auditor", AUDITOR)):
        FIXTURE["tokens"][profile] = issue(profile, recipient, AFFECTED, authorize_event_row=profile == "auditor")


def tearDownModule():
    out = os.environ.get("F5_EVIDENCE")
    if out:
        Path(out).write_text(json.dumps(EVIDENCE, indent=1, sort_keys=True, default=str), encoding="utf-8")
    FIXTURE["tmp"].cleanup()


def issue(profile, recipient, motor=AFFECTED, **kw):
    return P.issue(database=FIXTURE["db"], anchor=FIXTURE["anchor"], motor=motor, recipient=recipient, profile=profile, key_path=FIXTURE["private"], **kw)


def check(token, recipient=None, **kw):
    kw.setdefault("issuer_key", FIXTURE["public"])
    return V.verify(token, recipient=recipient, **kw)


def parts(token):
    jwt, *disclosures = token[:-1].split("~")
    h, p, s = jwt.split(".")
    return json.loads(V.b64u_decode(h)), json.loads(V.b64u_decode(p)), s, disclosures


def decode_disclosure(text):
    return json.loads(V.b64u_decode(text))


def reassemble(header, payload, signature, disclosures, *, resign=None):
    h = V.b64u(json.dumps(header, separators=(",", ":")).encode())
    p = V.b64u(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
    if resign:
        key, _ = P.load_private(resign)
        signature = V.b64u(key.sign((h + "." + p).encode("ascii")))
    return f"{h}.{p}.{signature}~" + "".join(d + "~" for d in disclosures)


def forge(*, claims=None, profile="customer", aud=CUSTOMER, payload=None, header=None, key=None, extra_disclosures=(), now=None, digests_extra=()):
    """A package signed by `key` (default: the REAL issuer key, i.e. a malicious or buggy issuer) with arbitrary content, to test what the verifier refuses."""
    private = key or FIXTURE["private"]
    signer, kid = P.load_private(private)
    entries = {n: P._disclosure(n, v) for n, v in (claims or {}).items()}
    checkpoint = json.loads(Path(FIXTURE["anchor"]).read_bytes())
    iat = 1_800_000_000 if now is None else now
    body = dict(iss=P.DEFAULT_ISSUER, aud=aud, iat=iat, exp=iat + 3600, jti="forged-jti", _sd_alg="sha-256",
                _sd=sorted([d for _, d in entries.values()] + list(digests_extra) + [V.b64u(hashlib.sha256(os.urandom(8)).digest()) for _ in range(6)]),
                format=V.FORMAT, profile=profile, purpose=V.PURPOSE, binding=dict(checkpointChecksum=checkpoint["checksum"], checkpointFormat=checkpoint["body"]["format"], state="ANCHORED_CURRENT"))
    body.update(payload or {})
    head = dict(alg="EdDSA", typ=V.TYP, kid=kid)
    head.update(header or {})
    h = V.b64u(json.dumps(head, separators=(",", ":")).encode())
    p = V.b64u(json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode())
    sig = V.b64u(signer.sign((h + "." + p).encode("ascii")))
    return f"{h}.{p}.{sig}~" + "".join([t for t, _ in entries.values()] + list(extra_disclosures)).replace("~", "") .join(["", ""]) if False else \
        f"{h}.{p}.{sig}~" + "".join(t + "~" for t, _ in entries.values()) + "".join(t + "~" for t in extra_disclosures)


NOW = 1_800_000_100            # inside the forged tokens' window (iat 1_800_000_000, 1 h)
GOOD_CUSTOMER = dict(motorSerial=AFFECTED, recallId="RC-026-014", evidenceFinding="AFFECTED", operationalAction="RECALL_HOLD")


class CryptoVectors(unittest.TestCase):
    def test_rfc_8032_ed25519_vectors(self):
        vectors = [("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60", "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
                    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
                   ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb", "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
                    "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00")]
        for sk, pk, msg, sig in vectors:
            key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(sk))
            self.assertEqual(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex(), pk)
            self.assertEqual(key.sign(bytes.fromhex(msg)).hex(), sig)
        EVIDENCE["rfc8032Vectors"] = "TEST 1 and TEST 2 (RFC 8032 section 7.1): public key and signature reproduced exactly"

    def test_rfc_9901_disclosure_and_digest_vectors(self):
        vectors = [("WyJfMjZiYzRMVC1hYzZxMktJNmNCVzVlcyIsICJmYW1pbHlfbmFtZSIsICJNw7ZiaXVzIl0", ["_26bc4LT-ac6q2KI6cBW5es", "family_name", "Möbius"], "X9yH0Ajrdm1Oij4tWso9UzzKJvPoDxwmuEcO3XAdRC0"),
                   ("WyIyR0xDNDJzS1F2ZUNmR2ZyeU5STjl3IiwgImdpdmVuX25hbWUiLCAiSm9obiJd", ["2GLC42sKQveCfGfryNRN9w", "given_name", "John"], "jsu9yVulwQQlhFlM_3JlzMaSFzglhQG0DpfayQwLUK4"),
                   ("WyI2SWo3dE0tYTVpVlBHYm9TNXRtdlZBIiwgImVtYWlsIiwgImpvaG5kb2VAZXhhbXBsZS5jb20iXQ", ["6Ij7tM-a5iVPGboS5tmvVA", "email", "johndoe@example.com"], "JzYjH4svliH0R3PyEMfeZu6Jt69u5qehZo7F7EPYlSE")]
        for text, array, digest in vectors:
            self.assertEqual(decode_disclosure(text), array)
            self.assertEqual(V.disclosure_digest(text), digest)
        EVIDENCE["rfc9901Vectors"] = "3 published Disclosure strings decode to the published arrays and hash to the published digests (RFC 9901 sections 4.2.1, 4.2.3, 5.1)"

    def test_schema_values_equal_the_frozen_evaluator_constants(self):
        sys.path.insert(0, str(ROOT / "recall-engine"))
        from pramaan_recall import engine, policy
        self.assertEqual(set(V.FINDINGS), {policy.EXCL, policy.AFF, policy.UNRES})
        self.assertEqual(set(engine.ACTION.values()), {"RELEASE_ELIGIBLE", "RECALL_HOLD"})
        self.assertEqual(V.ACTIONS_ISSUABLE, ("RECALL_HOLD",))
        EVIDENCE["schema"] = dict(findings=sorted(V.FINDINGS), actions=sorted(set(engine.ACTION.values())), issuable=list(V.ACTIONS_ISSUABLE))


class HonestPackages(unittest.TestCase):
    def test_three_profiles_verify_and_disclose_exactly_their_claims(self):
        matrix = {}
        for profile, recipient in (("customer", CUSTOMER), ("supplier", SUPPLIER), ("auditor", AUDITOR)):
            r = check(FIXTURE["tokens"][profile], recipient, checkpoint=FIXTURE["anchor"] if profile == "auditor" else None)
            self.assertTrue(r["accepted"], r["failure"])
            self.assertEqual(set(r["claims"]), set(V.PROFILES[profile]["disclosed"]) if profile != "supplier" else set(V.SUPPLIER_CLAIMS))
            self.assertEqual((r["checks"]["physicalProductTruth"], r["clearance"]), ("UNVERIFIED", "NONE"))
            self.assertTrue(r["checks"]["freshnessRevocation"].startswith("UNKNOWN"))
            matrix[profile] = dict(disclosed=sorted(r["claims"]), digestsCommitted=len(parts(FIXTURE["tokens"][profile])[1]["_sd"]), bytes=len(FIXTURE["tokens"][profile]),
                                   checkpointBinding=r["checks"]["checkpointBinding"])
        self.assertEqual(set(matrix["customer"]["disclosed"]), {"motorSerial", "recallId", "evidenceFinding", "operationalAction"})
        self.assertEqual(set(matrix["supplier"]["disclosed"]), {"recallId", "part", "lot", "slot", "supplierId", "evidenceFinding", "operationalAction"})
        self.assertNotIn("motorSerial", matrix["supplier"]["disclosed"])
        self.assertTrue({"eventRow", "eventRowIndex", "installEventId"} <= set(matrix["auditor"]["disclosed"]))
        EVIDENCE["disclosureMatrix"] = matrix

    def test_customer_and_supplier_checkpoint_binding_is_issuer_asserted_without_the_checkpoint(self):
        for profile, recipient in (("customer", CUSTOMER), ("supplier", SUPPLIER)):
            self.assertEqual(check(FIXTURE["tokens"][profile], recipient)["checks"]["checkpointBinding"], "ISSUER_ASSERTED_ONLY")
        r = check(FIXTURE["tokens"]["customer"], CUSTOMER, checkpoint=FIXTURE["anchor"])
        self.assertTrue(r["checks"]["checkpointBinding"].startswith("CHECKPOINT_DEMONSTRATED"))          # the claims are still issuer-asserted; the report says so
        self.assertIn("issuer-asserted", r["checks"]["checkpointBinding"])
        self.assertTrue(check(FIXTURE["tokens"]["auditor"], AUDITOR, checkpoint=FIXTURE["anchor"])["checks"]["checkpointBinding"].startswith("CLAIMS_BOUND_TO_CHECKPOINT_ROW"))

    def test_every_package_commits_to_the_same_number_of_digests(self):
        self.assertEqual({len(parts(t)[1]["_sd"]) for t in FIXTURE["tokens"].values()}, {P.TOTAL_DIGESTS})

    def test_tokens_are_sd_jwt_shaped(self):
        for t in FIXTURE["tokens"].values():
            self.assertTrue(t.endswith("~"))
            h, p, s, ds = parts(t)
            self.assertEqual((h["alg"], h["typ"], p["_sd_alg"]), ("EdDSA", V.TYP, "sha-256"))
            self.assertEqual(p["_sd"], sorted(p["_sd"]))
            for d in ds:
                self.assertEqual(len(decode_disclosure(d)), 3)
                self.assertIn(V.disclosure_digest(d), p["_sd"])


class PrivacyAndLeakage(unittest.TestCase):
    def full_text(self, token):
        """Everything a recipient holds: the raw file plus every base64url segment decoded."""
        h, p, s, ds = parts(token)
        return token + json.dumps(h) + json.dumps(p) + "".join(json.dumps(decode_disclosure(d), ensure_ascii=False) for d in ds)

    def test_customer_package_holds_no_supplier_lot_or_unrelated_motor_detail(self):
        text = self.full_text(FIXTURE["tokens"]["customer"])
        for forbidden in ("BR-204", "BR-312", "SUP-", "Northstar", "Kaveri", "STEEL", "NSB", "BR-6205", CLEAN, "MTR-26001", "MTR-26005", LOOKALIKE, "eventRow", "policyDigest",
                          "headHash", "supplierId", "installEventId", "ASSY", "BUILD-", "demo-record"):
            self.assertNotIn(forbidden, text, forbidden)
        self.assertEqual(sorted(decode_disclosure(d)[1] for d in parts(FIXTURE["tokens"]["customer"])[3]), sorted(V.CUSTOMER_CLAIMS))

    def test_supplier_package_holds_no_motor_or_customer_identity(self):
        text = self.full_text(FIXTURE["tokens"]["supplier"])
        for forbidden in ("MTR-", "DEMO", AFFECTED, CUSTOMER, AUDITOR, "motorSerial", "decisionId", "eventRow", "installEventId", "headHash", "sequence", "policyDigest"):
            self.assertNotIn(forbidden, text, forbidden)

    def test_customer_and_supplier_packages_embed_no_checkpoint_content(self):
        checkpoint = json.loads(Path(FIXTURE["anchor"]).read_bytes())
        for profile in ("customer", "supplier"):
            text = self.full_text(FIXTURE["tokens"][profile])
            payload = parts(FIXTURE["tokens"][profile])[1]
            self.assertEqual(set(payload["binding"]), {"checkpointChecksum", "checkpointFormat", "state"})
            for digest in checkpoint["body"]["ledger"]["rows"]["events"][:10]:
                self.assertNotIn(digest, text)
            self.assertNotIn("sourceHeads", text)

    def test_hidden_claims_are_committed_with_fresh_random_salts_and_never_reused(self):
        seen, digests = set(), set()
        for _ in range(3):
            for profile, recipient in (("customer", CUSTOMER), ("supplier", SUPPLIER)):
                token = issue(profile, recipient)
                for d in parts(token)[3]:
                    self.assertGreaterEqual(len(decode_disclosure(d)[0]), 22)                 # 16 random bytes, base64url
                    self.assertNotIn(d, seen); seen.add(d)
                for digest in parts(token)[1]["_sd"]:
                    self.assertNotIn(digest, digests); digests.add(digest)
        EVIDENCE["saltReuse"] = "no Disclosure string and no digest repeated across 6 further issuances"

    def test_an_opened_ledger_row_requires_the_auditor_profile_and_explicit_authorization(self):
        self.assertNotIn("eventRow", V.PROFILES["customer"]["disclosed"] + V.PROFILES["supplier"]["disclosed"])
        for profile, recipient in (("customer", CUSTOMER), ("supplier", SUPPLIER)):
            with self.assertRaises(P.IssuanceRefused):
                issue(profile, recipient, authorize_event_row=True)
        r = check(issue("auditor", AUDITOR), AUDITOR)                                          # no authorization flag: no row is committed or opened
        self.assertNotIn("eventRow", r["claims"])
        self.assertTrue(r["accepted"])


class Tampering(unittest.TestCase):
    def setUp(self):
        self.token = FIXTURE["tokens"]["customer"]
        self.h, self.p, self.s, self.d = parts(self.token)

    def reject(self, token, code, **kw):
        r = check(token, kw.pop("recipient", CUSTOMER), **kw)
        self.assertFalse(r["accepted"], r)
        self.assertEqual(r["failure"], code, r["detail"])
        return r

    def test_the_unmodified_package_verifies(self):
        self.assertTrue(check(self.token, CUSTOMER)["accepted"])

    def test_signed_payload_tampering_fails(self):
        for change in (dict(aud=SUPPLIER), dict(exp=self.p["exp"] + 10), dict(iat=self.p["iat"] - 10), dict(profile="auditor"), dict(jti="x"), dict(iss="urn:evil")):
            self.reject(reassemble(self.h, dict(self.p, **change), self.s, self.d), "BAD_SIGNATURE", recipient=None)
        stripped = dict(self.p, _sd=self.p["_sd"][1:])                                         # plain redaction of the signed document: removing a digest
        self.reject(reassemble(self.h, stripped, self.s, self.d), "BAD_SIGNATURE")
        extra = dict(self.p, _sd=self.p["_sd"] + [V.b64u(hashlib.sha256(b"x").digest())])
        self.reject(reassemble(self.h, extra, self.s, self.d), "BAD_SIGNATURE")
        EVIDENCE["tamperPayload"] = "aud, exp, iat, profile, jti, iss, _sd removal and _sd addition each fail with BAD_SIGNATURE"

    def test_disclosure_tampering_fails(self):
        name, value = decode_disclosure(self.d[0])[1:]
        salt = decode_disclosure(self.d[0])[0]
        edits = [[salt, name, "MTR-OTHER-9"], [salt[:-1] + ("A" if salt[-1] != "A" else "B"), name, value], [salt, "recallId" if name != "recallId" else "motorSerial", value]]
        for edit in edits:
            text = V.b64u(json.dumps(edit, separators=(",", ":")).encode())
            self.reject(reassemble(self.h, self.p, self.s, [text] + self.d[1:]), "DISCLOSURE_NOT_COMMITTED")
        self.reject(reassemble(self.h, self.p, self.s, self.d + [self.d[0]]), "DUPLICATE_DISCLOSURE")
        unknown = V.b64u(json.dumps(["x" * 22, "motorSerial", "MTR-ZZ"], separators=(",", ":")).encode())
        self.reject(reassemble(self.h, self.p, self.s, self.d + [unknown]), "DUPLICATE_CLAIM_NAME")                   # the name is already opened
        names = [decode_disclosure(x)[1] for x in self.d]
        keep = [x for x, n in zip(self.d, names) if n != "motorSerial"]
        self.reject(reassemble(self.h, self.p, self.s, keep + [unknown]), "DISCLOSURE_NOT_COMMITTED")                   # substituting a value nobody committed to
        self.reject(self.token.replace("~", "~~", 1), "MALFORMED_JSON")
        EVIDENCE["tamperDisclosure"] = "changed value, changed salt, renamed claim, duplicate, uncommitted and empty disclosures are all rejected"

    def test_wrong_issuer_key_and_forged_signatures_fail(self):
        attacker_private, attacker_public = FIXTURE["attacker"]
        self.reject(self.token, "WRONG_ISSUER_KEY", issuer_key=attacker_public)
        forged_other_kid = forge(claims=GOOD_CUSTOMER, key=attacker_private)                 # attacker signs with its own key and its own kid
        self.reject(forged_other_kid, "WRONG_ISSUER_KEY", now=NOW)
        attacker, _ = P.load_private(attacker_private)
        _, victim_kid = P.load_private(FIXTURE["private"])
        h = V.b64u(json.dumps(dict(alg="EdDSA", typ=V.TYP, kid=victim_kid), separators=(",", ":")).encode())
        p = V.b64u(json.dumps(self.p, separators=(",", ":")).encode())
        forged_victim_kid = f"{h}.{p}.{V.b64u(attacker.sign((h + '.' + p).encode()))}~" + "".join(d + "~" for d in self.d)
        self.reject(forged_victim_kid, "BAD_SIGNATURE")                                        # the victim's kid but the attacker's signature
        flipped = self.s[:5] + ("B" if self.s[5] != "B" else "C") + self.s[6:]                                                     # always differs from the real signature
        self.reject(self.token.replace(self.s, flipped), "BAD_SIGNATURE")
        self.assertIn(check(self.token.replace(self.s, self.s[:10]), CUSTOMER)["failure"], ("BAD_SIGNATURE", "MALFORMED_BASE64URL"))                 # truncated: rejected as malformed or bad
        self.reject(self.token.replace(self.s, V.b64u(os.urandom(64))), "BAD_SIGNATURE")
        EVIDENCE["wrongKey"] = "attacker key, attacker key under the victim kid, corrupted and truncated signatures: all rejected"

    def test_audience_mismatch(self):
        self.reject(self.token, "AUDIENCE_MISMATCH", recipient=SUPPLIER)
        self.reject(FIXTURE["tokens"]["supplier"], "AUDIENCE_MISMATCH", recipient=CUSTOMER)
        r = check(self.token)                                                                  # not asked: reported as NOT CHECKED, never as matching
        self.assertEqual(r["checks"]["intendedRecipient"], "NOT_CHECKED")
        self.assertTrue(any("RECIPIENT_NOT_CHECKED" in w for w in r["warnings"]))

    def test_expiry_and_clock_rules(self):
        self.reject(self.token, "EXPIRED", now=self.p["exp"])
        self.reject(self.token, "EXPIRED", now=self.p["exp"] + 86400)
        self.reject(self.token, "NOT_YET_VALID", now=self.p["iat"] - 3600)
        self.assertTrue(check(self.token, CUSTOMER, now=self.p["exp"] - 1)["accepted"])
        self.assertTrue(check(self.token, CUSTOMER, now=self.p["iat"] - 30)["accepted"])        # within the stated 60 s skew
        for bad in (dict(exp=1_800_000_000), dict(exp=1_800_000_000 + 8 * 24 * 3600), dict(exp="never"), dict(exp=None), dict(iat=1.5)):
            self.reject(forge(claims=GOOD_CUSTOMER, payload=bad), "INVALID_EXPIRY", recipient=CUSTOMER, now=NOW)
        self.reject(P.issue(database=FIXTURE["db"], anchor=FIXTURE["anchor"], motor=AFFECTED, recipient=CUSTOMER, profile="customer", key_path=FIXTURE["private"], ttl=3600, now=1)
                    if False else forge(claims=GOOD_CUSTOMER, payload=dict(iat=0, exp=10)), "EXPIRED", recipient=CUSTOMER, now=NOW)
        for ttl in (0, -5, 8 * 24 * 3600):
            with self.assertRaises(P.IssuanceRefused):
                issue("customer", CUSTOMER, ttl=ttl)

    def test_duplicate_and_unexpected_claims(self):
        good = forge(claims=GOOD_CUSTOMER)
        self.assertTrue(check(good, CUSTOMER, now=NOW)["accepted"])                            # the forging helper itself produces valid packages
        entry_a, entry_b = P._disclosure("motorSerial", AFFECTED), P._disclosure("motorSerial", "MTR-OTHER")
        self.reject(forge(claims=dict(recallId="RC-026-014"), extra_disclosures=[entry_a[0], entry_b[0]], digests_extra=[entry_a[1], entry_b[1]]), "DUPLICATE_CLAIM_NAME", recipient=CUSTOMER, now=NOW)
        self.reject(forge(claims=GOOD_CUSTOMER, digests_extra=[V.b64u(hashlib.sha256(b"d").digest())] * 2), "DUPLICATE_DIGEST", recipient=CUSTOMER, now=NOW)
        self.reject(forge(claims=dict(GOOD_CUSTOMER, lot="BR-204")), "UNEXPECTED_CLAIM", recipient=CUSTOMER, now=NOW)                      # customer profile may not disclose a lot
        self.reject(forge(claims=dict(GOOD_CUSTOMER, favouriteColour="red")), "UNEXPECTED_CLAIM", recipient=CUSTOMER, now=NOW)
        self.reject(forge(claims=dict(GOOD_CUSTOMER, currentReleaseEligible=True)), "UNEXPECTED_CLAIM", recipient=CUSTOMER, now=NOW)
        for reserved in V.RESERVED_NAMES:
            self.reject(forge(claims=dict(GOOD_CUSTOMER, **{reserved: "x"})), "RESERVED_CLAIM_NAME", recipient=CUSTOMER, now=NOW)
        self.reject(forge(claims=GOOD_CUSTOMER, payload=dict(motorSerial=AFFECTED)), "UNEXPECTED_CLAIM", recipient=CUSTOMER, now=NOW)          # plain claim colliding with a disclosable one
        self.reject(forge(claims=GOOD_CUSTOMER, payload=dict(admin=True)), "UNEXPECTED_CLAIM", recipient=CUSTOMER, now=NOW)
        self.reject(forge(claims=GOOD_CUSTOMER, payload=dict(binding=dict(checkpointChecksum="x", extra=1, state="ANCHORED_CURRENT"))), "MALFORMED_BINDING", recipient=CUSTOMER, now=NOW)
        self.reject(forge(claims=GOOD_CUSTOMER, payload=dict(binding=dict(checkpointChecksum="x", checkpointFormat="F", state="PREFIX_ONLY"))), "BINDING_STATE", recipient=CUSTOMER, now=NOW)
        weak = V.b64u(json.dumps(["short", "recallId", "RC"], separators=(",", ":")).encode())
        self.reject(forge(claims=GOOD_CUSTOMER, extra_disclosures=[weak], digests_extra=[V.disclosure_digest(weak)]), "WEAK_SALT", recipient=CUSTOMER, now=NOW)
        EVIDENCE["unexpectedClaims"] = "profile violation, unknown claim, currentReleaseEligible, reserved names, plain-claim collision, extra payload field, duplicate name/digest/disclosure, weak salt: all rejected"

    def test_clearance_can_never_be_accepted_even_from_the_real_issuer_key(self):
        self.reject(forge(claims=dict(GOOD_CUSTOMER, operationalAction="RELEASE_ELIGIBLE")), "ACTION_NOT_ACCEPTABLE", recipient=CUSTOMER, now=NOW)
        self.reject(forge(claims=dict(GOOD_CUSTOMER, operationalAction="SHIP")), "ACTION_NOT_ACCEPTABLE", recipient=CUSTOMER, now=NOW)
        self.reject(forge(claims=dict(GOOD_CUSTOMER, evidenceFinding="SAFE")), "UNKNOWN_FINDING", recipient=CUSTOMER, now=NOW)
        self.reject(forge(claims=dict(GOOD_CUSTOMER, evidenceFinding="excluded_with_evidence")), "UNKNOWN_FINDING", recipient=CUSTOMER, now=NOW)

    def test_malformed_and_hostile_inputs_never_crash_or_accept(self):
        raw = FIXTURE["tokens"]["customer"]
        jwt = raw.split("~")[0]
        h, p, s = jwt.split(".")
        def with_header(**over):
            head = dict(self.h, **over)
            return reassemble(head, self.p, s, self.d)
        hostile = ["", "~", "abc", raw[:-1], raw + "~", jwt, "a.b.c~", "..~", raw.replace(".", "..", 1), "\x00" + raw, raw + "é", "é" * 50 + "~",
                   raw.replace(h, h + "A", 1), raw.replace(p, p[:-1] + "=", 1), "x" * 100000 + "~",
                   with_header(alg="none"), with_header(alg="HS256"), with_header(alg="ES256"), with_header(typ="JWT"), with_header(typ="dc+sd-jwt"), with_header(kid="other"),
                   with_header(jwk={"kty": "OKP"}), with_header(crit=["b64"]), with_header(jku="http://evil"), with_header(x5c=["AA"]),
                   reassemble(self.h, dict(self.p, _sd_alg="sha-512"), s, self.d), reassemble(self.h, dict(self.p, _sd="notalist"), s, self.d), reassemble(self.h, {}, s, self.d)]
        for item in hostile:
            r = check(item, CUSTOMER)
            self.assertFalse(r["accepted"], item[:60])
            self.assertIsNotNone(r["failure"])
            self.assertEqual(r["clearance"], "NONE")
        for not_a_string in (None, 5, b"x", ["a"]):
            self.assertFalse(check(not_a_string, CUSTOMER)["accepted"])
        EVIDENCE["hostileInputs"] = f"{len(hostile) + 4} hostile inputs rejected without an exception"

    def test_pinned_key_document_is_validated(self):
        for bad in ('{"kty":"RSA"}', "{}", '{"kty":"OKP","crv":"Ed25519","kid":"a","x":"AAAA"}', "not json at all"):
            r = check(self.token, CUSTOMER, issuer_key=bad)
            self.assertFalse(r["accepted"])

    def test_incomplete_but_valid_disclosure_is_flagged_not_accepted_silently(self):
        r = check(reassemble(self.h, self.p, self.s, self.d[:2]), CUSTOMER)
        self.assertTrue(r["accepted"])                                                         # selective disclosure: withholding is legitimate
        self.assertTrue(any(w.startswith("INCOMPLETE_FOR_PROFILE") for w in r["warnings"]))


class CheckpointBinding(unittest.TestCase):
    def setUp(self):
        self.checkpoint = json.loads(Path(FIXTURE["anchor"]).read_bytes())
        self.auditor = FIXTURE["tokens"]["auditor"]

    def reject(self, token, code, **kw):
        r = check(token, AUDITOR, **kw)
        self.assertFalse(r["accepted"]); self.assertEqual(r["failure"], code, r["detail"])

    def forged_auditor(self, *, mutate=None, now=NOW):
        claims = {n: v for n, v in check(self.auditor, AUDITOR)["claims"].items()}
        (mutate or (lambda c: None))(claims)
        return forge(claims=claims, profile="auditor", aud=AUDITOR, now=now)

    def test_wrong_or_modified_checkpoint_is_detected(self):
        other = copy.deepcopy(self.checkpoint)
        other["body"]["sequence"] += 1
        self.reject(self.auditor, "CHECKPOINT_CHECKSUM_INVALID", checkpoint=other)             # body changed, checksum not recomputed
        other["checksum"] = V.checkpoint_checksum(other["body"])
        self.reject(self.auditor, "CHECKPOINT_MISMATCH", checkpoint=other)                      # a self-consistent but different checkpoint
        self.reject(self.auditor, "CHECKPOINT_MALFORMED", checkpoint={"nope": 1})

    def test_opened_row_must_match_the_checkpoint_digest_and_the_claims(self):
        good = self.forged_auditor()
        self.assertTrue(check(good, AUDITOR, checkpoint=self.checkpoint, now=NOW)["accepted"])
        def flip(c):
            row = list(c["eventRow"]); row[5] = row[5].replace("BR-204", "BR-310"); c["eventRow"] = row
        self.reject(self.forged_auditor(mutate=flip), "EVENT_ROW_NOT_IN_CHECKPOINT", checkpoint=self.checkpoint, now=NOW)
        self.reject(self.forged_auditor(mutate=lambda c: c.update(eventRowIndex=c["eventRowIndex"] + 1)), "EVENT_ROW_NOT_IN_CHECKPOINT", checkpoint=self.checkpoint, now=NOW)
        self.reject(self.forged_auditor(mutate=lambda c: c.update(eventRowIndex=10 ** 6)), "EVENT_ROW_NOT_IN_CHECKPOINT", checkpoint=self.checkpoint, now=NOW)
        self.reject(self.forged_auditor(mutate=lambda c: c.update(lot="BR-310")), "EVENT_ROW_CLAIM_MISMATCH", checkpoint=self.checkpoint, now=NOW)
        self.reject(self.forged_auditor(mutate=lambda c: c.update(slot="NDE")), "EVENT_ROW_CLAIM_MISMATCH", checkpoint=self.checkpoint, now=NOW)
        self.reject(self.forged_auditor(mutate=lambda c: c.update(motorSerial="MTR-26001")), "EVENT_ROW_CLAIM_MISMATCH", checkpoint=self.checkpoint, now=NOW)
        self.reject(self.forged_auditor(mutate=lambda c: c.update(policyDigest="0" * 64)), "CHECKPOINT_MISMATCH", checkpoint=self.checkpoint, now=NOW)
        self.reject(self.forged_auditor(mutate=lambda c: c.update(headHash="0" * 64)), "CHECKPOINT_MISMATCH", checkpoint=self.checkpoint, now=NOW)
        self.reject(self.forged_auditor(mutate=lambda c: c.update(sequence=c["sequence"] + 1)), "CHECKPOINT_MISMATCH", checkpoint=self.checkpoint, now=NOW)
        self.reject(self.forged_auditor(mutate=lambda c: c.pop("eventRowIndex")), "EVENT_ROW_INCOMPLETE", checkpoint=self.checkpoint, now=NOW)
        self.reject(self.forged_auditor(mutate=lambda c: c.update(eventRow=c["eventRow"][:9])), "BAD_CLAIM_VALUE", checkpoint=self.checkpoint, now=NOW)
        EVIDENCE["checkpointBindingNegatives"] = "wrong/modified checkpoint, altered row, shifted/out-of-range index, lot/slot/serial/policy/head/sequence mismatch, partial row: all rejected"

    def test_a_package_bound_to_another_checkpoint_is_rejected(self):
        later = self.forged_auditor()
        other = copy.deepcopy(self.checkpoint)
        other["body"]["format"] = "PRAMAAN_A31_ANCHOR_V2"
        other["checksum"] = V.checkpoint_checksum(other["body"])
        self.reject(later, "CHECKPOINT_MISMATCH", checkpoint=other, now=NOW)


class IssuerRefusals(unittest.TestCase):
    def test_no_package_for_a_clearance_motor(self):
        for profile, recipient in (("customer", CUSTOMER), ("supplier", SUPPLIER), ("auditor", AUDITOR)):
            with self.assertRaises(P.IssuanceRefused) as cm:
                issue(profile, recipient, CLEAN)
            self.assertIn("RELEASE_ELIGIBLE", str(cm.exception))
        EVIDENCE["clearanceMotorRefused"] = True

    def test_unknown_motor_and_bad_inputs(self):
        for kwargs in (dict(motor="MTR-NOPE"), dict(profile="partner"), dict(recipient=""), dict(recipient="x" * 300)):
            args = dict(motor=AFFECTED, profile="customer", recipient=CUSTOMER); args.update(kwargs)
            with self.assertRaises(P.IssuanceRefused):
                P.issue(database=FIXTURE["db"], anchor=FIXTURE["anchor"], motor=args["motor"], recipient=args["recipient"], profile=args["profile"], key_path=FIXTURE["private"])

    def test_supplier_profile_needs_an_established_affected_installation(self):
        for motor in (UNRESOLVED, LOOKALIKE):
            customer = issue("customer", CUSTOMER, motor)                                      # a held motor still gets a customer notice
            self.assertEqual(check(customer, CUSTOMER)["claims"]["operationalAction"], "RECALL_HOLD")
            with self.assertRaises(P.IssuanceRefused):
                issue("supplier", SUPPLIER, motor)                                             # but never an unverified lot claim for a supplier
            auditor = check(issue("auditor", AUDITOR, motor, authorize_event_row=True), AUDITOR)
            self.assertNotIn("lot", auditor["claims"]); self.assertNotIn("eventRow", auditor["claims"])
        EVIDENCE["unresolvedAndLookalikeNoLotClaim"] = True

    def test_stale_checkpoint_issues_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            db, anchor, private, public = build_world(d)
            app = Manufacturing(db); app.observe(CLEAN, "ZZ-9"); app.close()                   # the ledger moves past the checkpoint
            with self.assertRaises(P.IssuanceRefused) as cm:
                P.issue(database=db, anchor=anchor, motor=AFFECTED, recipient=CUSTOMER, profile="customer", key_path=private)
            self.assertIn("ANCHORED_PREFIX_ONLY", str(cm.exception))
            EVIDENCE["staleCheckpointRefused"] = True

    def test_an_existing_issuer_key_is_never_overwritten(self):
        with self.assertRaises(P.IssuanceRefused):
            P.keygen(Path(FIXTURE["private"]).parent)


class ReadOnly(unittest.TestCase):
    def state(self):
        app = Manufacturing(FIXTURE["db"])
        try:
            return ledger_binding(app), Path(FIXTURE["anchor"]).read_bytes()
        finally:
            app.close()

    def test_issuing_and_verifying_change_neither_ledger_nor_checkpoint(self):
        before = self.state()
        for profile, recipient in (("customer", CUSTOMER), ("supplier", SUPPLIER), ("auditor", AUDITOR)):
            token = issue(profile, recipient, authorize_event_row=profile == "auditor")
            check(token, recipient, checkpoint=FIXTURE["anchor"])
        with self.assertRaises(P.IssuanceRefused):
            issue("customer", CUSTOMER, CLEAN)
        self.assertEqual(self.state(), before)
        EVIDENCE["readOnly"] = "ledger_binding (every table's row digests + source heads) and the checkpoint file bytes are identical before and after issuing and verifying"

    def test_verifier_imports_nothing_from_the_ledger_service_server_or_anchor_code(self):
        code = ("import sys, application.evidence_verify; bad=[m for m in sys.modules if m in ('application.service','application.server','application.anchors',"
                "'application.checkpoint_ops','pramaan_integration','pramaan_recall','sqlite3')]; print(bad); sys.exit(1 if bad else 0)")
        r = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_no_operational_command_is_reachable_from_the_package_code(self):
        for name in ("evidence_package.py", "evidence_verify.py"):
            source = (Path(__file__).parent / name).read_text(encoding="utf-8")
            for call in (".announce(", ".ship(", ".assemble(", ".observe(", "app.replace(", ".create_unit(", "record_historical_shipment_fixture", "INSERT ", "UPDATE ", "DELETE ", "DROP "):
                self.assertNotIn(call, source, f"{name}: {call}")
        self.assertNotIn("evidence_", (Path(__file__).parent / "server.py").read_text(encoding="utf-8"))          # no HTTP route exposes issuance or import


class StatusList(unittest.TestCase):
    def test_revocation_is_reported_only_with_a_signed_issuer_list(self):
        token = FIXTURE["tokens"]["customer"]
        jti = parts(token)[1]["jti"]
        revoked = P.status_list(FIXTURE["private"], [jti, "other"])
        fine = P.status_list(FIXTURE["private"], ["unrelated"])
        r = check(token, CUSTOMER, status=revoked)
        self.assertEqual((r["accepted"], r["failure"]), (False, "REVOKED"))
        ok = check(token, CUSTOMER, status=fine)
        self.assertTrue(ok["accepted"]); self.assertIn("currency remains unconfirmed", ok["checks"]["freshnessRevocation"])
        self.assertFalse(check(token, CUSTOMER, status=P.status_list(FIXTURE["attacker"][0], [jti]))["accepted"])      # a list signed by another key is not honoured
        self.assertEqual(check(token, CUSTOMER, status=P.status_list(FIXTURE["attacker"][0], [jti]))["failure"], "WRONG_ISSUER_KEY")
        self.assertFalse(check(token, CUSTOMER, status="garbage")["accepted"])
        self.assertTrue(check(token, CUSTOMER)["checks"]["freshnessRevocation"].startswith("UNKNOWN"))


class CommandLine(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-B", "-m", *args], cwd=ROOT, capture_output=True, text=True)

    def test_issue_and_verify_end_to_end_with_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "customer.sdjwt"
            r = self.run_cli("application.evidence_package", "issue", "--database", str(FIXTURE["db"]), "--anchor", str(FIXTURE["anchor"]), "--motor", AFFECTED,
                             "--recipient", CUSTOMER, "--profile", "customer", "--key", str(FIXTURE["private"]), "--out", str(out))
            self.assertEqual(r.returncode, 0, r.stderr)
            ok = self.run_cli("application.evidence_verify", str(out), "--issuer-key", str(FIXTURE["public"]), "--recipient", CUSTOMER)
            self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
            self.assertIn("Not a release clearance", ok.stdout)
            self.assertIn("physical product truth : UNVERIFIED", ok.stdout)
            bad_recipient = self.run_cli("application.evidence_verify", str(out), "--issuer-key", str(FIXTURE["public"]), "--recipient", SUPPLIER)
            self.assertEqual(bad_recipient.returncode, 2); self.assertIn("AUDIENCE_MISMATCH", bad_recipient.stdout)
            out.write_text(out.read_text().replace("RC-026", "RC-027", 1) if "RC-026" in out.read_text() else out.read_text()[:-5] + "AAAA~")
            self.assertEqual(self.run_cli("application.evidence_verify", str(out), "--issuer-key", str(FIXTURE["public"])).returncode, 2)
            refused = self.run_cli("application.evidence_package", "issue", "--database", str(FIXTURE["db"]), "--anchor", str(FIXTURE["anchor"]), "--motor", CLEAN,
                                   "--recipient", CUSTOMER, "--profile", "customer", "--key", str(FIXTURE["private"]), "--out", str(Path(d) / "none.sdjwt"))
            self.assertEqual(refused.returncode, 2); self.assertFalse((Path(d) / "none.sdjwt").exists())


if __name__ == "__main__":
    unittest.main()
