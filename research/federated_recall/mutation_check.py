"""Sensitivity check for F6: each mutant removes ONE safeguard by rewriting the module source in memory (no file is changed); test_federation must then fail.
usage (repository root, F6/F5 venv):  python -B research/federated_recall/mutation_check.py OUT.json [mutant names...]
"""
import importlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import application.test_federation as T  # noqa: E402
from application.federation import lotmap, messages, node, supplier  # noqa: E402

MODULES = {"messages": messages, "node": node, "supplier": supplier, "lotmap": lotmap}
ORIGINAL = {name: Path(m.__file__).read_text(encoding="utf-8") for name, m in MODULES.items()}

# (name, module, old, new): `old` must occur exactly once
SOURCE_MUTANTS = (
    ("signature_not_verified", "messages", "        public.verify(signature, _signing_input(body))\n", "        pass\n"),
    ("kid_not_checked", "messages", 'if envelope["kid"] != kid:', "if False:"),
    ("sender_role_not_checked", "messages", "    if role != (", "    if False and role != ("),
    ("message_type_not_checked", "messages", '    if not isinstance(body, dict) or body.get("type") != expected_type:', "    if not isinstance(body, dict):"),
    ("expiry_not_checked", "messages", "    if at >= exp:", "    if False:"),
    ("lifetime_cap_removed", "messages", "or exp - iat > MAX_LIFETIME_SECONDS:", "or False:"),
    ("alert_field_set_open", "messages", '"humanText", "recipients"}', '"humanText", "recipients", "clearsHold", "release"}'),
    ("response_counts_consistency_removed", "messages", 'or sum(by.values()) != counts["heldMotors"]', "or False"),
    ("replay_check_removed", "node", '        if body["seq"] <= last_seq:', "        if False:"),
    ("sequence_gap_allowed", "node", '        if body["seq"] != last_seq + 1:', "        if False:"),
    ("prevhash_chain_removed", "node", '        if body["prevHash"] != last_hash:', "        if False:"),
    ("recipient_list_ignored", "node", '        if body.get("recipients") is not None and self.id not in body["recipients"]:', "        if False:"),
    ("adopt_on_receive", "node", "            self.store.accept(digest, body, envelope, at)\n", '            self.store.accept(digest, body, envelope, at)\n            self.adopt(body["alertId"], "auto", digest[:12], at)\n'),
    ("operator_not_required", "node", "        if not isinstance(operator, str) or not operator.strip() or len(operator) > 80:", "        if False:"),
    ("confirmation_not_required", "node", "        if confirm != digest[:12]:", "        if False:"),
    ("stored_alert_trusted_without_reverification", "node",
     '            body = M.verify_envelope(envelope, self.trust, expected_type="ALERT")\n            M.validate_alert(body)\n            M.check_window(body, at)\n        except M.Rejection as rej:\n            return dict(adopted=False',
     '            body = envelope["body"]\n        except M.Rejection as rej:\n            return dict(adopted=False'),
    ("counts_given_while_checkpoint_stale", "node", '        if snap["checkpoint"]["state"] != "ANCHORED_CURRENT":', "        if False:"),
    ("counts_without_matching_ledger_policy", "node", '        if not snap["recallAnnounced"] or not recall or recall["affectedLots"] != [local_lot]:', "        if False:"),
    ("response_leaks_local_lot", "node", "        M.validate_response(body)\n", "        pass\n"),
    ("lot_mapped_by_label_not_registry", "lotmap", '    res = registry.resolve(lot["supplierLot"], at=None, part=lot["part"])\n', '    return Mapping(True, canonical=lot["supplierLot"])\n    res = registry.resolve(lot["supplierLot"], at=None, part=lot["part"])\n'),
    ("supplier_scope_ignored", "lotmap", '    if res.entry["supplierId"] != lot["supplierId"]:', "    if False:"),
    ("board_accepts_unsigned_responses", "supplier", '                body = M.verify_envelope(envelope, self.trust, expected_type="RESPONSE")\n', '                body = envelope["body"]\n'),
    ("board_replay_check_removed", "supplier", '                if body["seq"] <= last_seq:', "                if False:"),
    ("board_alert_binding_removed", "supplier", '                if body["alertHash"] not in state["alerts"] or state["alerts"][body["alertHash"]] != body["alertId"]:', "                if False:"),
)
def apply(name, module, old, new):
    source = ORIGINAL[module]
    if name == "response_leaks_local_lot":
        source = source.replace("status=status, counts=counts, asOfCheckpoint=as_of)", 'status=status, counts=counts, asOfCheckpoint=as_of, localLot=(self.store.adoption(alert_id) or {"local_lot": None})["local_lot"])')
    assert source.count(old) == 1, (name, source.count(old))
    mutated = source.replace(old, new)
    exec(compile(mutated, MODULES[module].__file__, "exec"), MODULES[module].__dict__)
    T.FactoryNode, T.Supplier = node.FactoryNode, supplier.Supplier


def restore():
    for name, m in MODULES.items():
        exec(compile(ORIGINAL[name], m.__file__, "exec"), m.__dict__)
    T.FactoryNode, T.Supplier = node.FactoryNode, supplier.Supplier


def run():
    suite = unittest.defaultTestLoader.loadTestsFromModule(T)
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    return dict(ran=result.testsRun, failed=sorted({str(t).split(" ")[0] for t, _ in result.failures + result.errors}))


if __name__ == "__main__":
    only = set(sys.argv[2:])
    results = dict(unmutated=run())
    for name, module, old, new in SOURCE_MUTANTS:
        if only and name not in only:
            continue
        apply(name, module, old, new)
        try:
            results[name] = run()
        finally:
            restore()
    for k, v in results.items():
        print(k, v["ran"], "tests; failing:", len(v["failed"]), v["failed"][:4])
    Path(sys.argv[1]).write_text(json.dumps(results, indent=1, sort_keys=True))
    survivors = [k for k, v in results.items() if k != "unmutated" and not v["failed"]]
    print("SURVIVORS:", survivors)
    sys.exit(1 if survivors or results["unmutated"]["failed"] else 0)
