import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { buildImpactGraph, lotChoices, type GEdge, type GNode, type ImpactGraph } from "../src/orig/impact/projection";
import { simulate, summaryText, HYPOTHETICAL } from "../src/dash/simulate";

// Real backend snapshot: 9 motors, 47 ledger events. The simulator is run on the graph the existing genealogy projection builds from it.
const snap = JSON.parse(readFileSync(resolve(process.cwd(), "tests/fixtures/ask-snapshot.json"), "utf8"));
const motors: string[] = snap.units.map((u: { unitId: string }) => u.unitId);
const graphOf = (kind: "BEARING_LOT" | "RAW_LOT", id: string, current = true, s = snap) => buildImpactGraph(s, { kind, id }, { recallStatusCurrent: current, previewRecorded: true } as never);
const run = (kind: "BEARING_LOT" | "RAW_LOT", id: string, current = true) => simulate(graphOf(kind, id, current), motors);
const label = (id: string) => id;
const ids = (s: ReturnType<typeof simulate>, r = "CONFIRMED") => s.exposures.filter((x) => x.reach === r).map((x) => x.motor);

test("the 47-event reference ledger is what the simulator runs on", () => {
  assert.equal(motors.length, 9); assert.equal(snap.units.reduce((n: number, u: { events: unknown[] }) => n + u.events.length, 0), 47);
});

test("batch choices are real ledger lots; every one can be simulated", () => {
  const c = lotChoices(snap);
  assert.ok(c.bearingLots.some((l) => l.id === "BR-204")); assert.ok(c.rawLots.length > 0);
  for (const l of c.bearingLots) assert.equal(run("BEARING_LOT", l.id).found, true, l.id);
  for (const r of c.rawLots) assert.equal(run("RAW_LOT", r).found, true, r);
});

test("bearing lot exposure equals an independent count from the install records (BR-204)", () => {
  const expected = [...new Set<string>(snap.components.filter((c: { lot: string }) => c.lot === "BR-204").map((c: { unitId: string }) => c.unitId))].sort();
  const s = run("BEARING_LOT", "BR-204");
  assert.deepEqual([...ids(s), ...ids(s, "CLAIMED")].sort(), expected); assert.equal(s.exposedMotors, expected.length); assert.ok(expected.length >= 2);
  for (const x of s.exposures.filter((y) => y.reach !== "UNCONFIRMED")) { assert.ok(x.paths.length >= 1); for (const p of x.paths) { assert.equal(p[0], "lot:BR-204"); assert.equal(p.at(-1), x.nodeId); } }
});

test("every raw-material lot: each path follows real directed edges starting at that lot", () => {
  for (const raw of lotChoices(snap).rawLots) {
    const g = graphOf("RAW_LOT", raw), s = simulate(g, motors);
    for (const x of s.exposures) { assert.equal(x.paths[0][0], `raw:${raw}`); for (const p of x.paths) for (let i = 0; i + 1 < p.length; i++) assert.ok(g.edges.some((e) => e.from === p[i] && e.to === p[i + 1]), `${p[i]}>${p[i + 1]}`); }
  }
});

test("no fabricated nodes or edges: every path node exists in the projection; results contain only snapshot motors", () => {
  for (const l of lotChoices(snap).bearingLots) {
    const g = graphOf("BEARING_LOT", l.id), s = simulate(g, motors), nodeIds = new Set(g.nodes.map((n) => n.id));
    for (const x of s.exposures) { assert.ok(motors.includes(x.motor)); for (const p of x.paths) for (const n of p) assert.ok(nodeIds.has(n), n); }
  }
});

test("unknown or empty selection: zero known exposure, nothing traversed, never claimed safe", () => {
  const s = run("BEARING_LOT", "BR-999"); assert.equal(s.found, false); assert.equal(s.exposures.length, 0); assert.equal(s.exposedMotors, 0); assert.deepEqual(s.notLinked, []);
  assert.match(summaryText(s, label), /no record of this lot/);
  const g = graphOf("BEARING_LOT", "BR-204"); const lone: ImpactGraph = { ...g, nodes: g.nodes.filter((n) => n.kind !== "COMPONENT" && n.kind !== "MOTOR"), edges: [] };
  const z = simulate(lone, motors); assert.equal(z.found, true); assert.equal(z.exposedMotors, 0);
  assert.match(summaryText(z, label), /does not mean the batch is safe/); assert.equal(z.notLinked.length, 9);
});

// Hand-built graphs exercise traversal rules; they are inputs to the pure function, not data claims.
const n = (id: string, kind: GNode["kind"], unitId: string | null = null): GNode => ({ id, kind, label: id, sublabel: "", unitId, evidence: [], issueIds: [], attrs: {}, slot: null, slotInScope: null, lifecycle: null, status: null, recalled: null });
const e = (from: string, to: string, style: GEdge["style"] = "RECORDED", historical = false): GEdge => ({ id: `${from}>${to}`, from, to, kind: "COMPONENT_IN_MOTOR", style, basis: "", evidence: [], historical });
const base = (nodes: GNode[], edges: GEdge[]): ImpactGraph => ({ ...graphOf("BEARING_LOT", "BR-204"), selection: { kind: "BEARING_LOT", id: "A" }, knownSelection: true, nodes, edges, issues: [] });

test("direction: only downstream of the selection is exposed; an upstream or sibling motor is not", () => {
  const g = base([n("lot:A", "BEARING_LOT"), n("c1", "COMPONENT"), n("motor:M1", "MOTOR", "M1"), n("raw:R", "RAW_LOT"), n("c2", "COMPONENT"), n("motor:M2", "MOTOR", "M2")],
    [e("raw:R", "lot:A"), e("lot:A", "c1"), e("c1", "motor:M1"), e("raw:R", "c2"), e("c2", "motor:M2")]);
  const s = simulate(g, ["M1", "M2", "M3"]); assert.deepEqual(ids(s), ["M1"]); assert.deepEqual(s.notLinked, ["M2", "M3"]);
});

test("duplicate paths collapse per motor and cycles terminate", () => {
  const g = base([n("lot:A", "BEARING_LOT"), n("c1", "COMPONENT"), n("c2", "COMPONENT"), n("motor:M1", "MOTOR", "M1")],
    [e("lot:A", "c1"), e("lot:A", "c2"), e("c1", "motor:M1"), e("c2", "motor:M1"), e("c2", "c1"), e("c1", "c2"), e("c1", "lot:A")]);
  const s = simulate(g, ["M1"]); assert.equal(s.exposures.length, 1); const keys = s.exposures[0].paths.map((p) => p.join(">")); assert.equal(new Set(keys).size, keys.length);
  for (const p of s.exposures[0].paths) assert.equal(new Set(p).size, p.length, "simple path, no repeated node");
});

test("reach levels: recorded, lot-claim and conflicting links are distinguished; conflicts are never counted", () => {
  const g = base([n("lot:A", "BEARING_LOT"), n("c1", "COMPONENT"), n("c2", "COMPONENT"), n("c3", "COMPONENT"), n("motor:M1", "MOTOR", "M1"), n("motor:M2", "MOTOR", "M2"), n("motor:M3", "MOTOR", "M3")],
    [e("lot:A", "c1"), e("c1", "motor:M1"), e("lot:A", "c2", "LOT_CLAIM"), e("c2", "motor:M2"), e("lot:A", "c3", "CONFLICT"), e("c3", "motor:M3")]);
  const s = simulate(g, ["M1", "M2", "M3"]);
  assert.deepEqual(s.exposures.map((x) => [x.motor, x.reach]), [["M1", "CONFIRMED"], ["M2", "CLAIMED"], ["M3", "UNCONFIRMED"]]); assert.equal(s.exposedMotors, 2);
  assert.match(summaryText(s, label), /Not counted.*M3/);
});

test("historical links are flagged; disconnected motors are listed as not linked, not as safe", () => {
  const g = base([n("lot:A", "BEARING_LOT"), n("c1", "COMPONENT"), n("motor:M1", "MOTOR", "M1")], [e("lot:A", "c1"), e("c1", "motor:M1", "RECORDED", true)]);
  const s = simulate(g, ["M1", "M9"]); assert.equal(s.exposures[0].historical, true); assert.deepEqual(s.notLinked, ["M9"]);
});

test("missing relationships appear as gaps and are never drawn as edges", () => {
  const real = run("BEARING_LOT", "BR-204"); const g = graphOf("BEARING_LOT", "BR-204");
  assert.equal(real.gaps.length, g.issues.filter((i) => i.severity !== "INFO").length);
  const withGap = { ...g, issues: [...g.issues, { id: "x", kind: "MISSING_LINK", severity: "UNCERTAIN" as const, nodeIds: [], message: "component has no recorded lot", evidence: [] }] };
  const s = simulate(withGap, motors); assert.ok(s.gaps.some((x) => /no recorded lot/.test(x.message))); assert.equal(s.exposures.length, real.exposures.length);
});

test("comparison with decisions: engine decisions only when recall status is current; withheld otherwise", () => {
  const cur = run("BEARING_LOT", "BR-204", true), non = run("BEARING_LOT", "BR-204", false);
  assert.equal(cur.decisionsShown, true); assert.ok(cur.exposures.every((x) => x.status !== null));
  for (const x of cur.exposures) assert.equal(x.status!.finding, Object.values(snap.decisions[x.motor] as Record<string, { current: { evidenceFinding: string } }>)[0].current.evidenceFinding);
  assert.equal(non.decisionsShown, false); assert.ok(non.exposures.every((x) => x.status === null));
  assert.deepEqual(non.exposures.map((x) => x.motor), cur.exposures.map((x) => x.motor)); // exposure is independent of verification; decisions are not
  assert.match(summaryText(non, label), /Current decisions are withheld/); assert.doesNotMatch(summaryText(non, label), /RECALL HOLD/);
  assert.match(summaryText(cur, label), /Current verified decisions \(engine, not this simulation\)/);
});

test("the summary is labelled hypothetical and states it is not a decision; the simulator is pure and read-only", () => {
  const s = run("BEARING_LOT", "BR-204"), t = summaryText(s, label);
  assert.ok(t.startsWith(HYPOTHETICAL)); assert.match(t, /not a recall decision, creates no evidence and changes no hold or release/);
  const g = graphOf("BEARING_LOT", "BR-204"), before = JSON.stringify(g); simulate(g, motors); assert.equal(JSON.stringify(g), before);
  assert.doesNotMatch(readFileSync(resolve(process.cwd(), "src/dash/simulate.ts"), "utf8"), /fetch\(|XMLHttpRequest|localStorage|method:/);
});

test("simulation is deterministic and re-running on a changed snapshot reflects the new graph", () => {
  assert.deepEqual(run("BEARING_LOT", "BR-204"), run("BEARING_LOT", "BR-204"));
  const moved = JSON.parse(JSON.stringify(snap)); const u = moved.units.find((x: { unitId: string }) => x.unitId === "MTR-27001"); u.events = u.events.filter((ev: { eventType: string; payload: { lot?: string } }) => !(ev.eventType === "COMPONENT_INSTALLED" && ev.payload.lot === "BR-204"));
  const after = simulate(graphOf("BEARING_LOT", "BR-204", true, moved), motors);
  assert.equal(after.exposures.find((x) => x.motor === "MTR-27001")?.reach === "CONFIRMED", false);
  assert.ok(run("BEARING_LOT", "BR-204").exposures.some((x) => x.motor === "MTR-27001" && x.reach === "CONFIRMED"));
});
