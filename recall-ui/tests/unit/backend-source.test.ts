import { afterEach, expect, it, vi } from "vitest";
import { BackendRecallDataSource } from "../../src/data/RecallDataSource";
import { realSnapshot } from "./helpers";

afterEach(() => vi.unstubAllGlobals());
it("rejects an unavailable backend without requesting fixtures", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: false, status: 409 });
  vi.stubGlobal("fetch", fetch);
  await expect(new BackendRecallDataSource().load()).rejects.toThrow("Ledger unavailable");
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(fetch.mock.calls[0][0]).toBe("/api/snapshot");
});
it("refuses contradictory backend decisions", async () => {
  const snap = realSnapshot();
  snap.decisions["case-06"]["RC-009/P1"].current.operationalAction = "RELEASE_ELIGIBLE";
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => snap }));
  await expect(new BackendRecallDataSource().load()).rejects.toThrow("Invalid recall snapshot");
});
it("passes the local token and validates the returned mutation snapshot", async () => {
  const fetch = vi.fn().mockResolvedValueOnce({ json: async () => ({ token: "test-local-token" }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ snapshot: realSnapshot(), captureToDecisionMs: 123 }) });
  vi.stubGlobal("fetch", fetch);
  const result = await new BackendRecallDataSource().command("units", { serial: "MTR-TEST" });
  expect(result.captureToDecisionMs).toBe(123);
  expect(fetch.mock.calls[1][1].headers["X-Pramaan-Token"]).toBe("test-local-token");
});
it("bounds a hung backend request and aborts its transport", async () => {
  let signal: AbortSignal | undefined;
  vi.stubGlobal('fetch',vi.fn((_url,init)=>{signal=init.signal;return new Promise(()=>{});}));
  await expect(new BackendRecallDataSource(20).load()).rejects.toThrow('timed out');
  expect(signal?.aborted).toBe(true);
});
it("also bounds a response whose JSON body never completes", async () => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,status:200,json:()=>new Promise(()=>{})}));
  await expect(new BackendRecallDataSource(20).load()).rejects.toThrow('timed out');
});
