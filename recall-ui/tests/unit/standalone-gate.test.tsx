// Page-level adversarial tests: the three standalone pages, their REAL live adapters and the shared gate,
// driven by REAL H1/H2 envelopes (tests/fixtures/h1h2, captured from f9dcf56). fetch is the only stub.
import { cleanup, render, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ImpactApp } from "../../src/impact/ImpactApp";
import { LiveImpactSource } from "../../src/impact/impactSource";
import { InvestigationApp } from "../../src/investigation/InvestigationApp";
import { LiveInvestigationSource } from "../../src/investigation/investigationSource";
import { PassportApp } from "../../src/passport/PassportApp";
import { LivePassportSource } from "../../src/passport/passportSource";

type Env = { status: number; body: any };
const load = (n: string): Env => JSON.parse(readFileSync(join(__dirname, "../fixtures/h1h2", `${n}.json`), "utf8"));
const fresh = (e: Env): Env => { const c = structuredClone(e); if (c.body?.freshness && c.body.freshness.maxAgeSeconds > 0) c.body.freshness.verifiedAt = new Date().toISOString().replace(/\.\d+Z$/, "Z"); return c; };
const legacy = (): Env => { const c = fresh(load("current")); delete c.body.checkpoint; delete c.body.eligibility; return c; };
const unknownState = (): Env => { const c = fresh(load("current")); c.body.checkpoint.state = "ANCHORED_CURRENT "; return c; };

function stubFetch(responses: Array<Env | "NETWORK">) {
  let i = 0; const calls: Array<{ url: string; method?: string }> = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method });
    const r = responses[Math.min(i++, responses.length - 1)];
    if (r === "NETWORK") throw new TypeError("network down");
    return { ok: r.status >= 200 && r.status < 300, status: r.status, json: async () => structuredClone(r.body) } as unknown as Response;
  }));
  return calls;
}

const PAGES = {
  passport: { hash: "#/passport/MTR-26003/recall", mount: () => <PassportApp source={new LivePassportSource()} pageUrl="http://127.0.0.1/passport.html" pollMs={40} /> },
  investigation: { hash: "#/", mount: () => <InvestigationApp source={new LiveInvestigationSource()} pollMs={40} /> },
  impact: { hash: "#/", mount: () => <ImpactApp source={new LiveImpactSource()} pollMs={40} /> },
} as const;

const CLEARANCE = /RELEASE_ELIGIBLE|Release eligible|Excluded with evidence|No recall hold recorded|Eligible under this recall|shipment authorization/i;
const MOTOR_SPECIFIC = /MTR-\d|BR-\d|RECALL_HOLD|Recall hold|precaution|genealogy|SERIAL-|EXCLUDED_WITH_EVIDENCE|UNRESOLVED/i;

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const text = () => document.body.textContent ?? "";

describe.each(Object.entries(PAGES))("%s page under strict H1/H2 states", (_name, page) => {
  const setup = async (responses: Array<Env | "NETWORK">) => { window.location.hash = page.hash; const calls = stubFetch(responses); render(page.mount()); return calls; };

  it("FE-02 PREFIX_ONLY: no clearance wording anywhere and the checkpoint requirement is stated", async () => {
    await setup([fresh(load("prefix_only"))]);
    await waitFor(() => expect(text()).toMatch(/checkpoint is required|not currently verified|Current recall status unavailable|withheld|not current/i), { timeout: 4000 });
    expect(text()).not.toMatch(CLEARANCE);
  });
  it("FE-03 UNANCHORED: no clearance wording and no claim of external verification", async () => {
    await setup([fresh(load("unanchored"))]);
    await waitFor(() => expect(text()).toMatch(/not (currently )?verified|unavailable|withheld|not current|trusted/i), { timeout: 4000 });
    expect(text()).not.toMatch(CLEARANCE);
  });
  it.each([
    ["FE-04 ANCHOR_INVALID", () => load("anchor_invalid")],
    ["FE-05 VERIFYING", () => load("verifying")],
    ["FE-06 INVALID_REQUEST", () => load("invalid_request")],
    ["FE-07 legacy envelope", legacy],
    ["FE-09 unknown state", unknownState],
    ["FE-25 network failure", () => "NETWORK" as const],
  ])("%s: WITHHELD shows no motor-specific finding, hold, genealogy or label", async (_n, make) => {
    await setup([make()]);
    await waitFor(() => expect(text()).toMatch(/withheld|unavailable|could not be loaded|not current|not shown/i), { timeout: 4000 });
    expect(text()).not.toMatch(CLEARANCE);
    expect(text()).not.toMatch(MOTOR_SPECIFIC);
  });
  it("FE-19 CURRENT -> PREFIX_ONLY on the next poll removes the cleared view", async () => {
    await setup([fresh(load("current")), fresh(load("prefix_only"))]);
    await waitFor(() => expect(text()).toMatch(/checkpoint is required|not currently verified|Current recall status unavailable|withheld|not current/i), { timeout: 4000 });
    expect(text()).not.toMatch(CLEARANCE);
  });
  it("FE-21 CURRENT -> ANCHOR_INVALID leaves nothing from the earlier snapshot", async () => {
    await setup([fresh(load("current")), load("anchor_invalid")]);
    await waitFor(() => expect(text()).toMatch(/anchor check failed/i), { timeout: 4000 });
    expect(text()).not.toMatch(CLEARANCE);
    expect(text()).not.toMatch(MOTOR_SPECIFIC);
    expect(text()).toMatch(/historical, not currently verified|historical/i);
  });
  it("FE-22 regression (older snapshot after a newer one) withdraws everything", async () => {
    const newer = fresh(load("prefix_only")); const older = fresh(load("current"));
    await setup([newer, older]);
    await waitFor(() => expect(text()).toMatch(/moved backwards/i), { timeout: 4000 });
    expect(text()).not.toMatch(MOTOR_SPECIFIC);
  });
  it("only GET /api/snapshot is ever requested", async () => {
    const calls = await setup([fresh(load("prefix_only"))]);
    await waitFor(() => expect(calls.length).toBeGreaterThan(0));
    for (const c of calls) { expect(c.url).toBe("/api/snapshot"); expect(c.method).toBe("GET"); }
  });
});

describe("FE-01 the CURRENT state still renders for a cleared motor (the gate does not over-block)", () => {
  it("passport shows the verified recall card for the eligible motor only", async () => {
    window.location.hash = "#/passport/MTR-26003/recall"; stubFetch([fresh(load("current"))]); render(PAGES.passport.mount());
    await waitFor(() => expect(document.querySelector("[data-testid=recall-current]")).not.toBeNull(), { timeout: 4000 });
    cleanup();
    window.location.hash = "#/passport/MTR-26001/recall"; stubFetch([fresh(load("current"))]); render(PAGES.passport.mount());
    await waitFor(() => expect(document.querySelector("[data-testid=recall-current]")).not.toBeNull(), { timeout: 4000 });
    expect(text()).toMatch(/hold/i);
  });
});
