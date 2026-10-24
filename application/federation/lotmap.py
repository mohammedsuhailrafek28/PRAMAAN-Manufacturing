"""Supplier-qualified lot -> this factory's local canonical lot, through the factory's OWN registry (unchanged `LotRegistry.resolve`). No other path.

Outcomes: MAPPED (exactly one active registry entry for that supplier, part and lot string or declared alias) or LOT_UNMAPPED (anything else, including look-alikes such as
`NSB-2O4`, withdrawn/expired lots, another supplier's lot and a part mismatch). An unmapped lot is NEVER reported as "not affected"; it simply cannot be adopted.
"""
from dataclasses import dataclass


@dataclass
class Mapping:
    mapped: bool
    canonical: str = None
    reason: str = ""


def map_lot(registry, lot):
    res = registry.resolve(lot["supplierLot"], at=None, part=lot["part"])
    if not res.ok:
        return Mapping(False, reason=res.status)
    if res.entry["supplierId"] != lot["supplierId"]:
        return Mapping(False, reason="SUPPLIER_MISMATCH")
    return Mapping(True, canonical=res.canonical)
