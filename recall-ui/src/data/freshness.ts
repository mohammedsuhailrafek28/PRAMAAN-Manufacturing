import type { RecallSnapshot } from '../domain/types';

/** Bounded local freshness, not cryptographic proxy anti-replay. Clocks must
 * agree within 1s; ambiguous skew fails closed. The lease is never >5s. */
export function verifyFreshness(snap: RecallSnapshot, previous?: RecallSnapshot | null, now = Date.now()): number {
  const f = snap.freshness;
  if (!f || !['VERIFIED_ANCHORED_SYNTHETIC','VERIFIED_PREFIX_SYNTHETIC'].includes(f.status)) throw new Error('Current verification unavailable: trusted external anchor required. Decisions are historical.');
  if (snap.checkpoint) {
    const c=snap.checkpoint;
    if (c.state !== 'ANCHORED_CURRENT' && c.state !== 'ANCHORED_PREFIX_ONLY') throw new Error('Checkpoint invalid or unavailable');
    if ((c.state === 'ANCHORED_CURRENT') !== (f.status === 'VERIFIED_ANCHORED_SYNTHETIC') || c.checkpointRequired !== (c.state !== 'ANCHORED_CURRENT')) throw new Error('Contradictory checkpoint state');
    if (c.state === 'ANCHORED_CURRENT' && c.h2 !== 'VERIFIED') throw new Error('H2 replay proof unavailable');
    if (!snap.eligibility) throw new Error('Current eligibility projection unavailable');
    for (const unit of snap.units) {
      const eligible=snap.eligibility[unit.unitId]?.currentReleaseEligible;
      if (typeof eligible !== 'boolean') throw new Error('Missing motor eligibility');
      if (eligible && (c.state !== 'ANCHORED_CURRENT' || snap.notifications?.some(n=>n.unitId===unit.unitId) || !Object.values(snap.decisions[unit.unitId] ?? {}).length || Object.values(snap.decisions[unit.unitId] ?? {}).some(b=>b.current.operationalAction!=='RELEASE_ELIGIBLE'))) throw new Error('Unsafe eligibility projection');
    }
  }
  const at = Date.parse(f.verifiedAt);
  const age = now - at;
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,3})?Z$/.test(f.verifiedAt) || !Number.isFinite(at) || !Number.isFinite(f.maxAgeSeconds) || f.maxAgeSeconds <= 0 || f.maxAgeSeconds > 5 || age < -1000 || age >= f.maxAgeSeconds * 1000)
    throw new Error('Server freshness expired or client/server clock skew is ambiguous. Decisions are historical.');
  if (!f.archiveId || !f.headHash || !Number.isSafeInteger(f.sequence) || f.sequence < 1) throw new Error('Invalid snapshot journal version');
  const old = previous?.freshness;
  if (old) {
    if (f.archiveId !== old.archiveId || f.sequence < old.sequence || (f.sequence === old.sequence && f.headHash !== old.headHash) || at < Date.parse(old.verifiedAt))
      throw new Error('Snapshot archive/version regression; reload requires owner review');
    for (const unit of previous!.units) {
      const next = snap.units.find(u => u.unitId === unit.unitId);
      if (!next) throw new Error('Snapshot motor regression');
      for (const event of unit.events) {
        if (!next.events.some(e => e.eventId === event.eventId && e.sourceId === event.sourceId && e.sourceSeq === event.sourceSeq))
          throw new Error('Snapshot evidence watermark regression');
      }
      for (const [policy, bundle] of Object.entries(previous!.decisions[unit.unitId] ?? {})) {
        const current = snap.decisions[unit.unitId]?.[policy]?.current;
        if (!current || typeof current.version !== 'number' || typeof bundle.current.version !== 'number' || current.version < bundle.current.version || (current.version === bundle.current.version && current.decisionId !== bundle.current.decisionId))
          throw new Error('Snapshot decision version regression');
      }
    }
  }
  return Math.min(5000, f.maxAgeSeconds * 1000 - Math.max(0, age));
}
