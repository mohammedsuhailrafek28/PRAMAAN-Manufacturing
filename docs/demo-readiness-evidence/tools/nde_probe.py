"""Review probe of the known Phase 3 critical defect: recall of a lot installed ONLY in the NDE position, scope unspecified.
Usage: python nde_probe.py BASE_URL [anchored]"""
import json, sys, urllib.request, urllib.error
B = sys.argv[1]
def req(m, p, body=None, tok=None):
    h = {"Content-Type": "application/json"}
    if tok: h.update({"X-Pramaan-Token": tok, "Origin": B})
    r = urllib.request.Request(B + p, data=json.dumps(body).encode() if body is not None else None, method=m, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=30) as x: return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"{}")
tok = req("GET", "/api/session")[1]["token"]
print(req("POST", "/api/units", {"serial": "MTR-29001"}, tok)[0], "register")
print(req("POST", "/api/units/MTR-29001/assemble", {"deLot": "BR-310", "ndeLot": "BR-901", "identity": "SERIAL"}, tok)[0], "assemble DE=BR-310 NDE=BR-901")
print(req("POST", "/api/units/MTR-29001/ship", {}, tok)[0], "ship")
print(req("POST", "/api/recalls", {"lot": "BR-901"}, tok)[0], "announce BR-901, scope unspecified (NDE-only exposure)")
s, snap = req("GET", "/api/snapshot")
for pol, b in snap["decisions"]["MTR-29001"].items():
    d = b["current"]; print("RESULT", d["evidenceFinding"], d["operationalAction"], d["reasonCodes"])
print("recall affectedSlots:", snap["recall"].get("affectedSlots"))
