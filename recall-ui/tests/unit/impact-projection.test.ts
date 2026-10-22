import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import type { RecallSnapshot } from "../../src/domain/types";
import { buildImpactGraph, filterByFinding, lotChoices, trace, type GEdge, type ImpactGraph } from "../../src/impact/projection";
import { scaleSnapshot } from "../../src/impact/syntheticScale";
import { dataset, deepFreeze, FORBIDDEN, origin } from "./impactHelpers";

const lot = (snap: RecallSnapshot, id = "BR-204", current = true) => buildImpactGraph(snap, { kind: "BEARING_LOT", id }, { recallStatusCurrent: current });
const motors = (g: ImpactGraph) => g.nodes.filter((n) => n.kind === "MOTOR").map((n) => n.unitId!).sort();
const linkedMotors = (g: ImpactGraph) => g.nodes.filter((n) => n.kind === "COMPONENT").map((n) => n.unitId!).filter((v, i, a) => a.indexOf(v) === i).sort();
const issuesOf = (g: ImpactGraph, unit: string, kind: string) => g.issues.filter((i) => i.kind === kind && i.nodeIds.some((id) => g.nodes.find((n) => n.id === id)?.unitId === unit));
const compOf = (g: ImpactGraph, unit: string) => g.nodes.filter((n) => n.kind === "COMPONENT" && n.unitId === unit);

/** Independent check of one edge against the raw ledger records. Returns the recorded reason or throws. */
function justify(snap: RecallSnapshot, e: GEdge): string {
  const ev = (unitId: string, id: string) => snap.units.find((u) => u.unitId === unitId)!.events.find((x) => x.eventId === id)!;
  expect(e.evidence.length, e.id).toBeGreaterThan(0);
  for (const r of e.evidence) expect(ev(r.unitId, r.eventId), `${e.id} cites a missing record ${r.eventId}`).toBeDefined();
  const [a] = e.evidence;
  const unit = a.unitId;
  const get = (role: string) => ev(unit, e.evidence.find((r) => r.role === role)!.eventId);
  switch (e.kind) {
    case "ALLOCATION_TO_MANUFACTURE": {
      const m = get("Manufacture record"), al = get("Material allocation record");
      expect(m.payload.materialEventId).toBe(al.eventId);
      expect(e.from).toBe(`raw:${String(al.payload.rawMaterialLot)}`);
      return "materialEventId";
    }
    case "LOT_TO_MANUFACTURE": {
      const m = get("Manufacture record");
      expect(e.from).toBe(`lot:${String(m.payload.lot)}`);
      return "manufacture lot field";
    }
    case "MANUFACTURE_TO_COMPONENT": {
      const i = get("Installation record"), m = get("Manufacture record");
      expect(i.payload.manufacturingEventId).toBe(m.eventId);
      expect(e.from).toBe(`mfg:${unit}:${m.eventId}`);
      expect(e.to).toBe(`cmp:${unit}:${i.eventId}`);
      return "manufacturingEventId";
    }
    case "LOT_CLAIM_ON_COMPONENT": {
      const i = get("Installation record");
      expect(e.from).toBe(`lot:${String(i.payload.lot)}`);
      expect(snap.units.find((u) => u.unitId === unit)!.events.some((x) => x.eventId === i.payload.manufacturingEventId && x.eventType === "BEARING_MANUFACTURED")).toBe(false);
      return "install lot field";
    }
    case "COMPONENT_IN_MOTOR": {
      const i = get("Installation record");
      expect(i.eventType).toBe("COMPONENT_INSTALLED");
      expect(e.to).toBe(`motor:${i.motorSerial}`);
      return "install motorSerial";
    }
    case "MOTOR_SHIPMENT": {
      const s = get("Shipment record");
      expect(s.eventType).toBe("MOTOR_SHIPPED");
      expect(e.from).toBe(`motor:${s.motorSerial}`);
      return "shipment event";
    }
    case "OBSERVED_LOT_CLAIM": {
      const o = get("Observation record");
      expect(e.from).toBe(`lot:${String(o.payload.observedLot)}`);
      return "observedLot";
    }
    case "OBSERVATION_ON_MOTOR": {
      const o = get("Observation record");
      expect(e.to).toBe(`motor:${o.motorSerial}`);
      return "observation motorSerial";
    }
  }
}

describe("lot BR-204, recall scope DE (actual engine decisions plus labelled authored link edits)", () => {
  const snap = dataset("de");
  const g = lot(snap);
  it("connects the lot to exactly the motors whose records name it, separately from claim-only motors", () => {
    expect(linkedMotors(g)).toEqual(["MTR-26001", "MTR-26002", "MTR-26004", "MTR-26021", "MTR-26022", "MTR-26023", "MTR-26031", "MTR-26032", "MTR-26033", "MTR-26034"]);
    expect(g.summary.motors).toBe(10);
    expect(g.summary.claimOnlyMotors).toBe(1);
    expect(motors(g)).toContain("MTR-26005");
    expect(linkedMotors(g)).not.toContain("MTR-26005");
    expect(motors(g)).not.toContain("MTR-26003");
  });
  it("justifies every edge with a recorded reference, and none without", () => {
    const reasons = new Set(g.edges.map((e) => justify(snap, e)));
    expect(reasons).toEqual(new Set(["materialEventId", "manufacture lot field", "manufacturingEventId", "install lot field", "install motorSerial", "shipment event", "observedLot", "observation motorSerial"]));
    expect(g.edges.length).toBeGreaterThan(40);
  });
  it("draws no edge from a similar identifier alone", () => {
    // Every component edge to a manufacture node exists only where the install names that manufacture record.
    for (const e of g.edges.filter((x) => x.kind === "MANUFACTURE_TO_COMPONENT")) expect(e.basis).toBe("COMPONENT_INSTALLED.payload.manufacturingEventId");
    // The edited motors keep the missing links as issues, not edges.
    expect(g.edges.filter((e) => e.to === compOf(g, "MTR-26031")[0].id).map((e) => e.kind)).toEqual(["LOT_CLAIM_ON_COMPONENT"]);
    expect(g.edges.filter((e) => e.kind === "MANUFACTURE_TO_COMPONENT" && e.to.includes("MTR-26031"))).toHaveLength(0);
    expect(g.edges.filter((e) => e.kind === "ALLOCATION_TO_MANUFACTURE" && e.to.startsWith("mfg:MTR-26034"))).toHaveLength(0);
  });
  it("shows DE and NDE placement against the recall scope without calling an out-of-scope slot safe", () => {
    const nde = compOf(g, "MTR-26021");
    expect(nde).toHaveLength(1);
    expect(nde[0]).toMatchObject({ slot: "NDE", slotInScope: false });
    expect(issuesOf(g, "MTR-26021", "SLOT_OUTSIDE_SCOPE")).toHaveLength(1);
    expect(g.nodes.find((n) => n.id === "motor:MTR-26021")!.status).toMatchObject({ finding: "EXCLUDED_WITH_EVIDENCE" });
    expect(compOf(g, "MTR-26001")[0]).toMatchObject({ slot: "DE", slotInScope: true });
    expect(JSON.stringify(g)).not.toMatch(/\bsafe\b/i);
  });
  it("keeps a removed bearing as historical and never treats removal as elimination", () => {
    const [c] = compOf(g, "MTR-26004");
    expect(c.lifecycle).toBe("HISTORICAL");
    expect(c.attrs.removedAt).toBeTruthy();
    expect(c.attrs.removalRecordedAfterShipment).toBe("true");
    expect(c.evidence.map((r) => r.role)).toContain("Removal record");
    const i = issuesOf(g, "MTR-26004", "REMOVED_NOT_ELIMINATED")[0];
    expect(i.message).toMatch(/does not show that exposure ended/);
    expect(g.edges.find((e) => e.kind === "COMPONENT_IN_MOTOR" && e.from === c.id)!.historical).toBe(true);
    expect(g.summary.historicalComponents).toBeGreaterThan(0);
  });
  it("carries the evaluator's finding unchanged for every motor and counts motors by it", () => {
    for (const m of g.nodes.filter((n) => n.kind === "MOTOR" && n.status)) {
      const d = snap.decisions[m.unitId!][g.scope.policyId].current;
      expect(m.status).toMatchObject({ finding: d.evidenceFinding, action: d.operationalAction, decisionId: d.decisionId });
    }
    expect(g.summary.byFinding).toEqual({ AFFECTED: 7, UNRESOLVED: 2, EXCLUDED_WITH_EVIDENCE: 1 });
  });
  it("flags ambiguous slot attribution, lot-level identity, capture gaps and withdrawn exclusions as uncertainty", () => {
    expect(issuesOf(g, "MTR-26002", "AMBIGUOUS_SLOT")).toHaveLength(1);
    expect(issuesOf(g, "MTR-26002", "LOT_IDENTITY_ONLY").length).toBeGreaterThan(0);
    expect(issuesOf(g, "MTR-26004", "CAPTURE_GAP").length).toBeGreaterThan(0);
    expect(issuesOf(g, "MTR-26005", "EXCLUSION_WITHDRAWN")).toHaveLength(1);
  });
  it("shows an untrusted affected-lot observation as a dashed claim, not a confirmed link", () => {
    const obs = g.nodes.find((n) => n.kind === "OBSERVATION")!;
    expect(obs.unitId).toBe("MTR-26005");
    const es = g.edges.filter((e) => e.from === obs.id || e.to === obs.id);
    expect(es.map((e) => e.style)).toEqual(["UNTRUSTED_CLAIM", "UNTRUSTED_CLAIM"]);
    expect(issuesOf(g, "MTR-26005", "UNTRUSTED_OBSERVATION")[0].message).toMatch(/not as a confirmed link/);
  });
  it("reports the authored link problems as issues", () => {
    expect(issuesOf(g, "MTR-26031", "MISSING_MANUFACTURE_LINK")).toHaveLength(1);
    expect(issuesOf(g, "MTR-26032", "DUPLICATE_REFERENCE")).toHaveLength(1);
    expect(issuesOf(g, "MTR-26033", "LOT_MISMATCH")[0].severity).toBe("CONFLICT");
    expect(g.edges.find((e) => e.to === compOf(g, "MTR-26033")[0].id && e.kind === "MANUFACTURE_TO_COMPONENT")!.style).toBe("CONFLICT");
    expect(issuesOf(g, "MTR-26034", "MISSING_MATERIAL_LINK")).toHaveLength(1);
    for (const u of ["MTR-26031", "MTR-26032", "MTR-26033", "MTR-26034"]) expect(origin("de")[u].kind).toBe("AUTHORED_LINK_EDIT");
    expect(origin("de")["MTR-26004"].kind).toBe("SEEDED");
  });
  it("records shipments as shipment records only, and leaves unshipped motors unshipped", () => {
    expect(g.nodes.some((n) => n.id.startsWith("ship:MTR-26022"))).toBe(false);
    expect(g.summary.unshippedMotors).toBe(1);
    expect(g.summary.shipmentsRecorded).toBe(9);
    expect(g.summary.shipmentsByFinding).toEqual({ AFFECTED: 6, UNRESOLVED: 2, EXCLUDED_WITH_EVIDENCE: 1 });
    const ship = g.nodes.find((n) => n.kind === "SHIPMENT")!;
    expect(ship.sublabel).toMatch(/shipment recorded/);
    expect(JSON.stringify(g)).not.toMatch(/delivered|delivery|received by/i);
  });
  it("leaks no customer, destination or operator identifier", () => {
    const text = JSON.stringify(g);
    for (const f of FORBIDDEN) expect(text).not.toContain(f);
  });
  it("states the recall scope and the watermark", () => {
    expect(g.scope).toMatchObject({ recallId: "RC-026-014", affectedLots: ["BR-204"], affectedSlots: ["DE"], selectionNamedByRecall: true, policyId: "RC-026-014/P1" });
    expect(g.watermark.ledgerEvents).toBeGreaterThan(100);
  });
});

describe("recall status withheld (verification failed)", () => {
  const snap = dataset("de");
  const g = lot(snap, "BR-204", false);
  it("keeps recorded linkage but removes findings, actions, flags and decision-derived uncertainty", () => {
    expect(g.recallStatus).toBe("WITHHELD");
    expect(g.nodes.every((n) => n.status === null && n.recalled === null)).toBe(true);
    expect(g.summary.byFinding).toBeNull();
    expect(g.summary.shipmentsByFinding).toBeNull();
    expect(g.nodes.some((n) => n.kind === "OBSERVATION")).toBe(false);
    for (const k of ["AMBIGUOUS_SLOT", "CAPTURE_GAP", "UNTRUSTED_OBSERVATION", "EXCLUSION_WITHDRAWN"]) expect(g.issues.some((i) => i.kind === k)).toBe(false);
    const text = JSON.stringify(g);
    expect(text).not.toMatch(/RELEASE_ELIGIBLE|RECALL_HOLD|EXCLUDED_WITH_EVIDENCE|"AFFECTED"|UNRESOLVED/);
    expect(g.edges.length).toBeGreaterThan(30);
    expect(g.issues.some((i) => i.kind === "MISSING_MANUFACTURE_LINK")).toBe(true);
  });
});

describe("selection variants", () => {
  it("a lot not named by the recall is traced with no recall claim", () => {
    const g = lot(dataset("de"), "BR-310");
    expect(g.scope.selectionNamedByRecall).toBe(false);
    expect(g.nodes.find((n) => n.id === "lot:BR-310")!.recalled).toBe(false);
    expect(g.summary.motors).toBeGreaterThan(5);
  });
  it("an unknown lot gives an empty graph and says it is unknown", () => {
    const g = lot(dataset("de"), "BR-999");
    expect(g.knownSelection).toBe(false);
    expect(g.nodes).toEqual([]);
    expect(g.edges).toEqual([]);
  });
  it("a raw-material lot traces forward only through recorded allocation references", () => {
    const snap = dataset("de");
    const g = buildImpactGraph(snap, { kind: "RAW_LOT", id: "STEEL-26-410" }, { recallStatusCurrent: true });
    expect(g.nodes.some((n) => n.id === "raw:STEEL-26-410")).toBe(true);
    expect(g.edges.every((e) => justify(snap, e))).toBe(true);
    expect(linkedMotors(g)).not.toContain("MTR-26034"); // its allocation link is missing
    expect(linkedMotors(g)).toContain("MTR-26001");
    // MTR-26031's install lost its manufacture link, so under a raw-material trace nothing records where that bearing went
    expect(g.issues.some((i) => i.kind === "MANUFACTURED_NOT_INSTALLED" && i.nodeIds.some((id) => id.includes("MTR-26031")))).toBe(true);
  });
  it("lists the lots the ledger records", () => {
    const c = lotChoices(dataset("de"));
    expect(c.bearingLots).toEqual([{ id: "BR-204", named: true }, { id: "BR-310", named: false }, { id: "BR-312", named: false }]);
    expect(c.rawLots).toEqual(["STEEL-26-410", "STEEL-26-518"]);
  });
  it("NDE-only scope: the recalled lot in DE is outside scope, in NDE it is in scope", () => {
    const g = lot(dataset("nde"));
    expect(g.scope.affectedSlots).toEqual(["NDE"]);
    expect(compOf(g, "MTR-26101")[0]).toMatchObject({ slot: "DE", slotInScope: false });
    expect(compOf(g, "MTR-26102")[0]).toMatchObject({ slot: "NDE", slotInScope: true });
    expect(compOf(g, "MTR-26103").map((c) => c.slot).sort()).toEqual(["DE", "NDE"]);
    expect(linkedMotors(g)).not.toContain("MTR-26104");
    expect(g.summary.unshippedMotors).toBe(1);
  });
});

describe("tracing and filtering walk only recorded edges", () => {
  const g = lot(dataset("de"));
  it("traces forward from a raw-material claim to shipments and backward from a shipment to the claim", () => {
    const fwd = trace(g, "raw:STEEL-26-410", "FORWARD");
    expect([...fwd.nodeIds].some((id) => id.startsWith("ship:"))).toBe(true);
    const ship = g.nodes.find((n) => n.kind === "SHIPMENT" && n.unitId === "MTR-26001")!;
    const back = trace(g, ship.id, "BACKWARD");
    expect(back.nodeIds.has("raw:STEEL-26-410")).toBe(true);
    expect(back.nodeIds.has("lot:BR-204")).toBe(true);
    expect([...back.nodeIds].every((id) => !id.includes("MTR-26002") && !id.includes("MTR-26004"))).toBe(true);
  });
  it("filters by the evaluator's finding and reports how many motors it hides", () => {
    const only = filterByFinding(g, new Set(["UNRESOLVED"]));
    const kept = [...only.nodeIds].filter((id) => id.startsWith("motor:")).sort();
    expect(kept).toEqual(["motor:MTR-26002", "motor:MTR-26004", "motor:MTR-26005"]);
    expect(only.hiddenMotors).toBe(g.nodes.filter((n) => n.kind === "MOTOR").length - 3);
  });
});

describe("purity and independence", () => {
  it("does not mutate its input and is deterministic", () => {
    const snap = deepFreeze(dataset("de"));
    const before = JSON.stringify(snap);
    expect(lot(snap)).toEqual(lot(snap));
    expect(JSON.stringify(snap)).toBe(before);
  });
  it("imports only snapshot types and does no I/O", () => {
    const src = readFileSync(join(process.cwd(), "src/impact/projection.ts"), "utf8").split(/\r?\n/).filter((l) => !l.trim().startsWith("//")).join("\n");
    expect([...src.matchAll(/from\s+"([^"]+)"/g)].map((m) => m[1])).toEqual(["../domain/types"]);
    expect(src).not.toMatch(/fetch\(|localStorage|sessionStorage|indexedDB|Date\.now|new Date|Math\.random|evaluate\(|domain\/derive/);
  });
});

describe("a large synthetic fleet (authored clones of real motors)", () => {
  it("projects thousands of nodes quickly and deterministically, with every edge still justified", () => {
    const { snap, clones } = scaleSnapshot(dataset("de"), 1500);
    expect(clones.length).toBe(1500 - 12);
    const t0 = performance.now();
    const g = lot(snap);
    const ms = performance.now() - t0;
    expect(g.nodes.length).toBeGreaterThan(4000);
    expect(ms).toBeLessThan(4000);
    expect(lot(snap).nodes.map((n) => n.id)).toEqual(g.nodes.map((n) => n.id));
    for (const e of g.edges.slice(0, 400)) justify(snap, e);
    const t1 = performance.now();
    trace(g, "raw:STEEL-26-410", "FORWARD");
    expect(performance.now() - t1).toBeLessThan(2000);
    console.log(`impact projection: ${g.nodes.length} nodes, ${g.edges.length} edges, ${ms.toFixed(0)} ms`);
  });
});
