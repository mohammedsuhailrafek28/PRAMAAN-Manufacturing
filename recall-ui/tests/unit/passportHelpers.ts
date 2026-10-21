import preview from "../../public/data/passport-preview.json";
import type { RecallSnapshot } from "../../src/domain/types";
import { validateSnapshot } from "../../src/domain/validate";

/** Captured, seeded synthetic backend snapshot (unanchored), deep-cloned per call. */
export const previewSnapshot = (): RecallSnapshot => validateSnapshot(structuredClone(preview));

/** The same snapshot with server freshness metadata that verifyFreshness accepts at `now`. */
export function freshSnapshot(now = Date.now(), sequence = 100): RecallSnapshot {
  const s = previewSnapshot();
  s.freshness = { verifiedAt: new Date(now).toISOString(), maxAgeSeconds: 5, status: "VERIFIED_ANCHORED_SYNTHETIC", archiveId: "test-archive", sequence, headHash: `head-${sequence}` };
  return s;
}

export function deepFreeze<T>(o: T): T {
  if (o && typeof o === "object" && !Object.isFrozen(o)) {
    Object.freeze(o);
    for (const v of Object.values(o as Record<string, unknown>)) deepFreeze(v);
  }
  return o;
}

/** Strings that must never appear in passport content or in a QR payload. */
export const FORBIDDEN = [
  "Aster Pump", "Coimbatore", "SHP-26", "customer", "destination",
  "OP-ASSEMBLY", "OP-REWORK", "OP-OBSERVATION", "QA-INDEPENDENT", "SUPPLIER-INTAKE", "DISPATCH-09", "MES-SYSTEM",
];
