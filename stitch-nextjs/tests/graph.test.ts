import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import { buildGraph, pathOf, NODE_H, NODE_W, type Graph } from "../src/dash/graph";
import type { Snapshot, Unit } from "../src/dash/types";

const folder = process.env.PRAMAAN_COMPAT_FIXTURES!;
assert.ok(folder, "Use python -m compatibility.run for actual isolated-backend fixtures");
const fixture = (name: string): Snapshot => JSON.parse(readFileSync(resolve(folder, name + ".json"), "utf8"));
const manufacturing = fixture("manufacturing-current"), five = fixture("five-current");

// Test-only pre-fix rendering oracle from our exact requested baseline. No evaluator is
// copied or reimplemented. Compare all topology/provenance fields, not just counts.
const oldSource = execFileSync("git", ["show", "468dc99dc83c10b2395c8777b060c388ffd946a9:stitch-nextjs/src/dash/graph.ts"], { encoding: "utf8" });
const before = {} as { buildGraph(s: Snapshot): Graph; pathOf(g: Graph, id: string): ReturnType<typeof pathOf> };
runInNewContext(ts.transpileModule(oldSource, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2017 } }).outputText, { exports: before });
const plain = <T,>(x: T): T => structuredClone(x);
function topology(g: Graph) {
  return { nodes: g.nodes.map(({ x, y, ...n }) => n), edges: g.edges, issues: g.issues, width: g.width };
}
function bounded(g: Graph) {
  assert.ok(Number.isFinite(g.height) && g.height <= 114 + g.nodes.length * 62);
  for (const n of g.nodes) {
    assert.ok(Number.isFinite(n.y) && n.y >= 44 && n.y + NODE_H <= g.height);
    assert.ok(n.x >= 0 && n.x + NODE_W <= g.width);
  }
  for (const kind of ["raw", "lot", "comp", "motor", "ship"]) {
    const column = g.nodes.filter(n => n.kind === kind).sort((a, b) => a.y-b.y);
    for (let i = 1; i < column.length; i++) assert.ok(column[i].y-column[i-1].y >= 62, `${kind} nodes overlap`);
  }
}
function empty(): Snapshot {
  return { ...structuredClone(manufacturing), units: [], components: [], lineage: [], lots: [], decisions: {}, eligibility: {} };
}
function unit(id: string): Unit {
  return { ...structuredClone(manufacturing.units[0]), unitId: id, motorSerial: id, events: [], shipment: null };
}
function disconnected(): Snapshot {
  // Synthetic topology-only fixture; never supplied to the evaluator or ledger.
  const s = empty(); s.units = ["MTR-A", "MTR-B", "MTR-C", "MTR-ISOLATED"].map(unit);
  s.components = ["A", "B"].map(k => ({ componentId: `install-${k}`, unitId: `MTR-${k}`, slot: "DE", lot: `LOT-${k}` }));
  s.lineage = ["A", "B", "C"].map(k => ({ unitId: `MTR-${k}`, rawMaterialLot: `RAW-${k}`, lot: `LOT-${k}`, materialEventId: `material-${k}`, manufacturingEventId: `manufacture-${k}`, provenanceAssurance: "SYNTHETIC_LAYOUT_TEST" }));
  return s;
}

test("original five-motor graph retains exact pre-fix coordinates, paths and provenance", () => {
  assert.deepEqual(buildGraph(five), plain(before.buildGraph(five)));
  bounded(buildGraph(five));
});

test("47-event manufacturing graph retains every original node, edge and evidence field", () => {
  const old = plain(before.buildGraph(manufacturing)), next = buildGraph(manufacturing);
  assert.deepEqual(topology(next), topology(old));
  assert.ok(old.height > 1_000_000 && next.height < 2000);
  const unlinked = manufacturing.units.filter(u => !manufacturing.components.some(c => c.unitId === u.unitId));
  assert.ok(unlinked.length > 0);
  for (const u of unlinked) assert.ok(next.nodes.some(n => n.id === `motor:${u.unitId}`));
  // Connected motor/component paths keep their old coordinates.
  const connected = new Set(manufacturing.components.map(c => c.unitId));
  for (const n of next.nodes.filter(n => n.kind === "comp" || n.kind === "motor" && connected.has(n.motor!))) {
    assert.deepEqual(n, old.nodes.find(o => o.id === n.id));
  }
  bounded(next);
});

test("selected isolated motor highlights itself without gaining a fabricated edge", () => {
  const g = buildGraph(disconnected()), p = pathOf(g, "MTR-ISOLATED");
  assert.deepEqual([...p.nodes], ["motor:MTR-ISOLATED"]);
  assert.equal(p.edges.size, 0);
  assert.equal(g.edges.some(e => e.from === "motor:MTR-ISOLATED" || e.to === "motor:MTR-ISOLATED"), false);
  assert.equal(pathOf(g, "MTR-DOES-NOT-EXIST").nodes.size, 0);
});

test("disconnected subgraphs, uninstalled material and isolated motors remain finite and separate", () => {
  const s = disconnected(), g = buildGraph(s);
  bounded(g);
  assert.equal(g.nodes.filter(n => n.kind === "motor").length, 4);
  assert.ok(g.nodes.some(n => n.id === "raw:RAW-C"));
  assert.ok(g.nodes.some(n => n.id === "lot:LOT-C"));
  assert.ok(g.edges.some(e => e.from === "raw:RAW-C" && e.to === "lot:LOT-C"));
  assert.equal(g.edges.some(e => e.from === "lot:LOT-C" && e.to === "motor:MTR-C"), false);
  assert.deepEqual(topology(g), topology(plain(before.buildGraph(s))));
});

test("disconnected order is deterministic even when the unit input order changes", () => {
  const a = empty();a.units = ["MTR-Z", "MTR-A", "MTR-M"].map(unit);
  const b = structuredClone(a);b.units.reverse();
  const coords = (s: Snapshot) => Object.fromEntries(buildGraph(s).nodes.map(n => [n.id, n.y]).sort());
  assert.deepEqual(coords(a), coords(b));
  const g = buildGraph(a), ys = g.nodes.filter(n => n.kind === "motor").sort((a,b) => a.y-b.y);
  assert.deepEqual(ys.map(n => n.motor), ["MTR-A", "MTR-M", "MTR-Z"]);
});

test("1,000 unlinked motors retain readable spacing with linear coordinate bounds and no edges", () => {
  const s = empty();s.units = Array.from({ length: 1000 }, (_, i) => unit(`MTR-UNLINKED-${i.toString().padStart(4,"0")}`));
  const g = buildGraph(s);
  assert.equal(g.nodes.length, 1000);assert.equal(g.edges.length, 0);bounded(g);
  assert.equal(g.height, 44 + 999*62 + NODE_H + 24);
});

test("shipment-only motor follows its own motor coordinate, without an installation link", () => {
  const s = empty(), u = unit("MTR-SHIP-ONLY");
  u.shipment = { shipmentId: "SHIP-ONLY", evidenceEventId: "ship-event", backedByLedger: true };
  s.units = [u];const g = buildGraph(s);bounded(g);
  assert.deepEqual(g.edges.map(e => [e.from,e.to]), [["motor:MTR-SHIP-ONLY", "ship:SHIP-ONLY"]]);
  assert.equal(g.nodes.find(n => n.kind === "ship")!.y, g.nodes.find(n => n.kind === "motor")!.y);
});

test("linked trace filtering and all original edge provenance are unchanged", () => {
  for (const s of [five, manufacturing]) {
    const old = plain(before.buildGraph(s)), next = buildGraph(s);
    for (const u of s.units.filter(u => s.components.some(c => c.unitId === u.unitId))) {
      const a = pathOf(next, u.unitId), b = before.pathOf(old, u.unitId);
      assert.deepEqual([...a.edges], [...b.edges]);assert.deepEqual([...a.nodes], [...b.nodes]);
      for (const id of a.edges) assert.deepEqual(next.edges.find(e => e.id === id), old.edges.find(e => e.id === id));
    }
  }
});

test("layout is deterministic and leaves evaluator decisions and source snapshots untouched", () => {
  const s = structuredClone(manufacturing), previous = JSON.stringify(s);
  const freeze = (o: unknown) => { if (o && typeof o === "object" && !Object.isFrozen(o)) { Object.freeze(o);Object.values(o).forEach(freeze); } };
  freeze(s);assert.deepEqual(buildGraph(s), buildGraph(s));assert.equal(JSON.stringify(s), previous);
});

test("empty graph has finite bounds and no manufactured nodes or edges", () => {
  const g = buildGraph(empty());bounded(g);assert.equal(g.nodes.length, 0);assert.equal(g.edges.length, 0);
});
