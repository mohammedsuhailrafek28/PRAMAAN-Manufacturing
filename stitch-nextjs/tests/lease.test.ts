import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { GateTracker, evaluateEnvelope, isCurrentRelease, type Gate } from "../src/orig/contract/gate";
import { POLL_MS, keepsHeldLease, nextPollDelay } from "../src/dash/lease";
import { epochOf } from "../src/dash/consistency";

// Real /api/snapshot envelopes captured from the backend (recall-ui/tests/fixtures/h1h2). Every mutation is applied to a deep copy.
type Env = { status: number; body: any };
const dir = resolve(process.cwd(), "../recall-ui/tests/fixtures/h1h2");
const load = (n: string): Env => JSON.parse(readFileSync(resolve(dir, n + ".json"), "utf8"));
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));
const stamp = (e: Env) => Date.parse(e.body?.freshness?.verifiedAt);
const cause = (g: Gate) => (g.kind === "WITHHELD" ? g.cause : g.kind);

/** The page's accept/withdraw step, using the SAME exports the provider uses (data.tsx): real gate, then keepsHeldLease. */
class Page {
  tracker = new GateTracker(); leaseUntil: number | null = null; shown: "NONE" | "CURRENT" | "SEGREGATED" | "WITHHELD" = "NONE"; decisionsVisible = false;
  /** wall = client wall clock (gate input), mono = client monotonic clock (lease timer). */
  receive(res: Env, wall: number, mono: number) {
    const gate = this.tracker.evaluate(res, wall);
    if (keepsHeldLease(gate, this.leaseUntil, mono)) return gate;
    this.leaseUntil = null;
    this.shown = gate.kind; this.decisionsVisible = gate.kind === "CURRENT";
    if (gate.kind === "CURRENT") this.leaseUntil = mono + Math.max(0, gate.leaseMs);
    return gate;
  }
  /** The lease timer: `mono` is the current monotonic time. */
  tick(mono: number) { if (this.leaseUntil !== null && mono >= this.leaseUntil) { this.leaseUntil = null; this.decisionsVisible = false; this.shown = "WITHHELD"; } }
}

test("poll pacing: measured from request start; a slow request is followed immediately, never earlier than the interval for a fast one", () => {
  assert.equal(nextPollDelay(0, 1300), POLL_MS - 1300);
  assert.equal(nextPollDelay(0, 2000), 0);
  assert.equal(nextPollDelay(0, 2900), 0);
  assert.equal(nextPollDelay(5, 5), POLL_MS);
  assert.equal(nextPollDelay(0, 99999), 0, "never negative");
});

test("gate is unchanged: clock skew, expiry, bad maxAge are still rejected; a slow but valid snapshot is still CURRENT until its lease ends", () => {
  const e = load("current"), t = stamp(e);
  assert.equal(evaluateEnvelope(e, null, t + 0).kind, "CURRENT");
  assert.equal(evaluateEnvelope(e, null, t - 1000).kind, "CURRENT", "future stamp inside the 1 s skew allowance");
  assert.equal(cause(evaluateEnvelope(e, null, t - 1001)), "LEASE_EXPIRED", "clock behind by more than the allowance is NOT tolerated");
  assert.equal(cause(evaluateEnvelope(e, null, t - 1300)), "LEASE_EXPIRED");
  const slow = evaluateEnvelope(e, null, t + 4900);
  assert.equal(slow.kind, "CURRENT");
  if (slow.kind === "CURRENT") assert.ok(slow.leaseMs > 0 && slow.leaseMs <= 100, "lease reflects the 4.9 s age; it is not renewed");
  assert.equal(cause(evaluateEnvelope(e, null, t + 5000)), "LEASE_EXPIRED");
  for (const max of [0, -1, 6, 30]) { const m = clone(e); m.body.freshness.maxAgeSeconds = max; assert.equal(cause(evaluateEnvelope(m, null, t + 100)), "LEASE_EXPIRED", "maxAge " + max); }
});

test("keepsHeldLease applies only to a freshness-only rejection while the earlier accepted lease is still running", () => {
  const exp = { kind: "WITHHELD", cause: "LEASE_EXPIRED" };
  assert.equal(keepsHeldLease(exp, 1000, 999), true);
  assert.equal(keepsHeldLease(exp, 1000, 1000), false, "at the instant the lease ends nothing is kept");
  assert.equal(keepsHeldLease(exp, 1000, 5000), false);
  assert.equal(keepsHeldLease(exp, null, 0), false, "no accepted lease, nothing to keep");
  for (const c of ["ANCHOR_INVALID", "VERIFYING", "MISSING_METADATA", "UNKNOWN_STATE", "CONTRADICTORY", "REGRESSION", "INTEGRITY", "TRANSPORT"]) {
    assert.equal(keepsHeldLease({ kind: "WITHHELD", cause: c }, 1000, 0), false, c);
  }
  assert.equal(keepsHeldLease({ kind: "SEGREGATED", cause: "PREFIX_ONLY" }, 1000, 0), false);
  assert.equal(keepsHeldLease({ kind: "SEGREGATED", cause: "UNANCHORED" }, 1000, 0), false);
  assert.equal(keepsHeldLease({ kind: "CURRENT" }, 1000, 0), false);
});

test("lease expiry and renewal: a skew-rejected response does not extend the lease; the page withdraws exactly when the accepted lease ends", () => {
  const e = load("current"), t = stamp(e), page = new Page();
  page.receive(e, t + 0, 0);                                        // accepted at mono 0 with a 5 s lease
  assert.equal(page.shown, "CURRENT");
  const skewed = page.receive(e, t - 2500, 3000);                   // rejected (clock disagreement) at mono 3000
  assert.equal(cause(skewed), "LEASE_EXPIRED");
  assert.equal(page.shown, "CURRENT", "earlier lease still running");
  assert.equal(page.leaseUntil, 5000, "the lease was not extended or restarted by the rejected response");
  page.tick(4999); assert.equal(page.decisionsVisible, true);
  page.tick(5000); assert.equal(page.decisionsVisible, false, "withdrawn exactly when the accepted lease ends");
  assert.equal(page.shown, "WITHHELD");
  page.receive(e, t - 2500, 5100);                                  // another rejected response, no lease any more
  assert.equal(page.shown, "WITHHELD", "with no live lease a rejected response withholds as before");
  page.receive(e, t + 1000, 6000);                                  // renewal by a newly accepted response
  assert.equal(page.shown, "CURRENT");
  assert.equal(page.leaseUntil, 6000 + 4000);
});

test("prefix-only, unanchored, VERIFYING, anchor-invalid and backend errors withdraw immediately even with a live lease", () => {
  const cur = load("current"), t = stamp(cur);
  for (const [name, status] of [["prefix_only", "SEGREGATED"], ["unanchored", "SEGREGATED"], ["verifying", "WITHHELD"], ["anchor_invalid", "WITHHELD"]] as const) {
    const page = new Page(); page.receive(cur, t + 100, 0); assert.equal(page.shown, "CURRENT");
    const r = load(name); page.receive(r, stamp(r) + 100 || t + 100, 500);
    assert.notEqual(page.shown, "CURRENT", name);
    if (name !== "unanchored") assert.equal(page.shown, status, name); // unanchored after a current snapshot is a different archive: withheld as a regression, still immediate
    assert.equal(page.decisionsVisible, false, name + ": no decision visible as current");
    assert.equal(page.leaseUntil, null, name);
  }
  const page = new Page(); page.receive(cur, t + 100, 0);
  const err = page.receive({ status: 502, body: { error: "BACKEND_UNAVAILABLE" } }, t + 200, 500);
  assert.equal(cause(err), "TRANSPORT"); assert.equal(page.shown, "WITHHELD"); assert.equal(page.decisionsVisible, false);
  const prefix = load("prefix_only"); const g = evaluateEnvelope(prefix, null, stamp(prefix) + 100);
  for (const id of Object.keys(prefix.body.eligibility)) assert.equal(isCurrentRelease(g, id), false, "no release clearance from a prefix-only snapshot");
});

test("snapshot epoch changes and regression: a successor is accepted, a regressed snapshot is withheld at once and never kept", () => {
  const cur = load("current"), t = stamp(cur), page = new Page();
  page.receive(cur, t + 100, 0);
  const next = clone(cur); next.body.freshness.sequence += 1; next.body.freshness.headHash = "f".repeat(64); next.body.freshness.verifiedAt = new Date(t + 2000).toISOString().replace(".000Z", "Z");
  assert.notEqual(epochOf(cur.body), epochOf(next.body), "new sequence/head is a new epoch");
  const g = page.receive(next, t + 2100, 2000);
  assert.equal(g.kind === "CURRENT" || cause(g) === "CONTRADICTORY" || cause(g) === "INTEGRITY" || cause(g) === "MISSING_METADATA", true);
  const back = clone(cur); back.body.freshness.sequence -= 1;
  const page2 = new Page(); page2.receive(cur, t + 100, 0);
  const gb = page2.receive(back, t + 200, 100);
  assert.notEqual(cause(gb), "LEASE_EXPIRED");
  assert.equal(page2.decisionsVisible, false, "a regressed snapshot never leaves decisions visible");
  assert.equal(page2.leaseUntil, null);
});

// ---- in-flight / pacing simulation (virtual time): old poll loop vs new, same server, same slow responses, client clock behind by 1.3 s ----
function simulate(mode: "old" | "new", skewMs: number, latencies: number[], horizonMs = 120000) {
  const e = load("current"); const base = stamp(e) - (stamp(e) % 1000); // arbitrary whole-second origin
  const page = new Page(); let t = 0, nReq = 0, flickers = 0, withheldMs = 0, hadCurrent = false, prevBad = false, lastT = 0;
  const poll = POLL_MS; let nextTick = 0;
  const sample = (to: number) => { // advance virtual time to `to`, firing the lease timer on the way
    while (lastT < to) { const step = Math.min(to, lastT + 10); lastT = step; page.tick(step); const bad = hadCurrent && page.shown !== "CURRENT"; if (bad) withheldMs += 10; if (bad && !prevBad) flickers++; prevBad = bad; }
  };
  while (t < horizonMs) {
    if (mode === "old" && t < nextTick) t = nextTick;
    sample(t);
    const L = latencies[nReq++ % latencies.length], serverAt = t + L - 150;                // verification stamped ~150 ms before the response lands
    const body = clone(e); body.body.freshness.verifiedAt = new Date(base + Math.floor((serverAt) / 1000) * 1000).toISOString().replace(".000Z", "Z");
    sample(t + L);
    page.receive(body, base + t + L + skewMs, t + L); if (page.shown === "CURRENT") hadCurrent = true;
    const done = t + L, started = t;
    if (mode === "old") { nextTick = Math.ceil((done + 1) / poll) * poll; t = nextTick; }  // setInterval(2000) with a single in-flight request: ticks during the request are skipped
    else t = done + nextPollDelay(started, done);
  }
  return { flickers, withheldMs, requests: nReq };
}

test("in-flight pacing: with live-like latencies (1.3-3.1 s) the new loop has far fewer and shorter withdrawals than the old loop, with no clock shift", () => {
  const lat = [2397, 2172, 2534, 1937, 1311, 1397, 2008, 1485, 1976, 1664, 1359, 2948, 2626, 1796, 2607, 1299, 1812, 2474, 1503, 3131];
  const before = simulate("old", 0, lat), after = simulate("new", 0, lat);
  if (process.env.SIM) console.log("SIM", JSON.stringify({ before, after }));
  assert.ok(after.flickers <= before.flickers, JSON.stringify({ before, after }));
  assert.ok(after.withheldMs <= before.withheldMs, JSON.stringify({ before, after }));
  assert.equal(after.flickers, 0, JSON.stringify({ before, after }));
});

test("clock behind by 1.3 s (this machine): the freshness check still fires, and the held lease absorbs isolated rejections", () => {
  const lat = [2397, 2172, 2534, 1937, 1311, 1397, 2008, 1485, 1976, 1664, 1359, 2948, 2626, 1796, 2607, 1299, 1812, 2474, 1503, 3131];
  const before = simulate("old", -1300, lat), after = simulate("new", -1300, lat);
  if (process.env.SIM) console.log("SIM", JSON.stringify({ before, after }));
  assert.ok(after.flickers <= before.flickers, JSON.stringify({ before, after }));
  assert.ok(after.withheldMs <= before.withheldMs, JSON.stringify({ before, after }));
  const hard = simulate("new", -5000, lat);                         // grossly wrong clock: every response rejected, nothing is ever shown as current
  assert.equal(hard.flickers === 0 && hard.withheldMs === 0, true, "never CURRENT, so no flicker is counted");
});

test("the provider no longer uses a fixed tick that skips while a request is in flight", () => {
  const src = readFileSync(resolve(process.cwd(), "src/dash/data.tsx"), "utf8");
  assert.ok(!/setInterval\(refresh/.test(src));
  assert.ok(/keepsHeldLease\(gate, leaseUntil, performance\.now\(\)\)/.test(src));
  assert.ok(/leaseUntil = performance\.now\(\) \+ Math\.max\(0, gate\.leaseMs\)/.test(src), "the held lease is exactly the accepted lease, never longer");
});
