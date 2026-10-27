"""Synthetic staging for the F6 demo and tests: two separate factories (own ledger, own registry, own checkpoint, own keys) and one supplier. Disposable; not part of any product path.

Factory A ("Aster Motors") uses the bundled registry: the supplier's lot NSB-204 is its alias for canonical BR-204.
Factory B ("Kaveri Drives") uses a DIFFERENT registry: the same supplier lot NSB-204 is its alias for canonical BR-771 (no BR-204 exists there), and one B motor carries the look-alike
label BR-77I recorded through the legacy/bypassed capture path, which the unchanged guard must hold as unresolved.
"""
import contextlib
import copy
import json
from pathlib import Path

from .. import lot_identity as lots, service as svc
from ..anchors import export_anchor, publish_candidate
from ..service import PART, Manufacturing
from . import trust

SUPPLIER_ID, A_ID, B_ID = "urn:demo:supplier:northstar-bearings", "urn:demo:factory:aster-motors", "urn:demo:factory:kaveri-drives"
SUPPLIER_LOT = "NSB-204"


def registry_b():
    doc = copy.deepcopy(json.loads(lots.DEFAULT_REGISTRY.read_text(encoding="utf-8")))
    doc["entries"] = [e for e in doc["entries"] if e["canonical"] != "BR-204"]
    a = copy.deepcopy(next(e for e in json.loads(lots.DEFAULT_REGISTRY.read_text(encoding="utf-8"))["entries"] if e["canonical"] == "BR-204"))
    a.update(canonical="BR-771", aliases=["NSB-204"], rawMaterialLot="STEEL-26-410")
    doc["entries"].append(a)
    doc["registryId"] = "PRAMAAN-SYNTHETIC-LOT-REGISTRY-FACTORY-B"
    return doc


@contextlib.contextmanager
def registry_in_force(path):
    """The documented selector the server entry point uses (--lot-registry); needed so checkpoint_ops, which opens the ledger itself, sees this factory's registry."""
    previous = svc.DEFAULT_LOT_REGISTRY
    svc.DEFAULT_LOT_REGISTRY = Path(path) if path else None
    try:
        yield
    finally:
        svc.DEFAULT_LOT_REGISTRY = previous


def _bypass_assemble(app, motor, de, nde):
    """Legacy/bypassed capture with no lot validation (how a mistyped label gets into a ledger)."""
    build = f"BUILD-{motor}"
    app.event(motor, "WORK_ORDER_OPENED", "MES", dict(orderType="BUILD", expectedChanges=[dict(slot=s, action="INSTALL") for s in ("DE", "NDE")]), work_order=build)
    for slot, lot in (("DE", de), ("NDE", nde)):
        a = app.event(motor, "MATERIAL_ALLOCATED", "MATERIAL", dict(rawMaterialLot="STEEL-26-518", supplierId="SUP-KAV-02", supplierName="x"))
        made = app.event(motor, "BEARING_MANUFACTURED", "MATERIAL", dict(rawMaterialLot=a["payload"]["rawMaterialLot"], supplierId=a["payload"]["supplierId"], part=PART, lot=lot,
                                                                         serial=f"BRG-{motor}-{slot}-01", materialEventId=a["eventId"]))
        app.event(motor, "COMPONENT_INSTALLED", "ASSY", dict(componentType="BEARING", slot=slot, part=PART, lot=lot, identityGranularity="SERIAL", serial=f"BRG-{motor}-{slot}-01",
                                                          manufacturingEventId=made["eventId"]), work_order=build)
    app.event(motor, "WORK_ORDER_CLOSED", "MES", dict(disposition="COMPLETED"), work_order=build)


def stage_factory(root, kind, unresolved="sighting"):
    """kind 'A' or 'B'. Factory B's third motor carries an identity problem, chosen by `unresolved`:
      'sighting'            an unverified observation of QX-77 (unrelated string): existing scoped containment holds the motor as UNRESOLVED and the checkpoint cycle COMPLETES;
      'lookalike-sighting'  an observation of BR-77I, a look-alike of BR-771 which is in use on another B motor: the existing checkpoint accept REFUSES (nothing is renewed);
      'install'             BR-77I recorded as the INSTALLED lot through the bypassed capture path: the existing checkpoint accept REFUSES.
    No recall is announced here: the ledger is anchored and ANCHORED_CURRENT before any alert exists."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    registry_path = root / "registry.json"
    if kind == "B":
        registry_path.write_text(json.dumps(registry_b(), indent=1), encoding="utf-8")
        recalled = "BR-771"
    else:
        registry_path.write_text(lots.DEFAULT_REGISTRY.read_text(encoding="utf-8"), encoding="utf-8")
        recalled = "BR-204"
    db, anchor = root / "ledger.sqlite", root / "checkpoint.json"
    app = Manufacturing(db, lot_registry=registry_path)
    try:
        for serial, de in ((f"MTR-{kind}-001", recalled), (f"MTR-{kind}-002", "BR-310"), (f"MTR-{kind}-003", recalled if kind == "A" else "BR-310")):
            app.create_unit(serial)
            if kind == "B" and serial.endswith("003") and unresolved == "install":
                _bypass_assemble(app, serial, "BR-77I", "BR-312")
            else:
                app.assemble(serial, de, "BR-312")
        if kind == "B" and unresolved != "install":
            app.observe("MTR-B-003", "QX-77" if unresolved == "sighting" else "BR-77I")
        app.snapshot()
        publish_candidate(anchor, export_anchor(app))
    finally:
        app.close()
    return dict(root=root, database=db, registry=registry_path, anchor=anchor, custody=root / "custody", recalled=recalled)


def checkpoint_cycle(stage, anchor, previous, custodian):
    """The existing, unchanged operator cycle: propose, then accept with the typed hash and every required per-motor acknowledgement (scripted here; in real use a person decides)."""
    from .. import checkpoint_ops
    with registry_in_force(stage["registry"]):
        proposal = checkpoint_ops.propose(stage["database"], anchor, stage["custody"], previous)
        if proposal["status"] == "NO_CANDIDATE_NEEDED":
            return anchor, previous
        accepted = checkpoint_ops.accept(stage["database"], anchor, stage["custody"], proposal["candidate"], custodian, proposal["candidateSha256"],
                                         acknowledged=proposal["review"]["requiresAcknowledgement"], expected_registry_digest=proposal["review"]["registry"]["digest"],
                                         acknowledge_registry=proposal["review"]["registry"]["digest"] if proposal["review"]["registryChange"]["requiresAcknowledgement"] else None)
    return Path(accepted["accepted"]), Path(anchor)


def stage_world(root, unresolved="sighting"):
    """Supplier S + factories A and B with separate directories, keys and trust files. Returns everything needed by tests and the demo."""
    root = Path(root)
    keys = root / "keys"
    pairs = {}
    for name, peer, role in (("supplier", SUPPLIER_ID, "supplier"), ("factory-a", A_ID, "factory"), ("factory-b", B_ID, "factory")):
        pairs[name] = trust.keygen(keys, name, peer, role)
    factory_trust = trust.write_trust(root / "supplier" / "trust.json", [pairs["factory-a"][1], pairs["factory-b"][1]])
    supplier_pin = trust.write_trust(root / "factory-a" / "trust.json", [pairs["supplier"][1]])
    trust.write_trust(root / "factory-b" / "trust.json", [pairs["supplier"][1]])
    return dict(root=root, keys=pairs, supplier_trust=factory_trust, supplier_pin=supplier_pin,
                a=stage_factory(root / "factory-a", "A"), b=stage_factory(root / "factory-b", "B", unresolved))
