"""Pinned trust roots and local demo key generation. Keys here are LOCAL DEMO KEYS made on one machine; see federation.TRUST_NOTICE.

A trust file is a JSON document {"format":"PRAMAAN-FED-TRUST/1","notice":...,"peers":[{"id","role","kid","x"}]} that an operator pins for one node.
There is no key discovery, rotation or revocation.
"""
import json
from pathlib import Path

from . import TRUST_NOTICE, messages as M

TRUST_FORMAT = "PRAMAAN-FED-TRUST/1"
ROLES = ("supplier", "factory")


class TrustError(Exception):
    pass


def keygen(out_dir, name, peer_id, role):
    """Writes <name>.key.pem (private) and <name>.pub.json; refuses to overwrite."""
    if role not in ROLES:
        raise TrustError("role must be supplier or factory")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    private_path, public_path = out / f"{name}.key.pem", out / f"{name}.pub.json"
    if private_path.exists() or public_path.exists():
        raise TrustError("refusing to overwrite an existing key")
    from cryptography.hazmat.primitives import serialization
    key, raw = M.generate_key()
    private_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    public_path.write_text(json.dumps(dict(id=peer_id, role=role, kid=M.key_id(raw), x=M.b64u(raw)), indent=1), encoding="utf-8")
    return private_path, public_path


def write_trust(path, public_files):
    peers = [json.loads(Path(p).read_text(encoding="utf-8")) for p in public_files]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(dict(format=TRUST_FORMAT, notice=TRUST_NOTICE, peers=peers), indent=1), encoding="utf-8")
    return Path(path)


def load_trust(path):
    """-> {peer id: (role, kid, public key)}"""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        if doc.get("format") != TRUST_FORMAT or not isinstance(doc.get("peers"), list):
            raise TrustError("not a trust file")
        out = {}
        for peer in doc["peers"]:
            if set(peer) != {"id", "role", "kid", "x"} or peer["role"] not in ROLES or peer["id"] in out:
                raise TrustError("bad or duplicate peer entry")
            kid, public = M.public_from_x(peer["x"])
            if kid != peer["kid"]:
                raise TrustError("kid does not match key")
            out[peer["id"]] = (peer["role"], kid, public)
        return out
    except (OSError, ValueError, M.Rejection) as exc:
        raise TrustError(f"unusable trust file: {exc}") from exc
