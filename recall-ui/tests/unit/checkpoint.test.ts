import {afterEach,expect,it,vi} from 'vitest';
import {verifyFreshness} from '../../src/data/freshness';
import {BackendRecallDataSource} from '../../src/data/RecallDataSource';
import {realSnapshot} from './helpers';
import type {RecallSnapshot} from '../../src/domain/types';

afterEach(()=>vi.unstubAllGlobals());
function strict(prefix=false):RecallSnapshot {
 const s=realSnapshot();
 s.freshness={verifiedAt:new Date().toISOString(),maxAgeSeconds:5,status:prefix?'VERIFIED_PREFIX_SYNTHETIC':'VERIFIED_ANCHORED_SYNTHETIC',archiveId:'test',sequence:10,headHash:'hash'};
 s.checkpoint={state:prefix?'ANCHORED_PREFIX_ONLY':'ANCHORED_CURRENT',anchoredSequence:10,checkpointRequired:prefix,h2:'VERIFIED'};
 s.eligibility=Object.fromEntries(s.units.map(u=>[u.unitId,{currentReleaseEligible:false}]));
 return s;
}
it('accepts verified prefix for hold visibility with every current eligibility withheld',()=>{
 const s=strict(true);expect(verifyFreshness(s)).toBeGreaterThan(0);
 s.eligibility![s.units[0].unitId].currentReleaseEligible=true;
 expect(()=>verifyFreshness(s)).toThrow(/Unsafe/);
});
it('rejects contradictory state and missing replay proof',()=>{
 const s=strict();s.checkpoint!.h2='HISTORICAL_UNVERIFIABLE';expect(()=>verifyFreshness(s)).toThrow(/H2/);
 const p=strict(true);p.freshness!.status='VERIFIED_ANCHORED_SYNTHETIC';expect(()=>verifyFreshness(p)).toThrow(/Contradictory/);
});
it('never accepts a backend snapshot omitting strict checkpoint metadata',async()=>{
 const s=strict();delete s.checkpoint;
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>s}));
 await expect(new BackendRecallDataSource().load()).rejects.toThrow(/Strict checkpoint/);
});
it('an outstanding obligation cannot be advertised as current release eligibility',()=>{
 const s=strict();const unit=s.units[0].unitId;
 s.eligibility![unit].currentReleaseEligible=true;
 s.notifications=[{unitId:unit,decisionId:'old',deliveryStatus:'NOT_SENT'} as NonNullable<RecallSnapshot['notifications']>[number]];
 expect(()=>verifyFreshness(s)).toThrow(/Unsafe/);
});
