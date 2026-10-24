"""Operator workflow for refreshing the trusted checkpoint. It never grants trust by itself.

    python -m application.checkpoint_ops propose --database DB --current CURRENT.json --custody-dir DIR
    python -m application.checkpoint_ops accept  --database DB --current CURRENT.json --custody-dir DIR \
        --candidate DIR/candidates/<file> --custodian "<name>" --confirm-sha256 <candidate sha256>

`propose` verifies the current checkpoint against the ledger, exports a successor CANDIDATE (chained to the
current checkpoint, no overwrite) and prints what the candidate would newly cover. Nothing is activated.

`accept` records that the named custodian reviewed that exact candidate (its sha256 must be typed back) and moves it
to the accepted directory, read-only, with an acceptance record. That record is an operator assertion on this host,
NOT independent custody: a custodian who controls the host controls this record too. The application is then
restarted by the operator with --trusted-anchor <accepted> --previous-anchor <current>. This tool never starts,
stops or hot-swaps a server and there is no HTTP route that promotes a checkpoint.
"""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from .anchors import TrustedAnchor, export_anchor, publish_candidate
from .audit import IntegrityFailure
from .service import Manufacturing
from .checkpoint_review import build_review

STATUS_PROPOSED = "CANDIDATE_PROPOSED_NOT_ACTIVATED"
STATUS_ACCEPTED = "LOCAL_CUSTODY_ACCEPTANCE_OPERATOR_ASSERTED_NOT_INDEPENDENT"


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summarize(app, current_body, candidate_body):
    """What the candidate would newly cover, from the ledger's own counts. Informational only."""
    rows = candidate_body["ledger"]["rows"]; old = current_body["ledger"]["rows"] if "ledger" in current_body else {}
    return dict(
        archiveId=candidate_body["archiveId"],
        currentAnchoredSequence=current_body["sequence"], candidateSequence=candidate_body["sequence"],
        newJournalEntries=candidate_body["sequence"] - current_body["sequence"],
        newRowsByTable={t: len(r) - len(old.get(t, [])) for t, r in rows.items() if len(r) - len(old.get(t, [])) > 0},
        previousCheckpointHash=candidate_body["previousCheckpointHash"],
    )


def propose(database, current_path, custody_dir, current_previous=None):
    custody = Path(custody_dir); (custody / "candidates").mkdir(parents=True, exist_ok=True)
    app = Manufacturing(database)
    try:
        current = TrustedAnchor(current_path, current_previous)
        proof = current.verify(app)            # the current checkpoint must still verify against this ledger
        if proof["state"] == "ANCHORED_CURRENT":
            return dict(status="NO_CANDIDATE_NEEDED", reason="The current checkpoint already covers the ledger.")
        app.snapshot()                          # archive current results before committing publications
        previous = json.loads(Path(current_path).read_bytes())
        candidate = export_anchor(app, previous)
        name = f"candidate-{candidate['body']['sequence']:06d}-{candidate['checksum'][:12]}.json"
        path = custody / "candidates" / name
        publish_candidate(path, candidate)      # staged, fsynced, no overwrite
        return dict(status=STATUS_PROPOSED, candidate=str(path), candidateSha256=sha256_file(path),
                    covers=summarize(app, previous["body"], candidate["body"]),
                    review=build_review(app, previous["body"], candidate["body"]),
                    next="Review the candidate, then run 'accept' with the custodian name and the sha256 above. Nothing is active yet.")
    finally:
        app.close()


def accept(database, current_path, custody_dir, candidate_path, custodian, confirm_sha256, acknowledged=None, expected_registry_digest=None):
    if not custodian.strip():
        raise SystemExit("A named custodian is required.")
    candidate_path = Path(candidate_path); digest = sha256_file(candidate_path)
    if digest != confirm_sha256:
        raise SystemExit("REFUSED: the typed sha256 does not match the candidate file; nothing was accepted.")
    custody = Path(custody_dir)
    if candidate_path.parent.resolve() != (custody / "candidates").resolve():
        raise SystemExit("REFUSED: the candidate must be a file this tool proposed (custody-dir/candidates).")
    app = Manufacturing(database)
    try:
        # The candidate must verify as a chained successor of the current checkpoint, in a fresh trust object.
        proof = TrustedAnchor(candidate_path, current_path).verify(app)
        review = build_review(app, json.loads(Path(current_path).read_bytes())["body"], json.loads(candidate_path.read_bytes())["body"])
    finally:
        app.close()
    if expected_registry_digest is not None and expected_registry_digest != review["registry"]["digest"]:
        raise SystemExit("REFUSED: the lot registry changed since the candidate was proposed (digest mismatch); propose again so the review reflects the registry in force. Nothing was accepted.")
    if review["refusedForIdentity"]:
        raise SystemExit(f"REFUSED: an exclusion rests on lot identity that is not established for {review['refusedForIdentity']}; acknowledgement cannot override this. Nothing was accepted.")
    missing = sorted(set(review["requiresAcknowledgement"]) - set(acknowledged or []))
    if missing:
        raise SystemExit(f"REFUSED: every newly excluded or newly release-eligible motor must be acknowledged individually; missing {missing}. Nothing was accepted.")
    if proof["state"] != "ANCHORED_CURRENT":
        raise SystemExit("REFUSED: the ledger changed after the candidate was proposed; propose again.")
    accepted_dir = custody / "accepted"; accepted_dir.mkdir(parents=True, exist_ok=True)
    target = accepted_dir / candidate_path.name.replace("candidate-", "accepted-")
    os.link(candidate_path, target)             # no overwrite
    os.chmod(target, 0o444)
    record = dict(status=STATUS_ACCEPTED, custodian=custodian, acceptedAtUtc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  candidateSha256=digest, accepted=str(target), previous=str(Path(current_path)),
                  anchoredSequence=proof["anchoredSequence"], note="Operator-asserted on this host; not independent custody.",
                  acknowledgedMotors=sorted(acknowledged or []), registryDigest=review["registry"]["digest"], registryProvenance=review["registry"]["provenance"],
                  acknowledgementNote="Acknowledgement is an operator assertion; not authentication and not proof of physical lot identity.")
    log = accepted_dir / (target.name + ".acceptance.json")
    log.write_text(json.dumps(record, indent=2), encoding="utf-8"); os.chmod(log, 0o444)
    record["restart"] = f'python app.py --database "{database}" --trusted-anchor "{target}" --previous-anchor "{current_path}"'
    return record


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("operation", choices=["propose", "accept"])
    p.add_argument("--database", type=Path, required=True)
    p.add_argument("--current", type=Path, required=True, help="The checkpoint the running server was activated with")
    p.add_argument("--current-previous", type=Path, help="The predecessor the running server was activated with, if the current checkpoint is a successor")
    p.add_argument("--custody-dir", type=Path, required=True)
    p.add_argument("--candidate", type=Path)
    p.add_argument("--custodian")
    p.add_argument("--confirm-sha256")
    p.add_argument("--registry-digest", help="Registry digest shown by propose; accept refuses if the registry changed since")
    p.add_argument("--acknowledge", action="append", default=[], metavar="MOTOR", help="Acknowledge a newly excluded or newly release-eligible motor (repeatable)")
    a = p.parse_args(argv)
    if not a.database.is_file():
        p.error("Existing database required")
    try:
        if a.operation == "propose":
            out = propose(a.database, a.current, a.custody_dir, a.current_previous)
        else:
            if not (a.candidate and a.custodian and a.confirm_sha256):
                p.error("accept requires --candidate, --custodian and --confirm-sha256")
            out = accept(a.database, a.current, a.custody_dir, a.candidate, a.custodian, a.confirm_sha256, a.acknowledge, a.registry_digest)
    except IntegrityFailure as exc:
        print(exc.code, file=sys.stderr); raise SystemExit(1)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
