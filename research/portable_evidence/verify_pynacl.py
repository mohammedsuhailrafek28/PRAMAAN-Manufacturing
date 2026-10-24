"""Second independent implementation: PyNaCl (libsodium) for Ed25519, hashlib for digests; no code shared with application/evidence_verify.py and no `cryptography` import.
Run with a Python that has PyNaCl: python -I verify_pynacl.py corpus.json"""
import base64
import hashlib
import json
import re
import sys
import time

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

CUSTOMER = ["motorSerial", "recallId", "evidenceFinding", "operationalAction"]
PROFILES = {"customer": CUSTOMER, "supplier": ["recallId", "part", "lot", "slot", "supplierId", "evidenceFinding", "operationalAction"]}
PROFILES["auditor"] = CUSTOMER + ["part", "lot", "slot", "supplierId", "installEventId", "decisionId", "policyDigest", "registryDigest", "headHash", "sequence", "eventRow", "eventRowIndex"]
FIELDS = {"iss", "aud", "iat", "exp", "jti", "_sd_alg", "_sd", "format", "profile", "purpose", "binding"}


def un(s):
    assert re.fullmatch(r"[A-Za-z0-9_-]*", s) and len(s) % 4 != 1
    raw = base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
    assert base64.urlsafe_b64encode(raw).rstrip(b"=").decode() == s
    return raw


def check(token, vk, kid, recipient, now):
    assert isinstance(token, str) and token.endswith("~")
    jwt, *discs = token[:-1].split("~")
    h, p, s = jwt.split(".")
    header = json.loads(un(h))
    assert set(header) <= {"alg", "typ", "kid"} and header.get("alg") == "EdDSA" and header.get("typ") == "pramaan-evidence+sd-jwt" and header.get("kid") == kid
    sig = un(s)
    assert len(sig) == 64
    vk.verify((h + "." + p).encode("ascii"), sig)
    payload = json.loads(un(p))
    names = set(sum(PROFILES.values(), []))
    assert isinstance(payload, dict) and set(payload) <= FIELDS and not names & set(payload)
    allowed = PROFILES[payload["profile"]]
    assert payload["_sd_alg"] == "sha-256" and isinstance(payload["_sd"], list) and len(set(payload["_sd"])) == len(payload["_sd"])
    claims, seen = {}, set()
    for d in discs:
        assert d not in seen
        seen.add(d)
        salt, name, value = json.loads(un(d))
        assert isinstance(salt, str) and len(salt) >= 16 and name in allowed and name not in claims
        assert base64.urlsafe_b64encode(hashlib.sha256(d.encode("ascii")).digest()).rstrip(b"=").decode() in payload["_sd"]
        claims[name] = value
    assert claims.get("operationalAction", "RECALL_HOLD") == "RECALL_HOLD"
    assert claims.get("evidenceFinding", "AFFECTED") in ("AFFECTED", "EXCLUDED_WITH_EVIDENCE", "UNRESOLVED")
    assert recipient is None or payload["aud"] == recipient
    iat, exp = payload["iat"], payload["exp"]
    assert type(iat) is int and type(exp) is int and 0 < exp - iat <= 7 * 86400
    at = int(time.time()) if now is None else now
    assert iat - 60 <= at < exp
    assert payload["binding"]["state"] == "ANCHORED_CURRENT"
    return claims


corpus = json.load(open(sys.argv[1], encoding="utf-8"))
vk = VerifyKey(un(corpus["issuerKey"]["x"]))
out = []
for c in corpus["cases"]:
    try:
        out.append(dict(name=c["name"], accepted=True, failure=None, claims=check(c["token"], vk, corpus["issuerKey"]["kid"], c["recipient"], c["now"])))
    except (AssertionError, BadSignatureError, ValueError, KeyError, TypeError) as exc:
        out.append(dict(name=c["name"], accepted=False, failure=type(exc).__name__, claims={}))
print(json.dumps(out))
