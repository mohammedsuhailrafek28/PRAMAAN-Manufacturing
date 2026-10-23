import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { OwnedServer } from '../support/ownedServer';

const shots = "../docs/impact-screenshots";
const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const axe = async (page: Page) => (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze()).violations.map((v) => `${v.id}: ${v.nodes[0]?.target}`);
const python = resolve(process.platform === "win32" ? "../.venv/Scripts/python.exe" : "../.venv/bin/python");
const PREVIEW = "/impact.html?mode=preview";
const nodeById = (page: Page, id: string) => page.locator(`[data-testid="impact-node"][data-node-id="${id}"]`);

// ---- explicit preview of the authored synthetic datasets -------------------------------------

test("DE-scope dataset: headline, graph, trace, details and list", async ({ page }) => {
  mkdirSync(shots, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`${PREVIEW}&dataset=de#/`);
  await expect(page.getByTestId("impact-banner").or(page.getByTestId("impact-home").getByRole("note"))).toContainText(/not a live ledger/);
  await expect(page.getByTestId("dataset-note")).toContainText("MTR-26031 authored link edit");
  await page.screenshot({ path: `${shots}/01-lot-chooser.png`, fullPage: true });

  await page.goto(`${PREVIEW}&dataset=de#/lot/bearing/BR-204/graph`);
  await expect(page.getByTestId("impact-headline")).toContainText("Lot BR-204 is named by recall");
  await expect(page.getByTestId("impact-headline")).toContainText("10 motors have a ledger-recorded link to it (7 affected, 2 unresolved, 1 excluded with evidence)");
  await expect(page.getByTestId("impact-svg")).toBeVisible();
  await expect(page.getByTestId("impact-edge").first()).toBeAttached();
  await page.screenshot({ path: `${shots}/02-graph-overview.png`, fullPage: true });

  await nodeById(page, "motor:MTR-26001").click();
  await expect(page.getByTestId("impact-decision")).toContainText("Affected");
  await expect(page.getByTestId("impact-details")).toContainText("Ledger records behind this item");
  await page.getByRole("button", { name: "Trace back to source" }).click();
  await expect(page.getByText(/backward trace of MTR-26001 along recorded links only/)).toBeVisible();
  await page.screenshot({ path: `${shots}/03-trace-and-details.png`, fullPage: true });

  // historical removal, with the not-elimination note
  await page.goto(`${PREVIEW}&dataset=de#/lot/bearing/BR-204/list`);
  const hist = page.getByTestId("impact-list").locator("tr").filter({ hasText: "Installed component" }).filter({ hasText: "removed (historical)" }).first();
  await expect(hist).toBeVisible();
  await hist.getByRole("button").click();
  await expect(page.getByTestId("impact-details")).toContainText("not proof that the affected lot was eliminated");
  await page.screenshot({ path: `${shots}/04-historical-removal.png`, fullPage: true });

  // link-integrity issues come from authored edits and are listed with their records
  await page.goto(`${PREVIEW}&dataset=de#/lot/bearing/BR-204/list`);
  const kinds = await page.getByTestId("impact-issue").evaluateAll((els) => els.map((e) => e.getAttribute("data-issue-kind")));
  for (const k of ["MISSING_MANUFACTURE_LINK", "MISSING_MATERIAL_LINK", "LOT_MISMATCH", "DUPLICATE_REFERENCE"]) expect(kinds).toContain(k);
  await page.getByTestId("impact-issuebox").locator("summary").first().click();
  await page.screenshot({ path: `${shots}/05-list-with-issues.png`, fullPage: true });

  // a raw-material lot traces forward to bearing lots and motors
  await page.goto(`${PREVIEW}&dataset=de#/`);
  const raw = page.getByTestId("impact-home").getByRole("link", { name: /Raw-material lot/ }).first();
  await raw.click();
  await expect(page.getByTestId("impact-headline")).toContainText("Raw-material lot");
  await page.screenshot({ path: `${shots}/06-raw-lot.png`, fullPage: true });
});

test("NDE-scope dataset: a lot that is DE-only is out of scope and is not called safe", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${PREVIEW}&dataset=nde#/lot/bearing/BR-204/graph`);
  await expect(page.getByTestId("impact-headline")).toContainText(/slot NDE|slots? NDE/);
  await page.screenshot({ path: `${shots}/07-nde-scope.png`, fullPage: true });
  expect(await page.getByTestId("impact-workspace").innerText()).not.toMatch(/\bis safe\b|\bsafe to (use|ship)\b/i);
});

test("unknown lot and invalid addresses are refused without drawing anything", async ({ page }) => {
  await page.goto(`${PREVIEW}&dataset=de#/lot/bearing/NOPE-1/graph`);
  await expect(page.getByTestId("unknown-lot")).toContainText("not evidence that no motor holds it");
  await expect(page.getByTestId("impact-svg")).toHaveCount(0);
  await page.goto(`${PREVIEW}&dataset=de#/lot/bearing/BR-204/sideways`);
  await expect(page.getByTestId("invalid-route")).toBeVisible();
});

test("keyboard: tab to a node, Enter selects it, list view offers the same information", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${PREVIEW}&dataset=de#/lot/bearing/BR-204/graph`);
  const canvas = page.getByRole("group", { name: /Impact graph\. Arrow keys pan/ });
  await canvas.focus();
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("+");
  await expect(page.getByText(/Zoom 120%/)).toBeVisible();
  await nodeById(page, "motor:MTR-26002").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("impact-details")).toContainText("MTR-26002");
  await expect(page).toHaveURL(/motor%3AMTR-26002/);
  await page.getByRole("link", { name: "List" }).click();
  await expect(page.getByTestId("impact-list")).toBeVisible();
  await expect(page.getByTestId("impact-list").locator("tr[aria-current='true']")).toContainText("MTR-26002");
});

test("the page has no control that can change anything and issues only GET requests", async ({ page }) => {
  const methods: string[] = [];
  page.on("request", (r) => { if (new URL(r.url()).pathname !== "/favicon.ico") methods.push(r.method()); });
  await page.goto("/impact.html#/lot/bearing/BR-204/graph");
  await expect(page.getByTestId("impact-headline")).toBeVisible();
  await nodeById(page, "motor:MTR-26001").click();
  await page.getByRole("link", { name: "List" }).click();
  expect(new Set(methods)).toEqual(new Set(["GET"]));
  const labels = await page.locator("a, button, input, select, textarea").evaluateAll((els) => els.map((e) => (e.textContent ?? "") + (e.getAttribute("aria-label") ?? "")));
  for (const l of labels) expect(l).not.toMatch(/\b(assign|approve|resolve|release|delete|save|submit|notify|send)\b/i);
});

for (const [name, size] of [["desktop", { width: 1280, height: 900 }], ["mobile", { width: 375, height: 740 }]] as const) {
  test(`${name}: chooser, graph, list and details have no page overflow and pass axe`, async ({ page }) => {
    await page.setViewportSize(size);
    for (const hash of ["#/", "#/lot/bearing/BR-204/graph", "#/lot/bearing/BR-204/list", "#/lot/bearing/BR-204/list/motor%3AMTR-26001", "#/lot/bearing/BR-204/graph/motor%3AMTR-26001"]) {
      await page.goto(`${PREVIEW}&dataset=de${hash}`);
      await expect(page.locator("main h2").first()).toBeVisible();
      expect(await overflow(page), `${name} ${hash} overflow`).toBeLessThanOrEqual(0);
      expect(await axe(page), `${name} ${hash} axe`).toEqual([]);
    }
    await page.goto(`${PREVIEW}&dataset=de#/lot/bearing/BR-204`);
    if (name === "mobile") {
      // phones open on the list, which is the accessible equivalent
      await expect(page.getByTestId("impact-list")).toBeVisible();
      await page.screenshot({ path: `${shots}/08-mobile-list.png`, fullPage: true });
      await page.goto(`${PREVIEW}&dataset=de#/lot/bearing/BR-204/graph`);
      await expect(page.getByTestId("impact-svg")).toBeVisible();
      await page.screenshot({ path: `${shots}/09-mobile-graph.png`, fullPage: true });
    }
  });
}

test("large stress data: draws a bounded window, the list keeps every record, and rendering stays quick", async ({ page }) => {
  test.setTimeout(90_000); // 23 s alone, over the 30 s default when the combined suite loads the machine
  await page.setViewportSize({ width: 1440, height: 1000 });
  const t0 = Date.now();
  await page.goto(`${PREVIEW}&dataset=large#/lot/bearing/BR-204/graph`);
  await expect(page.getByTestId("impact-window")).toContainText("too many to draw at once");
  const ms = Date.now() - t0;
  const drawn = await page.getByTestId("impact-node").count();
  expect(drawn).toBeGreaterThan(0);
  expect(drawn).toBeLessThan(400);
  console.log(`large graph: first render ${ms} ms, ${drawn} nodes drawn`);
  expect(ms).toBeLessThan(15_000);
  await page.screenshot({ path: `${shots}/10-large-window.png` });
  await page.getByRole("button", { name: "Next motors" }).click();
  await expect(page.getByTestId("impact-window")).toContainText(/page 2 of/);
  await page.getByRole("link", { name: "List" }).click();
  await expect(page.getByRole("button", { name: /more of \d+ remaining/ })).toBeVisible();
});

// ---- live backend ---------------------------------------------------------------------------

test("live anchored ledger: verified status is shown, then withheld on outage and on a stale lease", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/impact.html#/lot/bearing/BR-204/graph");
  await expect(page.getByTestId("impact-headline")).toContainText("named by recall");
  await expect(page.getByTestId("noncurrent-label")).toHaveCount(0);
  await expect(page.getByText("VERIFIED_ANCHORED_SYNTHETIC")).toBeVisible();
  await page.screenshot({ path: `${shots}/11-live-verified.png`, fullPage: true });
  expect(page.url()).not.toContain("preview");

  // a stale verification timestamp: genealogy stays, labelled not current; status is withheld
  const good = await (await page.request.get("/api/snapshot")).json();
  const stale = structuredClone(good);
  stale.freshness.verifiedAt = new Date(Date.now() - 60_000).toISOString();
  await page.route("**/api/snapshot", (r) => r.fulfill({ json: stale }));
  await expect(page.getByTestId("noncurrent-label")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("impact-headline")).toContainText("Current recall status is withheld");
  await expect(page.getByTestId("impact-decision")).toHaveCount(0);
  await expect(page.locator(".chip-cap", { hasText: "Engine finding" })).toHaveCount(0);
  await page.screenshot({ path: `${shots}/12-live-not-current.png`, fullPage: true });

  // outage: nothing from the earlier snapshot remains on the page
  await page.unroute("**/api/snapshot");
  await page.route("**/api/snapshot", (r) => r.abort());
  await expect(page.getByTestId("withdrawn")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("impact-svg")).toHaveCount(0);
  await expect(page.getByTestId("impact-headline")).toHaveCount(0);
  await page.screenshot({ path: `${shots}/13-live-withdrawn.png`, fullPage: true });

  // recovery returns verified status
  await page.unroute("**/api/snapshot");
  await expect(page.getByTestId("impact-headline")).toContainText("named by recall", { timeout: 10_000 });
});

test("a snapshot whose journal sequence goes backwards is refused", async ({ page }) => {
  await page.goto("/impact.html#/lot/bearing/BR-204/list");
  await expect(page.getByTestId("impact-headline")).toBeVisible();
  const good = await (await page.request.get("/api/snapshot")).json();
  const rollback = structuredClone(good);
  rollback.freshness.sequence = 1;
  await page.route("**/api/snapshot", (r) => { rollback.freshness.verifiedAt = new Date().toISOString(); return r.fulfill({ json: rollback }); });
  await expect(page.getByTestId("withdrawn")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("impact-headline")).toHaveCount(0);
});

test("a hidden tab withholds status until a fresh verification arrives", async ({ page }) => {
  await page.goto("/impact.html#/lot/bearing/BR-204/list");
  await expect(page.getByTestId("impact-headline")).toContainText("named by recall");
  await page.route("**/api/snapshot", async (r) => { await new Promise((ok) => setTimeout(ok, 6000)); await r.abort().catch(() => undefined); });
  await page.evaluate(() => { Object.defineProperty(document, "hidden", { configurable: true, value: true }); document.dispatchEvent(new Event("visibilitychange")); });
  await expect(page.getByTestId("noncurrent-label")).toBeVisible();
  await expect(page.getByTestId("impact-decision")).toHaveCount(0);
});

let owned: OwnedServer | undefined;
test.afterEach(async () => { await owned?.dispose(); owned = undefined; });

test("an unanchored ledger shows its genealogy labelled not current and no recall status", async ({ page }) => {
  owned=new OwnedServer(4196,true);await owned.start();
  await expect(async () => { expect((await page.request.get("http://127.0.0.1:4196/api/session")).ok()).toBeTruthy(); }).toPass({ timeout: 20_000 });
  await page.goto("http://127.0.0.1:4196/impact.html#/lot/bearing/BR-204/list");
  await expect(page.getByTestId("noncurrent-label")).toBeVisible();
  await expect(page.getByTestId("impact-headline")).toContainText("Current recall status is withheld");
  await expect(page.getByTestId("impact-decision")).toHaveCount(0);
  await expect(page.getByText(/trusted external anchor/i).first()).toBeVisible();
  await page.screenshot({ path: `${shots}/14-unanchored.png`, fullPage: true });
});

test("browsing the graph leaves the journal, decisions, notifications and anchor untouched", async ({ page }) => {
  owned=new OwnedServer(4197);const database=owned.database;await owned.start();
  await expect(async () => { expect((await page.request.get("http://127.0.0.1:4197/api/session")).ok()).toBeTruthy(); }).toPass({ timeout: 20_000 });
  const anchor = database.replace(/\.sqlite$/, ".test-owner-anchor.json");
  const dump = () => {
    const r = spawnSync(python, ["-I", "-c", "import sqlite3,sys,json,hashlib;c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True);out={}\nfor (t,) in c.execute(\"select name from sqlite_master where type='table' and name not like 'sqlite_%' order by 1\").fetchall():\n    out[t]=[c.execute('select count(*) from \"'+t+'\"').fetchone()[0], hashlib.sha256(repr(c.execute('select * from \"'+t+'\" order by 1').fetchall()).encode()).hexdigest()]\nprint(json.dumps(out))", database], { encoding: "utf8", windowsHide: true, env: { ...process.env, PYTHONHASHSEED: "0" } });
    expect(r.status, r.stderr).toBe(0);
    return r.stdout.trim();
  };
  const before = { db: dump(), anchor: readFileSync(anchor, "utf8") };
  const methods: string[] = [];
  page.on("request", (r) => methods.push(r.method()));
  await page.goto("http://127.0.0.1:4197/impact.html#/lot/bearing/BR-204/graph");
  await expect(page.getByTestId("impact-headline")).toContainText("named by recall");
  await nodeById(page, "motor:MTR-26001").click();
  await page.getByRole("button", { name: "Trace both ways" }).click();
  await page.getByRole("link", { name: "List" }).click();
  await page.waitForTimeout(2500); // at least one more poll
  expect(new Set(methods)).toEqual(new Set(["GET"]));
  expect(dump()).toBe(before.db);
  expect(readFileSync(anchor, "utf8")).toBe(before.anchor);
});
