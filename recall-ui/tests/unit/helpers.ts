import snapshot from "../../public/data/snapshot.json";
import type { RecallDataSource } from "../../src/data/RecallDataSource";
import type { RecallSnapshot } from "../../src/domain/types";
import { validateSnapshot } from "../../src/domain/validate";

/** The real exported snapshot (engine output over the synthetic fixtures), deep-cloned per call. */
export const realSnapshot = (): RecallSnapshot => structuredClone(snapshot) as unknown as RecallSnapshot;

export const sourceOf = (raw: unknown, label = "test source"): RecallDataSource => ({
  label,
  load: async () => validateSnapshot(raw),
});

/**
 * MIGRATED FIXTURE (see docs/UNIFIED_TEST_MIGRATIONS.md, M1): a legacy "fresh" envelope carried only
 * `freshness`. The unified gate requires the full strict-current metadata the H1/H2 backend emits, so the
 * fresh-snapshot helpers add an honest ANCHORED_CURRENT checkpoint and per-motor eligibility (cleared iff the
 * motor has decisions, every one is RELEASE_ELIGIBLE, and no notification obligation is outstanding).
 */
export function withStrictCurrent(s: RecallSnapshot, sequence: number): RecallSnapshot {
  s.checkpoint = { state: "ANCHORED_CURRENT", anchoredSequence: sequence, checkpointRequired: false, h2: "VERIFIED" };
  s.eligibility = Object.fromEntries(s.units.map((u) => {
    const ds = Object.values(s.decisions[u.unitId] ?? {});
    const ok = ds.length > 0 && ds.every((b) => b.current.operationalAction === "RELEASE_ELIGIBLE") && !s.notifications?.some((n) => n.unitId === u.unitId);
    return [u.unitId, { currentReleaseEligible: ok }];
  }));
  return s;
}
