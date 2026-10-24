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

test("provisional sighting on an excluded motor: that motor stays held, unrelated motors are renewed, recovery is available in the console", async ({ page }) => {
  test.setTimeout(240_000);
  const stack = await OwnedStack.start(4234);
  try {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(stack.base + "/");
    await expect(page.getByRole("heading", { name: "Motor decisions" })).toBeVisible();
    const baseline = await snapshot(stack);
    const eligibleBefore = Object.fromEntries(Object.entries<any>(baseline.eligibility).map(([m, v]) => [m, v.currentReleaseEligible]));
    expect(eligibleBefore["MTR-26003"]).toBe(true);
    await openWorkspace(page);
    await page.getByLabel("Motor to capture").selectOption("MTR-26003");
    await page.getByLabel("Sighted label (as read; may be wrong)").fill("ZZ-9");        // not a look-alike of any lot in use elsewhere: isolation can be established
    await page.getByLabel("Sighting slot").selectOption("NDE");
    await page.getByRole("button", { name: "Record unverified sighting", exact: true }).click();
    await expect(page.getByTestId("capture-status")).toContainText("Evidence captured");
    await expect(page.getByRole("heading", { name: "Checkpoint required" })).toBeVisible({ timeout: 10_000 });
    const prov = JSON.stringify(await (await fetch(`${stack.base}/api/motors/MTR-26003/provenance`)).json());
    expect(prov).toContain("ZZ-9");                                                        // stored verbatim

    // The stale console now offers the restricted recovery workspace instead of a dead end.
    const recovery = page.getByTestId("recovery-workspace");
    await expect(recovery).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("recovery-held")).toContainText("MTR-26003");
    expect(await page.evaluate(() => document.body.innerText)).not.toMatch(/Release eligible/);
    await page.getByTestId("recovery-propose").click();
    const proposal = page.getByTestId("recovery-proposal");
    await expect(proposal).toContainText("Contained, stays held: MTR-26003", { timeout: 60_000 });
    await expect(proposal).toContainText("Refused (candidate cannot be accepted): none");
    expect((await snapshot(stack)).checkpoint.state).toBe("ANCHORED_PREFIX_ONLY");         // proposing activated nothing

    // Operator acceptance (test-only custodian): the sighted motor is contained, everything else is renewed.
    expect(await stack.cycle()).toBe(ACCEPTED);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Motor decisions" })).toBeVisible({ timeout: 15_000 });
    const mid = await snapshot(stack);
    expect(mid.checkpoint.state).toBe("ANCHORED_CURRENT");
    expect(mid.eligibility["MTR-26003"].currentReleaseEligible).toBe(false);
    expect(current(mid, "MTR-26003").operationalAction).toBe("RECALL_HOLD");
    expect(current(mid, "MTR-26003").identityGuard.findings.map((f: any) => f.source)).toContain("OBSERVATION");
    for (const m of Object.keys(eligibleBefore).filter(m => m !== "MTR-26003")) expect(mid.eligibility[m].currentReleaseEligible).toBe(eligibleBefore[m]);   // unrelated motors unchanged

    // Controlled replacement supersedes the sighting; eligibility returns only after another reviewed checkpoint.
    await openWorkspace(page);
    await page.getByLabel("Motor to capture").selectOption("MTR-26003");
    await page.getByLabel("Replacement slot").selectOption("NDE");
    await page.getByLabel(/Replacement NDE lot/).fill("BR-311");
    await page.getByRole("button", { name: "Capture authorized NDE replacement", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Checkpoint required" })).toBeVisible({ timeout: 10_000 });
    expect(await stack.cycle()).toBe(ACCEPTED);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Motor decisions" })).toBeVisible({ timeout: 15_000 });
    const after = await snapshot(stack);
    expect(after.eligibility["MTR-26003"].currentReleaseEligible).toBe(true);
    expect(JSON.stringify(after.units.find((u: any) => u.unitId === "MTR-26003").events)).toContain("ZZ-9");   // the sighting is still in the ledger
  } finally {
    await stack.stop();
  }
});

test("mandatory global refusal: a sighting string shared by two motors is not contained and the whole candidate is refused", async ({ page }) => {
  test.setTimeout(240_000);
  const stack = await OwnedStack.start(4235);
  try {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(stack.base + "/");
    await expect(page.getByRole("heading", { name: "Motor decisions" })).toBeVisible();
    await openWorkspace(page);
    await page.getByLabel("Motor to capture").selectOption("MTR-26003");                    // the same label read on two motors: cross-motor identity is uncertain
    await page.getByLabel("Sighted label (as read; may be wrong)").fill("ZZ-9");
    await page.getByLabel("Sighting slot").selectOption("NDE");
    await page.getByRole("button", { name: "Record unverified sighting", exact: true }).click();
    await expect(page.getByTestId("recovery-workspace")).toBeVisible({ timeout: 10_000 });
    await page.getByTestId("recovery-motor").selectOption("MTR-26004");                      // the console is stale: the second reading goes through the recovery surface
    await page.getByTestId("recovery-sighting").fill("zz 9");
    await page.getByRole("button", { name: "Record unverified sighting", exact: true }).click();
    await expect(page.getByTestId("recovery-held")).toContainText("MTR-26004", { timeout: 15_000 });
    await page.getByTestId("recovery-propose").click();
    await expect(page.getByTestId("recovery-proposal")).toContainText("Refused (candidate cannot be accepted): MTR-26003.", { timeout: 60_000 });
    expect(await stack.cycleExpectRefusal()).toContain("isolation");
    await page.reload();
    await expect(page.getByRole("heading", { name: "Checkpoint required" })).toBeVisible({ timeout: 15_000 });
    const snap = await snapshot(stack);
    expect(Object.values<any>(snap.eligibility).every(v => v.currentReleaseEligible === false)).toBe(true);
  } finally {
    await stack.stop();
  }
});

test("recovery workspace: capture and reconcile while stale, no shipment or release control exists, prohibited routes are refused", async ({ page }) => {
  test.setTimeout(240_000);
  const stack = await OwnedStack.start(4236);
  try {
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(stack.base + "/");
    await expect(page.getByRole("heading", { name: "Motor decisions" })).toBeVisible();
    await openWorkspace(page);
    await page.getByLabel("Motor to capture").selectOption("MTR-26003");
    await page.getByLabel("Sighted label (as read; may be wrong)").fill("QX-77");
    await page.getByLabel("Sighting slot").selectOption("DE");
    await page.getByRole("button", { name: "Record unverified sighting", exact: true }).click();
    await expect(page.getByTestId("recovery-workspace")).toBeVisible({ timeout: 10_000 });
    const names = await page.getByRole("button").allInnerTexts();
    expect(names.join("|")).not.toMatch(/ship|announce|accept|activate|release/i);          // no such control is offered in the stale console
    // Reconcile through the recovery surface itself: a registered replacement supersedes the unverified DE sighting.
    await page.getByTestId("recovery-motor").selectOption("MTR-26003");
    await page.getByTestId("recovery-replacement").fill("BR-311");
    await page.getByRole("button", { name: "Capture controlled replacement", exact: true }).click();
    await expect(page.getByTestId("recovery-workspace")).toContainText("None are held", { timeout: 15_000 });   // superseded: no longer held by the sighting
    expect((await snapshot(stack)).units.find((u: any) => u.unitId === "MTR-26003").eventCount).toBeGreaterThan(9);
    // The stale server withholds every release even after recovery captures.
    const stale = await snapshot(stack);
    expect(stale.checkpoint.state).toBe("ANCHORED_PREFIX_ONLY");
    expect(Object.values<any>(stale.eligibility).every(v => v.currentReleaseEligible === false)).toBe(true);
    // Prohibited routes do not exist on the recovery surface and write nothing.
    const before = (await snapshot(stack)).units.reduce((n: number, u: any) => n + u.eventCount, 0);
    for (const action of ["ship", "announce", "accept", "activate", "release"]) expect((await stack.post(`recovery/${action}`, { motor: "MTR-26003" })).status).toBe(404);
    expect((await snapshot(stack)).units.reduce((n: number, u: any) => n + u.eventCount, 0)).toBe(before);
    expect(await stack.cycle()).toBe(ACCEPTED);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Motor decisions" })).toBeVisible({ timeout: 15_000 });
    expect((await snapshot(stack)).eligibility["MTR-26003"].currentReleaseEligible).toBe(true);
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
