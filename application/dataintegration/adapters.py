"""Source-specific adapters: mapped fields (already column-mapped, transformed and format-checked) -> one canonical event.

An adapter knows what its system means (an ERP lot issue, an MES station event, a SCADA tag sample, a quality inspection, a logistics dispatch). It
does not look at other records and never decides anything about recall status; cross-record relationships are checked by the planner.
"""
import re
from typing import Callable

from pydantic import ValidationError

from .canonical import CanonicalEvent, Kind, SourceSystem, build_event, explain
from .mapping import MappingConfig


class AdapterError(Exception):
    def __init__(self, code, message, field=None):
        super().__init__(message)
        self.code, self.message, self.field = code, message, field


def _split(value):
    return [p.strip().upper() for p in re.split(r"[;|,]", value) if p.strip()] if value else []


def _build(system, rid, kind, motor, at, attrs) -> CanonicalEvent:
    try:
        return build_event(system, rid, kind, motor, at, {k: v for k, v in attrs.items() if v is not None})
    except ValidationError as exc:
        raise AdapterError("MISSING_REQUIRED" if all(e["type"] == "missing" for e in exc.errors()) else "BAD_VALUE", explain(exc)) from exc


def _need_motor(v):
    if not v.get("motorSerial"):
        raise AdapterError("MISSING_REQUIRED", "motor serial is required for this record", "motorSerial")
    return v["motorSerial"]


def erp_lot_issue(v: dict, cfg: MappingConfig) -> CanonicalEvent:
    return _build(SourceSystem.ERP, v["recordId"], Kind.BEARING_LOT_ISSUED, _need_motor(v), v["occurredAt"], dict(
        slot=v.get("slot"), lot=v.get("lot"), serial=v.get("serial"), rawMaterialLot=v.get("rawMaterialLot"), supplierId=v.get("supplierId"),
        supplierName=v.get("supplierName"), document=v["recordId"]))


def mes_assembly(v: dict, cfg: MappingConfig) -> CanonicalEvent:
    kind = {"OPEN": Kind.WORK_ORDER_OPENED, "INSTALL": Kind.COMPONENT_INSTALLED, "REMOVE": Kind.COMPONENT_REMOVED, "CLOSE": Kind.WORK_ORDER_CLOSED}.get(v.get("event") or "")
    if kind is None:
        raise AdapterError("BAD_VALUE", f"unsupported MES event {v.get('event')!r}", "event")
    common = dict(workOrderId=v.get("workOrderId"), station=v.get("station"), operatorId=v.get("operatorId"))
    if kind is Kind.WORK_ORDER_OPENED:
        attrs = dict(common, orderType=v.get("orderType"), expectedSlots=_split(v.get("slots")))
    elif kind is Kind.WORK_ORDER_CLOSED:
        attrs = dict(common, disposition=v.get("disposition"))
    else:
        attrs = dict(common, slot=v.get("slot"), lot=v.get("lot"), serial=v.get("serial"))
    return _build(SourceSystem.MES, v["recordId"], kind, _need_motor(v), v["occurredAt"], attrs)


def scada_signal(v: dict, cfg: MappingConfig) -> CanonicalEvent:
    ranges = cfg.options.get("tagRanges", {})
    try:
        value = float(v["value"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AdapterError("BAD_VALUE", f"signal value {v.get('value')!r} is not a number", "value") from exc
    if value != value or value in (float("inf"), float("-inf")):
        raise AdapterError("BAD_VALUE", "signal value is not finite", "value")
    tag = v.get("tag")
    spec = ranges.get(tag) if tag else None
    if ranges and spec is None:
        raise AdapterError("BAD_VALUE", f"tag {tag!r} is not in this mapping's tagRanges", "tag")
    if spec:
        if v.get("unit") != spec["unit"]:
            raise AdapterError("BAD_VALUE", f"tag {tag} is expected in {spec['unit']}, source gave {v.get('unit')!r}", "unit")
        if not spec["min"] <= value <= spec["max"]:
            raise AdapterError("BAD_VALUE", f"{tag}={value} {spec['unit']} is outside the plausible range {spec['min']}..{spec['max']}", "value")
    if v.get("signalQuality") == "BAD":
        raise AdapterError("BAD_SIGNAL_QUALITY", "source flags this sample as BAD quality", "signalQuality")
    return _build(SourceSystem.SCADA, v["recordId"], Kind.PROCESS_SIGNAL, v.get("motorSerial"), v["occurredAt"], dict(
        stationId=v.get("stationId"), tag=tag, value=value, unit=v.get("unit"), signalQuality=v.get("signalQuality"), workOrderId=v.get("workOrderId")))


def quality_inspection(v: dict, cfg: MappingConfig) -> CanonicalEvent:
    return _build(SourceSystem.QUALITY, v["recordId"], Kind.QUALITY_INSPECTION, _need_motor(v), v["occurredAt"], dict(
        inspectionId=v["recordId"], protocolId=v.get("protocolId"), result=v.get("result"), inspectorId=v.get("inspectorId"),
        qualifiedFor=_split(v.get("qualifiedFor")), slot=v.get("slot"), lot=v.get("lot")))


def logistics_dispatch(v: dict, cfg: MappingConfig) -> CanonicalEvent:
    return _build(SourceSystem.LOGISTICS, v["recordId"], Kind.SHIPMENT_DISPATCHED, _need_motor(v), v["occurredAt"], dict(
        shipmentId=v["recordId"], customer=v.get("customer"), destination=v.get("destination"), carrier=v.get("carrier"), trackingNo=v.get("trackingNo")))


ADAPTERS: dict[str, tuple[SourceSystem, Callable]] = {
    "erp_lot_issue": (SourceSystem.ERP, erp_lot_issue),
    "mes_assembly": (SourceSystem.MES, mes_assembly),
    "scada_signal": (SourceSystem.SCADA, scada_signal),
    "quality_inspection": (SourceSystem.QUALITY, quality_inspection),
    "logistics_dispatch": (SourceSystem.LOGISTICS, logistics_dispatch),
}


def adapter_for(cfg: MappingConfig) -> Callable:
    if cfg.adapter not in ADAPTERS:
        raise ValueError(f"unknown adapter {cfg.adapter!r}; known: {sorted(ADAPTERS)}")
    system, fn = ADAPTERS[cfg.adapter]
    if system is not cfg.sourceSystem:
        raise ValueError(f"adapter {cfg.adapter} serves {system.value}, mapping declares {cfg.sourceSystem.value}")
    return fn
