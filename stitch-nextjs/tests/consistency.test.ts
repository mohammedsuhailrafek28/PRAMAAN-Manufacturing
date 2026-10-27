import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { assess, epochOf } from "../src/dash/consistency";
import type { Snapshot } from "../src/dash/types";

// Real snapshots and per-motor bodies from owned ephemeral manufacturing databases (see compatibility/run.py). Nothing here is hand-made evidence.
type Res = { decisions: Record<string, any>; lifecycle: Record<string, any>; provenance: Record<string, any[]> };
const dir = process.env.PRAMAAN_COMPAT_FIXTURES!;
const load = <T,>(name: string): T => JSON.parse(readFileSync(resolve(dir, name + ".json"), "utf8"));
const cur = load<Snapshot>("manufacturing-current"), curR = load<Res>("resources-manufacturing-current");
const next = load<Snapshot>("manufacturing-successor"), nextR = load<Res>("resources-manufacturing-successor");
const stale = load<Snapshot>("manufacturing-stale"), staleR = load<Res>("resources-manufacturing-stale");
const M = "MTR-27002";
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));

test("epoch changes with the successor checkpoint, with another archive and when the snapshot is withdrawn", () => {
  assert.notEqual(epochOf(cur), epochOf(next));
  const other = clone(cur); other.freshness!.archiveId = "another-archive"; assert.notEqual(epochOf(cur), epochOf(other));
  assert.notEqual(epochOf(cur), epochOf(stale));
  assert.equal(epochOf(null), null);
  assert.equal(epochOf(clone(cur)), epochOf(cur), "an unchanged snapshot keeps its epoch, so polling alone never refetches");
});

test("each resource is CURRENT beside its own snapshot (actual backend bodies)", () => {
  for (const [s, r] of [[cur, curR], [next, nextR]] as const) {
    for (const u of s.units) {
      assert.equal(assess("decisions", r.decisions[u.unitId], s, u.unitId, true).consistency, "CURRENT", u.unitId);
      assert.equal(assess("lifecycle", r.lifecycle[u.unitId], s, u.unitId, true).consistency, "CURRENT", u.unitId);
    }
  }
});

test("a resource from the previous checkpoint is withheld beside the successor snapshot", () => {
  const d = assess("decisions", curR.decisions[M], next, M, true), l = assess("lifecycle", curR.lifecycle[M], next, M, true);
  assert.equal(d.consistency, "MISMATCH"); assert.equal(l.consistency, "MISMATCH");
  assert.equal(assess("decisions", nextR.decisions[M], cur, M, true).consistency, "MISMATCH", "a newer response is not current beside an older snapshot either");
});

test("decision version, history and eligibility differences are each rejected", () => {
  const v = clone(nextR.decisions[M]); const k = Object.keys(v).find((x) => x !== "checkpoint" && x !== "eligibility")!;
  const a = clone(v); a[k].current.decisionId += "-x"; assert.equal(assess("decisions", a, next, M, true).consistency, "MISMATCH");
  const b = clone(v); b[k].history = [...(b[k].history ?? []), b[k].current]; assert.equal(assess("decisions", b, next, M, true).consistency, "MISMATCH");
  const c = clone(v); c.eligibility = { currentReleaseEligible: !v.eligibility?.currentReleaseEligible }; assert.equal(assess("decisions", c, next, M, true).consistency, "MISMATCH");
  const d = clone(v); delete d.checkpoint; assert.equal(assess("decisions", d, next, M, true).consistency, "MISMATCH");
  assert.equal(assess("decisions", v, next, M, true).consistency, "CURRENT");
});

test("decisions are never current under an untrusted snapshot or a non-anchored checkpoint", () => {
  assert.equal(assess("decisions", curR.decisions[M], cur, M, false).consistency, "MISMATCH");
  const p = clone(curR.decisions[M]); p.checkpoint.state = "ANCHORED_PREFIX_ONLY"; assert.equal(assess("decisions", p, cur, M, true).consistency, "MISMATCH");
  assert.equal(assess("decisions", curR.decisions[M], stale, M, true).consistency, "MISMATCH");
});

test("lifecycle: prefix-only snapshot keeps recorded facts but is never CURRENT", () => {
  const v = assess("lifecycle", staleR.lifecycle[M], stale, M, false);
  assert.equal(v.consistency, "UNVERIFIED"); assert.match(v.reason, /not current/);
  assert.equal(assess("lifecycle", curR.lifecycle[M], cur, M, false).consistency, "UNVERIFIED", "lease expiry removes the CURRENT label even for a matching body");
});

test("lifecycle: event-count drift and missing metadata are not treated as consistent", () => {
  const more = clone(curR.lifecycle[M]); more.eventCount += 1; assert.equal(assess("lifecycle", more, cur, M, true).consistency, "MISMATCH");
  const bare = clone(curR.lifecycle[M]); delete bare.checkpoint; assert.equal(assess("lifecycle", bare, cur, M, true).consistency, "UNVERIFIED");
  const noCount = clone(curR.lifecycle[M]); delete noCount.eventCount; assert.equal(assess("lifecycle", noCount, cur, M, true).consistency, "UNVERIFIED");
  assert.equal(assess("lifecycle", curR.lifecycle["MTR-27001"], cur, "MTR-NOPE", true).consistency, "MISMATCH");
});

test("provenance has no watermark: never CURRENT, rejected when it holds events the snapshot lacks", () => {
  for (const s of [cur, next]) for (const u of s.units) {
    const r = (s === cur ? curR : nextR).provenance[u.unitId];
    assert.equal(assess("provenance", r, s, u.unitId, true).consistency, "UNVERIFIED");
  }
  const newer = clone(nextR.provenance[M]); assert.ok(newer.length > 0);
  assert.equal(assess("provenance", newer, cur, M, true).consistency === "CURRENT", false);
  const extra = [...clone(curR.provenance[M]), { ...clone(curR.provenance[M][0]), id: "urn:pramaan:MTR-27002:not-in-snapshot" }];
  assert.equal(assess("provenance", extra, cur, M, true).consistency, "MISMATCH");
  assert.equal(assess("provenance", { not: "an array" } as never, cur, M, true).consistency, "UNVERIFIED");
});

test("the successor adds evidence that the previous snapshot does not contain (so the fixtures really differ)", () => {
  const n = (s: Snapshot) => s.units.find((u) => u.unitId === M)!.eventCount;
  assert.ok(next.freshness!.sequence! > cur.freshness!.sequence! || next.checkpoint!.anchoredSequence! > cur.checkpoint!.anchoredSequence!);
  assert.ok((n(next) ?? 0) >= (n(cur) ?? 0));
});
