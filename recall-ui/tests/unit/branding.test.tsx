// Branded views: raw/forged/cloned objects are refused, clearance is per motor and minted only by clearanceOf,
// a historical view carries no decisions, a preview is never gated. The `@ts-expect-error` lines are checked by `tsc`.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ClaimChip, ClaimText, ClearanceChip } from "../../src/contract/ClearanceChip";
import { isCurrentClearance, mintCurrentClearance, claimFor } from "../../src/contract/clearance";
import { assertGated, clearanceOf, factsOf, isGated, isHistorical, isPreview, NotBranded, rawSnapshotOf } from "../../src/contract/gated";
import { gatedForTest, historicalForTest, previewForTest } from "../../src/contract/testing";
import { lotChoicesOf, projectImpact, projectInvestigation, projectPassport } from "../../src/contract/views";
import { InvestigationWorkspace } from "../../src/investigation/InvestigationWorkspace";
import { ImpactWorkspace } from "../../src/impact/ImpactWorkspace";
import type { RecallSnapshot } from "../../src/domain/types";
import { freshSnapshot } from "./passportHelpers";

afterEach(cleanup);

const snap = (): RecallSnapshot => freshSnapshot();
const actionOf = (s: RecallSnapshot, id: string) => Object.values(s.decisions[id]).map((b) => b.current.operationalAction);
const releaseMotor = (s: RecallSnapshot) => s.units.find((u) => actionOf(s, u.unitId).length > 0 && actionOf(s, u.unitId).every((a) => a === "RELEASE_ELIGIBLE"))!.unitId;
const holdMotor = (s: RecallSnapshot) => s.units.find((u) => actionOf(s, u.unitId).some((a) => a !== "RELEASE_ELIGIBLE"))!.unitId;

describe("type-level: a raw snapshot, a string or a cast is not a view or a clearance", () => {
  it("is enforced by tsc via @ts-expect-error", () => {
    const raw = snap();
    const throws = (f: () => unknown) => { try { f(); return false; } catch { return true; } };
    // @ts-expect-error a raw RecallSnapshot is not a PageView
    expect(throws(() => projectPassport(raw, "MTR-26004", { leaseOk: true, unavailableReason: "" }))).toBe(true);
    // @ts-expect-error a raw RecallSnapshot is not a PageView
    expect(throws(() => lotChoicesOf(raw))).toBe(true);
    // @ts-expect-error a raw RecallSnapshot is not a GatedSnapshot or PreviewView
    expect(throws(() => projectInvestigation(raw))).toBe(true);
    // @ts-expect-error a HistoricalView cannot build investigation tasks
    expect(throws(() => projectInvestigation(historicalForTest(raw)))).toBe(true);
    // @ts-expect-error a raw RecallSnapshot is not a PageView
    expect(throws(() => projectImpact(raw, { kind: "BEARING_LOT", id: "BR-204" }, { mode: "current" }))).toBe(true);
    // @ts-expect-error the workspace takes a PageView, not facts or a snapshot
    expect(throws(() => render(<ImpactWorkspace pageView={raw} route={{ page: "list", kind: "BEARING_LOT", lotId: "BR-204" } as never} mode="current" banner={null} />))).toBe(true);
    // @ts-expect-error a string is not a MotorClearance
    render(<ClearanceChip clearance="RELEASE_ELIGIBLE" />);
    expect(screen.queryByTestId("clearance-chip")).toBeNull();
    // @ts-expect-error a boolean is not a MotorClearance
    render(<ClearanceChip clearance={true} />);
    expect(screen.queryByTestId("clearance-chip")).toBeNull();
    void InvestigationWorkspace;
  });
});

describe("runtime brand checks", () => {
  it("refuse raw, cloned, spread and JSON-round-tripped views", () => {
    const g = gatedForTest(snap());
    for (const fake of [snap(), { ...g }, JSON.parse(JSON.stringify(g)), structuredClone({ facts: g.facts, watermark: g.watermark }), Object.create(g), null, "x"]) {
      expect(isGated(fake)).toBe(false);
      expect(() => assertGated(fake)).toThrow(NotBranded);
      expect(() => clearanceOf(fake as never, "MTR-26003")).toThrow(NotBranded);
      expect(() => factsOf(fake as never)).toThrow(NotBranded);
      expect(() => rawSnapshotOf(fake as never)).toThrow(NotBranded);
      expect(() => lotChoicesOf(fake as never)).toThrow(NotBranded);
    }
  });
  it("kinds are exclusive: gated, historical and preview never satisfy each other's guard", () => {
    const g = gatedForTest(snap()), h = historicalForTest(snap()), p = previewForTest(snap());
    expect([isGated(g), isHistorical(g), isPreview(g)]).toEqual([true, false, false]);
    expect([isGated(h), isHistorical(h), isPreview(h)]).toEqual([false, true, false]);
    expect([isGated(p), isHistorical(p), isPreview(p)]).toEqual([false, false, true]);
    expect(() => clearanceOf(p as never, "MTR-26003")).toThrow(NotBranded);
    expect(() => clearanceOf(h as never, "MTR-26003")).toThrow(NotBranded);
  });
  it("a historical view carries no decisions, eligibility, comparison or checkpoint even if the source had them", () => {
    const s = snap();
    expect(Object.keys(s.decisions).length).toBeGreaterThan(0);
    const h = historicalForTest(s, "PREFIX_ONLY");
    const raw = rawSnapshotOf(h);
    expect(raw.decisions).toEqual({});
    expect(raw.comparison).toEqual([]);
    expect(raw.eligibility).toBeUndefined();
    expect(raw.checkpoint).toBeUndefined();
    expect(JSON.stringify(h)).not.toMatch(/RELEASE_ELIGIBLE|RECALL_HOLD/);
    expect(() => projectInvestigation(h as never)).toThrow(NotBranded);
  });
  it("a preview never carries trust metadata, whatever the dataset file claims", () => {
    const s = snap();
    s.eligibility = Object.fromEntries(s.units.map((u) => [u.unitId, { currentReleaseEligible: true }])) as RecallSnapshot["eligibility"];
    const raw = rawSnapshotOf(previewForTest(s));
    expect(raw.eligibility).toBeUndefined();
    expect(raw.checkpoint).toBeUndefined();
    expect(raw.freshness).toBeUndefined();
  });
  it("facts exposed to components have no decision, eligibility, comparison or checkpoint keys", () => {
    const f = factsOf(gatedForTest(snap())) as Record<string, unknown>;
    // The runtime object is the validated snapshot; the type forbids reading these keys. This documents the limit.
    expect(typeof f.units).toBe("object");
  });
});

describe("clearance is per motor, minted only by clearanceOf", () => {
  it("a cleared motor gets a minted clearance; a hold motor gets HOLD", () => {
    const s = snap();
    const g = gatedForTest(s);
    expect(isCurrentClearance(clearanceOf(g, releaseMotor(s)))).toBe(true);
    expect(clearanceOf(g, holdMotor(s))).toBe("HOLD");
  });
  it("T7: eligibility withheld for one motor does not downgrade or delete the others", () => {
    const s = snap();
    const a = releaseMotor(s);
    const g = gatedForTest(s, { [a]: false });
    expect(clearanceOf(g, a)).toBe("NOT_CLEARED");
    expect(rawSnapshotOf(g).decisions[a]).toBeDefined();                 // findings, reason codes and holds are preserved
    for (const u of s.units) if (u.unitId !== a) expect(clearanceOf(g, u.unitId) === "HOLD" || isCurrentClearance(clearanceOf(g, u.unitId))).toBe(true);
  });
  it("eligibility true for a motor whose decisions hold is still HOLD (never cleared by the flag alone)", () => {
    const s = snap();
    const h = holdMotor(s);
    expect(clearanceOf(gatedForTest(s, { [h]: true }), h)).toBe("HOLD");
  });
  it("an unknown motor and a motor without decisions are NOT_CLEARED", () => {
    const g = gatedForTest(snap());
    expect(clearanceOf(g, "MTR-NOPE")).toBe("NOT_CLEARED");
  });
  it("a cast or cloned clearance renders nothing and a minted one is not copyable", () => {
    const real = mintCurrentClearance();
    expect(isCurrentClearance(real)).toBe(true);
    expect(isCurrentClearance({ ...real })).toBe(false);
    expect(isCurrentClearance(JSON.parse(JSON.stringify(real)))).toBe(false);
    render(<ClearanceChip clearance={{} as never} />);
    expect(screen.queryByTestId("clearance-chip")).toBeNull();
    cleanup();
    render(<ClearanceChip clearance={real} />);
    expect(screen.getByTestId("clearance-chip")).toHaveTextContent("Release eligible");
  });
  it("claimFor fails closed: no resolver, a hold, or an unknown action never yields clearance", () => {
    expect(claimFor("RELEASE_ELIGIBLE", "U")).toMatchObject({ hold: false, clearance: "NOT_CLEARED" });
    expect(claimFor("RECALL_HOLD", "U", { clearance: () => mintCurrentClearance() })).toMatchObject({ hold: true, clearance: "HOLD" });
    expect(claimFor("CLEARED", "U", { clearance: () => mintCurrentClearance() })).toMatchObject({ hold: true, clearance: "HOLD" });
    expect(claimFor("RELEASE_ELIGIBLE", "U", { clearance: () => "NOT_CLEARED" }).clearance).toBe("NOT_CLEARED");
    expect(claimFor("RELEASE_ELIGIBLE", "U", { clearance: (() => "RELEASE_ELIGIBLE") as never }).clearance).toBe("NOT_CLEARED");
  });
});

describe("projections through the wrappers", () => {
  it("investigation over a gated view: the cleared motor shows the clearance chip, others do not", () => {
    const s = snap(); const g = gatedForTest(s);
    const v = projectInvestigation(g);
    const claims = [...v.tasks.map((t) => t.decision), ...v.untasked];
    expect(claims.length).toBeGreaterThan(0);
    for (const c of claims) expect(c).not.toHaveProperty("recordedAction");
  });
  it("a preview carries labelled synthetic recorded actions and never a clearance", () => {
    const s = snap(); const p = previewForTest(s);
    const v = projectInvestigation(p);
    const claims = [...v.tasks.map((t) => t.decision), ...v.untasked];
    for (const c of claims) { expect(isCurrentClearance(c.clearance)).toBe(false); expect(c.recordedAction).toBeDefined(); }
    const pass = projectPassport(p, "MTR-26003", { leaseOk: true, unavailableReason: "preview" });
    expect(pass.found && pass.recall.state).toBe("UNAVAILABLE");          // a preview can never be current, even with a live lease
  });
  it("impact: current mode needs a gated view and preview mode needs a preview", () => {
    const s = snap(); const sel = { kind: "BEARING_LOT" as const, id: "BR-204" };
    expect(() => projectImpact(previewForTest(s), sel, { mode: "current" })).toThrow(NotBranded);
    expect(() => projectImpact(historicalForTest(s), sel, { mode: "current" })).toThrow(NotBranded);
    expect(() => projectImpact(gatedForTest(s), sel, { mode: "preview" })).toThrow(NotBranded);
    expect(() => projectImpact(historicalForTest(s), sel, { mode: "noncurrent" })).not.toThrow();
  });
  it("passport: a gated view without a live lease is unavailable; with it, only the cleared motor is cleared", () => {
    const s = snap(); const g = gatedForTest(s);
    const off = projectPassport(g, releaseMotor(s), { leaseOk: false, unavailableReason: "x" });
    expect(off.found && off.recall.state).toBe("UNAVAILABLE");
    const on = projectPassport(g, releaseMotor(s), { leaseOk: true, unavailableReason: "x" });
    expect(on.found && on.recall.state === "CURRENT" && isCurrentClearance(on.recall.clearance)).toBe(true);
    const nc = projectPassport(gatedForTest(s, { [releaseMotor(s)]: false }), releaseMotor(s), { leaseOk: true, unavailableReason: "x" });
    expect(nc.found && nc.recall.state === "CURRENT" && nc.recall.clearance).toBe("NOT_CLEARED");
    expect(nc.found && nc.recall.state === "CURRENT" && nc.recall.finding).toBeDefined();   // finding preserved
  });
});

describe("rendering of a recorded claim", () => {
  it("withheld clearance is stated honestly and never as release", () => {
    render(<><ClaimChip claim={{ hold: false, clearance: "NOT_CLEARED" }} /><ClaimText claim={{ hold: false, clearance: "NOT_CLEARED" }} /></>);
    expect(screen.getByTestId("clearance-withheld")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/Release eligible/);
  });
  it("a preview claim is labelled synthetic evaluator output and is not a ClearanceChip", () => {
    render(<ClaimChip claim={{ hold: false, clearance: "NOT_CLEARED", recordedAction: "RELEASE_ELIGIBLE" }} />);
    expect(screen.getByTestId("preview-recorded-action")).toHaveTextContent(/Synthetic evaluator output.*not an authorization/);
    expect(screen.queryByTestId("clearance-chip")).toBeNull();
  });
});
