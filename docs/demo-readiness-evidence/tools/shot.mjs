// review tooling: node shot.mjs <playwrightRoot> <url> <outPrefix> [waitMs] [width]
import { createRequire } from "node:module";
import fs from "node:fs";
const [root, url, out, wait = "2500", width = "1280"] = process.argv.slice(2);
const { chromium } = createRequire(root + "/package.json")("playwright-core");
const exe = process.env.CHROME_EXE;
const browser = await chromium.launch({ channel: exe ? undefined : "chrome", executablePath: exe });
const page = await browser.newPage({ viewport: { width: +width, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
const t0 = Date.now();
await page.goto(url, { waitUntil: "load" });
await page.waitForTimeout(+wait);
await page.screenshot({ path: out + ".png", fullPage: true });
const text = await page.locator("body").innerText();
fs.writeFileSync(out + ".txt", text + "\n--- console errors ---\n" + errors.join("\n"));
console.log(`${url} -> ${out}.png (${Date.now() - t0}ms, ${text.length} chars text, ${errors.length} console errors)`);
await browser.close();
