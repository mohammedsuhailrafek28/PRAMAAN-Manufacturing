import {test,expect,Page} from '@playwright/test';
import {spawn,spawnSync} from 'node:child_process';
import {mkdtempSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';

// MIGRATED (R5 amendment, owner decision 1; see docs/R5_AMENDMENT.md). Original assertion: after a post-checkpoint capture the page
// "shows holds and obligations" (spec R5 "holds visible"). Approved replacement: backend holds/obligations stay enforced and are
// asserted through the API; the PREFIX_ONLY UI shows historical facts only, with NO hold chip, release chip, per-motor decision or
// current clearance, plus a prominent global CHECKPOINT REQUIRED / DO NOT SHIP warning. The negative checks below reject the old
// behavior (hold text or a release label rendered as a current decision under PREFIX_ONLY).
const python=resolve(process.platform==='win32'?'../.venv/Scripts/python.exe':'../.venv/bin/python');
let PORT=4201;
let BASE=`http://127.0.0.1:${PORT}`;

async function owned(page:Page,port:number,use:(database:string)=>Promise<void>){
 PORT=port; BASE=`http://127.0.0.1:${port}`;
 const database=join(mkdtempSync(join(tmpdir(),'pramaan-strict-')),'db.sqlite');
 const server=spawn(python,['recall-ui/tests/browser_server.py',database,'--port',String(PORT)],{cwd:resolve('..'),stdio:'ignore',windowsHide:true});
 try{
  await expect(async()=>{expect((await page.request.get(`${BASE}/api/session`)).ok()).toBeTruthy();}).toPass({timeout:15000});
  await use(database);
 }finally{server.kill();}
}
function externalCapture(database:string){
 const writer=spawnSync(python,['-c',"import sys;from application.service import Manufacturing;a=Manufacturing(sys.argv[1]);a.observe('MTR-26003','BR-204');a.close()",database],{cwd:resolve('..'),encoding:'utf8',windowsHide:true});
 expect(writer.status,writer.stderr).toBe(0);
}
const bodyText=(page:Page)=>page.evaluate(()=>document.body.innerText);

test('post-checkpoint capture globally withholds releases while showing holds and obligations',async({page})=>{
 await owned(page,4201,async(database)=>{
  await page.goto(`${BASE}/#/unit/MTR-26003/decision`);
  await expect(page.getByTestId('chip-action').first()).toContainText('Release eligible');
  externalCapture(database);
  // UI: facts only, global warning, no current decision of any kind
  await expect(page.getByRole('heading',{name:'Checkpoint required'})).toBeVisible({timeout:8000});
  await expect(page.getByTestId('no-shipment-warning')).toContainText(/Do not ship or release any motor/);
  await expect(page.getByTestId('chip-action')).toHaveCount(0);
  await expect(page.getByTestId('chip-finding')).toHaveCount(0);
  await expect(page.getByTestId('clearance-chip')).toHaveCount(0);
  const text=await bodyText(page);
  expect(text).not.toMatch(/Release eligible|Recall hold remains in effect|Excluded with evidence/);   // negative: the old hold/release rendering
  // Backend: holds and obligations remain enforced and preserved, and nothing is currently eligible
  const snapshot=await(await page.request.get(`${BASE}/api/snapshot`)).json();
  expect(snapshot.checkpoint.state).toBe('ANCHORED_PREFIX_ONLY');
  expect(Object.values(snapshot.eligibility).every((p:any)=>p.currentReleaseEligible===false)).toBeTruthy();
  expect(snapshot.notifications.some((p:any)=>p.unitId==='MTR-26003')).toBeTruthy();
  const decisions=JSON.stringify(snapshot.decisions?.['MTR-26003']??{});
  expect(decisions).toContain('RECALL_HOLD');
  // and the per-motor decision endpoint refuses to serve a current decision
  const direct=await page.request.get(`${BASE}/api/motors/MTR-26003/decisions`);
  expect(direct.status()).toBe(409);
  expect((await direct.json()).error).toBe('CHECKPOINT_REQUIRED');
 });
});

// M8 (owner decision 2): a PREFIX_ONLY snapshot must not become current through reload, navigation, visibility changes or cache.
test('a prefix-only console never regains current clearance through reload, navigation, visibility or back/forward',async({page})=>{
 await owned(page,4202,async(database)=>{
  await page.goto(`${BASE}/#/unit/MTR-26003/decision`);
  await expect(page.getByTestId('chip-action').first()).toContainText('Release eligible');
  externalCapture(database);
  await expect(page.getByRole('heading',{name:'Checkpoint required'})).toBeVisible({timeout:8000});
  const noClearance=async()=>{
   await expect(page.getByTestId('no-shipment-warning')).toBeVisible();
   await expect(page.getByTestId('clearance-chip')).toHaveCount(0);
   await expect(page.getByTestId('chip-action')).toHaveCount(0);
   expect(await bodyText(page)).not.toMatch(/Release eligible|Excluded with evidence/);
  };
  await noClearance();
  await page.reload(); await expect(page.getByTestId('no-shipment-warning')).toBeVisible({timeout:8000}); await noClearance();
  for (const hash of ['#/','#/unit/MTR-26001/decision','#/unit/MTR-26003/history']){
   await page.evaluate(h=>{window.location.hash=h;},hash); await noClearance();
  }
  await page.evaluate(()=>{Object.defineProperty(document,'visibilityState',{value:'hidden',configurable:true});document.dispatchEvent(new Event('visibilitychange'));});
  await page.evaluate(()=>{Object.defineProperty(document,'visibilityState',{value:'visible',configurable:true});document.dispatchEvent(new Event('visibilitychange'));window.dispatchEvent(new Event('focus'));window.dispatchEvent(new Event('online'));});
  await page.waitForTimeout(2500);      // longer than the 2 s poll
  await noClearance();
  await page.goBack(); await page.goForward(); await noClearance();
  await page.goto('about:blank'); await page.goBack({waitUntil:'load'}); await expect(page.getByTestId('no-shipment-warning')).toBeVisible({timeout:8000}); await noClearance();
 });
});
