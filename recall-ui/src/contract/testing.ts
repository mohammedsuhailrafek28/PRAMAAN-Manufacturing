// TEST-ONLY constructors for branded views. Production code must not import this file (static test).
// They stand in for what the shared gate produces, so page tests can drive pages with views of each kind.
import type { RecallSnapshot } from "../domain/types";
import { makeGated, makeHistorical, makePreview, type GatedSnapshot, type HistoricalView, type PreviewView, type Watermark } from "./gated";

const mark = (snap: RecallSnapshot): Watermark => ({
  archiveId: snap.freshness?.archiveId ?? "TEST-ARCHIVE", sequence: snap.freshness?.sequence ?? 1, verifiedAt: snap.freshness?.verifiedAt ?? "2026-01-01T00:00:00Z",
});

/** Eligibility defaults to what an honest backend reports: a motor is cleared iff it has decisions and every one is RELEASE_ELIGIBLE. */
export function gatedForTest(snap: RecallSnapshot, eligibility?: Record<string, boolean>): GatedSnapshot {
  const elig: Record<string, { currentReleaseEligible: boolean }> = {};
  for (const u of snap.units) {
    const ds = Object.values(snap.decisions[u.unitId] ?? {});
    const honest = ds.length > 0 && ds.every((b) => b.current.operationalAction === "RELEASE_ELIGIBLE");
    elig[u.unitId] = { currentReleaseEligible: eligibility?.[u.unitId] ?? honest };
  }
  return makeGated({ ...snap, eligibility: elig as RecallSnapshot["eligibility"] }, mark(snap));
}

export const historicalForTest = (snap: RecallSnapshot, cause: "PREFIX_ONLY" | "UNANCHORED" = "UNANCHORED", reason = "Historical evidence only."): HistoricalView =>
  makeHistorical(cause, snap, mark(snap), reason);

export const previewForTest = (snap: RecallSnapshot, label = "Preview: synthetic test data"): PreviewView => makePreview(snap, label);
