import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { REASONS } from "../../src/domain/glossary";
import type { RecallSnapshot } from "../../src/domain/types";
import { buildInvestigation, PRIORITY_RULES, type InvestigationView, type Task } from "../../src/investigation/projection";
import { CLASSES, FLAG_HANDLING, LIMITATIONS, REASON_HANDLING } from "../../src/investigation/taxonomy";
import { demoOrigin, deepFreeze, ENGINE_FLAGS, ENGINE_REASON_CODES, FORBIDDEN, POLICY, SEEDED, SHARED_SOURCE, stage, subset } from "./investigationHelpers";

const tasksOf = (v: InvestigationView, unit: string): Task[] => v.tasks.filter((t) => t.unitId === unit);
const clusterOf = (v: InvestigationView, unit: string, cls: string) => {
  const t = tasksOf(v, unit).find((x) => x.cls === cls);
  if (!t) throw new Error(`no ${cls} task for ${unit}`);
  return v.clusters.find((c) => c.clusterId === t.clusterId)!;
};
const current = (s: RecallSnapshot, unit: string) => s.decisions[unit][POLICY].current;

describe("actual seeded cases (no shared gap exists in seeded data)", () => {
  const v = buildInvestigation(subset(stage("before"), SEEDED));
  it("turns each seeded hold into one task of the right class", () => {
    expect(tasksOf(v, "MTR-26002").map((t) => t.cls)).toEqual(["AMBIGUOUS_ATTRIBUTION"]);
    expect(tasksOf(v, "MTR-26004").map((t) => t.cls)).toEqual(["CAPTURE_GAP"]);
    expect(tasksOf(v, "MTR-26005").map((t) => t.cls)).toEqual(["UNTRUSTED_AFFECTED_OBSERVATION"]);
  });
  it("lists affected and released motors as having no evidence items, not as tasks", () => {
    expect(v.untasked.map((u) => u.unitId)).toEqual(["MTR-26001", "MTR-26003"]);
    expect(v.tasks.some((t) => t.unitId === "MTR-26001" || t.unitId === "MTR-26003")).toBe(false);
  });
  it("every seeded cluster is a single motor because source ids are per motor", () => {
    for (const c of v.clusters.filter((x) => x.family === "EVIDENCE_GAP")) expect(c.unitIds).toHaveLength(1);
  });
  it("grounds the capture gap in the exact source, window and slot", () => {
    const g = tasksOf(v, "MTR-26004")[0].grounded;
    expect(g).toMatchObject({ gapKind: "SOURCE_OUTAGE", materiality: "MATERIAL", sourceId: "ASSY:MTR-26004", windowFrom: "2026-10-02T00:00:00Z", windowTo: "2026-10-09T00:00:00Z", slots: ["DE"] });
  });
  it("grounds the untrusted observation in the rejection reasons, actor claim, method and event", () => {
    const t = tasksOf(v, "MTR-26005")[0];
    expect(t.grounded).toMatchObject({
      slot: "DE", observedLot: "BR-204", rejectedReasons: ["ACTOR_NOT_AUTHORIZED", "METHOD_NOT_APPROVED", "SOURCE_NOT_TRUSTED"],
      actorClaim: "OP-OBSERVATION-21", method: "HANDHELD_LABEL_READ", observedEventId: "urn:pramaan:MTR-26005:HANDHELD:1",
    });
    expect(t.evidenceEventIds).toEqual(["urn:pramaan:MTR-26005:HANDHELD:1"]);
  });
  it("grounds the ambiguity in the removal, candidate slots and assurance level", () => {
    const g = tasksOf(v, "MTR-26002")[0].grounded;
    expect(g).toMatchObject({ claimedSlot: "DE", assurance: "CLAIMED_SLOT", observedLot: "BR-204", removalEventId: "urn:pramaan:MTR-26002:REWORK:1" });
    expect(g.candidates).toEqual(["DE:RECORDED_OCCUPANT_MATCH:claimed", "NDE:RECORDED_OCCUPANT_MATCH"]);
    expect(tasksOf(v, "MTR-26002")[0].evidenceEventIds).toContain("urn:pramaan:MTR-26002:REWORK:1");
  });
});

describe("authored demonstration: shared exact keys form shared clusters", () => {
  const snap = stage("before");
  const v = buildInvestigation(snap);
  it("clusters the three untrusted observations on identical rejection, actor, method and lot", () => {
    const c = clusterOf(v, "MTR-26005", "UNTRUSTED_AFFECTED_OBSERVATION");
    expect(c.unitIds).toEqual(["MTR-26005", "MTR-26011", "MTR-26012"]);
    expect(c.key).toContain("actorClaim=OP-OBSERVATION-21");
    expect(c.key).toContain("rejectedReasons=ACTOR_NOT_AUTHORIZED,METHOD_NOT_APPROVED,SOURCE_NOT_TRUSTED");
  });
  it("clusters the lot-level ambiguities (one seeded, two demo extras)", () => {
    expect(clusterOf(v, "MTR-26002", "AMBIGUOUS_ATTRIBUTION").unitIds).toEqual(["MTR-26002", "MTR-26013", "MTR-26014"]);
  });
  it("clusters the two authored-source capture gaps and keeps the seeded gap separate", () => {
    const shared = clusterOf(v, "MTR-26015", "CAPTURE_GAP");
    expect(shared.unitIds).toEqual(["MTR-26015", "MTR-26016"]);
    expect(shared.key).toContain(`sourceId=${SHARED_SOURCE}`);
    expect(clusterOf(v, "MTR-26004", "CAPTURE_GAP").unitIds).toEqual(["MTR-26004"]);
  });
  it("keeps authored and seeded origins distinguishable", () => {
    expect(demoOrigin["MTR-26004"]).toBe("SEEDED");
    expect(demoOrigin["MTR-26015"]).toBe("AUTHORED_SOURCE_EDIT");
    expect(demoOrigin["MTR-26011"]).toBe("ENGINE_DEMO_EXTRA");
  });
  it("gives an identity-only motor an explicit baseline task", () => {
    const t = tasksOf(v, "MTR-26017");
    expect(t).toHaveLength(1);
    expect(t[0].cls).toBe("BASELINE_OR_STATE");
    expect(t[0].coveredCodes).toEqual(["CURRENT_STATE_UNVERIFIED", "NO_TRUSTED_BASELINE"]);
  });
  it("adds a raw-material-lot context group from the ledger's own lineage, labelled as a supplier claim", () => {
    const lot = v.clusters.find((c) => c.family === "RAW_MATERIAL_LOT")!;
    expect(lot.key).toContain("rawMaterialLot=STEEL-26-410");
    expect(lot.unitIds).toEqual(["MTR-26002", "MTR-26013", "MTR-26014"]);
    expect(tasksOf(v, "MTR-26013")[0].grounded.rawMaterialLots).toEqual([expect.stringContaining("supplier claim")]);
  });
  it("shows no lot context for an observation of a lot the ledger never traced to that motor", () => {
    // MTR-26005 was built with BR-310/BR-312; the rejected record only claims BR-204.
    expect(tasksOf(v, "MTR-26005")[0].grounded.rawMaterialLots).toEqual([]);
    expect(v.clusters.filter((c) => c.family === "RAW_MATERIAL_LOT").every((c) => !c.unitIds.includes("MTR-26005"))).toBe(true);
  });
});

describe("an evidence update changes the projection without any manual closing", () => {
  const before = buildInvestigation(stage("before"));
  const after = buildInvestigation(stage("after"));
  it("drops the task of a motor whose assembly record arrived, with no closure state anywhere", () => {
    expect(tasksOf(before, "MTR-26017")).toHaveLength(1);
    expect(tasksOf(after, "MTR-26017")).toHaveLength(0);
    expect(after.untasked.map((u) => u.unitId)).toContain("MTR-26017");
  });
  it("keeps a task whose new evidence did not answer it, now under a newer decision version", () => {
    const b = tasksOf(before, "MTR-26012")[0], a = tasksOf(after, "MTR-26012")[0];
    expect(a.taskId).toBe(b.taskId);
    expect(a.decision.version).toBeGreaterThan(b.decision.version!);
    expect(a.decision.decisionId).not.toBe(b.decision.decisionId);
    expect(after.watermark.ledgerEvents).toBeGreaterThan(before.watermark.ledgerEvents);
  });
  it("leaves unrelated tasks identical", () => {
    for (const unit of ["MTR-26002", "MTR-26004", "MTR-26015"]) expect(tasksOf(after, unit)).toEqual(tasksOf(before, unit));
  });
});

describe("priority order is a published lexicographic key, not a score", () => {
  it("puts serious untrusted observations and withdrawn exclusions ahead of larger clusters", () => {
    const v = buildInvestigation(subset(stage("before"), [...SEEDED, "MTR-26013", "MTR-26014"]));
    const ambiguity = clusterOf(v, "MTR-26002", "AMBIGUOUS_ATTRIBUTION");
    const untrusted = clusterOf(v, "MTR-26005", "UNTRUSTED_AFFECTED_OBSERVATION");
    expect(ambiguity.unitIds).toHaveLength(3);
    expect(untrusted.unitIds).toHaveLength(1);
    expect(untrusted.rank).toBeLessThan(ambiguity.rank);
    expect(untrusted.priority).toMatchObject({ serious: true, withdrawn: true });
  });
  it("then orders by distinct motors, then class rank, then key text", () => {
    const v = buildInvestigation(stage("before"));
    const rest = v.clusters.filter((c) => !c.priority.serious && !c.priority.withdrawn && c.family === "EVIDENCE_GAP");
    for (let i = 1; i < rest.length; i++) {
      const p = rest[i - 1].priority, q = rest[i].priority;
      expect(p.motors > q.motors || (p.motors === q.motors && (p.classRank < q.classRank || (p.classRank === q.classRank && rest[i - 1].key < rest[i].key)))).toBe(true);
    }
    expect(v.clusters.map((c) => c.rank)).toEqual(v.clusters.map((_, i) => i + 1));
    const lastGapIdx = Math.max(...v.clusters.map((c, i) => (c.family === "EVIDENCE_GAP" ? i : -1)));
    const firstLotIdx = v.clusters.findIndex((c) => c.family === "RAW_MATERIAL_LOT");
    expect(firstLotIdx).toBeGreaterThan(lastGapIdx);
  });
  it("invents no numeric score or probability", () => {
    const json = JSON.stringify(buildInvestigation(stage("before")));
    expect(json).not.toMatch(/"(score|probability|risk|severity|likelihood|confidence)[A-Za-z]*"\s*:/i);
    expect(PRIORITY_RULES.join(" ")).toMatch(/no numeric score/i);
  });
});

describe("exact equality only: nothing fuzzy", () => {
  it("splits a group when one grounded field differs", () => {
    const snap = stage("before");
    const base = clusterOf(buildInvestigation(snap), "MTR-26005", "UNTRUSTED_AFFECTED_OBSERVATION");
    expect(base.unitIds).toHaveLength(3);
    // a different actor claim for one motor
    const changed = structuredClone(snap);
    const ver = (current(changed, "MTR-26011").slots.DE.verifications as Array<Record<string, unknown>>)[0];
    ver.actor = "OP-OBSERVATION-22";
    const v = buildInvestigation(changed);
    expect(clusterOf(v, "MTR-26011", "UNTRUSTED_AFFECTED_OBSERVATION").unitIds).toEqual(["MTR-26011"]);
    expect(clusterOf(v, "MTR-26005", "UNTRUSTED_AFFECTED_OBSERVATION").unitIds).toEqual(["MTR-26005", "MTR-26012"]);
  });
  it("does not join gaps whose window differs by one second", () => {
    const snap = stage("before");
    for (const g of current(snap, "MTR-26016").slots.DE.gaps!) g.to = "2026-10-09T00:00:01Z";
    const v = buildInvestigation(snap);
    expect(clusterOf(v, "MTR-26015", "CAPTURE_GAP").unitIds).toEqual(["MTR-26015"]);
    expect(clusterOf(v, "MTR-26016", "CAPTURE_GAP").unitIds).toEqual(["MTR-26016"]);
  });
  it("does not join gaps from different sources over the same window", () => {
    const snap = stage("before");
    expect(clusterOf(buildInvestigation(snap), "MTR-26004", "CAPTURE_GAP").unitIds).toEqual(["MTR-26004"]);
  });
  it("assigns every task to exactly one primary cluster with a unique id", () => {
    const v = buildInvestigation(stage("before"));
    const primary = v.clusters.filter((c) => c.family === "EVIDENCE_GAP");
    expect(primary.flatMap((c) => c.taskIds).sort()).toEqual(v.tasks.map((t) => t.taskId).sort());
    expect(new Set(v.clusters.map((c) => c.clusterId)).size).toBe(v.clusters.length);
    for (const t of v.tasks) expect(primary.find((c) => c.clusterId === t.clusterId)!.taskIds).toContain(t.taskId);
  });
});

describe("taxonomy completeness: nothing silently disappears", () => {
  it("classifies every engine reason code, flag and glossary code explicitly", () => {
    for (const code of [...ENGINE_REASON_CODES, ...Object.keys(REASONS)]) expect(REASON_HANDLING[code], code).toBeDefined();
    for (const flag of ENGINE_FLAGS) expect(FLAG_HANDLING[flag], flag).toBeDefined();
  });
  it("keeps the withdrawn exclusion as an obligation, never a task", () => {
    expect(REASON_HANDLING.PRIOR_EXCLUSION_WITHDRAWN).toEqual({ handling: "OBLIGATION" });
    const v = buildInvestigation(stage("before"));
    expect(v.tasks.some((t) => t.coveredCodes.includes("PRIOR_EXCLUSION_WITHDRAWN") || t.trigger.code === "PRIOR_EXCLUSION_WITHDRAWN")).toBe(false);
    expect(v.obligations.map((o) => o.unitId)).toContain("MTR-26005");
    expect(tasksOf(v, "MTR-26005")[0].decision.withdrawnExclusion).toBe(true);
  });
  it("shows an unknown reason code as an unclassified item", () => {
    const snap = stage("before");
    current(snap, "MTR-26004").reasonCodes.push("FUTURE_ENGINE_CODE");
    const t = buildInvestigation(snap).tasks.find((x) => x.unitId === "MTR-26004" && x.cls === "UNCLASSIFIED")!;
    expect(t.grounded.code).toBe("FUTURE_ENGINE_CODE");
    expect(t.blocksHold).toBe(true);
  });
  it("shows an unknown flag as an unclassified item, non-blocking", () => {
    const snap = stage("before");
    current(snap, "MTR-26003").flags.push("FUTURE_FLAG");
    const t = buildInvestigation(snap).tasks.find((x) => x.unitId === "MTR-26003")!;
    expect(t).toMatchObject({ cls: "UNCLASSIFIED", blocksHold: false });
  });
  it("shows a held unresolved motor that lists no evidence reason", () => {
    const snap = stage("before");
    current(snap, "MTR-26004").reasonCodes = [];
    const t = tasksOf(buildInvestigation(snap), "MTR-26004");
    expect(t).toHaveLength(1);
    expect(t[0].trigger).toEqual({ type: "NO_LISTED_REASON", code: "NO_LISTED_EVIDENCE_REASON" });
  });
  it("falls back to a code-only task when a listed reason has no detail in the snapshot", () => {
    const snap = stage("before");
    current(snap, "MTR-26004").slots.DE.gaps = [];
    const t = tasksOf(buildInvestigation(snap), "MTR-26004")[0];
    expect(t).toMatchObject({ cls: "CAPTURE_GAP", detailFound: false });
  });
  it("accounts for every non-informational reason of every held decision in the scenario", () => {
    for (const id of ["before", "after"] as const) {
      const snap = stage(id), v = buildInvestigation(snap);
      for (const u of snap.units) {
        const d = current(snap, u.unitId);
        if (d.operationalAction !== "RECALL_HOLD") continue;
        const covered = new Set(tasksOf(v, u.unitId).flatMap((t) => t.coveredCodes));
        for (const code of d.reasonCodes) {
          const h = REASON_HANDLING[code];
          if (h?.handling === "TASK") expect(covered.has(code), `${u.unitId} ${code}`).toBe(true);
        }
      }
    }
  });
});

describe("other evidence classes", () => {
  it("separates a rejected verification from an untrusted affected observation", () => {
    const snap = stage("before");
    const d = current(snap, "MTR-26004");
    d.slots.DE.verifications = [{ eventId: "urn:pramaan:MTR-26004:QA:9", actor: "QA-X", source: "QA:MTR-26004", lot: "BR-312", part: "BR-6205", serial: null, granularity: "LOT", trusted: false, rejectedReasons: ["ACTOR_NOT_INDEPENDENT"] }];
    const t = tasksOf(buildInvestigation(snap), "MTR-26004").find((x) => x.cls === "REJECTED_EVIDENCE")!;
    expect(t.grounded).toMatchObject({ actorClaim: "QA-X", rejectedReasons: ["ACTOR_NOT_INDEPENDENT"], observedLot: "BR-312" });
    expect(t.blocksHold).toBe(false);
  });
  it("does not duplicate the untrusted observation as rejected evidence", () => {
    const v = buildInvestigation(stage("before"));
    expect(tasksOf(v, "MTR-26005").map((t) => t.cls)).toEqual(["UNTRUSTED_AFFECTED_OBSERVATION"]);
  });
  it("turns a recorded conflict into a conflicting-records task", () => {
    const snap = stage("before");
    const d = current(snap, "MTR-26004");
    d.reasonCodes.push("DOUBLE_OCCUPANCY");
    d.slots.DE.conflicts = [{ kind: "DOUBLE_OCCUPANCY", eventIds: ["e1", "e2"], note: "two" }];
    const t = tasksOf(buildInvestigation(snap), "MTR-26004").find((x) => x.cls === "CONFLICTING_RECORDS")!;
    expect(t.evidenceEventIds).toEqual(["e1", "e2"]);
    expect(t.grounded.conflictKind).toBe("DOUBLE_OCCUPANCY");
  });
  it("lists a non-blocking untrusted sighting outside the policy scope without blocking claims", () => {
    const snap = stage("before");
    const d = current(snap, "MTR-26003");
    d.flags.push("OUT_OF_SCOPE_UNTRUSTED_AFFECTED_OBSERVATION");
    d.untrustedObservations = [{ eventId: "urn:x", slot: "NDE", observed: { lot: "BR-204", part: "BR-6205", serial: null }, status: "OUT_OF_SCOPE", rejectedReasons: ["SOURCE_NOT_TRUSTED"] }];
    const t = buildInvestigation(snap).tasks.find((x) => x.unitId === "MTR-26003")!;
    expect(t).toMatchObject({ cls: "UNTRUSTED_AFFECTED_OBSERVATION", blocksHold: false });
  });
  it("produces no tasks when no recall has been announced", () => {
    const snap = stage("before");
    snap.recallAnnounced = false;
    expect(buildInvestigation(snap).tasks).toEqual([]);
  });
});

describe("static guidance is reviewed text that coaches no evidence", () => {
  const all = Object.values(CLASSES).flatMap((c) => [c.statement, ...c.investigate]);
  it("never tells anyone what a record should say or to approve trust", () => {
    for (const text of all) {
      expect(text).not.toMatch(/\bshould (say|show|read|record|be recorded)\b/i);
      expect(text).not.toMatch(/\b(enter|record|scan|set|use) (the )?(expected|correct|matching|right)\b/i);
      expect(text).not.toMatch(/\b(clears?|releases?|lifts?) the (hold|motor)\b/i);
    }
    expect(CLASSES.UNTRUSTED_AFFECTED_OBSERVATION.investigate.join(" ")).toMatch(/not evidence/);
  });
  it("states the limitations, including that resolving an item does not itself release a motor", () => {
    expect(LIMITATIONS.join(" ")).toMatch(/does not by itself release a motor/);
    expect(LIMITATIONS.join(" ")).toMatch(/read-only/);
  });
});

describe("privacy, purity and independence", () => {
  it("carries no customer or destination and no shipment authorization claim", () => {
    const v = buildInvestigation(stage("before"));
    const text = JSON.stringify(v);
    for (const f of FORBIDDEN) expect(text).not.toContain(f);
    expect(v.motors["MTR-26004"].shipment).toEqual({ shipmentId: "SHP-26-26004", shippedAt: expect.any(String) });
  });
  it("does not mutate its input, is deterministic, and copies decisions unchanged", () => {
    const snap = deepFreeze(stage("before"));
    const before = JSON.stringify(snap);
    const a = buildInvestigation(snap), b = buildInvestigation(snap);
    expect(a).toEqual(b);
    expect(JSON.stringify(snap)).toBe(before);
    for (const t of a.tasks) {
      const d = snap.decisions[t.unitId][t.policyId].current;
      expect(t.decision).toMatchObject({ decisionId: d.decisionId, finding: d.evidenceFinding, hold: d.operationalAction !== "RELEASE_ELIGIBLE", clearance: d.operationalAction === "RELEASE_ELIGIBLE" ? "NOT_CLEARED" : "HOLD", reasonCodes: d.reasonCodes });
      expect(t.decision).not.toHaveProperty("action");      // BRANDED-VIEWS migration
    }
  });
  it("imports only the snapshot types and the reviewed taxonomy, and does no I/O", () => {
    for (const file of ["projection.ts", "taxonomy.ts"]) {
      const src = readFileSync(join(process.cwd(), "src/investigation", file), "utf8").split(/\r?\n/).filter((l) => !l.trim().startsWith("//")).join("\n");
      const imports = [...src.matchAll(/from\s+"([^"]+)"/g)].map((m) => m[1]).sort();
      expect(imports).toEqual(file === "projection.ts" ? ["../contract/clearance", "../domain/types", "./taxonomy"] : []);
      expect(src).not.toMatch(/fetch\(|localStorage|sessionStorage|indexedDB|Date\.now|new Date|Math\.random|evaluate\(|domain\/derive/);
    }
  });
});
