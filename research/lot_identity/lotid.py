"""Research prototype (NOT part of the demo application, NOT promoted): positive lot-identity contract and two bounded correction strategies.

Nothing in the frozen application or the pinned v3 evaluator is edited. The candidates subclass application.service.Manufacturing
(application/bridge layer) and are used only by the tests and scripts in this directory.

Trust limits: every registry here is LOCALLY AUTHORED SYNTHETIC reference data. Membership proves only that a string appears in a
file this repository's operator wrote; it is not independently authenticated supplier evidence and not proof of physical lot identity.
"""
import copy
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "integration"))
from application.service import Manufacturing, PART  # noqa: E402
from pramaan_integration import ValidationFailure  # noqa: E402

CANONICAL = re.compile(r"[A-Z]{2}-[0-9]{3}")          # synthetic lot syntax; configurable, owner decision
SENTINELS = {"UNKNOWN", "UNK", "N/A", "NA", "NONE", "NULL", "TBD", "TBC", "?", "-", "--", "UNSPECIFIED", "NOT AVAILABLE", "0", "OTHER"}
ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)
DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−﹘﹣－"), "-")
CONFUSABLE = str.maketrans({"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2"})


def normalize(raw):
    """Aggressive comparison key (never used to accept a lot, only to detect look-alikes)."""
    s = unicodedata.normalize("NFKC", str(raw)).translate(ZERO_WIDTH).translate(DASHES).upper()
    return re.sub(r"[\s_./]+", "", s)


def skeleton(raw):
    n = normalize(raw)
    m = re.fullmatch(r"([A-Z]+)-?([A-Z0-9]+)", n)
    return (m.group(1) + "-" + m.group(2).translate(CONFUSABLE)) if m else n


def damerau1(a, b):
    """True when a and b differ by at most one insertion, deletion, substitution or adjacent transposition."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        d = [i for i in range(len(a)) if a[i] != b[i]]
        return len(d) == 1 or (len(d) == 2 and d[1] == d[0] + 1 and a[d[0]] == b[d[1]] and a[d[1]] == b[d[0]])
    s, t = (a, b) if len(a) < len(b) else (b, a)
    return any(t[:i] + t[i + 1:] == s for i in range(len(t)))


def lexical_problem(raw):
    """Reason a lot string cannot be an identity at all, or None. Pure syntax; no registry."""
    if not isinstance(raw, str):
        return "NOT_A_STRING"
    if not raw.strip():
        return "EMPTY_OR_WHITESPACE"
    if raw.strip().upper() in SENTINELS or normalize(raw) in SENTINELS:
        return "SENTINEL"
    if not CANONICAL.fullmatch(raw):
        return "NOT_CANONICAL_FORM"
    return None


@dataclass
class LotEntry:
    canonical: str
    issuer: str                      # who asserts the lot exists (local registry owner here)
    supplierId: str
    supplierName: str
    part: str = PART
    aliases: tuple = ()
    effectiveFrom: str = "2026-01-01T00:00:00Z"
    effectiveTo: str = None
    provenance: str = "LOCALLY_AUTHORED_SYNTHETIC"   # NOT independently authenticated supplier evidence
    state: str = "REGISTERED"                         # REGISTERED | WITHDRAWN


@dataclass
class Resolution:
    status: str        # REGISTERED | UNREGISTERED | SENTINEL | MALFORMED | NEAR_MISS | ALIAS_CONFLICT | OUT_OF_WINDOW | WITHDRAWN
    canonical: str = None
    detail: str = ""
    entry: LotEntry = None


class LotRegistry:
    def __init__(self, entries):
        self.entries = {e.canonical: e for e in entries}
        self.alias = {}
        self.conflicts = set()
        for e in entries:
            for a in e.aliases:
                if a in self.alias and self.alias[a] != e.canonical or a in self.entries:
                    self.conflicts.add(a)
                self.alias[a] = e.canonical

    def resolve(self, raw, at="2026-10-10T08:00:00Z", part=PART):
        problem = lexical_problem(raw) if not (isinstance(raw, str) and raw in self.alias) else None
        if problem in ("NOT_A_STRING", "EMPTY_OR_WHITESPACE"):
            return Resolution("MALFORMED", detail=problem)
        if problem == "SENTINEL":
            return Resolution("SENTINEL", detail=problem)
        if raw in self.conflicts:
            return Resolution("ALIAS_CONFLICT", detail=f"alias {raw!r} is declared more than once or collides with a canonical lot")
        key = self.alias.get(raw, raw)
        e = self.entries.get(key)
        if e is None:
            near = [c for c in self.entries if damerau1(normalize(raw), c) or skeleton(raw) == skeleton(c)]
            if near:
                return Resolution("NEAR_MISS", detail=f"resembles registered lot {near}")
            return Resolution("MALFORMED" if problem else "UNREGISTERED", detail=problem or "not in registry")
        if e.state != "REGISTERED":
            return Resolution("WITHDRAWN", e.canonical, entry=e)
        if e.part != part or not (e.effectiveFrom <= at and (e.effectiveTo is None or at <= e.effectiveTo)):
            return Resolution("OUT_OF_WINDOW", e.canonical, entry=e)
        return Resolution("REGISTERED", e.canonical, entry=e)


def demo_registry():
    return LotRegistry([
        LotEntry("BR-204", "LOCAL-MFG-REGISTRY", "SUP-NSB-01", "Northstar Bearings — synthetic supplier", aliases=("NSB-204",)),
        LotEntry("BR-310", "LOCAL-MFG-REGISTRY", "SUP-KAV-02", "Kaveri Precision — synthetic supplier"),
        LotEntry("BR-312", "LOCAL-MFG-REGISTRY", "SUP-KAV-02", "Kaveri Precision — synthetic supplier"),
        LotEntry("BR-401", "LOCAL-MFG-REGISTRY", "SUP-NSB-01", "Northstar Bearings — synthetic supplier"),
        LotEntry("BR-555", "LOCAL-MFG-REGISTRY", "SUP-KAV-02", "Kaveri Precision — synthetic supplier", effectiveFrom="2027-01-01T00:00:00Z"),
        LotEntry("BR-666", "LOCAL-MFG-REGISTRY", "SUP-KAV-02", "Kaveri Precision — synthetic supplier", state="WITHDRAWN"),
    ])


def conflicting_registry():
    return LotRegistry([
        LotEntry("BR-204", "LOCAL-MFG-REGISTRY", "SUP-NSB-01", "Northstar", aliases=("ALIAS-1",)),
        LotEntry("BR-310", "LOCAL-MFG-REGISTRY", "SUP-KAV-02", "Kaveri", aliases=("ALIAS-1",)),
    ])


# ---------------------------------------------------------------- read-side identity safeguard (strategy B)

def identity_findings(snap, recalled):
    """Per motor: reasons its lot identities cannot establish release. Reads a snapshot only."""
    keys = [skeleton(r) for r in recalled]
    out = {}

    def judge(lot):
        p = lexical_problem(lot)
        if p:
            return p
        if lot not in recalled and any(skeleton(lot) == k or damerau1(normalize(lot), normalize(r)) for k, r in zip(keys, recalled)):
            return "NEAR_MISS_OF_RECALLED_LOT"
        return None

    for c in snap["components"]:
        if c["removedAt"] or c["supersededBy"]:
            continue
        p = judge(c["lot"])
        if p:
            out.setdefault(c["unitId"], []).append(dict(slot=c["slot"], lot=c["lot"], source="INSTALL", eventId=c["componentId"], reason=p))
    for u in snap["units"]:
        for e in u["events"]:
            if e["eventType"] == "SLOT_STATE_VERIFIED":
                p = judge(e["payload"].get("observedLot"))
                if p:
                    out.setdefault(u["unitId"], []).append(dict(slot=e["payload"].get("slot"), lot=e["payload"].get("observedLot"), source="OBSERVATION", eventId=e["eventId"], reason=p))
    return out


def apply_guard(snap, recalled, registry=None):
    snap = copy.deepcopy(snap)
    findings = identity_findings(snap, recalled)
    if registry is not None:
        for c in snap["components"]:
            if not (c["removedAt"] or c["supersededBy"]) and registry.resolve(c["lot"]).status != "REGISTERED":
                findings.setdefault(c["unitId"], []).append(dict(slot=c["slot"], lot=c["lot"], source="INSTALL", eventId=c["componentId"], reason="NOT_IN_REGISTRY_OR_NOT_EFFECTIVE"))
    snap["identityGuard"] = dict(version="LOT_IDENTITY_GUARD_RESEARCH_V1", trust="LOCAL_SYNTHETIC_RULES_NOT_PROOF_OF_PHYSICAL_IDENTITY", motors=findings)
    for motor, items in findings.items():
        if motor in snap["eligibility"]:
            snap["eligibility"][motor]["currentReleaseEligible"] = False
            snap["eligibility"][motor]["identityGuard"] = "LOT_IDENTITY_NOT_ESTABLISHED"
        for v in snap["decisions"].get(motor, {}).values():
            cur = v["current"]
            if cur.get("operationalAction") == "RELEASE_ELIGIBLE":
                cur["operationalAction"] = "RECALL_HOLD"
                cur["identityGuardOverride"] = dict(from_="RELEASE_ELIGIBLE", reason="LOT_IDENTITY_NOT_ESTABLISHED", evidenceEventIds=[i["eventId"] for i in items])
    return snap


# ---------------------------------------------------------------- strategies

class _Strict(Manufacturing):
    """Shared: validate every lot argument BEFORE the first manufacturing event is written."""
    registry = None

    def _now(self):
        return self.db.execute("SELECT at FROM app_clock WHERE id=1").fetchone()[0]

    def _check_lot(self, raw, what):
        raise NotImplementedError

    def assemble(self, motor, de_lot, nde_lot, identity="SERIAL"):
        de, nde = self._check_lot(de_lot, "DE lot"), self._check_lot(nde_lot, "NDE lot")
        return super().assemble(motor, de, nde, identity)

    def replace(self, motor, lot):
        return super().replace(motor, self._check_lot(lot, "replacement lot"))

    def observe(self, motor, lot):
        return super().observe(motor, self._check_lot(lot, "observed lot"))

    def announce(self, affected_lot, affected_slots=None):
        return super().announce(self._check_lot(affected_lot, "recalled lot"), affected_slots)


class StrategyA(_Strict):
    """A: strict capture validation + positive registry membership (write-side only)."""

    def __init__(self, path, registry=None, **kw):
        super().__init__(path, **kw)
        self.registry = registry or demo_registry()

    def _check_lot(self, raw, what):
        r = self.registry.resolve(raw, self._now())
        if r.status != "REGISTERED":
            raise ValidationFailure(f"{what}: lot identity not established ({r.status}{': ' + r.detail if r.detail else ''})")
        return r.canonical

    def manufacture(self, motor, lot, serial=None):
        e = self.registry.entries[lot]      # supplier provenance comes from the registry, not from a hard-coded lot name
        allocated = self.event(motor, "MATERIAL_ALLOCATED", "MATERIAL", dict(rawMaterialLot=f"STEEL-{lot}", supplierId=e.supplierId, supplierName=e.supplierName))
        return self.event(motor, "BEARING_MANUFACTURED", "MATERIAL", dict(
            rawMaterialLot=allocated["payload"]["rawMaterialLot"], supplierId=e.supplierId, part=PART, lot=lot, serial=serial, materialEventId=allocated["eventId"]))


class StrategyB(_Strict):
    """B: capture validation (syntax, sentinels, atomic) + fail-closed bridge safeguard in the read model. No registry."""

    def _check_lot(self, raw, what):
        p = lexical_problem(raw)
        if p:
            raise ValidationFailure(f"{what}: lot identity not established ({p})")
        return raw

    def snapshot(self, *, trusted_anchor=None):
        snap = super().snapshot(trusted_anchor=trusted_anchor)
        return apply_guard(snap, snap["recall"]["affectedLots"])
