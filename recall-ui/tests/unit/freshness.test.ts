import { expect,it } from 'vitest';
import { verifyFreshness } from '../../src/data/freshness';
import {realSnapshot, withStrictCurrent} from './helpers';

const causeOf=(fn:()=>unknown)=>{try{fn();return 'NO_THROW';}catch(e:any){return e.gate?.cause ?? e.message;}};

const now=Date.parse('2026-10-21T16:00:00Z');
// MIGRATED FIXTURE (M1): honest strict-current checkpoint/eligibility metadata added; assertions unchanged.
function fresh():any{return withStrictCurrent({...realSnapshot(),freshness:{verifiedAt:new Date(now).toISOString(),maxAgeSeconds:5,status:'VERIFIED_ANCHORED_SYNTHETIC',archiveId:'archive',sequence:10,headHash:"hash"}} as any,10);}
it('accepts current timestamp and budgets only remaining server lease',()=>{
 expect(verifyFreshness(fresh(),null,now+3000)).toBe(2000);
});
it('rejects old, invalid, future/skewed, unanchored and absent metadata',()=>{
 for(const verifiedAt of ['invalid',new Date(now-5001).toISOString(),new Date(now+2000).toISOString()]){
  const s=fresh();s.freshness.verifiedAt=verifiedAt;expect(()=>verifyFreshness(s,null,now)).toThrow();
 }
 expect(()=>verifyFreshness(realSnapshot(),null,now)).toThrow();
 const s=fresh();s.freshness.status='HISTORICAL_UNANCHORED';expect(()=>verifyFreshness(s,null,now)).toThrow();
});
it('rejects journal rollback, same sequence rewrite, and replaced archive',()=>{
 const previous=fresh();
 for(const change of [{sequence:9},{headHash:'replaced'},{archiveId:'other'}]){
  const s=fresh();Object.assign(s.freshness,change);expect(()=>verifyFreshness(s,previous,now)).toThrow();
 }
});
it('rejects evidence watermark and decision version regression',()=>{
 const previous=fresh();const s=fresh();s.freshness.sequence++;
 s.units[0].events.pop();expect(causeOf(()=>verifyFreshness(s,previous,now))).toBe('REGRESSION');   // MIGRATED (M7): typed category replaces the 'watermark' wording
 const d=fresh();d.freshness.sequence++;
 const motor=Object.keys(d.decisions)[0],policy=Object.keys(d.decisions[motor])[0];
 d.decisions[motor][policy].current.version=(d.decisions[motor][policy].current.version ?? 1)-1;
 expect(causeOf(()=>verifyFreshness(d,previous,now))).toBe('REGRESSION');   // MIGRATED (M7): typed category replaces the 'version' wording
});
