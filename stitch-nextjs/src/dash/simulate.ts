// Recall blast-radius simulator: a pure, read-only traversal over an ImpactGraph that the existing genealogy projection already built
// from the ledger. It adds no data, no edge and no node of its own. It is a hypothetical investigation aid, never a recall decision.
import type { EdgeStyle, GEdge, GNode, ImpactGraph, MotorStatus } from "@/orig/impact/projection";

export const HYPOTHETICAL = "HYPOTHETICAL — INVESTIGATION ONLY";
/** CONFIRMED: every link on some path is a recorded ledger link. CLAIMED: at least one link is a recorded lot claim without a manufacture link. UNCONFIRMED: reachable only through conflicting or untrusted links; never counted as exposure. */
export type Reach = "CONFIRMED" | "CLAIMED" | "UNCONFIRMED";

export interface Exposure {
  motor: string; nodeId: string; reach: Reach;
  paths: string[][];            // node ids, start to motor, distinct simple paths (capped)
  pathsCapped: boolean;
  historical: boolean;          // every path crosses a link recorded as historical (for example a removed component)
  shipped: boolean;
  status: MotorStatus | null;   // the engine's own decision copied by the projection; null when withheld
}
export interface Gap { severity: string; message: string }
export interface Simulation {
  selection: { kind: string; id: string }; startId: string; found: boolean;
  exposures: Exposure[];        // CONFIRMED and CLAIMED, then UNCONFIRMED, each sorted by motor id
  exposedMotors: number;        // CONFIRMED + CLAIMED only
  gaps: Gap[];
  notLinked: string[];          // motors in the snapshot with no recorded path from the selection (absence of a record, not safety)
  decisionsShown: boolean;
  watermark: ImpactGraph["watermark"];
}

const MAX_PATHS = 6, MAX_DEPTH = 12, MAX_VISITS = 5000;
const RECORDED: ReadonlySet<EdgeStyle> = new Set<EdgeStyle>(["RECORDED"]);
const CLAIMING: ReadonlySet<EdgeStyle> = new Set<EdgeStyle>(["RECORDED", "LOT_CLAIM"]);
const ANY: ReadonlySet<EdgeStyle> = new Set<EdgeStyle>(["RECORDED", "LOT_CLAIM", "CONFLICT", "UNTRUSTED_CLAIM"]);

export const startNodeId = (kind: string, id: string) => (kind === "RAW_LOT" ? `raw:${id}` : `lot:${id}`);

/** Every simple path from `start` to a motor along edges of the allowed styles, following edge direction only. Cycles cannot loop; duplicates collapse. */
function walk(adj: Map<string, GEdge[]>, start: string, isMotor: (id: string) => boolean, allowed: ReadonlySet<EdgeStyle>) {
  const out = new Map<string, { paths: string[][]; capped: boolean; edgesOf: GEdge[][] }>();
  let visits = 0;
  const seen = new Set<string>();
  const dfs = (id: string, trail: string[], edges: GEdge[]) => {
    if (++visits > MAX_VISITS || trail.length > MAX_DEPTH) return;
    if (isMotor(id) && trail.length > 1) {
      const key = trail.join(">");
      const rec = out.get(id) ?? { paths: [], capped: false, edgesOf: [] };
      if (!seen.has(key)) { seen.add(key); if (rec.paths.length < MAX_PATHS) { rec.paths.push([...trail]); rec.edgesOf.push([...edges]); } else rec.capped = true; }
      out.set(id, rec);
    }
    for (const e of adj.get(id) ?? []) { if (!allowed.has(e.style) || trail.includes(e.to)) continue; trail.push(e.to); edges.push(e); dfs(e.to, trail, edges); trail.pop(); edges.pop(); }
  };
  dfs(start, [start], []);
  return out;
}

export function simulate(g: ImpactGraph, allMotors: string[]): Simulation {
  const startId = startNodeId(g.selection.kind, g.selection.id);
  const nodes = new Map<string, GNode>(g.nodes.map((n) => [n.id, n]));
  const found = g.knownSelection && nodes.has(startId);
  const adj = new Map<string, GEdge[]>();
  for (const e of g.edges) { if (!nodes.has(e.from) || !nodes.has(e.to)) continue; (adj.get(e.from) ?? adj.set(e.from, []).get(e.from)!).push(e); }
  const isMotor = (id: string) => nodes.get(id)?.kind === "MOTOR";
  const shipped = new Set(g.edges.filter((e) => e.kind === "MOTOR_SHIPMENT").map((e) => e.from));
  const exposures: Exposure[] = [];
  if (found) {
    const confirmed = walk(adj, startId, isMotor, RECORDED), claiming = walk(adj, startId, isMotor, CLAIMING), any = walk(adj, startId, isMotor, ANY);
    for (const [id, rec] of [...any.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
      const reach: Reach = confirmed.has(id) ? "CONFIRMED" : claiming.has(id) ? "CLAIMED" : "UNCONFIRMED";
      const best = (confirmed.get(id) ?? claiming.get(id) ?? rec);
      const edgesOf = (confirmed.get(id) ?? claiming.get(id) ?? rec).edgesOf;
      const n = nodes.get(id)!;
      exposures.push({ motor: n.unitId ?? n.label, nodeId: id, reach, paths: best.paths, pathsCapped: best.capped, historical: edgesOf.length > 0 && edgesOf.every((es) => es.some((e) => e.historical)), shipped: shipped.has(id), status: n.status });
    }
    const rank = { CONFIRMED: 0, CLAIMED: 1, UNCONFIRMED: 2 } as const;
    exposures.sort((a, b) => rank[a.reach] - rank[b.reach] || a.motor.localeCompare(b.motor));
  }
  const linked = new Set(exposures.map((x) => x.motor));
  const gaps: Gap[] = g.issues.filter((i) => i.severity !== "INFO").map((i) => ({ severity: i.severity, message: i.message }));
  return {
    selection: g.selection, startId, found, exposures, exposedMotors: exposures.filter((x) => x.reach !== "UNCONFIRMED").length, gaps,
    notLinked: found ? allMotors.filter((m) => !linked.has(m)).sort() : [], decisionsShown: g.recallStatus === "CURRENT", watermark: g.watermark,
  };
}

const REACH_TEXT: Record<Reach, string> = { CONFIRMED: "recorded link", CLAIMED: "via a recorded lot claim", UNCONFIRMED: "only via conflicting or untrusted links (not counted)" };
export const reachText = (r: Reach) => REACH_TEXT[r];

/** Plain-text investigation summary a person may copy. States what it is not. */
export function summaryText(s: Simulation, label: (id: string) => string): string {
  const L = [`${HYPOTHETICAL}`, `Simulated exposure of ${s.selection.kind === "RAW_LOT" ? "raw-material lot" : "lot"} ${s.selection.id}. This is not a recall decision, creates no evidence and changes no hold or release.`];
  if (!s.found) { L.push("The ledger has no record of this lot. Nothing was traversed."); return L.join("\n"); }
  L.push(`Ledger: sequence ${s.watermark.sequence ?? "not recorded"}, head ${s.watermark.headHash?.slice(0, 12) ?? "not recorded"}…, ${s.watermark.ledgerEvents} records.`);
  L.push(`Potentially exposed motors (recorded graph reachability): ${s.exposedMotors}${s.exposedMotors ? " — " + s.exposures.filter((x) => x.reach !== "UNCONFIRMED").map((x) => `${x.motor} (${REACH_TEXT[x.reach]}${x.historical ? ", historical link" : ""})`).join(", ") : ""}.`);
  if (!s.exposedMotors) L.push("No known exposure is recorded. That describes the records, not the batch: it does not mean the batch is safe.");
  const un = s.exposures.filter((x) => x.reach === "UNCONFIRMED"); if (un.length) L.push(`Not counted (conflicting or untrusted links only): ${un.map((x) => x.motor).join(", ")}.`);
  for (const x of s.exposures.filter((y) => y.reach !== "UNCONFIRMED").slice(0, 12)) L.push(`  ${x.motor}: ${x.paths[0]?.map(label).join(" → ")}`);
  if (s.gaps.length) L.push(`Incomplete or uncertain evidence (${s.gaps.length}): ${s.gaps.slice(0, 5).map((x) => x.message).join(" | ")}`);
  L.push(s.decisionsShown ? "Current verified decisions (engine, not this simulation): " + s.exposures.filter((x) => x.reach !== "UNCONFIRMED" && x.status).map((x) => `${x.motor} ${x.status!.finding}${x.status!.hold ? " / RECALL HOLD" : ""}`).join("; ") : "Current decisions are withheld: verification is not current, so no comparison is made.");
  return L.join("\n");
}
