import { describe, expect, it } from "vitest";
import { countDecisions, genealogyFor, investigateLot, isFalseRelease, missingEvidence, safetyAgainstTruth } from "../../src/domain/derive";
import { realSnapshot } from "./helpers";

const P1 = "RC-009/P1";

describe("derived views", () => {
  const s = realSnapshot();

  it("counts add up to the engine's decisions", () => {
    const c = countDecisions(s, P1);
    expect(c.total).toBe(s.units.length);
    expect(c.byFinding.AFFECTED + c.byFinding.UNRESOLVED + c.byFinding.EXCLUDED_WITH_EVIDENCE).toBe(c.total);
    expect(c.hold + c.release).toBe(c.total);
    // release iff excluded: the engine's own invariant, never re-decided by the UI
    expect(c.release).toBe(c.byFinding.EXCLUDED_WITH_EVIDENCE);
  });

  it("classifies against synthetic truth", () => {
    const d = (a: string) => ({ operationalAction: a }) as any;
    expect(safetyAgainstTruth(d("RELEASE_ELIGIBLE"), "AFFECTED").cls).toBe("FALSE_RELEASE");
    expect(safetyAgainstTruth(d("RELEASE_ELIGIBLE"), "UNAFFECTED").cls).toBe("CORRECT_RELEASE");
    expect(safetyAgainstTruth(d("RECALL_HOLD"), "UNAFFECTED").cls).toBe("OVER_CAUTIOUS_HOLD");
    expect(safetyAgainstTruth(d("RECALL_HOLD"), "AFFECTED").cls).toBe("HELD_TRUTH_AFFECTED");
    expect(safetyAgainstTruth(d("RECALL_HOLD"), undefined).cls).toBe("NO_TRUTH");
  });

  it("case 06: the original engine falsely releases, the current engine does not", () => {
    const rows = s.comparison.filter((c) => c.policyId === P1);
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.filter((r) => isFalseRelease(r, "legacy")).length).toBeGreaterThan(0);
    expect(rows.filter((r) => isFalseRelease(r, "current")).length).toBe(0);
  });

  it("builds genealogy and lot investigations from install records", () => {
    const g = genealogyFor(s, "case-06")!;
    expect(g.components.length).toBeGreaterThan(0);
    expect(g.lots.every((l) => g.components.some((c) => c.lot === l.lotId))).toBe(true);
    const inv = investigateLot(s, "BR-204", P1)!;
    expect(inv.lot.affected).toBe(true);
    expect(inv.rows.every((r) => r.components.every((c) => c.lot === "BR-204"))).toBe(true);
    expect(investigateLot(s, "NOPE", P1)).toBeUndefined();
  });

  it("flags cited events missing from the event log", () => {
    const unit = s.units.find((u) => u.unitId === "case-01")!;
    const d = s.decisions["case-01"][P1].current;
    expect(missingEvidence(d, unit)).toEqual([]);
    expect(missingEvidence({ ...d, evidenceEventIds: [...d.evidenceEventIds, "GHOST-1"] }, unit)).toEqual(["GHOST-1"]);
  });
});
