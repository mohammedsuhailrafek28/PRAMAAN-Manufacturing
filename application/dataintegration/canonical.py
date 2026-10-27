"""Canonical manufacturing event schema for the data integration layer (Pydantic v2).

Every record that leaves a source adapter is a RECORDED CLAIM made by a source system. Nothing here is an independently authenticated physical fact,
and the schema has no place to put a verification, clearance, release or recall-status statement: such keys are rejected by name and
`independentlyVerified` can only ever be False.
"""
import hashlib
import json
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

SERIAL_RE = r"MTR-[A-Z0-9-]{3,30}"      # same shape application.service.Manufacturing.create_unit accepts
SLOTS = ("DE", "NDE")
NOT_ESTABLISHED = ("that the physical event happened as described", "that the part, lot or serial is the one named",
                   "release eligibility", "recall clearance", "independent verification")


class SourceSystem(str, Enum):
    ERP = "ERP"
    MES = "MES"
    SCADA = "SCADA"
    QUALITY = "QUALITY"
    LOGISTICS = "LOGISTICS"


class Kind(str, Enum):
    BEARING_LOT_ISSUED = "BEARING_LOT_ISSUED"           # ERP    -> MATERIAL_ALLOCATED + BEARING_MANUFACTURED
    WORK_ORDER_OPENED = "WORK_ORDER_OPENED"             # MES    -> same ledger type
    COMPONENT_INSTALLED = "COMPONENT_INSTALLED"         # MES    -> same ledger type
    COMPONENT_REMOVED = "COMPONENT_REMOVED"             # MES    -> same ledger type
    WORK_ORDER_CLOSED = "WORK_ORDER_CLOSED"             # MES    -> same ledger type
    PROCESS_SIGNAL = "PROCESS_SIGNAL"                   # SCADA  -> staged only (no ledger event type exists for it)
    QUALITY_INSPECTION = "QUALITY_INSPECTION"           # QUALITY-> staged only (see docs: INSPECTION_RECORDED is a recall-policy input)
    SHIPMENT_DISPATCHED = "SHIPMENT_DISPATCHED"         # LOGISTICS -> MOTOR_SHIPPED (historical record, not the ship operation)


# Kinds that can become ledger events through the existing EPCIS-compatible capture path.
CAPTURABLE = {Kind.BEARING_LOT_ISSUED, Kind.WORK_ORDER_OPENED, Kind.COMPONENT_INSTALLED, Kind.COMPONENT_REMOVED, Kind.WORK_ORDER_CLOSED, Kind.SHIPMENT_DISPATCHED}
# Order used when two records of one motor carry the same timestamp.
RANK = {Kind.BEARING_LOT_ISSUED: 0, Kind.WORK_ORDER_OPENED: 1, Kind.COMPONENT_REMOVED: 2, Kind.COMPONENT_INSTALLED: 3, Kind.WORK_ORDER_CLOSED: 4,
        Kind.SHIPMENT_DISPATCHED: 5, Kind.PROCESS_SIGNAL: 6, Kind.QUALITY_INSPECTION: 6}
FORBIDDEN_KEYS = frozenset({"verified", "independentlyVerified", "independent", "trusted", "authorized", "approved", "clearance", "cleared", "releaseEligible",
                            "currentReleaseEligible", "recallStatus", "recallDecision", "semanticsProfile", "coveragePolicy"})


class _Attr(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class LotIssued(_Attr):
    slot: Literal["DE", "NDE"]
    lot: str = Field(min_length=1, max_length=80)
    serial: Optional[str] = Field(default=None, min_length=1, max_length=80)
    rawMaterialLot: str = Field(min_length=1, max_length=80)
    supplierId: str = Field(min_length=1, max_length=80)
    supplierName: str = Field(min_length=1, max_length=200)
    document: str = Field(min_length=1, max_length=80)


class WorkOrderOpened(_Attr):
    workOrderId: str = Field(min_length=1, max_length=80)
    orderType: Literal["BUILD", "REWORK"]
    expectedSlots: list[Literal["DE", "NDE"]] = Field(min_length=1, max_length=2)
    station: Optional[str] = None
    operatorId: Optional[str] = None

    @field_validator("expectedSlots")
    @classmethod
    def unique(cls, v):
        if len(set(v)) != len(v):
            raise ValueError("duplicate slot")
        return v


class ComponentChange(_Attr):
    workOrderId: str = Field(min_length=1, max_length=80)
    slot: Literal["DE", "NDE"]
    lot: str = Field(min_length=1, max_length=80)
    serial: Optional[str] = Field(default=None, min_length=1, max_length=80)
    station: Optional[str] = None
    operatorId: Optional[str] = None


class WorkOrderClosed(_Attr):
    workOrderId: str = Field(min_length=1, max_length=80)
    disposition: Literal["COMPLETED", "CANCELLED"]
    station: Optional[str] = None
    operatorId: Optional[str] = None


class ProcessSignal(_Attr):
    stationId: str = Field(min_length=1, max_length=80)
    tag: str = Field(min_length=1, max_length=80)
    value: float
    unit: str = Field(min_length=1, max_length=20)
    signalQuality: Literal["GOOD", "UNCERTAIN", "BAD"]
    workOrderId: Optional[str] = None


class QualityInspection(_Attr):
    inspectionId: str = Field(min_length=1, max_length=80)
    protocolId: str = Field(min_length=1, max_length=80)
    result: Literal["PASS", "FAIL"]
    inspectorId: str = Field(min_length=1, max_length=80)
    qualifiedFor: list[str] = Field(default_factory=list)
    slot: Optional[Literal["DE", "NDE"]] = None
    lot: Optional[str] = None


class ShipmentDispatched(_Attr):
    shipmentId: str = Field(min_length=1, max_length=80)
    customer: str = Field(min_length=1, max_length=200)
    destination: str = Field(min_length=1, max_length=200)
    carrier: Optional[str] = None
    trackingNo: Optional[str] = None


ATTRIBUTES = {Kind.BEARING_LOT_ISSUED: LotIssued, Kind.WORK_ORDER_OPENED: WorkOrderOpened, Kind.COMPONENT_INSTALLED: ComponentChange,
              Kind.COMPONENT_REMOVED: ComponentChange, Kind.WORK_ORDER_CLOSED: WorkOrderClosed, Kind.PROCESS_SIGNAL: ProcessSignal,
              Kind.QUALITY_INSPECTION: QualityInspection, Kind.SHIPMENT_DISPATCHED: ShipmentDispatched}


def sha256_json(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


class CanonicalEvent(BaseModel):
    """One normalized source record. `canonicalId` identifies the SOURCE RECORD (system + record id + kind), so re-importing the same record is recognised;
    `contentSha256` identifies what the source said, so the same record id with different content is a contradiction, not an update."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    canonicalId: str = Field(pattern=r"^[0-9a-f]{32}$")
    contentSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sourceSystem: SourceSystem
    sourceRecordId: str = Field(min_length=1, max_length=200)
    kind: Kind
    motorSerial: Optional[str] = Field(default=None, pattern=r"^" + SERIAL_RE + r"$")
    occurredAt: str = Field(pattern=r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
    attributes: dict[str, Any]
    claim: Literal["RECORDED_CLAIM_FROM_SOURCE_SYSTEM"] = "RECORDED_CLAIM_FROM_SOURCE_SYSTEM"
    independentlyVerified: Literal[False] = False

    @field_validator("attributes")
    @classmethod
    def no_forbidden(cls, v):
        bad = FORBIDDEN_KEYS & set(v)
        if bad:
            raise ValueError(f"attribute(s) not allowed in an imported record: {sorted(bad)}")
        return v


def canonical_id(system: str, record_id: str, kind: str) -> str:
    return hashlib.sha256(f"{system}\x1f{record_id}\x1f{kind}".encode("utf-8")).hexdigest()[:32]


def build_event(system: SourceSystem, record_id: str, kind: Kind, motor: Optional[str], occurred_at: str, attributes: dict) -> CanonicalEvent:
    """Validate kind-specific attributes with their Pydantic model and freeze the canonical event. Raises pydantic.ValidationError."""
    attrs = ATTRIBUTES[kind].model_validate(attributes).model_dump(mode="json")
    probe = dict(sourceSystem=system.value, sourceRecordId=record_id, kind=kind.value, motorSerial=motor, occurredAt=occurred_at, attributes=attrs)
    return CanonicalEvent(canonicalId=canonical_id(system.value, record_id, kind.value), contentSha256=sha256_json(probe), **{**probe, "sourceSystem": system, "kind": kind})


def explain(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'record'}: {e['msg']}" for e in exc.errors())
