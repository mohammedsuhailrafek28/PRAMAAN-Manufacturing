"""Issuer side of the F5 portable evidence package (synthetic, informational only). Verification lives in the standalone `evidence_verify.py`.

Issuing READS the ledger through the existing, unchanged `Manufacturing.snapshot(trusted_anchor=...)` and the existing FORMAT_V3 checkpoint file; it writes only the package
file. It never calls announce/ship/assemble/observe, never changes the evaluator, ledger or checkpoint, and an imported package can never be loaded back into a ledger.

Refusals (IssuanceRefused): checkpoint not ANCHORED_CURRENT; motor unknown or without a decision; evaluator action other than RECALL_HOLD (in particular RELEASE_ELIGIBLE: a package
must never be readable as clearance); supplier profile without an established-identity AFFECTED installation of an affected lot; auditor event row without explicit authorization.
The issuer key lives on the same host as the ledger: same-host custody is not independent verification.

    python -B -m application.evidence_package keygen --out-dir KEYS
    python -B -m application.evidence_package issue --database DB --anchor CHECKPOINT --motor M --recipient ID --profile customer|supplier|auditor --key KEYS/issuer-ed25519.key.pem --out FILE
"""
import argparse
import json
import secrets
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from . import evidence_verify as V

TOTAL_DIGESTS = 24                       # every package carries exactly this many digests (hidden claims + decoys) so the claim count does not leak
DEFAULT_TTL = 3600
DEFAULT_ISSUER = "urn:pramaan:synthetic:factory:aster-motors"
PART = "BR-6205"


class IssuanceRefused(Exception):
    pass


def keygen(out_dir):
    out = Path(out_dir)
    private_path, public_path = out / "issuer-ed25519.key.pem", out / "issuer-ed25519.pub.json"
    if private_path.exists() or public_path.exists():
        raise IssuanceRefused("refusing to overwrite an existing issuer key")
    out.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    raw_public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    private_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    public_path.write_text(json.dumps(dict(kty="OKP", crv="Ed25519", kid=V.key_id(raw_public), x=V.b64u(raw_public)), indent=1), encoding="utf-8")
    return private_path, public_path


def load_private(path):
    key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise IssuanceRefused("issuer key must be Ed25519")
    raw_public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return key, V.key_id(raw_public)


def _jws(key, kid, typ, payload):
    header = V.b64u(json.dumps(dict(alg="EdDSA", typ=typ, kid=kid), separators=(",", ":")).encode())
    body = V.b64u(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    return f"{header}.{body}.{V.b64u(key.sign((header + '.' + body).encode('ascii')))}"


def _disclosure(name, value):
    salt = secrets.token_urlsafe(16)                                    # 128-bit CSPRNG salt, fresh per claim per package
    text = V.b64u(json.dumps([salt, name, value], separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    return text, V.disclosure_digest(text)


def collect(database, anchor, previous_anchor, motor, *, include_event_row, lot_registry=None):
    """Read-only extraction of every claim this motor can support, straight from the existing snapshot (no remapping of decision values)."""
    from .anchors import TrustedAnchor
    from .service import Manufacturing                                   # issuer side only; the verifier never imports these
    app = Manufacturing(database, lot_registry=lot_registry)
    try:
        snap = app.snapshot(trusted_anchor=TrustedAnchor(Path(anchor), Path(previous_anchor) if previous_anchor else None))
        if snap["checkpoint"]["state"] != "ANCHORED_CURRENT":
            raise IssuanceRefused(f"checkpoint is {snap['checkpoint']['state']}, not ANCHORED_CURRENT: no package is issued")
        decisions = snap["decisions"].get(motor)
        if not decisions or not snap["recallAnnounced"]:
            raise IssuanceRefused("no recall decision exists for this motor")
        current = next(iter(decisions.values()))["current"]
        action, finding = current["operationalAction"], current["evidenceFinding"]
        if action not in V.ACTIONS_ISSUABLE:
            raise IssuanceRefused(f"operational action {action!r}: packages describe held motors only and are never issued as clearance")
        if finding not in V.FINDINGS:
            raise IssuanceRefused(f"unknown evidence finding {finding!r}")
        policy = snap["recall"]
        doc = json.loads(Path(anchor).read_bytes())
        body = doc["body"]
        claims = dict(motorSerial=motor, recallId=current["recallId"], evidenceFinding=finding, operationalAction=action, decisionId=current["decisionId"],
                      policyDigest=body["policyDigest"], registryDigest=body["registryBinding"]["registryDigest"], headHash=body["headHash"], sequence=body["sequence"])
        established = current.get("identityGuard", {}).get("status") == "IDENTITY_ESTABLISHED_LOCAL_REGISTRY"
        component = next((c for c in snap["components"] if c["unitId"] == motor and c.get("removedAt") is None and c["lot"] in policy["affectedLots"]
                          and c["slot"] in policy["affectedSlots"]), None)
        if established and finding == "AFFECTED" and component:
            entry = app.registry.resolve(component["lot"], at=app.clock(), part=PART).entry
            if entry:
                claims.update(part=component["part"], lot=component["lot"], slot=component["slot"], supplierId=entry["supplierId"], installEventId=component["componentId"])
                if include_event_row:
                    rows = [tuple(r) for r in app.db.execute("SELECT * FROM events ORDER BY rowid")]
                    for index, row in enumerate(rows):
                        if row[1] == component["componentId"]:
                            claims.update(eventRow=list(row), eventRowIndex=index)
                            break
        return claims, dict(checkpointChecksum=doc["checksum"], checkpointFormat=body["format"], state="ANCHORED_CURRENT")
    finally:
        app.close()


def issue(*, database, anchor, motor, recipient, profile, key_path, previous_anchor=None, issuer=DEFAULT_ISSUER, ttl=DEFAULT_TTL, now=None,
          authorize_event_row=False, lot_registry=None):
    if profile not in V.PROFILES:
        raise IssuanceRefused("unknown profile")
    if not isinstance(recipient, str) or not recipient.strip() or len(recipient) > 256:
        raise IssuanceRefused("a recipient id is required")
    if not isinstance(ttl, int) or not 0 < ttl <= V.MAX_LIFETIME_SECONDS:
        raise IssuanceRefused("invalid lifetime")
    if authorize_event_row and profile != "auditor":
        raise IssuanceRefused("an opened ledger row is only ever issued to the auditor profile")
    key, kid = load_private(key_path)
    claims, binding = collect(database, anchor, previous_anchor, motor, include_event_row=authorize_event_row, lot_registry=lot_registry)
    spec = V.PROFILES[profile]
    missing = [c for c in spec["required"] if c not in claims]
    if missing:
        raise IssuanceRefused(f"{profile} profile cannot be supported by the evidence: missing {','.join(missing)}")
    if profile != "auditor":
        for name in V.AUDITOR_ONLY:
            claims.pop(name, None)                                       # never even commit auditor-only values (including the ledger row) for other recipients
    entries = {name: _disclosure(name, value) for name, value in claims.items()}
    digests = [d for _, d in entries.values()]
    while len(digests) < TOTAL_DIGESTS:
        digests.append(V.b64u(__import__("hashlib").sha256(secrets.token_bytes(32)).digest()))          # decoy: hash of random bytes
    digests.sort()
    issued = int(time.time()) if now is None else int(now)
    payload = dict(iss=issuer, aud=recipient, iat=issued, exp=issued + ttl, jti=V.b64u(secrets.token_bytes(16)), _sd_alg="sha-256", _sd=digests,
                   format=V.FORMAT, profile=profile, purpose=V.PURPOSE, binding=binding)
    disclosed = [text for name, (text, _) in entries.items() if name in spec["disclosed"]]
    secrets.SystemRandom().shuffle(disclosed)
    return _jws(key, kid, V.TYP, payload) + "~" + "".join(d + "~" for d in disclosed)


def status_list(key_path, revoked, *, issuer=DEFAULT_ISSUER, now=None):
    key, kid = load_private(key_path)
    return _jws(key, kid, V.STATUS_TYP, dict(iss=issuer, asOf=int(time.time()) if now is None else int(now), revoked=sorted(revoked)))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keygen"); k.add_argument("--out-dir", type=Path, required=True)
    i = sub.add_parser("issue")
    i.add_argument("--database", type=Path, required=True); i.add_argument("--anchor", type=Path, required=True); i.add_argument("--previous-anchor", type=Path)
    i.add_argument("--motor", required=True); i.add_argument("--recipient", required=True); i.add_argument("--profile", choices=sorted(V.PROFILES), required=True)
    i.add_argument("--key", type=Path, required=True); i.add_argument("--out", type=Path, required=True); i.add_argument("--ttl", type=int, default=DEFAULT_TTL)
    i.add_argument("--authorize-event-row", action="store_true", help="auditor only: explicitly authorize opening the ledger row of the install event")
    s = sub.add_parser("status"); s.add_argument("--key", type=Path, required=True); s.add_argument("--revoke", action="append", default=[]); s.add_argument("--out", type=Path, required=True)
    a = p.parse_args(argv)
    try:
        if a.cmd == "keygen":
            print(json.dumps(dict(zip(("privateKey", "publicKey"), map(str, keygen(a.out_dir))))))
        elif a.cmd == "issue":
            a.out.write_text(issue(database=a.database, anchor=a.anchor, previous_anchor=a.previous_anchor, motor=a.motor, recipient=a.recipient, profile=a.profile,
                                   key_path=a.key, ttl=a.ttl, authorize_event_row=a.authorize_event_row), encoding="utf-8")
            print(json.dumps(dict(issued=str(a.out), profile=a.profile, recipient=a.recipient, bytes=a.out.stat().st_size)))
        else:
            a.out.write_text(status_list(a.key, a.revoke), encoding="utf-8"); print(json.dumps(dict(status=str(a.out), revoked=a.revoke)))
    except IssuanceRefused as exc:
        print(json.dumps(dict(refused=str(exc))), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
