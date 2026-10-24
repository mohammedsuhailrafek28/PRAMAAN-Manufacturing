"""Second independent implementation: PyNaCl (libsodium) Ed25519 and its own canonical JSON (sorted keys, no whitespace, UTF-8, integers only). No code shared with
application/federation/messages.py and no `cryptography` import. Run with a Python that has PyNaCl: python -I verify_pynacl.py corpus.json"""
import base64
import json
import re
import sys

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

FORMAT = "PRAMAAN-FED/1"
ALERT = {"type", "alertId", "issuer", "seq", "prevHash", "iat", "exp", "lot", "affectedSlots", "humanText", "recipients"}
ALERT_REQUIRED = ALERT - {"recipients"}
RESPONSE = {"type", "responseId", "alertId", "alertHash", "responder", "seq", "prevHash", "iat", "status", "counts", "asOfCheckpoint"}


def canon(v):
    if isinstance(v, float):
        raise ValueError("non-integer")
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def un(text):
    assert isinstance(text, str) and re.fullmatch(r"[A-Za-z0-9_-]*", text)
    raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    assert base64.urlsafe_b64encode(raw).rstrip(b"=").decode() == text
    return raw


def check(c, now):
    env, kind = c["envelope"], c["kind"]
    if not isinstance(env, dict) or set(env) != {"format", "kid", "body", "signature"} or env["format"] != FORMAT:
        return False
    body = env["body"]
    if not isinstance(body, dict) or body.get("type") != kind:
        return False
    who = body.get("issuer" if kind == "ALERT" else "responder")
    peer = c["pinned"].get(who) if isinstance(who, str) else None
    if not peer or peer["role"] != ("supplier" if kind == "ALERT" else "factory") or env["kid"] != peer["kid"]:
        return False
    sig = un(env["signature"])
    if len(sig) != 64:
        return False
    try:
        VerifyKey(un(peer["x"])).verify(FORMAT.encode() + b"\0" + canon(body).encode("utf-8"), sig)
    except BadSignatureError:
        return False
    keys = set(body)
    if kind == "ALERT":
        if keys - ALERT or ALERT_REQUIRED - keys:
            return False
        iat, exp = body["iat"], body["exp"]
        return type(iat) is int and type(exp) is int and 0 < exp - iat <= 7 * 86400 and iat - 60 <= now < exp
    if keys != RESPONSE:
        return False
    counts = body["counts"]
    if body["status"] == "ANSWERED":
        by = counts.get("heldByEvidenceFinding") if isinstance(counts, dict) else None
        return (set(counts) == {"heldMotors", "heldByEvidenceFinding", "heldOnlyByIdentityGuard"} and isinstance(by, dict) and set(by) == {"AFFECTED", "UNRESOLVED", "EXCLUDED_WITH_EVIDENCE"}
                and all(type(n) is int and n >= 0 for n in by.values()) and type(counts["heldMotors"]) is int and sum(by.values()) == counts["heldMotors"]
                and type(counts["heldOnlyByIdentityGuard"]) is int and 0 <= counts["heldOnlyByIdentityGuard"] <= counts["heldMotors"])
    return counts is None and body["asOfCheckpoint"] is None


corpus = json.load(open(sys.argv[1], encoding="utf-8"))
out = []
for case in corpus["cases"]:
    try:
        ok = check(case, corpus["now"])
    except (AssertionError, ValueError, KeyError, TypeError):
        ok = False
    out.append(dict(name=case["name"], accepted=ok))
print(json.dumps(out))
