"""Owner-custodied external commitments. Files are NOT intrinsically trusted.

The caller must establish custody independently. Replacing both archive and
trusted reference is outside this mechanism's trust model. No signing key or
authenticated identity is invented here.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import os
import tempfile
import time
from functools import wraps
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integration'))

import rfc8785
from pramaan_integration import LedgerBlocked
from pramaan_integration.profile import digest
from . import registry_binding
from .audit import PROFILE, VERIFIER_VERSION, ENGINE_TREE, IntegrityFailure, ReplayCache

FORMAT = 'PRAMAAN_A31_ANCHOR_V1'
HARDENING_PROFILE = 'A31_C1_C3_PENDING_OBLIGATIONS_V1'


def state(audit, records):
    return dict(publications=digest([p for k,p in records if k=='EVALUATION']),
                outstanding=digest(audit.outstanding(records)))


def export_v1(app):
    records=app.audit.verify(copy_records=False)
    head=app.db.execute('SELECT * FROM app_audit_head WHERE id=1').fetchone()
    body=dict(format=FORMAT, publicationProfile=PROFILE, hardeningProfile=HARDENING_PROFILE, archiveId=head['archive_id'],
              sequence=head['count'], headHash=head['hash'], legacyDigest=head['legacy_digest'],
              policyDigest=digest(app.policy()), state=state(app.audit,records))
    return dict(body=body, checksum=digest(body))


def verify_v1(app, anchor, *, replay_inputs=True, prefix_cache=None):
    """Prove the current archive extends the trusted prefix, not merely its ID."""
    try:
        body=anchor['body']
        if set(anchor)!= {'body','checksum'} or anchor['checksum']!=digest(body):
            raise ValueError('anchor checksum')
        if set(body)!= {'format','publicationProfile','hardeningProfile','archiveId','sequence','headHash','legacyDigest','policyDigest','state'}:
            raise ValueError('anchor fields')
        if body['format']!=FORMAT or body['publicationProfile']!=PROFILE or body['hardeningProfile']!=HARDENING_PROFILE or type(body['sequence']) is not int or body['sequence']<1:
            raise ValueError('anchor format/profile/sequence')
        records=app.audit.verify(copy_records=False)
        head=app.db.execute('SELECT * FROM app_audit_head WHERE id=1').fetchone()
        if head['archive_id']!=body['archiveId'] or head['legacy_digest']!=body['legacyDigest']:
            raise ValueError('archive/legacy identity')
        if digest(app.policy())!=body['policyDigest'] and body['policyDigest']!=digest(None):
            raise ValueError('recall policy changed; explicit owner anchor review required')
        row=app.db.execute('SELECT hash FROM app_audit WHERE seq=?',(body['sequence'],)).fetchone()
        if row is None or row[0]!=body['headHash']:
            raise ValueError('archive does not extend trusted journal prefix')
        prefix=records[:body['sequence']]
        prefix_rows=[tuple(r) for r in app.db.execute('SELECT * FROM app_audit WHERE seq<=? ORDER BY seq',(body['sequence'],))]
        prefix_key=hashlib.sha256(json.dumps(dict(body=body,rows=prefix_rows),sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if prefix_cache is None or prefix_cache.get('key')!=prefix_key:
            if state(app.audit,prefix)!=body['state']:raise ValueError('publication/obligation commitment')
            if prefix_cache is not None:prefix_cache['key']=prefix_key
        if any(kind=='OBLIGATION_RESOLVED' for kind,_ in records[body['sequence']:]):
            raise IntegrityFailure('RESOLUTION_FORBIDDEN')
        # Bind original publication inputs too. Re-evaluating every old decision
        # on every poll is unnecessary: the trusted prefix commits its bytes and
        # original profile; exact kernel replay remains a separate test gate.
        for kind,entry in prefix:
            if replay_inputs and kind=='EVALUATION' and 'manifest' in entry:
                _,manifest=app.ledger.snapshot(entry['context']['motor'],entry['manifest']['watermark'])
                if manifest!=entry['manifest'] or digest(entry['policy'])!=entry['context']['policyDigest']:
                    raise ValueError('anchored publication inputs changed')
        return dict(status='VERIFIED_TRUSTED_PREFIX', archiveId=head['archive_id'],
                    anchoredSequence=body['sequence'], sequence=head['count'], headHash=head['hash'])
    except IntegrityFailure:raise
    except (KeyError,TypeError,ValueError,IndexError):
        raise IntegrityFailure('PREFIX_MISMATCH') from None


FORMAT_V2='PRAMAAN_A31_ANCHOR_V2'
FORMAT_V3='PRAMAAN_A31_ANCHOR_V3'   # V2 plus registryBinding (registry digest inside the checksum-covered, hash-chained body)
TABLES=('motors','captures','events','rejections','decision_runs','app_units','recall_announcements')


class AnchorUnavailable(FileNotFoundError):
    """Preserve the missing-file contract without disclosing the host path."""
    code='PREFIX_MISMATCH'
    def __init__(self):super().__init__(self.code)


def consistent(index=0):
    """One SQLite cut even when verification is called outside an HTTP read."""
    def decorate(function):
        @wraps(function)
        def call(*args,**kwargs):
            app=args[index];owns=not app.db.in_transaction
            try:
                if owns:
                    app.db.execute('BEGIN IMMEDIATE');app.audit._verified_token=None
                result=function(*args,**kwargs)
                if owns:app.db.commit()
                return result
            except IntegrityFailure:
                if owns:app.db.rollback()
                raise
            except Exception:
                if owns:app.db.rollback()
                raise IntegrityFailure('CHECKPOINT_UNAVAILABLE') from None
            finally:
                if owns:app.audit._verified_token=None
        return call
    return decorate


def ledger_binding(app):
    # Actual row bytes are committed, including raw captures and repository time.
    rows={t:[digest([v.hex() if isinstance(v,bytes) else v for v in tuple(r)])
             for r in app.db.execute('SELECT * FROM '+t+' ORDER BY rowid')] for t in TABLES}
    heads={}
    for r in app.db.execute('SELECT motor,source,seq,hash FROM events ORDER BY ordinal'):
        heads[r['motor']+'|'+r['source']]=dict(sequence=r['seq'],hash=r['hash'])
    return dict(rows=rows,sourceHeads=heads)


def extends(current,old):
    return all(current['rows'].get(t,[])[:len(rows)]==rows for t,rows in old['rows'].items())


class BoundAnchor(dict):
    """The exported checkpoint carrying, out of band, the registry document in force at export (advisory sidecar content). Serialises exactly like a dict."""
    registry_document = None


def export_anchor(app, previous=None, version=3):
    if version not in (2,3):raise ValueError('checkpoint version')
    owns=not app.db.in_transaction
    if owns:app.db.execute('BEGIN IMMEDIATE')
    try:
        app.audit.verify_publications()
        for motor, in app.db.execute('SELECT serial FROM motors'):
            app.ledger.snapshot(motor,app.ledger.watermark(motor))
        if previous is not None:verify_anchor(app,previous,predecessor=True)
        if previous is not None and previous['body']['format']==FORMAT_V3 and version!=3:raise IntegrityFailure('PREFIX_MISMATCH')   # no downgrade
        body=export_v1(app)['body']
        body.update(format=FORMAT_V3 if version==3 else FORMAT_V2,verifierVersion=VERIFIER_VERSION,engineTreeId=ENGINE_TREE,
                    ledger=ledger_binding(app),previousCheckpointHash=digest(previous) if previous else None)
        if version==3:body['registryBinding']=registry_binding.binding_block(app.registry)
        result=BoundAnchor(body=body,checksum=digest(body))
        result.registry_document=copy.deepcopy(app.registry.document)
        if owns:app.db.commit()
        return result
    except Exception:
        if owns:app.db.rollback()
        raise


@consistent()
def verify_anchor(app,anchor,previous=None,cache=None,deadline=None,prefix_cache=None,predecessor=False):
    try:
        body=anchor['body']
        if set(anchor)!={'body','checksum'} or digest(body)!=anchor['checksum']:raise IntegrityFailure('PREFIX_MISMATCH')
        v3=body['format']==FORMAT_V3
        v2=body['format'] in (FORMAT_V2,FORMAT_V3)
        if v2:
            fields={'format','publicationProfile','hardeningProfile','archiveId','sequence','headHash','legacyDigest','policyDigest','state','verifierVersion','engineTreeId','ledger','previousCheckpointHash'}
            if v3:fields=fields|{'registryBinding'}
            if set(body)!=fields or body['verifierVersion']!=VERIFIER_VERSION or body['engineTreeId']!=ENGINE_TREE:raise IntegrityFailure('PREFIX_MISMATCH')
            if set(body['ledger'])!={'rows','sourceHeads'} or set(body['ledger']['rows'])!=set(TABLES):raise IntegrityFailure('PREFIX_MISMATCH')
            heads={}
            for row in app.db.execute('SELECT motor,source,seq,hash FROM events ORDER BY rowid LIMIT ?',
                                     (len(body['ledger']['rows']['events']),)):
                heads[row['motor']+'|'+row['source']]=dict(sequence=row['seq'],hash=row['hash'])
            if heads!=body['ledger']['sourceHeads']:raise IntegrityFailure('PREFIX_MISMATCH')
            policies=list(app.db.execute('SELECT policy FROM recall_announcements ORDER BY rowid LIMIT ?',
                          (len(body['ledger']['rows']['recall_announcements']),)))
            if digest(json.loads(policies[-1][0]) if policies else None)!=body['policyDigest']:raise IntegrityFailure('PREFIX_MISMATCH')
            if body['previousCheckpointHash'] is not None and previous is None and predecessor:
                pass  # verifying an already-linked predecessor on export: its own link is bound by hash into the successor
            elif body['previousCheckpointHash'] is not None:
                if previous is None or digest(previous)!=body['previousCheckpointHash']:raise IntegrityFailure('PREFIX_MISMATCH')
                p=previous['body']
                if digest(p)!=previous['checksum'] or p['archiveId']!=body['archiveId'] or p['sequence']>body['sequence']:raise IntegrityFailure('PREFIX_MISMATCH')
                if p['format'] not in (FORMAT,FORMAT_V2,FORMAT_V3) or p['publicationProfile']!=PROFILE or p['hardeningProfile']!=HARDENING_PROFILE:raise IntegrityFailure('PREFIX_MISMATCH')
                if p['format']==FORMAT_V3 and not v3:raise IntegrityFailure('PREFIX_MISMATCH')
                if p['format'] in (FORMAT_V2,FORMAT_V3) and (p['engineTreeId']!=ENGINE_TREE or p['verifierVersion']!=VERIFIER_VERSION):raise IntegrityFailure('PREFIX_MISMATCH')
                row=app.db.execute('SELECT hash FROM app_audit WHERE seq=?',(p['sequence'],)).fetchone()
                if row is None or row[0]!=p['headHash']:raise IntegrityFailure('PREFIX_MISMATCH')
                if p['format'] in (FORMAT_V2,FORMAT_V3) and not extends(body['ledger'],p['ledger']):raise IntegrityFailure('PREFIX_MISMATCH')
            elif previous is not None:raise IntegrityFailure('PREFIX_MISMATCH')
            if v3 and not registry_binding.valid_block(body['registryBinding']):raise IntegrityFailure('PREFIX_MISMATCH')
            old=dict(body);old['format']=FORMAT;old.pop('registryBinding',None)
            for key in ('verifierVersion','engineTreeId','ledger','previousCheckpointHash'):old.pop(key)
            old['policyDigest']=digest(None)
            # V1 validates identity and the journal prefix; v2 separately binds policy
            # additions as an extension, never as current checkpoint coverage.
            prefix=verify_v1(app,dict(body=old,checksum=digest(old)),replay_inputs=False,prefix_cache=prefix_cache)
            current=ledger_binding(app)
            if not extends(current,body['ledger']):raise IntegrityFailure('PREFIX_MISMATCH')
        elif body['format']==FORMAT:
            prefix=verify_v1(app,anchor,replay_inputs=False,prefix_cache=prefix_cache);current=None
        else:raise IntegrityFailure('PREFIX_MISMATCH')
        proof=app.audit.verify_publications(cache,deadline)
        state='ANCHORED_CURRENT' if v2 and current==body['ledger'] and prefix['sequence']==body['sequence'] and proof['status']=='VERIFIED' else 'ANCHORED_PREFIX_ONLY'
        return dict(prefix,state=state,h2=proof,status='VERIFIED_TRUSTED_PREFIX')
    except IntegrityFailure:raise
    except Exception:raise IntegrityFailure('PREFIX_MISMATCH') from None


def publish_candidate(path,anchor):
    """Stage and fsync, then publish without replacing any existing destination."""
    path=Path(path); staging=None
    try:
        fd,staging=tempfile.mkstemp(prefix='.checkpoint-',dir=path.parent)
        with os.fdopen(fd,'wb') as f:
            data=rfc8785.dumps(anchor)
            if f.write(data)!=len(data):raise OSError('CHECKPOINT_UNAVAILABLE')
            f.flush();os.fsync(f.fileno())
        os.link(staging,path)
        if getattr(anchor,'registry_document',None) is not None:
            registry_binding.write_binding(path,data,anchor.registry_document)   # advisory sidecar (field-level diff for the reviewer); never decides eligibility
    finally:
        if staging is not None:os.unlink(staging)


class TrustedAnchor:
    """Explicit owner-supplied reference, pinned for this server process.

    Pinning catches file replacement during this process; it does not establish
    original custody, or protect a restart with a substituted reference.
    """
    def __init__(self,path,previous=None):
        try:
            self.path=Path(path)
            self.bytes=self.path.read_bytes()
            self.anchor=json.loads(self.bytes)
            self.previous_path=Path(previous) if previous else None
            self.previous_bytes=self.previous_path.read_bytes() if previous else None
            self.previous=json.loads(self.previous_bytes) if previous else None
        except FileNotFoundError:raise AnchorUnavailable() from None
        except Exception:raise IntegrityFailure('PREFIX_MISMATCH') from None
        self.high=None
        self.cache=ReplayCache()
        self.prefix_cache={}

    @consistent(1)
    def verify(self,app,deadline=None):
        try:
            if deadline is None:deadline=time.monotonic()+1.25
            if self.path.read_bytes()!=self.bytes:
                raise IntegrityFailure('PREFIX_MISMATCH')
            if self.previous_path and self.previous_path.read_bytes()!=self.previous_bytes:raise IntegrityFailure('PREFIX_MISMATCH')
            now=ledger_binding(app)
            if self.high:
                sequence,head,binding=self.high
                row=app.db.execute('SELECT hash FROM app_audit WHERE seq=?',(sequence,)).fetchone()
                if row is None or row[0]!=head or not extends(now,binding):raise IntegrityFailure('ROLLBACK_DETECTED')
            result=verify_anchor(app,self.anchor,self.previous,self.cache,deadline,self.prefix_cache)
            self.high=(result['sequence'],result['headHash'],now)
            return result
        except IntegrityFailure:raise
        except Exception:raise IntegrityFailure('PREFIX_MISMATCH') from None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['export','verify'])
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--anchor','--trusted-anchor',dest='anchor',type=Path,required=True)
    parser.add_argument('--previous-anchor',type=Path)
    args=parser.parse_args()
    if not args.database.is_file(): parser.error('Existing database required; no implicit bootstrap')
    from .service import Manufacturing
    app=None
    try:
        app=Manufacturing(args.database)
        if args.operation=='export':
            app.snapshot()  # archive current results before committing publications
            previous=json.loads(args.previous_anchor.read_bytes()) if args.previous_anchor else None
            anchor=export_anchor(app,previous)
            publish_candidate(args.anchor,anchor)
            print('CANDIDATE_UNTRUSTED_UNTIL_OWNER_CUSTODY_ESTABLISHED')
        else:
            print(json.dumps(TrustedAnchor(args.anchor,args.previous_anchor).verify(app)))
    except IntegrityFailure as exc:
        print(exc.code,file=sys.stderr);raise SystemExit(1)
    except Exception:
        print('CHECKPOINT_UNAVAILABLE',file=sys.stderr);raise SystemExit(1)
    finally:
        if app is not None:app.close()


if __name__=='__main__': main()
