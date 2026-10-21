import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";

test("actual backend shutdown revokes live release presentation", async ({ page }) => {
  const python=resolve(process.platform==='win32'?'../.venv/Scripts/python.exe':'../.venv/bin/python');
  const server=spawn(python,['app.py','--seed-demo','--database',join(mkdtempSync(join(tmpdir(),'pramaan-offline-')),'db.sqlite'),'--port','4182'],{cwd:resolve('..'),stdio:'ignore',windowsHide:true});
  try {
    await expect(async()=>{ expect((await page.request.get('http://127.0.0.1:4182/api/session')).ok()).toBeTruthy(); }).toPass({timeout:15000});
    await page.goto('http://127.0.0.1:4182/#/unit/MTR-26003/decision');
    await expect(page.getByTestId('chip-action').first()).toContainText('Release eligible');
    await expect(page.getByText(/Verified with local synthetic backend/)).toBeVisible();
    server.kill();
    await expect(page.getByTestId('load-error')).toBeVisible({timeout:8000});
    await expect(page.getByTestId('chip-action')).toHaveCount(0);
    await page.screenshot({path:'../docs/phase31-screenshots/backend-offline.png',fullPage:true});
  } finally { server.kill(); }
});

test("live long identifiers: decision, history and keyboard-scrollable genealogy at 390px", async({page})=>{
  await page.setViewportSize({width:390,height:844});
  for(const route of ['decision','history','genealogy']){
    await page.goto(`/#/unit/MTR-26002/${route}`);
    await expect(page.getByTestId('chip-action').first()).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth),route).toBeLessThanOrEqual(0);
    const result=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();
    expect(result.violations.map(v=>`${v.id}: ${v.nodes.map(n=>n.target).join(',')}`)).toEqual([]);
    if(route==='genealogy'){
      const region=page.getByRole('region',{name:'Scrollable genealogy for MTR-26002'});
      await region.focus();await expect(region).toBeFocused();
      await page.keyboard.press('ArrowRight');
      await expect.poll(()=>region.evaluate(e=>e.scrollLeft)).toBeGreaterThan(0);
    }
    await page.screenshot({path:`../docs/phase31-screenshots/mobile-${route}.png`,fullPage:true});
  }
});

test("NDE-only affected motor is held by unspecified recall scope through real API", async({page})=>{
  // The shared seed has an explicitly restricted DE policy; prove NDE capture
  // and explicit scope using a separate empty local backend instead of mutating it.
  const python=resolve(process.platform==='win32'?'../.venv/Scripts/python.exe':'../.venv/bin/python');
  const server=spawn(python,['app.py','--database',join(mkdtempSync(join(tmpdir(),'pramaan-scope-')),'db.sqlite'),'--port','4183'],{cwd:resolve('..'),stdio:'ignore',windowsHide:true});
  try{
    await expect(async()=>{expect((await page.request.get('http://127.0.0.1:4183/api/session')).ok()).toBeTruthy();}).toPass({timeout:15000});
    const session=await(await page.request.get('http://127.0.0.1:4183/api/session')).json();
    const command=async(path:string,body:object)=>{
      const res=await page.request.post(`http://127.0.0.1:4183/api/${path}`,{headers:{'X-Pramaan-Token':session.token},data:body});expect(res.ok()).toBeTruthy();return res.json();
    };
    await command('units',{serial:'MTR-NDE-REGRESSION'});
    await command('units/MTR-NDE-REGRESSION/assemble',{deLot:'BR-310',ndeLot:'BR-204'});
    await command('units/MTR-NDE-REGRESSION/ship',{});
    const result=await command('recalls',{lot:'BR-204'});
    expect(result.snapshot.recall.affectedSlots).toEqual(['DE','NDE']);
    await page.goto('http://127.0.0.1:4183/#/unit/MTR-NDE-REGRESSION/decision');
    await expect(page.getByTestId('chip-finding').first()).toContainText('Affected');
    await expect(page.getByTestId('chip-action').first()).toContainText('Recall hold');
  }finally{server.kill();}
});
