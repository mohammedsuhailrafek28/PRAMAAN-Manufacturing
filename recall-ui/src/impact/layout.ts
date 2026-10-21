// Deterministic layered layout: raw-material claim | bearing lot | manufacture | component | motor | shipment.
// Position carries no meaning beyond grouping: rows are grouped by motor, ordered by the engine's finding
// (when recall status is current) and then by identifier.
import type { GNode, ImpactGraph, NodeKind } from "./projection";

export interface Box { x: number; y: number; w: number; h: number }
export interface Layout { pos: Map<string, Box>; width: number; height: number; columns: Array<{ title: string; x: number }> }

export const NODE_W = 196;
export const NODE_H = 52;
const COL_GAP = 244;
const ROW = 66;
const TOP = 44;
const COLUMN: Record<NodeKind, number> = { RAW_LOT: 0, BEARING_LOT: 1, MANUFACTURE: 2, COMPONENT: 3, OBSERVATION: 3, MOTOR: 4, SHIPMENT: 5 };
export const COLUMN_TITLES = ["Raw-material claim", "Bearing lot", "Manufacture record", "Installed component", "Motor", "Recorded shipment"];
const FINDING_RANK: Record<string, number> = { AFFECTED: 0, UNRESOLVED: 1, EXCLUDED_WITH_EVIDENCE: 2 };
const cmp = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

/** Deterministic motor order: engine finding (when shown), then identifier. */
export const motorOrder = (a: GNode, b: GNode): number => (FINDING_RANK[a.status?.finding ?? ""] ?? 3) - (FINDING_RANK[b.status?.finding ?? ""] ?? 3) || cmp(a.id, b.id);

export function layoutGraph(g: ImpactGraph, visible: ReadonlySet<string> | null): Layout {
  const nodes = g.nodes.filter((n) => !visible || visible.has(n.id));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const edges = g.edges.filter((e) => byId.has(e.from) && byId.has(e.to));
  const parentsOf = new Map<string, string[]>();
  const childrenOf = new Map<string, string[]>();
  for (const e of edges) {
    (parentsOf.get(e.to) ?? parentsOf.set(e.to, []).get(e.to)!).push(e.from);
    (childrenOf.get(e.from) ?? childrenOf.set(e.from, []).get(e.from)!).push(e.to);
  }
  const rowOf = new Map<string, number>();
  let row = 0;
  const motors = nodes.filter((n) => n.kind === "MOTOR").sort(motorOrder);
  for (const m of motors) {
    const members = (parentsOf.get(m.id) ?? []).map((id) => byId.get(id)!).sort((a, b) => cmp(a.slot ?? "~", b.slot ?? "~") || cmp(a.id, b.id));
    const start = row;
    members.forEach((c, i) => {
      rowOf.set(c.id, start + i);
      for (const p of parentsOf.get(c.id) ?? []) if (byId.get(p)?.kind === "MANUFACTURE" && !rowOf.has(p)) rowOf.set(p, start + i);
    });
    const span = Math.max(1, members.length);
    rowOf.set(m.id, start + (span - 1) / 2);
    for (const s of childrenOf.get(m.id) ?? []) if (byId.get(s)?.kind === "SHIPMENT") rowOf.set(s, start + (span - 1) / 2);
    row += span;
  }
  // manufacture records and anything else with no motor yet (for example manufactured but never installed)
  for (const n of nodes.filter((x) => x.kind === "MANUFACTURE" || x.kind === "COMPONENT" || x.kind === "SHIPMENT").sort((a, b) => cmp(a.id, b.id))) {
    if (!rowOf.has(n.id)) rowOf.set(n.id, row++);
  }
  // lots and raw-material claims sit at the mean row of what they feed
  for (const kind of ["BEARING_LOT", "RAW_LOT"] as NodeKind[]) {
    for (const n of nodes.filter((x) => x.kind === kind).sort((a, b) => cmp(a.id, b.id))) {
      const kids = (childrenOf.get(n.id) ?? []).map((id) => rowOf.get(id)).filter((r): r is number => r !== undefined);
      rowOf.set(n.id, kids.length ? kids.reduce((a, b) => a + b, 0) / kids.length : row++);
    }
  }
  const pos = new Map<string, Box>();
  let maxRow = 0;
  for (const n of nodes) {
    const r = rowOf.get(n.id) ?? 0;
    maxRow = Math.max(maxRow, r);
    pos.set(n.id, { x: 12 + COLUMN[n.kind] * COL_GAP, y: TOP + r * ROW, w: NODE_W, h: NODE_H });
  }
  return {
    pos, width: 12 + 5 * COL_GAP + NODE_W + 12, height: TOP + maxRow * ROW + NODE_H + 24,
    columns: COLUMN_TITLES.map((title, i) => ({ title, x: 12 + i * COL_GAP })),
  };
}

export const nodesInLayout = (g: ImpactGraph, l: Layout): GNode[] => g.nodes.filter((n) => l.pos.has(n.id));
