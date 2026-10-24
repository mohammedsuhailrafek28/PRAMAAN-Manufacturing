"""Generate the explicitly synthetic investigation-workspace demonstration scenario.

Everything is produced by the real application service and the pinned v3 evaluator, using only
existing commands, with ONE authored edit: the capture-gap source id of two units is rewritten to
a shared value, because the current event schema scopes every source to one motor. That edit is
recorded in the output ("origin": "AUTHORED_SOURCE_EDIT") and is never applied to live data.

    python tools/generate_investigation_demo.py            # writes public/data/investigation-demo.json
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

OUT = Path(__file__).resolve().parents[1] / "public" / "data" / "investigation-demo.json"
SHARED_SOURCE = "ASSY:SHARED-DEMO-STATION"
SEEDED = ["MTR-26001", "MTR-26002", "MTR-26003", "MTR-26004", "MTR-26005"]

# unitId -> (title, de lot, nde lot, identity, gap, origin note)
EXTRAS = {
    "MTR-26011": ("Demo extra: untrusted observation", "BR-310", "BR-312", "SERIAL", False, "ENGINE_DEMO_EXTRA"),
    "MTR-26012": ("Demo extra: untrusted observation", "BR-310", "BR-312", "SERIAL", False, "ENGINE_DEMO_EXTRA"),
    "MTR-26013": ("Demo extra: lot-level ambiguity", "BR-204", "BR-204", "LOT", False, "ENGINE_DEMO_EXTRA"),
    "MTR-26014": ("Demo extra: lot-level ambiguity", "BR-204", "BR-204", "LOT", False, "ENGINE_DEMO_EXTRA"),
    "MTR-26015": ("Authored demo: shared capture gap", "BR-204", "BR-310", "SERIAL", True, "AUTHORED_SOURCE_EDIT"),
    "MTR-26016": ("Authored demo: shared capture gap", "BR-204", "BR-310", "SERIAL", True, "AUTHORED_SOURCE_EDIT"),
}
# Identity only until the evidence-update stage, when its assembly is recorded through the existing command.
LATE = {"MTR-26017": ("Demo extra: identity only, assembly recorded later", "ENGINE_DEMO_EXTRA")}


def author_shared_source(snap):
    """The only authored change: give two units' gaps one shared source id, in decisions only."""
    for unit in ("MTR-26015", "MTR-26016"):
        for bundle in snap["decisions"][unit].values():
            for d in [bundle["current"], *bundle["history"]]:
                for slot in d["slots"].values():
                    for gap in slot.get("gaps", []):
                        gap["sourceId"] = SHARED_SOURCE
    return snap


def main():
    with tempfile.TemporaryDirectory() as tmp:
        app = Manufacturing(Path(tmp) / "demo.sqlite")
        app.seed_demo()
        for unit, (title, de, nde, identity, gap, _) in EXTRAS.items():
            app.create_unit(unit, title, gap=gap)
            app.assemble(unit, de, nde, identity)
            app.record_historical_shipment_fixture(unit)
        for unit, (title, _) in LATE.items():
            app.create_unit(unit, title)
        app.snapshot()  # issue pre-rework records with the actual evaluator
        for unit in ("MTR-26013", "MTR-26014", "MTR-26015", "MTR-26016"):
            app.replace(unit, "BR-312")
        for unit in ("MTR-26011", "MTR-26012"):
            app.observe(unit, "BR-204")
        before = author_shared_source(copy.deepcopy(app.snapshot()))
        # Evidence updates through existing commands. Nothing is closed by hand; the evaluator's
        # answer changes (MTR-26012 stays listed with new evidence; MTR-26017 no longer has a task).
        app.replace("MTR-26012", "BR-312")
        app.assemble("MTR-26017", "BR-310", "BR-312", "SERIAL")
        after = author_shared_source(copy.deepcopy(app.snapshot()))
        app.close()
    origin = {u: "SEEDED" for u in SEEDED}
    origin.update({u: spec[5] for u, spec in EXTRAS.items()})
    origin.update({u: spec[1] for u, spec in LATE.items()})
    doc = dict(
        kind="SYNTHETIC_INVESTIGATION_DEMONSTRATION",
        label=("Synthetic demonstration. Decisions are real output of the pinned v3 evaluator over a synthetic ledger. "
               "Units MTR-26015 and MTR-26016 carry one authored edit: a shared capture-gap source id. Nothing here is a real recall."),
        sharedAuthoredSource=SHARED_SOURCE,
        origin=origin,
        stages=[
            dict(id="before", label="Before the evidence update", snapshot=before),
            dict(id="after", label="After a later install on MTR-26012 and an assembly record on MTR-26017", snapshot=after),
        ],
    )
    OUT.write_text(json.dumps(sanitize(doc), sort_keys=True, separators=(",", ":")), encoding="utf-8")
    print("wrote", OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
