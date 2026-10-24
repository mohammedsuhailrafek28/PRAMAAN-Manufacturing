"""Checkpoint-bound lot-registry snapshots (candidate; no change to the anchor/checkpoint format).

A checkpoint file is exported and published with a sidecar `<checkpoint>.registry-binding.json` holding the exact registry document that was in force when the
checkpoint candidate was exported, the registry digest, and the sha256 of the checkpoint bytes it belongs to. At read time current release eligibility requires
that (a) the sidecar exists, (b) it matches the checkpoint bytes, (c) its registry document matches its own digest and declared provenance, and (d) the LIVE
registry has the same digest. Any other state is a discrepancy and prevents current release eligibility (fail closed). Decisions and the evaluator's reports are
unchanged; the discrepancy is reported with a field-level difference so a person can review it and, if valid, propose and accept a new checkpoint.

CUSTODY LIMIT. The checkpoint, the sidecar and the live registry are files on the same host. This detects silent, accidental or unreviewed drift between what a
person accepted and what the application now reads. It is NOT independent verification: someone who controls the host controls all three files. Not
authentication, not proof of physical lot identity.
"""
import hashlib
import json
import os
import tempfile
from pathlib import Path

from . import lot_identity as lots

SUFFIX = ".registry-binding.json"
FORMAT = "PRAMAAN_REGISTRY_BINDING_RESEARCH_V1"
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


def check(checkpoint_path, checkpoint_bytes, live_registry):
    """Status of the registry binding for the checkpoint the process is pinned to."""
    live = dict(digest=live_registry.digest, **_meta(live_registry.document))
    path = binding_path(checkpoint_path)
    base = dict(status="MISSING", live=live, bound=None, changes=[], custodyNote=CUSTODY_NOTE)
    if not path.exists():
        return dict(base, detail="no registry binding exists for this checkpoint; current eligibility cannot be proven")
    try:
        b = json.loads(path.read_text(encoding="utf-8"))
        doc = b["registryDocument"]
        bound = dict(digest=b["registryDigest"], **_meta(doc))
        if b.get("format") != FORMAT or b.get("checkpointSha256") != hashlib.sha256(checkpoint_bytes).hexdigest():
            return dict(base, status="INVALID", bound=bound, detail="binding does not belong to these checkpoint bytes")
        if _digest_of(doc) != b["registryDigest"] or doc.get("provenance") != lots.PROVENANCE:
            return dict(base, status="INVALID", bound=bound, detail="bound registry snapshot does not match its digest or provenance")
    except Exception as exc:                                     # unreadable, malformed, or an invalid registry document
        return dict(base, status="INVALID", detail=f"binding unreadable: {type(exc).__name__}")
    if b["registryDigest"] != live_registry.digest:
        return dict(base, status="DISCREPANCY", bound=bound, changes=diff(doc, live_registry.document),
                    detail="the live registry differs from the registry accepted with this checkpoint")
    return dict(base, status="OK", bound=bound, detail="")


def bound_document(checkpoint_path):
    try:
        return json.loads(binding_path(checkpoint_path).read_text(encoding="utf-8"))["registryDocument"]
    except Exception:
        return None


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
