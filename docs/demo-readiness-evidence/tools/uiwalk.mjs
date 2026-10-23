// review tooling: node uiwalk.mjs <playwrightRoot> <baseUrl> <outPrefix> <serialPrefix>
// Drives the capture workspace through the real UI (no API shortcuts) and records elapsed ms and a screenshot per step.
import { createRequire } from "node:module";
import fs from "node:fs";
const [root, base, out, pre] = process.argv.slice(2);
const { chromium } = createRequire(root + "/package.json")("playwright-core");
const browser = await chromium.launch({ channel: "chrome" });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const log = [];
const step = async (name, fn) => {
  const t = Date.now(); let err = null;
  try { await openBench(); await fn(); } catch (e) { err = String(e).split("\n")[0]; }
  await page.waitForTimeout(600);
  const n = String(log.length + 1).padStart(2, "0");
  await page.screenshot({ path: `${out}_${n}.png`, fullPage: true });
  log.push({ n, name, ms: Date.now() - t, err });
  console.log(`${n} ${name}: ${Date.now() - t}ms ${err ? "FAILED " + err : "ok"}`);
};
await page.goto(base + "/");
await page.waitForSelector("text=Manufacturing capture workspace", { timeout: 15000 });
page.setDefaultTimeout(10000);
const openBench = () => page.evaluate(() => { const d = document.querySelector("details.workbench"); if (d) d.open = true; });
await openBench();
const motors = [[`${pre}1`, "BR-901", "BR-310", "SERIAL"], [`${pre}2`, "BR-901", "BR-901", "LOT"], [`${pre}3`, "BR-310", "BR-312", "SERIAL"]];
for (const [s, de, nde, id] of motors) {
  await step(`register ${s}`, async () => { await page.getByLabel("New motor serial").fill(s); await page.getByRole("button", { name: "Create unit" }).click(); await page.waitForFunction((x) => [...document.querySelectorAll("option")].some((o) => o.textContent === x), s, { timeout: 8000 }); });
  await step(`assemble ${s} (DE ${de}, NDE ${nde})`, async () => { await page.getByLabel("Motor to capture").selectOption(s); await page.getByLabel("DE bearing lot", { exact: true }).fill(de); await page.getByLabel("NDE bearing lot", { exact: true }).fill(nde); await page.getByLabel("Identity evidence").selectOption(id); await page.getByRole("button", { name: "Capture bearing assembly" }).click(); await page.waitForTimeout(1200); });
  await step(`ship ${s}`, async () => { await page.getByLabel("Motor to capture").selectOption(s); await page.getByRole("button", { name: "Record synthetic shipment" }).click(); await page.waitForTimeout(1200); });
}
await step("announce recall BR-901 DE-only", async () => { await page.getByLabel("Defective bearing lot").fill("BR-901"); await page.getByLabel("Recall positions").selectOption("DE"); await page.getByRole("button", { name: "Announce recall and evaluate" }).click(); await page.waitForTimeout(1500); });
await step(`replace DE on ${pre}1`, async () => { await page.getByLabel("Motor to capture").selectOption(`${pre}1`); await page.getByLabel("Replacement DE lot").fill("BR-312"); await page.getByRole("button", { name: "Capture authorized DE replacement" }).click(); await page.waitForTimeout(1500); });
await step(`late untrusted observation on ${pre}3`, async () => { await page.getByLabel("Motor to capture").selectOption(`${pre}3`); await page.getByRole("button", { name: /Inject late untrusted/ }).click(); await page.waitForTimeout(1500); });
const text = await page.locator("body").innerText();
fs.writeFileSync(`${out}_final.txt`, text);
fs.writeFileSync(`${out}_log.json`, JSON.stringify(log, null, 1));
await browser.close();
