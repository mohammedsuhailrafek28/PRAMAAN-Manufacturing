import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.describe.configure({ mode: "serial" });
const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const LONG = "MTR-" + "LONGIDENTIFIER-0123456789".repeat(2).slice(0, 30);

async function longUnit(page: Page) {
  const token = (await (await page.request.get("/api/session")).json()).token;
  const post = async (path: string, body: object) => {
    const res = await page.request.post(path, { data: body, headers: { "X-Pramaan-Token": token } });
    expect(res.ok(), `${path}: ${await res.text()}`).toBeTruthy();
  };
  const existing = await (await page.request.get("/api/motors")).json();
  if (!existing.some((u: { unitId: string }) => u.unitId === LONG)) {
    await post("/api/units", { serial: LONG });
    await post(`/api/units/${LONG}/assemble`, { deLot: "BR-204", ndeLot: "BR-310", identity: "SERIAL" });
    await post(`/api/units/${LONG}/ship`, {});
  }
}

for (const [name, size] of [["mobile", { width: 390, height: 844 }], ["desktop", { width: 1440, height: 1000 }]] as const) {
  test(`${name}: long identifiers never widen the page and every view passes axe`, async ({ page }) => {
    await longUnit(page);
    await page.setViewportSize(size);
    for (const path of ["/", `/#/unit/${LONG}/decision`, `/#/unit/${LONG}/genealogy`, `/#/unit/${LONG}/history`, `/#/unit/${LONG}/events`, "/#/lot/BR-204"]) {
      await page.goto(path);
      await expect(page.locator("main h2").first()).toBeVisible();
      if (path.endsWith("/events")) await page.getByText("Inspect event provenance", { exact: true }).first().click();
      expect(await overflow(page), `${name} ${path}`).toBeLessThanOrEqual(0);
      const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      expect(audit.violations.map((v) => `${v.id} @ ${path}`)).toEqual([]);
    }
  });
}

test("genealogy diagram region is reachable and scrollable by keyboard", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#/unit/MTR-26001/genealogy");
  const region = page.getByRole("region", { name: /Genealogy diagram for MTR-26001/ });
  await expect(region).toBeVisible();
  let reached = false;
  for (let i = 0; i < 40 && !reached; i++) {
    await page.keyboard.press("Tab");
    reached = await region.evaluate((el) => el === document.activeElement);
  }
  expect(reached).toBeTruthy();
  const before = await region.evaluate((el) => el.scrollLeft);
  await page.keyboard.press("ArrowRight");
  expect(await region.evaluate((el) => el.scrollLeft)).toBeGreaterThan(before);
});

test("backend unreachable after a successful load marks everything historical, then recovers", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("chip-action").first()).toContainText(/Recall hold|Release eligible/);
  await expect(page.getByTestId("stale-banner")).toHaveCount(0);
  await page.route("**/api/heartbeat", (route) => route.abort("connectionrefused"));
  const banner = page.getByTestId("stale-banner");
  await expect(banner).toBeVisible({ timeout: 15_000 });
  await expect(banner).toContainText("not current operational status");
  await expect(page.getByTestId("chip-action").first()).toContainText("Last recorded action");
  await expect(page.getByRole("button", { name: "Create unit", exact: true })).toBeHidden();  // workbench is collapsed...
  await page.getByText("Manufacturing capture workspace", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Create unit", exact: true })).toBeDisabled();  // ...and disabled while stale
  await page.unroute("**/api/heartbeat");
  await expect(banner).toHaveCount(0, { timeout: 15_000 });
  await expect(page.getByTestId("chip-action").first()).not.toContainText("Last recorded action");
});

test("a hung ledger on first load times out into an error, never an indefinite spinner", async ({ page }) => {
  await page.route("**/api/snapshot", () => { /* never fulfilled */ });
  await page.goto("/");
  await expect(page.getByTestId("load-error")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("chip-finding")).toHaveCount(0);
});
