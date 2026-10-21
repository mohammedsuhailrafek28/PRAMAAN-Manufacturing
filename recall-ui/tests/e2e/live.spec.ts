import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdirSync, writeFileSync } from "node:fs";

const screenshots = "../docs/phase31-screenshots";
test("live manufacturing capture, genealogy, recall, replacement and late withdrawal", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await expect(page.getByText("Live ledger. Synthetic manufacturing data; not production.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Motor decisions" })).toBeVisible();
  mkdirSync(screenshots, { recursive: true });
  await page.screenshot({ path: `${screenshots}/phase3-live-fleet.png`, fullPage: true });
  await page.getByText("Manufacturing capture workspace", { exact: true }).click();
  await page.getByLabel("New motor serial").fill("MTR-E2E-001");
  await page.getByRole("button", { name: "Create unit", exact: true }).click();
  await expect(page.getByTestId("capture-status")).toContainText("Evidence captured");
  await page.getByLabel("Motor to capture").selectOption("MTR-E2E-001");
  const row = page.getByRole("row").filter({ has: page.getByRole("link", { name: "MTR-E2E-001", exact: true }) });
  await expect(row).toContainText("Recall hold");
  const started = Date.now();
  await page.getByRole("button", { name: "Capture bearing assembly", exact: true }).click();
  await expect(row).toContainText("Affected");
  const assemblyVisibleMs = Date.now()-started;
  await page.getByRole("button", { name: "Record synthetic shipment", exact: true }).click();
  await expect(row).toContainText("SHP-26-E2E-001");
  await page.getByRole("button", { name: "Announce recall and evaluate", exact: true }).click();
  await expect(row).toContainText("Affected");
  const replacementStarted = Date.now();
  await page.getByRole("button", { name: "Capture authorized DE replacement", exact: true }).click();
  await expect(row).toContainText("Excluded with evidence");
  const replacementVisibleMs = Date.now()-replacementStarted;
  await page.getByRole("button", { name: "Inject late untrusted affected-lot observation", exact: true }).click();
  await expect(row).toContainText("Recall hold");
  await expect(row).toContainText("Unresolved");
  await page.goto("/#/unit/MTR-E2E-001/genealogy");
  await expect(page.getByRole("heading", { name: "Ledger-backed material genealogy" })).toBeVisible();
  await expect(page.getByText("Shipment capture is not a release authorization.", { exact: false })).toBeVisible();
  await page.screenshot({ path: `${screenshots}/phase3-genealogy.png`, fullPage: true });
  await page.getByRole("tab", { name: "Decision history" }).click();
  await expect(page.getByText("Prior exclusion withdrawn", { exact: false }).first()).toBeVisible();
  await page.screenshot({ path: `${screenshots}/phase3-history.png`, fullPage: true });
  await page.getByRole("tab", { name: "Event log" }).click();
  await page.getByText("Inspect event provenance", { exact: true }).first().click();
  await expect(page.locator("pre").first()).toContainText("captureSha256");
  const provenance = await page.request.get("/api/motors/MTR-E2E-001/provenance");
  expect(provenance.ok()).toBeTruthy();
  await page.reload();
  await expect(page.getByTestId("chip-finding").first()).toContainText("Unresolved");
  writeFileSync("../docs/phase31-validation/browser-latency.json", JSON.stringify({ methodology: "Chrome loopback production build, seeded 5 motors plus one new 16-event motor; one measured workflow; wall-clock button click through visible decision assertion (includes browser assertion polling)", assemblyVisibleMs, replacementVisibleMs }, null, 2));
});

test("live responsive and accessibility review", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of ["/", "/#/unit/MTR-26002/genealogy", "/#/unit/MTR-26005/history", "/#/case06/MTR-26002", "/#/lot/BR-204"]) {
    await page.goto(path);
    await expect(page.locator("main h2").first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth-document.documentElement.clientWidth), path).toBeLessThanOrEqual(0);
  }
  await page.goto("/");
  await page.getByText("Manufacturing capture workspace", { exact: true }).click();
  await expect(page.getByLabel("New motor serial")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(audit.violations.map(v => v.id)).toEqual([]);
  mkdirSync(screenshots, { recursive: true });
  await page.screenshot({ path: `${screenshots}/phase3-mobile-capture.png`, fullPage: true });
});

test("backend failure has no implicit fixture fallback", async ({ page }) => {
  await page.route("**/api/snapshot", r => r.fulfill({ status: 409, json: { error: "Integrity failure" } }));
  await page.goto("/");
  await expect(page.getByTestId("load-error")).toBeVisible();
  await expect(page.getByTestId("chip-finding")).toHaveCount(0);
});
