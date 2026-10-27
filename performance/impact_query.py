"""Conservative lot impact over verified ledger facts, NOT a recall/clearance endpoint.

Hybrid proof. Every query first recomputes the complete SQLite image proof (serialize() + SHA-256 over every byte of the transaction snapshot, bound to the lot
registry) and compares it to the verified one; nothing about that proof is weakened or skipped. Only when the image proof differs does the reader compute the
complete evidence-content generation: a digest over every byte the projection can read (evidence_scope.SCOPE). If the generation is unchanged the difference was
in bytes the projection cannot read (header counters, application clock, audit, decision runs...), so the verified projection is reused and the image proof is
re-anchored. If the generation changed the reader fails closed until an explicit verified rebuild. A rebuild re-verifies only motors whose own content digest (or
the registry) changed, and verifies each motor once.

No disk cache, no mutation hooks, no trust promotion, no evaluator fork, no lease, no worker processes. The caller must keep using the ordinary
checkpoint/evaluation/shipment paths for decisions and authorization.

Memory-mapped reads (connection-local PRAGMA mmap_size) only change the read I/O path of SQLite; see docs/PS10_IMPACT_HYBRID.md for their failure characteristics.
"""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import threading
from contextlib import contextmanager

from application.service import PART
from application import lot_identity as lots
from pramaan_integration import Ledger, LedgerBlocked
from pramaan_integration import ledger as _ledger_module
from pramaan_integration import profile as _profile_module
from pramaan_integration.profile import digest

from . import evidence_scope as scope

ROOT = Path(__file__).resolve().parents[1]
MMAP_BYTES = 1073741824            # connection-local maximum, not an allocation


class ImpactUnavailable(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


_PINS_OK = False


def check_pins():
    """The reader reuses the unchanged Ledger verifier; refuse to run against any ledger/profile that is not a reviewed, pinned file."""
    global _PINS_OK
    if _PINS_OK:
        return
    try:
        pins = json.loads((ROOT / "application/source-provenance.json").read_text(encoding="utf-8"))["files"]
        for module in (_ledger_module, _profile_module):
            path = Path(module.__file__).resolve()
            if pins.get(path.relative_to(ROOT).as_posix()) != hashlib.sha256(path.read_bytes()).hexdigest():
                raise ValueError(path.name)
    except (OSError, ValueError, KeyError):
        raise ImpactUnavailable("READER_PIN_MISMATCH") from None
    _PINS_OK = True


class ReadOnlyLedger(Ledger):
    """The unchanged verifier methods bound to an existing read-only connection: no constructor DDL, no writes, no construction shortcuts."""
    def __init__(self, db):
        self.db = db


def open_readonly(database):
    db = sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def _gaps(config):
    # Over-approximation, never a replacement for evaluator coverage rules.
    mandatory = {s for m in config["coverage"]["mandatoryCapture"] for s in m["sources"]}
    for source in mandatory:
        spans = sorted((s["from"], s["to"]) for s in config["sessions"]
                       if s["sourceId"] == source and s["authenticated"] is True)
        if not spans:
            return True
        end = spans[0][1]
        for start, stop in spans[1:]:
            if start > end:
                return True
            end = max(end, stop)
    return False


def verify_motor(db, ledger, registry, motor):
    """Full verification of one motor with the unchanged Ledger.snapshot, then the conservative projection facts. Pure function of the motor's digested bytes."""
    row = db.execute("SELECT config,hash FROM motors WHERE serial=?", (motor,)).fetchone()
    if not row:
        raise LedgerBlocked("Motor not provisioned")
    config = json.loads(row["config"])
    if digest(config) != row["hash"]:
        raise LedgerBlocked("Provisioned configuration changed")
    wm = {s: 0 for s in config["sources"]}
    for source, highest in db.execute("SELECT source,max(seq) FROM events WHERE motor=? GROUP BY source", (motor,)).fetchall():
        if source not in wm:
            raise LedgerBlocked("Event from an unprovisioned source")
        wm[source] = highest
    stored = db.execute("SELECT count(*) FROM events WHERE motor=?", (motor,)).fetchone()[0]
    case, manifest = ledger.snapshot(motor, wm)       # blocked-motor check, original documents, decoding, hash chain, prefix completeness, references
    if len(manifest["evidence"]) != stored:
        raise LedgerBlocked("Snapshot does not cover every stored event")
    hashes = frozenset(e["hash"] for e in manifest["evidence"])
    events = case["events"]
    by_id = {x["eventId"]: x for x in manifest["evidence"]}

    def ref(e):
        return dict(by_id[e["eventId"]], sourceId=e["sourceId"], sourceSeq=e["sourceSeq"],
                    occurredAt=e["occurredAt"], producerRecordedAt=e["recordedAt"],
                    slot=e["payload"].get("slot"), eventType=e["eventType"])
    references, ships = {}, []
    for e in events:
        kind, p = e["eventType"], e["payload"]
        if kind in ("COMPONENT_INSTALLED", "COMPONENT_REMOVED", "SLOT_STATE_VERIFIED"):
            value = p.get("lot") if kind == "COMPONENT_INSTALLED" else p.get("observedLot")
            if isinstance(value, str):
                resolved = registry.resolve(value, part=PART)
                for token in {value, resolved.canonical if resolved.ok else value}:
                    references.setdefault(token, []).append(ref(e))
        if kind == "MOTOR_SHIPPED":
            ships.append(dict(shipmentId=p["shipmentId"], shippedAt=e["occurredAt"],
                              evidence=ref(e), recordedClaimOnly=True, releaseAuthorization=False))
    reasons = []
    # Keep every observation, even one the current evaluator might resolve;
    # this is intentionally broader than recall eligibility, not a new hold.
    sightings = [ref(e) for e in events if e["eventType"] == "SLOT_STATE_VERIFIED"]
    if sightings:
        reasons.append("OBSERVATION_REQUIRES_EVALUATION")
    if _gaps(config):
        reasons.append("CAPTURE_COVERAGE_UNCERTAINTY")
    if lots.interrupted_operations(events):
        reasons.append("INTERRUPTED_OPERATION")
    if lots.motor_findings(registry, events, {"exposureBasis": "HISTORICAL_OPERATION"}, PART):
        reasons.append("IDENTITY_OR_PROVENANCE_UNCERTAINTY")
    ended = {e["payload"].get("endsInstallEventId") for e in events if e["eventType"] == "COMPONENT_REMOVED"}
    corrected = {e.get("supersedesEventId") for e in events}
    for slot in ("DE", "NDE"):
        active = [e for e in events if e["eventType"] == "COMPONENT_INSTALLED" and e["payload"]["slot"] == slot and e["eventId"] not in ended | corrected]
        if len(active) != 1:
            reasons.append("SLOT_STATE_UNCERTAINTY")
            break
    if any(e["eventType"] == "CAPTURE_EXCEPTION_RAISED" for e in events):
        reasons.append("CAPTURE_EXCEPTION_REQUIRES_EVALUATION")
    return dict(row=dict(motorSerial=motor, watermark=wm, evidenceSnapshotDigest=manifest["evidenceSnapshotDigest"],
                         shipments=ships, shipmentCoverage="RECORDED_CLAIMS" if ships else "NO_RECORDED_SHIPMENT",
                         uncertaintyReasons=reasons, observationEvidence=sightings),
                references=references, uncertain=bool(reasons),
                accepted=(manifest["configurationDigest"], hashes), events=len(events))


class ImpactQuery:
    """One long-lived, read-only reader. query() never silently refreshes changed input."""

    def __init__(self, database, *, registry=None):
        check_pins()
        self._database = database
        self._registry_path = registry
        self._lock = threading.RLock()
        self.db = self._connect()
        self._ledger = ReadOnlyLedger(self.db)
        self._key = None              # complete SQLite image proof of the verified state (None: nothing verified / invalidated)
        self._gen = None              # complete evidence-content generation of the verified state
        self._index = {}
        self._uncertain = {}
        self._rows = {}
        self._total = 0
        self._event_count = 0
        self._image_bytes = 0
        self._accepted = {}
        self._memo = {}               # motor -> (registry digest, motor digest, verified facts); in memory only
        self._json_cache = {}
        self.last_rebuild = {}
        self.stats = dict(imageProofMatches=0, reAnchors=0, rejections=0)

    def _connect(self):
        try:
            db = open_readonly(self._database)
        except (sqlite3.Error, OSError, ValueError):
            raise ImpactUnavailable("SOURCE_UNAVAILABLE") from None
        # SQLite owns page/WAL visibility. This only changes its read I/O path; serialize() and SHA-256 still consume the entire transaction snapshot.
        # Unsupported platforms may cap this to zero, retaining the slower path.
        self._mmap_bytes = db.execute(f"PRAGMA mmap_size={MMAP_BYTES}").fetchone()[0]
        return db

    def close(self):
        """Close the connection and its memory map. Close (or use maintenance()) before VACUUM, truncation or replacement of the database file."""
        with self._lock:
            self._key = self._gen = None
            self.db.close()

    @contextmanager
    def maintenance(self):
        """Release the connection and memory map while the caller vacuums, truncates or replaces the database file. The verified state is kept but not trusted:
        the next query recomputes the image proof, and either re-anchors (evidence bytes unchanged) or fails closed."""
        with self._lock:
            self.db.close()
            try:
                yield
            finally:
                try:
                    self.db = self._connect()
                except ImpactUnavailable:
                    self._key = self._gen = None
                    raise
                self._ledger = ReadOnlyLedger(self.db)

    @property
    def generation(self):
        return self._gen

    @contextmanager
    def _snapshot(self):
        with self._lock:
            try:
                self.db.execute("BEGIN")
                yield
            except ImpactUnavailable:
                raise
            except Exception:
                self._key = self._gen = None
                raise ImpactUnavailable("INPUT_VERIFICATION_FAILED") from None
            finally:
                try:
                    self.db.rollback()
                except sqlite3.Error:
                    pass

    def _content_key(self, registry):
        # Force a SQLite read snapshot before serialization. serialize() includes
        # WAL-visible pages from THIS transaction, not just the main database file.
        # The full image binds all tables/indexes/schema, captures and derived rows.
        # No head/count/mtime/data_version shortcut; unchanged bytes reuse the proof.
        self.db.execute("SELECT rootpage FROM sqlite_schema LIMIT 1").fetchone()
        image = self.db.serialize()
        self._image_bytes = len(image)
        h = hashlib.sha256(b"PRAMAAN_IMPACT_DATABASE_IMAGE_V1")
        registry_bytes = registry.digest.encode("ascii")
        h.update(struct.pack(">Q", len(registry_bytes))); h.update(registry_bytes)
        h.update(struct.pack(">Q", len(image))); h.update(image)
        return h.hexdigest()

    def _generation(self, registry):
        """Complete evidence-content generation, inside the caller's read transaction (the snapshot the image proof was taken from)."""
        self._state = scope.fleet_state(self.db, registry.digest)
        return self._state.fleet

    def rebuild(self):
        """Verify the fleet and publish an index atomically, with no partial success. Reuses a motor's verification only under an equal content digest."""
        # A failed rebuild invalidates the old in-memory proof, even on identical later input.
        with self._lock:
            self._key = self._gen = None
            with self._snapshot():
                registry = lots.LotRegistry.load(self._registry_path)
                image = self._content_key(registry)
                generation = self._generation(registry)
                state = self._state
                motors = list(state.motors)
                if motors != state.units:
                    raise ImpactUnavailable("FLEET_MEMBERSHIP_MISMATCH")
                if not set(self._accepted) <= set(motors):
                    raise ImpactUnavailable("ROLLBACK_DETECTED")
                reuse = {m: self._memo[m][2] for m in motors
                         if m in self._memo and self._memo[m][:2] == (registry.digest, state.motors[m])}
                todo = [m for m in motors if m not in reuse]
                fresh = {m: verify_motor(self.db, self._ledger, registry, m) for m in todo}
                rows, index, uncertain, accepted, memo = {}, {}, {}, {}, {}
                event_count = 0
                for motor in motors:
                    facts = reuse[motor] if motor in reuse else fresh[motor]
                    prior = self._accepted.get(motor)
                    configuration, hashes = facts["accepted"]
                    if prior and (prior[0] != configuration or not prior[1] <= hashes):
                        raise ImpactUnavailable("ROLLBACK_OR_CONFIGURATION_REWRITE")
                    accepted[motor] = facts["accepted"]
                    memo[motor] = (registry.digest, state.motors[motor], facts)
                    rows[motor] = facts["row"]
                    event_count += facts["events"]
                    if facts["uncertain"]:
                        uncertain[motor] = True
                    for token, refs in facts["references"].items():
                        index.setdefault(token, {})[motor] = refs
                # Publish only after every motor verified in this transaction.
                self._rows, self._index, self._uncertain = rows, index, uncertain
                self._accepted, self._memo, self._json_cache = accepted, memo, {}
                self._total, self._event_count, self._key, self._gen = len(motors), event_count, image, generation
                self.last_rebuild = dict(motorsVerified=len(todo), motorsReused=len(reuse))
                return dict(motors=len(motors), events=event_count, contentDigest=image, evidenceGeneration=generation,
                            databaseImageBytes=self._image_bytes, sqliteMmapLimitBytes=self._mmap_bytes,
                            evidenceBytes=state.evidence_bytes, **self.last_rebuild)

    def _checked(self, lot):
        if not isinstance(lot, str) or not lot.strip() or len(lot) > 80 or any(ord(c) < 32 for c in lot):
            raise ImpactUnavailable("INVALID_LOT_QUERY")
        if self._key is None:
            raise ImpactUnavailable("VERIFIED_INDEX_REQUIRED")
        registry = lots.LotRegistry.load(self._registry_path)
        image = self._content_key(registry)                      # the full-image proof, on every query
        if image == self._key:
            self.stats["imageProofMatches"] += 1
        else:
            # The image differs. Is that because evidence changed, or only bytes the projection cannot read? Decide by the complete content generation,
            # computed in this same transaction snapshot.
            if self._generation(registry) != self._gen:
                self._key = self._gen = None
                self.stats["rejections"] += 1
                raise ImpactUnavailable("EVIDENCE_CHANGED_REBUILD_REQUIRED")
            self._key = image                                    # same evidence, same projection: re-anchor the image proof
            self._json_cache = {}                                # payloads embed the image proof
            self.stats["reAnchors"] += 1
        return registry, self._key

    def _project(self, lot, registry, key):
        resolved = registry.resolve(lot, part=PART)
        tokens = {lot, resolved.canonical} if resolved.ok else {lot}
        matched = {}
        for token in sorted(tokens):
            for motor, refs in self._index.get(token, {}).items():
                matched.setdefault(motor, {}).update({r["eventId"]: r for r in refs})
        # Unknown lot identity cannot establish a negative candidate set.
        candidates = set(self._rows) if not resolved.ok else set(matched) | set(self._uncertain)
        result = []
        for motor in sorted(candidates):
            row = copy.deepcopy(self._rows[motor])
            row["matchingEvidence"] = list(matched.get(motor, {}).values())
            if not resolved.ok:
                row["uncertaintyReasons"].append("QUERY_LOT_IDENTITY_UNESTABLISHED")
            result.append(row)
        return dict(kind="CONSERVATIVE_LEDGER_IMPACT_NOT_A_RECALL_DECISION", lot=lot,
                    canonicalLot=resolved.canonical if resolved.ok else None, contentDigest=key, evidenceGeneration=self._gen,
                    integrity="FULL_IMAGE_PROOF_EVERY_REQUEST_EVIDENCE_GENERATION_ON_MISMATCH", asOf="SQLITE_TRANSACTION_SNAPSHOT",
                    checkpoint="NOT_ASSESSED", operationalClearance="NOT_ASSESSED",
                    notListedMeans="NO_DIRECT_MATCH_OR_INDEXED_UNCERTAINTY; NOT CLEARED",
                    totalMotors=self._total, eventCount=self._event_count, motors=result,
                    limitations=["No physical identity or independently protected checkpoint authentication",
                                 "All slots and historical evidence retained; conservative false positives expected",
                                 "Use existing evaluator/checkpoint/shipment gate for operational decisions"])

    def query(self, lot):
        with self._snapshot():
            registry, key = self._checked(lot)
            return self._project(lot, registry, key)

    def query_json(self, lot):
        """Ready-to-send immutable JSON; the full image proof is recomputed on EVERY call.

        At most eight payloads retained, dropped at every rebuild and every re-anchor. This is never a disk/freshness/decision cache.
        The first query for a new lot pays projection/encoding cost explicitly.
        """
        with self._snapshot():
            registry, key = self._checked(lot)
            if lot not in self._json_cache:
                encoded = json.dumps(self._project(lot, registry, key), separators=(",", ":")).encode("utf8")
                if len(self._json_cache) >= 8:
                    del self._json_cache[next(iter(self._json_cache))]
                self._json_cache[lot] = encoded
            return self._json_cache[lot]
