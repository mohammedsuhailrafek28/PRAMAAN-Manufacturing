import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { NextRequest } from "next/server";
import { GET } from "../src/app/api/[...path]/route";
import * as proxy from "../src/app/api/[...path]/route";
import { evaluateEnvelope } from "../src/orig/contract/gate";
import { projectPassport } from "../src/orig/contract/views";
import { buildPassport } from "../src/orig/passport/projection";
import { isCurrentClearance } from "../src/orig/contract/clearance";
import type { RecallSnapshot } from "../src/orig/domain/types";

const folder = process.env.PRAMAAN_COMPAT_FIXTURES;
assert.ok(folder, "Run compatibility/run.py to create isolated, actual-evaluator fixtures first");
const load = (name: string): RecallSnapshot => JSON.parse(readFileSync(resolve(folder!, name + ".json"), "utf8"));
const current = load("manufacturing-current");
const stale = load("manufacturing-stale");
const five = load("five-current");
const now = (s: RecallSnapshot) => Date.parse(s.freshness!.verifiedAt);
function passport(s = current, id = "MTR-27002") {
  const g = evaluateEnvelope({ status: 200, body: s }, null, now(s));
  assert.notEqual(g.kind, "WITHHELD");
  if (g.kind === "WITHHELD") throw Error(g.reason);
  const p = projectPassport(g.view, id, { leaseOk: g.kind === "CURRENT", unavailableReason: "Checkpoint required" });
  assert.equal(p.found, true);
  if (!p.found) throw Error("missing motor");
  return p;
}

test("actual imported machining and QC PASS render as claims with useful evidence facts", () => {
  const p = passport();
  const machining = p.timeline.find(e => e.category === "Machining")!;
  const qc = p.timeline.find(e => e.title === "Inspection claim recorded")!;
  assert.ok(machining && qc);
  assert.match(qc.detail, /PASS/);
  assert.match(qc.detail, /not independent verification or release authorization/);
  assert.ok(p.evidence[machining.eventId].facts.some(([k, v]) => k === "Machine" && v === "LATHE-R2"));
  assert.ok(p.evidence[qc.eventId].facts.some(([k]) => k === "Inspected machining events"));
  assert.ok(!p.notes.some(n => n.id === "inspection"));
  assert.equal(p.notes.find(n => n.id === "inspection-claim")?.kind, "UNVERIFIED");
});

test("QC PASS preserves actual affected and unresolved recall holds", () => {
  for (const [id, finding] of [["MTR-27002", "AFFECTED"], ["MTR-27003", "UNRESOLVED"]]) {
    const r = passport(current, id).recall;
    assert.equal(r.state, "CURRENT");
    if (r.state !== "CURRENT") throw Error("not current");
    assert.equal(r.finding, finding); assert.equal(r.hold, true);
    assert.equal(isCurrentClearance(r.clearance), false);
  }
});

test("stale checkpoint retains lifecycle facts but no current findings or clearance", () => {
  const g = evaluateEnvelope({ status: 200, body: stale }, null, now(stale));
  assert.equal(g.kind, "SEGREGATED");
  const p = passport(stale);
  assert.ok(p.timeline.some(e => e.category === "Machining"));
  assert.equal(p.recall.state, "UNAVAILABLE");
  assert.equal("clearance" in p.recall, false);
});

test("expired verification lease withholds current claims", () => {
  const g = evaluateEnvelope({ status: 200, body: current }, null, now(current) + 6000);
  assert.equal(g.kind, "WITHHELD");
});

test("original five-motor actual findings survive the cloned frontend gate", () => {
  const expected = ["AFFECTED", "UNRESOLVED", "EXCLUDED_WITH_EVIDENCE", "UNRESOLVED", "UNRESOLVED"];
  for (let i = 0; i < 5; i++) {
    const p = passport(five, `MTR-2600${i + 1}`);
    assert.equal(p.recall.state, "CURRENT");
    if (p.recall.state !== "CURRENT") throw Error("not current");
    assert.equal(p.recall.finding, expected[i]);
    if (i !== 2) { assert.equal(p.recall.hold, true); assert.equal(isCurrentClearance(p.recall.clearance), false); }
  }
});

test("projection is deterministic, does not mutate data or expose actor identities", () => {
  const before = JSON.stringify(current);
  assert.deepEqual(passport(), passport());
  assert.equal(JSON.stringify(current), before);
  const text = JSON.stringify(passport());
  for (const e of current.units.find(u => u.unitId === "MTR-27002")!.events) {
    if (["MACHINING_RECORDED", "QUALITY_INSPECTION_RECORDED"].includes(e.eventType)) assert.equal(text.includes(e.actorId), false);
  }
});

test("missing inspection result never becomes PASS", () => {
  const s = structuredClone(current);
  const u = s.units.find(u => u.unitId === "MTR-27002")!;
  const e = u.events.find(e => e.eventType === "QUALITY_INSPECTION_RECORDED")!;
  delete e.payload.result;
  // Exercise the pure fact projection; malformed evidence is never passed off as a validated ledger.
  const p = buildPassport(s, u.unitId, { recallVerified: false });
  assert.ok(p.found);
  if (p.found) assert.match(p.timeline.find(t => t.eventId === e.eventId)!.detail, /result: not stated/);
});

async function call(path: string) {
  return GET(new NextRequest(`http://unified.test/api/${path}`), { params: Promise.resolve({ path: path.split("/") }) });
}

test("GET-only proxy retains approved resources and adds only the four history trace keys", async () => {
  const old = globalThis.fetch;
  const seen: string[] = [];
  globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
    seen.push(String(url)); assert.equal(init?.cache, "no-store");
    return new Response(JSON.stringify({ claim: "history" }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    for (const path of ["snapshot", "motors/MTR-27002/lifecycle", "motors/MTR-27002/genealogy", "motors/MTR-27002/provenance", "trace/rawMaterialLot/RAW-A", "trace/bearingLot/BR-204", "trace/machineId/LATHE-R2", "trace/componentId/SHAFT-A"]) {
      assert.equal((await call(path)).status, 200);
    }
    const count = seen.length;
    for (const path of ["units/MTR-27002/ship", "anchors/activate", "trace/customer/x", "trace/rawMaterialLot/a/b", "deviations"]) assert.equal((await call(path)).status, 404);
    assert.equal(seen.length, count); assert.equal("POST" in proxy, false);
  } finally { globalThis.fetch = old; }
});

test("proxy preserves checkpoint-required and verifying responses without fabricating snapshots", async () => {
  const old = globalThis.fetch;
  try {
    for (const [status, error] of [[409, "CHECKPOINT_REQUIRED"], [503, "VERIFYING"]] as const) {
      globalThis.fetch = (async () => new Response(JSON.stringify({ error }), { status })) as typeof fetch;
      const res = await call("motors/MTR-27002/decisions");
      assert.equal(res.status, status); assert.deepEqual(await res.json(), { error });
    }
    globalThis.fetch = (async () => { throw Error("private path should not be leaked"); }) as typeof fetch;
    const unavailable = await call("snapshot");
    assert.equal(unavailable.status, 503);
    assert.deepEqual(await unavailable.json(), { error: "UPSTREAM_UNAVAILABLE", decisionsUnavailable: true });
  } finally { globalThis.fetch = old; }
});

test("real GET proxy reaches only isolated manufacturing backend and returns genealogy", async () => {
  const url = process.env.PRAMAAN_API_URL!;
  assert.ok(url && !url.endsWith(":4411"), "Never use the running handoff backend in compatibility tests");
  const res = await call("motors/MTR-27002/lifecycle");
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.checkpoint.state, "ANCHORED_CURRENT");
  const bearing = body.backward.bearings.find((b: { slot: string; lot: string }) => b.slot === "DE" && b.lot === "BR-204");
  const trace = await call(`trace/rawMaterialLot/${encodeURIComponent(bearing.rawMaterialLot)}`);
  assert.equal(trace.status, 200);
  assert.ok((await trace.json()).motors.some((m: { motorSerial: string }) => m.motorSerial === "MTR-27002"));
});
