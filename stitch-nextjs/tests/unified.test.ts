import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { correctiveEvents, confirmationEvents, assuranceOf, pairOf } from "../src/dash/trailModel";
import { allRows, buildReport, changesOf, kpisOf, dayOf } from "../src/dash/reportModel";
import { buildDailyPdf } from "../src/dash/reportPdf";
import { flatEvents, qcStates, completeness } from "../src/dash/eda";
import type { Snapshot, DecisionCurrent } from "../src/dash/types";
import { evaluateEnvelope } from "../src/orig/contract/gate";

const load = (name: string): Snapshot => JSON.parse(readFileSync(resolve(process.env.PRAMAAN_COMPAT_FIXTURES!, name + '.json'), 'utf8'));
const manufacturing = load('manufacturing-current'), five = load('five-current');
const total = (s: Snapshot) => s.units.reduce((n,u) => n+(u.events?.length ?? 0),0);
const date = (s: Snapshot, basis: 'source' | 'ingest') => allRows(s,basis).filter(r => r.day).at(-1)!.day!;

test('one backend contract supplies both separate 47-event manufacturing and 58-event five-motor scenarios', () => {
  assert.equal(manufacturing.units.length,9);assert.equal(total(manufacturing),47);
  assert.equal(five.units.length,5);assert.equal(total(five),58);
  assert.equal(manufacturing.units.some(u => five.units.some(f => f.unitId===u.unitId)),false);
  const rows=[['manufacturing',manufacturing],['five',five]] as const;
  const summary=Object.fromEntries(rows.map(([name,s])=>[name,{motors:s.units.length,events:total(s),
    sourceDays:buildReport(s,'','source',false).dates,ingestionDays:buildReport(s,'','ingest',false).dates,
    findings:Object.fromEntries(s.units.map(u=>[u.unitId,Object.values(s.decisions[u.unitId])[0].current.evidenceFinding]))}]));
  writeFileSync(resolve(process.env.PRAMAAN_TEST_ARTIFACTS!,'dataset-summary.json'),JSON.stringify(summary,null,2)+'\n');
});

test('EDA recognizes actual native QC PASS without granting recall clearance or filling missing inspections', () => {
  const f=flatEvents(manufacturing),q=qcStates(manufacturing,f);
  assert.equal(q.PASS,1);assert.equal(q.FAIL,0);assert.equal(q.NO_RECORD,8);
  const d=Object.values(manufacturing.decisions['MTR-27002'])[0].current;
  assert.equal(d.evidenceFinding,'AFFECTED');assert.equal(d.operationalAction,'RECALL_HOLD');
  assert.equal(qcStates(five,flatEvents(five)).PASS,0);
  assert.equal(completeness(manufacturing,f).rows.length,9);
});

test('Resolution Trail uses actual linked rework and backend decision versions; ambiguity stays held', () => {
  const u=five.units.find(u => u.unitId==='MTR-26002')!,b=Object.values(five.decisions[u.unitId])[0];
  const c=correctiveEvents(u.events!);
  assert.ok(c.some(e => e.eventType==='COMPONENT_REMOVED'));
  assert.ok(c.some(e => e.eventType==='COMPONENT_INSTALLED' && e.payload?.lot==='BR-312'));
  for(const e of c)assert.ok(u.events!.some(x => x.eventId===e.eventId));
  const pair=pairOf(b.current,b.history as DecisionCurrent[]);
  assert.ok(pair.prev);assert.equal(pair.cur?.evidenceFinding,'UNRESOLVED');
  assert.equal(pair.cur?.operationalAction,'RECALL_HOLD');
  assert.ok(pair.cur?.reasonCodes?.includes('AMBIGUOUS_SLOT_ATTRIBUTION'));
});

test('Resolution confirmation labels native inspections as claims, not independent clearance', () => {
  const ev=confirmationEvents(manufacturing.units.find(u=>u.unitId==='MTR-27002')!.events!);
  const qc=ev.find(e=>e.eventType==='QUALITY_INSPECTION_RECORDED')!;
  assert.ok(qc);assert.equal(assuranceOf(qc).weak,true);assert.match(assuranceOf(qc).label,/Not recall clearance/);
  assert.equal(correctiveEvents(manufacturing.units.find(u=>u.unitId==='MTR-27002')!.events!).length,0);
});

test('Daily Report UTC source and ingestion lenses each enumerate actual records without combining the datasets', () => {
  for(const s of [manufacturing,five])for(const basis of ['source','ingest'] as const){
    const rows=allRows(s,basis);assert.equal(rows.length,total(s));
    const r=buildReport(s,date(s,basis),basis,true);
    assert.equal(r.day.length,rows.filter(e=>e.day===date(s,basis)).length);
    assert.equal(r.risks.holds,s.units.filter(u=>Object.values(s.decisions[u.unitId])[0]?.current.operationalAction==='RECALL_HOLD').length);
  }
  assert.notEqual(date(manufacturing,'source'),date(manufacturing,'ingest'));
  assert.equal(dayOf('2026-10-10T23:59:59Z'),'2026-10-10');
  assert.equal(dayOf('2026-10-11T00:00:00Z'),'2026-10-11');
});

test('missing ingestion timestamps remain unknown rather than falling back to source time', () => {
  const s=structuredClone(manufacturing);delete s.units[0].events![0].repository!.localReceivedAt;
  const r=buildReport(s,date(s,'ingest'),'ingest',false);
  assert.equal(r.unknown,1);assert.equal(r.risks.holds,0);assert.equal(r.changesDay.length,0);
  assert.equal(kpisOf(r,false,9,'Anchored prefix only').find(k=>k.id==='kpi-holds')!.value,'—');
});

test('decision changes remain attributed to trigger evidence, not invented publication timestamps', () => {
  const changes=changesOf(five,'source');assert.ok(changes.length);
  for(const c of changes){
    if(c.day){assert.ok(c.trigger);assert.equal(c.day,dayOf(c.trigger!.occurredAt));}
    assert.notEqual(c.from.decisionId,c.to.decisionId);
  }
});

test('actual prefix-only and unanchored envelopes cannot produce current report findings', () => {
  for(const name of ['manufacturing-stale','manufacturing-unanchored']){
    const s=load(name),g=evaluateEnvelope({status:200,body:s},null);
    assert.equal(g.kind,'SEGREGATED');
    const r=buildReport({...s,decisions:{},eligibility:undefined},date(s,'source'),'source',false);
    assert.equal(r.risks.affected.length,0);assert.equal(r.changesDay.length,0);
  }
});

test('real Daily PDF exporter handles both datasets and historical reports without layout or decision rewrites', () => {
  const out=process.env.PRAMAAN_TEST_ARTIFACTS!;mkdirSync(out,{recursive:true});
  for(const [name,s,allowed,state] of [['manufacturing',manufacturing,true,'ANCHORED_CURRENT'],['five',five,true,'ANCHORED_CURRENT'],['prefix',load('manufacturing-stale'),false,'ANCHORED_PREFIX_ONLY']] as const){
    const clean=allowed?s:{...s,decisions:{},eligibility:undefined,comparison:undefined};
    const before=JSON.stringify(clean);
    const bytes=buildDailyPdf({snap:clean,allowed,state,label:allowed?'Anchored current':'Anchored prefix only',detail:'Actual test-ledger envelope',date:date(s,'source'),basis:'source',generatedAt:new Date().toISOString(),mode:allowed?'current':'noncurrent'});
    const text=Buffer.from(bytes).toString('latin1');
    assert.ok(text.startsWith('%PDF-1.4'));assert.match(text,/startxref\s+\d+\s+%%EOF/);
    assert.ok(text.includes(`${s.units.length}-motor synthetic ledger demonstration`));
    assert.equal(text.includes('five-motor'),false);
    if(!allowed){assert.ok(text.includes('NOT CURRENT'));assert.equal(text.includes('RELEASE_ELIGIBLE'),false);}
    assert.equal(JSON.stringify(clean),before);
    writeFileSync(resolve(out,name+'.pdf'),bytes);
  }
});

test('report and Resolution Trail projections do not mutate actual evidence or evaluator outputs', () => {
  const before=JSON.stringify(manufacturing);
  buildReport(manufacturing,date(manufacturing,'source'),'source',true);
  for(const u of manufacturing.units){correctiveEvents(u.events!);confirmationEvents(u.events!);}
  assert.equal(JSON.stringify(manufacturing),before);
});
