import {test,expect} from '@playwright/test';
import {spawn,spawnSync} from 'node:child_process';
import {mkdtempSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';

test('post-checkpoint capture globally withholds releases while showing holds and obligations',async({page})=>{
 const python=resolve(process.platform==='win32'?'../.venv/Scripts/python.exe':'../.venv/bin/python');
 const database=join(mkdtempSync(join(tmpdir(),'pramaan-strict-')),'db.sqlite');
 const server=spawn(python,['recall-ui/tests/browser_server.py',database,'--port','4185'],{cwd:resolve('..'),stdio:'ignore',windowsHide:true});
 try{
  await expect(async()=>{expect((await page.request.get('http://127.0.0.1:4185/api/session')).ok()).toBeTruthy();}).toPass({timeout:15000});
  await page.goto('http://127.0.0.1:4185/#/unit/MTR-26003/decision');
  await expect(page.getByTestId('chip-action').first()).toContainText('Release eligible');
  const writer=spawnSync(python,['-c',"import sys;from application.service import Manufacturing;a=Manufacturing(sys.argv[1]);a.observe('MTR-26003','BR-204');a.close()",database],{cwd:resolve('..'),encoding:'utf8',windowsHide:true});
  expect(writer.status,writer.stderr).toBe(0);
  await expect(page.getByRole('heading',{name:'Checkpoint required'})).toBeVisible({timeout:8000});
  await expect(page.getByTestId('chip-action')).toHaveCount(0);
  await expect(page.getByText(/Recall hold remains in effect/).first()).toBeVisible();
  const snapshot=await(await page.request.get('http://127.0.0.1:4185/api/snapshot')).json();
  expect(snapshot.checkpoint.state).toBe('ANCHORED_PREFIX_ONLY');
  expect(Object.values(snapshot.eligibility).every((p:any)=>p.currentReleaseEligible===false)).toBeTruthy();
  expect(snapshot.notifications.some((p:any)=>p.unitId==='MTR-26003')).toBeTruthy();
 }finally{server.kill();}
});
