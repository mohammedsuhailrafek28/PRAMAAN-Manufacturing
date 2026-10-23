// The live console (App + BackendRecallDataSource) driven through the SAME shared gate as the standalone pages,
// with REAL H1/H2 envelopes captured from f9dcf56 (tests/fixtures/h1h2). fetch is the only stub.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../src/App";
import { BackendRecallDataSource } from "../../src/data/RecallDataSource";

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
const mount = () => render(<App source={new BackendRecallDataSource()} />);
const text = () => document.body.textContent ?? "";

beforeEach(() => { window.location.hash = ""; });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("console on the shared gate", () => {
  it("CURRENT: findings, holds and per-motor clearance are shown", async () => {
    stub(fresh(load("current")));
    mount();
    expect(await screen.findByRole("heading", { name: "Motor decisions" })).toBeInTheDocument();
    const actions = screen.getAllByTestId("chip-action").map((n) => n.textContent ?? "");
    expect(actions.filter((a) => /Release eligible/.test(a))).toHaveLength(1);     // only MTR-26003
    expect(actions.filter((a) => /Recall hold/.test(a)).length).toBeGreaterThan(0);
    expect(screen.queryByTestId("checkpoint-required")).toBeNull();
  });

  it("PREFIX_ONLY: segregated historical facts only, no decision, hold, action or clearance (display policy)", async () => {
    stub(fresh(load("prefix_only")));
    mount();
    const panel = await screen.findByTestId("checkpoint-required");
    expect(panel).toHaveTextContent("Checkpoint required");
    expect(panel).toHaveTextContent(/Do not ship or release any motor/);
    expect(panel).toHaveTextContent(/does not establish trust/);
    expect(screen.queryAllByTestId("chip-action")).toHaveLength(0);
    expect(screen.queryAllByTestId("chip-finding")).toHaveLength(0);
    // negative: the unsafe old behavior (a bare release label / hold list during PREFIX_ONLY) is rejected
    expect(text()).not.toMatch(/Release eligible|RELEASE_ELIGIBLE|Recall hold remains|Recall hold|Excluded with evidence/);
    expect(screen.queryByRole("heading", { name: "Motor decisions" })).toBeNull();
    expect(screen.queryByText(/Manufacturing capture workspace/)).toBeNull();      // no commands while a checkpoint is required
  });

  it("UNANCHORED: trusted anchor required, nothing current", async () => {
    stub(fresh(load("unanchored")));
    mount();
    const panel = await screen.findByTestId("checkpoint-required");
    expect(panel).toHaveTextContent("Trusted anchor required");
    expect(screen.queryAllByTestId("chip-action")).toHaveLength(0);
  });

  it.each(["anchor_invalid", "verifying", "invalid_request"])("%s is fully WITHHELD with no motor-specific information", async (name) => {
    stub(load(name));
    mount();
    const alert = await screen.findByTestId("load-error");
    expect(alert).toHaveTextContent(/Ledger unavailable/);
    expect(text()).not.toMatch(/MTR-\d|BR-\d|Recall hold|Release eligible/);
    expect(screen.queryByTestId("checkpoint-required")).toBeNull();
  });

  it("a legacy envelope without checkpoint/eligibility is withheld, not shown as current", async () => {
    const e = fresh(load("current")); delete e.body.checkpoint; delete e.body.eligibility;
    stub(e);
    mount();
    expect(await screen.findByTestId("load-error")).toHaveTextContent(/checkpoint or eligibility metadata is missing/);
    expect(text()).not.toMatch(/MTR-26003|Release eligible/);
  });

  it("CURRENT: a recorded release without current eligibility keeps its findings but is not shown as cleared (per motor, not global)", async () => {
    const e = fresh(load("current"));
    e.body.eligibility["MTR-26003"].currentReleaseEligible = false;   // e.g. an outstanding notification obligation
    stub(e);
    mount();
    expect(await screen.findByRole("heading", { name: "Motor decisions" })).toBeInTheDocument();   // not globally hidden
    const actions = screen.getAllByTestId("chip-action").map((n) => n.textContent ?? "");
    expect(actions.some((a) => /Release clearance withheld/.test(a))).toBe(true);
    expect(actions.some((a) => /^Operational action.*Release eligible/.test(a))).toBe(false);       // negative: no bare release label
    expect(screen.getByRole("status", { name: "Release clearance withheld" })).toHaveTextContent(/MTR-26003/);
    expect(screen.getAllByTestId("chip-finding").length).toBeGreaterThan(1);                          // findings stay visible
  });

  it("CURRENT: an eligibility projection that contradicts a hold is withheld entirely", async () => {
    const e = fresh(load("current"));
    e.body.eligibility["MTR-26001"].currentReleaseEligible = true;     // MTR-26001 is held
    stub(e);
    mount();
    expect(await screen.findByTestId("load-error")).toBeInTheDocument();
    expect(text()).not.toMatch(/Release eligible/);
  });

  it("a later PREFIX_ONLY poll replaces a previously shown CURRENT console", async () => {
    stub(fresh(load("current")), fresh(load("prefix_only")), fresh(load("prefix_only")));
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      mount();
      expect(await screen.findByRole("heading", { name: "Motor decisions" })).toBeInTheDocument();
      await vi.advanceTimersByTimeAsync(2100);
      await waitFor(() => expect(screen.getByTestId("checkpoint-required")).toBeInTheDocument());
      expect(screen.queryAllByTestId("chip-action")).toHaveLength(0);
    } finally { vi.useRealTimers(); }
  });
});
