"""Shared harness: drive a Manufacturing-like class on a disposable synthetic DB and report every layer. Loopback/in-process only."""
import json
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lotid  # noqa: E402,F401  (sets sys.path for the application)
from application.service import Manufacturing  # noqa: E402
from application.anchors import TrustedAnchor, export_anchor, publish_candidate  # noqa: E402
from lotid import StrategyA, StrategyB  # noqa: E402

CLASSES = {"BASELINE_V1_0": Manufacturing, "A": StrategyA, "B": StrategyB}
MOTOR, RECALLED, SAFE = "MTR-90001", "BR-204", "BR-310"

# (name, value, valid-registered-unaffected?)
LOTS = [
    ("missing", None), ("empty", ""), ("whitespace", "   "), ("UNKNOWN", "UNKNOWN"), ("unknown", "unknown"), ("N/A", "N/A"),
    ("sentinel-dash", "-"), ("sentinel-0", "0"),
    ("recalled-lowercase", "br-204"), ("recalled-trailing-space", "BR-204 "), ("recalled-letterO", "BR-2O4"),
    ("recalled-en-dash", "BR–204"), ("recalled-zero-width", "BR-204​"), ("recalled-no-dash", "BR204"),
    ("recalled-transposed", "BR-240"), ("recalled-fullwidth", "ＢＲ-204"),
    ("different-wellformed-unregistered", "BR-999"), ("different-malformed", "foo bar"),
    ("registered-future-effective", "BR-555"), ("registered-withdrawn", "BR-666"),
    ("registered-alias-of-recalled", "NSB-204"),
    ("registered-unaffected", SAFE), ("registered-unaffected-2", "BR-401"), ("registered-recalled", RECALLED),
]
SCOPES = [("scoped DE", ["DE"]), ("scoped NDE", ["NDE"]), ("unspecified", None)]
VALID_UNAFFECTED = {"registered-unaffected", "registered-unaffected-2"}
VALID_RECALLED = {"registered-recalled"}


def err(e):
    return f"{type(e).__name__}: {e}"


def current_snapshot(app, d):
    app.snapshot()
    a = Path(d) / "a.json"
    publish_candidate(a, export_anchor(app))
    return app.snapshot(trusted_anchor=TrustedAnchor(a))


def summarize(snap):
    cur = next(iter(snap["decisions"][MOTOR].values()))["current"]
    return dict(checkpoint=snap["checkpoint"]["state"], eligible=snap["eligibility"][MOTOR]["currentReleaseEligible"],
                finding=cur.get("evidenceFinding"), action=cur.get("operationalAction"), reasonCodes=cur.get("reasonCodes"),
                guard=(snap.get("identityGuard", {}).get("motors", {}).get(MOTOR) and [g["reason"] for g in snap["identityGuard"]["motors"][MOTOR]]))


def case(cls, path, lot, slot, scope, **kw):
    with tempfile.TemporaryDirectory() as d:
        app = cls(Path(d) / "m.sqlite", **kw)
        r = dict(path=path, slot=slot, scope=scope)
        try:
            app.create_unit(MOTOR)
            try:
                if path == "assemble":
                    de, nde = (lot, SAFE) if slot == "DE" else (SAFE, lot)
                    app.assemble(MOTOR, de, nde)
                elif path == "replace":
                    app.assemble(MOTOR, RECALLED, SAFE)
                    app.replace(MOTOR, lot)
                elif path == "observe":
                    app.assemble(MOTOR, SAFE, SAFE)
                    app.observe(MOTOR, lot)
                r["capture"] = "ACCEPTED"
            except Exception as e:
                r["capture"] = "REJECTED " + err(e)
            r["eventsAfterCapture"] = len(app.events(MOTOR))
            if path != "assemble" or r["capture"] == "ACCEPTED":
                app.ship(MOTOR)
            app.announce(RECALLED, dict(SCOPES)[scope])
            r["result"] = summarize(current_snapshot(app, d))
        except Exception as e:
            r["error"] = err(e)
        finally:
            app.close()
        return r


def run_matrix(cls_name, **kw):
    cls, out = CLASSES[cls_name], []
    for sname, scope in SCOPES:
        for lname, lot in LOTS:
            for slot in ("DE", "NDE"):
                out.append(case(cls, "assemble", lot, slot, sname, **kw) | dict(lotCase=lname, lot=repr(lot)))
    for sname, scope in (SCOPES[0], SCOPES[2]):
        for lname, lot in LOTS:
            for path in ("replace", "observe"):
                out.append(case(cls, path, lot, "DE", sname, **kw) | dict(lotCase=lname, lot=repr(lot)))
    return out


def classify(r, strategy="BASELINE_V1_0"):
    """UNSAFE = the unit ends current-eligible although the lot identity is not a valid registered unaffected lot or the lot is recalled in scope.
    Controls: valid registered unaffected must still be eligible when its position is unaffected; registered recalled in scope must hold."""
    name, res = r["lotCase"], r.get("result")
    eligible = bool(res and res["eligible"])
    rejected = str(r.get("capture", "")).startswith("REJECTED")
    if name == "registered-alias-of-recalled" and strategy == "A":
        name = "registered-recalled"          # A resolves the declared alias to the canonical recalled lot
    if rejected and name not in VALID_UNAFFECTED and name not in VALID_RECALLED:
        # nothing entered the record: the unit stays as before (observe path: a valid eligible unit; replace path: held; assemble: no assembly)
        return "OK_SAFE_REJECTED" if (not eligible or r["path"] == "observe") else "UNSAFE_AFTER_REJECT"
    if name in VALID_UNAFFECTED:
        return "OK_UTILITY" if eligible else "FALSE_HOLD"
    if name in VALID_RECALLED:
        scoped_out = (r["scope"] == "scoped DE" and r["slot"] == "NDE" and r["path"] == "assemble") or (r["scope"] == "scoped NDE" and r["slot"] == "DE" and r["path"] == "assemble")
        if r["path"] == "observe":
            return "OK_SAFE" if not eligible else "UNSAFE"
        return ("OK_UTILITY" if eligible else "FALSE_HOLD") if scoped_out else ("OK_SAFE" if not eligible else "UNSAFE")
    # any other lot string: identity not established
    return "UNSAFE" if eligible else ("OK_SAFE_REJECTED" if str(r.get("capture", "")).startswith("REJECTED") else "OK_SAFE_HELD")


def summary(rows, strategy="BASELINE_V1_0"):
    s = {}
    for r in rows:
        s.setdefault(classify(r, strategy), []).append(f'{r["path"]}/{r["slot"]}/{r["scope"]}/{r["lotCase"]}')
    return {k: len(v) for k, v in sorted(s.items())}, {k: v for k, v in s.items() if k in ("UNSAFE", "FALSE_HOLD")}


if __name__ == "__main__":
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    allsum = {}
    for name in CLASSES:
        rows = run_matrix(name)
        counts, bad = summary(rows, name)
        allsum[name] = dict(cases=len(rows), counts=counts, unsafeOrFalseHoldCases=bad)
        (out / f"matrix_{name}.json").write_text(json.dumps(rows, indent=1, sort_keys=True))
        print(name, len(rows), counts)
    (out / "matrix_summary.json").write_text(json.dumps(allsum, indent=1, sort_keys=True))
