// Owner decision 2 (M8): a verified PREFIX_ONLY snapshot must not acquire or renew a CURRENT freshness/clearance lease, and no
// historical snapshot becomes current through polling, refresh, visibility changes or a stale (replayed) response.
// Real H1/H2 envelopes; fetch is the only stub.
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../src/App";
import { BackendRecallDataSource } from "../../src/data/RecallDataSource";
import { verifyFreshness } from "../../src/data/freshness";

type Env = { status: number; body: any };
const load = (n: string): Env => JSON.parse(readFileSync(join(__dirname, "../fixtures/h1h2", `${n}.json`), "utf8"));
const stamp = (e: Env, at = Date.now()): Env => { const c = structuredClone(e); c.body.freshness.verifiedAt = new Date(at).toISOString().replace(/\.\d+Z$/, "Z"); return c; };
let calls = 0;
const stub = (pick: (i: number) => Env) => {
  calls = 0;
  vi.stubGlobal("fetch", vi.fn(async () => {
    const r = pick(calls++);
    return { ok: r.status >= 200 && r.status < 300, status: r.status, json: async () => structuredClone(r.body) } as unknown as Response;
  }));
};
const mount = () => render(<App source={new BackendRecallDataSource()} />);
const noClearance = () => {
  expect(screen.queryAllByTestId("clearance-chip")).toHaveLength(0);
  expect(screen.queryAllByTestId("chip-action")).toHaveLength(0);
  expect(document.body.textContent).not.toMatch(/Release eligible|RELEASE_ELIGIBLE|Excluded with evidence/);
};

beforeEach(() => { window.location.hash = ""; vi.useFakeTimers({ shouldAdvanceTime: true }); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("M8: PREFIX_ONLY never earns or renews a current lease", () => {
  it("verifyFreshness refuses a verified prefix even when the previous snapshot was current (no lease renewal)", () => {
    const cur = stamp(load("current")).body, pre = stamp(load("prefix_only")).body;
    expect(() => verifyFreshness(pre, cur)).toThrow();
    expect(() => verifyFreshness(pre)).toThrow(/Historical evidence only/);
  });

  it("repeated fresh PREFIX responses over several lease periods never show clearance", async () => {
    stub(() => stamp(load("prefix_only")));
    mount();
    await screen.findByTestId("console-historical");
    for (let i = 0; i < 4; i++) { await act(async () => { await vi.advanceTimersByTimeAsync(2100); }); noClearance(); }
    expect(screen.getByTestId("no-shipment-warning")).toBeInTheDocument();
  });

  it("a stale CURRENT response replayed after the ledger advanced to PREFIX is not shown (cache/replay)", async () => {
    const old = load("current");
    stub((i) => (i === 0 ? stamp(old) : i === 1 ? stamp(load("prefix_only")) : stamp(old)));
    mount();
    await screen.findByRole("heading", { name: "Motor decisions" });
    await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
    await waitFor(() => expect(screen.getByTestId("console-historical")).toBeInTheDocument());
    await act(async () => { await vi.advanceTimersByTimeAsync(2100); });     // the replayed older CURRENT arrives
    noClearance();
    expect(screen.queryByRole("heading", { name: "Motor decisions" })).toBeNull();
  });

  it("visibility change and focus after PREFIX do not restore the earlier current view", async () => {
    stub((i) => (i === 0 ? stamp(load("current")) : stamp(load("prefix_only"))));
    mount();
    await screen.findByRole("heading", { name: "Motor decisions" });
    await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
    await screen.findByTestId("console-historical");
    await act(async () => {
      Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true }); document.dispatchEvent(new Event("visibilitychange"));
      Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true }); document.dispatchEvent(new Event("visibilitychange"));
      window.dispatchEvent(new Event("focus"));
    });
    noClearance();
  });

  it("navigating between routes while PREFIX shows no clearance on any route", async () => {
    stub(() => stamp(load("prefix_only")));
    mount();
    await screen.findByTestId("console-historical");
    for (const hash of ["#/unit/MTR-26003/decision", "#/", "#/unit/MTR-26001/history", "#/lot/BR-204"]) {
      await act(async () => { window.location.hash = hash; await vi.advanceTimersByTimeAsync(50); });
      noClearance();
    }
  });
});
