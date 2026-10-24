import { test, expect } from "@playwright/test";
import { OwnedStack } from "../support/ownedStack";

// Real-browser regression for v1.1 NDE replacement and provisional sightings. Owned per-test stacks (own ledger, custody, checkpoint, port).
// The custodian cycle is the same TEST-ONLY propose/accept helper the other live specs use: local test custody, not independent custody.
// A sighting is an UNVERIFIED claim: it holds the motor, never clears or excludes anything, and is superseded only by a physical re-installation.

async function openWorkspace(page: import("@playwright/test").Page) { await page.getByText("Manufacturing capture workspace", { exact: true }).click(); }
const snapshot = async (stack: OwnedStack) => (await fetch(`${stack.base}/api/snapshot`)).json();
const current = (snap: any, motor: string) => Object.values<any>(snap.decisions[motor])[0].current;
const ACCEPTED = "LOCAL_CUSTODY_ACCEPTANCE_OPERATOR_ASSERTED_NOT_INDEPENDENT";

test("NDE replacement through the browser form: original evidence kept, eligible only after a newly accepted checkpoint", async ({ page }) => {
  test.setTimeout(240_000);
  const stack = await OwnedStack.start(4231);
  try {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(stack.base + "/");
    await expect(page.getByRole("heading", { name: "Motor decisions" })).toBeVisible();
    expect((await snapshot(stack)).eligibility["MTR-26003"].currentReleaseEligible).toBe(true);
    await openWorkspace(page);
    await page.getByLabel("Motor to capture").selectOption("MTR-26003");
    await page.getByLabel("Replacement slot").selectOption("NDE");
    await page.getByLabel(/Replacement NDE lot/).fill("BR-2O4");                         // not a registered lot: refused, nothing written
    await page.getByRole("button", { name: "Capture authorized NDE replacement", exact: true }).click();
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 10_000 });
    expect((await snapshot(stack)).units.find((u: any) => u.unitId === "MTR-26003").eventCount).toBe(9);   // the refused command appended no event
    await page.reload();
    await openWorkspace(page);
    await page.getByLabel("Motor to capture").selectOption("MTR-26003");
    await page.getByLabel("Replacement slot").selectOption("NDE");
    await page.getByLabel(/Replacement NDE lot/).fill("BR-311");
    await page.getByRole("button", { name: "Capture authorized NDE replacement", exact: true }).click();
    await expect(page.getByTestId("capture-status")).toContainText("Evidence captured");
    await expect(page.getByRole("heading", { name: "Checkpoint required" })).toBeVisible({ timeout: 10_000 });
    expect(await page.evaluate(() => document.body.innerText)).not.toMatch(/Release eligible/);   // no clearance from the capture alone
    expect(await stack.cycle()).toBe(ACCEPTED);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Motor decisions" })).toBeVisible({ timeout: 15_000 });
    const after = await snapshot(stack);
    expect(after.checkpoint.state).toBe("ANCHORED_CURRENT");
    expect(after.eligibility["MTR-26003"].currentReleaseEligible).toBe(true);
    const nde = after.components.filter((c: any) => c.unitId === "MTR-26003" && c.slot === "NDE");
    expect(nde.map((c: any) => c.lot)).toEqual(["BR-312", "BR-311"]);                   // original install preserved and removed, new registered lot installed
    expect(nde[0].removedAt).toBeTruthy();
    const de = after.components.filter((c: any) => c.unitId === "MTR-26003" && c.slot === "DE");
    expect(de.map((c: any) => c.lot)).toEqual(["BR-310"]);                                // DE untouched
  } finally {
    await stack.stop();
  }
});

test("provisional sighting on an excluded motor: console withholds, renewal is refused, recovery is a controlled NDE replacement", async ({ page }) => {
  test.setTimeout(240_000);
  const stack = await OwnedStack.start(4234);
  try {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(stack.base + "/");
    await expect(page.getByRole("heading", { name: "Motor decisions" })).toBeVisible();
    await openWorkspace(page);
    await page.getByLabel("Motor to capture").selectOption("MTR-26003");
    await page.getByLabel("Sighted label (as read; may be wrong)").fill("BR-2O4");
    await page.getByLabel("Sighting slot").selectOption("NDE");
    await page.getByRole("button", { name: "Record unverified sighting", exact: true }).click();
    await expect(page.getByTestId("capture-status")).toContainText("Evidence captured");
    await expect(page.getByRole("heading", { name: "Checkpoint required" })).toBeVisible({ timeout: 10_000 });
    const prov = JSON.stringify(await (await fetch(`${stack.base}/api/motors/MTR-26003/provenance`)).json());
    expect(prov).toContain("BR-2O4");                                                      // stored verbatim

    // Renewal is refused: an exclusion now rests on an identity that is not established; acknowledgement cannot override it.
    expect(await stack.cycleExpectRefusal()).toContain("not established");
    await page.reload();
    await expect(page.getByRole("heading", { name: "Checkpoint required" })).toBeVisible({ timeout: 15_000 });
    expect(await page.evaluate(() => document.body.innerText)).not.toMatch(/Release eligible/);
    // KNOWN GAP (reported): the console cannot capture while the checkpoint is stale, so the recovery below is an API/operator step, not a UI step.
    await expect(page.getByText("Manufacturing capture workspace", { exact: true })).toHaveCount(0);

    expect((await stack.post("units/MTR-26003/replace", { lot: "BR-311", slot: "NDE" })).status).toBe(200);
    expect(await stack.cycle()).toBe(ACCEPTED);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Motor decisions" })).toBeVisible({ timeout: 15_000 });
    const after = await snapshot(stack);
    expect(after.eligibility["MTR-26003"].currentReleaseEligible).toBe(true);              // the stale sighting is superseded by the physical re-installation
    expect(JSON.stringify(after.units.find((u: any) => u.unitId === "MTR-26003").events)).toContain("BR-2O4");   // and still in the ledger
  } finally {
    await stack.stop();
  }
});

test("provisional sighting on an affected motor is shown as unverified, advisory, never clearing", async ({ page }) => {
  test.setTimeout(240_000);
  const stack = await OwnedStack.start(4232);
  try {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(stack.base + "/");
    await expect(page.getByRole("heading", { name: "Motor decisions" })).toBeVisible();
    const entriesBefore = (await snapshot(stack)).lotIdentity.registry.entryCount;
    await openWorkspace(page);
    await page.getByLabel("Motor to capture").selectOption("MTR-26001");
    await page.getByLabel("Sighted label (as read; may be wrong)").fill("UNKNOWN");
    await page.getByLabel("Sighting slot").selectOption("DE");
    await page.getByRole("button", { name: "Record unverified sighting", exact: true }).click();
    await expect(page.getByTestId("capture-status")).toContainText("Evidence captured");
    expect(await stack.cycle()).toBe(ACCEPTED);                                            // already held by the evaluator: not an identity-unsafe exclusion
    await page.goto(stack.base + "/#/unit/MTR-26001/decision");
    await page.reload();
    const guard = page.getByTestId("identity-guard");
    await expect(guard).toBeVisible({ timeout: 15_000 });
    await expect(guard).toContainText("Lot identity not established");
    await expect(guard).toContainText("UNKNOWN");
    await expect(page.getByTestId("quarantine")).toContainText("Quarantined, not cleared");
    await expect(page.getByTestId("quarantine")).toContainText("never implies clearance");
    const snap = await snapshot(stack);
    expect(snap.eligibility["MTR-26001"].currentReleaseEligible).toBe(false);
    expect(current(snap, "MTR-26001").operationalAction).toBe("RECALL_HOLD");
    expect(snap.lotIdentity.registry.entryCount).toBe(entriesBefore);                        // no registry entry was created
  } finally {
    await stack.stop();
  }
});
