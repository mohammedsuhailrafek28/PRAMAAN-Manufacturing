"""B2 design experiment (read-only on the product): what do the EXISTING ledger contract, pinned evaluator and application guards do when an interrupted work order is
closed with the already-valid disposition CANCELLED? Disposable synthetic database; no product file is changed and no event contract is touched.
usage (repository root):  python -B research/v1_1_scoped_containment/b2_experiment.py OUT.json
"""
import json
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from application.service import Manufacturing, PART  # noqa: E402
from application import lot_identity as lots  # noqa: E402

M = "MTR-93001"


def partial_build(app, motor, installs):
    """The first events of assemble(), stopping after `installs` component installations (a crash before WORK_ORDER_CLOSED)."""
    build = f"BUILD-{motor}"
    app.event(motor, "WORK_ORDER_OPENED", "MES", dict(orderType="BUILD", expectedChanges=[dict(slot=s, action="INSTALL") for s in ("DE", "NDE")]), work_order=build)
    for slot, lot in (("DE", "BR-310"), ("NDE", "BR-312"))[:installs]:
        made = app.manufacture(motor, lot, f"BRG-{motor}-{slot}-01")
        app.event(motor, "COMPONENT_INSTALLED", "ASSY", dict(componentType="BEARING", slot=slot, part=PART, lot=lot, identityGranularity="SERIAL",
                                                             manufacturingEventId=made["eventId"], serial=f"BRG-{motor}-{slot}-01"), work_order=build)
    return build


def measure(app, motor):
    snap = app.snapshot()
    d = next(iter(snap["decisions"][motor].values()))["current"]
    wo = [e for e in app.events(motor) if e["eventType"] == "WORK_ORDER_CLOSED"]
    return dict(openOperations=[o["workOrderId"] for o in lots.interrupted_operations(app.events(motor))],
                closeDispositions=[e["payload"]["disposition"] for e in wo],
                integrityGuard=d["integrityGuard"]["status"], identityGuard=d["identityGuard"]["status"],
                evaluatorAction=d["evaluatorOperationalAction"], finalAction=d["operationalAction"], evidenceFinding=d["evidenceFinding"], reasonCodes=d["reasonCodes"])


def interrupted(d, installs):
    app = Manufacturing(Path(d) / "b2.sqlite")
    app.create_unit(M)
    app.announce("BR-204", ["DE"])
    build = partial_build(app, M, installs)
    return app, build


def main(out):
    results = {}
    for installs in (0, 1, 2):
        with tempfile.TemporaryDirectory() as d:                       # branch 1: cancel, measure, then try the application's controlled replacement
            app, build = interrupted(d, installs)
            try:
                before = measure(app, M)
                app.event(M, "WORK_ORDER_CLOSED", "MES", dict(disposition="CANCELLED"), work_order=build)
                after = measure(app, M)
                try:
                    app.replace(M, "BR-312", "DE")
                    replace_after_cancel = "ACCEPTED"
                except Exception as exc:
                    replace_after_cancel = f"REFUSED: {exc}"
                after_replace = measure(app, M)
                try:
                    app.replace(M, "BR-312", "NDE")
                    both = measure(app, M)
                except Exception as exc:
                    both = f"REFUSED: {exc}"
            finally:
                app.close()
        with tempfile.TemporaryDirectory() as d:                       # branch 2: cancel, then a shipment that references the cancelled close
            app, build = interrupted(d, installs)
            try:
                app.event(M, "WORK_ORDER_CLOSED", "MES", dict(disposition="CANCELLED"), work_order=build)
                closed = next(e for e in app.events(M) if e["eventType"] == "WORK_ORDER_CLOSED")
                try:
                    app.event(M, "MOTOR_SHIPPED", "SHIP", dict(shipmentId="SHP-B2", customer="x", destination="y", assemblyEventId=closed["eventId"]))
                    shipped = "ACCEPTED"
                except Exception as exc:
                    shipped = f"REFUSED: {exc}"
                try:
                    app.replace(M, "BR-312", "DE")
                    after_rejection = "ACCEPTED"
                except Exception as exc:
                    after_rejection = f"REFUSED: {exc}"
            finally:
                app.close()
        results[f"installsBeforeCrash={installs}"] = dict(beforeCancel=before, afterCancelledClose=after, replaceAfterCancel=replace_after_cancel, afterReplace=after_replace, afterBothSlotsReplaced=both,
                                                          shipReferencingCancelledClose=shipped, captureAfterThatRejection=after_rejection)
    Path(out).write_text(json.dumps(results, indent=1, sort_keys=True, default=str), encoding="utf-8")
    for k, v in results.items():
        print(k, "| before:", v["beforeCancel"]["integrityGuard"], v["beforeCancel"]["finalAction"], "| after cancel:", v["afterCancelledClose"]["integrityGuard"],
              v["afterCancelledClose"]["finalAction"], v["afterCancelledClose"]["reasonCodes"], "| replace:", v["replaceAfterCancel"][:50], "| ship:", v["shipReferencingCancelledClose"][:50], "| next capture:", v["captureAfterThatRejection"][:60])


if __name__ == "__main__":
    main(sys.argv[1])
