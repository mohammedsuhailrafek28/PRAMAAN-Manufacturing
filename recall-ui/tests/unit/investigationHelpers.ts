import demo from "../../public/data/investigation-demo.json";
import type { RecallSnapshot } from "../../src/domain/types";
import { validateSnapshot } from "../../src/domain/validate";
import { withStrictCurrent } from "./helpers";

export type StageId = "before" | "after";
interface DemoDoc { origin: Record<string, string>; sharedAuthoredSource: string; stages: Array<{ id: string; snapshot: unknown }> }
const doc = demo as unknown as DemoDoc;

export const demoOrigin = doc.origin;
export const SHARED_SOURCE = doc.sharedAuthoredSource;
export const SEEDED = Object.keys(doc.origin).filter((u) => doc.origin[u] === "SEEDED");

/** Captured synthetic scenario snapshot (unanchored), deep-cloned and validated per call. */
export function stage(id: StageId = "before"): RecallSnapshot {
  const s = doc.stages.find((x) => x.id === id);
  if (!s) throw new Error(`no stage ${id}`);
  return validateSnapshot(structuredClone(s.snapshot));
}

/** Keep only the given motors (a read-only filtered copy; used to build smaller cases). */
export function subset(snap: RecallSnapshot, ids: string[]): RecallSnapshot {
  const keep = new Set(ids);
  const s = structuredClone(snap);
  s.units = s.units.filter((u) => keep.has(u.unitId));
  s.decisions = Object.fromEntries(Object.entries(s.decisions).filter(([u]) => keep.has(u)));
  s.comparison = s.comparison.filter((c) => keep.has(c.unitId));
  s.components = s.components.filter((c) => keep.has(c.unitId));
  s.lineage = (s.lineage ?? []).filter((l) => keep.has(l.unitId));
  s.notifications = (s.notifications ?? []).filter((n) => keep.has(n.unitId));
  return s;
}

export const POLICY = "RC-026-014/P1";

export function freshStage(id: StageId = "before", now = Date.now(), sequence = 100): RecallSnapshot {
  const s = stage(id);
  s.freshness = { verifiedAt: new Date(now).toISOString(), maxAgeSeconds: 5, status: "VERIFIED_ANCHORED_SYNTHETIC", archiveId: "test-archive", sequence, headHash: `head-${sequence}` };
  return withStrictCurrent(s, sequence);
}

export function deepFreeze<T>(o: T): T {
  if (o && typeof o === "object" && !Object.isFrozen(o)) {
    Object.freeze(o);
    for (const v of Object.values(o as Record<string, unknown>)) deepFreeze(v);
  }
  return o;
}

/** Text that must never reach the workspace. */
export const FORBIDDEN = ["Aster Pump", "Coimbatore", "customer", "destination"];

/** All reason codes the pinned v3 engine can emit (from recall-engine/pramaan_recall/policy.py). */
export const ENGINE_REASON_CODES = [
  "AFFECTED_LOT_INSTALLED", "AMBIGUOUS_SLOT_ATTRIBUTION", "AS_BUILT_UNAFFECTED_LOT", "CORROBORATED_BY_VERIFICATION", "CURRENT_STATE_UNVERIFIED",
  "DAMAGE_INSPECTION_FAILED", "DAMAGE_INSPECTION_INVALID", "DAMAGE_INSPECTION_MISSING", "DAMAGE_INSPECTION_PASSED", "DOUBLE_OCCUPANCY",
  "EVENT_INTEGRITY_VIOLATION", "EVENT_ORDER_INTEGRITY", "EXPOSURE_REMEDIATED", "EXPOSURE_UNKNOWN", "GAP_BOUNDED_BY_VERIFICATION",
  "HISTORICAL_EXPOSURE_CONFIRMED", "HISTORY_GAP_NOT_RECOVERED_BY_VERIFICATION", "IRRELEVANT_SLOT_GAP", "LATE_CLAIM_RISK_DECREASING_NOT_APPLIED",
  "LATE_CLAIM_RISK_INCREASING", "LOT_LEVEL_SLOT_AMBIGUITY", "MATERIAL_CAPTURE_GAP", "NO_HISTORICAL_EXPOSURE", "NO_TRUSTED_BASELINE",
  "PRIOR_EXCLUSION_WITHDRAWN", "REMEDIATION_COMPLETENESS_UNCERTAIN", "REMOVAL_OBSERVATION_MISMATCH", "REMOVAL_RECORD_INCONSISTENT",
  "REMOVAL_SERIAL_IN_OTHER_SLOT", "REPLACED_WITH_UNAFFECTED_LOT", "SLOT_EMPTY", "SOURCE_SEQUENCE_GAP", "UNTRUSTED_AFFECTED_OBSERVATION",
  "UNTRUSTED_SOURCE_CLAIM", "VERIFIED_AFFECTED_LOT_PRESENT", "VERIFIED_STATE_MISMATCH", "VERIFIED_STATE_MISMATCH_RISK_DECREASING",
  "VERIFIED_UNAFFECTED_LOT", "WORK_ORDER_UNRECONCILED",
];
export const ENGINE_FLAGS = [
  "KNOWN_LIMITATION_LOT_LEVEL_SLOT_AMBIGUITY", "OUT_OF_SCOPE_UNTRUSTED_AFFECTED_OBSERVATION", "SLOT_RECORD_CONFLICT",
  "UNATTRIBUTABLE_UNTRUSTED_AFFECTED_OBSERVATION", "UNTRUSTED_AFFECTED_OBSERVATION_SUPERSEDED",
];
