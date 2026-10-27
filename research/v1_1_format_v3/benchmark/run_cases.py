"""Candidate runner for independent benchmark cases (schema: research/v1_1_hardening/case.schema.v1_1.json).

The runner is generic: it contains no knowledge of any sealed case and is NOT tuned to any. It executes the `steps` of each case against a disposable
synthetic database and reports, per motor, the observed outcome next to the author's expectation. It never edits a case, never reads reviewer verdicts to
change behaviour, and writes results unchanged.

usage (repository root):  python -B research/v1_1_format_v3/benchmark/run_cases.py CASES_DIR OUT.json [--sample]
`--sample` marks the output as a harness self-check on candidate-authored samples: such results are NOT independent evidence and must not be scored.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from application import checkpoint_ops, lot_identity as lots, service as S            # noqa: E402
from application.anchors import TrustedAnchor, export_anchor, publish_candidate        # noqa: E402
from application.service import Manufacturing, ValidationFailure, LedgerBlocked, PART  # noqa: E402


def bypass_assemble(app, motor, de, nde, registry_doc):
    """Capture route that did not pass the validating commands (legacy or other-system records): v1.0 sequence, no lot validation.
    Supplier fields are copied from the case registry when it knows the lot (a consistent legacy record), else a default Kaveri-like supplier."""
    known = {e["canonical"]: e for e in registry_doc.get("entries", [])}
    build = f"BUILD-{motor}"
    app.event(motor, "WORK_ORDER_OPENED", "MES", dict(orderType="BUILD", expectedChanges=[dict(slot=s, action="INSTALL") for s in ("DE", "NDE")]), work_order=build)
    for slot, lot in (("DE", de), ("NDE", nde)):
        serial = f"BRG-{motor}-{slot}-01"
        ent = known.get(lot) or {}
        raw_lot, sup_id, sup_name = ent.get("rawMaterialLot", "STEEL-LEGACY"), ent.get("supplierId", "SUP-KAV-02"), ent.get("supplierName", "legacy supplier")
        a = app.event(motor, "MATERIAL_ALLOCATED", "MATERIAL", dict(rawMaterialLot=raw_lot, supplierId=sup_id, supplierName=sup_name))
        made = app.event(motor, "BEARING_MANUFACTURED", "MATERIAL", dict(rawMaterialLot=raw_lot, supplierId=sup_id, part=PART, lot=lot, serial=serial, materialEventId=a["eventId"]))
        app.event(motor, "COMPONENT_INSTALLED", "ASSY", dict(componentType="BEARING", slot=slot, part=PART, lot=lot, identityGranularity="SERIAL", manufacturingEventId=made["eventId"], serial=serial), work_order=build)
    app.event(motor, "WORK_ORDER_CLOSED", "MES", dict(disposition="COMPLETED"), work_order=build)


class Interrupt:
    def __init__(self, app, after):
        self.app, self.after, self.n, self.real = app, after, 0, app.ledger.capture

    def __enter__(self):
        def flaky(*a, **kw):
            if self.n == self.after:
                raise RuntimeError("injected interruption")
            self.n += 1
            return self.real(*a, **kw)
        self.app.ledger.capture = flaky

    def __exit__(self, *exc):
        self.app.ledger.capture = self.real
        return exc[0] is RuntimeError


def run_case(case, work):
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    db, custody = work / "case.sqlite", work / "custody"
    regfile = work / "registry.json"; regfile.write_text(json.dumps(case["registry"]), encoding="utf-8")
    S.DEFAULT_LOT_REGISTRY = regfile
    log, refused = [], {}
    app = Manufacturing(db)
    motors = [m["motor"] for m in case["motors"]]
    for m in motors:
        app.create_unit(m)
    root = work / "root.json"
    app.snapshot(); publish_candidate(root, export_anchor(app)); app.close()
    chain = [root]; app = Manufacturing(db)
    try:
        return _execute(case, app, db, custody, regfile, chain, log, refused)
    finally:
        S.DEFAULT_LOT_REGISTRY = None


def _execute(case, app, db, custody, regfile, chain, log, refused):
    for i, st in enumerate(case.get("steps", [])):
        do = st["do"]
        try:
            if do == "assemble":
                lots_ = st["lots"]
                if st.get("route", "service") == "bypass":
                    bypass_assemble(app, st["motor"], lots_.get("DE"), lots_.get("NDE"), json.loads(regfile.read_text(encoding="utf-8")))
                elif "interruptAfterEvent" in st:
                    with Interrupt(app, st["interruptAfterEvent"]):
                        app.assemble(st["motor"], lots_.get("DE"), lots_.get("NDE"))
                else:
                    app.assemble(st["motor"], lots_.get("DE"), lots_.get("NDE"))
            elif do == "replace":
                if "interruptAfterEvent" in st:
                    with Interrupt(app, st["interruptAfterEvent"]):
                        app.replace(st["motor"], st["lot"], st["slot"])
                else:
                    app.replace(st["motor"], st["lot"], st["slot"])
            elif do == "sighting":
                app.observe(st["motor"], st["label"], st["slot"])
            elif do == "ship":
                app.record_historical_shipment_fixture(st["motor"])
            elif do == "announce_recall":
                app.announce(case["recall"]["lot"], case["recall"].get("affectedSlots"))
            elif do == "edit_registry":
                app.close(); regfile.write_text(json.dumps(st["registry"]), encoding="utf-8"); app = Manufacturing(db)
            elif do == "accept_checkpoint":
                app.close()
                prop = checkpoint_ops.propose(db, chain[-1], custody, chain[-2] if len(chain) > 1 else None)
                if prop["status"] != checkpoint_ops.STATUS_PROPOSED:
                    log.append(dict(step=i, do=do, result=prop["status"]))
                else:
                    every = bool(st.get("acknowledgeAll"))       # the operator acknowledges everything the review asks for; identity-unsafe rows are still refused
                    acks = prop["review"]["requiresAcknowledgement"] if every else st.get("acknowledgeMotors", [])
                    try:
                        regack = prop["review"]["registry"]["digest"] if (st.get("acknowledgeRegistryChange") or every) else None
                        rec = checkpoint_ops.accept(db, chain[-1], custody, Path(prop["candidate"]), "benchmark-runner", prop["candidateSha256"], acks, acknowledge_registry=regack)
                        chain.append(Path(rec["accepted"])); result = "ACCEPTED"
                    except SystemExit as exc:
                        refused[i] = str(exc)[:160]; result = "REFUSED"
                    entry = dict(step=i, do=do, result=result)
                    if st.get("expectAccepted") is not None:
                        entry["expectAccepted"] = bool(st["expectAccepted"]); entry["acceptAgrees"] = (result == "ACCEPTED") == bool(st["expectAccepted"])
                    log.append(entry)
                app = Manufacturing(db)
        except (ValidationFailure, LedgerBlocked) as exc:
            refused[i] = type(exc).__name__ + ": " + str(exc)[:160]; log.append(dict(step=i, do=do, result="CAPTURE_REFUSED"))
    out = dict(caseId=case["caseId"], split=case.get("split"), steps=log, refusedSteps=refused, motors={})
    try:
        prev = chain[-2] if len(chain) > 1 else None
        snap = app.snapshot(trusted_anchor=TrustedAnchor(chain[-1], prev))
        out["checkpoint"] = snap["checkpoint"]["state"]; out["registryBinding"] = snap["lotIdentity"]["registryBinding"]["status"]
        for m in case["motors"]:
            mid = m["motor"]
            dec = next(iter(snap["decisions"][mid].values()))["current"] if snap["decisions"].get(mid) else None
            eligible = snap["eligibility"][mid]["currentReleaseEligible"]
            reasons = sorted({f["reason"] for f in dec["identityGuard"]["findings"]} | {f["reason"] for f in dec["integrityGuard"]["findings"]}) if dec else []
            exp = m["expected"]
            out["motors"][mid] = dict(eligible=eligible, held=not eligible, reasons=reasons, expectedMustHold=exp["mustHold"], agrees=(not eligible) == exp["mustHold"],
                                      expectedCaptureRefusedAtStep=exp.get("captureRefusedAtStep"), contested=exp.get("contested", False))
            if exp.get("captureRefusedAtStep") is not None:
                out["motors"][mid]["captureRefusalAgrees"] = exp["captureRefusedAtStep"] in refused
    except Exception as exc:                                  # a view that is withheld is reported as such, never as a pass
        out["checkpoint"] = "WITHHELD:" + type(exc).__name__ + ":" + getattr(exc, "code", "")
        for m in case["motors"]:
            out["motors"][m["motor"]] = dict(eligible=False, held=True, reasons=[], expectedMustHold=m["expected"]["mustHold"], agrees=m["expected"]["mustHold"], contested=m["expected"].get("contested", False), withheld=True)
    finally:
        app.close()
    return out


def main():
    cases_dir, out_path = Path(sys.argv[1]), Path(sys.argv[2]); sample = "--sample" in sys.argv
    results = []
    for f in sorted(cases_dir.glob("*.json")):
        case = json.loads(f.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as t:
            results.append(run_case(case, t))
    agree = sum(1 for r in results for m in r["motors"].values() if m["agrees"]); total = sum(len(r["motors"]) for r in results)
    unsafe = [r["caseId"] + ":" + k for r in results for k, m in r["motors"].items() if m["expectedMustHold"] and m["eligible"]]
    accept_disagree = [r["caseId"] + f"@{s['step']}" for r in results for s in r["steps"] if s.get("acceptAgrees") is False]
    payload = dict(sampleSelfCheckOnly=sample, acceptDisagreements=accept_disagree, independentEvidence=False if sample else "per pre-registration only", cases=len(results), motors=total, agree=agree,
                   expectedHoldButEligible=unsafe, results=results)
    out_path.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "results"}, indent=1))


if __name__ == "__main__":
    main()
