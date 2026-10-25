"""Independent admissibility check for an A7 timeline: replay it through the FROZEN capture path into a NEW scratch ledger and read the frozen product's
own decision and eligibility there. Writes only to the new scratch directory it is given (refuses to touch an existing ledger file).

If the frozen capture rules rejected the shifted events, this raises (the timeline would not be admissible). If they accept it, the snapshot below is
produced by the unchanged service, evaluator, guard and checkpoint verification, not by the diagnostic."""
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from firewall import Manufacturing  # same import path as the diagnostic (repo root on sys.path)
from application.anchors import TrustedAnchor, export_anchor, publish_candidate
from pramaan_integration import encode_document

F = "%Y-%m-%dT%H:%M:%SZ"


def replay(ev, events, scratch_dir):
    scratch = Path(scratch_dir)
    db = scratch / "replay.sqlite"
    if db.exists():
        raise FileExistsError("replay refuses to write into an existing ledger")
    scratch.mkdir(parents=True, exist_ok=True)
    motor = ev["motor"]
    app = Manufacturing(db, lot_registry=ev["registry"])
    try:
        cfg = dict(sources=ev["config"]["sources"], sessions=ev["sessions"], coverage=ev["coverage"])
        app.ledger.register_motor(motor, **cfg)
        with app.db:
            app.db.execute("INSERT INTO app_units VALUES(?,?)", (motor, "A7 replay (synthetic)"))
            p = ev["policy"]
            from pramaan_integration.profile import digest
            app.db.execute("INSERT INTO recall_announcements VALUES(?,?,?)", (p["version"], json.dumps(p), digest(p)))
        for e in sorted(events, key=lambda e: (e["recordedAt"], e["sourceId"], e["sourceSeq"])):
            native = {k: v for k, v in e.items() if k != "repository"}
            rt = (datetime.strptime(e["recordedAt"], F) + timedelta(seconds=4)).strftime(F)
            raw = json.dumps(encode_document([native], rt), separators=(",", ":")).encode()
            app.ledger.capture(motor, raw, producer_source=e["sourceId"], expected_sha256=hashlib.sha256(raw).hexdigest())
        app.snapshot()
        publish_candidate(scratch / "root.json", export_anchor(app))
        snap = app.snapshot(trusted_anchor=TrustedAnchor(scratch / "root.json"))
        cur = snap["decisions"][motor][p["policyId"]]["current"]
        return dict(checkpoint=snap["checkpoint"]["state"], operationalAction=cur["operationalAction"], evaluatorOperationalAction=cur["evaluatorOperationalAction"],
                    evidenceFinding=cur["evidenceFinding"], identityFindings=sorted(f["reason"] for f in cur["identityGuard"]["findings"]),
                    releaseEligible=snap["eligibility"][motor]["currentReleaseEligible"], ledger=str(db))
    finally:
        app.close()
