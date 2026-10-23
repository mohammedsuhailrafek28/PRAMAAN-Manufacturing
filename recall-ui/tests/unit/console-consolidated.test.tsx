// Consolidation tests (additive): the unified console and all three standalone pages are driven through their
// REAL live adapters with the SAME real H1/H2 envelopes (tests/fixtures/h1h2, captured from f9dcf56).
// Origin: Claude's console-gate tests (548e434) re-expressed against Codex's console wording, plus cross-page
// agreement. fetch is the only stub.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../src/App";
import { BackendRecallDataSource } from "../../src/data/RecallDataSource";
import { ImpactApp } from "../../src/impact/ImpactApp";
import { LiveImpactSource } from "../../src/impact/impactSource";
import { InvestigationApp } from "../../src/investigation/InvestigationApp";
import { LiveInvestigationSource } from "../../src/investigation/investigationSource";
import { PassportApp } from "../../src/passport/PassportApp";
import { LivePassportSource } from "../../src/passport/passportSource";

type Env = { status: number; body: any };
const load = (n: string): Env => JSON.parse(readFileSync(join(__dirname, "../fixtures/h1h2", `${n}.json`), "utf8"));
const fresh = (e: Env): Env => { const c = structuredClone(e); if (c.body?.freshness && c.body.freshness.maxAgeSeconds > 0) c.body.freshness.verifiedAt = new Date().toISOString().replace(/\.\d+Z$/, "Z"); return c; };
const stub = (...responses: Env[]) => {
  let i = 0;
  vi.stubGlobal("fetch", vi.fn(async () => {
    const r = responses[Math.min(i++, responses.length - 1)];
    return { ok: r.status >= 200 && r.status < 300, status: r.status, json: async () => structuredClone(r.body) } as unknown as Response;
  }));
};
const mountConsole = () => render(<App source={new BackendRecallDataSource()} />);
const text = () => document.body.textContent ?? "";

beforeEach(() => { window.location.hash = ""; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("unified console: states", () => {
  it("CURRENT: findings, holds and per-motor clearance; only the eligible motor shows a release", async () => {
    stub(fresh(load("current")));
    mountConsole();
    expect(await screen.findByRole("heading", { name: "Motor decisions" })).toBeInTheDocument();
    expect(screen.getAllByTestId("clearance-chip")).toHaveLength(1);
    expect(screen.queryByTestId("console-historical")).toBeNull();
  });

  it("PREFIX_ONLY: facts only, no decision/hold/release chips, prominent no-shipment-or-release warning", async () => {
    stub(fresh(load("prefix_only")));
    mountConsole();
    const panel = await screen.findByTestId("console-historical");
    expect(panel).toHaveTextContent("Checkpoint required");
    expect(screen.getByTestId("no-shipment-warning")).toHaveTextContent(/Do not ship or release any motor/);
    expect(panel).toHaveTextContent(/does not establish trust/);
    expect(screen.queryAllByTestId("chip-action")).toHaveLength(0);
    expect(screen.queryAllByTestId("chip-finding")).toHaveLength(0);
    expect(screen.queryAllByTestId("clearance-chip")).toHaveLength(0);
    // negative: the unsafe old behavior (a bare release label or hold list during PREFIX_ONLY) is rejected
    expect(text()).not.toMatch(/Release eligible|RELEASE_ELIGIBLE|Recall hold|Excluded with evidence/);
    expect(screen.queryByRole("heading", { name: "Motor decisions" })).toBeNull();
    expect(screen.queryByText(/Manufacturing capture workspace/)).toBeNull();      // no commands while a checkpoint is required
  });

  it("UNANCHORED: historical records only, nothing current", async () => {
    stub(fresh(load("unanchored")));
    mountConsole();
    const panel = await screen.findByTestId("console-historical");
    expect(panel).toHaveTextContent("Unanchored historical records");
    expect(screen.getByTestId("no-shipment-warning")).toBeInTheDocument();
    expect(screen.queryAllByTestId("clearance-chip")).toHaveLength(0);
  });

  it.each(["anchor_invalid", "verifying", "invalid_request"])("%s: fully WITHHELD, no motor-specific information", async (name) => {
    stub(load(name));
    mountConsole();
    expect(await screen.findByTestId("load-error")).toHaveTextContent(/withheld/);
    expect(text()).not.toMatch(/MTR-\d|BR-\d|Recall hold|Release eligible/);
    expect(screen.queryByTestId("console-historical")).toBeNull();
  });

  it("a legacy envelope without checkpoint/eligibility is withheld", async () => {
    const e = fresh(load("current")); delete e.body.checkpoint; delete e.body.eligibility;
    stub(e);
    mountConsole();
    expect(await screen.findByTestId("load-error")).toHaveTextContent(/checkpoint or eligibility metadata is missing/);
    expect(text()).not.toMatch(/MTR-26003|Release eligible/);
  });

  it("a successful non-200 status is not accepted as a snapshot (F6 holds for the console)", async () => {
    const e = fresh(load("current")); e.status = 201;
    stub(e);
    mountConsole();
    expect(await screen.findByTestId("load-error")).toBeInTheDocument();
    expect(screen.queryAllByTestId("clearance-chip")).toHaveLength(0);
  });

  it("CURRENT: withheld eligibility on one motor keeps its findings and does not disturb another motor (per motor, not global)", async () => {
    const e = fresh(load("current"));
    e.body.eligibility["MTR-26003"].currentReleaseEligible = false;
    stub(e);
    mountConsole();
    expect(await screen.findByRole("heading", { name: "Motor decisions" })).toBeInTheDocument();
    expect(screen.getAllByTestId("clearance-withheld").length).toBeGreaterThan(0);
    expect(screen.queryAllByTestId("clearance-chip")).toHaveLength(0);                    // negative: no bare release label
    expect(screen.getAllByTestId("chip-finding").length).toBeGreaterThan(1);               // findings stay visible
  });

  it("CURRENT: an eligibility projection that contradicts a hold is withheld entirely", async () => {
    const e = fresh(load("current"));
    e.body.eligibility["MTR-26001"].currentReleaseEligible = true;
    stub(e);
    mountConsole();
    expect(await screen.findByTestId("load-error")).toBeInTheDocument();
    expect(screen.queryAllByTestId("clearance-chip")).toHaveLength(0);
  });

  it("new evidence invalidates current clearance: a later PREFIX_ONLY poll replaces a shown CURRENT console", async () => {
    stub(fresh(load("current")), fresh(load("prefix_only")), fresh(load("prefix_only")));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mountConsole();
    expect(await screen.findByRole("heading", { name: "Motor decisions" })).toBeInTheDocument();
    expect(screen.getAllByTestId("clearance-chip")).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(2100);
    await waitFor(() => expect(screen.getByTestId("console-historical")).toBeInTheDocument());
    expect(screen.queryAllByTestId("clearance-chip")).toHaveLength(0);
  });
});

// One envelope, four surfaces: every surface must make the same trust decision.
const SURFACES = {
  console: { mount: () => mountConsole(), shown: () => document.querySelector('[data-testid="load-error"]') === null && document.querySelector("main") !== null },
  passport: { mount: () => { window.location.hash = "#/passport/MTR-26003/recall"; return render(<PassportApp source={new LivePassportSource()} pageUrl="http://127.0.0.1/passport.html" pollMs={100000} />); } },
  investigation: { mount: () => { window.location.hash = "#/"; return render(<InvestigationApp source={new LiveInvestigationSource()} pollMs={100000} />); } },
  impact: { mount: () => { window.location.hash = "#/"; return render(<ImpactApp source={new LiveImpactSource()} pollMs={100000} />); } },
} as const;
const RELEASE = /Release eligible|RELEASE_ELIGIBLE|No recall hold recorded|Excluded with evidence/i;

describe("all four surfaces apply the same gate", () => {
  const withheldEnvelopes: Array<[string, () => Env]> = [
    ["anchor_invalid", () => load("anchor_invalid")],
    ["verifying", () => load("verifying")],
    ["invalid_request", () => load("invalid_request")],
    ["legacy (no checkpoint)", () => { const e = fresh(load("current")); delete e.body.checkpoint; delete e.body.eligibility; return e; }],
    ["unknown checkpoint state", () => { const e = fresh(load("current")); e.body.checkpoint.state = "ANCHORED_CURRENT "; return e; }],
    ["contradictory eligibility", () => { const e = fresh(load("current")); e.body.eligibility["MTR-26001"].currentReleaseEligible = true; return e; }],
    ["status 201", () => { const e = fresh(load("current")); e.status = 201; return e; }],
    ["expired lease", () => { const e = structuredClone(load("current")); e.body.freshness.verifiedAt = new Date(Date.now() - 120000).toISOString().replace(/\.\d+Z$/, "Z"); return e; }],
  ];
  for (const [surface, def] of Object.entries(SURFACES)) {
    it.each(withheldEnvelopes)(`${surface}: %s shows no release or motor clearance`, async (_name, make) => {
      stub(make());
      def.mount();
      await waitFor(() => expect(document.body.textContent).toMatch(/withheld|unavailable|could not be loaded/i), { timeout: 3000 });
      expect(text()).not.toMatch(RELEASE);
    });
    it(`${surface}: PREFIX_ONLY shows no release or clearance`, async () => {
      stub(fresh(load("prefix_only")));
      def.mount();
      await waitFor(() => expect(document.body.textContent).toMatch(/Checkpoint required|not currently verified|unavailable|historical/i), { timeout: 3000 });
      expect(text()).not.toMatch(RELEASE);
    });
  }
});
