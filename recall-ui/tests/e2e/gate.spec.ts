// FE browser matrix: the three standalone pages in a real browser, fed REAL H1/H2 envelopes
// (tests/fixtures/h1h2) by a tiny local server that also serves the production build. Loopback only.
import { expect, test, type Page } from "@playwright/test";
import { createServer, type Server } from "node:http";
import { existsSync, readFileSync } from "node:fs";
import { extname, join, resolve } from "node:path";

const PORT = 4321;
const DIST = resolve("dist");
const FIX = resolve("tests/fixtures/h1h2");
const fixture = (n: string): { status: number; body: any } => JSON.parse(readFileSync(join(FIX, `${n}.json`), "utf8"));
const TYPES: Record<string, string> = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml", ".map": "application/json" };

type Mode = "current" | "prefix_only" | "unanchored" | "anchor_invalid" | "verifying" | "invalid_request" | "legacy" | "unknown_state" | "network" | "regress_current" | "not_cleared" | "forged_preview";
let mode: Mode = "current";
let requests: string[] = [];
let server: Server;

function envelope(m: Mode): { status: number; body: any } | null {
  const now = new Date().toISOString().replace(/\.\d+Z$/, "Z");
  const f = (n: string) => { const e = fixture(n); if (e.body?.freshness?.maxAgeSeconds > 0) e.body.freshness.verifiedAt = now; return e; };
  switch (m) {
    case "current": return f("current");
    case "prefix_only": return f("prefix_only");
    case "unanchored": return f("unanchored");
    case "anchor_invalid": return fixture("anchor_invalid");
    case "verifying": return fixture("verifying");
    case "invalid_request": return fixture("invalid_request");
    case "legacy": { const e = f("current"); delete e.body.checkpoint; delete e.body.eligibility; return e; }
    case "unknown_state": { const e = f("current"); e.body.checkpoint.state = "ANCHORED_CURRENT "; return e; }
    case "regress_current": { const e = f("current"); e.body.freshness.sequence -= 1; e.body.checkpoint.anchoredSequence -= 1; return e; }
    case "not_cleared": { const e = f("current"); e.body.eligibility["MTR-26003"].currentReleaseEligible = false; return e; }
    case "network": return null;
    default: return null;
  }
}

test.beforeAll(async () => {
  expect(existsSync(DIST), "run npm run build first").toBeTruthy();
  server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://x");
    if (url.pathname !== "/__mode") requests.push(`${req.method} ${url.pathname}`);
    if (url.pathname === "/__mode") { mode = url.searchParams.get("m") as Mode; res.end("ok"); return; }
    if (url.pathname === "/api/snapshot") {
      const e = envelope(mode);
      if (!e) { req.socket.destroy(); return; }
      res.writeHead(e.status, { "content-type": "application/json", "cache-control": "no-store" }); res.end(JSON.stringify(e.body)); return;
    }
    if (url.pathname.startsWith("/api/")) { res.writeHead(404); res.end("{}"); return; }
    if (mode === "forged_preview" && /^\/data\/.*\.json$/.test(url.pathname) && existsSync(join(DIST, url.pathname))) {
      // A preview dataset that LIES: it claims a current anchored checkpoint and eligibility for every motor.
      const raw = JSON.parse(readFileSync(join(DIST, url.pathname), "utf8"));
      const forge = (snap: any) => { if (!snap || typeof snap !== "object") return; snap.checkpoint = { state: "ANCHORED_CURRENT", h2: "VERIFIED", checkpointRequired: false, anchoredSequence: 1 }; snap.eligibility = Object.fromEntries((snap.units ?? []).map((u: any) => [u.unitId, { currentReleaseEligible: true }])); };
      forge(raw); (raw.stages ?? raw.datasets ?? []).forEach((x: any) => forge(x.snapshot));
      res.writeHead(200, { "content-type": "application/json" }); res.end(JSON.stringify(raw)); return;
    }
    const file = join(DIST, url.pathname === "/" ? "index.html" : url.pathname);
    if (!file.startsWith(DIST) || !existsSync(file)) { res.writeHead(404); res.end("nf"); return; }
    res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" }); res.end(readFileSync(file));
  });
  await new Promise<void>((r) => server.listen(PORT, "127.0.0.1", r));
});
test.afterAll(async () => { await new Promise((r) => server.close(r)); });
test.beforeEach(() => { requests = []; });

test.describe.configure({ mode: "serial" });   // one shared envelope server and mode: never run these across workers

const BASE = `http://127.0.0.1:${PORT}`;
const PAGES: Array<[string, string]> = [
  ["passport (eligible motor)", "/passport.html#/passport/MTR-26003/recall"],
  ["passport (index)", "/passport.html#/"],
  ["investigation", "/investigation.html#/"],
  ["impact list", "/impact.html#/"],
];
const CLEARANCE = /RELEASE_ELIGIBLE|Release eligible|Excluded with evidence|No recall hold recorded|Eligible under this recall|shipment authorization/i;
const MOTOR_SPECIFIC = /MTR-\d|BR-\d|RECALL_HOLD|Recall hold|SERIAL-|EXCLUDED_WITH_EVIDENCE/i;
const NEUTRAL = /withheld|unavailable|could not be loaded|not current|not shown/i;
const setMode = async (page: Page, m: Mode) => { await page.request.get(`${BASE}/__mode?m=${m}`); };
const body = async (page: Page, settle = 1800) => { await page.waitForTimeout(settle); return page.locator("body").innerText(); };

for (const [name, path] of PAGES) {
  test.describe(name, () => {
    test("FE-02 PREFIX_ONLY: no clearance wording, never presented as current", async ({ page }) => {
      await setMode(page, "prefix_only"); await page.goto(BASE + path);
      const t = await body(page);
      expect(t).not.toMatch(CLEARANCE);
      expect(t).toMatch(/checkpoint is required/i);       // the page must SAY it is not current, not merely omit a word
    });
    test("FE-03 UNANCHORED: no clearance wording", async ({ page }) => {
      await setMode(page, "unanchored"); await page.goto(BASE + path);
      const t = await body(page);
      expect(t).not.toMatch(CLEARANCE);
      expect(t).toMatch(/no trusted external anchor/i);
    });
    for (const m of ["anchor_invalid", "verifying", "invalid_request", "legacy", "unknown_state", "network", "regress_current"] as Mode[]) {
      test(`WITHHELD (${m}): no motor-specific finding, hold, genealogy or label; neutral reason shown`, async ({ page }) => {
        await setMode(page, m === "regress_current" ? "prefix_only" : m); await page.goto(BASE + path);
        if (m === "regress_current") { await page.waitForTimeout(800); await setMode(page, "regress_current"); }
        const t = await body(page, 3000);
        expect(t).not.toMatch(CLEARANCE);
        expect(t).not.toMatch(MOTOR_SPECIFIC);
        expect(t).toMatch(NEUTRAL);
      });
    }
    test("FE-19/21 CURRENT then PREFIX_ONLY then ANCHOR_INVALID: nothing from the earlier snapshot remains; persistence empty", async ({ page }) => {
      await setMode(page, "current"); await page.goto(BASE + path); await page.waitForTimeout(1500);
      await setMode(page, "prefix_only"); await page.waitForTimeout(3500);
      expect(await page.locator("body").innerText()).not.toMatch(CLEARANCE);
      await setMode(page, "anchor_invalid"); await page.waitForTimeout(3500);
      const t = await page.locator("body").innerText();
      expect(t).not.toMatch(CLEARANCE); expect(t).not.toMatch(MOTOR_SPECIFIC);
      const stored = await page.evaluate(() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage), history.state]));
      expect(stored).not.toMatch(/MTR-|RELEASE|decision/i);
    });
    test("FE-26 live page never falls back to preview data when the backend fails", async ({ page }) => {
      await setMode(page, "network"); await page.goto(BASE + path); await page.waitForTimeout(2500);
      expect(requests.filter((r) => /-demo\.json|preview\.json|snapshot\.json/.test(r))).toEqual([]);
      expect(await page.locator("body").innerText()).not.toMatch(MOTOR_SPECIFIC);
    });
    test("only GET /api/snapshot is requested from the API", async ({ page }) => {
      await setMode(page, "prefix_only"); await page.goto(BASE + path); await page.waitForTimeout(1500);
      const api = requests.filter((r) => r.includes("/api/"));
      expect(api.length).toBeGreaterThan(0);
      for (const r of api) expect(r).toBe("GET /api/snapshot");
    });
  });
}

test("FE-01 CURRENT: passport still shows the verified recall card (the gate does not over-block)", async ({ page }) => {
  await setMode(page, "current"); await page.goto(`${BASE}/passport.html#/passport/MTR-26003/recall`);
  await expect(page.getByTestId("recall-current")).toBeVisible({ timeout: 8000 });
});

test("FE-02b passport PREFIX_ONLY keeps genealogy facts but states recall status is unavailable", async ({ page }) => {
  await setMode(page, "prefix_only"); await page.goto(`${BASE}/passport.html#/passport/MTR-26003/recall`);
  await expect(page.getByTestId("recall-unavailable")).toBeVisible({ timeout: 8000 });
  expect(await page.locator("body").innerText()).toMatch(/not currently verified|checkpoint is required/i);
});

test("FE-28 deep link to a motor tab while WITHHELD shows no hold or label", async ({ page }) => {
  await setMode(page, "anchor_invalid"); await page.goto(`${BASE}/passport.html#/passport/MTR-26001/components`);
  const t = await body(page, 2500);
  expect(t).not.toMatch(/Recall hold|RECALL_HOLD|SERIAL-|BR-\d/i);
  expect(t).toMatch(NEUTRAL);
});

test("FE-PRV explicit preview mode is labelled, unverified and carries no customer, destination or operator ids", async ({ page }) => {
  await page.goto(`${BASE}/passport.html?mode=preview#/passport/MTR-26003`);
  await page.waitForTimeout(2000);
  const t = await page.locator("body").innerText();
  expect(t).toMatch(/Preview|not a live ledger|not currently verified/i);
  expect(t).not.toMatch(/Aster Pump|Coimbatore|OP-[A-Z]|DISPATCH-|SUPPLIER-INTAKE|MES-SYSTEM/);
  const raw = await (await page.request.get(`${BASE}/data/passport-preview.json`)).text();
  expect(raw).not.toMatch(/Aster Pump|Coimbatore|"OP-|"QA-|"EMP-/);
});

for (const [name, path] of [["investigation", "/investigation.html#/"], ["impact list", "/impact.html#/"]] as Array<[string, string]>) {
  test(`FE-01 CURRENT: ${name} shows motor-level content (positive control for the withheld assertions)`, async ({ page }) => {
    await setMode(page, "current"); await page.goto(BASE + path);
    expect(await body(page, 3000)).toMatch(/MTR-\d|BR-\d/);
  });
}

test.describe("branded views in the browser (per-motor clearance and previews)", () => {
  const WITHHELD_CLEARANCE = /No recall hold recorded|Release eligible|shipment authorization|Eligible under this recall/i;

  test("T7 passport: eligibility withheld for MTR-26003 keeps the finding, shows no clearance, and stays CURRENT", async ({ page }) => {
    await setMode(page, "not_cleared"); await page.goto(`${BASE}/passport.html#/passport/MTR-26003/recall`);
    const card = page.getByTestId("recall-current");
    await expect(card).toBeVisible({ timeout: 8000 });
    await expect(card).toContainText("Current clearance withheld for this motor");
    await expect(card).toContainText(/Excluded with evidence/i);                // the recorded finding is preserved
    expect(await page.locator("body").innerText()).not.toMatch(WITHHELD_CLEARANCE);
  });
  test("T7 passport: another motor's recall card is unaffected by MTR-26003's withheld eligibility", async ({ page }) => {
    await setMode(page, "not_cleared"); await page.goto(`${BASE}/passport.html#/passport/MTR-26001/recall`);
    await expect(page.getByTestId("recall-current")).toContainText("Held under the recall policy", { timeout: 8000 });
  });
  for (const [name, path] of [["investigation", "/investigation.html#/"], ["impact list", "/impact.html#/"]] as Array<[string, string]>) {
    test(`T7 ${name}: gate stays CURRENT (content shown), with no clearance chip for the motor whose eligibility is withheld`, async ({ page }) => {
      await setMode(page, "not_cleared"); await page.goto(BASE + path);
      const t = await body(page, 3000);
      expect(t).toMatch(/MTR-\d|BR-\d/);
      expect(t).not.toMatch(/withheld \(|Current status unavailable/i);
      expect(await page.getByTestId("clearance-chip").count()).toBeLessThanOrEqual(0);
    });
  }
  for (const [name, path] of [["passport", "/passport.html?mode=preview#/passport/MTR-26003/recall"], ["investigation", "/investigation.html?mode=preview#/"], ["impact", "/impact.html?mode=preview#/"]] as Array<[string, string]>) {
    test(`T8 ${name}: a preview dataset that forges a current checkpoint and eligibility is still a labelled preview with no clearance`, async ({ page }) => {
      await setMode(page, "forged_preview"); await expect.poll(async () => (await page.request.get(`${BASE}/data/passport-preview.json`)).text()).toContain("ANCHORED_CURRENT");   // positive control: the forgery is really served
      await page.goto(BASE + path);
      const t = await body(page, 2500);
      expect(t).toMatch(/Preview|not a live ledger|not currently verified/i);
      expect(t).not.toMatch(WITHHELD_CLEARANCE);
      expect(await page.getByTestId("clearance-chip").count()).toBe(0);
      expect(requests.filter((r) => r.includes("/api/"))).toEqual([]);          // preview never calls the live API
    });
  }
});
