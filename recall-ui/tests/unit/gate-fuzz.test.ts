// Deterministic mutation fuzz of the shared gate over REAL captured envelopes (tests/fixtures/h1h2).
// The oracle is independent of gate.ts: it states only the necessary conditions for each verdict.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { evaluateDetailed } from "../../src/contract/gate";
import { clearanceOf, isHistorical, rawSnapshotOf } from "../../src/contract/gated";
import { isCurrentClearance } from "../../src/contract/clearance";

type Env = { status: number; body: any };
const load = (n: string): Env => JSON.parse(readFileSync(join(__dirname, "../fixtures/h1h2", `${n}.json`), "utf8"));
const BASES = ["current", "prefix_only", "unanchored"].map(load);

function rng(seed: number) { let s = seed >>> 0; return () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 2 ** 32; }; }
const pick = <T,>(r: () => number, xs: readonly T[]): T => xs[Math.floor(r() * xs.length)];
const JUNK: unknown[] = [undefined, null, "", "x", "verified", 0, -1, 1, 7, 1e9, true, false, [], {}, "UNVERIFIED", "VERIFIED", "ANCHORED_CURRENT", "ANCHORED_PREFIX_ONLY", "UNANCHORED", "HISTORICAL_UNVERIFIABLE"];
const PATHS = [
  ["checkpoint", "state"], ["checkpoint", "h2"], ["checkpoint", "anchoredSequence"], ["checkpoint", "checkpointRequired"],
  ["freshness", "status"], ["freshness", "sequence"], ["freshness", "headHash"], ["freshness", "archiveId"], ["freshness", "verifiedAt"], ["freshness", "maxAgeSeconds"],
  ["eligibility", "MTR-26003", "currentReleaseEligible"], ["eligibility", "MTR-26001", "currentReleaseEligible"], ["eligibility", "MTR-26003"], ["eligibility"], ["checkpoint"], ["freshness"],
] as const;

function mutateOnce(r: () => number, b: any) {
  const path = pick(r, PATHS);
  let o = b;
  for (let i = 0; i < path.length - 1; i++) { if (o == null || typeof o !== "object") return; o = o[path[i]]; }
  if (o == null || typeof o !== "object") return;
  const key = path[path.length - 1];
  if (r() < 0.2) delete o[key]; else o[key] = pick(r, JUNK);
}

const eligibleIds = (b: any): string[] => (b.eligibility && typeof b.eligibility === "object" ? Object.keys(b.eligibility).filter((k) => b.eligibility[k]?.currentReleaseEligible === true) : []);

describe("gate fuzz: 12,000 mutated real envelopes", () => {
  it("SEGREGATED / CURRENT verdicts only ever occur under their exact structural conditions", () => {
    const r = rng(0xC0FFEE);
    const tally: Record<string, number> = { CURRENT: 0, PREFIX_ONLY: 0, UNANCHORED: 0, WITHHELD: 0 };
    const N = 12_000;
    for (let i = 0; i < N; i++) {
      const base = pick(r, BASES);
      const env: Env = JSON.parse(JSON.stringify(base));
      const nMut = 1 + Math.floor(r() * 3);
      for (let k = 0; k < nMut; k++) mutateOnce(r, env.body);
      if (r() < 0.02) env.status = pick(r, [201, 400, 409, 503, 500]);
      const b = env.body;
      const now = Date.parse(base.body.freshness.verifiedAt) + 1000;
      const { gate } = evaluateDetailed(env, null, now);
      tally[gate.kind === "CURRENT" ? "CURRENT" : gate.kind === "SEGREGATED" ? gate.cause : "WITHHELD"]++;

      if (gate.kind === "SEGREGATED") {
        expect(env.status).toBe(200);
        expect(isHistorical(gate.view)).toBe(true);
        const raw = rawSnapshotOf(gate.view);
        expect(raw.decisions).toEqual({});
        expect(eligibleIds(b)).toEqual([]);                              // eligibility must be withheld everywhere
        if (gate.cause === "PREFIX_ONLY") {
          expect(b.checkpoint.state).toBe("ANCHORED_PREFIX_ONLY");
          expect(b.checkpoint.h2).toBe("VERIFIED");                      // owner decision: only a verified H2 may be segregated
          expect(Number.isInteger(b.checkpoint.anchoredSequence)).toBe(true);
          expect(b.checkpoint.anchoredSequence).toBeGreaterThanOrEqual(1);
          expect(b.checkpoint.anchoredSequence).toBeLessThanOrEqual(b.freshness.sequence);
        } else {
          expect(b.checkpoint.state).toBe("UNANCHORED");
          expect(b.checkpoint.anchoredSequence).toBeNull();
          expect(b.checkpoint.h2).toBe("UNVERIFIED");                    // explicitly unverified local claims only
        }
      }
      if (gate.kind === "CURRENT") {
        expect(env.status).toBe(200);
        expect(b.checkpoint.state).toBe("ANCHORED_CURRENT");
        expect(b.checkpoint.h2).toBe("VERIFIED");
        expect(b.checkpoint.anchoredSequence).toBe(b.freshness.sequence);
        expect(b.checkpoint.checkpointRequired).toBe(false);
        expect(gate.leaseMs).toBeGreaterThan(0);
        expect(gate.leaseMs).toBeLessThanOrEqual(5000);
        for (const u of b.units) {
          const cleared = isCurrentClearance(clearanceOf(gate.view, u.unitId));
          const ds = Object.values(b.decisions[u.unitId] ?? {}) as any[];
          const honest = b.eligibility[u.unitId]?.currentReleaseEligible === true && ds.length > 0 && ds.every((x) => x.current.operationalAction === "RELEASE_ELIGIBLE");
          expect(cleared, u.unitId).toBe(honest);                        // clearance == explicit eligibility AND all-release decisions, nothing else
        }
      }
    }
    // The fuzzer must actually reach every verdict, or it proves nothing.
    expect(tally.CURRENT).toBeGreaterThan(50);
    expect(tally.PREFIX_ONLY).toBeGreaterThan(50);
    expect(tally.UNANCHORED).toBeGreaterThan(50);
    expect(tally.WITHHELD).toBeGreaterThan(1000);
  }, 120_000);
});

describe("Decision-2 table", () => {
  const withMeta = (base: Env, fn: (b: any) => void) => { const e: Env = JSON.parse(JSON.stringify(base)); fn(e.body); return e; };
  const kind = (e: Env) => { const g = evaluateDetailed(e, null, Date.parse(e.body.freshness.verifiedAt) + 1000).gate; return g.kind === "WITHHELD" ? `WITHHELD/${g.cause}` : g.kind === "SEGREGATED" ? `SEGREGATED/${g.cause}` : "CURRENT"; };
  const prefix = BASES[1], unanch = BASES[2], current = BASES[0];
  it("PREFIX_ONLY: segregated only with H2 VERIFIED + integer anchoredSequence; missing/unknown/contradictory is WITHHELD", () => {
    expect(kind(prefix)).toBe("SEGREGATED/PREFIX_ONLY");
    expect(kind(withMeta(prefix, (b) => { b.checkpoint.h2 = "UNVERIFIED"; }))).toBe("WITHHELD/INTEGRITY");
    expect(kind(withMeta(prefix, (b) => { b.checkpoint.h2 = "HISTORICAL_UNVERIFIABLE"; }))).toBe("WITHHELD/INTEGRITY");
    expect(kind(withMeta(prefix, (b) => { b.checkpoint.h2 = "MAYBE"; }))).toBe("WITHHELD/UNKNOWN_STATE");
    expect(kind(withMeta(prefix, (b) => { delete b.checkpoint.h2; }))).toBe("WITHHELD/MISSING_METADATA");
    expect(kind(withMeta(prefix, (b) => { b.checkpoint.anchoredSequence = null; }))).toBe("WITHHELD/MISSING_METADATA");
    expect(kind(withMeta(prefix, (b) => { b.checkpoint.anchoredSequence = b.freshness.sequence + 1; }))).toBe("WITHHELD/CONTRADICTORY");
    expect(kind(withMeta(prefix, (b) => { b.checkpoint.anchoredSequence = 0; }))).toBe("WITHHELD/CONTRADICTORY");
    expect(kind(withMeta(prefix, (b) => { b.eligibility["MTR-26003"].currentReleaseEligible = true; }))).toBe("WITHHELD/CONTRADICTORY");
  });
  it("UNANCHORED: only explicitly unverified local claims", () => {
    expect(kind(unanch)).toBe("SEGREGATED/UNANCHORED");
    expect(kind(withMeta(unanch, (b) => { b.checkpoint.h2 = "VERIFIED"; }))).toBe("WITHHELD/CONTRADICTORY");
    expect(kind(withMeta(unanch, (b) => { b.checkpoint.anchoredSequence = 3; }))).toBe("WITHHELD/CONTRADICTORY");
    expect(kind(withMeta(unanch, (b) => { b.checkpoint.h2 = "garbage"; }))).toBe("WITHHELD/UNKNOWN_STATE");
  });
  it("ELIGIBILITY_WITHHELD is per-motor only: the snapshot stays CURRENT", () => {
    expect(kind(current)).toBe("CURRENT");
    expect(kind(withMeta(current, (b) => { b.eligibility["MTR-26003"].currentReleaseEligible = false; }))).toBe("CURRENT");
  });
});
