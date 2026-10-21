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
