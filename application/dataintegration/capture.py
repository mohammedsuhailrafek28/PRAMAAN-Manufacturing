"""Capture through the EXISTING EPCIS-compatible path (`pramaan_integration.encode_document` -> `Ledger.capture`).

`native_event` rebuilds exactly what `Manufacturing.event` builds, with one difference: `evidenceRefs` carries an import provenance reference
(`pramaan-import:v1:<canonicalId>:<content16>`) instead of the demo placeholder. That reference lives inside the hashed, chained ledger event, so
(a) the origin of an imported event survives loss of the staging database and (b) a repeated import can recognise what it already wrote.
`test_data_integration` asserts the rebuild is byte-identical to `Manufacturing.event` when given the same evidence reference.

Nothing here validates trust or grants anything: the ledger's own validation, hash chain, source capabilities and sequence rules still decide.
"""
import hashlib
import json
import re
from datetime import datetime, timedelta

from ..service import ALL_ROLES, Manufacturing          # first: importing the service puts integration/ on sys.path
from pramaan_integration import encode_document
from pramaan_integration.profile import validate_native

REF_RE = re.compile(r"^pramaan-import:v1:([0-9a-f]{32}):([0-9a-f]{16})$")
FMT = "%Y-%m-%dT%H:%M:%SZ"


# The capture window `Manufacturing.create_unit` registers for every source (tests pin these to the registered sessions). The ledger accepts an event only when
# session.from <= recordedAt <= session.to, and a rejection permanently blocks the motor, so the window is enforced BEFORE capture.
DEFAULT_WINDOW = ("2026-01-01T00:00:00Z", "2027-12-31T23:59:59Z")
DEFAULT_CLOCK = "2026-10-10T08:00:00Z"                  # the application clock of a ledger that has not moved yet
MAX_AHEAD_SECONDS = 0                                   # a source time may never lead the application clock: importing must not move the shared clock to source time
RECORDED_LAG, REPOSITORY_LAG, TICK = 4, 8, 30           # what `capture_event` adds: recordedAt = clock + 4, repository time = clock + 8, one tick = 30 s


class CaptureRefused(Exception):
    """Refused BEFORE anything was written or the application clock moved."""


def _parse(at):
    try:
        return datetime.strptime(at, FMT) if isinstance(at, str) else None
    except ValueError:
        return None


def projected_times(clock, occurred):
    """-> (recordedAt, repositoryTime) that `capture_event` would produce for this clock and source time."""
    at = _parse(max(clock, occurred)) + timedelta(seconds=TICK)
    return at + timedelta(seconds=RECORDED_LAG), at + timedelta(seconds=REPOSITORY_LAG)


def time_problem(occurred, clock, window=DEFAULT_WINDOW):
    """-> None when capturing an event with this source time is safe, else why not. Pure: reads nothing, moves no clock."""
    when, now = _parse(occurred), _parse(clock)
    if when is None or now is None or when.strftime(FMT) != occurred:
        return f"source time {occurred!r} is not a UTC timestamp of the form YYYY-MM-DDTHH:MM:SSZ"
    if occurred < window[0]:
        return f"source time {occurred} is before the authorised capture session ({window[0]} to {window[1]})"
    if when - now > timedelta(seconds=MAX_AHEAD_SECONDS):
        return f"source time {occurred} is after the application clock ({clock}); an import never moves the shared clock to a source time"
    recorded, repository = projected_times(clock, occurred)
    if max(recorded, repository).strftime(FMT) > window[1]:
        return f"source time {occurred} would be recorded after the authorised capture session ends ({window[1]})"
    return None


def session_window(config, source):
    """(earliest from, latest to) over the motor's authenticated sessions for `source`, from the ledger's own provisioned configuration; None if there is none."""
    spans = [(s["from"], s["to"]) for s in config["sessions"] if s["sourceId"] == source and s["authenticated"] is True]
    return (min(a for a, _ in spans), max(b for _, b in spans)) if spans else None


LIFECYCLE_REFERENCE_KEYS = {"subjectEventIds", "previousOperationEventId"}
HISTORICAL_SHIPMENT_REF = "pramaan-import-historical-shipment:v1"   # carried (inside the hashed event) by every imported MOTOR_SHIPPED: a record of the past, never an authorization


def with_markers(kind, evidence):
    """Evidence list of an imported event; an imported shipment always declares itself historical."""
    refs = list(evidence or [])
    if kind == "MOTOR_SHIPPED" and HISTORICAL_SHIPMENT_REF not in refs:
        refs.append(HISTORICAL_SHIPMENT_REF)
    return refs


def import_ref(canonical_id: str, content_sha256: str) -> str:
    return f"pramaan-import:v1:{canonical_id}:{content_sha256[:16]}"


def parse_ref(text):
    m = REF_RE.match(text) if isinstance(text, str) else None
    return (m.group(1), m.group(2)) if m else None


def _plus(at, seconds):
    return (datetime.strptime(at, FMT) + timedelta(seconds=seconds)).strftime(FMT)


def event_id(motor, role, seq):
    return f"urn:pramaan:{motor}:{role}:{seq}"


def native_event(motor, kind, role, payload, seq, at, *, work_order=None, occurred=None, evidence=None, supersedes=None):
    """The native event Manufacturing.event would build for source sequence `seq` when the application clock reads `at`."""
    source = Manufacturing.source(role, motor)
    return dict(eventId=event_id(motor, role, seq), eventType=kind, schemaVersion=1, motorSerial=motor, sourceId=source, sourceSeq=seq,
                occurredAt=occurred or at, recordedAt=_plus(at, 4), actorId=ALL_ROLES[role][0], timeSource="SYNTHETIC_SIMULATED",
                evidenceRefs=list(evidence) if evidence is not None else [f"demo-record:{motor}:{role}:{seq}"], workOrderId=work_order, recallId=None,
                supersedesEventId=supersedes, captureSessionId=f"session:{source}", payload=payload)


def dry_run_problem(motor, kind, role, payload, seq, occurred, *, work_order=None, evidence=None, clock=DEFAULT_CLOCK, window=DEFAULT_WINDOW):
    """Profile + capability check WITHOUT touching the ledger. -> None when the ledger would accept the shape, else a message.
    A ledger rejection permanently blocks a motor, so nothing is captured that this check refuses."""
    if role not in ALL_ROLES or kind not in ALL_ROLES[role][1]:
        return f"source role {role} may not record {kind}"
    problem = time_problem(occurred, clock, window)
    if problem:
        return f"TIME_OUT_OF_WINDOW: {problem}"
    if kind not in ALL_ROLES["MACHINING"][1] + ALL_ROLES["QC"][1] and LIFECYCLE_REFERENCE_KEYS & set(payload):
        # The pinned ledger applies its lifecycle reference rule to ANY payload carrying these keys; a bad reference is a permanent rejection.
        return f"payload field {sorted(LIFECYCLE_REFERENCE_KEYS & set(payload))} is reserved for lifecycle events"
    try:
        validate_native(native_event(motor, kind, role, payload, seq, occurred, work_order=work_order, occurred=occurred, evidence=with_markers(kind, evidence)))
    except Exception as exc:                # ValidationFailure and any profile error: refuse, never capture
        return str(exc)
    return None


def capture_event(app: Manufacturing, motor, kind, role, payload, *, work_order=None, occurred=None, evidence=None):
    """Write one event through ledger.capture at the application clock's next tick; `occurred` is the source's own time and can never lead that clock (see `time_problem`),
    so recordedAt never precedes occurredAt and importing never moves the shared clock to a source time.
    Source role, source registration and capture window are checked first: a refusal leaves the clock and the ledger untouched."""
    source = Manufacturing.source(role, motor)
    config = app.ledger._config(motor)
    capability = config["sources"].get(source)
    if role not in ALL_ROLES or capability is None:
        raise CaptureRefused(f"{motor} has no {role} source registered (units created without lifecycle=True have no MACHINING or QC source)")
    if kind not in ALL_ROLES[role][1] or kind not in capability["eventTypes"] or ALL_ROLES[role][0] not in capability["actors"]:
        raise CaptureRefused(f"source {source} may not record {kind}")
    problem = time_problem(occurred or app.clock(), app.clock(), session_window(config, source) or ("9", "0"))
    if problem:
        raise CaptureRefused(problem)
    seq = app.ledger.watermark(motor)[source] + 1
    at = app.tick()
    event = native_event(motor, kind, role, payload, seq, at, work_order=work_order, occurred=occurred, evidence=with_markers(kind, evidence))
    repository_time = _plus(at, 8)
    raw = json.dumps(encode_document([event], repository_time), separators=(",", ":")).encode()
    app.ledger.capture(motor, raw, producer_source=source, expected_sha256=hashlib.sha256(raw).hexdigest())
    return event
