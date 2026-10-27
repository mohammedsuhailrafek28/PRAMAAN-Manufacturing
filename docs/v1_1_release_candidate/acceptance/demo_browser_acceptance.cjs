// Browser acceptance walk of docs/v1_1_release_candidate/DEMO_RUNBOOK.md against a clean checkout. Automated Chrome (not a human). Loopback only.
// env: REPO (checkout root, with .venv and built recall-ui/dist), OUT (output dir), CHROME (pinned chrome.exe), PW (path of @playwright/test module)
const { chromium } = require(process.env.PW);
const { execFileSync, spawn } = require('node:child_process');
const fs = require('node:fs'); const path = require('node:path');
const REPO = process.env.REPO, OUT = process.env.OUT; fs.mkdirSync(OUT, { recursive: true });
const PY = path.join(REPO, '.venv/Scripts/python.exe'); const B = 'http://127.0.0.1:4173';
const DB = 'demo/ledger.sqlite', CUST = 'demo/custody'; let current = 'demo/custody/root.json', previous;
const log = []; const t0 = Date.now(); const errors = [];
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const step = async (name, fn) => { const s = Date.now(); try { const d = await fn(); log.push({ step: name, result: 'PASS', ms: Date.now() - s, detail: d }); console.log('PASS', name, Date.now() - s, 'ms |', d ?? ''); } catch (e) { log.push({ step: name, result: 'FAIL', ms: Date.now() - s, detail: String(e.message).slice(0, 500) }); console.log('FAIL', name, String(e.message).slice(0, 300)); } };
const py = (args) => execFileSync(PY, ['-B', ...args], { cwd: REPO, encoding: 'utf8', windowsHide: true });
let server;
async function serve() {
  const args = ['-B', 'app.py', '--database', DB, '--port', '4173', '--custody-dir', CUST, '--trusted-anchor', current]; if (previous) args.push('--previous-anchor', previous);
  server = spawn(PY, args, { cwd: REPO, stdio: 'ignore', windowsHide: true });
  for (let i = 0; i < 100; i++) { try { if ((await fetch(B + '/api/session')).ok) return; } catch {} await wait(150); }
  throw new Error('server did not start');
}
const stop = async () => { if (!server) return; const s = server; server = undefined; await new Promise((ok) => { s.once('close', ok); s.kill(); setTimeout(ok, 4000); }); };
const snap = async () => (await fetch(B + '/api/snapshot')).json();
const post = async (p, body) => { const token = (await (await fetch(B + '/api/session')).json()).token; const r = await fetch(B + '/api/' + p, { method: 'POST', headers: { 'content-type': 'application/json', origin: B, 'x-pramaan-token': token }, body: JSON.stringify(body) }); return { status: r.status, body: await r.json().catch(() => null) }; };
const cycle = async () => {
  await stop();
  const base = ['-m', 'application.checkpoint_ops']; const common = ['--database', DB, '--current', current, '--custody-dir', CUST]; if (previous) common.push('--current-previous', previous);
  const p = JSON.parse(py([...base, 'propose', ...common]));
  const acks = (p.review.requiresAcknowledgement || []).flatMap((m) => ['--acknowledge', m]);
  const a = JSON.parse(py([...base, 'accept', ...common, '--candidate', p.candidate, '--custodian', 'Acceptance operator (local test custody)', '--confirm-sha256', p.candidateSha256, '--registry-digest', p.review.registry.digest, ...acks]));
  previous = current; current = a.accepted; await serve();
  return { contained: p.review.containedMotors || [], acknowledged: p.review.requiresAcknowledgement, status: a.status };
};
const text = (page) => page.evaluate(() => document.body.innerText);
let n = 0; const shot = (page, name) => page.screenshot({ path: path.join(OUT, `${String(++n).padStart(2, '0')}-${name}.png`), fullPage: true });
const openWs = async (page) => { await page.getByText('Manufacturing capture workspace', { exact: true }).click(); };

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME, headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push('pageerror: ' + String(e).slice(0, 200))); page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text().slice(0, 200)); });
  const heading = (name) => page.getByRole('heading', { name }).waitFor({ timeout: 15000 });

  await step('0:00 server up (runbook command), console current', async () => {
    await serve(); const s = await snap(); if (s.checkpoint.state !== 'ANCHORED_CURRENT') throw new Error(s.checkpoint.state);
    await page.goto(B + '/#/'); await heading('Motor decisions'); await shot(page, 'console-current');
    return `state=${s.checkpoint.state}; eligible=${Object.entries(s.eligibility).filter(([, v]) => v.currentReleaseEligible).map(([k]) => k)}; holds=${await page.getByTestId('chip-action').filter({ hasText: 'Recall hold' }).count()}`; });
  await step('0:20 DPP / passport recall context (MTR-26003)', async () => {
    await page.goto(B + '/passport.html#/passport/MTR-26003/recall'); await page.getByTestId('recall-current').waitFor({ timeout: 15000 }); await shot(page, 'passport-current');
    return (await page.getByTestId('recall-current').innerText()).split('\n')[0]; });
  await step('0:30 genealogy (shipped fixture motor MTR-26001)', async () => {
    await page.goto(B + '/#/unit/MTR-26001/genealogy'); await heading('Ledger-backed material genealogy'); await shot(page, 'genealogy-26001');
    return (await text(page)).includes('Shipment capture is not a release authorization.') ? 'shipment note present' : 'NO shipment note'; });
  await step('0:40 evidence investigation', async () => {
    await page.goto(B + '/investigation.html#/'); await page.getByTestId('cluster-card').first().waitFor({ timeout: 15000 }); await shot(page, 'investigation-current');
    return `cards=${await page.getByTestId('cluster-card').count()}`; });
  await step('0:50 impact graph lot BR-204', async () => {
    await page.goto(B + '/impact.html#/lot/bearing/BR-204/graph'); await page.getByTestId('impact-headline').waitFor({ timeout: 15000 }); await shot(page, 'impact-current');
    return (await page.getByTestId('impact-headline').innerText()).slice(0, 120); });

  const shipButton = async (motor) => {
    await page.goto(B + '/#/'); await heading('Motor decisions'); await openWs(page); await page.getByLabel('Motor to capture').selectOption(motor);
    await page.getByRole('button', { name: 'Record synthetic shipment', exact: true }).click(); await wait(800); await shot(page, `workbench-ship-${motor}-0.8s`);
    const early = (await text(page)).replace(/\s+/g, ' ').slice(0, 200); await wait(6000); await shot(page, `workbench-ship-${motor}-7s`);
    const late = (await text(page)).replace(/\s+/g, ' ').slice(0, 200);
    return { early, late, loadError: await page.getByTestId('load-error').count(), checkpointRequired: await page.getByRole('heading', { name: 'Checkpoint required' }).count(), shipment: !!(await snap()).units.find((u) => u.unitId === motor).shipment };
  };
  await step('1:00 workspace capture (new unit MTR-DEMO-3) moves ledger past checkpoint: console withholds decisions', async () => {
    await page.goto(B + '/#/'); await heading('Motor decisions'); await openWs(page);
    await page.getByLabel('New motor serial').fill('MTR-DEMO-3'); await page.getByRole('button', { name: 'Create unit', exact: true }).click();
    await page.getByTestId('capture-status').waitFor({ timeout: 15000 }); await heading('Checkpoint required'); const body = await text(page); await shot(page, 'checkpoint-required');
    if (/Release eligible|Recall hold/.test(body)) throw new Error('decision text shown while stale');
    return `workbench visible while stale: ${await page.getByText('Manufacturing capture workspace', { exact: true }).count()}; warning="${(await page.getByTestId('no-shipment-warning').innerText()).slice(0, 70)}"`; });
  await step('1:30 API ship of the clean eligible-after-cycle motor DEMO-1 while stale is refused', async () => {
    const r = await post('units/MTR-DEMO-1/ship', {}); if (r.status !== 409 || r.body.error !== 'SHIPMENT_REFUSED') throw new Error(JSON.stringify(r)); return `${r.status} ${r.body.error}`; });
  await step('2:00 recovery workspace visible in stale console', async () => {
    await page.goto(B + '/#/'); await page.getByTestId('recovery-workspace').waitFor({ timeout: 20000 }); await shot(page, 'recovery-workspace'); return (await page.getByTestId('recovery-mode').innerText()).slice(0, 120); });
  await step('2:15 operator checkpoint cycle (propose, accept with typed digest, restart with --previous-anchor)', async () => JSON.stringify(await cycle()));
  await step('3:00 console current: DEMO-1 release eligible, DEMO-2 recall hold', async () => {
    const s = await snap(); await page.goto(B + '/#/'); await heading('Motor decisions'); await page.getByTestId('chip-action').first().waitFor({ timeout: 15000 }); await shot(page, 'console-after-cycle');
    await page.goto(B + '/#/unit/MTR-DEMO-2/decision'); await page.getByTestId('chip-action').first().waitFor({ timeout: 15000 }); await shot(page, 'decision-demo2-hold');
    const chip = await page.getByTestId('chip-action').first().innerText();
    if (s.checkpoint.state !== 'ANCHORED_CURRENT' || s.eligibility['MTR-DEMO-1'].currentReleaseEligible !== true || s.eligibility['MTR-DEMO-2'].currentReleaseEligible !== false) throw new Error(JSON.stringify(s.eligibility));
    return `DEMO-2 chip="${chip}"`; });
  await step('3:00 DPP for MTR-DEMO-2 (hold) ', async () => {
    await page.goto(B + '/passport.html#/passport/MTR-DEMO-2/recall'); await page.getByTestId('recall-current').waitFor({ timeout: 15000 }); await shot(page, 'passport-demo2'); return (await page.getByTestId('recall-current').innerText()).split('\n')[0]; });
  await step('ITEM 3 workbench "Record synthetic shipment" on recall-held MTR-DEMO-2 (refusal path)', async () => JSON.stringify(await shipButton('MTR-DEMO-2')));
  await step('3:30 API ship DEMO-2 with forged claims refused', async () => { const r = await post('units/MTR-DEMO-2/ship', { currentReleaseEligible: true, force: true }); if (r.status !== 409) throw new Error(JSON.stringify(r)); return `${r.status} ${r.body.error}`; });
  await step('3:30 workbench shipment of current eligible MTR-DEMO-1 (success path) ', async () => {
    const s0 = await snap(); if (s0.checkpoint.state !== 'ANCHORED_CURRENT') throw new Error('not current before eligible shipment: ' + s0.checkpoint.state);
    const r = await shipButton('MTR-DEMO-1'); if (!r.shipment) throw new Error(JSON.stringify(r)); return JSON.stringify(r); });
  await step('3:45 cycle, then genealogy shows the recorded shipment', async () => {
    const c = await cycle(); await page.goto(B + '/#/unit/MTR-DEMO-1/genealogy'); await heading('Ledger-backed material genealogy'); await shot(page, 'genealogy-demo1-shipped');
    return JSON.stringify(c) + ((await text(page)).includes('Shipment capture is not a release authorization.') ? ' | shipment note present' : ' | NO shipment note'); });
  await step('4:15 unverified sighting ZZ-9 on MTR-26003 via workspace, then cycle: that motor held', async () => {
    await page.goto(B + '/#/'); await heading('Motor decisions'); await openWs(page); await page.getByLabel('Motor to capture').selectOption('MTR-26003');
    await page.getByLabel('Sighted label (as read; may be wrong)').fill('ZZ-9'); await page.getByRole('button', { name: 'Record unverified sighting', exact: true }).click();
    await page.getByTestId('capture-status').waitFor({ timeout: 15000 }); await heading('Checkpoint required'); await shot(page, 'sighting-stale');
    const c = await cycle(); const s = await snap(); await page.goto(B + '/#/unit/MTR-26003/decision'); await page.getByTestId('chip-action').first().waitFor({ timeout: 15000 }); await shot(page, 'sighting-26003-held');
    if (s.eligibility['MTR-26003'].currentReleaseEligible !== false || !c.contained.includes('MTR-26003')) throw new Error(JSON.stringify([c, s.eligibility]));
    return JSON.stringify(c) + ` chip="${await page.getByTestId('chip-action').first().innerText()}"; DEMO-1 eligible=${s.eligibility['MTR-DEMO-1'].currentReleaseEligible}`; });
  await step('4:30 investigation after sighting', async () => { await page.goto(B + '/investigation.html#/'); await page.getByTestId('cluster-card').first().waitFor({ timeout: 15000 }); await shot(page, 'investigation-after'); return `cards=${await page.getByTestId('cluster-card').count()}`; });

  await ctx.close(); await browser.close(); await stop();
  fs.writeFileSync(path.join(OUT, 'acceptance-log.json'), JSON.stringify({ totalMs: Date.now() - t0, browserErrors: errors, steps: log }, null, 2));
  console.log('TOTAL', Date.now() - t0, 'ms; failed:', log.filter((l) => l.result === 'FAIL').length, '; browser errors:', errors.length);
})().catch(async (e) => { console.error('FATAL', e); await stop(); process.exit(1); });
