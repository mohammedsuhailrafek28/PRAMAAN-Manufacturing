import {test,expect} from '@playwright/test';
import {spawn,spawnSync} from 'node:child_process';
import {mkdtempSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';

test('old successful proxy snapshot cannot renew operational clearance; recovery stays live',async({page})=>{
 const old=await(await page.request.get('/api/snapshot')).json();
 await page.goto('/#/unit/MTR-26003/decision');
 await expect(page.getByTestId('chip-action').first()).toContainText('Release eligible');
 old.freshness.verifiedAt=new Date(Date.now()-60000).toISOString();
 await page.route('**/api/snapshot',r=>r.fulfill({json:old}));
 await expect(page.getByTestId('load-error')).toBeVisible({timeout:8000});
 await expect(page.getByTestId('chip-action')).toHaveCount(0);
 // MIGRATED (M9): original = the workbench stayed on screen with 'Create unit' disabled and a 'historical, not operational
 // clearance' note. Conflicting approved contract (owner O3): a WITHHELD console shows nothing motor-specific and offers no command
 // surface. Replacement is stronger: the workbench and every command button are absent while the lease is invalid.
 await expect(page.getByText('Manufacturing capture workspace',{exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Create unit',exact:true})).toHaveCount(0);
 await expect(page.getByTestId('load-error')).toContainText(/withheld/);
 await page.unroute('**/api/snapshot');
 await expect(page.getByTestId('chip-action').first()).toContainText('Release eligible',{timeout:8000});
 expect(page.url()).not.toContain('fixtures');
});

test('external capture writer withdraws displayed exclusion without an API command',async({page})=>{
 const python=resolve(process.platform==='win32'?'../.venv/Scripts/python.exe':'../.venv/bin/python');
 const database=join(mkdtempSync(join(tmpdir(),'pramaan-writer-')),'db.sqlite');
 const server=spawn(python,['recall-ui/tests/browser_server.py',database,'--port','4184'],{cwd:resolve('..'),stdio:'ignore',windowsHide:true});
 try{
  await expect(async()=>{expect((await page.request.get('http://127.0.0.1:4184/api/session')).ok()).toBeTruthy();}).toPass({timeout:15000});
  await page.goto('http://127.0.0.1:4184/#/unit/MTR-26003/decision');
  await expect(page.getByTestId('chip-action').first()).toContainText('Release eligible');
  const writer=spawnSync(python,['-c',"import sys;from application.service import Manufacturing;a=Manufacturing(sys.argv[1]);a.observe('MTR-26003','BR-204');a.close()",database],{cwd:resolve('..'),encoding:'utf8',windowsHide:true});
  expect(writer.status,writer.stderr).toBe(0);
  // MIGRATED (M10, R5 amendment): original = the withdrawn exclusion was shown as a 'Recall hold' chip with reason
  // PRIOR_EXCLUSION_WITHDRAWN. Under the approved amendment a PREFIX_ONLY console shows no per-motor decision/hold chip; the
  // displayed exclusion is withdrawn (no release label remains) and the backend still carries the hold and the reason code.
  await expect(page.getByRole('heading',{name:'Checkpoint required'})).toBeVisible({timeout:8000});
  await expect(page.getByTestId('chip-action')).toHaveCount(0);
  expect(await page.evaluate(()=>document.body.innerText)).not.toMatch(/Release eligible|Excluded with evidence/);
  const snap=await(await page.request.get('http://127.0.0.1:4184/api/snapshot')).json();
  expect(snap.checkpoint.state).toBe('ANCHORED_PREFIX_ONLY');
  const cur=JSON.stringify(snap.decisions['MTR-26003']);
  expect(cur).toContain('RECALL_HOLD'); expect(cur).toContain('PRIOR_EXCLUSION_WITHDRAWN');
 }finally{server.kill();}
});

test('fresh timestamp cannot conceal journal version rollback',async({page})=>{
 const old=await(await page.request.get('/api/snapshot')).json();
 await page.goto('/#/unit/MTR-26003/decision');
 await expect(page.getByTestId('chip-action').first()).toBeVisible();
 const rollback=structuredClone(old);rollback.freshness.sequence=1;
 await page.route('**/api/snapshot',r=>{rollback.freshness.verifiedAt=new Date().toISOString();return r.fulfill({json:rollback});});
 await expect(page.getByTestId('load-error')).toBeVisible({timeout:8000});
 await expect(page.getByTestId('chip-action')).toHaveCount(0);
});

test('suspension invalidates lease before fresh verification; delayed body stays hidden',async({page})=>{
 await page.goto('/#/unit/MTR-26003/decision');
 await expect(page.getByTestId('chip-action').first()).toBeVisible();
 await page.route('**/api/snapshot',async r=>{await new Promise(resolve=>setTimeout(resolve,6000));await r.abort().catch(()=>{});});
 await page.evaluate(()=>document.dispatchEvent(new Event('visibilitychange')));
 await expect(page.getByTestId('chip-action')).toHaveCount(0);
 await expect(page.getByTestId('load-error')).toBeVisible({timeout:10000});
 await expect(page.getByTestId('chip-action')).toHaveCount(0);
});
