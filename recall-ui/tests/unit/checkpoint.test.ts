import {afterEach,expect,it,vi} from 'vitest';
import {verifyFreshness} from '../../src/data/freshness';
import {BackendRecallDataSource} from '../../src/data/RecallDataSource';
import {realSnapshot} from './helpers';
import type {RecallSnapshot} from '../../src/domain/types';

afterEach(()=>vi.unstubAllGlobals());
const causeOf=(fn:()=>unknown)=>{try{fn();return 'NO_THROW';}catch(e:any){return e.gate?.cause ?? e.message;}};
function strict(prefix=false):RecallSnapshot {
 const s=realSnapshot();
 s.freshness={verifiedAt:new Date().toISOString(),maxAgeSeconds:5,status:prefix?'VERIFIED_PREFIX_SYNTHETIC':'VERIFIED_ANCHORED_SYNTHETIC',archiveId:'test',sequence:10,headHash:'hash'};
 s.checkpoint={state:prefix?'ANCHORED_PREFIX_ONLY':'ANCHORED_CURRENT',anchoredSequence:10,checkpointRequired:prefix,h2:'VERIFIED'};
 s.eligibility=Object.fromEntries(s.units.map(u=>[u.unitId,{currentReleaseEligible:false}]));
 return s;
}
it('accepts verified prefix for hold visibility with every current eligibility withheld',()=>{
 // MIGRATED (M8): original = a verified prefix earned a lease so holds stayed visible. Conflicting approved contract:
 // owner display policy, PREFIX_ONLY is historical facts only (no current decisions/holds/clearance), so it never earns a
 // lease. R5 wording ("holds visible") is NOT amended here; the original is preserved in git history pending owner approval.
 const s=strict(true);expect(()=>verifyFreshness(s)).toThrow(/Historical evidence only/);
 s.eligibility![s.units[0].unitId].currentReleaseEligible=true;
 expect(causeOf(()=>verifyFreshness(s))).toBe('CONTRADICTORY');     // negative: eligibility inside PREFIX is refused outright
});
it('rejects contradictory state and missing replay proof',()=>{
 const s=strict();s.checkpoint!.h2='HISTORICAL_UNVERIFIABLE';expect(causeOf(()=>verifyFreshness(s))).toBe('CONTRADICTORY');   // M8: typed category replaces the 'H2' wording
 const p=strict(true);p.freshness!.status='VERIFIED_ANCHORED_SYNTHETIC';expect(causeOf(()=>verifyFreshness(p))).toBe('CONTRADICTORY');
});
it('never accepts a backend snapshot omitting strict checkpoint metadata',async()=>{
 const s=strict();delete s.checkpoint;
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,status:200,json:async()=>s}));
 // MIGRATED (M5): the message now comes from the shared gate (MISSING_METADATA); a snapshot without it is still never accepted.
 await expect(new BackendRecallDataSource().load()).rejects.toThrow(/checkpoint or eligibility metadata is missing/);
});
it('an outstanding obligation cannot be advertised as current release eligibility',()=>{
 const s=strict();const unit=s.units[0].unitId;
 s.eligibility![unit].currentReleaseEligible=true;
 s.notifications=[{unitId:unit,decisionId:'old',deliveryStatus:'NOT_SENT'} as NonNullable<RecallSnapshot['notifications']>[number]];
 expect(causeOf(()=>verifyFreshness(s))).toBe('CONTRADICTORY');   // M8: typed category replaces 'Unsafe'; the malformed obligation and the eligibility claim are both refused
});
