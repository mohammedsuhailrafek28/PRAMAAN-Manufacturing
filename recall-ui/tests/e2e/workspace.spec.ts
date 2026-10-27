import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { spawn, type ChildProcess } from "node:child_process";
import { mkdirSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { OwnedStack } from "../support/ownedStack";

const screenshots = "../docs/investigation-screenshots";
const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const axe = async (page: Page) => (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze()).violations.map((v) => `${v.id}: ${v.nodes[0]?.target}`);
const cards = (page: Page) => page.getByTestId("cluster-card");

// ---- explicit preview of the authored scenario: static data, fully deterministic ------------------

test("authored scenario walkthrough: shared clusters, evidence drill-down, before and after", async ({ page }) => {
  mkdirSync(screenshots, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/investigation.html?mode=preview&stage=before#/");
  await expect(page.getByText("Preview: not current")).toBeVisible();
  await expect(page.getByTestId("iw-banner")).toContainText(/not a live ledger/);
  await expect(page.getByTestId("stage-note")).toContainText("MTR-26015 authored source edit");
  await expect(page.getByTestId("stage-note")).toContainText("MTR-26004 seeded");
  await expect(cards(page)).toHaveCount(6);
  await expect(cards(page).first()).toContainText("Untrusted affected-lot observation");
  await expect(cards(page).first()).toContainText("MTR-26005, MTR-26011, MTR-26012");
  await expect(page.getByTestId("obligations")).toContainText("not evidence-gathering tasks");
  await page.screenshot({ path: `${screenshots}/01-overview-before.png`, fullPage: true });

  // the authored shared-source gap group
  await cards(page).filter({ hasText: "ASSY:SHARED-DEMO-STATION" }).getByRole("link", { name: "Capture gap" }).click();
  await expect(page.getByTestId("task-MTR-26015")).toBeVisible();
  await expect(page.getByTestId("task-MTR-26016")).toBeVisible();
  await expect(page.getByTestId("task-MTR-26015")).toContainText("What a quality engineer should independently investigate");
  await page.screenshot({ path: `${screenshots}/02-shared-gap-cluster.png`, fullPage: true });

  // untrusted observation: rejection reasons, actor claim, method, and the evidence page
  await page.goto("/investigation.html?mode=preview&stage=before#/");
  await cards(page).first().getByRole("link", { name: "Untrusted affected-lot observation" }).click();
  const task = page.getByTestId("task-MTR-26005");
  await expect(task).toContainText("ACTOR_NOT_AUTHORIZED");
  // MIGRATED (M2, owner O2): preview data is pseudonymised; the raw operator id must not appear.
  await expect(task).toContainText("ACTOR-04");
  await expect(task).not.toContainText("OP-OBSERVATION-21");
  await expect(task).toContainText("HANDHELD_LABEL_READ");
  await page.screenshot({ path: `${screenshots}/03-untrusted-cluster.png`, fullPage: true });
  await task.getByRole("link", { name: "urn:pramaan:MTR-26005:HANDHELD:1" }).first().click();
  const evidence = page.getByTestId("evidence-page");
  await expect(evidence).toContainText("Capture hash");
  expect(await evidence.innerText()).toMatch(/[0-9a-f]{64}/);
  await page.screenshot({ path: `${screenshots}/04-evidence-page.png`, fullPage: true });

  // evidence update: an identity-only motor gains its assembly record; nothing is closed by hand
  await page.goto("/investigation.html?mode=preview&stage=after#/");
  await expect(cards(page)).toHaveCount(5);
  await expect(page.getByTestId("changes")).toContainText(/MTR-26017.*no longer listed/);
  await expect(page.getByTestId("changes")).toContainText(/MTR-26012.*re-evaluated \(version 2 to 3\)/);
  await expect(page.getByRole("button")).toHaveCount(0);
  await page.screenshot({ path: `${screenshots}/05-overview-after-update.png`, fullPage: true });
});

for (const [name, size] of [["desktop", { width: 1280, height: 900 }], ["mobile", { width: 375, height: 740 }]] as const) {
  test(`${name}: overview, cluster and evidence pages have no overflow and pass axe`, async ({ page }) => {
    await page.setViewportSize(size);
    await page.goto("/investigation.html?mode=preview&stage=before#/");
    await expect(cards(page).first()).toBeVisible();
    expect(await overflow(page), `${name} overview overflow`).toBeLessThanOrEqual(0);
    expect(await axe(page), `${name} overview axe`).toEqual([]);
    if (name === "mobile") await page.screenshot({ path: `${screenshots}/mobile-overview.png`, fullPage: true });
    for (const [label, href] of [["cluster", "Untrusted affected-lot observation"], ["gap", "Capture gap"]] as const) {
      await page.goto("/investigation.html?mode=preview&stage=before#/");
      await cards(page).filter({ hasText: label === "gap" ? "ASSY:SHARED-DEMO-STATION" : "ACTOR-04" }).first().getByRole("link", { name: href }).click();
      await expect(page.getByTestId("task-MTR-26005").or(page.getByTestId("task-MTR-26015"))).toBeVisible();
      expect(await overflow(page), `${name} ${label} overflow`).toBeLessThanOrEqual(0);
      expect(await axe(page), `${name} ${label} axe`).toEqual([]);
      if (name === "mobile" && label === "cluster") await page.screenshot({ path: `${screenshots}/mobile-cluster.png`, fullPage: true });
    }
    await page.goto("/investigation.html?mode=preview&stage=before#/evidence/MTR-26005/urn%3Apramaan%3AMTR-26005%3AHANDHELD%3A1");
    await expect(page.getByTestId("evidence-page")).toBeVisible();
    expect(await overflow(page), `${name} evidence overflow`).toBeLessThanOrEqual(0);
    expect(await axe(page), `${name} evidence axe`).toEqual([]);
  });
}

test("keyboard: skip link, group link, filter and breadcrumb work without a pointer", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/investigation.html?mode=preview&stage=before#/");
  await expect(cards(page).first()).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  const select = page.getByLabel("Show");
  await select.focus();
  await select.selectOption("CAPTURE_GAP");
  await expect(cards(page)).toHaveCount(2);
  await cards(page).first().getByRole("link", { name: "Capture gap" }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#\/cluster\/g-/);
  const back = page.getByRole("link", { name: /All groups/ });
  await back.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#\/$/);
});

test("invalid, unknown and malformed addresses are handled in the page", async ({ page }) => {
  await page.goto("/investigation.html?mode=preview#/cluster/g-00000000000000");
  await expect(page.getByTestId("unknown-cluster")).toBeVisible();
  await page.goto("/investigation.html?mode=preview#/evidence/MTR-26005/missing");
  await expect(page.getByTestId("unknown-evidence")).toBeVisible();
  await page.goto("/investigation.html?mode=preview#/cluster/%3Cscript%3E");
  await expect(page.getByTestId("invalid-route")).toBeVisible();
  await page.goto("/investigation.html?mode=preview&stage=nope#/");
  await expect(page.getByTestId("load-error")).toContainText(/Unknown preview stage/);
});

// ---- live, isolated, anchored servers --------------------------------------------------------------

const python = resolve(process.platform === "win32" ? "../.venv/Scripts/python.exe" : "../.venv/bin/python");
interface Ctx { base: string; database: string; kill: () => void; restart: () => Promise<void>; post: (path: string, body: object) => Promise<void> }
async function isolated(page: Page, port: number, body: (ctx: Ctx) => Promise<void>) {
  const database = join(mkdtempSync(join(tmpdir(), "pramaan-workspace-")), "db.sqlite");
  let server: ChildProcess | undefined;
  const base = `http://127.0.0.1:${port}`;
  const start = async () => {
    server = spawn(python, ["recall-ui/tests/browser_server.py", database, "--port", String(port)], { cwd: resolve(".."), stdio: "ignore", windowsHide: true });
    for (let i = 0; i < 80; i++) { try { if ((await fetch(`${base}/api/session`)).ok) return; } catch { /* starting */ } await new Promise((r) => setTimeout(r, 250)); }
    throw new Error("server did not start");
  };
  const post = async (path: string, data: object) => {
    const session = await (await page.request.get(`${base}/api/session`)).json();
    const res = await page.request.post(`${base}/api/${path}`, { headers: { "X-Pramaan-Token": session.token }, data });
    expect(res.ok(), await res.text()).toBeTruthy();
  };
  await start();
  try { await body({ base, database, kill: () => server?.kill(), restart: start, post }); } finally { server?.kill(); }
}

test("live seeded ledger: three actual single-motor groups, untrusted observation first, verified watermark", async ({ page }) => {
  await isolated(page, 4191, async ({ base }) => {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${base}/investigation.html#/`);
    await expect(page.getByTestId("watermark")).toContainText(/Verified ledger journal sequence/, { timeout: 15000 });
    await expect(cards(page)).toHaveCount(3);
    await expect(cards(page).first()).toContainText("Untrusted affected-lot observation");
    await expect(cards(page).first()).toContainText("MTR-26005");
    for (const c of await cards(page).all()) await expect(c).toContainText("1 motor");
    await expect(page.getByText("Preview: not current")).toHaveCount(0);
    await expect(page.getByTestId("obligations")).toContainText("MTR-26005");
    await page.screenshot({ path: `${screenshots}/06-live-seeded.png`, fullPage: true });
  });
});

// MIGRATED (M17, R5 amendment). Original: each write changed the listing within one poll. A write now moves the ledger past the
// checkpoint, so the listing must disappear (nothing is shown as current) until the successor checkpoint is activated; the original
// listing expectations are then asserted unchanged. The page is not reloaded: it keeps polling across the restart and stays read-only.
test("live: an evidence update changes the listing with no manual closure, and the page only reads", async ({ page }) => {
  const stack = await OwnedStack.start(4192);
  try {
    const requests: Array<{ method: string; url: string }> = [];
    page.on("request", (r) => { if (r.url().includes("/api/") || r.url().includes("investigation-demo")) requests.push({ method: r.method(), url: r.url() }); });
    await page.goto(`${stack.base}/investigation.html#/`);
    await expect(cards(page)).toHaveCount(3, { timeout: 15000 });
    const postFromOutside = async (path: string, data: object) => { const r = await stack.post(path, data); expect(r.status, JSON.stringify(r.body)).toBe(200); };
    const mustBeWithheld = async () => {
      await expect(cards(page)).toHaveCount(0, { timeout: 15000 });         // negative: no listing is presented as current in PREFIX_ONLY
      expect(await page.evaluate(() => document.body.innerText)).not.toMatch(/Untrusted affected-lot observation|No trusted baseline/);
    };
    await postFromOutside("units", { serial: "MTR-26021", title: "Identity only" });
    await mustBeWithheld();
    await stack.cycle();
    await expect(cards(page)).toHaveCount(4, { timeout: 20000 });
    await expect(cards(page).filter({ hasText: "MTR-26021" })).toContainText("No trusted baseline");
    await postFromOutside("units/MTR-26021/assemble", { deLot: "BR-310", ndeLot: "BR-312", identity: "SERIAL" });
    await mustBeWithheld();
    await stack.cycle();
    await expect(cards(page)).toHaveCount(3, { timeout: 20000 });
    await expect(page.getByRole("button")).toHaveCount(0);
    await page.screenshot({ path: `${screenshots}/07-live-update.png`, fullPage: true });
    expect(requests.length).toBeGreaterThan(0);
    expect(requests.every((r) => r.method === "GET" && /\/api\/snapshot$/.test(r.url))).toBe(true);
  } finally { await stack.stop(); }
});

test("live: a backend outage withdraws every task, uses no fixture, and recovers when verified again", async ({ page }) => {
  await isolated(page, 4193, async ({ base, kill, restart }) => {
    const fetched: string[] = [];
    page.on("request", (r) => fetched.push(r.url()));
    await page.goto(`${base}/investigation.html#/`);
    await expect(cards(page)).toHaveCount(3, { timeout: 15000 });
    kill();
    await expect(page.getByTestId("withdrawn")).toBeVisible({ timeout: 15000 });
    await expect(cards(page)).toHaveCount(0);
    await expect(page.locator("body")).not.toContainText("MTR-26005");
    await expect(page.getByTestId("withdrawn")).toContainText(/not current/);
    await page.screenshot({ path: `${screenshots}/08-backend-offline.png`, fullPage: true });
    expect(fetched.some((u) => u.includes("snapshot.json") || u.includes("investigation-demo"))).toBe(false);
    await restart();
    await expect(cards(page)).toHaveCount(3, { timeout: 20000 });
  });
});

// MIGRATED (M3/M18). Original faked UNANCHORED at the network boundary on an anchored server; that envelope (UNANCHORED status on a
// CURRENT checkpoint) is contradictory and is withheld. The real scenario is a server started without a trusted anchor: it must show
// no tasks or clusters as current. The old fake is kept as a negative.
test("an unanchored envelope is withheld rather than shown as current", async ({ page }) => {
  const stack = await OwnedStack.start(4195, { unanchored: true });
  try {
    await page.goto(`${stack.base}/investigation.html#/`);
    await expect(page.locator("body")).toContainText(/anchor|unavailable|not current|unverified/i, { timeout: 15000 });
    await expect(cards(page)).toHaveCount(0);
    expect(await page.evaluate(() => document.body.innerText)).not.toMatch(/Verified ledger journal sequence/);
  } finally { await stack.stop(); }
  await isolated(page, 4206, async ({ base }) => {
    await page.route("**/api/snapshot", async (route) => {
      const res = await route.fetch(); const j = await res.json();
      j.freshness.status = "HISTORICAL_UNANCHORED"; j.freshness.maxAgeSeconds = 0;
      await route.fulfill({ json: j });
    });
    await page.goto(`${base}/investigation.html#/`);
    await expect(page.getByTestId("load-error")).toBeVisible({ timeout: 15000 });   // contradictory on first load: never reaches a ready view
    await expect(cards(page)).toHaveCount(0);
  });
});

test("viewing every page does not change decisions, ledger, journal, obligations or external checkpoints", async ({ page }) => {
  await isolated(page, 4194, async ({ base, database }) => {
    const anchorFile = database.replace(/\.sqlite$/, ".test-owner-anchor.json");
    const snap = async () => {
      const j = await (await page.request.get(`${base}/api/snapshot`)).json();
      return { sequence: j.freshness.sequence, headHash: j.freshness.headHash, archiveId: j.freshness.archiveId, decisions: j.decisions, notifications: j.notifications, events: j.units.map((u: { unitId: string; eventCount: number }) => [u.unitId, u.eventCount]) };
    };
    await snap(); // publish any pending evaluations once
    const before = await snap();
    const anchorBefore = readFileSync(anchorFile, "utf8");
    await page.goto(`${base}/investigation.html#/`);
    await expect(cards(page).first()).toBeVisible({ timeout: 15000 });
    const hrefs = await cards(page).getByRole("link").evaluateAll((els) => els.map((e) => (e as HTMLAnchorElement).getAttribute("href")));
    for (const href of hrefs) {
      await page.goto(`${base}/investigation.html${href}`);
      await expect(page.getByTestId("watermark")).toBeVisible();
      for (const link of await page.locator("main a[href^='#/evidence/']").evaluateAll((els) => els.map((e) => e.getAttribute("href")))) {
        await page.goto(`${base}/investigation.html${link}`);
        await expect(page.getByTestId("evidence-page")).toBeVisible();
      }
    }
    await page.waitForTimeout(2500); // allow at least one poll
    expect(await snap()).toEqual(before);
    expect(readFileSync(anchorFile, "utf8")).toBe(anchorBefore);
  });
});
