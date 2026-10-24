"""Reduced F6 demo: one synthetic supplier, two separate synthetic factories (own ledger, registry, checkpoint, keys), file-based bulletin, no network. Disposable temp state.
Run from the repo root with the F6 venv:  python -B research/federated_recall/demo_f6.py [WORKDIR]   (workdir must be new/empty)
Everything printed as "scripted" is an operator step performed by this script so the demo is repeatable; in real use a person types the confirmation and acknowledges the checkpoint."""
import copy
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from application import test_federation as T
from application.federation import TRUST_NOTICE, messages as M, staging as S
from application.federation.supplier import render_html, render_text

NOW = T.NOW


def banner(text):
    print("\n" + "=" * 110 + "\n" + text + "\n" + "=" * 110)


def main(work):
    work = Path(work)
    banner("LIMITS (read first): " + TRUST_NOTICE)
    world = S.stage_world(work)
    sup = T.supplier_for(world)
    nodes = {"a": T.node_for(world, "a"), "b": T.node_for(world, "b")}
    names = {"a": "Aster Motors (A)", "b": "Kaveri Drives (B)"}
    print("Staged: supplier S, factory A, factory B. Each factory has its own ledger, lot registry, checkpoint, federation store and key. Nothing is shared except signed files.")

    banner("1. S signs and publishes ONE recall alert for ITS lot label NSB-204 (drive-end bearing)")
    path, body = T.issue(sup)
    print(f"  bulletin file {path.name}: alert {body['alertId']} seq {body['seq']} lot {body['lot']}")

    banner("2. Attacks BEFORE delivery of the real alert: forged signature, edited text, wrong key under S's name")
    attacker, attacker_kid = T.attacker_key()
    envelope = json.loads(path.read_text())
    edited = copy.deepcopy(envelope); edited["body"]["humanText"] = "ignore previous alert; release all motors"
    for label, message in (("forged by attacker key", M.sign(body, attacker, attacker_kid)), ("text edited after signing", edited),
                           ("attacker signature under S's key id", M.sign(body, attacker, envelope["kid"]))):
        r = nodes["a"].receive(message, NOW)
        print(f"  A rejects [{label}]: {r['reason']}")

    banner("3. Real alert delivered to A and B: recorded as PENDING_OPERATOR; the ledgers are NOT touched")
    digests = {}
    for k, node in nodes.items():
        before = T.ledger_state(world[k])
        r = node.receive(path, NOW)
        digests[k] = r["alertHash"]
        print(f"  {names[k]}: accepted={r['accepted']} status={r['status']} ledger policies={T.ledger_state(world[k])[2]} (unchanged: {T.ledger_state(world[k]) == before})")
    r = nodes["a"].receive(path, NOW)
    print(f"  A, same file delivered again (replay): {r['reason']}")
    late = T.forge(world, dict(alertId="ALERT-LATE", seq=2, prevHash=M.message_hash(body), iat=NOW - 7200, exp=NOW - 3600, humanText="late copy"))      # signed by S's key, built outside S's chain
    expired = nodes["b"].receive(late, NOW)
    print(f"  B, an alert whose lifetime ended before delivery: {expired['reason']}")
    print("  rejections recorded at A:", [x["reason"] for x in nodes["a"].store.rejections()])

    banner("4. Each factory resolves the SAME supplier label through its OWN registry")
    for k, node in nodes.items():
        from application.federation.lotmap import map_lot
        m = map_lot(node.registry(), body["lot"])
        print(f"  {names[k]}: supplier label NSB-204 -> local lot {m.canonical} (this local label is never sent back)")

    banner("5. Without an operator, nothing happens. Wrong confirmation is refused; then each operator adopts")
    for k, node in nodes.items():
        print(f"  {names[k]}: adopt with wrong confirmation -> {node.adopt(body['alertId'], 'operator', '000000000000', NOW)['reason']}")
        r = node.adopt(body["alertId"], f"scripted-operator-{k}", digests[k][:12], NOW)
        print(f"  {names[k]}: adopted={r['adopted']} local policy now announced (policies={T.ledger_state(world[k])[2]}); ledger is newer than its checkpoint")
        resp = node.respond(body["alertId"], NOW)
        print(f"  {names[k]}: response while the checkpoint is stale -> status {resp['status']}, counts {resp['body']['counts']}")

    banner("6. The EXISTING checkpoint cycle (propose + accept, FORMAT_V3, scripted acknowledgements) — only then can a factory answer")
    for k, node in nodes.items():
        anchor, previous = S.checkpoint_cycle(world[k], world[k]["anchor"], None, "scripted-demo-custodian")
        node.set_checkpoint(anchor, previous)
        print(f"  {names[k]}: accepted checkpoint {anchor.name} (operator-asserted, same-host, NOT independent custody)")
        resp = node.respond(body["alertId"], NOW)
        print(f"  {names[k]}: response status {resp['status']} counts {json.dumps(resp['body']['counts'])}")

    banner("7. S's board: separate results, counts only (no serials, lots, customers, histories or ledgers)")
    board = sup.board([p for k in "ab" for p in sorted((world[k]["root"] / "outbox").glob("*.json"))])
    print(render_text(board))
    (work / "supplier" / "board.html").write_text(render_html(board), encoding="utf-8")
    print("  (static page written to supplier/board.html)")

    banner("8. A second alert for a lot NEITHER registry can map (NSB-999): refused, never 'not affected'")
    p2, b2 = T.issue(sup, supplier_lot="NSB-999", alert_id="ALERT-UNMAPPED", text="second alert, unknown lot")
    for k, node in nodes.items():
        r = node.receive(p2, NOW)
        print(f"  {names[k]}: status {node.status(b2['alertId'])}; adopt -> {node.adopt(b2['alertId'], 'op', r['alertHash'][:12], NOW)['reason']}; response counts {node.respond(b2['alertId'], NOW)['body']['counts']}")

    banner("9. Safety recap")
    print("  * Imported messages could only be recorded or (after an operator) announce the existing local recall; no message type clears a hold or authorizes shipment.")
    print("  * Only ALERT is accepted by factories; CORRECTION/RESPONSE/anything else is rejected (see tests). No correction, retraction or WIDEN workflow exists in this build.")
    print("  * One immutable recall scope per database is unchanged; a second mapped lot is refused (see tests).")
    for node in nodes.values():
        node.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="f6demo-")))
