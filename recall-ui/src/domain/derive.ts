import type { Comparison, Component, Decision, Finding, Lot, PolicyDecisions, RecallSnapshot, Unit } from "./types";

export const POLICY_LABEL: Record<string, string> = {
  "RC-009/P1": "P1 current installation",
  "RC-009/P2": "P2 operating history + damage inspection",
};

export function unitDecision(s: RecallSnapshot, unitId: string, policyId: string): PolicyDecisions | undefined {
  return s.decisions[unitId]?.[policyId];
}

export interface Counts {
  total: number;
  byFinding: Record<Finding, number>;
  hold: number;
  release: number;
  review: number;
}

/** Tallies of engine outputs. No classification: it only counts what the engine said. */
export function countDecisions(s: RecallSnapshot, policyId: string): Counts {
  const c: Counts = { total: 0, byFinding: { AFFECTED: 0, UNRESOLVED: 0, EXCLUDED_WITH_EVIDENCE: 0 }, hold: 0, release: 0, review: 0 };
  for (const u of s.units) {
    const d = unitDecision(s, u.unitId, policyId)?.current;
    if (!d) continue;
    c.total++;
    c.byFinding[d.evidenceFinding]++;
    if (d.operationalAction === "RECALL_HOLD") c.hold++;
    else c.release++;
    if (d.reviewRequired) c.review++;
  }
  return c;
}

export type SafetyClass = "FALSE_RELEASE" | "CORRECT_RELEASE" | "OVER_CAUTIOUS_HOLD" | "HELD_TRUTH_AFFECTED" | "NO_TRUTH";

export interface SafetyView {
  cls: SafetyClass;
  label: string;
  detail: string;
}

/**
 * Compares an engine decision with the SYNTHETIC ground truth of a fixture (P1 only).
 * Only used to show the safety improvement; the engine never sees the truth.
 */
export function safetyAgainstTruth(d: Decision, truth: "AFFECTED" | "UNAFFECTED" | undefined): SafetyView {
  if (!truth) return { cls: "NO_TRUTH", label: "No synthetic truth", detail: "This fixture carries no synthetic ground truth." };
  const released = d.operationalAction === "RELEASE_ELIGIBLE";
  if (released && truth === "AFFECTED") return { cls: "FALSE_RELEASE", label: "False release", detail: "Released although the synthetic truth is affected." };
  if (released) return { cls: "CORRECT_RELEASE", label: "Correct release", detail: "Released and the synthetic truth is unaffected." };
  if (truth === "UNAFFECTED") return { cls: "OVER_CAUTIOUS_HOLD", label: "Over-cautious hold", detail: "Held although the synthetic truth is unaffected. Costs a manual check, not safety." };
  return { cls: "HELD_TRUTH_AFFECTED", label: "Held, truth affected", detail: "Held and the synthetic truth is affected." };
}

export function isFalseRelease(c: Comparison, which: "legacy" | "current"): boolean {
  return safetyAgainstTruth(c[which], c.syntheticGroundTruth?.trueP1Finding).cls === "FALSE_RELEASE";
}

export interface GenealogyColumns {
  lots: Array<{ lotId: string; part: string; affected: boolean; supplier: string | null }>;
  components: Component[];
  unit: Unit;
}

/** Everything one motor's genealogy graph needs; lots come only from this motor's installs. */
export function genealogyFor(s: RecallSnapshot, unitId: string): GenealogyColumns | undefined {
  const unit = s.units.find((u) => u.unitId === unitId);
  if (!unit) return undefined;
  const components = s.components.filter((c) => c.unitId === unitId);
  const seen = new Set<string>();
  const lots: GenealogyColumns["lots"] = [];
  for (const c of components) {
    if (!c.lot || seen.has(c.lot)) continue;
    seen.add(c.lot);
    const meta = s.lots.find((l) => l.lotId === c.lot);
    lots.push({ lotId: c.lot, part: c.part ?? meta?.part ?? "?", affected: meta?.affected ?? false, supplier: meta?.supplier ?? null });
  }
  return { lots, components, unit };
}

export interface LotInvestigation {
  lot: Lot;
  rows: Array<{ unit: Unit; components: Component[]; decision: Decision | undefined }>;
}

/** Motors that ever had this lot installed, with the engine's current decision under the chosen policy. */
export function investigateLot(s: RecallSnapshot, lotId: string, policyId: string): LotInvestigation | undefined {
  const lot = s.lots.find((l) => l.lotId === lotId);
  if (!lot) return undefined;
  const rows = s.units
    .map((unit) => ({
      unit,
      components: s.components.filter((c) => c.unitId === unit.unitId && c.lot === lotId),
      decision: unitDecision(s, unit.unitId, policyId)?.current,
    }))
    .filter((r) => r.components.length > 0);
  return { lot, rows };
}

/** Event ids cited by a decision that are missing from the unit's event log (incomplete evidence). */
export function missingEvidence(d: Decision, unit: Unit): string[] {
  const have = new Set(unit.events.map((e) => e.eventId));
  return d.evidenceEventIds.filter((id) => !have.has(id));
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  return iso.replace("T", " ").replace(/:00Z$/, "Z").replace(/Z$/, " UTC");
}
