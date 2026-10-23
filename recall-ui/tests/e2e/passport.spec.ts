import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import jsQR from "jsqr";
import { spawnSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { OwnedServer } from '../support/ownedServer';

const screenshots = "../docs/dpp-screenshots";
const TABS = ["overview", "components", "evidence", "timeline", "recall", "qr"];
const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const axe = async (page: Page) => (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze()).violations.map((v) => `${v.id}: ${v.nodes[0]?.target}`);

// ---- shared seeded, anchored server (port 4173, started by playwright.config.ts) -----------------

test("MTR-26004 passport: replaced DE bearing, claim evidence and hashes, live recall context", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/passport.html#/passport/MTR-26004");
  await expect(page.getByRole("heading", { name: /Digital product passport · MTR-26004/ })).toBeVisible();
  await expect(page.getByTestId("recall-current")).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("Synthetic demonstration data")).toBeVisible();
  mkdirSync(screenshots, { recursive: true });
  await page.screenshot({ path: `${screenshots}/01-overview-desktop.png`, fullPage: true });

  await page.getByRole("link", { name: "Components" }).click();
  await expect(page.getByText("Currently recorded claim").first()).toBeVisible();
  await expect(page.getByText("BRG-MTR-26004-DE-R9")).toBeVisible();
  await page.getByRole("button", { name: /Show replacement history/ }).first().click();
  await expect(page.getByText("Removed (historical)")).toBeVisible();
  await expect(page.getByText("BRG-MTR-26004-DE-01")).toBeVisible();
  await page.screenshot({ path: `${screenshots}/02-components-history.png`, fullPage: true });

  await page.getByRole("link", { name: "View evidence for this claim" }).first().click();
  const detail = page.getByTestId("evidence-detail");
  await expect(detail).toBeVisible();
  await expect(detail).toContainText("Capture SHA-256");
  expect(await detail.innerText()).toMatch(/[0-9a-f]{64}/);
  await expect(detail).toContainText("Not a trusted time source");
  await page.screenshot({ path: `${screenshots}/03-evidence-drilldown.png`, fullPage: true });

  await page.getByRole("link", { name: "Timeline" }).click();
  await expect(page.getByText(/No capture session recorded for the Assembly station/)).toBeVisible();
  await page.screenshot({ path: `${screenshots}/04-timeline.png`, fullPage: true });
});

test("the QR on the page decodes to the route-only address", async ({ page }) => {
  await page.setViewportSize({ width: 1000, height: 900 });
  await page.goto("/passport.html#/passport/MTR-26004/qr");
  const svg = page.getByTestId("qr-svg");
  await expect(svg).toBeVisible();
  const d = await svg.locator("path").getAttribute("d");
  const viewBox = (await svg.getAttribute("viewBox"))!.split(" ").map(Number);
  const n = viewBox[2];
  const scale = 6, px = n * scale, rgba = new Uint8ClampedArray(px * px * 4).fill(255);
  for (const m of d!.matchAll(/M(\d+) (\d+)h(\d+)v1h-\d+z/g)) {
    const [x0, y, w] = [Number(m[1]), Number(m[2]), Number(m[3])];
    for (let x = x0; x < x0 + w; x++) for (let dy = 0; dy < scale; dy++) for (let dx = 0; dx < scale; dx++) {
      const i = ((y * scale + dy) * px + x * scale + dx) * 4;
      rgba[i] = rgba[i + 1] = rgba[i + 2] = 0;
    }
  }
  const decoded = jsQR(rgba, px, px)?.data;
  expect(decoded).toBe("http://127.0.0.1:4173/passport.html#/passport/MTR-26004");
  await expect(page.getByTestId("qr-url")).toHaveText(decoded!);
  await expect(page.getByText(/will not work while this application is restricted to 127\.0\.0\.1/)).toBeVisible();
  await page.getByTestId("qr-svg").screenshot({ path: `${screenshots}/05-qr-label.png` });
});

test("passport pages issue only GET requests and never fetch preview data in live mode", async ({ page }) => {
  const requests: Array<{ method: string; url: string }> = [];
  page.on("request", (r) => { if (r.url().includes("/api/") || r.url().includes("passport-preview")) requests.push({ method: r.method(), url: r.url() }); });
  for (const tab of TABS) { await page.goto(`/passport.html#/passport/MTR-26003/${tab}`); await page.waitForTimeout(400); }
  expect(requests.length).toBeGreaterThan(0);
  expect(requests.every((r) => r.method === "GET")).toBe(true);
  expect(requests.every((r) => /\/api\/snapshot$/.test(r.url))).toBe(true);
  expect(requests.some((r) => r.url.includes("passport-preview"))).toBe(false);
});

for (const [name, size] of [["desktop", { width: 1280, height: 900 }], ["mobile", { width: 375, height: 740 }]] as const) {
  test(`${name}: every section has no horizontal overflow and passes axe`, async ({ page }) => {
    await page.setViewportSize(size);
    for (const tab of TABS) {
      const suffix = tab === "evidence" ? "/urn%3Apramaan%3AMTR-26004%3AREWORK%3A2" : "";
      await page.goto(`/passport.html#/passport/MTR-26004/${tab}${suffix}`);
      await expect(page.getByRole("heading", { name: /MTR-26004/ }).first()).toBeVisible();
      await page.waitForTimeout(200);
      if (tab === "components") await page.getByRole("button", { name: /Show replacement history/ }).first().click();
      expect(await overflow(page), `${name} ${tab} overflow`).toBeLessThanOrEqual(0);
      expect(await axe(page), `${name} ${tab} axe`).toEqual([]);
      if (name === "mobile" && tab !== "evidence") await page.screenshot({ path: `${screenshots}/mobile-${tab}.png`, fullPage: true });
    }
  });
}

test("keyboard: skip link, section navigation and replacement-history toggle", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/passport.html#/passport/MTR-26004/components");
  await expect(page.getByRole("heading", { name: /MTR-26004/ }).first()).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  const nav = page.getByRole("navigation", { name: "Passport sections" });
  await nav.getByRole("link", { name: "Timeline" }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/passport\/MTR-26004\/timeline$/);
  await expect(page.getByRole("link", { name: "Timeline" })).toHaveAttribute("aria-current", "page");
  await page.goto("/passport.html#/passport/MTR-26004/components");
  const toggle = page.getByRole("button", { name: /replacement history/ }).first();
  await toggle.focus();
  await page.keyboard.press("Space");
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByText("Removed (historical)")).toBeVisible();
});

test("invalid and unknown identifiers produce no passport and no QR", async ({ page }) => {
  await page.goto("/passport.html#/passport/MTR-1%3Fx%3D1");
  await expect(page.getByTestId("invalid-id")).toBeVisible();
  await expect(page.getByTestId("qr-svg")).toHaveCount(0);
  await page.goto("/passport.html#/passport/MTR-99999/qr");
  await expect(page.getByTestId("unknown-unit")).toBeVisible();
  await expect(page.getByTestId("qr-svg")).toHaveCount(0);
});

test("explicit preview mode is labelled and never shows recall status", async ({ page }) => {
  await page.goto("/passport.html?mode=preview#/passport/MTR-26003");
  await expect(page.getByTestId("passport-banner")).toContainText(/not a verified live ledger/);
  await expect(page.getByText("Current recall status unavailable").first()).toBeVisible();
  await expect(page.getByTestId("recall-current")).toHaveCount(0);
  await expect(page.getByText(/Source: Preview/)).toBeVisible();
  await page.screenshot({ path: `${screenshots}/06-preview-mode.png`, fullPage: true });
});

// ---- isolated server: external writer, outage, and read-only invariance -----------------------

const python = resolve(process.platform === "win32" ? "../.venv/Scripts/python.exe" : "../.venv/bin/python");
async function isolated(port: number, body: (ctx: { base: string; database: string; kill: () => Promise<void>; restart: () => Promise<void> }) => Promise<void>) {
  const server=new OwnedServer(port);
  try { await server.start(); await body({ base:server.base,database:server.database,kill:()=>server.stop(),restart:()=>server.start() }); }
  finally { await server.dispose(); }
}
const writeHold = (database: string, motor: string) => {
  const w = spawnSync(python, ["-c", `import sys;from application.service import Manufacturing;a=Manufacturing(sys.argv[1]);a.observe(sys.argv[2],'BR-204');a.close()`, database, motor], { cwd: resolve(".."), encoding: "utf8", windowsHide: true });
  expect(w.status, w.stderr).toBe(0);
};

test("external writer: recall context changes on the passport without any API command", async ({ page }) => {
  await isolated(4185, async ({ base, database }) => {
    await page.goto(`${base}/passport.html#/passport/MTR-26003/recall`);
    await expect(page.getByTestId("recall-current")).toContainText("No recall hold recorded under this policy", { timeout: 15000 });
    writeHold(database, "MTR-26003");
    await expect(page.getByTestId("recall-current")).toContainText("Held under the recall policy", { timeout: 12000 });
  });
});

test("backend outage withdraws recall status, labels records stale and never substitutes fixtures", async ({ page }) => {
  await isolated(4186, async ({ base, kill, restart }) => {
    const fetched: string[] = [];
    page.on("request", (r) => fetched.push(r.url()));
    await page.goto(`${base}/passport.html#/passport/MTR-26003/recall`);
    await expect(page.getByTestId("recall-current")).toBeVisible({ timeout: 15000 });
    await kill();
    await expect(page.getByTestId("recall-unavailable")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("passport-banner")).toContainText(/may be outdated/i);
    await expect(page.locator("body")).not.toContainText("No recall hold recorded");
    await page.screenshot({ path: `${screenshots}/07-backend-offline.png`, fullPage: true });
    expect(fetched.some((u) => u.includes("preview") || u.includes("snapshot.json"))).toBe(false);
    await restart();
    await expect(page.getByTestId("recall-current")).toBeVisible({ timeout: 20000 });
  });
});

test("an unanchored backend yields records labelled unverified and no recall status", async ({ page }) => {
  // The shared server is anchored; simulate an unanchored envelope at the network boundary only.
  await page.route("**/api/snapshot", async (route) => {
    const res = await route.fetch(); const j = await res.json();
    j.freshness.status = "HISTORICAL_UNANCHORED"; j.freshness.maxAgeSeconds = 0;
    await route.fulfill({ json: j });
  });
  await page.goto("/passport.html#/passport/MTR-26003");
  await expect(page.getByTestId("passport-banner")).toContainText(/anchor|unavailable/i);
  await expect(page.getByText("Current recall status unavailable").first()).toBeVisible();
  await expect(page.getByTestId("recall-current")).toHaveCount(0);
});

test("viewing every passport section does not change ledger, journal, decisions or obligations", async ({ page }) => {
  await isolated(4187, async ({ base }) => {
    const snap = async () => {
      const j = await (await page.request.get(`${base}/api/snapshot`)).json();
      return { sequence: j.freshness.sequence, headHash: j.freshness.headHash, archiveId: j.freshness.archiveId, decisions: j.decisions, notifications: j.notifications, events: j.units.map((u: { unitId: string; eventCount: number }) => [u.unitId, u.eventCount]) };
    };
    await snap(); // publish any pending evaluations once
    const before = await snap();
    for (const id of ["MTR-26001", "MTR-26004", "MTR-26005"]) for (const tab of TABS) {
      await page.goto(`${base}/passport.html#/passport/${id}/${tab}`);
      await page.waitForTimeout(150);
    }
    await page.waitForTimeout(2500); // allow at least one poll
    const after = await snap();
    expect(after).toEqual(before);
  });
});
