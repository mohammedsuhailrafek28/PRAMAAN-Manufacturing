import demo from "../../public/data/impact-demo.json";
import type { RecallSnapshot } from "../../src/domain/types";
import { validateSnapshot } from "../../src/domain/validate";
import { withStrictCurrent } from "./helpers";

export type DatasetId = "de" | "nde";
interface Doc { datasets: Array<{ id: string; origin: Record<string, { kind: string; note: string }>; snapshot: unknown }> }
const doc = demo as unknown as Doc;

export const origin = (id: DatasetId) => doc.datasets.find((d) => d.id === id)!.origin;

/** Captured synthetic dataset (unanchored), deep-cloned and validated per call. */
export function dataset(id: DatasetId = "de"): RecallSnapshot {
  const d = doc.datasets.find((x) => x.id === id);
  if (!d) throw new Error(`no dataset ${id}`);
  return validateSnapshot(structuredClone(d.snapshot));
}

export function freshDataset(id: DatasetId = "de", now = Date.now(), sequence = 100): RecallSnapshot {
  const s = dataset(id);
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

/** Text and identifiers that must never reach the graph. */
export const FORBIDDEN = ["Aster Pump", "Coimbatore", "customer", "destination", "OP-ASSEMBLY", "OP-REWORK", "OP-OBSERVATION", "QA-INDEPENDENT", "SUPPLIER-INTAKE", "DISPATCH-09", "MES-SYSTEM"];
