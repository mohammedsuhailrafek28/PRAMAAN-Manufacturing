"""Production-path unknown-lot audit (read-only against the frozen source; disposable synthetic databases only).

Drives the real application service (application.service.Manufacturing) on throwaway SQLite files,
the same code the HTTP handlers call. Layers recorded per case:
  (b) service validation, (c) ledger/profile acceptance, (d) pinned evaluator decision,
  (e) checkpoint-aware eligibility (snapshot with a trusted anchor => ANCHORED_CURRENT).
Layer (a), the UI input validation, is recorded statically by unknown_lot_ui_check.py.
usage: python -B unknown_lot_matrix.py OUTDIR
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from application.service import Manufacturing  # noqa: E402
from application.anchors import TrustedAnchor, export_anchor, publish_candidate  # noqa: E402

MOTOR = "MTR-90001"
RECALLED, SAFE = "BR-204", "BR-310"
LOTS = [("missing(None)", None), ("empty", ""), ("whitespace", "   "), ("UNKNOWN", "UNKNOWN"),
        ("unknown(lower)", "unknown"), ("known-unaffected", SAFE), ("known-recalled", RECALLED)]
SCOPES = [("scoped DE", ["DE"]), ("scoped NDE", ["NDE"]), ("scoped DE+NDE", ["DE", "NDE"]), ("unspecified", None)]


def err(e):
    return f"{type(e).__name__}: {e}"


def evaluate(app, d):
    """Current anchored snapshot -> per-slot decision + eligibility."""
    app.snapshot()  # issue publication with the real evaluator
    a = Path(d) / "a.json"
    publish_candidate(a, export_anchor(app))
    snap = app.snapshot(trusted_anchor=TrustedAnchor(a))
    dec = snap["decisions"][MOTOR]
    out = {"checkpoint": snap["checkpoint"]["state"], "eligibility": snap["eligibility"][MOTOR]["currentReleaseEligible"], "decisions": {}}
    for pid, v in dec.items():
        cur = v["current"]
        out["decisions"][pid] = {k: cur.get(k) for k in ("evidenceFinding", "operationalAction", "reasonCodes", "holdReasons", "slotFindings") if k in cur}
        out["decisionKeys"] = sorted(cur)
    return out


def case(path, lot, slot, scope, scope_name):
    with tempfile.TemporaryDirectory() as d:
        app = Manufacturing(Path(d) / "m.sqlite")
        r = {"path": path, "lot": repr(lot), "slot": slot, "recallScope": scope_name}
        try:
            app.create_unit(MOTOR)
            de, nde = (lot, SAFE) if slot == "DE" else (SAFE, lot)
            if path == "assemble":
                try:
                    app.assemble(MOTOR, de, nde)
                    r["capture"] = "ACCEPTED"
                except Exception as e:
                    r["capture"] = "REJECTED " + err(e)
                    r["eventsAfterReject"] = len(app.events(MOTOR))
            elif path == "replace":
                # start from a recalled DE install (HOLD expected), then replace with the case lot
                app.assemble(MOTOR, RECALLED, SAFE)
                try:
                    app.replace(MOTOR, lot)
                    r["capture"] = "ACCEPTED"
                except Exception as e:
                    r["capture"] = "REJECTED " + err(e)
                    r["eventsAfterReject"] = len(app.events(MOTOR))
            elif path == "observe":
                app.assemble(MOTOR, SAFE, SAFE)
                try:
                    app.observe(MOTOR, lot)
                    r["capture"] = "ACCEPTED"
                except Exception as e:
                    r["capture"] = "REJECTED " + err(e)
                    r["eventsAfterReject"] = len(app.events(MOTOR))
            if path != "assemble" or r["capture"] == "ACCEPTED":
                app.ship(MOTOR)
            else:
                app.ship(MOTOR) if False else None
            app.announce(RECALLED, scope)
            r["evaluation"] = evaluate(app, d)
        except Exception as e:
            r["error"] = err(e)
        finally:
            app.close()
        return r


def main(out):
    results = []
    for scope_name, scope in SCOPES:
        for lname, lot in LOTS:
            for slot in ("DE", "NDE"):
                results.append(case("assemble", lot, slot, scope, scope_name) | {"lotCase": lname})
    for scope_name, scope in SCOPES[:1] + SCOPES[3:]:
        for lname, lot in LOTS:
            results.append(case("replace", lot, "DE", scope, scope_name) | {"lotCase": lname})
            results.append(case("observe", lot, "DE", scope, scope_name) | {"lotCase": lname})
    Path(out).mkdir(parents=True, exist_ok=True)
    Path(out, "matrix.json").write_text(json.dumps(results, indent=1, sort_keys=True))
    for r in results:
        ev = r.get("evaluation", {})
        d = next(iter(ev.get("decisions", {}).values()), {})
        print(f'{r["path"]:8s} {r["slot"]:3s} {r["recallScope"]:14s} {r["lotCase"]:17s} capture={str(r.get("capture", "-"))[:60]:60s} '
              f'finding={d.get("evidenceFinding")} action={d.get("operationalAction")} eligible={ev.get("eligibility")} {r.get("error", "")}')


if __name__ == "__main__":
    main(sys.argv[1])
