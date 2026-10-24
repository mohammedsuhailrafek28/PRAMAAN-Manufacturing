"""Synthetic supplier side: signs and publishes recall ALERTs to a file bulletin, and builds a counts-only board from the factories' signed RESPONSEs.

The supplier runs no evaluator and holds no ledger. It learns only what a factory chose to sign: a status and held-motor counts by the evaluator's own evidence finding.
Counts are factory-asserted under a locally generated demo key (see federation.TRUST_NOTICE); the supplier cannot verify them against any ledger.
"""
import hashlib
import html
import json
import time
import uuid
from pathlib import Path

from . import TRUST_NOTICE, messages as M
from .trust import load_trust


class Supplier:
    def __init__(self, workdir, supplier_id, key_path, factory_trust_path, supplier_code="SUP-NSB-01"):
        # supplier_id: messaging identity of the trust file; supplier_code: the supplierId the factories' registries declare for this supplier's lots (synthetic)
        self.workdir, self.id, self.supplier_code = Path(workdir), supplier_id, supplier_code
        self.key, self.kid = M.load_private(Path(key_path).read_bytes())
        self.trust = load_trust(factory_trust_path)
        (self.workdir / "bulletin").mkdir(parents=True, exist_ok=True)
        self.state_path = self.workdir / "supplier-state.json"

    def _state(self):
        return json.loads(self.state_path.read_text(encoding="utf-8")) if self.state_path.exists() else dict(seq=0, hash=None, alerts={})

    def issue_alert(self, *, supplier_lot, part, slots, text, recipients=None, ttl=3600, now=None, alert_id=None):
        at = int(time.time()) if now is None else int(now)
        state = self._state()
        body = dict(type="ALERT", alertId=alert_id or "ALERT-" + uuid.uuid4().hex[:12], issuer=self.id, seq=state["seq"] + 1, prevHash=state["hash"], iat=at, exp=at + ttl,
                    lot=dict(supplierId=self.supplier_code, part=part, supplierLot=supplier_lot), affectedSlots=list(slots), humanText=text)
        if recipients is not None:
            body["recipients"] = list(recipients)
        M.validate_alert(body)
        M.check_window(body, at)
        envelope = M.sign(body, self.key, self.kid)
        path = self.workdir / "bulletin" / f"alert-{body['seq']:06d}.json"
        path.write_text(json.dumps(envelope, indent=1), encoding="utf-8")
        digest = M.message_hash(body)
        state["alerts"][digest] = body["alertId"]
        state.update(seq=body["seq"], hash=digest)
        self.state_path.write_text(json.dumps(state), encoding="utf-8")
        return path, body

    def board(self, response_paths):
        """Verify every response and keep, per factory and alert, the latest accepted one. Rejected files are listed with their reason; nothing else is stored."""
        state, accepted, rejected, chains = self._state(), {}, [], {}
        envelopes = []
        for path in response_paths:
            try:
                envelopes.append((json.loads(Path(path).read_text(encoding="utf-8")), str(path)))
            except (OSError, ValueError):
                rejected.append(dict(file=str(path), reason="MALFORMED_ENVELOPE"))
        def seq_of(item):
            body = item[0].get("body") if isinstance(item[0], dict) else None
            return body.get("seq") if isinstance(body, dict) and type(body.get("seq")) is int else 0
        for envelope, path in sorted(envelopes, key=seq_of):
            try:
                body = M.verify_envelope(envelope, self.trust, expected_type="RESPONSE")
                M.validate_response(body)
                if body["alertHash"] not in state["alerts"] or state["alerts"][body["alertHash"]] != body["alertId"]:
                    raise M.Rejection("UNKNOWN_ALERT", "response does not refer to an alert this supplier issued")
                last_seq, last_hash = chains.get(body["responder"], (0, None))
                digest = M.message_hash(body)
                if body["seq"] <= last_seq:
                    raise M.Rejection("REPLAY" if body["seq"] == last_seq and digest == last_hash else "STALE_SEQUENCE")
                if body["seq"] != last_seq + 1:
                    raise M.Rejection("OUT_OF_ORDER", f"expected {last_seq + 1}")
                if body["prevHash"] != last_hash:
                    raise M.Rejection("PREVHASH_MISMATCH")
                chains[body["responder"]] = (body["seq"], digest)
                accepted[(body["responder"], body["alertId"])] = body
            except M.Rejection as rej:
                rejected.append(dict(file=path, reason=rej.reason, detail=rej.detail))
        rows = [dict(factory=who, alertId=alert, status=b["status"], counts=b["counts"], asOfCheckpoint=b["asOfCheckpoint"], responseSeq=b["seq"]) for (who, alert), b in sorted(accepted.items())]
        return dict(rows=rows, rejected=rejected, notice=TRUST_NOTICE,
                    scope="Only a status and held-motor counts by evaluator evidence finding. No serials, lots, customers, event histories or ledgers. A missing or zero count is not a clearance.")


def render_text(board):
    lines = ["SUPPLIER BOARD (counts only; factory-asserted)", board["notice"], board["scope"], ""]
    for r in board["rows"]:
        if r["counts"]:
            by = r["counts"]["heldByEvidenceFinding"]
            detail = f"held {r['counts']['heldMotors']} (AFFECTED {by['AFFECTED']}, UNRESOLVED {by['UNRESOLVED']}, EXCLUDED_WITH_EVIDENCE {by['EXCLUDED_WITH_EVIDENCE']}; held only by identity guard {r['counts']['heldOnlyByIdentityGuard']}); checkpoint {r['asOfCheckpoint'][:12]}"
        else:
            detail = "no counts yet"
        lines.append(f"  {r['factory']:40s} {r['alertId']:18s} {r['status']:20s} {detail}")
    lines += [f"  REJECTED {x['file']}: {x['reason']}" for x in board["rejected"]]
    return "\n".join(lines)


def render_html(board):
    e = html.escape
    rows = "".join(f"<tr><td>{e(r['factory'])}</td><td>{e(r['alertId'])}</td><td>{e(r['status'])}</td>"
                   f"<td>{e(json.dumps(r['counts']['heldByEvidenceFinding']) + ' of ' + str(r['counts']['heldMotors']) + '; only by identity guard: ' + str(r['counts']['heldOnlyByIdentityGuard'])) if r['counts'] else 'none yet'}</td></tr>" for r in board["rows"])
    return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Supplier board</title>"
            "<style>body{font:15px system-ui;margin:16px auto;max-width:860px;padding:0 16px;color:#1b1b1b;background:#fff}table{border-collapse:collapse;width:100%}"
            "td,th{border:1px solid #bbb;padding:6px 8px;text-align:left}.n{background:#fff3cd;padding:8px;border:1px solid #d9b100}@media(prefers-color-scheme:dark){body{background:#161616;color:#eee}.n{background:#3a3000;color:#eee}}</style>"
            f"<h1>Supplier board</h1><p class=n>{e(board['notice'])}</p><p>{e(board['scope'])}</p>"
            f"<table><tr><th>Factory</th><th>Alert</th><th>Status</th><th>Held motors by evidence finding</th></tr>{rows}</table>"
            f"<p>Rejected responses: {len(board['rejected'])}</p>")
