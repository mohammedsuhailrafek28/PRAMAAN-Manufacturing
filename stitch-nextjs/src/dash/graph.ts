import type { Component, Lineage, Snapshot } from "./types";

/** Genealogy graph projection. Every edge is built from one backend record and carries it as `source`. A missing link is reported in `issues`, never drawn. */
export type Kind = "raw" | "lot" | "comp" | "motor" | "ship";
export type GNode = { id: string; kind: Kind; label: string; sub: string; x: number; y: number; motor?: string; affected?: boolean; removed?: boolean };
export type GEdge = {
  id: string; from: string; to: string; relation: string; claim: boolean; motors: string[];
  source: { type: string; eventIds: string[]; assurance?: string; backedByLedger?: boolean; note?: string }[];
};
export type Graph = { nodes: GNode[]; edges: GEdge[]; issues: string[]; width: number; height: number };

export const COL_X: Record<Kind, number> = { raw: 12, lot: 202, comp: 392, motor: 582, ship: 772 };
export const NODE_W = 160, NODE_H = 46;
const GAP = 62, TOP = 44;

export function buildGraph(s: Snapshot): Graph {
  const issues: string[] = [];
  const nodes = new Map<string, GNode>();
  const edges = new Map<string, GEdge>();
  const add = (n: Omit<GNode, "x" | "y">) => { if (!nodes.has(n.id)) nodes.set(n.id, { ...n, x: COL_X[n.kind], y: 0 }); return nodes.get(n.id)!; };
  const link = (e: Omit<GEdge, "id">, key: string) => {
    const id = `${e.from}>${e.to}`;
    const have = edges.get(id);
    if (have) { have.source.push(...e.source); for (const m of e.motors) if (!have.motors.includes(m)) have.motors.push(m); }
    else edges.set(id, { ...e, id });
    void key;
  };
  const affectedLots = new Set(s.recall.affectedLots ?? []);
  const lotInfo = new Map(s.lots.map((l) => [l.lotId, l]));

  const comps = [...s.components].sort((a, b) => a.unitId.localeCompare(b.unitId) || a.slot.localeCompare(b.slot) || (a.installedAt ?? "").localeCompare(b.installedAt ?? ""));
  for (const u of s.units) add({ id: `motor:${u.unitId}`, kind: "motor", label: u.motorSerial, sub: u.unitId, motor: u.unitId });
  for (const c of comps) {
    const removed = !!c.removedAt || !!c.supersededBy;
    add({ id: `comp:${c.componentId}`, kind: "comp", label: `${c.unitId.replace("MTR-", "")} · ${c.slot}`, sub: removed ? `removed ${(c.removedAt ?? "").slice(0, 10)}` : (c.serial ?? c.part ?? ""), motor: c.unitId, removed });
    link({ from: `comp:${c.componentId}`, to: `motor:${c.unitId}`, relation: `Installed in slot ${c.slot}`, claim: false, motors: [c.unitId], source: [{ type: "Component install record", eventIds: [c.componentId], note: `claimed by ${c.claimedBy ?? "unknown"}${c.removedAt ? `; removed ${c.removedAt}` : ""}` }] }, "ci");
    if (c.lot) {
      const info = lotInfo.get(c.lot);
      add({ id: `lot:${c.lot}`, kind: "lot", label: c.lot, sub: `${c.part ?? "part ?"} · ${affectedLots.has(c.lot) ? "RECALLED LOT" : "not recalled"}`, affected: affectedLots.has(c.lot) || !!info?.affected });
      link({ from: `lot:${c.lot}`, to: `comp:${c.componentId}`, relation: "Bearing lot recorded on install", claim: true, motors: [c.unitId], source: [{ type: "Component install record", eventIds: [c.componentId], assurance: info?.provenanceAssurance, note: `lot ${c.lot} serial ${c.serial ?? "none"}` }] }, "lc");
    } else issues.push(`Component ${c.componentId} has no lot recorded; no lot edge is drawn.`);
  }
  for (const l of s.lineage as Lineage[]) {
    if (!l.rawMaterialLot || !l.lot) { issues.push(`Lineage record for ${l.unitId} lacks a ${!l.rawMaterialLot ? "raw material lot" : "bearing lot"}; no edge drawn.`); continue; }
    add({ id: `raw:${l.rawMaterialLot}`, kind: "raw", label: l.rawMaterialLot, sub: "raw material lot (claimed)" });
    if (!nodes.has(`lot:${l.lot}`)) add({ id: `lot:${l.lot}`, kind: "lot", label: l.lot, sub: `${l.part ?? "part ?"} · no install record`, affected: affectedLots.has(l.lot) });
    link({ from: `raw:${l.rawMaterialLot}`, to: `lot:${l.lot}`, relation: `Material for bearing lot (supplier ${l.supplierName ?? "unknown"})`, claim: true, motors: [l.unitId], source: [{ type: "Supplier material and manufacturing events", eventIds: [l.materialEventId, l.manufacturingEventId].filter(Boolean) as string[], assurance: l.provenanceAssurance, backedByLedger: l.backedByLedger, note: `recorded via ${l.unitId}` }] }, "rl");
  }
  for (const u of s.units) {
    const sh = u.shipment;
    if (!sh) continue;
    add({ id: `ship:${sh.shipmentId}`, kind: "ship", label: sh.shipmentId, sub: sh.customer?.replace(" — synthetic customer", "") ?? "customer not recorded", motor: u.unitId });
    link({ from: `motor:${u.unitId}`, to: `ship:${sh.shipmentId}`, relation: "Shipped as", claim: !sh.backedByLedger, motors: [u.unitId], source: [{ type: "Shipment record", eventIds: [sh.evidenceEventId, sh.assemblyEventId].filter(Boolean) as string[], assurance: sh.provenanceAssurance, backedByLedger: sh.backedByLedger, note: `${sh.destination ?? ""} ${sh.shippedAt ?? ""}`.trim() }] }, "ms");
  }

  // Layered layout: components ordered by motor, other columns by the mean position of their neighbours.
  const place = (kind: Kind, order: GNode[]) => { let y = TOP; for (const n of order) { n.y = y; y += GAP; } };
  const all = [...nodes.values()];
  const byKind = (k: Kind) => all.filter((n) => n.kind === k);
  const compNodes = byKind("comp"); place("comp", compNodes);
  const mean = (n: GNode, want: Kind, dir: "in" | "out") => { const ys = [...edges.values()].filter((e) => (dir === "in" ? e.to === n.id : e.from === n.id)).map((e) => nodes.get(dir === "in" ? e.from : e.to)!).filter((m) => m.kind === want).map((m) => m.y); return ys.length ? ys.reduce((a, b) => a + b, 0) / ys.length : null; };
  const spread = (list: GNode[], ideal: (n: GNode) => number | null) => {
    // Missing neighbours are absence of evidence, not a coordinate. Keep those nodes
    // after linked nodes, spaced by one ordinary row, with deterministic ID ordering.
    const ordered = list.map(n => ({ n, y: ideal(n) })).sort((a, b) =>
      (a.y === null ? b.y === null ? 0 : 1 : b.y === null ? -1 : a.y - b.y) ||
      (a.n.id < b.n.id ? -1 : a.n.id > b.n.id ? 1 : 0));
    let prev = TOP - GAP;
    for (const { n, y } of ordered) { n.y = Math.max(y ?? TOP, prev + GAP); prev = n.y; }
  };
  spread(byKind("motor"), (n) => mean(n, "comp", "in"));
  spread(byKind("lot"), (n) => mean(n, "comp", "out"));
  spread(byKind("raw"), (n) => mean(n, "lot", "out"));
  for (const n of byKind("ship")) n.y = [...edges.values()].filter((e) => e.to === n.id).map((e) => nodes.get(e.from)!.y)[0] ?? TOP;
  const height = Math.max(...all.map((n) => n.y), 0) + NODE_H + 24;
  return { nodes: all, edges: [...edges.values()], issues, width: COL_X.ship + NODE_W + 12, height };
}

export const edgePath = (a: GNode, b: GNode) => { const x1 = a.x + NODE_W, y1 = a.y + NODE_H / 2, x2 = b.x, y2 = b.y + NODE_H / 2, mx = (x1 + x2) / 2; return `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`; };

/** Ids connected to a motor (its path from raw material to shipment). */
export function pathOf(g: Graph, motor: string): { nodes: Set<string>; edges: Set<string> } {
  const ns = new Set<string>(), es = new Set<string>();
  for (const e of g.edges) if (e.motors.includes(motor)) { es.add(e.id); ns.add(e.from); ns.add(e.to); }
  // An isolated selected motor is still a visible fact; never invent a connecting edge.
  if (g.nodes.some(n => n.id === `motor:${motor}`)) ns.add(`motor:${motor}`);
  return { nodes: ns, edges: es };
}
export type { Component };
