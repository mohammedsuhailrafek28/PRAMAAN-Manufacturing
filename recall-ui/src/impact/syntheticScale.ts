// AUTHORED stress data for the preview and tests only. It clones the motors of an existing snapshot under
// new identifiers so the graph can be exercised with thousands of nodes. Cloned decisions are copies of
// the template motors' engine decisions with identifiers rewritten; they are NOT new evaluator output.
// Never used by the live adapter.
import type { RecallSnapshot } from "../domain/types";

export const CLONE_PREFIX = "MTR-S";

export function scaleSnapshot(base: RecallSnapshot, totalMotors: number): { snap: RecallSnapshot; clones: string[] } {
  const snap = structuredClone(base);
  const templates = base.units.map((u) => u.unitId).sort();
  const clones: string[] = [];
  for (let i = base.units.length; i < totalMotors; i++) {
    const old = templates[i % templates.length];
    const next = `${CLONE_PREFIX}${String(i).padStart(5, "0")}`;
    const oldNum = old.replace(/^MTR-/, "");
    const rename = <T,>(value: T): T =>
      JSON.parse(JSON.stringify(value).split(old).join(next).split(`SHP-26-${oldNum}`).join(`SHP-S-${next.slice(CLONE_PREFIX.length)}`)) as T;
    const unit = base.units.find((u) => u.unitId === old)!;
    snap.units.push(rename(unit));
    snap.decisions[next] = rename(base.decisions[old]);
    snap.components.push(...base.components.filter((c) => c.unitId === old).map((c) => rename(c)));
    snap.lineage = [...(snap.lineage ?? []), ...(base.lineage ?? []).filter((l) => l.unitId === old).map((l) => rename(l))];
    snap.comparison.push(...base.comparison.filter((c) => c.unitId === old).map((c) => rename(c)));
    clones.push(next);
  }
  return { snap, clones };
}
