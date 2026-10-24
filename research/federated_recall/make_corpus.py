"""Builds the F6 interop corpus (valid + tampered envelopes) with the reference code. Run from the repo root with the F6 venv: python -B research/federated_recall/make_corpus.py OUT.json"""
import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from cryptography.hazmat.primitives import serialization
from application import test_federation as T
from application.federation import messages as M, staging as S, trust

NOW = T.NOW


def reference(envelope, kind, peers):
    """The reference verdict for exactly the checks the independent verifiers implement (signature, pinned sender/role/kid, type, closed field set, validity window)."""
    try:
        body = M.verify_envelope(envelope, peers, expected_type=kind)
        (M.validate_alert if kind == "ALERT" else M.validate_response)(body)
        if kind == "ALERT":
            M.check_window(body, NOW)
        return True
    except M.Rejection:
        return False


def main(out):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        world = S.stage_world(d)
        sup = T.supplier_for(world)
        path, body = T.issue(sup)
        alert = json.loads(path.read_text())
        node = T.node_for(world, "a")
        digest = node.receive(path, NOW)["alertHash"]
        node.adopt(body["alertId"], "op", digest[:12], NOW)
        response = json.loads(Path(node.respond(body["alertId"], NOW)["path"]).read_text())
        peers_alert, peers_response = trust.load_trust(world["supplier_pin"]), trust.load_trust(world["supplier_trust"])
        attacker, attacker_kid = T.attacker_key()
        sup_key, sup_kid = M.load_private(Path(world["keys"]["supplier"][0]).read_bytes())
        fac_key, fac_kid = M.load_private(Path(world["keys"]["factory-a"][0]).read_bytes())

        def tweak(env, **changes):
            e = copy.deepcopy(env); e["body"].update(changes); return e
        flipped = copy.deepcopy(alert); s = flipped["signature"]; flipped["signature"] = s[:5] + ("B" if s[5] != "B" else "C") + s[6:]
        answered = dict(response["body"], status="ANSWERED", asOfCheckpoint="a" * 64,
                        counts=dict(heldMotors=3, heldByEvidenceFinding=dict(AFFECTED=2, UNRESOLVED=0, EXCLUDED_WITH_EVIDENCE=1), heldOnlyByIdentityGuard=1))
        cases = [("valid-alert", "ALERT", alert), ("valid-response", "RESPONSE", response), ("valid-answered-response", "RESPONSE", M.sign(answered, fac_key, fac_kid)),
                 ("alert-text-changed", "ALERT", tweak(alert, humanText="changed")), ("alert-lot-changed", "ALERT", tweak(alert, lot=dict(body["lot"], supplierLot="NSB-999"))),
                 ("response-status-changed", "RESPONSE", tweak(response, status="LOT_UNMAPPED")), ("signature-flipped", "ALERT", flipped),
                 ("attacker-own-kid", "ALERT", M.sign(body, attacker, attacker_kid)), ("attacker-victim-kid", "ALERT", M.sign(body, attacker, sup_kid)),
                 ("factory-key-as-supplier", "ALERT", M.sign(dict(body, issuer=S.A_ID), fac_key, fac_kid)), ("supplier-key-as-responder", "RESPONSE", M.sign(response["body"], sup_key, sup_kid)),
                 ("wrong-type", "ALERT", M.sign(dict(body, type="CORRECTION"), sup_key, sup_kid)), ("extra-field-signed-by-real-key", "ALERT", M.sign(dict(body, clearsHold=True), sup_key, sup_kid)),
                 ("expired", "ALERT", M.sign(dict(body, iat=1, exp=100), sup_key, sup_kid)), ("alert-as-response", "RESPONSE", alert),
                 ("response-extra-counts-field", "RESPONSE", M.sign(dict(response["body"], counts=dict(heldMotors=0, heldByEvidenceFinding=dict(AFFECTED=0, UNRESOLVED=0, EXCLUDED_WITH_EVIDENCE=0),
                                                                                              heldOnlyByIdentityGuard=0, serials=[])), fac_key, fac_kid))]
        def pins(kind):
            peers = peers_alert if kind == "ALERT" else peers_response
            return {k: dict(role=v[0], kid=v[1], x=M.b64u(v[2].public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))) for k, v in peers.items()}
        Path(out).write_text(json.dumps(dict(now=NOW, cases=[dict(name=n, kind=k, envelope=e, pinned=pins(k), reference=reference(e, k, peers_alert if k == "ALERT" else peers_response))
                                                            for n, k, e in cases]), indent=1))
        print(len(cases), "cases; reference accepted:", sum(reference(e, k, peers_alert if k == "ALERT" else peers_response) for _, k, e in cases))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
