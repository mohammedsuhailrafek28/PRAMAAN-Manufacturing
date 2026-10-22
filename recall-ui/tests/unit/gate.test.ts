// Adversarial unit tests for the shared typed fail-closed gate. Envelopes in tests/fixtures/h1h2 are
// REAL /api/snapshot responses captured from the H1/H2 backend (f9dcf56) by
// tools/capture_h1h2_envelopes.py. Every mutation below is applied to a deep copy.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { clearanceOf } from "../../src/contract/gated";
import { GateTracker, evaluateDetailed, evaluateEnvelope, isCurrentRelease, type Gate } from "../../src/contract/gate";

type Env = { status: number; body: any };
const load = (name: string): Env => JSON.parse(readFileSync(join(__dirname, "../fixtures/h1h2", `${name}.json`), "utf8"));
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));
const at = (e: Env, extraMs = 1000) => Date.parse(e.body.freshness.verifiedAt) + extraMs;
const cur = () => load("current");
const withheld = (g: Gate) => (g.kind === "WITHHELD" ? g.cause : `NOT_WITHHELD:${g.kind}`);
const mutate = (e: Env, fn: (b: any) => void): Env => { const c = clone(e); fn(c.body); return c; };

describe("gate: real captured envelopes", () => {
  it("FE-01 CURRENT: only the eligible motor is cleared", () => {
    const e = cur(); const g = evaluateEnvelope(e, null, at(e));
    expect(g.kind).toBe("CURRENT");
    expect(isCurrentRelease(g, "MTR-26003")).toBe(true);
    for (const id of ["MTR-26001", "MTR-26002", "MTR-26004", "MTR-26005"]) expect(isCurrentRelease(g, id)).toBe(false);
    if (g.kind === "CURRENT") expect(g.leaseMs).toBeGreaterThan(0);
  });

  it("FE-02 PREFIX_ONLY is segregated, never verified, and nothing is current release", () => {
    const e = load("prefix_only");
    expect(Object.values(e.body.decisions["MTR-26003"]).map((b: any) => b.current.operationalAction)).toContain("RELEASE_ELIGIBLE"); // the trap
    const g = evaluateEnvelope(e, null, at(e));
    expect(g.kind).toBe("SEGREGATED");
    if (g.kind === "SEGREGATED") { expect(g.cause).toBe("PREFIX_ONLY"); expect(g.reason).toMatch(/checkpoint is required/); }
    for (const id of Object.keys(e.body.eligibility)) expect(isCurrentRelease(g, id)).toBe(false);
  });

  it("FE-03 UNANCHORED is segregated as unverified local claims, with no lease required", () => {
    const e = load("unanchored"); const g = evaluateEnvelope(e, null, at(e));
    expect(g.kind).toBe("SEGREGATED");
    if (g.kind === "SEGREGATED") { expect(g.cause).toBe("UNANCHORED"); expect(g.reason).toMatch(/externally verified or current/); }
  });

  it("FE-04/05/06 structured error bodies: ANCHOR_INVALID, VERIFYING and 400 are WITHHELD with distinct causes", () => {
    expect(withheld(evaluateEnvelope(load("anchor_invalid"), null))).toBe("ANCHOR_INVALID");
    expect(withheld(evaluateEnvelope(load("verifying"), null))).toBe("VERIFYING");
    expect(withheld(evaluateEnvelope(load("invalid_request"), null))).toBe("TRANSPORT");
  });

  it("FE-04 a 409 whose body is not the structured ANCHOR_INVALID shape is TRANSPORT, never a historical view", () => {
    for (const body of [null, "boom", {}, { state: "SOMETHING" }, { error: "ANCHOR_INVALID" }, []]) expect(withheld(evaluateEnvelope({ status: 409, body }, null))).toBe("TRANSPORT");
    for (const status of [201, 204, 301, 400, 404, 500, 502, 503, 0]) expect(withheld(evaluateEnvelope({ status, body: cur().body }, null))).toBe(status === 503 ? "TRANSPORT" : "TRANSPORT");
  });
});

describe("gate: strict metadata (FE-07..FE-16)", () => {
  it("FE-07 legacy envelope (anchored status, no checkpoint/eligibility) is never CURRENT", () => {
    const e = mutate(cur(), (b) => { delete b.checkpoint; delete b.eligibility; });
    expect(withheld(evaluateEnvelope(e, null, at(e)))).toBe("MISSING_METADATA");
  });
  it("FE-08 each strict field alone missing is WITHHELD", () => {
    for (const k of ["checkpoint", "eligibility", "freshness"]) {
      const e = mutate(cur(), (b) => { delete b[k]; });
      expect(withheld(evaluateEnvelope(e, null, at(cur())))).toBe("MISSING_METADATA");
    }
    for (const k of ["checkpoint", "eligibility", "freshness"]) for (const v of [null, "x", 1, [], true]) {
      const e = mutate(cur(), (b) => { b[k] = v; });
      expect(withheld(evaluateEnvelope(e, null, at(cur())))).toBe("MISSING_METADATA");
    }
  });
  it("FE-09 unknown / near-miss checkpoint states are UNKNOWN_STATE", () => {
    for (const v of ["ANCHORED_CURRENT ", "anchored_current", "", "CURRENT", "ANCHORED_FUTURE", null, 1, {}, ["ANCHORED_CURRENT"], true]) {
      const e = mutate(cur(), (b) => { b.checkpoint.state = v; });
      expect(withheld(evaluateEnvelope(e, null, at(cur())))).toBe("UNKNOWN_STATE");
    }
  });
  it("FE-04 checkpoint.state ANCHOR_INVALID inside a 200 body is WITHHELD", () => {
    const e = mutate(cur(), (b) => { b.checkpoint.state = "ANCHOR_INVALID"; });
    expect(withheld(evaluateEnvelope(e, null, at(cur())))).toBe("ANCHOR_INVALID");
  });
  it("FE-10/11/12/13 contradictory state/status/h2/required combinations are CONTRADICTORY", () => {
    const cases: Array<[string, Env, (b: any) => void]> = [
      ["current + prefix status", cur(), (b) => { b.freshness.status = "VERIFIED_PREFIX_SYNTHETIC"; }],
      ["current + unanchored status", cur(), (b) => { b.freshness.status = "HISTORICAL_UNANCHORED"; }],
      ["current + unknown status", cur(), (b) => { b.freshness.status = "VERIFIED"; }],
      ["prefix + anchored status", load("prefix_only"), (b) => { b.freshness.status = "VERIFIED_ANCHORED_SYNTHETIC"; }],
      ["current + h2 unverified", cur(), (b) => { b.checkpoint.h2 = "UNVERIFIED"; }],
      ["current + required true", cur(), (b) => { b.checkpoint.checkpointRequired = true; }],
      ["prefix + required false", load("prefix_only"), (b) => { b.checkpoint.checkpointRequired = false; }],
      ["current + anchoredSequence != sequence", cur(), (b) => { b.checkpoint.anchoredSequence = b.freshness.sequence - 1; }],
      ["unanchored + anchored status", load("unanchored"), (b) => { b.freshness.status = "VERIFIED_ANCHORED_SYNTHETIC"; }],
    ];
    for (const [name, env, fn] of cases) expect(withheld(evaluateEnvelope(mutate(env, fn), null, at(env))), name).toBe("CONTRADICTORY");
  });
  it("FE-14/15/16 eligibility contradictions are CONTRADICTORY", () => {
    const e = cur(); const t = at(e);
    const cases: Array<[string, (b: any) => void]> = [
      ["eligible while RECALL_HOLD", (b) => { b.eligibility["MTR-26001"].currentReleaseEligible = true; }],
      ["eligible with a pending notification", (b) => { const n = b.notifications[0]; b.eligibility["MTR-26003"].currentReleaseEligible = true; n.unitId = "MTR-26003"; }],
      ["unit missing from eligibility", (b) => { delete b.eligibility["MTR-26003"]; }],
      ["extra eligibility key", (b) => { b.eligibility["MTR-99999"] = { currentReleaseEligible: false }; }],
      ["string true", (b) => { b.eligibility["MTR-26003"].currentReleaseEligible = "true"; }],
      ["number 1", (b) => { b.eligibility["MTR-26003"].currentReleaseEligible = 1; }],
      ["null entry", (b) => { b.eligibility["MTR-26003"] = null; }],
      ["entry without flag", (b) => { b.eligibility["MTR-26003"] = {}; }],
    ];
    for (const [name, fn] of cases) expect(withheld(evaluateEnvelope(mutate(e, fn), null, t)), name).toBe("CONTRADICTORY");
  });
  it("FE-16 eligible=true in PREFIX_ONLY or UNANCHORED is CONTRADICTORY (never promoted)", () => {
    for (const n of ["prefix_only", "unanchored"]) {
      const e = mutate(load(n), (b) => { b.eligibility["MTR-26003"].currentReleaseEligible = true; });
      expect(withheld(evaluateEnvelope(e, null, at(e))), n).toBe("CONTRADICTORY");
    }
  });
  it("PREFIX_ONLY whose H2 proof is not VERIFIED is WITHHELD (evidence must pass the available checks)", () => {
    for (const h2 of ["HISTORICAL_UNVERIFIABLE", "UNVERIFIED"]) {
      const e = mutate(load("prefix_only"), (b) => { b.checkpoint.h2 = h2; });
      expect(withheld(evaluateEnvelope(e, null, at(e))), h2).toBe("INTEGRITY");
    }
    for (const h2 of ["", "verified", "OK"]) {                    // not a defined H2 value at all
      const e = mutate(load("prefix_only"), (b) => { b.checkpoint.h2 = h2; });
      expect(withheld(evaluateEnvelope(e, null, at(e))), h2).toBe("UNKNOWN_STATE");
    }
    for (const h2 of [undefined, null, 1]) {
      const e = mutate(load("prefix_only"), (b) => { b.checkpoint.h2 = h2; });
      expect(withheld(evaluateEnvelope(e, null, at(e))), String(h2)).toBe("MISSING_METADATA");
    }
  });
  it("FE-17/18 decision invariants and unknown actions are WITHHELD (INTEGRITY)", () => {
    const e = cur(); const t = at(e);
    const a = mutate(e, (b) => { b.decisions["MTR-26001"]["P1"] ??= null; const pol = Object.keys(b.decisions["MTR-26001"])[0]; b.decisions["MTR-26001"][pol].current.operationalAction = "RELEASE_ELIGIBLE"; });
    expect(withheld(evaluateEnvelope(a, null, t))).toBe("INTEGRITY");
    const b2 = mutate(e, (b) => { const pol = Object.keys(b.decisions["MTR-26001"])[0]; b.decisions["MTR-26001"][pol].current.operationalAction = "CLEARED"; });
    expect(withheld(evaluateEnvelope(b2, null, t))).toBe("INTEGRITY");
    for (const body of [null, "x", 1, [], { schemaVersion: 2 }, { schemaVersion: 1, checkpoint: {}, eligibility: {}, freshness: {} }]) expect(["INTEGRITY", "MISSING_METADATA", "UNKNOWN_STATE"]).toContain(withheld(evaluateEnvelope({ status: 200, body }, null, at(e))));
  });
  it("FE-27 unknown extra top-level fields do not change the verdict", () => {
    const e = mutate(cur(), (b) => { b.extraField = { a: 1 }; });
    expect(evaluateEnvelope(e, null, at(e)).kind).toBe("CURRENT");
  });
  it("a CURRENT motor whose own eligibility is withheld stays CURRENT: findings kept, only that motor's clearance is NOT_CLEARED", () => {
    const e = mutate(cur(), (b) => { b.eligibility["MTR-26003"].currentReleaseEligible = false; });
    const g = evaluateEnvelope(e, null, at(e));
    expect(g.kind).toBe("CURRENT");                                // never a gate cause, never downgrades other motors
    if (g.kind !== "CURRENT") return;
    expect(clearanceOf(g.view, "MTR-26003")).toBe("NOT_CLEARED");
    expect(isCurrentRelease(g, "MTR-26003")).toBe(false);
    const others = Object.keys(e.body.eligibility).filter((id) => id !== "MTR-26003" && e.body.eligibility[id].currentReleaseEligible);
    for (const id of others) expect(isCurrentRelease(g, id), id).toBe(true);
  });
});

describe("gate: lease (FE-23)", () => {
  it("expired, skewed, malformed, non-finite and over-long leases are LEASE_EXPIRED", () => {
    const e = cur(); const t0 = Date.parse(e.body.freshness.verifiedAt);
    expect(withheld(evaluateEnvelope(e, null, t0 + 5000))).toBe("LEASE_EXPIRED");
    expect(withheld(evaluateEnvelope(e, null, t0 + 60_000))).toBe("LEASE_EXPIRED");
    expect(withheld(evaluateEnvelope(e, null, t0 - 1001))).toBe("LEASE_EXPIRED");
    for (const [k, v] of [["maxAgeSeconds", 0], ["maxAgeSeconds", 6], ["maxAgeSeconds", -1], ["maxAgeSeconds", null], ["maxAgeSeconds", "5"], ["verifiedAt", "2026-10-22 08:17:56"], ["verifiedAt", ""], ["verifiedAt", "garbage"]] as const) {
      const m = mutate(e, (b) => { b.freshness[k] = v; });
      expect(withheld(evaluateEnvelope(m, null, t0 + 1000)), `${k}=${String(v)}`).toBe("LEASE_EXPIRED");
    }
    expect(evaluateEnvelope(e, null, t0 + 4999).kind).toBe("CURRENT");
  });
});

describe("gate: regression and ordering, by structure not message text (FE-22/FE-32)", () => {
  const accepted = (name: string) => { const e = load(name); const g = evaluateEnvelope(e, null, at(e)); if (g.kind === "WITHHELD") throw new Error("setup"); return evaluateDetailed(e, null, at(e)).snap!; };
  it("lower sequence, same sequence with a different head, other archive, older verifiedAt are REGRESSION", () => {
    const e = cur(); const prev = accepted("current"); const t = at(e);
    expect(withheld(evaluateEnvelope(mutate(e, (b) => { b.freshness.sequence -= 1; b.checkpoint.anchoredSequence -= 1; }), prev, t))).toBe("REGRESSION");
    expect(withheld(evaluateEnvelope(mutate(e, (b) => { b.freshness.headHash = "f".repeat(64); }), prev, t))).toBe("REGRESSION");
    expect(withheld(evaluateEnvelope(mutate(e, (b) => { b.freshness.archiveId = "other"; }), prev, t))).toBe("REGRESSION");
    expect(withheld(evaluateEnvelope(mutate(e, (b) => { b.freshness.verifiedAt = "2026-10-22T08:17:55Z"; }), prev, t))).toBe("REGRESSION");
  });
  it("a removed event or removed unit or lower decision version is REGRESSION", () => {
    const e = cur(); const prev = accepted("current"); const t = at(e);
    expect(withheld(evaluateEnvelope(mutate(e, (b) => { const u = b.units.find((x: any) => x.events.length); u.events.pop(); }), prev, t))).toBe("REGRESSION");
    expect(withheld(evaluateEnvelope(mutate(e, (b) => { b.units.pop(); }), prev, t))).not.toBe("CURRENT");
    expect(withheld(evaluateEnvelope(mutate(e, (b) => { const pol = Object.keys(b.decisions["MTR-26001"])[0]; b.decisions["MTR-26001"][pol].current.version -= 1; }), prev, t))).toBe("REGRESSION");
  });
  it("the regression verdict does not depend on any message text", () => {
    const e = cur(); const prev = accepted("current");
    const g = evaluateEnvelope(mutate(e, (b) => { b.freshness.sequence -= 1; b.checkpoint.anchoredSequence -= 1; }), prev, at(e));
    expect(g.kind).toBe("WITHHELD");
    if (g.kind === "WITHHELD") { expect(g.cause).toBe("REGRESSION"); (g as any).reason = "totally different words"; expect(g.cause).toBe("REGRESSION"); }
  });
  it("FE-19/20/21 tracker: CURRENT -> PREFIX_ONLY -> WITHHELD -> PREFIX_ONLY keeps the watermark and never reuses a view", () => {
    const tr = new GateTracker(); const c = cur(); const p = load("prefix_only");
    expect(tr.evaluate(c, at(c)).kind).toBe("CURRENT");
    expect(tr.evaluate(p, at(p)).kind).toBe("SEGREGATED");
    const w = tr.evaluate(load("anchor_invalid"));
    expect(w.kind).toBe("WITHHELD");
    if (w.kind === "WITHHELD") { expect(w.lastAccepted?.sequence).toBe(p.body.freshness.sequence); expect(w.reason).toMatch(/historical, not currently verified/); expect(JSON.stringify(w)).not.toMatch(/MTR-/); }
    expect(tr.evaluate(p, at(p)).kind).toBe("SEGREGATED");
  });
  it("FE-32 an older CURRENT arriving after a newer PREFIX_ONLY is dropped as REGRESSION", () => {
    const tr = new GateTracker(); const c = cur(); const p = load("prefix_only");
    expect(tr.evaluate(p, at(p)).kind).toBe("SEGREGATED");
    expect(withheld(tr.evaluate(c, at(c)))).toBe("REGRESSION");
  });
  it("WITHHELD output and tracker state never carry a motor id, finding or action", () => {
    const tr = new GateTracker(); const c = cur(); tr.evaluate(c, at(c));
    for (const env of [load("anchor_invalid"), load("verifying"), load("invalid_request"), mutate(c, (b) => { delete b.checkpoint; })]) {
      const g = tr.evaluate(env, at(c)); expect(g.kind).toBe("WITHHELD");
      expect(JSON.stringify(g)).not.toMatch(/MTR-|RECALL_HOLD|RELEASE_ELIGIBLE|EXCLUDED|Release eligible/);
    }
    expect(tr.transport(" HTTP 0.").kind).toBe("WITHHELD");
  });
});

describe("architecture guards (FE-ARCH-1/2)", () => {
  const files = (dir: string): string[] => readdirSync(dir).flatMap((n) => { const p = join(dir, n); return statSync(p).isDirectory() ? files(p) : [p]; });
  const src = join(__dirname, "../../src");
  it("no standalone adapter classifies by message text or calls the legacy freshness check", () => {
    for (const f of files(src).filter((x) => /(passport|investigation|impact)Source\.ts$/.test(x))) {
      const text = readFileSync(f, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
      expect(text, f).not.toMatch(/\/regression\/i|verifyFreshness|\.test\(message\)|e\.message\b/);
    }
  });
  it("only src/contract may treat an action as current clearance", () => {
    for (const f of files(src).filter((x) => /(passport|investigation|impact)Source\.ts$/.test(x))) expect(readFileSync(f, "utf8").replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, ""), f).not.toMatch(/currentReleaseEligible|RELEASE_ELIGIBLE/);
  });
});
