"""Offline verifier for PRAMAAN portable evidence packages (feature F5; synthetic, informational only).

STANDALONE ON PURPOSE: this module imports only the standard library, `cryptography` (Ed25519, hash-pinned in ci/requirements-hackathon-crypto.lock) and, lazily and only when
an opened ledger row must be re-hashed, `rfc8785`. It never opens a ledger, never imports the service, server or anchors code, and writes nothing.

Format: a SUBSET of IETF RFC 9901 (SD-JWT), labelled `PRAMAAN-EVIDENCE/1`, typ `pramaan-evidence+sd-jwt`.
  Implemented: compact serialization `<issuer-signed JWT>~<Disclosure>~...~` (trailing `~`, no key-binding JWT); `_sd` digests with `_sd_alg` sha-256;
  object-property Disclosures `[salt, name, value]`; decoy digests; Disclosure hashing over the base64url string as received; duplicate-digest, duplicate-name,
  unmatched-Disclosure, reserved-name (`_sd`, `...`) and plain-claim-collision rejection; JWS alg EdDSA (Ed25519, RFC 8037) only.
  NOT implemented (documented in docs/hackathon_features/F5_IMPLEMENTATION.md): array-element Disclosures (`...`), nested/recursive Disclosures, Key Binding JWT
  (recipient binding is the issuer-signed `aud` claim, which is weaker than RFC 9901 holder key binding), any `alg` other than EdDSA, `_sd_alg` other than sha-256,
  JSON serialization, issuer key discovery (the issuer key is PINNED by the verifier's operator).

The result separates what was checked from what cannot be checked offline. `accepted` means only: signature, commitments, closed claim set, validity window and (when
asked) recipient all hold. It is never a release clearance.
"""
import base64
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

FORMAT = "PRAMAAN-EVIDENCE/1"
TYP = "pramaan-evidence+sd-jwt"
STATUS_TYP = "pramaan-evidence-status+jwt"
PURPOSE = "RECALL_EVIDENCE_NOTICE"
MAX_LIFETIME_SECONDS = 7 * 24 * 3600
CLOCK_SKEW_SECONDS = 60
RESERVED_NAMES = ("_sd", "...")

# The frozen evaluator schema (recall-engine/pramaan_recall/policy.py: EXCL/AFF/UNRES; engine.py ACTION). A test asserts these equal the engine's own constants.
FINDINGS = ("AFFECTED", "EXCLUDED_WITH_EVIDENCE", "UNRESOLVED")
ACTIONS_ISSUABLE = ("RECALL_HOLD",)          # RELEASE_ELIGIBLE exists in the schema but is NEVER issuable or accepted: a package must not be readable as clearance

CUSTOMER_CLAIMS = ("motorSerial", "recallId", "evidenceFinding", "operationalAction")
SUPPLIER_CLAIMS = ("recallId", "part", "lot", "slot", "supplierId", "evidenceFinding", "operationalAction")
AUDITOR_ONLY = ("installEventId", "decisionId", "policyDigest", "registryDigest", "headHash", "sequence", "eventRow", "eventRowIndex")
ALL_CLAIMS = tuple(dict.fromkeys(CUSTOMER_CLAIMS + SUPPLIER_CLAIMS + AUDITOR_ONLY))
PROFILES = {
    "customer": dict(disclosed=CUSTOMER_CLAIMS, required=("motorSerial", "evidenceFinding", "operationalAction")),
    "supplier": dict(disclosed=SUPPLIER_CLAIMS, required=("lot", "slot", "supplierId", "evidenceFinding", "operationalAction")),
    "auditor": dict(disclosed=tuple(c for c in ALL_CLAIMS), required=("motorSerial", "evidenceFinding", "operationalAction")),
}
PAYLOAD_FIELDS = {"iss", "aud", "iat", "exp", "jti", "_sd_alg", "_sd", "format", "profile", "purpose", "binding"}
NOTICE = "Informational evidence only. Not a release clearance, shipment permission or finding. Physical product truth is not verified."


class Rejected(Exception):
    def __init__(self, code, detail=""):
        super().__init__(code + (": " + detail if detail else ""))
        self.code, self.detail = code, detail


def b64u(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64u_decode(text):
    """Strict base64url without padding; rejects non-canonical encodings."""
    if not isinstance(text, str) or not re.fullmatch(r"[A-Za-z0-9_-]*", text) or len(text) % 4 == 1:
        raise Rejected("MALFORMED_BASE64URL")
    raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    if b64u(raw) != text:
        raise Rejected("MALFORMED_BASE64URL", "non-canonical")
    return raw


def disclosure_digest(disclosure):
    return b64u(hashlib.sha256(disclosure.encode("ascii")).digest())


def load_public_key(source):
    """Pinned issuer key: a JSON object {"kty":"OKP","crv":"Ed25519","kid":...,"x":...} (a path, text or dict)."""
    doc = source
    try:
        if isinstance(source, Path) or (isinstance(source, str) and not source.lstrip().startswith("{")):
            doc = json.loads(Path(source).read_text(encoding="utf-8"))
        elif isinstance(source, str):
            doc = json.loads(source)
    except (OSError, ValueError) as exc:
        raise Rejected("BAD_PINNED_KEY", "unreadable or not JSON") from exc
    if not isinstance(doc, dict) or doc.get("kty") != "OKP" or doc.get("crv") != "Ed25519" or not isinstance(doc.get("x"), str) or not isinstance(doc.get("kid"), str):
        raise Rejected("BAD_PINNED_KEY")
    raw = b64u_decode(doc["x"])
    if len(raw) != 32:
        raise Rejected("BAD_PINNED_KEY")
    return doc["kid"], Ed25519PublicKey.from_public_bytes(raw)


def key_id(raw_public):
    return hashlib.sha256(raw_public).hexdigest()[:16]


def _json(raw, what):
    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
    except (ValueError, UnicodeDecodeError) as exc:
        raise Rejected("MALFORMED_JSON", what) from exc
    return value


def _epoch(now):
    if now is None:
        return int(time.time())
    if isinstance(now, (int, float)):
        return int(now)
    return int(datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())


def _verify_jws(compact, key, kid, expected_typ):
    parts = compact.split(".")
    if len(parts) != 3:
        raise Rejected("MALFORMED_JWS")
    header = _json(b64u_decode(parts[0]), "header")
    if not isinstance(header, dict) or set(header) - {"alg", "typ", "kid"}:
        raise Rejected("UNEXPECTED_HEADER", "only alg, typ, kid are accepted")
    if header.get("alg") != "EdDSA":
        raise Rejected("UNSUPPORTED_ALG", str(header.get("alg")))
    if header.get("typ") != expected_typ:
        raise Rejected("WRONG_TYP", str(header.get("typ")))
    if header.get("kid") != kid:
        raise Rejected("WRONG_ISSUER_KEY", "kid does not match the pinned key")
    signature = b64u_decode(parts[2])
    if len(signature) != 64:
        raise Rejected("BAD_SIGNATURE", "length")
    try:
        key.verify(signature, (parts[0] + "." + parts[1]).encode("ascii"))
    except InvalidSignature as exc:
        raise Rejected("BAD_SIGNATURE") from exc
    payload = _json(b64u_decode(parts[1]), "payload")
    if not isinstance(payload, dict):
        raise Rejected("MALFORMED_JSON", "payload")
    return payload


def row_digest(row):
    import rfc8785                                   # lazily: only an opened ledger row needs JCS
    return hashlib.sha256(rfc8785.dumps([v.hex() if isinstance(v, bytes) else v for v in row])).hexdigest()


def checkpoint_checksum(body):
    import rfc8785
    return hashlib.sha256(rfc8785.dumps(body)).hexdigest()


def verify(token, *, issuer_key, recipient=None, now=None, checkpoint=None, status=None, expected_profile=None):
    """Returns a result dict; never raises on a malformed or hostile package. `accepted` is cryptographic acceptance only."""
    checks = dict(signature="NOT_CHECKED", claimCommitments="NOT_CHECKED", intendedRecipient="NOT_CHECKED", validityWindow="NOT_CHECKED",
                  checkpointBinding="ISSUER_ASSERTED_ONLY", freshnessRevocation="UNKNOWN_WITHOUT_EXTERNAL_EVIDENCE", physicalProductTruth="UNVERIFIED")
    result = dict(accepted=False, format=FORMAT, failure=None, detail="", checks=checks, claims={}, profile=None, issuer=None, audience=None, jti=None,
                  notDisclosed=[], warnings=[], clearance="NONE", notice=NOTICE)
    try:
        kid, key = load_public_key(issuer_key)
        _check(token, kid, key, recipient, now, checkpoint, status, expected_profile, result)
        result["accepted"] = True
    except Rejected as exc:
        result["failure"], result["detail"] = exc.code, exc.detail
    except (ValueError, KeyError, TypeError, IndexError, UnicodeError) as exc:           # a hostile package must never crash the verifier into an ambiguous state
        result["failure"], result["detail"] = "MALFORMED_PACKAGE", type(exc).__name__
    return result


def _check(token, kid, key, recipient, now, checkpoint, status, expected_profile, result):
    checks = result["checks"]
    if not isinstance(token, str) or not token.endswith("~") or not token.isascii():
        raise Rejected("MALFORMED_SD_JWT", "compact SD-JWT without key binding must end with '~'")
    jwt, *disclosures = token[:-1].split("~")
    if disclosures and disclosures[-1] == "" and len(disclosures) > 0:
        raise Rejected("MALFORMED_SD_JWT", "empty Disclosure")
    payload = _verify_jws(jwt, key, kid, TYP)
    checks["signature"] = "VALID_UNDER_PINNED_ISSUER_KEY"
    if set(payload) - PAYLOAD_FIELDS or any(c in payload for c in ALL_CLAIMS):
        raise Rejected("UNEXPECTED_CLAIM", "payload carries a field outside the closed set")
    for field in ("iss", "aud", "jti", "format", "profile", "purpose"):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise Rejected("MISSING_CLAIM", field)
    if payload["format"] != FORMAT or payload["purpose"] != PURPOSE:
        raise Rejected("UNSUPPORTED_FORMAT")
    if payload["profile"] not in PROFILES or (expected_profile and payload["profile"] != expected_profile):
        raise Rejected("WRONG_PROFILE", str(payload["profile"]))
    if payload.get("_sd_alg") != "sha-256":
        raise Rejected("UNSUPPORTED_SD_ALG")
    digests = payload.get("_sd")
    if not isinstance(digests, list) or not digests or any(not isinstance(d, str) for d in digests):
        raise Rejected("MALFORMED_SD")
    if len(set(digests)) != len(digests):
        raise Rejected("DUPLICATE_DIGEST")
    for d in digests:
        if len(b64u_decode(d)) != 32:
            raise Rejected("MALFORMED_SD", "digest length")
    profile = PROFILES[payload["profile"]]
    # --- disclosures -> commitments
    claims, seen = {}, set()
    for text in disclosures:
        if text in seen:
            raise Rejected("DUPLICATE_DISCLOSURE")
        seen.add(text)
        item = _json(b64u_decode(text), "disclosure")
        if not isinstance(item, list) or len(item) != 3 or not isinstance(item[0], str) or not isinstance(item[1], str):
            raise Rejected("MALFORMED_DISCLOSURE")
        salt, name, value = item
        if len(salt) < 16:
            raise Rejected("WEAK_SALT")
        if name in RESERVED_NAMES:
            raise Rejected("RESERVED_CLAIM_NAME", name)
        if name not in profile["disclosed"]:
            raise Rejected("UNEXPECTED_CLAIM", name)
        if name in claims:
            raise Rejected("DUPLICATE_CLAIM_NAME", name)
        if disclosure_digest(text) not in digests:
            raise Rejected("DISCLOSURE_NOT_COMMITTED", name)
        claims[name] = value
    checks["claimCommitments"] = f"VALID ({len(claims)} disclosed of {len(digests)} committed digests incl. decoys)"
    _claim_values(claims)
    missing = [c for c in profile["required"] if c not in claims]
    if missing:
        result["warnings"].append("INCOMPLETE_FOR_PROFILE: " + ",".join(missing))
    result["notDisclosed"] = f"{len(digests) - len(claims)} committed digests are not opened (hidden claims and decoys are indistinguishable)"
    result.update(claims=claims, profile=payload["profile"], issuer=payload["iss"], audience=payload["aud"], jti=payload["jti"])
    # --- recipient
    if recipient is not None:
        if payload["aud"] != recipient:
            raise Rejected("AUDIENCE_MISMATCH", f"package is for {payload['aud']!r}")
        checks["intendedRecipient"] = "MATCHES"
    else:
        result["warnings"].append("RECIPIENT_NOT_CHECKED: no --recipient supplied")
    # --- time
    iat, exp, at = payload.get("iat"), payload.get("exp"), _epoch(now)
    if type(iat) is not int or type(exp) is not int or exp <= iat or exp - iat > MAX_LIFETIME_SECONDS:
        raise Rejected("INVALID_EXPIRY")
    if at < iat - CLOCK_SKEW_SECONDS:
        raise Rejected("NOT_YET_VALID")
    if at >= exp:
        raise Rejected("EXPIRED")
    checks["validityWindow"] = "WITHIN_WINDOW_BY_VERIFIER_CLOCK (the clock is not signed or attested)"
    # --- binding
    binding = payload.get("binding")
    if not isinstance(binding, dict) or not isinstance(binding.get("checkpointChecksum"), str) or set(binding) - {"checkpointChecksum", "checkpointFormat", "state"}:
        raise Rejected("MALFORMED_BINDING")
    if binding.get("state") != "ANCHORED_CURRENT":
        raise Rejected("BINDING_STATE", "package must be issued against an ANCHORED_CURRENT checkpoint")
    if checkpoint is not None:
        _bind(binding, claims, checkpoint, checks)
    # --- optional status list
    if status is not None:
        _status(status, key, kid, payload, result)


def _claim_values(claims):
    if "operationalAction" in claims and claims["operationalAction"] not in ACTIONS_ISSUABLE:
        raise Rejected("ACTION_NOT_ACCEPTABLE", f"{claims['operationalAction']!r}: only held motors are described; a package is never a clearance")
    if "evidenceFinding" in claims and claims["evidenceFinding"] not in FINDINGS:
        raise Rejected("UNKNOWN_FINDING", str(claims["evidenceFinding"]))
    for name in ("motorSerial", "recallId", "part", "lot", "slot", "supplierId", "installEventId", "decisionId", "policyDigest", "registryDigest", "headHash"):
        if name in claims and (not isinstance(claims[name], str) or not claims[name] or len(claims[name]) > 512):
            raise Rejected("BAD_CLAIM_VALUE", name)
    if "slot" in claims and claims["slot"] not in ("DE", "NDE"):
        raise Rejected("BAD_CLAIM_VALUE", "slot")
    if "sequence" in claims and type(claims["sequence"]) is not int:
        raise Rejected("BAD_CLAIM_VALUE", "sequence")
    if "eventRowIndex" in claims and (type(claims["eventRowIndex"]) is not int or claims["eventRowIndex"] < 0):
        raise Rejected("BAD_CLAIM_VALUE", "eventRowIndex")
    if "eventRow" in claims and not (isinstance(claims["eventRow"], list) and len(claims["eventRow"]) == 10 and all(isinstance(v, (str, int)) for v in claims["eventRow"])):
        raise Rejected("BAD_CLAIM_VALUE", "eventRow")


def _bind(binding, claims, checkpoint, checks):
    doc = checkpoint
    if isinstance(checkpoint, (str, Path)):
        doc = json.loads(Path(checkpoint).read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or not isinstance(doc.get("body"), dict) or not isinstance(doc.get("checksum"), str):
        raise Rejected("CHECKPOINT_MALFORMED")
    body = doc["body"]
    if checkpoint_checksum(body) != doc["checksum"]:
        raise Rejected("CHECKPOINT_CHECKSUM_INVALID")
    if doc["checksum"] != binding["checkpointChecksum"]:
        raise Rejected("CHECKPOINT_MISMATCH", "package is bound to a different checkpoint")
    if binding.get("checkpointFormat") != body.get("format"):
        raise Rejected("CHECKPOINT_MISMATCH", "format")
    for claim, key in (("policyDigest", "policyDigest"), ("headHash", "headHash"), ("sequence", "sequence"), ("registryDigest", None)):
        if claim in claims:
            actual = body.get("registryBinding", {}).get("registryDigest") if key is None else body.get(key)
            if claims[claim] != actual:
                raise Rejected("CHECKPOINT_MISMATCH", claim)
    level = "CHECKPOINT_DEMONSTRATED (package refers to this checkpoint; its claims are still issuer-asserted unless an event row is opened)"
    if "eventRow" in claims or "eventRowIndex" in claims:
        if not ("eventRow" in claims and "eventRowIndex" in claims):
            raise Rejected("EVENT_ROW_INCOMPLETE")
        rows = body.get("ledger", {}).get("rows", {}).get("events", [])
        idx, row = claims["eventRowIndex"], claims["eventRow"]
        if idx >= len(rows) or row_digest(row) != rows[idx]:
            raise Rejected("EVENT_ROW_NOT_IN_CHECKPOINT")
        native = json.loads(row[5])
        for claim, actual in (("installEventId", row[1]), ("motorSerial", row[2]), ("lot", native.get("payload", {}).get("lot")), ("slot", native.get("payload", {}).get("slot"))):
            if claim in claims and claims[claim] != actual:
                raise Rejected("EVENT_ROW_CLAIM_MISMATCH", claim)
        level = "CLAIMS_BOUND_TO_CHECKPOINT_ROW (opened event row re-hashes to the checkpoint's row digest; the checkpoint itself is same-host custody)"
    checks["checkpointBinding"] = level


def _status(status, key, kid, payload, result):
    compact = Path(status).read_text(encoding="utf-8").strip() if isinstance(status, Path) else status
    doc = _verify_jws(compact, key, kid, STATUS_TYP)
    if doc.get("iss") != payload["iss"] or not isinstance(doc.get("revoked"), list) or type(doc.get("asOf")) is not int:
        raise Rejected("STATUS_MALFORMED")
    if payload["jti"] in doc["revoked"]:
        raise Rejected("REVOKED", "listed as revoked in the supplied issuer status list")
    result["checks"]["freshnessRevocation"] = f"NOT_LISTED_AS_REVOKED_AS_OF_{doc['asOf']} (a status list proves nothing after its own date; currency remains unconfirmed)"


def render(result):
    c = result["checks"]
    lines = ["ACCEPTED (cryptographic checks only)" if result["accepted"] else f"REJECTED: {result['failure']} {result['detail']}".rstrip(),
             f"  signature              : {c['signature']}", f"  claim commitments      : {c['claimCommitments']}",
             f"  intended recipient     : {c['intendedRecipient']}", f"  validity window        : {c['validityWindow']}",
             f"  checkpoint binding     : {c['checkpointBinding']}", f"  freshness / revocation : {c['freshnessRevocation']}",
             f"  physical product truth : {c['physicalProductTruth']}", f"  profile / audience     : {result['profile']} / {result['audience']}", "  disclosed claims:"]
    lines += [f"    {k} = {json.dumps(v) if k != 'eventRow' else '[opened ledger row, 10 fields]'}" for k, v in result["claims"].items()]
    lines += ["  not disclosed: " + str(result["notDisclosed"])] if result["accepted"] else []
    lines += ["  warning: " + w for w in result["warnings"]]
    lines += ["  " + result["notice"]]
    return "\n".join(lines)


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description="Offline verifier for PRAMAAN portable evidence packages (informational only).")
    p.add_argument("package", type=Path)
    p.add_argument("--issuer-key", type=Path, required=True, help="pinned issuer public key JSON (obtained out of band)")
    p.add_argument("--recipient", help="the recipient id this package must be addressed to")
    p.add_argument("--checkpoint", type=Path, help="checkpoint file (auditor scope only; it lists every motor serial)")
    p.add_argument("--status", type=Path, help="issuer-signed status list")
    p.add_argument("--now", help="verification time YYYY-MM-DDTHH:MM:SSZ (default: system clock)")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    result = verify(a.package.read_text(encoding="utf-8").strip() + "", issuer_key=a.issuer_key, recipient=a.recipient, now=a.now, checkpoint=a.checkpoint,
                    status=a.status)
    print(json.dumps(result, indent=1, ensure_ascii=False) if a.json else render(result))
    return 0 if result["accepted"] else 2


if __name__ == "__main__":
    sys.exit(main())
