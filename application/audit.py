"""Application publication profile A31. Raw v3 exposure semantics are unchanged.

The journal is append-only, hash chained and checked against a separate head.
Current clearance additionally requires a separately owner-protected checkpoint
and in-process H2 replay proof. Replacing the host and trusted custody together
is outside that protection.
"""
import copy
import json
import uuid
import time
import hashlib

from pramaan_integration import engine_bridge, LedgerBlocked
from pramaan_integration.profile import digest

PROFILE = "APPLICATION_PUBLICATION_A31"
VERIFIER_VERSION = 'H2_REPLAY_V1'
ENGINE_TREE = '22d205d5b2d42e609e8b872c564c7283ffd758e9'


class IntegrityFailure(LedgerBlocked):
    """Only fixed reason codes cross the API/CLI boundary."""
    def __init__(self, code='EXTENSION_INVALID'):
        self.code=code
        super().__init__(code)


class Verifying(IntegrityFailure):
    def __init__(self): super().__init__('VERIFYING')


def derive_publication(case, manifest, policy, raw, prior, obligations, archive):
    """Pure A31 publication derivation; original issued A31 semantics retained."""
    context=dict(motor=case['caseId'],policyDigest=digest(policy),configurationDigest=manifest['configurationDigest'],profile=PROFILE)
    previous=prior[-1]['decision'] if prior else None
    base_identity=digest(dict(context=context,manifest=manifest))
    created=None
    if previous and previous['evidenceFinding']=='EXCLUDED_WITH_EVIDENCE' and raw['evidenceFinding']!='EXCLUDED_WITH_EVIDENCE':
        created=dict(obligationId=digest(dict(context=context,prior=previous['decisionId'],trigger=base_identity)),unitId=context['motor'],
                     required=True,reason='PRIOR_EXCLUSION_WITHDRAWN',appliesIfDecisionCommunicated=previous['decisionId'],
                     communicated=None,deliveryStatus='NOT_SENT',deliveryEvidence=None)
    pending=[p for p in obligations if p['unitId']==context['motor']]+([created] if created else [])
    ids=[p['obligationId'] for p in pending]
    fingerprint=digest(dict(kernel={k:v for k,v in raw.items() if k!='watermark'},outstandingObligations=ids))
    identity=digest(dict(base=base_identity,outstandingObligations=ids))
    if prior and prior[-1]['inputDigest']==identity:return copy.deepcopy(prior[-1]),None,True
    new=not prior or prior[-1]['materialDigest']!=fingerprint
    version=previous['version']+1 if previous and new else previous['version'] if previous else 1
    decision=copy.deepcopy(raw)
    decision.update(decisionId=f"A31-{context['motor']}-{context['policyDigest']}-{archive}-v{version}",version=version,
                    publicationProfile=PROFILE,supersedesDecisionId=previous['decisionId'] if previous and new else previous.get('supersedesDecisionId') if previous else None,
                    unchanged=not new,triggerEventId=None)
    if previous and new:
        before=prior[-1]['manifest']['watermark']
        events=[e['eventId'] for e in case['events'] if e['sourceSeq']>before.get(e['sourceId'],0) and e['eventType'] not in ('WORK_ORDER_OPENED','WORK_ORDER_CLOSED')]
        decision['triggerEventId']=events[-1] if events else None
    if created:created['decisionId']=decision['decisionId']
    if pending and raw['evidenceFinding']!='EXCLUDED_WITH_EVIDENCE':
        decision.update(precautionaryHold=True,notificationObligation=pending[-1])
        if 'PRIOR_EXCLUSION_WITHDRAWN' not in decision['reasonCodes']:decision['reasonCodes'].append('PRIOR_EXCLUSION_WITHDRAWN')
    return dict(context=context,inputDigest=identity,materialDigest=fingerprint,newVersion=new,raw=copy.deepcopy(raw),
                policy=copy.deepcopy(policy),manifest=copy.deepcopy(manifest),decision=decision),created,False


class ReplayCache:
    """Process-local progress tied to full evidence/journal bytes, never just a head."""
    def __init__(self):self.key=None;self.source_checked=False
    def reset(self,key):
        self.key=key;self.index=0;self.priors={};self.obligations=[];self.pair=None;self.legacy=False;self.verified=set();self.motor_wm={}


class Audit:
    def __init__(self, ledger, *, journal_cache=None, deadline=None):
        self.ledger, self.db = ledger, ledger.db
        self.journal_cache=journal_cache
        version=self.db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0,31):
            raise LedgerBlocked('Unsupported application database version')
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS app_audit_head(id INTEGER PRIMARY KEY CHECK(id=1), archive_id TEXT NOT NULL, count INTEGER NOT NULL, hash TEXT NOT NULL, legacy_digest TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS app_audit(seq INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, previous TEXT NOT NULL, hash TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS app_audit_no_update BEFORE UPDATE ON app_audit BEGIN SELECT RAISE(ABORT,'immutable application history'); END;
        CREATE TRIGGER IF NOT EXISTS app_audit_no_delete BEFORE DELETE ON app_audit BEGIN SELECT RAISE(ABORT,'immutable application history'); END;
        CREATE TRIGGER IF NOT EXISTS app_audit_head_no_delete BEFORE DELETE ON app_audit_head BEGIN SELECT RAISE(ABORT,'history anchor cannot be deleted'); END;
        """)
        # A missing anchor with surviving history is corruption, never a reset.
        if not self.db.execute("SELECT 1 FROM app_audit_head").fetchone():
            if version==31 or self.db.execute("SELECT 1 FROM app_audit").fetchone():
                raise LedgerBlocked("Application history anchor missing")
            self.db.execute("INSERT INTO app_audit_head VALUES(1,?,0,'GENESIS',?)", (uuid.uuid4().hex, self.legacy_digest()))
            h=self.db.execute('SELECT * FROM app_audit_head WHERE id=1').fetchone()
            self.append('ARCHIVE_CREATED',dict(archiveId=h['archive_id'], legacyDigest=h['legacy_digest'], profile=PROFILE))
        self.db.execute('PRAGMA user_version=31')
        self.db.commit()
        self.verify(copy_records=False,deadline=deadline)

    def legacy_digest(self):
        return digest([dict(r) for r in self.db.execute("SELECT * FROM decision_runs ORDER BY ordinal")])

    def journal_bytes_key(self):
        # Fast commitment to actual serialized bytes, not a database-provided
        # digest. This cache only accelerates structural journal verification;
        # H2 separately binds all ledger inputs and re-derives publications.
        h=hashlib.sha256()
        for table,order in (('app_audit','seq'),('app_audit_head','id'),('decision_runs','ordinal')):
            for row in self.db.execute('SELECT * FROM '+table+' ORDER BY '+order):
                data=json.dumps(tuple(row),ensure_ascii=True,separators=(',',':')).encode()
                h.update(len(data).to_bytes(8,'big'));h.update(data)
            h.update(b'END_TABLE')
        return h.hexdigest()

    def verify(self, *, copy_records=True, deadline=None):
        token=(self.db.total_changes,self.db.execute('PRAGMA data_version').fetchone()[0])
        if self.db.in_transaction and getattr(self,'_verified_token',None)==token:
            return copy.deepcopy(self._verified_records) if copy_records else self._verified_records
        raw_key=self.journal_bytes_key()
        if getattr(self,'_verified_raw_key',None)==raw_key:
            self._verified_token=token
            return copy.deepcopy(self._verified_records) if copy_records else self._verified_records
        if self.journal_cache is not None and self.journal_cache.get('key')==raw_key:
            # Parse actual current bytes; the shared cache contains no mutable
            # decision objects and only attests unchanged structural bytes.
            result=[(r['kind'],json.loads(r['payload'])) for r in self.db.execute('SELECT kind,payload FROM app_audit ORDER BY seq')]
            self._verified_token=token;self._verified_records=result;self._verified_raw_key=raw_key
            return copy.deepcopy(result) if copy_records else result
        head = self.db.execute("SELECT * FROM app_audit_head WHERE id=1").fetchone()
        if not head or head['legacy_digest'] != self.legacy_digest():
            raise LedgerBlocked("Legacy decision history changed or anchor missing")
        previous, result = 'GENESIS', []
        for n, row in enumerate(self.db.execute("SELECT * FROM app_audit ORDER BY seq"), 1):
            if deadline is not None and time.monotonic()>=deadline:raise Verifying()
            try:
                p = json.loads(row['payload'])
            except (ValueError,TypeError) as exc:
                raise LedgerBlocked('Invalid application audit payload') from exc
            h = digest(dict(seq=n, kind=row['kind'], payload=p, previous=previous))
            if row['seq'] != n or row['previous'] != previous or row['hash'] != h:
                raise LedgerBlocked("Application decision/obligation journal changed")
            result.append((row['kind'], p)); previous = h
        if head['count'] != len(result) or head['hash'] != previous:
            raise LedgerBlocked("Application decision history missing, truncated or changed")
        if not result or result[0] != ('ARCHIVE_CREATED',dict(archiveId=head['archive_id'],legacyDigest=head['legacy_digest'],profile=PROFILE)):
            raise LedgerBlocked('Application archive identity/legacy anchor changed')
        self._verified_token=token;self._verified_records=result
        self._verified_raw_key=raw_key
        if self.journal_cache is not None:self.journal_cache['key']=raw_key
        return copy.deepcopy(result) if copy_records else result

    def append(self, kind, payload):
        token=(self.db.total_changes,self.db.execute('PRAGMA data_version').fetchone()[0])
        cached=getattr(self,'_verified_token',None)==token
        h = self.db.execute("SELECT count,hash FROM app_audit_head WHERE id=1").fetchone()
        seq = h['count']+1
        hashed = digest(dict(seq=seq, kind=kind, payload=payload, previous=h['hash']))
        self.db.execute("INSERT INTO app_audit VALUES(?,?,?,?,?)", (seq, kind, json.dumps(payload), h['hash'], hashed))
        self.db.execute("UPDATE app_audit_head SET count=?,hash=? WHERE id=1", (seq, hashed))
        if cached:
            self._verified_records.append((kind,copy.deepcopy(payload)))
            self._verified_token=(self.db.total_changes,token[1])
            self._verified_raw_key=self.journal_bytes_key()
            if self.journal_cache is not None:self.journal_cache['key']=self._verified_raw_key

    def outstanding(self, records=None):
        records = self.verify(copy_records=False) if records is None else records
        # No independently authenticated resolution exists in this prototype.
        # Retain old RESOLVED entries as historical claims, not authority to
        # suppress a pending obligation. Historical decision replay is unchanged.
        return copy.deepcopy([p for k,p in records if k == 'OBLIGATION_CREATED'])

    def decide(self, motor, policy):
        owns = not self.db.in_transaction
        if owns: self.db.execute("BEGIN IMMEDIATE")
        try:
            records = self.verify(copy_records=False)
            wm = self.ledger.watermark(motor)
            case, manifest = self.ledger.snapshot(motor, wm)
            coverage = self.ledger._config(motor)['coverage']
            raw = engine_bridge.pramaan_recall.evaluate(case, copy.deepcopy(policy), coverage, wm, engine_bridge.Config.v3())
            context = dict(motor=motor, policyDigest=digest(policy), configurationDigest=manifest['configurationDigest'], profile=PROFILE)
            # Legacy manifest-less rows remain historical journal evidence; they cannot seed derivation (H2 skips them identically).
            prior = [p for k,p in records if k == 'EVALUATION' and 'manifest' in p and p['context'] == context]
            archive = self.db.execute("SELECT archive_id FROM app_audit_head WHERE id=1").fetchone()[0]
            entry, created, reused = derive_publication(case, manifest, policy, raw, prior,
                                                       self.outstanding(records), archive)
            if reused:
                if owns: self.db.commit()
                return entry, copy.deepcopy([p['decision'] for p in prior if p['newVersion']])
            if created: self.append('OBLIGATION_CREATED', created)
            self.append('EVALUATION', entry)
            if owns: self.db.commit()
            return entry, copy.deepcopy([p['decision'] for p in prior if p['newVersion']]+([entry['decision']] if entry['newVersion'] else []))
        except Exception:
            if owns: self.db.rollback()
            raise

    def resolve(self, *args, **kwargs):
        """Disabled. Historical resolution entries replay, but no new resolution
        is authorized by caller-provided principal, callback or demo identity.
        """
        raise PermissionError('Notification resolution disabled pending authenticated identity and authorization')

    def verify_publications(self, cache=None, deadline=None):
        """Re-derive complete publications, not merely their raw kernel verdicts.

        Call while holding a consistent SQLite transaction. Cache keys include
        actual database contents; rewriting a claimed head cannot reuse a proof.
        Legacy rows remain historical and do not acquire a replay proof.
        """
        try:
            records=self.verify(copy_records=False)
            tables=('motors','captures','events','rejections','decision_runs','app_units','recall_announcements','app_audit','app_audit_head')
            contents={t:[[v.hex() if isinstance(v,bytes) else v for v in tuple(r)]
                         for r in self.db.execute('SELECT * FROM '+t+' ORDER BY rowid')] for t in tables}
            key=hashlib.sha256(json.dumps(dict(contents=contents,verifier=VERIFIER_VERSION,engine=ENGINE_TREE,profile=PROFILE),
                                         sort_keys=True,separators=(',',':')).encode()).hexdigest()
            cache=cache if cache is not None else ReplayCache()
            if cache.key!=key:cache.reset(key)
            archive=self.db.execute('SELECT archive_id FROM app_audit_head WHERE id=1').fetchone()[0]
            # D5: the only authority for a policy is an immutable recall_announcements row whose stored hash matches its content.
            announced=set()
            for row in self.db.execute('SELECT policy,hash FROM recall_announcements'):
                policy_row=json.loads(row[0])
                if digest(policy_row)!=row[1]:raise IntegrityFailure('POLICY_NOT_ANNOUNCED')
                announced.add(row[1])
            ledger_wm={}
            while cache.index<len(records):
                if deadline is not None and time.monotonic()>=deadline:raise Verifying()
                kind,p=records[cache.index]
                if kind=='ARCHIVE_CREATED':
                    if cache.index!=0 or cache.pair is not None:raise IntegrityFailure()
                elif kind=='OBLIGATION_CREATED':
                    if cache.pair is not None:raise IntegrityFailure()
                    cache.pair=p
                elif kind=='OBLIGATION_RESOLVED':raise IntegrityFailure('RESOLUTION_FORBIDDEN')
                elif kind=='EVALUATION':
                    if 'manifest' not in p:
                        if cache.pair is not None:raise IntegrityFailure()
                        cache.legacy=True
                    else:
                        motor=p['context']['motor']
                        case,manifest=self.ledger.snapshot(motor,p['manifest']['watermark'])
                        if manifest!=p['manifest']:raise IntegrityFailure()
                        if digest(p['policy']) not in announced:raise IntegrityFailure('POLICY_NOT_ANNOUNCED')
                        # D5: a publication is evaluated at the ledger's receipt position at that time. Positions only grow, so it can
                        # neither precede the motor's earlier publication nor exceed what the ledger holds now.
                        wm=manifest['watermark']
                        earlier=cache.motor_wm.get(motor)
                        if earlier is not None and any(wm.get(src,0)<seq for src,seq in earlier.items()):raise IntegrityFailure('WATERMARK_REGRESSION')
                        if motor not in ledger_wm:ledger_wm[motor]=self.ledger.watermark(motor)
                        if any(seq>ledger_wm[motor].get(src,0) for src,seq in wm.items()):raise IntegrityFailure('WATERMARK_BEYOND_LEDGER')
                        cache.motor_wm[motor]=copy.deepcopy(wm)
                        config=self.ledger._config(motor)
                        raw=engine_bridge.pramaan_recall.evaluate(case,copy.deepcopy(p['policy']),config['coverage'],manifest['watermark'],engine_bridge.Config.v3())
                        context=dict(motor=motor,policyDigest=digest(p['policy']),configurationDigest=digest(config),profile=PROFILE)
                        ctx=digest(context)
                        prior=cache.priors.get(ctx,[])
                        expected,created,reused=derive_publication(case,manifest,p['policy'],raw,prior,cache.obligations,archive)
                        if reused or digest(expected)!=digest(p) or digest(created)!=digest(cache.pair):raise IntegrityFailure()
                        if created:cache.obligations.append(created)
                        cache.pair=None
                        cache.priors.setdefault(ctx,[]).append(p)
                        cache.verified.add(p['inputDigest'])
                else:raise IntegrityFailure()
                cache.index+=1
            if cache.pair is not None:raise IntegrityFailure()
            return dict(status='HISTORICAL_UNVERIFIABLE' if cache.legacy else 'VERIFIED',
                        verifiedInputs=sorted(cache.verified),verifierVersion=VERIFIER_VERSION)
        except (IntegrityFailure,Verifying):raise
        except Exception:
            raise IntegrityFailure() from None

    def replay(self, entry):
        records=self.verify()
        if not any(k=='EVALUATION' and p==entry for k,p in records):
            raise LedgerBlocked('Unissued application decision')
        case, manifest=self.ledger.snapshot(entry['context']['motor'],entry['manifest']['watermark'])
        if manifest != entry['manifest'] or digest(entry['policy']) != entry['context']['policyDigest']:
            raise LedgerBlocked('Application replay input drift')
        result=engine_bridge.replay(case,entry['policy'],self.ledger._config(entry['context']['motor'])['coverage'],entry['raw'])
        if result != entry['raw']:
            raise LedgerBlocked('Application raw decision replay differs')
        return copy.deepcopy(entry['decision'])
