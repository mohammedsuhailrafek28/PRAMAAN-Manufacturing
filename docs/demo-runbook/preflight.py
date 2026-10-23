"""Demo preflight (review tooling, not application source). Run from the root of the demo checkout with its venv:

    .venv/Scripts/python.exe <path>/preflight.py scratch
    .venv/Scripts/python.exe <path>/preflight.py server http://127.0.0.1:4173

`scratch` proves, on disposable synthetic databases created through the application's own service layer, that the recall
policy is applied to the DE and NDE positions as declared. It never touches the demo database.
`server` checks the running demo server over GET only: anchored freshness, recall scope, the five seeded motors and the
four page entry points. Exit code 0 means every check passed; any failure prints FAIL and exits 1.
No check can be bypassed by a flag and nothing is faked: a failed check is reported as failed.
"""
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
FAILS = []


def check(ok, what):
    print(("PASS  " if ok else "FAIL  ") + what)
    if not ok:
        FAILS.append(what)


def scratch():
    from application.service import Manufacturing
    cases = [  # scope argument, expected affectedSlots, {motor: (DE lot, NDE lot, expected finding, expected action)}
        (None, ["DE", "NDE"], {"MTR-91001": ("BR-901", "BR-310", "AFFECTED", "RECALL_HOLD"),
                               "MTR-91002": ("BR-310", "BR-901", "AFFECTED", "RECALL_HOLD"),
                               "MTR-91003": ("BR-310", "BR-312", "EXCLUDED_WITH_EVIDENCE", "RELEASE_ELIGIBLE")}),
        (["DE"], ["DE"], {"MTR-91001": ("BR-901", "BR-310", "AFFECTED", "RECALL_HOLD"),
                          "MTR-91002": ("BR-310", "BR-901", "EXCLUDED_WITH_EVIDENCE", "RELEASE_ELIGIBLE"),
                          "MTR-91003": ("BR-310", "BR-312", "EXCLUDED_WITH_EVIDENCE", "RELEASE_ELIGIBLE")}),
        (["NDE"], ["NDE"], {"MTR-91001": ("BR-901", "BR-310", "EXCLUDED_WITH_EVIDENCE", "RELEASE_ELIGIBLE"),
                            "MTR-91002": ("BR-310", "BR-901", "AFFECTED", "RECALL_HOLD"),
                            "MTR-91003": ("BR-310", "BR-312", "EXCLUDED_WITH_EVIDENCE", "RELEASE_ELIGIBLE")}),
    ]
    for scope, slots, motors in cases:
        label = "scope omitted" if scope is None else f"scope {scope}"
        with tempfile.TemporaryDirectory() as d:
            m = Manufacturing(Path(d) / "preflight.sqlite")
            try:
                for serial, (de, nde, *_ ) in motors.items():
                    m.create_unit(serial)
                    m.assemble(serial, de, nde, "SERIAL")
                    m.ship(serial)
                try:
                    policy = m.announce("BR-901") if scope is None else m.announce("BR-901", scope)
                except Exception as exc:                       # e.g. a version without explicit scope support
                    check(False, f"[{label}] announce raised {type(exc).__name__}: {exc}")
                    continue
                check(policy["affectedSlots"] == slots, f"[{label}] policy affectedSlots == {slots} (got {policy['affectedSlots']})")
                snap = m.snapshot()
                for serial, (de, nde, finding, action) in motors.items():
                    cur = next(iter(snap["decisions"][serial].values()))["current"]
                    check((cur["evidenceFinding"], cur["operationalAction"]) == (finding, action),
                          f"[{label}] {serial} DE={de} NDE={nde} -> {finding}/{action} (got {cur['evidenceFinding']}/{cur['operationalAction']})")
            finally:
                m.close()


def server(base):
    def get(path):
        with urllib.request.urlopen(base + path, timeout=15) as r:
            return r.status, r.read()
    s, raw = get("/api/snapshot")
    snap = json.loads(raw)
    fr = snap.get("freshness") or {}
    check(s == 200 and fr.get("status") == "VERIFIED_ANCHORED_SYNTHETIC", f"snapshot freshness is VERIFIED_ANCHORED_SYNTHETIC (got {fr.get('status')})")
    check(fr.get("maxAgeSeconds") == 5, "lease is 5 seconds")
    rc = snap["recall"]
    check(rc["affectedLots"] == ["BR-204"] and rc["affectedSlots"] == ["DE"], f"seeded recall is BR-204, DE explicit (got {rc['affectedLots']} {rc['affectedSlots']})")
    check(rc.get("scopeDeclaration") == "EXPLICIT_POSITIONS", f"scopeDeclaration EXPLICIT_POSITIONS (got {rc.get('scopeDeclaration')})")
    ids = sorted(u["unitId"] for u in snap["units"])
    check(ids == [f"MTR-2600{i}" for i in range(1, 6)], f"five seeded motors present (got {ids})")
    want = {"MTR-26001": ("AFFECTED", "RECALL_HOLD"), "MTR-26002": ("UNRESOLVED", "RECALL_HOLD"), "MTR-26003": ("EXCLUDED_WITH_EVIDENCE", "RELEASE_ELIGIBLE"),
            "MTR-26004": ("UNRESOLVED", "RECALL_HOLD"), "MTR-26005": ("UNRESOLVED", "RECALL_HOLD")}
    for u, (f, a) in want.items():
        cur = next(iter(snap["decisions"][u].values()))["current"]
        check((cur["evidenceFinding"], cur["operationalAction"]) == (f, a), f"{u} -> {f}/{a} (got {cur['evidenceFinding']}/{cur['operationalAction']})")
    check(len(snap.get("notifications") or []) == 1, "one pending notification obligation (MTR-26005)")
    for page in ("/index.html", "/passport.html", "/investigation.html", "/impact.html"):
        s, _ = get(page)
        check(s == 200, f"GET {page} -> 200")


mode = sys.argv[1] if len(sys.argv) > 1 else ""
if mode == "scratch":
    scratch()
elif mode == "server" and len(sys.argv) > 2:
    server(sys.argv[2].rstrip("/"))
else:
    sys.exit(__doc__)
print("\nPREFLIGHT " + ("FAILED: " + "; ".join(FAILS) if FAILS else "PASSED"))
sys.exit(1 if FAILS else 0)
