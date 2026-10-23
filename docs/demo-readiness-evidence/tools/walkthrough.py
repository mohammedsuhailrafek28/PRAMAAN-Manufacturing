"""Synthetic end-to-end walkthrough driver (review tooling, not application code).
Usage: python walkthrough.py BASE_URL OUT_JSON
Drives only the documented HTTP API with the loopback session token. Records every call, status, elapsed ms and a
summary of what came back. Never retries around a refusal and never fabricates a result: a refusal is recorded as such.
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE, OUT = sys.argv[1].rstrip("/"), sys.argv[2]
LOG = []
TOKEN = None


def call(step, method, path, body=None, note=""):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if method == "POST":
        headers["X-Pramaan-Token"] = TOKEN or ""
        headers["Origin"] = BASE
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    ms = (time.perf_counter() - t) * 1000
    try:
        js = json.loads(raw)
    except Exception:
        js = None
    LOG.append(dict(step=step, method=method, path=path, body=body, status=status, ms=round(ms, 1), note=note,
                    error=(js or {}).get("error") if isinstance(js, dict) else None))
    return status, js


def decisions(snap):
    out = {}
    for unit in snap.get("units", []):
        uid = unit["unitId"]
        for pol, bundle in (snap.get("decisions", {}).get(uid) or {}).items():
            d = bundle["current"]
            out[uid] = dict(finding=d["evidenceFinding"], action=d["operationalAction"], reasons=d["reasonCodes"], review=d["reviewRequired"])
    return out


def envelope_summary(snap):
    if not isinstance(snap, dict):
        return None
    return dict(freshness=(snap.get("freshness") or {}).get("status"), checkpointState=(snap.get("checkpoint") or {}).get("state"),
                h2=(snap.get("checkpoint") or {}).get("h2"), eligibility={k: v.get("currentReleaseEligible") for k, v in (snap.get("eligibility") or {}).items()} or None)


results = {}
s, sess = call("0 session", "GET", "/api/session")
TOKEN = (sess or {}).get("token")
s, snap = call("0 initial snapshot", "GET", "/api/snapshot")
results["initialEnvelope"] = envelope_summary(snap)

MOTORS = [("MTR-27001", "BR-901", "BR-310", "SERIAL"), ("MTR-27002", "BR-901", "BR-901", "LOT"),
          ("MTR-27003", "BR-310", "BR-312", "SERIAL"), ("MTR-27004", "BR-901", "BR-312", "SERIAL")]
ok = True
for serial, de, nde, ident in MOTORS:
    s, _ = call("1 register motor", "POST", "/api/units", dict(serial=serial, title=f"Synthetic IE3 motor {serial}"))
    ok &= s == 200
if ok:
    for serial, de, nde, ident in MOTORS:   # material allocation + bearing manufacture are emitted inside assemble
        s, _ = call("2-4 allocate+manufacture+install DE/NDE", "POST", f"/api/units/{serial}/assemble", dict(deLot=de, ndeLot=nde, identity=ident))
    for serial, *_ in MOTORS:
        call("5 shipment capture", "POST", f"/api/units/{serial}/ship", {})
    call("6 announce defective lot (DE only)", "POST", "/api/recalls", dict(lot="BR-901", affectedSlots=["DE"]))
    s, snap = call("6b snapshot after recall", "GET", "/api/snapshot")
    results["afterRecall"] = dict(envelope=envelope_summary(snap), decisions=decisions(snap or {}))
    s, snap = call("7 replace DE bearing on MTR-27001", "POST", "/api/units/MTR-27001/replace", dict(lot="BR-312"))
    s, snap = call("7b snapshot after replacement", "GET", "/api/snapshot")
    results["afterReplace"] = dict(envelope=envelope_summary(snap), decisions=decisions(snap or {}))
    call("8 late untrusted observation on MTR-27003 (BR-901)", "POST", "/api/units/MTR-27003/observe", dict(lot="BR-901"))
    s, snap = call("8b snapshot after observation", "GET", "/api/snapshot")
    results["afterObservation"] = dict(envelope=envelope_summary(snap), decisions=decisions(snap or {}),
                                       notifications=len((snap or {}).get("notifications") or []))
    call("9 genealogy read", "GET", "/api/motors/MTR-27001/genealogy")
    call("9 provenance read", "GET", "/api/motors/MTR-27001/provenance")
    call("9 lot investigation read", "GET", "/api/lots/BR-901/investigation")
# Not-implemented probes: each should be refused or absent; recorded as found.
call("probe: EPCIS capture over HTTP", "POST", "/api/capture", {"type": "EPCISDocument"})
call("probe: material receipt command", "POST", "/api/materials", {"lot": "STEEL-1"})
call("probe: second recall (immutable-scope limit)", "POST", "/api/recalls", dict(lot="BR-310", affectedSlots=["DE"]))
call("probe: unknown motor", "GET", "/api/motors/MTR-NOPE/genealogy")

json.dump(dict(base=BASE, results=results, calls=LOG), open(OUT, "w"), indent=1)
refused = [c for c in LOG if c["status"] >= 400 and not c["step"].startswith("probe")]
print(f"calls={len(LOG)} refused_non_probe={len(refused)}")
for c in LOG:
    print(f"{c['status']:>3} {c['ms']:>8}ms {c['method']:<4} {c['path']:<42} {c['step']}" + (f"  !! {c['error']}" if c["error"] else ""))
print(json.dumps(results, indent=1)[:3000])
