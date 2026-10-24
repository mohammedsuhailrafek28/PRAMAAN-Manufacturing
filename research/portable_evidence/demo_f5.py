"""Offline demo of F5 portable evidence packages: one recalled motor, three recipients, one success per recipient and negative cases. Synthetic data, disposable temp ledger.
Independent of the frozen v1.1 demo. Run from the repo root with the F5 venv:  python -B research/portable_evidence/demo_f5.py [WORKDIR]
Every verification below uses only application/evidence_verify.py and the pinned public key file (no ledger, no server, no network)."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from application import evidence_package as P
from application import evidence_verify as V
from application import test_evidence_package as T


def banner(text):
    print("\n" + "=" * 100 + "\n" + text + "\n" + "=" * 100)


def main(work):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    db, anchor, private, public = T.build_world(work)
    T.FIXTURE.update(db=db, anchor=anchor, private=private, public=public)
    banner("ISSUER SIDE: recalled motor MTR-DEMO-2 (affected lot BR-204, DE bearing); checkpoint is ANCHORED_CURRENT; issuer key pinned out of band")
    packages = {}
    for profile, recipient in (("customer", T.CUSTOMER), ("supplier", T.SUPPLIER), ("auditor", T.AUDITOR)):
        token = P.issue(database=db, anchor=anchor, motor=T.AFFECTED, recipient=recipient, profile=profile, key_path=private, authorize_event_row=profile == "auditor")
        (work / f"{profile}.sdjwt").write_text(token, encoding="utf-8")
        packages[profile] = (token, recipient)
        print(f"  issued {profile:9s} -> {recipient:28s} {len(token):6d} bytes")
    banner("SUCCESS 1/3: CUSTOMER verifies offline (no supplier, lot or other-motor detail exists in the file)")
    print(V.render(V.verify(packages["customer"][0], issuer_key=public, recipient=T.CUSTOMER)))
    banner("SUCCESS 2/3: SUPPLIER verifies offline (lot and supplier, no motor or customer identity)")
    print(V.render(V.verify(packages["supplier"][0], issuer_key=public, recipient=T.SUPPLIER)))
    banner("SUCCESS 3/3: AUDITOR verifies offline WITH the checkpoint (opened event row re-hashes to the checkpoint's row digest)")
    print(V.render(V.verify(packages["auditor"][0], issuer_key=public, recipient=T.AUDITOR, checkpoint=anchor)))
    banner("NEGATIVE 1: the customer package presented by/for the supplier (audience mismatch)")
    print(V.render(V.verify(packages["customer"][0], issuer_key=public, recipient=T.SUPPLIER)).splitlines()[0])
    banner("NEGATIVE 2: one disclosed value edited after signing (motorSerial -> MTR-OTHER-9)")
    token = packages["customer"][0]
    h, p, s, d = T.parts(token)
    edited = []
    for x in d:
        salt, name, value = T.decode_disclosure(x)
        edited.append(V.b64u(json.dumps([salt, name, "MTR-OTHER-9" if name == "motorSerial" else value], separators=(",", ":")).encode()))
    print(V.render(V.verify(T.reassemble(h, p, s, edited), issuer_key=public, recipient=T.CUSTOMER)).splitlines()[0])
    banner("NEGATIVE 3: signed by a different key (attacker)")
    attacker_private, attacker_public = P.keygen(work / "attacker")
    forged = T.forge(claims=T.GOOD_CUSTOMER, key=attacker_private, now=T.NOW)
    print(V.render(V.verify(forged, issuer_key=public, recipient=T.CUSTOMER, now=T.NOW)).splitlines()[0])
    banner("NEGATIVE 4: expired package (verified one day after issue)")
    print(V.render(V.verify(packages["customer"][0], issuer_key=public, recipient=T.CUSTOMER, now=p["exp"] + 86400)).splitlines()[0])
    banner("NEGATIVE 5: auditor claim (lot) contradicts the opened ledger row bound to the checkpoint")
    forged_auditor = T.forge(claims={**V.verify(packages["auditor"][0], issuer_key=public)["claims"], "lot": "BR-310"}, profile="auditor", aud=T.AUDITOR, now=T.NOW)
    print(V.render(V.verify(forged_auditor, issuer_key=public, recipient=T.AUDITOR, checkpoint=anchor, now=T.NOW)).splitlines()[0])
    banner("ISSUER REFUSAL: a release-eligible motor (MTR-DEMO-1) gets no package: packages are never clearance")
    try:
        P.issue(database=db, anchor=anchor, motor=T.CLEAN, recipient=T.CUSTOMER, profile="customer", key_path=private)
    except P.IssuanceRefused as exc:
        print("  REFUSED:", exc)
    banner("PRIVACY: bytes each recipient holds (everything decoded) searched for forbidden strings")
    for profile, forbidden in (("customer", ("BR-204", "Northstar", "SUP-", "MTR-DEMO-1", "headHash")), ("supplier", ("MTR-", T.CUSTOMER, "sourceHeads"))):
        h, p, s, d = T.parts(packages[profile][0])
        text = packages[profile][0] + json.dumps(p) + "".join(json.dumps(T.decode_disclosure(x)) for x in d)
        print(f"  {profile:9s} leaks:", [f for f in forbidden if f in text] or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="f5demo-")))
