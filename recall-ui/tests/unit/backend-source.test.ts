import { afterEach, expect, it, vi } from "vitest";
import { BackendRecallDataSource } from "../../src/data/RecallDataSource";
import { realSnapshot, withStrictCurrent } from "./helpers";

// MIGRATED FIXTURES (M1): the three envelopes below add honest strict-current checkpoint/eligibility metadata so the
// original assertions still exercise freshness, stale replay and supersession through the unified gate.
const strictFresh = (verifiedAt: string) => withStrictCurrent({ ...realSnapshot(), freshness: { status: "VERIFIED_ANCHORED_SYNTHETIC", verifiedAt, maxAgeSeconds: 5, archiveId: "test", sequence: 1, headHash: "hash" } }, 1);

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
    .mockResolvedValueOnce({ ok: true, json: async () => ({ snapshot: strictFresh(new Date().toISOString()), captureToDecisionMs: 123 }) });
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

it('rejects a successful stale replay instead of treating arrival as verification',async()=>{
 const snap=strictFresh(new Date(Date.now()-60000).toISOString());
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>snap}));
 await expect(new BackendRecallDataSource().load()).rejects.toThrow(/expired/);
});

it('late older concurrent request cannot overwrite the latest accepted response',async()=>{
 const snap=strictFresh(new Date().toISOString());
 let release!:(v:unknown)=>void;
 vi.stubGlobal('fetch',vi.fn().mockImplementationOnce(()=>new Promise(r=>{release=r;})).mockResolvedValueOnce({ok:true,json:async()=>snap}));
 const source=new BackendRecallDataSource();const old=source.load();
 await expect(source.load()).resolves.toBeTruthy();
 release({ok:true,json:async()=>snap});
 await expect(old).rejects.toThrow(/Superseded/);
});
