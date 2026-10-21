import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const SHOTS = process.env.SHOTS === "1";
const shot = async (page: import("@playwright/test").Page, name: string) => {
  if (SHOTS) await page.screenshot({ path: `docs/screenshots/${name}.png`, fullPage: true });
};

test("demo workflow: fleet -> unit -> explanation -> history", async ({ page }) => {
  await page.goto("/?mode=fixtures");
  await expect(page.getByRole("heading", { name: "Motor decisions" })).toBeVisible();
  await expect(page.getByText(/Synthetic fixtures/)).toBeVisible();
  await shot(page, "01-fleet");

  await page.getByRole("link", { name: "case-06", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Slot attribution and ambiguity/ })).toBeVisible();
  await expect(page.getByTestId("chip-finding").first()).toContainText("Unresolved");
  await expect(page.getByTestId("chip-action").first()).toContainText("Recall hold");
  await expect(page.getByTestId("chip-review").first()).toContainText("Review required");
  await shot(page, "02-decision-explanation");

  await page.getByRole("tab", { name: "Genealogy" }).click();
  await expect(page.getByRole("img", { name: /Genealogy of case-06/ })).toBeVisible();
  await shot(page, "03-genealogy");

  await page.goto("/?mode=fixtures#/unit/case-05/history");
  await expect(page.getByText(/Notification obligation/)).toBeVisible();
  await expect(page.getByText(/Superseded by v2/)).toBeVisible();
  await shot(page, "04-decision-history");
});

test("case 06 before / after shows the safety improvement", async ({ page }) => {
  await page.goto("/?mode=fixtures#/case06/case-06");
  const before = page.getByRole("region", { name: "Before: original engine" });
  const after = page.getByRole("region", { name: "After: current engine" });
  await expect(before.getByTestId("chip-finding")).toContainText("Excluded with evidence");
  await expect(before.getByTestId("safety")).toContainText("False release");
  await expect(after.getByTestId("chip-finding")).toContainText("Unresolved");
  await expect(page.getByTestId("false-release-summary")).toContainText("current engine");
  await shot(page, "05-case06-comparison");
});

test("lot investigation", async ({ page }) => {
  await page.goto("/?mode=fixtures#/lot/BR-204");
  await expect(page.getByText("This lot is named by the recall.")).toBeVisible();
  await shot(page, "06-lot-investigation");
});

test("mobile layout has no horizontal page scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  for (const hash of ["/", "/#/unit/case-06", "/#/case06/case-06", "/#/lot/BR-204"]) {
    await page.goto(hash === "/" ? "/?mode=fixtures" : hash.replace("/#", "/?mode=fixtures#"));
    await expect(page.locator("main h2").first()).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, hash).toBeLessThanOrEqual(0);
  }
  await page.goto("/?mode=fixtures");
  await shot(page, "07-mobile-fleet");
});

test("invalid fixture is refused in the browser", async ({ page }) => {
  await page.route("**/data/snapshot.json", async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    body.decisions["case-06"]["RC-009/P1"].current.operationalAction = "RELEASE_ELIGIBLE";
    await route.fulfill({ response: res, json: body });
  });
  await page.goto("/?mode=fixtures");
  await expect(page.getByTestId("load-error")).toContainText("failed validation");
  await expect(page.getByRole("heading", { name: "Motor decisions" })).toHaveCount(0);
  await shot(page, "08-invalid-fixture");
});

for (const [name, hash] of [
  ["fleet", "/"],
  ["decision", "/#/unit/case-06/decision"],
  ["genealogy", "/#/unit/case-06/genealogy"],
  ["history", "/#/unit/case-05/history"],
  ["events", "/#/unit/case-06/events"],
  ["lot", "/#/lot/BR-204"],
  ["case06", "/#/case06/case-06"],
] as const) {
  for (const scheme of ["light", "dark"] as const) {
    test(`axe: ${name} (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.goto(hash === "/" ? "/?mode=fixtures" : hash.replace("/#", "/?mode=fixtures#"));
      await expect(page.locator("main h2").first()).toBeVisible();
      const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      expect(r.violations.map((v) => `${v.id}: ${v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
    });
  }
}
