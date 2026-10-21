import { expect,it } from 'vitest';
import { verifyFreshness } from '../../src/data/freshness';
import {realSnapshot} from './helpers';

const now=Date.parse('2026-10-21T16:00:00Z');
function fresh(){return {...realSnapshot(),freshness:{verifiedAt:new Date(now).toISOString(),maxAgeSeconds:5,status:'VERIFIED_ANCHORED_SYNTHETIC',archiveId:'archive',sequence:10,headHash:'hash'}};}
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
 s.units[0].events.pop();expect(()=>verifyFreshness(s,previous,now)).toThrow(/watermark/);
 const d=fresh();d.freshness.sequence++;
 const motor=Object.keys(d.decisions)[0],policy=Object.keys(d.decisions[motor])[0];
 d.decisions[motor][policy].current.version=(d.decisions[motor][policy].current.version ?? 1)-1;
 expect(()=>verifyFreshness(d,previous,now)).toThrow(/version/);
});
