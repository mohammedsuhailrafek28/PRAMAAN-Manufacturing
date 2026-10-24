"""Registry binding for checkpoints (FORMAT_V3 research candidate).

FORMAT_V3 carries `registryBinding` (the registry digest) INSIDE the checkpoint body, so it is covered by the checkpoint checksum, chained by
`previousCheckpointHash`, pinned by TrustedAnchor and rolled back/substituted exactly like the ledger prefix. Current release eligibility requires that the
digest authenticated by the verified checkpoint equals the digest of the registry the application is running with.

  OK                    V3 checkpoint, live registry digest equals the authenticated digest
  DISCREPANCY           V3 checkpoint, live registry differs: every motor is held (checkpoint state stays truthful)
  UNBOUND_LEGACY_FORMAT V1/V2 checkpoint: the registry was never inside the verified boundary, so it cannot grant current eligibility (history still verifies)
  INVALID               checkpoint unreadable or its registryBinding block malformed

The optional sidecar `<checkpoint>.registry-binding.json` holds the registry DOCUMENT so a reviewer can see a field-level difference. It is ADVISORY: it never
creates, preserves or removes eligibility. Under V3 it is used only if its document hashes to the authenticated digest.

CUSTODY LIMIT. This puts the registry at the same trust level as the ledger prefix: as strong as the custody of the accepted checkpoint file. It is NOT
independent verification; whoever controls the host controls the checkpoint, the database and the registry. Not authentication, not proof of physical lot identity.
"""
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from . import lot_identity as lots

SUFFIX = ".registry-binding.json"
FORMAT = "PRAMAAN_REGISTRY_BINDING_RESEARCH_V1"          # sidecar
BLOCK_FORMAT = "PRAMAAN_REGISTRY_DIGEST_V1"              # inside the V3 checkpoint body
CHECKPOINT_V3 = "PRAMAAN_A31_ANCHOR_V3"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
CUSTODY_NOTE = "Same-host binding. Detects unreviewed drift; not independent verification, not authentication, not proof of physical lot identity."


def binding_path(checkpoint_path):
    return Path(str(checkpoint_path) + SUFFIX)


def _digest_of(document):
    return lots.LotRegistry(document).digest


def write_binding(checkpoint_path, checkpoint_bytes, registry_document):
    """Exclusive create (never overwrites): the binding for these exact checkpoint bytes."""
    body = dict(format=FORMAT, checkpointSha256=hashlib.sha256(checkpoint_bytes).hexdigest(), registryDigest=_digest_of(registry_document),
                registryProvenance=registry_document.get("provenance"), registryDocument=registry_document, custodyNote=CUSTODY_NOTE)
    path = binding_path(checkpoint_path)
    fd, staging = tempfile.mkstemp(prefix=".binding-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(json.dumps(body, sort_keys=True, indent=1).encode("utf-8")); f.flush(); os.fsync(f.fileno())
        os.link(staging, path)
    finally:
        os.unlink(staging)
    return body


def copy_binding(src_checkpoint, dst_checkpoint):
    """Accepted checkpoint = same bytes as the candidate, so the binding is carried over unchanged (exclusive create)."""
    data = binding_path(src_checkpoint).read_bytes()
    dst = binding_path(dst_checkpoint)
    fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return dst


def _meta(doc):
    return dict(registryId=doc.get("registryId"), version=doc.get("version"), entryCount=len(doc.get("entries", [])))


def binding_block(registry):
    d = registry.document
    return dict(format=BLOCK_FORMAT, registryDigest=registry.digest, registryId=d.get("registryId"), version=d.get("version"),
                entryCount=len(d.get("entries", [])), provenance=d.get("provenance"))


def valid_block(b):
    return (isinstance(b, dict) and set(b) == {"format", "registryDigest", "registryId", "version", "entryCount", "provenance"} and b["format"] == BLOCK_FORMAT
            and isinstance(b["registryDigest"], str) and bool(_HEX.match(b["registryDigest"])) and isinstance(b["registryId"], str) and type(b["version"]) is int
            and type(b["entryCount"]) is int and b["provenance"] == lots.PROVENANCE)


def _sidecar(checkpoint_path, checkpoint_bytes, authenticated_digest):
    """(state, document). The document is trusted for display only when it hashes to the digest the verified checkpoint carries."""
    path = binding_path(checkpoint_path)
    if not path.exists():
        return "ABSENT", None
    try:
        b = json.loads(path.read_text(encoding="utf-8"))
        doc = b["registryDocument"]
        ok = (b.get("format") == FORMAT and b.get("checkpointSha256") == hashlib.sha256(checkpoint_bytes).hexdigest()
              and doc.get("provenance") == lots.PROVENANCE and _digest_of(doc) == authenticated_digest)
        return ("VALID", doc) if ok else ("INVALID", None)
    except Exception:
        return "INVALID", None


def check(checkpoint_path, checkpoint_bytes, live_registry):
    """Status of the registry binding for the checkpoint the process is pinned to (decided by the digest INSIDE the checkpoint, never by the sidecar)."""
    live = dict(digest=live_registry.digest, **_meta(live_registry.document))
    base = dict(status="INVALID", live=live, bound=None, changes=[], sidecar="ABSENT", checkpointFormat=None, custodyNote=CUSTODY_NOTE, detail="")
    try:
        body = json.loads(checkpoint_bytes)["body"]
        fmt = body["format"]
    except Exception:
        return dict(base, detail="checkpoint unreadable; registry binding cannot be established")
    base["checkpointFormat"] = fmt
    if fmt != CHECKPOINT_V3:
        return dict(base, status="UNBOUND_LEGACY_FORMAT",
                    detail="this checkpoint format does not carry a registry digest inside its verified boundary; it can establish history but not current eligibility")
    block = body.get("registryBinding")
    if not valid_block(block):
        return dict(base, detail="registryBinding block malformed")
    bound = dict(digest=block["registryDigest"], registryId=block["registryId"], version=block["version"], entryCount=block["entryCount"])
    state, doc = _sidecar(checkpoint_path, checkpoint_bytes, block["registryDigest"])
    base.update(bound=bound, sidecar=state)
    if block["registryDigest"] == live_registry.digest:
        return dict(base, status="OK")
    return dict(base, status="DISCREPANCY", changes=diff(doc, live_registry.document) if doc is not None else [],
                detail="the live registry differs from the registry digest in the accepted checkpoint" + ("" if doc is not None else " (no verifiable registry document is available, so no field-level difference can be shown)"))


def prior_registry(checkpoint_path):
    """(document|None, digest|None, basis) for the registry accepted with a checkpoint, for REVIEW display only."""
    try:
        data = Path(checkpoint_path).read_bytes()
        body = json.loads(data)["body"]
    except Exception:
        return None, None, "NONE"
    if body.get("format") == CHECKPOINT_V3 and valid_block(body.get("registryBinding")):
        dg = body["registryBinding"]["registryDigest"]
        state, doc = _sidecar(checkpoint_path, data, dg)
        return doc, dg, "V3_VERIFIED_DOCUMENT" if state == "VALID" else "V3_DIGEST_ONLY"
    try:                                                                        # legacy checkpoint: the sidecar was never inside any verified boundary
        b = json.loads(binding_path(checkpoint_path).read_text(encoding="utf-8"))
        if b.get("checkpointSha256") == hashlib.sha256(data).hexdigest() and b["registryDocument"].get("provenance") == lots.PROVENANCE:
            return b["registryDocument"], _digest_of(b["registryDocument"]), "LEGACY_SIDECAR_UNVERIFIED"
    except Exception:
        pass
    return None, None, "NONE"


_FIELDS = ("part", "supplierId", "supplierName", "issuer", "effectiveFrom", "effectiveTo", "status", "rawMaterialLot")


def diff(old, new):
    """Field-level registry changes between two documents (for the person reviewing a registry update)."""
    def index(doc):
        out = {}
        for e in doc.get("entries", []):
            out.setdefault((e.get("canonical"), e.get("supplierId")), []).append(e)
        return out
    a, b = index(old), index(new)
    # a lot whose only entry changed supplier is ONE entry with a changed supplier, not a removal plus an addition
    for lot in {k[0] for k in a} & {k[0] for k in b}:
        ka, kb = [k for k in a if k[0] == lot], [k for k in b if k[0] == lot]
        if len(ka) == 1 and len(kb) == 1 and ka[0] != kb[0]:
            b[ka[0]] = b.pop(kb[0])
    out = []
    for key in sorted(set(a) | set(b), key=str):
        if key not in a:
            out.append(dict(change="ENTRY_ADDED", lot=key[0], supplierId=key[1], effectiveFrom=b[key][0].get("effectiveFrom"), aliases=b[key][0].get("aliases", [])))
        elif key not in b:
            out.append(dict(change="ENTRY_REMOVED", lot=key[0], supplierId=key[1]))
        else:
            x, y = a[key][0], b[key][0]
            for f in _FIELDS:
                if x.get(f) != y.get(f):
                    out.append(dict(change="FIELD_CHANGED", lot=key[0], supplierId=key[1], field=f, old=x.get(f), new=y.get(f)))
            for al in sorted(set(x.get("aliases", [])) - set(y.get("aliases", []))):
                out.append(dict(change="ALIAS_REMOVED", lot=key[0], alias=al))
            for al in sorted(set(y.get("aliases", [])) - set(x.get("aliases", []))):
                out.append(dict(change="ALIAS_ADDED", lot=key[0], alias=al))
            if len(a[key]) != len(b[key]):
                out.append(dict(change="DUPLICATE_DECLARATION_CHANGED", lot=key[0], supplierId=key[1]))
    # an alias that now points at a different canonical lot is an alias redirect
    def alias_map(doc):
        m = {}
        for e in doc.get("entries", []):
            for al in e.get("aliases", []):
                m.setdefault(al, set()).add(e.get("canonical"))
        return m
    am, bm = alias_map(old), alias_map(new)
    for al in sorted(set(am) & set(bm)):
        if am[al] != bm[al]:
            out.append(dict(change="ALIAS_REDIRECTED", alias=al, old=sorted(am[al]), new=sorted(bm[al])))
    for f in ("registryId", "version", "administeredBy", "provenance", "note"):
        if old.get(f) != new.get(f):
            out.append(dict(change="DOCUMENT_FIELD_CHANGED", field=f, old=old.get(f), new=new.get(f)))
    return out
