"""Application publication profile A31. Raw v3 exposure semantics are unchanged.

The journal is append-only, hash chained and checked against a separate head.
This detects missing/altered history, not an attacker rewriting the entire DB
and every anchor. Independent external anchoring is an operational follow-up.
"""
import copy
import json
import uuid

from pramaan_integration import engine_bridge, LedgerBlocked
from pramaan_integration.profile import digest

PROFILE = "APPLICATION_PUBLICATION_A31"


class Audit:
    def __init__(self, ledger):
        self.ledger, self.db = ledger, ledger.db
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
        self.verify()

    def legacy_digest(self):
        return digest([dict(r) for r in self.db.execute("SELECT * FROM decision_runs ORDER BY ordinal")])

    def verify(self):
        head = self.db.execute("SELECT * FROM app_audit_head WHERE id=1").fetchone()
        if not head or head['legacy_digest'] != self.legacy_digest():
            raise LedgerBlocked("Legacy decision history changed or anchor missing")
        previous, result = 'GENESIS', []
        for n, row in enumerate(self.db.execute("SELECT * FROM app_audit ORDER BY seq"), 1):
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
        return result

    def append(self, kind, payload):
        h = self.db.execute("SELECT count,hash FROM app_audit_head WHERE id=1").fetchone()
        seq = h['count']+1
        hashed = digest(dict(seq=seq, kind=kind, payload=payload, previous=h['hash']))
        self.db.execute("INSERT INTO app_audit VALUES(?,?,?,?,?)", (seq, kind, json.dumps(payload), h['hash'], hashed))
        self.db.execute("UPDATE app_audit_head SET count=?,hash=? WHERE id=1", (seq, hashed))

    def outstanding(self, records=None):
        records = self.verify() if records is None else records
        resolved = {p['obligationId'] for k,p in records if k == 'OBLIGATION_RESOLVED'}
        return [p for k,p in records if k == 'OBLIGATION_CREATED' and p['obligationId'] not in resolved]

    def decide(self, motor, policy):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            records = self.verify()
            wm = self.ledger.watermark(motor)
            case, manifest = self.ledger.snapshot(motor, wm)
            coverage = self.ledger._config(motor)['coverage']
            raw = engine_bridge.pramaan_recall.evaluate(case, copy.deepcopy(policy), coverage, wm, engine_bridge.Config.v3())
            context = dict(motor=motor, policyDigest=digest(policy), configurationDigest=manifest['configurationDigest'], profile=PROFILE)
            prior = [p for k,p in records if k == 'EVALUATION' and p['context'] == context]
            # Complete fresh kernel fields are material except receipt positions.
            # Uncited provenance-only claims are receipts, not decision revisions.
            material = {k:v for k,v in raw.items() if k != 'watermark'}
            previous = prior[-1]['decision'] if prior else None
            base_identity = digest(dict(context=context, manifest=manifest))
            created = None
            if previous and previous['evidenceFinding'] == 'EXCLUDED_WITH_EVIDENCE' and raw['evidenceFinding'] != 'EXCLUDED_WITH_EVIDENCE':
                created = dict(obligationId=digest(dict(context=context, prior=previous['decisionId'], trigger=base_identity)), unitId=motor,
                               required=True, reason='PRIOR_EXCLUSION_WITHDRAWN', appliesIfDecisionCommunicated=previous['decisionId'],
                               communicated=None, deliveryStatus='NOT_SENT', deliveryEvidence=None)
            pending = [p for p in self.outstanding(records) if p['unitId'] == motor]
            if created:
                pending.append(created)
            obligation_state = [p['obligationId'] for p in pending]
            fingerprint = digest(dict(kernel=material, outstandingObligations=obligation_state))
            identity = digest(dict(base=base_identity, outstandingObligations=obligation_state))
            if prior and prior[-1]['inputDigest'] == identity:
                self.db.commit()
                return prior[-1], [p['decision'] for p in prior if p['newVersion']]
            new = not prior or prior[-1]['materialDigest'] != fingerprint
            version = (previous['version']+1 if previous and new else previous['version'] if previous else 1)
            archive = self.db.execute("SELECT archive_id FROM app_audit_head WHERE id=1").fetchone()[0]
            decision = copy.deepcopy(raw)
            decision.update(decisionId=f"A31-{motor}-{context['policyDigest']}-{archive}-v{version}", version=version,
                            publicationProfile=PROFILE, supersedesDecisionId=previous['decisionId'] if previous and new else previous.get('supersedesDecisionId') if previous else None,
                            unchanged=not new, triggerEventId=None)
            if previous and new:
                before = next((p['manifest']['watermark'] for p in reversed(prior)), {})
                new_events = [e['eventId'] for e in case['events'] if e['sourceSeq'] > before.get(e['sourceId'],0) and e['eventType'] not in ('WORK_ORDER_OPENED','WORK_ORDER_CLOSED')]
                decision['triggerEventId'] = new_events[-1] if new_events else None
            if created:
                created['decisionId'] = decision['decisionId']
                self.append('OBLIGATION_CREATED', created)
            if pending and raw['evidenceFinding'] != 'EXCLUDED_WITH_EVIDENCE':
                decision.update(precautionaryHold=True, notificationObligation=pending[-1])
                if 'PRIOR_EXCLUSION_WITHDRAWN' not in decision['reasonCodes']:
                    decision['reasonCodes'].append('PRIOR_EXCLUSION_WITHDRAWN')
            entry = dict(context=context, inputDigest=identity, materialDigest=fingerprint, newVersion=new, raw=raw,
                         policy=copy.deepcopy(policy), manifest=manifest, decision=decision)
            self.append('EVALUATION', entry)
            self.db.commit()
            return entry, [p['decision'] for p in prior if p['newVersion']]+([decision] if new else [])
        except Exception:
            self.db.rollback()
            raise

    def resolve(self, obligation_id, *, principal, evidence_refs, reason, authorize=lambda principal: False):
        """Trusted control-plane boundary; no HTTP resolution endpoint/identity is invented.

        Default denies everyone. An integrating authenticated authority must supply
        the authorizer. Resolution records no delivery acknowledgement.
        """
        if not isinstance(principal,str) or not principal or not authorize(principal) or not isinstance(evidence_refs,list) or not evidence_refs or any(not isinstance(r,str) or not r for r in evidence_refs) or not isinstance(reason,str) or not reason.strip():
            raise PermissionError('Explicit authority, evidence and reason required')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            records=self.verify()
            obligation=next((p for p in self.outstanding(records) if p['obligationId']==obligation_id),None)
            if not obligation:
                raise ValueError('Outstanding obligation not found')
            known={e['eventId'] for _,e in self.ledger._verified_rows(obligation['unitId'])}
            if any(r not in known for r in evidence_refs):
                raise ValueError('Resolution evidence must reference archived events for this motor')
            self.append('OBLIGATION_RESOLVED', dict(obligationId=obligation_id, principal=principal, evidenceRefs=evidence_refs, reason=reason))
            self.db.commit()
        except Exception:
            self.db.rollback(); raise

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
