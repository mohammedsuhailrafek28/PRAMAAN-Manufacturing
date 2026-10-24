"""Sensitivity check for the F5 evidence package: each mutant removes one safety mechanism in-process (no file is changed); test_evidence_package must fail.
usage (repository root, F5 venv):  python -B research/portable_evidence/mutation_check.py OUT.json [mutant names...]
"""
import copy
import io
import json
import secrets
import sys
import types
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from application import evidence_package as P  # noqa: E402
from application import evidence_verify as V  # noqa: E402
from application import service as SVC  # noqa: E402

SAVED = dict(verify=V.verify, load_public_key=V.load_public_key, disclosure_digest=V.disclosure_digest, PAYLOAD_FIELDS=V.PAYLOAD_FIELDS, ACTIONS=V.ACTIONS_ISSUABLE,
             profiles=copy.deepcopy(V.PROFILES), bind=V._bind, status=V._status, row_digest=V.row_digest, checksum=V.checkpoint_checksum, total=P.TOTAL_DIGESTS,
             secrets=P.secrets, collect=P.collect, snapshot=SVC.Manufacturing.snapshot)


class Anything:
    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    __hash__ = None


def run():
    import application.test_evidence_package as T
    suite = unittest.defaultTestLoader.loadTestsFromModule(T)
    r = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return dict(ran=r.testsRun, failed=sorted({str(t).split(" ")[0] for t, _ in r.failures + r.errors}))


def restore():
    V.verify, V.load_public_key, V.disclosure_digest, V.PAYLOAD_FIELDS, V.ACTIONS_ISSUABLE = (SAVED[k] for k in ("verify", "load_public_key", "disclosure_digest", "PAYLOAD_FIELDS", "ACTIONS"))
    V.PROFILES.clear(); V.PROFILES.update(copy.deepcopy(SAVED["profiles"]))
    V._bind, V._status, V.row_digest, V.checkpoint_checksum = SAVED["bind"], SAVED["status"], SAVED["row_digest"], SAVED["checksum"]
    P.TOTAL_DIGESTS, P.secrets, P.collect = SAVED["total"], SAVED["secrets"], SAVED["collect"]
    SVC.Manufacturing.snapshot = SAVED["snapshot"]


def m_signature_not_verified():
    real = SAVED["load_public_key"]

    def load(source):
        kid, key = real(source)
        return kid, types.SimpleNamespace(verify=lambda signature, message: None)
    V.load_public_key = load


def m_digest_checks_only_a_prefix():
    V.disclosure_digest = lambda text: SAVED["disclosure_digest"](text[:16])


def m_audience_ignored():
    V.verify = lambda token, **kw: SAVED["verify"](token, **dict(kw, recipient=None))


def m_expiry_ignored():
    def verify(token, **kw):
        payload = json.loads(V.b64u_decode(token.split(".")[1])) if isinstance(token, str) and token.count(".") >= 2 else {}
        iat = payload.get("iat") if isinstance(payload.get("iat"), int) else 0
        return SAVED["verify"](token, **dict(kw, now=iat + 1))
    V.verify = verify


def m_clearance_action_accepted_and_issuable():
    V.ACTIONS_ISSUABLE = ("RECALL_HOLD", "RELEASE_ELIGIBLE")


def m_closed_claim_set_open_for_customer():
    V.PROFILES["customer"]["disclosed"] = V.ALL_CLAIMS


def m_supplier_sees_motor_serial():
    V.PROFILES["supplier"]["disclosed"] = V.SUPPLIER_CLAIMS + ("motorSerial",)


def m_unexpected_payload_fields_allowed():
    V.PAYLOAD_FIELDS = set(SAVED["PAYLOAD_FIELDS"]) | {"admin"}


def m_checkpoint_binding_skipped():
    V._bind = lambda *args, **kw: None


def m_checkpoint_checksum_not_recomputed():
    V.checkpoint_checksum = lambda body: Anything()


def m_event_row_digest_not_compared():
    V.row_digest = lambda row: Anything()


def m_revocation_list_ignored():
    V._status = lambda *args, **kw: None


def m_salts_reused():
    P.secrets = types.SimpleNamespace(token_urlsafe=lambda n: "A" * 22, token_bytes=secrets.token_bytes, SystemRandom=secrets.SystemRandom)


def m_digest_count_leaks_claim_count():
    P.TOTAL_DIGESTS = 0


def m_stale_checkpoint_accepted():
    def snapshot(self, *, trusted_anchor=None, **kw):
        result = SAVED["snapshot"](self, trusted_anchor=trusted_anchor, **kw)
        result["checkpoint"] = dict(result["checkpoint"], state="ANCHORED_CURRENT")
        return result
    SVC.Manufacturing.snapshot = snapshot


def m_event_row_opened_without_authorization():
    P.collect = lambda *args, **kw: SAVED["collect"](*args, **dict(kw, include_event_row=True))


def m_issuer_mutates_the_ledger():
    def collect(database, anchor, previous_anchor, motor, **kw):
        app = SVC.Manufacturing(database)
        try:
            app.observe("MTR-26001", "ZZ-0")                                   # a write through the real service, before reading
        finally:
            app.close()
        return SAVED["collect"](database, anchor, previous_anchor, motor, **kw)
    P.collect = collect


MUTANTS = (("signature_not_verified", m_signature_not_verified), ("digest_checks_only_a_prefix", m_digest_checks_only_a_prefix), ("audience_ignored", m_audience_ignored),
           ("expiry_ignored", m_expiry_ignored), ("clearance_action_accepted_and_issuable", m_clearance_action_accepted_and_issuable),
           ("closed_claim_set_open_for_customer", m_closed_claim_set_open_for_customer), ("supplier_sees_motor_serial", m_supplier_sees_motor_serial),
           ("unexpected_payload_fields_allowed", m_unexpected_payload_fields_allowed), ("checkpoint_binding_skipped", m_checkpoint_binding_skipped),
           ("checkpoint_checksum_not_recomputed", m_checkpoint_checksum_not_recomputed), ("event_row_digest_not_compared", m_event_row_digest_not_compared),
           ("revocation_list_ignored", m_revocation_list_ignored), ("salts_reused", m_salts_reused), ("digest_count_leaks_claim_count", m_digest_count_leaks_claim_count),
           ("stale_checkpoint_accepted", m_stale_checkpoint_accepted), ("event_row_opened_without_authorization", m_event_row_opened_without_authorization),
           ("issuer_mutates_the_ledger", m_issuer_mutates_the_ledger))

if __name__ == "__main__":
    only = set(sys.argv[2:])
    results = dict(unmutated=run())
    for name, fn in MUTANTS:
        if only and name not in only:
            continue
        fn()
        try:
            results[name] = run()
        finally:
            restore()
    for k, v in results.items():
        print(k, v["ran"], "tests; failing:", len(v["failed"]), v["failed"])
    Path(sys.argv[1]).write_text(json.dumps(results, indent=1, sort_keys=True))
    survivors = [k for k, v in results.items() if k != "unmutated" and not v["failed"]]
    print("SURVIVORS:", survivors)
    sys.exit(1 if survivors or results["unmutated"]["failed"] else 0)
