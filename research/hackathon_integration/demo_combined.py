"""Combined F5 + F6 demo on ONE synthetic evidence set (disposable temp state, loopback-free: no sockets at all). ~5 minutes.
Run from the repo root with the pinned venv:  python -B research/hackathon_integration/demo_combined.py [WORKDIR]   (WORKDIR new/empty)
Storyline: (1) factory A recalls bearing lot BR-204 and counts affected motors, (2) genealogy from the same ledger, (3) recipient-scoped F5 packages verified offline,
(4) supplier S sends a signed F6 alert; A (already recalled) and B (new adoption) answer with counts only.
Scripted here, done by people in real use: operator confirmations and checkpoint acknowledgements. Local demo keys are NOT independent company authentication."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from application import evidence_package as P, evidence_verify as V
from application import test_federation as T
from application.federation import TRUST_NOTICE, staging as S
from application.federation.lotmap import map_lot
from application.federation.supplier import render_text
from application.service import Manufacturing

CUSTOMER, SUPPLIER_R, AUDITOR = "urn:demo:customer:pumpco", "urn:demo:supplier:northstar-bearings", "urn:demo:auditor:regulator"


def banner(text):
    print("\n" + "=" * 110 + "\n" + text + "\n" + "=" * 110)


def main(work):
    work = Path(work)
    banner("LIMITS (read first): " + TRUST_NOTICE + "  Not production-ready; synthetic data; acknowledgements and confirmations below are scripted.")
    world = S.stage_world(work)
    A, B = world["a"], world["b"]
    f5_private, f5_public = P.keygen(work / "f5keys")

    banner("1. RECALL (v1.1 behaviour): factory A announces a recall of its bearing lot BR-204, drive end; existing checkpoint cycle anchors the ledger")
    app = Manufacturing(A["database"], lot_registry=A["registry"])
    try:
        app.announce("BR-204", ["DE"]); app.snapshot()
    finally:
        app.close()
    a_anchor, a_prev = S.checkpoint_cycle(A, A["anchor"], None, "scripted-custodian")
    snap, held = T.snapshot_held(A, a_anchor, a_prev)
    print(f"  checkpoint state: {snap['checkpoint']['state']}; motors held: {sorted(held)}; clean motors stay unaffected: {sorted(set(snap['eligibility']) - held)}")

    banner("2. GENEALOGY from the same ledger: why each held motor is held (frozen evaluator output, not recomputed here)")
    for motor, per_policy in sorted(snap["decisions"].items()):
        for policy_id, entry in per_policy.items():
            cur = entry["current"]
            print(f"  {motor}: evidenceFinding={cur['evidenceFinding']} operationalAction={cur['operationalAction']} reasons={cur['reasonCodes']}")
        for c in snap["components"]:
            if c["unitId"] == motor and not c["removedAt"]:
                print(f"      installed {c['slot']} bearing {c['serial']} part {c['part']} lot {c['lot']} (registry {c['registry']['status']}) at {c['installedAt']}")
        for l in snap["lineage"]:
            if l["unitId"] == motor and l["lot"] == "BR-204":
                print(f"      lineage: supplier {l['supplierId']} raw material {l['rawMaterialLot']} ({l['provenanceAssurance']})")

    banner("3. F5 PORTABLE EVIDENCE: one recalled motor, three recipient-scoped packages; verified OFFLINE with only the issuer's public key (informational, never clearance)")
    motor = "MTR-A-001"
    tokens = {}
    for profile, recipient in (("customer", CUSTOMER), ("supplier", SUPPLIER_R), ("auditor", AUDITOR)):
        tokens[profile] = P.issue(database=A["database"], anchor=a_anchor, previous_anchor=a_prev, motor=motor, recipient=recipient, profile=profile, key_path=f5_private,
                                  lot_registry=A["registry"], authorize_event_row=profile == "auditor")
        (work / f"{profile}.sdjwt").write_text(tokens[profile], encoding="utf-8")
        print(f"  issued {profile:9s} for {recipient:36s} {len(tokens[profile]):6d} bytes")
    print(V.render(V.verify(tokens["customer"], issuer_key=f5_public, recipient=CUSTOMER)))
    print(V.render(V.verify(tokens["supplier"], issuer_key=f5_public, recipient=SUPPLIER_R)).splitlines()[0])
    print(V.render(V.verify(tokens["auditor"], issuer_key=f5_public, recipient=AUDITOR, checkpoint=a_anchor)).splitlines()[0])
    print("  NEGATIVE (wrong audience):", V.render(V.verify(tokens["customer"], issuer_key=f5_public, recipient=SUPPLIER_R)).splitlines()[0])
    _, attacker_public = P.keygen(work / "attacker")
    print("  NEGATIVE (wrong issuer key):", V.render(V.verify(tokens["customer"], issuer_key=attacker_public, recipient=CUSTOMER)).splitlines()[0])
    try:
        P.issue(database=A["database"], anchor=a_anchor, previous_anchor=a_prev, motor="MTR-A-002", recipient=CUSTOMER, profile="customer", key_path=f5_private, lot_registry=A["registry"])
    except P.IssuanceRefused as exc:
        print("  ISSUER REFUSAL for the clean motor MTR-A-002 (packages are never clearance):", exc)

    banner("4. F6 FEDERATED RECALL: supplier S signs ONE alert for ITS label NSB-204; factories A and B authenticate, map with their OWN registries, and operators adopt")
    sup = T.supplier_for(world)
    path, body = T.issue(sup)
    nodes = {"a": T.node_for(world, "a"), "b": T.node_for(world, "b")}
    nodes["a"].set_checkpoint(a_anchor, a_prev)
    names = {"a": "Aster Motors (A)", "b": "Kaveri Drives (B)"}
    digests = {}
    for k, node in nodes.items():
        r = node.receive(path, T.NOW)
        digests[k] = r["alertHash"]
        m = map_lot(node.registry(), body["lot"])
        print(f"  {names[k]}: accepted={r['accepted']} status={r['status']}; label NSB-204 -> local lot {m.canonical} (never sent back)")
    wrong = nodes["b"].adopt(body["alertId"], "op", "000000000000", T.NOW)
    print(f"  wrong confirmation refused: {wrong['reason']}")
    before = T.ledger_state(A)[0]
    ra = nodes["a"].adopt(body["alertId"], "scripted-op-a", digests["a"][:12], T.NOW)
    print(f"  A adopts: adopted={ra['adopted']}; A already recalled BR-204 on its own, so the ledger is unchanged: {T.ledger_state(A)[0] == before}")
    rb = nodes["b"].adopt(body["alertId"], "scripted-op-b", digests["b"][:12], T.NOW)
    print(f"  B adopts: adopted={rb['adopted']}; B's response while its checkpoint is stale: {nodes['b'].respond(body['alertId'], T.NOW)['body']['counts']}")
    b_anchor, b_prev = S.checkpoint_cycle(B, B["anchor"], None, "scripted-custodian")
    nodes["b"].set_checkpoint(b_anchor, b_prev)

    banner("5. Counts-only responses (no serials, lots, customers) and the supplier's board")
    for k, node in nodes.items():
        resp = node.respond(body["alertId"], T.NOW)
        print(f"  {names[k]}: {resp['status']} {json.dumps(resp['body']['counts'])}")
    board = sup.board([p for k in "ab" for p in sorted((world[k]["root"] / "outbox").glob("*.json"))])
    print(render_text(board))

    banner("6. Same evidence set, other direction: B's recalled motor also gets an F5 package; B's guard-only hold is stated, not hidden")
    for motor_b in ("MTR-B-001", "MTR-B-003"):
        token = P.issue(database=B["database"], anchor=b_anchor, previous_anchor=b_prev, motor=motor_b, recipient=CUSTOMER, profile="customer", key_path=f5_private, lot_registry=B["registry"])
        claims = V.verify(token, issuer_key=f5_public, recipient=CUSTOMER)["claims"]
        print(f"  {motor_b}: evidenceFinding={claims['evidenceFinding']} operationalAction={claims['operationalAction']}")

    banner("7. Unmapped lot: a second alert for NSB-999 is refused by both factories, never reported as 'not affected'")
    p2, b2 = T.issue(sup, supplier_lot="NSB-999", alert_id="ALERT-UNMAPPED", text="second alert, unknown lot")
    for k, node in nodes.items():
        r = node.receive(p2, T.NOW)
        print(f"  {names[k]}: adopt -> {node.adopt(b2['alertId'], 'op', r['alertHash'][:12], T.NOW)['reason']}")

    banner("8. Safety recap")
    print("  * F5 packages are informational: signed, recipient-scoped, never issued for clean motors, no release-eligibility path.")
    print("  * F6 messages only add holds after a named operator; no message clears a hold. Neither feature writes the ledger except F6's operator-gated existing announce.")
    print("  * Same-host custody and local demo keys: NOT independent verification; physical product identity is not verified.")
    for node in nodes.values():
        node.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="combo-")))
