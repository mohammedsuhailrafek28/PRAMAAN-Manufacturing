"""Generate the explicitly synthetic datasets for the recall impact graph preview.

Two datasets, each produced by the real application service and the pinned v3 evaluator using only
existing commands: "de" (recall scope DE) and "nde" (recall scope NDE). Four units of "de" then carry
an AUTHORED link edit, so that link-integrity cases can be shown: the ledger event schema cannot
produce a missing or duplicated reference through the application. Those edits change events and
component rows after capture, so the capture hashes of those units no longer match their payloads;
this is recorded in the output. Decisions in edited units are the engine's output on the UNEDITED ledger.

    python tools/generate_impact_demo.py        # writes public/data/impact-demo.json
"""
import copy
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from preview_sanitize import sanitize  # noqa: E402  (public preview JSON must not carry customer/destination/operator ids)
from application.service import Manufacturing  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "public" / "data" / "impact-demo.json"

# unit, title, DE lot, NDE lot, identity, gap, ship, origin kind
DE_UNITS = [
    ("MTR-26001", "Serial-tracked assembly", "BR-204", "BR-310", "SERIAL", False, True, "SEEDED"),
    ("MTR-26002", "Lot-level ambiguity", "BR-204", "BR-204", "LOT", False, True, "SEEDED"),
    ("MTR-26003", "Unaffected supplier lot", "BR-310", "BR-312", "SERIAL", False, True, "SEEDED"),
    ("MTR-26004", "Capture coverage gap", "BR-204", "BR-310", "SERIAL", True, True, "SEEDED"),
    ("MTR-26005", "Untrusted affected-bearing observation", "BR-310", "BR-312", "SERIAL", False, True, "SEEDED"),
    ("MTR-26021", "Demo extra: recalled lot in NDE only", "BR-310", "BR-204", "SERIAL", False, True, "ENGINE_DEMO_EXTRA"),
    ("MTR-26022", "Demo extra: recalled lot in DE, not shipped", "BR-204", "BR-310", "SERIAL", False, False, "ENGINE_DEMO_EXTRA"),
    ("MTR-26023", "Demo extra: lot-level identity, shipped", "BR-204", "BR-310", "LOT", False, True, "ENGINE_DEMO_EXTRA"),
    ("MTR-26031", "Authored link edit: no manufacture record linked", "BR-204", "BR-310", "SERIAL", False, True, "AUTHORED_LINK_EDIT"),
    ("MTR-26032", "Authored link edit: one manufacture record, two installs", "BR-204", "BR-310", "SERIAL", False, True, "AUTHORED_LINK_EDIT"),
    ("MTR-26033", "Authored link edit: installation lot contradicts manufacture lot", "BR-204", "BR-310", "SERIAL", False, True, "AUTHORED_LINK_EDIT"),
    ("MTR-26034", "Authored link edit: no material allocation linked", "BR-204", "BR-310", "SERIAL", False, True, "AUTHORED_LINK_EDIT"),
]
NDE_UNITS = [
    ("MTR-26101", "Recalled lot in DE, outside NDE scope", "BR-204", "BR-310", "SERIAL", False, True, "ENGINE_DEMO_EXTRA"),
    ("MTR-26102", "Recalled lot in NDE", "BR-310", "BR-204", "SERIAL", False, True, "ENGINE_DEMO_EXTRA"),
    ("MTR-26103", "Recalled lot in both, lot-level identity", "BR-204", "BR-204", "LOT", False, True, "ENGINE_DEMO_EXTRA"),
    ("MTR-26104", "Control: unaffected lots", "BR-310", "BR-312", "SERIAL", False, True, "ENGINE_DEMO_EXTRA"),
    ("MTR-26105", "Recalled lot in NDE, not shipped", "BR-312", "BR-204", "SERIAL", False, False, "ENGINE_DEMO_EXTRA"),
]


def run(units, slots, after=None):
    with tempfile.TemporaryDirectory() as tmp:
        app = Manufacturing(Path(tmp) / "demo.sqlite")
        for serial, title, de, nde, identity, gap, ship, _ in units:
            app.create_unit(serial, title, gap=gap)
            app.assemble(serial, de, nde, identity)
            if ship:
                app.ship(serial)
        app.announce("BR-204", slots)
        app.snapshot()  # issue pre-rework records with the actual evaluator
        if after:
            after(app)
        snap = app.snapshot()
        app.close()
    return snap


def de_after(app):
    app.replace("MTR-26002", "BR-312")
    app.replace("MTR-26004", "BR-312")
    app.observe("MTR-26005", "BR-204")


def edit(snap, unit, fn):
    u = next(x for x in snap["units"] if x["unitId"] == unit)
    fn(u)


def install(u, slot):
    return next(e for e in u["events"] if e["eventType"] == "COMPONENT_INSTALLED" and e["payload"]["slot"] == slot)


def drop_lineage(snap, unit, manufacturing_event_id):
    snap["lineage"] = [l for l in snap["lineage"] if not (l["unitId"] == unit and l["manufacturingEventId"] == manufacturing_event_id)]


def author_edits(snap):
    notes = {}
    # 26031: the DE installation names no manufacture record
    def no_link(u):
        e = install(u, "DE")
        drop_lineage(snap, u["unitId"], e["payload"].pop("manufacturingEventId"))
    edit(snap, "MTR-26031", no_link)
    notes["MTR-26031"] = "COMPONENT_INSTALLED(DE).payload.manufacturingEventId removed after capture"

    # 26032: the NDE installation references the DE installation's manufacture record
    def duplicate(u):
        de, nde = install(u, "DE"), install(u, "NDE")
        drop_lineage(snap, u["unitId"], nde["payload"]["manufacturingEventId"])
        nde["payload"]["manufacturingEventId"] = de["payload"]["manufacturingEventId"]
    edit(snap, "MTR-26032", duplicate)
    notes["MTR-26032"] = "COMPONENT_INSTALLED(NDE).payload.manufacturingEventId pointed at the DE manufacture record after capture"

    # 26033: the DE installation writes a different lot than its manufacture record
    def mismatch(u):
        e = install(u, "DE")
        e["payload"]["lot"] = "BR-312"
        for c in snap["components"]:
            if c["unitId"] == u["unitId"] and c["componentId"] == e["eventId"]:
                c["lot"] = "BR-312"
    edit(snap, "MTR-26033", mismatch)
    notes["MTR-26033"] = "COMPONENT_INSTALLED(DE).payload.lot changed to BR-312 after capture; its manufacture record still says BR-204"

    # 26034: the DE manufacture record names no material allocation
    def no_material(u):
        e = install(u, "DE")
        m = next(x for x in u["events"] if x["eventId"] == e["payload"]["manufacturingEventId"])
        m["payload"].pop("materialEventId")
        m["payload"].pop("rawMaterialLot", None)
        drop_lineage(snap, u["unitId"], m["eventId"])
    edit(snap, "MTR-26034", no_material)
    notes["MTR-26034"] = "BEARING_MANUFACTURED(DE).payload.materialEventId and rawMaterialLot removed after capture"
    return notes


def main():
    de = run(DE_UNITS, ["DE"], de_after)
    edit_notes = author_edits(de)
    nde = run(NDE_UNITS, ["NDE"])

    def origin(units, notes):
        out = {}
        for u in units:
            kind = u[7]
            out[u[0]] = dict(kind=kind, note=notes.get(u[0], "Engine decisions over an unedited synthetic ledger"))
        return out

    doc = dict(
        kind="SYNTHETIC_IMPACT_DEMONSTRATION",
        label=("Synthetic demonstration. Decisions are real output of the pinned v3 evaluator over a synthetic ledger. "
               "Four units of the DE dataset carry an authored link edit made after capture (hashes of those units no longer match). "
               "Nothing here is a real recall."),
        datasets=[
            dict(id="de", label="Recall scope: DE position", origin=origin(DE_UNITS, edit_notes), snapshot=de),
            dict(id="nde", label="Recall scope: NDE position", origin=origin(NDE_UNITS, {}), snapshot=nde),
        ],
    )
    OUT.write_text(json.dumps(sanitize(doc), sort_keys=True, separators=(",", ":")), encoding="utf-8")
    print("wrote", OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
