"""Owner-custodied external commitments. Files are NOT intrinsically trusted.

The caller must establish custody independently. Replacing both archive and
trusted reference is outside this mechanism's trust model. No signing key or
authenticated identity is invented here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integration'))

import rfc8785
from pramaan_integration import LedgerBlocked
from pramaan_integration.profile import digest
from .audit import PROFILE

FORMAT = 'PRAMAAN_A31_ANCHOR_V1'
HARDENING_PROFILE = 'A31_C1_C3_PENDING_OBLIGATIONS_V1'


def state(audit, records):
    return dict(publications=digest([p for k,p in records if k=='EVALUATION']),
                outstanding=digest(audit.outstanding(records)))


def export_anchor(app):
    records=app.audit.verify()
    head=app.db.execute('SELECT * FROM app_audit_head WHERE id=1').fetchone()
    body=dict(format=FORMAT, publicationProfile=PROFILE, hardeningProfile=HARDENING_PROFILE, archiveId=head['archive_id'],
              sequence=head['count'], headHash=head['hash'], legacyDigest=head['legacy_digest'],
              policyDigest=digest(app.policy()), state=state(app.audit,records))
    return dict(body=body, checksum=digest(body))


def verify_anchor(app, anchor):
    """Prove the current archive extends the trusted prefix, not merely its ID."""
    try:
        body=anchor['body']
        if set(anchor)!= {'body','checksum'} or anchor['checksum']!=digest(body):
            raise ValueError('anchor checksum')
        if set(body)!= {'format','publicationProfile','hardeningProfile','archiveId','sequence','headHash','legacyDigest','policyDigest','state'}:
            raise ValueError('anchor fields')
        if body['format']!=FORMAT or body['publicationProfile']!=PROFILE or body['hardeningProfile']!=HARDENING_PROFILE or type(body['sequence']) is not int or body['sequence']<1:
            raise ValueError('anchor format/profile/sequence')
        records=app.audit.verify()
        head=app.db.execute('SELECT * FROM app_audit_head WHERE id=1').fetchone()
        if head['archive_id']!=body['archiveId'] or head['legacy_digest']!=body['legacyDigest']:
            raise ValueError('archive/legacy identity')
        if digest(app.policy())!=body['policyDigest'] and body['policyDigest']!=digest(None):
            raise ValueError('recall policy changed; explicit owner anchor review required')
        row=app.db.execute('SELECT hash FROM app_audit WHERE seq=?',(body['sequence'],)).fetchone()
        if row is None or row[0]!=body['headHash']:
            raise ValueError('archive does not extend trusted journal prefix')
        prefix=records[:body['sequence']]
        if state(app.audit,prefix)!=body['state']:
            raise ValueError('publication/obligation commitment')
        if any(kind=='OBLIGATION_RESOLVED' for kind,_ in records[body['sequence']:]):
            raise ValueError('New obligation resolution forbidden in this profile')
        # Bind original publication inputs too. Re-evaluating every old decision
        # on every poll is unnecessary: the trusted prefix commits its bytes and
        # original profile; exact kernel replay remains a separate test gate.
        for kind,entry in prefix:
            if kind=='EVALUATION':
                _,manifest=app.ledger.snapshot(entry['context']['motor'],entry['manifest']['watermark'])
                if manifest!=entry['manifest'] or digest(entry['policy'])!=entry['context']['policyDigest']:
                    raise ValueError('anchored publication inputs changed')
        return dict(status='VERIFIED_TRUSTED_PREFIX', archiveId=head['archive_id'],
                    anchoredSequence=body['sequence'], sequence=head['count'], headHash=head['hash'])
    except (KeyError,TypeError,ValueError,IndexError) as exc:
        raise LedgerBlocked(f'External anchor verification failed: {exc}') from exc


class TrustedAnchor:
    """Explicit owner-supplied reference, pinned for this server process.

    Pinning catches file replacement during this process; it does not establish
    original custody, or protect a restart with a substituted reference.
    """
    def __init__(self,path):
        self.path=Path(path)
        self.bytes=self.path.read_bytes()
        self.anchor=json.loads(self.bytes)

    def verify(self,app):
        try:
            if self.path.read_bytes()!=self.bytes:
                raise LedgerBlocked('Owner-supplied anchor changed during process')
            return verify_anchor(app,self.anchor)
        except (OSError,ValueError) as exc:
            raise LedgerBlocked('Trusted anchor missing or unreadable') from exc


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['export','verify'])
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--anchor',type=Path,required=True)
    args=parser.parse_args()
    if not args.database.is_file(): parser.error('Existing database required; no implicit bootstrap')
    from .service import Manufacturing
    app=Manufacturing(args.database)
    try:
        if args.operation=='export':
            app.snapshot()  # archive current results before committing publications
            anchor=export_anchor(app)
            with args.anchor.open('xb') as file: file.write(rfc8785.dumps(anchor))
            print('EXPORTED_UNTRUSTED_UNTIL_OWNER_CUSTODY_ESTABLISHED')
        else:
            print(json.dumps(TrustedAnchor(args.anchor).verify(app)))
    finally: app.close()


if __name__=='__main__': main()
