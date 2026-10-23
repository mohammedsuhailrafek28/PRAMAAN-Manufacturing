import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import {describe,it,expect} from 'vitest';
import {evaluateEnvelope,isCurrentRelease} from '../../src/contract/gate';
import {makePreview,isPreview,isGated} from '../../src/contract/gated';
import {projectImpact,projectInvestigation} from '../../src/contract/views';
import {passportUrl} from '../../src/passport/qr';

function fixture(name='current'):any {
 const e=JSON.parse(readFileSync(join(__dirname,'../fixtures/h1h2',name+'.json'),'utf8'));
 if(e.body.freshness.maxAgeSeconds>0)e.body.freshness.verifiedAt=new Date().toISOString();
 return e;
}
describe('independent frontend audit challenges',()=>{
 it('control: actual captured current metadata clears only the eligible motor',()=>{
  const e=fixture();const g=evaluateEnvelope(e,null);
  expect(g.kind).toBe('CURRENT');expect(isCurrentRelease(g,'MTR-26003')).toBe(true);
  expect(isCurrentRelease(g,'MTR-26001')).toBe(false);
 });
 it('duplicate unit identities cannot satisfy an eligibility-map cardinality check',()=>{
  const e=fixture();const b=e.body;b.units.push(structuredClone(b.units[0]));
  b.eligibility['UNKNOWN-UNIT']={currentReleaseEligible:false};
  expect(evaluateEnvelope(e,null).kind).toBe('WITHHELD');
 });
 it('a hidden contradictory decision cannot evade validation through an empty policy list',()=>{
  const e=fixture();e.body.policies=[];
  Object.values(e.body.decisions['MTR-26003']).forEach((bundle:any)=>bundle.current.evidenceFinding='AFFECTED');
  expect(evaluateEnvelope(e,null).kind).toBe('WITHHELD');
 });
 it('a malformed obligation with no motor identity cannot be treated as irrelevant',()=>{
  const e=fixture();e.body.notifications=[{required:true,reason:'PRIOR_EXCLUSION_WITHDRAWN',obligationId:'AUDIT-OB'}];
  expect(evaluateEnvelope(e,null).kind).toBe('WITHHELD');
 });
 it('one non-cleared motor does not downgrade a different eligible motor',()=>{
  const e=fixture();e.body.eligibility['MTR-26001'].currentReleaseEligible=false;
  const g=evaluateEnvelope(e,null);expect(g.kind).toBe('CURRENT');
  expect(isCurrentRelease(g,'MTR-26003')).toBe(true);
 });
 it('prefix-only cannot become a current or task-bearing view',()=>{
  const g=evaluateEnvelope(fixture('prefix_only'),null);expect(g.kind).toBe('SEGREGATED');
  if(g.kind==='SEGREGATED')expect(()=>projectInvestigation(g.view as never)).toThrow();
  expect(isCurrentRelease(g,'MTR-26003')).toBe(false);
 });
 it('unknown checkpoint state is withheld regardless of otherwise valid metadata',()=>{
  const e=fixture();e.body.checkpoint.state='ANCHORED_CURRENT_NEXT';
  expect(evaluateEnvelope(e,null).kind).toBe('WITHHELD');
 });
 it('a preview strips forged trust metadata and cannot be cast into a current graph',()=>{
  const e=fixture();const p=makePreview(e.body,'Explicit synthetic preview');
  expect(isPreview(p)).toBe(true);expect(isGated(p)).toBe(false);
  expect(p.facts).not.toHaveProperty('checkpoint',expect.anything());
  expect(()=>projectImpact(p,{kind:'BEARING_LOT',id:'BR-310'},{mode:'current'})).toThrow();
 });
 it('QR removes URL userinfo in addition to query and fragment credentials',()=>{
  const url=passportUrl('MTR-26003','https://operator:private-password@example.invalid/passport.html?token=private-query#old');
  expect(url).toBe('https://example.invalid/passport.html#/passport/MTR-26003');
 });
 it('a recorded shipment edge cannot name a different shipment than its cited event',()=>{
  const e=fixture();const b=e.body;const unit=b.units.find((u:any)=>u.unitId==='MTR-26003');
  expect(unit.shipment).toBeTruthy();unit.shipment.shipmentId='AUDIT-FORGED-SHIPMENT';
  const g=evaluateEnvelope(e,null);expect(g.kind).toBe('CURRENT');
  if(g.kind==='CURRENT'){
   const graph=projectImpact(g.view,{kind:'BEARING_LOT',id:'BR-310'},{mode:'current'});
   expect(graph.nodes.some(n=>n.kind==='SHIPMENT' && n.label==='AUDIT-FORGED-SHIPMENT')).toBe(false);
  }
 });
});
