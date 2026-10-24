"""Builds the interop corpus (valid + tampered packages) with the reference issuer; reference verdicts come from application.evidence_verify.
Run from the repo root with the F5 venv: python -B research/portable_evidence/make_corpus.py OUT.json"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from application import evidence_verify as V
from application import test_evidence_package as T

CASES = []


def add(name, token, recipient, now=None):
    ref = V.verify(token, issuer_key=T.FIXTURE["public"], recipient=recipient, now=now)
    CASES.append(dict(name=name, token=token, recipient=recipient, now=now, reference=dict(accepted=ref["accepted"], failure=ref["failure"], claims=ref["claims"])))


def main(out):
    T.setUpModule()
    try:
        tokens = T.FIXTURE["tokens"]
        audiences = dict(customer=T.CUSTOMER, supplier=T.SUPPLIER, auditor=T.AUDITOR)
        for profile, token in tokens.items():
            add(f"valid-{profile}", token, audiences[profile])
        h, p, s, d = T.parts(tokens["customer"])
        add("aud-mismatch", tokens["customer"], T.SUPPLIER)
        add("expired", tokens["customer"], T.CUSTOMER, p["exp"] + 5)
        add("not-yet-valid", tokens["customer"], T.CUSTOMER, p["iat"] - 3600)
        add("payload-aud-changed", T.reassemble(h, dict(p, aud=T.SUPPLIER), s, d), T.SUPPLIER)
        add("payload-sd-entry-dropped", T.reassemble(h, dict(p, _sd=p["_sd"][1:]), s, d), T.CUSTOMER)
        salt, name, value = T.decode_disclosure(d[0])
        add("disclosure-value-changed", T.reassemble(h, p, s, [V.b64u(json.dumps([salt, name, "X"], separators=(",", ":")).encode())] + d[1:]), T.CUSTOMER)
        add("disclosure-duplicated", T.reassemble(h, p, s, d + [d[0]]), T.CUSTOMER)
        add("signature-bit-flipped", T.reassemble(h, p, s[:5] + ("B" if s[5] != "B" else "C") + s[6:], d), T.CUSTOMER)
        add("attacker-key-signed", T.forge(claims=T.GOOD_CUSTOMER, key=T.FIXTURE["attacker"][0], now=T.NOW), T.CUSTOMER, T.NOW)
        add("forged-by-real-key-valid", T.forge(claims=T.GOOD_CUSTOMER), T.CUSTOMER, T.NOW)
        add("forged-release-eligible", T.forge(claims=dict(T.GOOD_CUSTOMER, operationalAction="RELEASE_ELIGIBLE")), T.CUSTOMER, T.NOW)
        add("forged-extra-claim", T.forge(claims=dict(T.GOOD_CUSTOMER, lot="BR-204")), T.CUSTOMER, T.NOW)
        add("forged-overlong-expiry", T.forge(claims=T.GOOD_CUSTOMER, payload=dict(exp=1_800_000_000 + 8 * 86400)), T.CUSTOMER, T.NOW)
        add("forged-alg-none", T.forge(claims=T.GOOD_CUSTOMER, header=dict(alg="none")), T.CUSTOMER, T.NOW)
        key = json.loads(Path(T.FIXTURE["public"]).read_text())
        Path(out).write_text(json.dumps(dict(issuerKey=key, cases=CASES), indent=1))
        print(f"{len(CASES)} cases; reference accepted: {sum(c['reference']['accepted'] for c in CASES)}")
    finally:
        T.tearDownModule()


if __name__ == "__main__":
    main(sys.argv[1])
