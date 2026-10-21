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
 await page.getByText('Manufacturing capture workspace',{exact:true}).click();
 await expect(page.getByRole('button',{name:'Create unit',exact:true})).toBeDisabled();
 await expect(page.getByText(/historical, not operational clearance/)).toBeVisible();
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
  await expect(page.getByTestId('chip-action').first()).toContainText('Recall hold',{timeout:8000});
  await expect(page.getByText(/PRIOR_EXCLUSION_WITHDRAWN/).first()).toBeVisible();
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
