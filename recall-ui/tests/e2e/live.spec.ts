import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mkdirSync } from "node:fs";
import { OwnedStack } from "../support/ownedStack";

const screenshots = "../docs/phase31-screenshots";
// MIGRATED (M12). Original: one shared seeded server; every click wrote to the ledger and the next decision was expected
// immediately. Conflicting approved contract (Option A R5/R10 + R5 amendment): a capture moves the ledger past the active
// checkpoint, so the console withholds every current decision until a successor checkpoint is activated. Replacement: an OWNED
// per-test stack (own ledger, custody dir, root checkpoint, port); after every capture the test asserts the console is
// PREFIX_ONLY (no clearance, global warning), runs the explicit test-only custodian cycle (propose -> accept with typed digest ->
// restart with --trusted-anchor/--previous-anchor), reloads, and then asserts the original row expectations unchanged.
// Negative: between capture and activation no decision, hold or release label for the motor is shown.
test("live manufacturing capture, genealogy, recall, replacement and late withdrawal", async ({ page }) => {
  test.setTimeout(240_000);
  const stack = await OwnedStack.start(4203);
  try {
    const url = (hash = "") => `${stack.base}/${hash}`;
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(url());
    await expect(page.getByText("Live ledger. Synthetic manufacturing data; not production.")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Motor decisions" })).toBeVisible();
    mkdirSync(screenshots, { recursive: true });
    await page.screenshot({ path: `${screenshots}/phase3-live-fleet.png`, fullPage: true });
    const openWorkspace = async () => { await page.getByText("Manufacturing capture workspace", { exact: true }).click(); };
    const withheldThenActivate = async () => {
      await expect(page.getByRole("heading", { name: "Checkpoint required" })).toBeVisible({ timeout: 10_000 });
      await expect(page.getByTestId("no-shipment-warning")).toBeVisible();
      await expect(page.getByTestId("chip-action")).toHaveCount(0);
      expect(await page.evaluate(() => document.body.innerText)).not.toMatch(/Release eligible|Recall hold|Excluded with evidence|Affected/);
      expect(await stack.cycle()).toBe("LOCAL_CUSTODY_ACCEPTANCE_OPERATOR_ASSERTED_NOT_INDEPENDENT");
      await page.reload();
      await expect(page.getByRole("heading", { name: "Motor decisions" })).toBeVisible({ timeout: 15_000 });
    };
    const rowFor = () => page.getByRole("row").filter({ has: page.getByRole("link", { name: "MTR-E2E-001", exact: true }) });

    await openWorkspace();
    await page.getByLabel("New motor serial").fill("MTR-E2E-001");
    await page.getByRole("button", { name: "Create unit", exact: true }).click();
    await expect(page.getByTestId("capture-status")).toContainText("Evidence captured");
    await withheldThenActivate();
    const row = rowFor();
    await expect(row).toContainText("Recall hold");

    await openWorkspace();
    await page.getByLabel("Motor to capture").selectOption("MTR-E2E-001");
    const started = Date.now();
    await page.getByRole("button", { name: "Capture bearing assembly", exact: true }).click();
    await withheldThenActivate();
    await expect(rowFor()).toContainText("Affected");
    const assemblyToCurrentMs = Date.now() - started;

    // CHANGED (owner-approved shipment gate): the ordinary ship operation records a shipment only for a motor with a current checkpoint AND current release
    // eligibility. This motor is under recall hold, so the same request that used to be recorded is now refused and writes nothing (no cycle is needed).
    const shipped = await stack.post("units/MTR-E2E-001/ship", {});
    expect(shipped.status).toBe(409);
    expect(shipped.body.error).toBe("SHIPMENT_REFUSED");
    const afterRefusal = await (await page.request.get(`${stack.base}/api/snapshot`)).json();
    expect(afterRefusal.checkpoint.state).toBe("ANCHORED_CURRENT");
    expect(afterRefusal.units.find((u: { unitId: string }) => u.unitId === "MTR-E2E-001").shipment).toBeNull();
    await expect(rowFor()).not.toContainText("SHP-26-E2E-001");

    await openWorkspace(); await page.getByLabel("Motor to capture").selectOption("MTR-E2E-001");
    const seqBefore = (await (await page.request.get(`${stack.base}/api/snapshot`)).json()).freshness.sequence;
    await page.getByRole("button", { name: "Announce recall and evaluate", exact: true }).click();
    await expect(page.getByTestId("capture-status")).toContainText("Evidence captured");
    // The seeded recall policy is already announced, so this command is idempotent and appends nothing to the journal:
    // the ledger is not newer than the checkpoint and the console correctly stays CURRENT (no cycle needed, none invented).
    const after = (await (await page.request.get(`${stack.base}/api/snapshot`)).json());
    expect(after.freshness.sequence).toBe(seqBefore);
    expect(after.checkpoint.state).toBe("ANCHORED_CURRENT");
    await expect(rowFor()).toContainText("Affected");

    await openWorkspace(); await page.getByLabel("Motor to capture").selectOption("MTR-E2E-001");
    const replacementStarted = Date.now();
    await page.getByRole("button", { name: "Capture authorized DE replacement", exact: true }).click();
    await withheldThenActivate();
    await expect(rowFor()).toContainText("Excluded with evidence");
    const replacementToCurrentMs = Date.now() - replacementStarted;

    await openWorkspace(); await page.getByLabel("Motor to capture").selectOption("MTR-E2E-001");
    await page.getByRole("button", { name: "Inject late untrusted affected-lot observation", exact: true }).click();
    await withheldThenActivate();
    await expect(rowFor()).toContainText("Recall hold");
    await expect(rowFor()).toContainText("Unresolved");
    expect(stack.generations).toBe(4);                                     // four legitimate successor generations, each accepted explicitly (the refused shipment needed none)

    await page.goto(url("#/unit/MTR-E2E-001/genealogy"));
    await expect(page.getByRole("heading", { name: "Ledger-backed material genealogy" })).toBeVisible();
    await expect(page.getByText("Shipment capture is not a release authorization.", { exact: false })).toHaveCount(0);   // CHANGED: this motor's shipment was refused, so no shipment note
    await page.goto(url("#/unit/MTR-26001/genealogy"));                       // a seeded historical-fixture shipment still carries the note
    await expect(page.getByText("Shipment capture is not a release authorization.", { exact: false })).toBeVisible();
    await page.goto(url("#/unit/MTR-E2E-001/genealogy"));
    await expect(page.getByRole("heading", { name: "Ledger-backed material genealogy" })).toBeVisible();
    await page.screenshot({ path: `${screenshots}/phase3-genealogy.png`, fullPage: true });
    await page.getByRole("tab", { name: "Decision history" }).click();
    await expect(page.getByText("Prior exclusion withdrawn", { exact: false }).first()).toBeVisible();
    await page.screenshot({ path: `${screenshots}/phase3-history.png`, fullPage: true });
    await page.getByRole("tab", { name: "Event log" }).click();
    await page.getByText("Inspect event provenance", { exact: true }).first().click();
    await expect(page.locator("pre").first()).toContainText("captureSha256");
    const provenance = await page.request.get(`${stack.base}/api/motors/MTR-E2E-001/provenance`);
    expect(provenance.ok()).toBeTruthy();
    await page.reload();
    await expect(page.getByTestId("chip-finding").first()).toContainText("Unresolved");
    // the shared tracked browser-latency.json is not rewritten: capture-to-current now includes an explicit checkpoint cycle
    test.info().annotations.push({ type: "capture-to-current-ms", description: JSON.stringify({ assemblyToCurrentMs, replacementToCurrentMs }) });
  } finally {
    await stack.stop();
  }
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
