// review tooling: node soak.mjs <playwrightRoot> <url> <okRegex> <seconds>  (samples every 5 s whether the page still shows current content)
import { createRequire } from "node:module";
const [root, url, ok, secs] = process.argv.slice(2);
const { chromium } = createRequire(root + "/package.json")("playwright-core");
const b = await chromium.launch({ channel: "chrome" }); const p = await b.newPage();
await p.goto(url); await p.waitForTimeout(3000);
const re = new RegExp(ok); let good = 0, bad = 0; const t0 = Date.now();
while ((Date.now() - t0) / 1000 < +secs) { const t = await p.locator("body").innerText(); re.test(t) ? good++ : bad++; await p.waitForTimeout(5000); }
console.log(`${url}: ${good} ok samples, ${bad} not-ok samples over ${Math.round((Date.now() - t0) / 1000)}s`);
await b.close();
