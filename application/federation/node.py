"""One synthetic factory instance: receives signed supplier ALERTs, records them, and acts on its own ledger ONLY after an explicit operator adoption.

Flow: receive (authenticate -> validate -> freshness -> addressed -> strict sequence chain -> store; the ledger is not opened)
      adopt   (operator + typed confirmation -> signature re-verified from the stored envelope -> registry mapping -> existing `Manufacturing.announce`)
      respond (signed, counts-only; counts exist only when the unchanged snapshot is ANCHORED_CURRENT under the unchanged FORMAT_V3 checkpoint)
The ledger is touched only by `announce` (adds the one local recall policy) and the read-only `snapshot`. Nothing here ships, clears, replaces, observes or edits anything.
"""
import hashlib
import json
import time
import uuid
from pathlib import Path

from . import messages as M
from .lotmap import map_lot
from .store import Store
from .trust import load_trust


class FactoryNode:
    def __init__(self, workdir, factory_id, database, registry_path, trust_path, key_path, anchor, previous_anchor=None):
        self.workdir, self.id = Path(workdir), factory_id
        self.database, self.registry_path = Path(database), Path(registry_path)
        self.trust = load_trust(trust_path)
        self.key, self.kid = M.load_private(Path(key_path).read_bytes())
        self.anchor, self.previous = Path(anchor), (Path(previous_anchor) if previous_anchor else None)
        self.store = Store(self.workdir / "federation.sqlite")
        (self.workdir / "outbox").mkdir(parents=True, exist_ok=True)

    def close(self):
        self.store.close()

    def set_checkpoint(self, anchor, previous=None):
        self.anchor, self.previous = Path(anchor), (Path(previous) if previous else None)

    # ------------------------------------------------------------------ receive (never opens the ledger)
    def receive(self, source, now=None):
        at = int(time.time()) if now is None else int(now)
        raw = Path(source).read_bytes() if isinstance(source, (str, Path)) else json.dumps(source).encode()
        sha = hashlib.sha256(raw).hexdigest()
        try:
            try:
                envelope = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeError) as exc:
                raise M.Rejection("MALFORMED_ENVELOPE", "not JSON") from exc
            body = M.verify_envelope(envelope, self.trust, expected_type="ALERT")        # authenticate first
            M.validate_alert(body)
            M.check_window(body, at)
            if body.get("recipients") is not None and self.id not in body["recipients"]:
                raise M.Rejection("NOT_ADDRESSED", "this factory is not a listed recipient")
            digest = M.message_hash(body)
            last_seq, last_hash = self.store.hwm(body["issuer"])
            if self.store.alert(body["alertId"])[0] is not None and self.store.alert(body["alertId"])[0] != digest:
                raise M.Rejection("DUPLICATE_ALERT_ID", "alertId already used by a different message")
            if body["seq"] <= last_seq:
                raise M.Rejection("REPLAY" if self.store.alert(body["alertId"])[0] == digest else "STALE_SEQUENCE", f"seq {body['seq']} <= high-water mark {last_seq}")
            if body["seq"] != last_seq + 1:
                raise M.Rejection("OUT_OF_ORDER", f"expected seq {last_seq + 1}, got {body['seq']}")
            if body["prevHash"] != last_hash:
                raise M.Rejection("PREVHASH_MISMATCH", "does not extend the last accepted message")
            self.store.accept(digest, body, envelope, at)
            return dict(accepted=True, alertId=body["alertId"], alertHash=digest, status="PENDING_OPERATOR", ledgerTouched=False)
        except M.Rejection as rej:
            self.store.reject(rej.reason, rej.detail[:200], sha, at)
            return dict(accepted=False, reason=rej.reason, detail=rej.detail, ledgerTouched=False)

    # ------------------------------------------------------------------ views
    def _stored(self, alert_id):
        digest, envelope = self.store.alert(alert_id)
        if digest is None:
            raise KeyError(f"unknown alert {alert_id}")
        return digest, envelope

    def registry(self):
        from ..lot_identity import LotRegistry
        return LotRegistry.load(self.registry_path)

    def status(self, alert_id):
        digest, envelope = self._stored(alert_id)
        adoption = self.store.adoption(alert_id)
        if adoption is not None:
            if adoption["outcome"] == "ADOPTED":
                return "ADOPTED"
            return "LOT_UNMAPPED" if adoption["detail"].startswith("LOT_UNMAPPED") else "ADOPTION_REFUSED"
        return "PENDING_OPERATOR" if map_lot(self.registry(), envelope["body"]["lot"]).mapped else "LOT_UNMAPPED"

    # ------------------------------------------------------------------ adopt (the only path to the ledger)
    def adopt(self, alert_id, operator, confirm, now=None):
        at = int(time.time()) if now is None else int(now)
        digest, envelope = self._stored(alert_id)
        if not isinstance(operator, str) or not operator.strip() or len(operator) > 80:
            return dict(adopted=False, reason="OPERATOR_REQUIRED")
        if confirm != digest[:12]:
            return dict(adopted=False, reason="CONFIRMATION_MISMATCH", detail="type the first 12 hex characters of the alert hash shown by `status`")
        previous = self.store.adoption(alert_id)
        if previous is not None and previous["outcome"] == "ADOPTED":
            return dict(adopted=True, alreadyAdopted=True, localLot=previous["local_lot"])
        try:                                                                  # the stored copy is outside any integrity protection: authenticate it again
            body = M.verify_envelope(envelope, self.trust, expected_type="ALERT")
            M.validate_alert(body)
            M.check_window(body, at)
        except M.Rejection as rej:
            return dict(adopted=False, reason=rej.reason, detail=rej.detail)
        mapping = map_lot(self.registry(), body["lot"])
        if not mapping.mapped:
            self.store.record_adoption(alert_id, operator, at, "", body["affectedSlots"], "REFUSED", "LOT_UNMAPPED:" + mapping.reason)
            return dict(adopted=False, reason="LOT_UNMAPPED", detail=mapping.reason)
        from ..service import Manufacturing, ValidationFailure
        slots = sorted(body["affectedSlots"], key=M.SLOTS.index)
        app = Manufacturing(self.database, lot_registry=self.registry_path)
        try:
            app.announce(mapping.canonical, slots)                            # hold-increasing; refuses a second scope in this database
        except ValidationFailure as exc:
            self.store.record_adoption(alert_id, operator, at, mapping.canonical, slots, "REFUSED", str(exc)[:200])
            return dict(adopted=False, reason="ADOPTION_REFUSED", detail=str(exc))
        finally:
            app.close()
        self.store.record_adoption(alert_id, operator, at, mapping.canonical, slots, "ADOPTED")
        return dict(adopted=True, localLot=mapping.canonical, slots=slots, next="ledger is newer than the checkpoint: run the existing checkpoint propose/accept cycle, then respond")

    # ------------------------------------------------------------------ respond (counts only)
    def respond(self, alert_id, now=None):
        at = int(time.time()) if now is None else int(now)
        digest, envelope = self._stored(alert_id)
        status, counts, as_of = self.status(alert_id), None, None
        if status == "ADOPTED":
            counts, as_of, status = self._counts(self.store.adoption(alert_id)["local_lot"])
        seq, prev = self.store.last_response()
        body = dict(type="RESPONSE", responseId=uuid.uuid4().hex, alertId=alert_id, alertHash=digest, responder=self.id, seq=seq + 1, prevHash=prev, iat=at,
                    status=status, counts=counts, asOfCheckpoint=as_of)
        M.validate_response(body)
        signed = M.sign(body, self.key, self.kid)
        path = self.workdir / "outbox" / f"response-{body['seq']:06d}.json"
        path.write_text(json.dumps(signed, indent=1), encoding="utf-8")
        self.store.add_response(body["seq"], body["responseId"], alert_id, M.message_hash(body), path)
        return dict(status=status, path=path, body=body)

    def _counts(self, local_lot):
        from ..anchors import TrustedAnchor
        from ..service import Manufacturing
        app = Manufacturing(self.database, lot_registry=self.registry_path)
        try:
            snap = app.snapshot(trusted_anchor=TrustedAnchor(self.anchor, self.previous))
        finally:
            app.close()
        if snap["checkpoint"]["state"] != "ANCHORED_CURRENT":
            return None, None, "PENDING_CHECKPOINT"
        recall = snap.get("recall")
        if not snap["recallAnnounced"] or not recall or recall["affectedLots"] != [local_lot]:
            return None, None, "ADOPTION_REFUSED"                              # the ledger does not hold the adopted scope: report no counts
        held, guard_only, by = 0, 0, {f: 0 for f in M.FINDINGS}
        for per_policy in snap["decisions"].values():
            current = next(iter(per_policy.values()))["current"]
            if current["operationalAction"] == "RECALL_HOLD":
                held += 1
                by[current["evidenceFinding"]] += 1
                guard_only += current.get("evaluatorOperationalAction", "RECALL_HOLD") != "RECALL_HOLD"      # the unchanged evaluator would release; the identity guard holds
        checksum = json.loads(self.anchor.read_bytes())["checksum"]
        return dict(heldMotors=held, heldByEvidenceFinding=by, heldOnlyByIdentityGuard=guard_only), checksum, "ANSWERED"
