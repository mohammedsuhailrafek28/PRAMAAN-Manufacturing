"""Signed message envelope `PRAMAAN-FED/1` (ALERT from a supplier, RESPONSE from a factory). Ed25519 via the hash-pinned `cryptography` package; no custom primitives.

Envelope: {"format","kid","body","signature"}. The signature covers b"PRAMAAN-FED/1\\0" + JCS(body) (RFC 8785). The message hash chained by `prevHash` is SHA-256(JCS(body)).
Closed field sets: an unknown or missing field rejects the message. Verification never raises on hostile input; it returns a Rejection with a distinct reason code.
"""
import base64
import hashlib
import re
import time
from dataclasses import dataclass

import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

FORMAT = "PRAMAAN-FED/1"
MAX_LIFETIME_SECONDS = 7 * 24 * 3600
CLOCK_SKEW_SECONDS = 60
SLOTS = ("DE", "NDE")
FINDINGS = ("AFFECTED", "UNRESOLVED", "EXCLUDED_WITH_EVIDENCE")          # frozen evaluator values (recall-engine policy.py)
STATUSES = ("PENDING_OPERATOR", "PENDING_CHECKPOINT", "ANSWERED", "LOT_UNMAPPED", "ADOPTION_REFUSED")
ALERT_FIELDS = {"type", "alertId", "issuer", "seq", "prevHash", "iat", "exp", "lot", "affectedSlots", "humanText", "recipients"}
RESPONSE_FIELDS = {"type", "responseId", "alertId", "alertHash", "responder", "seq", "prevHash", "iat", "status", "counts", "asOfCheckpoint"}
_ID = re.compile(r"[A-Za-z0-9:._-]{1,128}")
_HEX = re.compile(r"[0-9a-f]{64}")


@dataclass
class Rejection(Exception):
    reason: str
    detail: str = ""

    def __str__(self):
        return self.reason + (": " + self.detail if self.detail else "")


def b64u(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64u_decode(text):
    if not isinstance(text, str) or not re.fullmatch(r"[A-Za-z0-9_-]*", text) or len(text) % 4 == 1:
        raise Rejection("MALFORMED_ENCODING")
    raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    if b64u(raw) != text:
        raise Rejection("MALFORMED_ENCODING", "non-canonical")
    return raw


def key_id(raw_public):
    return hashlib.sha256(raw_public).hexdigest()[:16]


def message_hash(body):
    return hashlib.sha256(rfc8785.dumps(body)).hexdigest()


def _signing_input(body):
    return FORMAT.encode("ascii") + b"\0" + rfc8785.dumps(body)


def generate_key():
    key = Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return key, raw


def load_private(pem_bytes):
    key = serialization.load_pem_private_key(pem_bytes, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise Rejection("BAD_KEY", "Ed25519 required")
    return key, key_id(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))


def sign(body, key, kid):
    return dict(format=FORMAT, kid=kid, body=body, signature=b64u(key.sign(_signing_input(body))))


def verify_envelope(envelope, trust, *, expected_type):
    """Authenticate under a pinned key and return the body. `trust` maps peer id -> (role, kid, Ed25519PublicKey). Raises Rejection."""
    if not isinstance(envelope, dict) or set(envelope) != {"format", "kid", "body", "signature"} or envelope.get("format") != FORMAT:
        raise Rejection("MALFORMED_ENVELOPE")
    body = envelope["body"]
    if not isinstance(body, dict) or body.get("type") != expected_type:
        raise Rejection("UNSUPPORTED_TYPE", str(body.get("type") if isinstance(body, dict) else None))
    who = body.get("issuer" if expected_type == "ALERT" else "responder")
    peer = trust.get(who) if isinstance(who, str) else None
    if peer is None:
        raise Rejection("UNKNOWN_SENDER", str(who))
    role, kid, public = peer
    if role != ("supplier" if expected_type == "ALERT" else "factory"):
        raise Rejection("WRONG_SENDER_ROLE", f"{who} is {role}")
    if envelope["kid"] != kid:
        raise Rejection("WRONG_KEY", "kid does not match the pinned key for this sender")
    signature = b64u_decode(envelope["signature"]) if isinstance(envelope["signature"], str) else None
    if signature is None or len(signature) != 64:
        raise Rejection("BAD_SIGNATURE", "length")
    try:
        public.verify(signature, _signing_input(body))
    except InvalidSignature as exc:
        raise Rejection("BAD_SIGNATURE") from exc
    except (TypeError, ValueError) as exc:                                   # e.g. a body JCS cannot canonicalise
        raise Rejection("MALFORMED_ENVELOPE", type(exc).__name__) from exc
    return body


def _text(value, limit):
    return isinstance(value, str) and 0 < len(value) <= limit and value.isprintable()


def validate_alert(body):
    if set(body) - ALERT_FIELDS or {"type", "alertId", "issuer", "seq", "prevHash", "iat", "exp", "lot", "affectedSlots", "humanText"} - set(body):
        raise Rejection("MALFORMED_BODY", "closed field set")
    if not all(isinstance(body[k], str) and _ID.fullmatch(body[k]) for k in ("alertId", "issuer")):
        raise Rejection("MALFORMED_BODY", "ids")
    if type(body["seq"]) is not int or body["seq"] < 1:
        raise Rejection("MALFORMED_BODY", "seq")
    if body["prevHash"] is not None and not (isinstance(body["prevHash"], str) and _HEX.fullmatch(body["prevHash"])):
        raise Rejection("MALFORMED_BODY", "prevHash")
    if (body["seq"] == 1) != (body["prevHash"] is None):
        raise Rejection("MALFORMED_BODY", "prevHash must be null exactly for seq 1")
    lot = body["lot"]
    if not isinstance(lot, dict) or set(lot) != {"supplierId", "part", "supplierLot"} or not all(_text(lot[k], 80) for k in lot):
        raise Rejection("MALFORMED_BODY", "lot must be exactly supplierId, part, supplierLot")
    slots = body["affectedSlots"]
    if not isinstance(slots, list) or not slots or len(set(slots)) != len(slots) or any(s not in SLOTS for s in slots):
        raise Rejection("MALFORMED_BODY", "affectedSlots")
    if not _text(body["humanText"], 500):
        raise Rejection("MALFORMED_BODY", "humanText")
    recipients = body.get("recipients")
    if recipients is not None and not (isinstance(recipients, list) and recipients and all(isinstance(r, str) and _ID.fullmatch(r) for r in recipients)):
        raise Rejection("MALFORMED_BODY", "recipients")
    return body


def validate_response(body):
    if set(body) != RESPONSE_FIELDS:
        raise Rejection("MALFORMED_BODY", "closed field set")
    if not all(isinstance(body[k], str) and _ID.fullmatch(body[k]) for k in ("responseId", "alertId", "responder")):
        raise Rejection("MALFORMED_BODY", "ids")
    if not (isinstance(body["alertHash"], str) and _HEX.fullmatch(body["alertHash"])):
        raise Rejection("MALFORMED_BODY", "alertHash")
    if type(body["seq"]) is not int or body["seq"] < 1 or (body["seq"] == 1) != (body["prevHash"] is None):
        raise Rejection("MALFORMED_BODY", "seq/prevHash")
    if body["prevHash"] is not None and not (isinstance(body["prevHash"], str) and _HEX.fullmatch(body["prevHash"])):
        raise Rejection("MALFORMED_BODY", "prevHash")
    if body["status"] not in STATUSES:
        raise Rejection("MALFORMED_BODY", "status")
    counts = body["counts"]
    if body["status"] == "ANSWERED":
        if not (isinstance(counts, dict) and set(counts) == {"heldMotors", "heldByEvidenceFinding", "heldOnlyByIdentityGuard"}):
            raise Rejection("MALFORMED_BODY", "counts must be exactly heldMotors, heldByEvidenceFinding, heldOnlyByIdentityGuard")
        by = counts["heldByEvidenceFinding"]
        if type(counts["heldMotors"]) is not int or counts["heldMotors"] < 0 or not isinstance(by, dict) or set(by) != set(FINDINGS) \
                or any(type(v) is not int or v < 0 for v in by.values()) or sum(by.values()) != counts["heldMotors"] \
                or type(counts["heldOnlyByIdentityGuard"]) is not int or not 0 <= counts["heldOnlyByIdentityGuard"] <= counts["heldMotors"]:
            raise Rejection("MALFORMED_BODY", "counts values")
        if not (isinstance(body["asOfCheckpoint"], str) and _HEX.fullmatch(body["asOfCheckpoint"])):
            raise Rejection("MALFORMED_BODY", "asOfCheckpoint")
    elif counts is not None or body["asOfCheckpoint"] is not None:
        raise Rejection("MALFORMED_BODY", "counts only accompany ANSWERED")
    return body


def check_window(body, now=None):
    at = int(time.time()) if now is None else int(now)
    iat, exp = body.get("iat"), body.get("exp")
    if type(iat) is not int or type(exp) is not int or exp <= iat or exp - iat > MAX_LIFETIME_SECONDS:
        raise Rejection("INVALID_EXPIRY")
    if at < iat - CLOCK_SKEW_SECONDS:
        raise Rejection("NOT_YET_VALID")
    if at >= exp:
        raise Rejection("EXPIRED")


def public_from_x(x):
    raw = b64u_decode(x)
    if len(raw) != 32:
        raise Rejection("BAD_KEY", "length")
    return key_id(raw), Ed25519PublicKey.from_public_bytes(raw)
