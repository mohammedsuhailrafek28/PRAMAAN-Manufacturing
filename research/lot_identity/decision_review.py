"""Research prototype: mandatory decision-change review before a checkpoint is accepted. Read-only except the final delegated accept().

Shows, per motor, what changes between the decisions covered by the CURRENT accepted checkpoint and the decisions the candidate would
newly cover: newly excluded, newly held, unresolved, new motors, plus the lots and evidence events each exclusion depends on and whether
each lot's identity is established. An acknowledgement is an operator assertion on this host: it is NOT independent authentication
and NOT proof of physical lot identity.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lotid  # noqa: E402
from application import checkpoint_ops  # noqa: E402
from application.service import Manufacturing  # noqa: E402

EXCLUDED, HELD = "EXCLUDED_WITH_EVIDENCE", "RECALL_HOLD"


def _latest_by_motor(records, upto=None):
    out = {}
    for n, (kind, p) in enumerate(records, 1):
        if upto is not None and n > upto:
            break
        if kind == "EVALUATION" and "decision" in p:
            out[p["context"]["motor"]] = p["decision"]
    return out


def build_review(database, current_checkpoint, candidate_checkpoint, registry=None):
    cur = json.loads(Path(current_checkpoint).read_bytes())["body"]
    cand = json.loads(Path(candidate_checkpoint).read_bytes())["body"]
    app = Manufacturing(database)
    try:
        records = app.audit.verify(copy_records=False)
        before, after = _latest_by_motor(records, cur["sequence"]), _latest_by_motor(records, cand["sequence"])
        snap = app.snapshot()
        guard = lotid.apply_guard(snap, snap["recall"]["affectedLots"], registry)["identityGuard"]["motors"]
        lots = {}
        for c in snap["components"]:
            if not (c["removedAt"] or c["supersededBy"]):
                lots.setdefault(c["unitId"], []).append(dict(slot=c["slot"], lot=c["lot"], installEventId=c["componentId"],
                                                              identity="NOT_ESTABLISHED" if any(g["eventId"] == c["componentId"] for g in guard.get(c["unitId"], [])) else "ESTABLISHED_LOCAL_RULES"))
        rows = []
        for motor, d in sorted(after.items()):
            old = before.get(motor)
            kind = ("NEW_MOTOR" if old is None else "UNCHANGED" if old["evidenceFinding"] == d["evidenceFinding"] and old["operationalAction"] == d["operationalAction"] else "CHANGED")
            if d["evidenceFinding"] == EXCLUDED and (old is None or old["evidenceFinding"] != EXCLUDED):
                kind = "NEWLY_EXCLUDED"
            elif d["operationalAction"] == HELD and d["evidenceFinding"] == "AFFECTED" and (old is None or old["operationalAction"] != HELD):
                kind = "NEWLY_HELD"
            elif d["evidenceFinding"] == "UNRESOLVED" and (old is None or old["evidenceFinding"] != "UNRESOLVED"):
                kind = "NEWLY_UNRESOLVED"
            rows.append(dict(motor=motor, change=kind, before=old and [old["evidenceFinding"], old["operationalAction"]], after=[d["evidenceFinding"], d["operationalAction"]],
                             reasonCodes=d["reasonCodes"], evidenceEventIds=d["evidenceEventIds"], installedLots=lots.get(motor, []),
                             identityNotEstablished=[g for g in guard.get(motor, [])]))
        need_ack = [r["motor"] for r in rows if r["change"] in ("NEWLY_EXCLUDED", "NEWLY_HELD", "NEWLY_UNRESOLVED", "NEW_MOTOR")]
        blocked = [r["motor"] for r in rows if r["change"] == "NEWLY_EXCLUDED" and r["identityNotEstablished"]]
        return dict(trust="ACKNOWLEDGEMENT_IS_NOT_AUTHENTICATION_AND_NOT_PROOF_OF_PHYSICAL_LOT_IDENTITY", rows=rows, requiresAcknowledgement=need_ack, blockedByIdentity=blocked)
    finally:
        app.close()


def accept_with_review(database, current, custody, candidate, candidate_sha, custodian, acknowledged_motors, registry=None):
    review = build_review(database, current, candidate, registry)
    if review["blockedByIdentity"]:
        raise SystemExit(f"REFUSED: exclusion rests on lot identity that is not established for {review['blockedByIdentity']}; fix or hold the motors, then propose again.")
    missing = sorted(set(review["requiresAcknowledgement"]) - set(acknowledged_motors))
    if missing:
        raise SystemExit(f"REFUSED: each changed motor must be acknowledged individually; missing {missing}.")
    return checkpoint_ops.accept(database, current, custody, candidate, custodian, candidate_sha), review
