import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { buildPassport, type Passport } from "../../src/passport/projection";
import { FORBIDDEN, deepFreeze, previewSnapshot } from "./passportHelpers";

const verified = { recallVerified: true };
const unverified = { recallVerified: false, unavailableReason: "Current recall status unavailable. test" };
function passport(id: string, opts = verified): Passport {
  const r = buildPassport(previewSnapshot(), id, opts);
  if (!r.found) throw new Error(`expected a passport for ${id}`);
  return r;
}

describe("identifier handling", () => {
  it("rejects malformed identifiers and unknown motors without leaking other motors", () => {
    for (const bad of ["", "MTR-1", "mtr-26004", "../etc", "MTR-26004?x=1", "MTR-26004/DE", "MTR-" + "A".repeat(40)]) {
      expect(buildPassport(previewSnapshot(), bad, verified)).toEqual({ found: false, unitId: bad, reason: "INVALID_IDENTIFIER" });
    }
    expect(buildPassport(previewSnapshot(), "MTR-99999", verified)).toEqual({ found: false, unitId: "MTR-99999", reason: "UNKNOWN_UNIT" });
  });
});

describe("component replacement history (MTR-26004)", () => {
  const p = passport("MTR-26004");
  const de = p.slots.find((s) => s.slot === "DE")!;
  const nde = p.slots.find((s) => s.slot === "NDE")!;
  it("shows the replacement as the current DE claim and the original as removed history", () => {
    expect(de.current).toMatchObject({ lot: "BR-312", status: "CURRENT" });
    expect(de.current!.serial).toMatch(/-DE-R\d+$/);
    expect(de.history).toHaveLength(1);
    expect(de.history[0]).toMatchObject({ lot: "BR-204", serial: "BRG-MTR-26004-DE-01", status: "REMOVED" });
    expect(de.history[0].removedAt).toBeTruthy();
    expect(de.history[0].replacedByClaimId).toBe(de.current!.claimId);
    expect(de.current!.replacesClaimId).toBe(de.history[0].claimId);
  });
  it("links every claim to installation, manufacture and material records that exist as events", () => {
    for (const c of [de.current!, de.history[0], nde.current!]) {
      const relations = c.evidence.map((e) => e.relation);
      expect(relations).toEqual(expect.arrayContaining(["Installation record", "Bearing manufacture record", "Material allocation record"]));
      for (const l of c.evidence) expect(p.evidence[l.eventId]).toBeDefined();
    }
    expect(de.history[0].evidence.map((e) => e.relation)).toContain("Removal record");
  });
  it("carries supplier information only as a claim", () => {
    expect(de.history[0].supplierClaim).toMatch(/synthetic supplier/);
    expect(p.notes.find((n) => n.id === "supplier")).toMatchObject({ kind: "UNVERIFIED" });
    expect(JSON.stringify(p)).not.toMatch(/verified supplier|supplier verified|certified supplier|independently verified supplier/i);
  });
  it("reports the capture gap and the removed bearing's evidence hashes", () => {
    expect(p.notes.some((n) => n.kind === "GAP" && /Assembly station/.test(n.title))).toBe(true);
    const removal = p.evidence[de.history[0].evidence.find((e) => e.relation === "Removal record")!.eventId];
    expect(removal.captureSha256).toMatch(/^[0-9a-f]{64}$/);
    expect(removal.eventChainHash).toMatch(/^[0-9a-f]{64}$/);
  });
});

describe("chronology", () => {
  it("lists every recorded event once, ordered by claimed occurrence", () => {
    const snap = previewSnapshot();
    const p = passport("MTR-26004");
    const unit = snap.units.find((u) => u.unitId === "MTR-26004")!;
    expect(p.timeline).toHaveLength(unit.events.length);
    expect(new Set(p.timeline.map((t) => t.eventId)).size).toBe(unit.events.length);
    for (let i = 1; i < p.timeline.length; i++) expect(p.timeline[i].at >= p.timeline[i - 1].at).toBe(true);
    const order = p.timeline.map((t) => t.title);
    expect(order.indexOf("Raw material allocated")).toBeLessThan(order.indexOf("Bearing manufactured"));
    expect(order.some((t) => t === "Shipment recorded")).toBe(true);
    expect(order.some((t) => /removed from DE/.test(t))).toBe(true);
  });
  it("describes shipment as a record, never an authorization, and omits customer and destination", () => {
    const entry = passport("MTR-26004").timeline.find((t) => t.category === "Shipment")!;
    expect(entry.detail).toMatch(/not a shipment authorization/i);
  });
});

describe("privacy and invention", () => {
  it("never projects customer, destination, shipment id or operator identifiers", () => {
    for (const id of ["MTR-26001", "MTR-26002", "MTR-26003", "MTR-26004", "MTR-26005", "MTR-26006", "MTR-26007"]) {
      const text = JSON.stringify(passport(id));
      for (const f of FORBIDDEN) expect(text, `${id} leaks ${f}`).not.toContain(f);
    }
  });
  it("states what is not recorded rather than inventing it", () => {
    const ids = passport("MTR-26003").notes.map((n) => n.id);
    expect(ids).toEqual(expect.arrayContaining(["inspection", "specification", "certification", "manufacturer", "time", "supplier"]));
    const text = JSON.stringify(passport("MTR-26003"));
    expect(text).not.toMatch(/certified by|ISO ?9001|CE marked|inspected by/i);
  });
  it("handles a partially recorded motor (identity only)", () => {
    const p = passport("MTR-26006");
    expect(p.slots.every((s) => s.current === null && s.history.length === 0)).toBe(true);
    expect(p.timeline).toHaveLength(0);
    expect(p.lifecycle).toEqual({ assembled: false, shipped: false, reworkOrders: 0 });
    expect(p.notes.map((n) => n.id)).toEqual(expect.arrayContaining(["assembly", "shipment", "inspection"]));
  });
  it("handles an assembled but unshipped motor", () => {
    const p = passport("MTR-26007");
    expect(p.lifecycle).toMatchObject({ assembled: true, shipped: false });
    expect(p.notes.some((n) => n.id === "shipment")).toBe(true);
    expect(p.slots.find((s) => s.slot === "DE")!.current).toMatchObject({ lot: "BR-310" });
  });
  it("does not let an unverified field observation redefine the current occupant (MTR-26005)", () => {
    const p = passport("MTR-26005");
    expect(p.slots.find((s) => s.slot === "DE")!.current!.lot).toBe("BR-310");
    const obs = p.timeline.find((t) => t.category === "Observation")!;
    expect(obs.detail).toMatch(/assessed by the recall evaluator, not by this passport/);
  });
});

describe("recall context is separate and gated", () => {
  it("is unavailable, with no decision content at all, unless verification is asserted", () => {
    for (const id of ["MTR-26001", "MTR-26003"]) {
      const p = passport(id, unverified);
      expect(p.recall).toEqual({ state: "UNAVAILABLE", reason: unverified.unavailableReason });
      expect(JSON.stringify(p)).not.toMatch(/RELEASE_ELIGIBLE|RECALL_HOLD|EXCLUDED_WITH_EVIDENCE|AFFECTED/);
    }
  });
  it("copies the engine decision unchanged when verified", () => {
    const snap = previewSnapshot();
    for (const id of ["MTR-26001", "MTR-26003", "MTR-26005"]) {
      const d = snap.decisions[id][snap.policies[0].policyId].current;
      const r = buildPassport(snap, id, verified);
      expect(r.found && r.recall).toMatchObject({ state: "CURRENT", finding: d.evidenceFinding, action: d.operationalAction, decisionId: d.decisionId, reasonCodes: d.reasonCodes });
    }
  });
  it("reports no recall when none is announced", () => {
    const snap = previewSnapshot();
    snap.recallAnnounced = false;
    const r = buildPassport(snap, "MTR-26003", verified);
    expect(r.found && r.recall).toEqual({ state: "NO_RECALL" });
  });
});

describe("read-only and deterministic", () => {
  it("does not mutate its input and is deterministic", () => {
    const snap = deepFreeze(previewSnapshot());
    const before = JSON.stringify(snap);
    const a = buildPassport(snap, "MTR-26004", verified);
    const b = buildPassport(snap, "MTR-26004", verified);
    expect(a).toEqual(b);
    expect(JSON.stringify(snap)).toBe(before);
  });
  it("imports no recall logic, networking or storage", () => {
    const src = readFileSync(join(process.cwd(), "src/passport/projection.ts"), "utf8")
      .split(/\r?\n/).filter((l) => !l.trim().startsWith("//")).join("\n");
    const imports = [...src.matchAll(/from\s+"([^"]+)"/g)].map((m) => m[1]);
    expect(imports.sort()).toEqual(["../domain/glossary", "../domain/types"]);
    expect(src).not.toMatch(/fetch\(|localStorage|sessionStorage|evaluate\(|domain\/derive/);
  });
});
