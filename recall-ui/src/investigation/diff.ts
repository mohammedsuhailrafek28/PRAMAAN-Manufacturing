// What changed between two accepted projections. Pure; shown so a reader can see tasks appear or
// disappear because the evaluator's decision changed, never because anyone closed them.
import type { InvestigationView, Task } from "./projection";

export interface ChangeEntry {
  taskId: string;
  unitId: string;
  cls: string;
  detail: string;
}
export interface ViewChanges {
  added: ChangeEntry[];
  removed: ChangeEntry[];
  reevaluated: ChangeEntry[];
}

const entry = (t: Task, detail: string): ChangeEntry => ({ taskId: t.taskId, unitId: t.unitId, cls: t.cls, detail });

export function diffViews(prev: InvestigationView, next: InvestigationView): ViewChanges {
  const before = new Map(prev.tasks.map((t) => [t.taskId, t]));
  const after = new Map(next.tasks.map((t) => [t.taskId, t]));
  const added: ChangeEntry[] = [], removed: ChangeEntry[] = [], reevaluated: ChangeEntry[] = [];
  for (const [id, t] of after) {
    const old = before.get(id);
    if (!old) added.push(entry(t, "newly listed by the evaluator"));
    else if (old.decision.decisionId !== t.decision.decisionId)
      reevaluated.push(entry(t, `still listed; decision re-evaluated (version ${old.decision.version ?? "?"} to ${t.decision.version ?? "?"})`));
  }
  for (const [id, t] of before) if (!after.has(id)) removed.push(entry(t, "no longer listed by the evaluator"));
  return { added, removed, reevaluated };
}

export const hasChanges = (c: ViewChanges | null): c is ViewChanges => !!c && c.added.length + c.removed.length + c.reevaluated.length > 0;
