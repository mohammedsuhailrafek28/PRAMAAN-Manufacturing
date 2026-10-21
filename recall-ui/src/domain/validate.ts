import type { RecallSnapshot } from "./types";

export interface ValidationIssue {
  path: string;
  message: string;
}
export class SnapshotValidationError extends Error {
  issues: ValidationIssue[];
  constructor(issues: ValidationIssue[]) {
    super(`Invalid recall snapshot (${issues.length} problem${issues.length === 1 ? "" : "s"})`);
    this.issues = issues;
  }
}

const FINDINGS = ["AFFECTED", "UNRESOLVED", "EXCLUDED_WITH_EVIDENCE"];
const ACTIONS = ["RECALL_HOLD", "RELEASE_ELIGIBLE"];
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

/** Structural check plus the engine's own invariants. A contradictory decision is refused, not displayed. */
export function validateSnapshot(raw: unknown): RecallSnapshot {
  const issues: ValidationIssue[] = [];
  const bad = (path: string, message: string) => issues.push({ path, message });
  if (!isObj(raw)) throw new SnapshotValidationError([{ path: "$", message: "snapshot is not an object" }]);
  if (raw.schemaVersion !== 1) bad("schemaVersion", `expected 1, got ${String(raw.schemaVersion)}`);
  for (const k of ["units", "components", "lots", "policies", "comparison"]) {
    if (!Array.isArray(raw[k])) bad(k, "missing or not a list");
  }
  for (const k of ["provenance", "recall", "decisions"]) if (!isObj(raw[k])) bad(k, "missing or not an object");
  if (issues.length) throw new SnapshotValidationError(issues);

  const policies = (raw.policies as Array<{ policyId?: string }>).map((p) => p.policyId as string);
  const decisions = raw.decisions as Record<string, Record<string, unknown>>;

  const checkDecision = (d: unknown, path: string) => {
    if (!isObj(d)) return bad(path, "decision is not an object");
    const okFinding = FINDINGS.includes(d.evidenceFinding as string);
    const okAction = ACTIONS.includes(d.operationalAction as string);
    if (!okFinding) bad(`${path}.evidenceFinding`, `unknown finding ${String(d.evidenceFinding)}`);
    if (!okAction) bad(`${path}.operationalAction`, `unknown action ${String(d.operationalAction)}`);
    if (typeof d.reviewRequired !== "boolean") bad(`${path}.reviewRequired`, "must be boolean");
    if (!Array.isArray(d.reasonCodes)) bad(`${path}.reasonCodes`, "must be a list");
    if (typeof d.decisionId !== "string") bad(`${path}.decisionId`, "missing");
    if (!isObj(d.slots)) bad(`${path}.slots`, "missing");
    // Engine invariants: release iff excluded; an unresolved finding always needs review.
    if (okFinding && okAction) {
      const release = d.evidenceFinding === "EXCLUDED_WITH_EVIDENCE";
      if (release !== (d.operationalAction === "RELEASE_ELIGIBLE")) bad(path, "finding and operational action contradict each other");
      if (d.evidenceFinding === "UNRESOLVED" && d.reviewRequired !== true) bad(path, "UNRESOLVED without review required");
    }
  };

  for (const [i, u] of (raw.units as Array<Record<string, unknown>>).entries()) {
    const id = u.unitId;
    if (typeof id !== "string" || !Array.isArray(u.events)) {
      bad(`units[${i}]`, "needs unitId and events");
      continue;
    }
    const byPolicy = decisions[id];
    if (!isObj(byPolicy)) {
      bad(`decisions.${id}`, "no decisions for this unit");
      continue;
    }
    for (const pid of policies) {
      const pd = byPolicy[pid] as { current?: unknown; history?: unknown[] } | undefined;
      if (!pd) {
        bad(`decisions.${id}.${pid}`, "missing policy decision");
        continue;
      }
      checkDecision(pd.current, `decisions.${id}.${pid}.current`);
      if (!Array.isArray(pd.history) || pd.history.length === 0) bad(`decisions.${id}.${pid}.history`, "empty history");
      else pd.history.forEach((h, j) => checkDecision(h, `decisions.${id}.${pid}.history[${j}]`));
    }
  }
  if (issues.length) throw new SnapshotValidationError(issues);
  return raw as unknown as RecallSnapshot;
}
