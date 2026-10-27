"""Evidence scope and content digests for the impact projection.

The projection reads exactly the tables and columns listed in SCOPE (plus the lot registry). Everything the projection can depend on is hashed here, every
byte, in canonical order, with a type tag and an 8-byte length prefix per field. Bytes that cannot influence a result (database header, free pages, application
clock, audit, decision runs, recall announcements, ship tickets) are NOT hashed, so writing them does not invalidate a verified projection.

motor_digest(m) binds one motor's provisioning row, event rows (including ordinal, so reordering is visible), a digest of every capture those events reference
(row key, raw bytes and received time), and its rejection rows. Verifying a motor is a pure function of exactly those bytes plus the pinned code, so a
verification result may be reused under an equal digest. fleet_state() binds every motor digest, fleet membership, the schema of the evidence tables (including
their append-only triggers), evidence rows that belong to no registered motor, captures no event references, and the lot registry digest.

fleet_state() reads each table once in a streaming pass; motor_digest() (used by worker processes for one motor) computes the identical value with point lookups.
"""
import hashlib
import itertools
from operator import itemgetter
import struct

MOTOR_DOMAIN = b"PRAMAAN_IMPACT_MOTOR_EVIDENCE_V2"
FLEET_DOMAIN = b"PRAMAAN_IMPACT_FLEET_GENERATION_V2"
CAPTURE_DOMAIN = b"PRAMAAN_IMPACT_CAPTURE_V2"

SCOPE = {
    "motors": ("serial", "config", "hash"),
    "events": ("ordinal", "id", "motor", "source", "seq", "native", "epcis", "capture", "previous", "hash"),
    "captures": ("hash", "raw", "received"),
    "rejections": ("ordinal", "motor", "raw_hash", "reason", "received"),
    "app_units": ("serial", "title"),
}
SCHEMA_TABLES = tuple(SCOPE)
_EV_MOTOR, _EV_CAPTURE = SCOPE["events"].index("motor"), SCOPE["events"].index("capture")
_COLS = {table: ", ".join(columns) for table, columns in SCOPE.items()}
_LEN = struct.Struct(">Q").pack
_INT = struct.Struct(">q").pack


def encode(value):
    """Typed, length-prefixed field; no two different field sequences produce the same byte stream."""
    kind = type(value)
    if kind is str:
        data = value.encode("utf-8", "surrogatepass")
        return b"T" + _LEN(len(data)) + data
    if kind is bytes:
        return b"B" + _LEN(len(value)) + value
    if kind is int:
        return b"I" + _INT(value)
    if value is None:
        return b"N"
    raise TypeError("unexpected SQLite value type in an evidence row")


class Split:
    """Which columns of a table are short (covered by repr() of their tuple, one C call) and which are large payloads (typed, length-prefixed, fed as is).
    Static per table, so no per-field work in the hot loop; correct for any value types because repr() and encode() are injective on str/bytes/int/None."""
    def __init__(self, table, large=()):
        columns = SCOPE[table]
        self.large = tuple(columns.index(c) for c in large)
        small = [i for i in range(len(columns)) if i not in self.large]
        self.small = itemgetter(*small) if len(small) > 1 else (lambda row, i=small[0]: (row[i],))
        self.small_indexes = tuple(small)


SPLITS = {"events": Split("events", ("native", "epcis")), "captures": Split("captures", ("raw",)), "motors": Split("motors", ("config",)),
          "rejections": Split("rejections"), "app_units": Split("app_units")}


def feed(h, row, split):
    """Add one row to hash h; returns the bytes hashed. A row of the wrong width raises (fail closed)."""
    if len(row) != len(split.small_indexes) + len(split.large):
        raise ValueError("evidence row has an unexpected width")
    head = repr(split.small(row)).encode("utf-8", "surrogatepass")
    h.update(head)
    size = len(head)
    for i in split.large:
        data = encode(row[i])
        h.update(data)
        size += len(data)
    return size


def put(h, value):
    h.update(encode(value))


def put_row(h, tag, row, split):
    h.update(tag)
    return feed(h, row, split)


def capture_digest(row):
    h = hashlib.sha256(CAPTURE_DOMAIN)
    feed(h, row, SPLITS["captures"])
    return h.digest()


def _plain(db):
    cursor = db.cursor()
    cursor.row_factory = None
    return cursor


def rejections_by_motor(db):
    """One read of the rejection rows (small in a healthy ledger: any rejection blocks its motor)."""
    out = {}
    for row in _plain(db).execute(f"SELECT {_COLS['rejections']} FROM rejections ORDER BY ordinal"):
        out.setdefault(row[1], []).append(row)
    return out


def _motor_digest(serial, motor_row, events, capture_lookup, rejections):
    h = hashlib.sha256(MOTOR_DOMAIN)
    h.update(encode(serial))
    size = 0
    if motor_row is None:
        h.update(b"m")
    else:
        h.update(b"M"); size += feed(h, motor_row, SPLITS["motors"])
    h.update(b"E")
    captures = set()
    for ev in events:
        h.update(b"R"); size += feed(h, ev, SPLITS["events"])
        captures.add(ev[_EV_CAPTURE])
    h.update(encode(len(events)))
    h.update(b"C"); h.update(encode(len(captures)))
    for ref in sorted(captures):
        found = capture_lookup(ref)
        if found is None:
            h.update(b"m"); h.update(encode(ref))                      # a referenced capture is missing: part of the digest, verification fails closed
        else:
            h.update(b"c"); h.update(encode(ref)); h.update(found[0]); size += found[1]
    h.update(b"J"); h.update(encode(len(rejections)))
    for r in rejections:
        h.update(b"R"); size += feed(h, r, SPLITS["rejections"])
    return h.hexdigest(), size


def motor_digest(db, serial, rejections=None):
    """Digest of everything verification and projection of one motor can read, by point lookups. Returns (hex, bytes_hashed)."""
    cursor = _plain(db)
    motor_row = cursor.execute(f"SELECT {_COLS['motors']} FROM motors WHERE serial=?", (serial,)).fetchone()
    events = cursor.execute(f"SELECT {_COLS['events']} FROM events WHERE motor=? ORDER BY ordinal", (serial,)).fetchall()

    def lookup(ref):
        row = cursor.execute(f"SELECT {_COLS['captures']} FROM captures WHERE hash=?", (ref,)).fetchone()
        return None if row is None else (capture_digest(row), len(row[1]) if isinstance(row[1], bytes) else 0)
    if rejections is None:
        rejections = rejections_by_motor(db)
    return _motor_digest(serial, motor_row, events, lookup, rejections.get(serial, ()))


class _Schema:
    large, small_indexes = (3,), (0, 1, 2)
    small = staticmethod(itemgetter(0, 1, 2))


SCHEMA_SPLIT = _Schema()


def schema_digest(db):
    h = hashlib.sha256(FLEET_DOMAIN + b"/schema")
    marks = ",".join("?" * len(SCHEMA_TABLES))
    for row in _plain(db).execute(f"SELECT type, name, tbl_name, sql FROM sqlite_schema WHERE tbl_name IN ({marks}) ORDER BY type, name", SCHEMA_TABLES):
        put_row(h, b"S", row, SCHEMA_SPLIT)
    return h.hexdigest()


class EvidenceState:
    """One consistent reading of the evidence scope inside one read transaction."""
    def __init__(self, fleet, motors, units, evidence_bytes):
        self.fleet, self.motors, self.units, self.evidence_bytes = fleet, motors, units, evidence_bytes


def fleet_state(db, registry_digest):
    """Hash the whole evidence scope in one streaming pass. Must be called inside the caller's read transaction (so one snapshot)."""
    cursor = _plain(db)
    captures, capture_bytes = {}, {}
    for row in cursor.execute(f"SELECT {_COLS['captures']} FROM captures"):
        captures[row[0]] = capture_digest(row)
        capture_bytes[row[0]] = len(row[1]) if isinstance(row[1], bytes) else 0
    rejections = rejections_by_motor(db)
    motor_rows = {row[0]: row for row in cursor.execute(f"SELECT {_COLS['motors']} FROM motors ORDER BY serial")}

    def lookup(ref):
        d = captures.get(ref)
        return None if d is None else (d, capture_bytes[ref])
    digests, total, referenced = {}, 0, set()
    h = hashlib.sha256(FLEET_DOMAIN)
    orphan_events = []
    stream = itertools.groupby(cursor.execute(f"SELECT {_COLS['events']} FROM events ORDER BY motor, ordinal"), key=lambda r: r[_EV_MOTOR])
    for motor, group in stream:
        events = list(group)
        referenced.update(ev[_EV_CAPTURE] for ev in events)
        if motor in motor_rows:
            digests[motor], size = _motor_digest(motor, motor_rows[motor], events, lookup, rejections.get(motor, ()))
            total += size
        else:
            orphan_events.extend(events)
    for serial, row in motor_rows.items():
        if serial not in digests:                                                                              # a motor with no events at all
            digests[serial], size = _motor_digest(serial, row, (), lookup, rejections.get(serial, ()))
            total += size
    digests = {serial: digests[serial] for serial in motor_rows}
    units = [row for row in cursor.execute(f"SELECT {_COLS['app_units']} FROM app_units ORDER BY serial")]
    put(h, registry_digest)
    put(h, schema_digest(db))
    put(h, len(units))
    for u in units:
        total += put_row(h, b"U", u, SPLITS["app_units"])
    put(h, len(digests))
    for serial, d in digests.items():
        put(h, serial); put(h, d)
    # Rows that belong to no registered motor (foreign keys or triggers removed): hashed in full, normally none.
    orphan_events.sort(key=lambda r: r[0])
    put(h, len(orphan_events))
    for ev in orphan_events:
        total += put_row(h, b"O", ev, SPLITS["events"])
    stray = [r for motor, rows in rejections.items() if motor not in motor_rows for r in rows]
    put(h, len(stray))
    for r in stray:
        total += put_row(h, b"X", r, SPLITS["rejections"])
    # Captures no event references cannot influence a result, but a new one is evidence-shaped: bind their keys.
    unreferenced = sorted(k for k in captures if k not in referenced)
    put(h, len(unreferenced))
    for key in unreferenced:
        put(h, key)
    return EvidenceState(h.hexdigest(), digests, [u[0] for u in units], total)
