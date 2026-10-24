"""Positive lot identity for the synthetic demonstration (research candidate A+B; not promoted, not independently authenticated).

One module holds the identity semantics used by the capture commands, the snapshot/eligibility read model, the HTTP API, the UI contract and the
checkpoint decision review, so they cannot disagree.

TRUST LIMITS. The registry is LOCALLY AUTHORED SYNTHETIC reference data administered by the manufacturer. A lot that resolves in it means only
that its string, part, supplier scope and dates are declared in that file. It is not real supplier authentication, not proof of the physical
identity of any bearing, and not a custody-protected record (changing the file changes read-side results; the digest is reported but not anchored).

The `BR-###` shape is a fixture convention of this demonstration, not an industrial standard. Look-alike detection (edit distance, confusables)
only produces investigation hints for lots that do NOT resolve; it never reclassifies a lot that resolves in the registry.
"""
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "application" / "lot_registry.synthetic.json"
PROVENANCE = "LOCALLY_AUTHORED_SYNTHETIC"
TRUST_STATEMENT = ("Locally authored synthetic registry administered by the manufacturer. Registry membership does not prove the physical identity of a "
                   "bearing and is not real supplier authentication or custody.")
SENTINELS = {"UNKNOWN", "UNK", "N/A", "NA", "NONE", "NULL", "TBD", "TBC", "?", "-", "--", "UNSPECIFIED", "NOT AVAILABLE", "0", "OTHER", "MISSING"}
_ZW = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)
_DASH = dict.fromkeys(map(ord, "‐‑‒–—―−﹘﹣－"), "-")
_CONF = str.maketrans({"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2"})
OK = "REGISTERED"


class RegistryError(Exception):
    pass


def _norm(raw):
    s = unicodedata.normalize("NFKC", str(raw)).translate(_ZW).translate(_DASH).upper()
    return re.sub(r"[\s_./]+", "", s)


def _skeleton(raw):
    n = _norm(raw)
    m = re.fullmatch(r"([A-Z]+)-?([A-Z0-9]+)", n)
    return (m.group(1) + "-" + m.group(2).translate(_CONF)) if m else n


def _near(a, b):
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        d = [i for i in range(len(a)) if a[i] != b[i]]
        return len(d) == 1 or (len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]])
    s, t = (a, b) if len(a) < len(b) else (b, a)
    return any(t[:i] + t[i + 1:] == s for i in range(len(t)))


@dataclass
class Resolution:
    status: str
    canonical: str = None
    entry: dict = None
    viaAlias: bool = False
    detail: str = ""
    resembles: tuple = ()          # investigation hint only; never changes the status of a resolved lot

    @property
    def ok(self):
        return self.status == OK

    def public(self):
        out = dict(status=self.status, canonical=self.canonical, viaAlias=self.viaAlias, detail=self.detail, resembles=list(self.resembles))
        if self.entry:
            out.update(supplierId=self.entry["supplierId"], issuer=self.entry["issuer"], provenance=self.entry["provenance"])
        return out


class LotRegistry:
    def __init__(self, document):
        if not isinstance(document, dict) or not isinstance(document.get("entries"), list):
            raise RegistryError("Lot registry document is invalid")
        if document.get("provenance") != PROVENANCE:
            raise RegistryError("Registry provenance must be declared as " + PROVENANCE)
        from pramaan_integration.profile import digest
        self.document = document
        self.digest = digest(document)
        self.registryId = document.get("registryId", "")
        self.version = document.get("version")
        self.by_lot = {}        # canonical string -> [entries] (several suppliers declaring the same string is a conflict)
        self.by_alias = {}      # alias string -> [(entry)]
        for e in document["entries"]:
            for k in ("canonical", "part", "supplierId", "supplierName", "issuer", "provenance", "status", "effectiveFrom"):
                if not isinstance(e.get(k), str) or not e[k]:
                    raise RegistryError(f"Registry entry missing {k}: {e.get('canonical')!r}")
            if e["provenance"] != PROVENANCE or e["status"] not in ("ACTIVE", "WITHDRAWN"):
                raise RegistryError(f"Registry entry has unsupported provenance/status: {e['canonical']!r}")
            self.by_lot.setdefault(e["canonical"], []).append(e)
            for a in e.get("aliases", []):
                self.by_alias.setdefault(a, []).append(e)

    @classmethod
    def load(cls, path=None):
        try:
            return cls(json.loads(Path(path or DEFAULT_REGISTRY).read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            raise RegistryError(f"Lot registry unavailable: {exc}") from exc

    def meta(self):
        return dict(registryId=self.registryId, version=self.version, digest=self.digest, provenance=PROVENANCE,
                    administeredBy=self.document.get("administeredBy", ""), trustStatement=TRUST_STATEMENT, entryCount=len(self.document["entries"]))

    def _hints(self, raw):
        if not isinstance(raw, str):
            return ()
        n, sk = _norm(raw), _skeleton(raw)
        return tuple(sorted(c for c in self.by_lot if _near(n, c) or sk == _skeleton(c)))

    def resolve(self, raw, *, at=None, part=None):
        """Exact string (or exact declared alias) -> status. No normalisation is ever applied to accept a lot."""
        if not isinstance(raw, str):
            return Resolution("MALFORMED", detail="lot is not a string")
        if not raw.strip():
            return Resolution("MALFORMED", detail="empty or whitespace")
        if raw.strip().upper() in SENTINELS or _norm(raw) in SENTINELS:
            return Resolution("SENTINEL", detail="placeholder value, not a lot identity")
        if len(raw) > 80:
            return Resolution("MALFORMED", detail="too long")
        direct, aliased = self.by_lot.get(raw, []), self.by_alias.get(raw, [])
        if direct and aliased:
            return Resolution("ALIAS_CONFLICT", detail="string is both a canonical lot and an alias")
        cands = direct or aliased
        if not cands:
            return Resolution("UNREGISTERED", detail="not in the registry", resembles=self._hints(raw))
        if len({(e["canonical"], e["supplierId"]) for e in cands}) > 1:
            kinds = {e["canonical"] for e in cands}
            return Resolution("ALIAS_CONFLICT" if len(kinds) > 1 else "AMBIGUOUS_SUPPLIER_SCOPE",
                              detail="declared more than once with different " + ("canonical lots" if len(kinds) > 1 else "supplier scopes"))
        e = cands[0]
        via = bool(aliased)
        if e["status"] != "ACTIVE":
            return Resolution("WITHDRAWN", e["canonical"], e, via, "lot withdrawn in the registry")
        if part is not None and e["part"] != part:
            return Resolution("PART_MISMATCH", e["canonical"], e, via, f"registered for part {e['part']}")
        if at is not None:
            if at < e["effectiveFrom"]:
                return Resolution("NOT_YET_EFFECTIVE", e["canonical"], e, via, "before effectiveFrom")
            if e.get("effectiveTo") and at > e["effectiveTo"]:
                return Resolution("EXPIRED", e["canonical"], e, via, "after effectiveTo")
        return Resolution(OK, e["canonical"], e, via)


# ------------------------------------------------------------------ read-side evaluation over recorded events

def _occupancy(events):
    ended = {e["payload"].get("endsInstallEventId") for e in events if e["eventType"] == "COMPONENT_REMOVED"}
    corrected = {e["supersedesEventId"] for e in events if e.get("supersedesEventId")}
    return ended, corrected


def interrupted_operations(events):
    closed = {e["workOrderId"] for e in events if e["eventType"] == "WORK_ORDER_CLOSED"}
    return [dict(workOrderId=e["workOrderId"], openedEventId=e["eventId"], orderType=e["payload"].get("orderType"))
            for e in events if e["eventType"] == "WORK_ORDER_OPENED" and e["workOrderId"] not in closed]


def motor_findings(registry, events, policy, part):
    """Reasons this motor's recorded lot identities cannot support an exclusion. Pure function of recorded events, whoever captured them."""
    by_id = {e["eventId"]: e for e in events}
    ended, corrected = _occupancy(events)
    historical = bool(policy) and policy.get("exposureBasis") == "HISTORICAL_OPERATION"
    out = []

    def add(e, lot, source, res, **extra):
        out.append(dict(eventId=e["eventId"], slot=e["payload"].get("slot"), lot=lot, source=source, reason=res if isinstance(res, str) else res.status,
                        detail="" if isinstance(res, str) else res.detail, resembles=[] if isinstance(res, str) else list(res.resembles), **extra))

    for e in events:
        p, kind = e["payload"], e["eventType"]
        if kind == "COMPONENT_INSTALLED":
            current = e["eventId"] not in ended and e["eventId"] not in corrected
            if not (current or historical):
                continue
            r = registry.resolve(p.get("lot"), at=e["occurredAt"], part=part)
            if not r.ok:
                add(e, p.get("lot"), "INSTALL", r)
            elif r.viaAlias or p.get("lot") != r.canonical:
                add(e, p.get("lot"), "INSTALL", "ALIAS_NOT_CANONICALISED")     # the evaluator compares the literal string
            made = by_id.get(p.get("manufacturingEventId"))
            if made is None:
                add(e, p.get("lot"), "INSTALL", "MANUFACTURING_RECORD_MISSING")
            else:
                mp = made["payload"]
                if mp.get("lot") != p.get("lot"):
                    add(e, p.get("lot"), "INSTALL", "MANUFACTURED_LOT_CONTRADICTS_INSTALL")
                elif r.ok and mp.get("supplierId") != r.entry["supplierId"]:
                    add(e, p.get("lot"), "INSTALL", "SUPPLIER_SCOPE_MISMATCH", recordedSupplier=mp.get("supplierId"), registrySupplier=r.entry["supplierId"])
        elif kind == "SLOT_STATE_VERIFIED":
            r = registry.resolve(p.get("observedLot"), at=e["occurredAt"], part=part)
            if not r.ok or p.get("observedLot") != r.canonical:
                add(e, p.get("observedLot"), "OBSERVATION", r if not r.ok else "ALIAS_NOT_CANONICALISED")
        elif kind == "COMPONENT_REMOVED" and historical:
            r = registry.resolve(p.get("observedLot"), at=e["occurredAt"], part=part)
            if not r.ok or p.get("observedLot") != r.canonical:
                add(e, p.get("observedLot"), "REMOVAL", r if not r.ok else "ALIAS_NOT_CANONICALISED")
    for op in interrupted_operations(events):
        out.append(dict(eventId=op["openedEventId"], slot=None, lot=None, source="OPERATION", reason="OPERATION_INTERRUPTED",
                        detail=f"work order {op['workOrderId']} was opened and never closed; manual reconciliation required", resembles=[]))
    return out


def policy_findings(registry, policy, part):
    """The recall itself must name registered, canonical lots; otherwise no exclusion anywhere can be trusted."""
    out = []
    for lot in (policy or {}).get("affectedLots", []):
        r = registry.resolve(lot, part=part)
        if not r.ok or r.canonical != lot:
            out.append(dict(eventId=None, slot=None, lot=lot, source="RECALL_POLICY", reason=r.status if not r.ok else "ALIAS_NOT_CANONICALISED", detail=r.detail, resembles=list(r.resembles)))
    return out


def guard_decision(current, findings):
    """Return (guarded copy of one decision, guard block). The evaluator's own fields stay untouched under their own names."""
    guarded = dict(current)
    established = not findings
    block = dict(status="IDENTITY_ESTABLISHED_LOCAL_REGISTRY" if established else "IDENTITY_NOT_ESTABLISHED", findings=findings,
                 evaluatorOperationalAction=current.get("operationalAction"), evaluatorEvidenceFinding=current.get("evidenceFinding"))
    guarded["evaluatorOperationalAction"] = current.get("operationalAction")
    if not established and current.get("operationalAction") == "RELEASE_ELIGIBLE":
        guarded["operationalAction"] = "RECALL_HOLD"
        block["guardChangedAction"] = True
    else:
        block["guardChangedAction"] = False
    guarded["identityGuard"] = block
    return guarded
