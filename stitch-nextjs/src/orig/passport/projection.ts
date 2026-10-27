// Pure passport projection over an already-validated RecallSnapshot.
//
// Invariants (enforced by tests/unit/passport-projection.test.ts):
//  * Read-only: the snapshot is never mutated and nothing is evaluated here. This module
//    imports no recall logic; recall context is the engine's decision, copied verbatim.
//  * Historical records, currently recorded component claims and live recall findings are
//    separate sections. Recall context is only populated when the caller states that the
//    snapshot passed the application's verified-freshness boundary.
//  * Customer, destination, shipment id and operator/actor identifiers are never projected.
//  * Nothing is invented: absent inspection, certification, specification, manufacturer
//    identity and trusted time are reported as "not recorded".
import { humanize } from "../domain/glossary";
import { claimFor, type ClearanceOptions, type MotorClearance } from "../contract/clearance";
import type { Component, Decision, EventRecord, RecallSnapshot, Unit } from "../domain/types";

export const UNIT_ID_PATTERN = /^MTR-[A-Z0-9-]{3,30}$/;

export const SOURCE_ROLE_LABEL: Record<string, string> = {
  MES: "Work-order system",
  ASSY: "Assembly station",
  REWORK: "Rework station",
  QA: "Quality station",
  HANDHELD: "Handheld operator device",
  MATERIAL: "Material intake",
  SHIP: "Dispatch",
  MACHINING: "Machining station",
  QC: "Inspection station (claim)",
};

export type ClaimStatus = "CURRENT" | "REMOVED" | "SUPERSEDED";

export interface EvidenceItem {
  eventId: string;
  eventType: string;
  label: string;
  sourceId: string;
  sourceRole: string;
  sourceRoleLabel: string;
  sourceSeq: number;
  occurredAt: string;
  recordedAt: string;
  timeSource: string;
  trustedTime: false;
  captureSha256: string | null;
  eventChainHash: string | null;
  repositoryRecordTime: string | null;
  localReceivedAt: string | null;
  supersedesEventId: string | null;
  /** Whitelisted payload facts only (no customer, destination, shipment id or actor ids). */
  facts: Array<[string, string]>;
}

export interface EvidenceLink {
  relation: "Installation record" | "Bearing manufacture record" | "Material allocation record" | "Removal record" | "Correcting record";
  eventId: string;
}

export interface ComponentClaim {
  claimId: string;
  slot: string;
  status: ClaimStatus;
  part: string | null;
  lot: string | null;
  serial: string | null;
  identityGranularity: string | null;
  installedAt: string;
  removedAt: string | null;
  rawMaterialLot: string | null;
  /** A synthetic supplier claim; never independently verified. */
  supplierClaim: string | null;
  evidence: EvidenceLink[];
  replacedByClaimId: string | null;
  replacesClaimId: string | null;
}

export interface SlotPassport {
  slot: string;
  current: ComponentClaim | null;
  history: ComponentClaim[];
}

export interface TimelineEntry {
  eventId: string;
  at: string;
  recordedAt: string;
  category: "Machining" | "Material" | "Assembly" | "Rework" | "Shipment" | "Observation" | "Inspection" | "Work order" | "Other";
  title: string;
  detail: string;
  slot: string | null;
}

export type NoteKind = "NOT_RECORDED" | "UNVERIFIED" | "GAP";
export interface PassportNote {
  kind: NoteKind;
  id: string;
  title: string;
  detail: string;
}

export type RecallContext =
  | { state: "UNAVAILABLE"; reason: string }
  | { state: "NO_RECALL" }
  | {
      state: "CURRENT";
      policyId: string;
      recallId: string;
      decisionId: string;
      version: number | null;
      finding: Decision["evidenceFinding"];
      /** A recall hold is in effect. Kept apart from finding and clearance. */
      hold: boolean;
      /** Per-motor current clearance; never inferred from `finding`. */
      clearance: MotorClearance;
      /** Explicit preview only: synthetic evaluator output, not an authorization. */
      recordedAction?: string;
      reviewRequired: boolean;
      precautionaryHold: boolean;
      notificationPending: boolean;
      reasonCodes: string[];
    };

export interface Passport {
  found: true;
  unitId: string;
  title: string;
  family: string;
  eventCount: number;
  firstOccurredAt: string | null;
  lastOccurredAt: string | null;
  lifecycle: { assembled: boolean; shipped: boolean; reworkOrders: number };
  slots: SlotPassport[];
  timeline: TimelineEntry[];
  evidence: Record<string, EvidenceItem>;
  notes: PassportNote[];
  recall: RecallContext;
}
export type PassportResult = Passport | { found: false; unitId: string; reason: "INVALID_IDENTIFIER" | "UNKNOWN_UNIT" };

const FACT_KEYS: Array<[string, string]> = [
  ["slot", "Slot"], ["componentType", "Component type"], ["part", "Part"], ["lot", "Lot"], ["serial", "Serial"],
  ["identityGranularity", "Identity recorded as"], ["rawMaterialLot", "Raw-material lot"],
  ["supplierName", "Supplier (claim)"], ["orderType", "Order type"], ["disposition", "Disposition"],
  ["observedPart", "Observed part"], ["observedLot", "Observed lot"], ["observedSerial", "Observed serial"],
  ["method", "Method"], ["provisional", "Provisional"], ["result", "Result"], ["state", "State"], ["reason", "Reason"],
];

export const roleOf = (sourceId: string): string => sourceId.split(":")[0] ?? sourceId;

function factsOf(e: EventRecord): Array<[string, string]> {
  const p = e.payload ?? {};
  const out: Array<[string, string]> = [];
  const lifecycleKeys: Array<[string, string]> = e.eventType === "MACHINING_RECORDED"
    ? [["componentId", "Component id"], ["operation", "Operation"], ["machineId", "Machine"], ["routingStepId", "Routing step"], ["drawingRef", "Drawing reference"]]
    : e.eventType === "QUALITY_INSPECTION_RECORDED" ? [["inspectionType", "Inspection type"], ["protocolId", "Inspection protocol"]] : [];
  for (const [k, label] of [...FACT_KEYS, ...lifecycleKeys]) {
    const v = (p as Record<string, unknown>)[k];
    if (v === null || v === undefined || typeof v === "object") continue;
    out.push([label, String(v)]);
  }
  if (e.eventType === "QUALITY_INSPECTION_RECORDED") {
    const refs = (p as Record<string, unknown>).subjectEventIds;
    if (Array.isArray(refs) && refs.every((v) => typeof v === "string")) out.push(["Inspected machining events", refs.join(", ")]);
  }
  return out;
}

function str(v: unknown): string | null {
  return typeof v === "string" && v ? v : null;
}

function evidenceOf(e: EventRecord): EvidenceItem {
  const role = roleOf(e.sourceId);
  const repo = e.repository;
  return {
    eventId: e.eventId, eventType: e.eventType, label: humanize(e.eventType), sourceId: e.sourceId, sourceRole: role,
    sourceRoleLabel: SOURCE_ROLE_LABEL[role] ?? `Source ${role}`, sourceSeq: e.sourceSeq,
    occurredAt: e.occurredAt, recordedAt: e.recordedAt, timeSource: e.timeSource, trustedTime: false,
    captureSha256: repo?.captureSha256 ?? null, eventChainHash: repo?.eventChainHash ?? null,
    repositoryRecordTime: repo?.recordTime ?? null, localReceivedAt: repo?.localReceivedAt ?? null,
    supersedesEventId: e.supersedesEventId, facts: factsOf(e),
  };
}

function timelineEntry(e: EventRecord): TimelineEntry {
  const p = (e.payload ?? {}) as Record<string, unknown>;
  const slot = str(p.slot);
  const base = { eventId: e.eventId, at: e.occurredAt, recordedAt: e.recordedAt, slot };
  switch (e.eventType) {
    case "MACHINING_RECORDED":
      return { ...base, category: "Machining", title: "Machining claim recorded", detail: `${str(p.operation) ?? "Operation not stated"} of ${str(p.componentType) ?? "component"} ${str(p.componentId) ?? "not stated"} on ${str(p.machineId) ?? "machine not stated"}; routing step ${str(p.routingStepId) ?? "not stated"}, drawing ${str(p.drawingRef) ?? "not stated"}. A recorded claim.` };
    case "QUALITY_INSPECTION_RECORDED":
      return { ...base, category: "Inspection", title: "Inspection claim recorded", detail: `${str(p.inspectionType) ?? "Inspection"} result: ${str(p.result) ?? "not stated"}; protocol ${str(p.protocolId) ?? "not stated"}. A recorded claim, not independent verification or release authorization.` };
    case "MATERIAL_ALLOCATED":
      return { ...base, category: "Material", title: "Raw material allocated", detail: `Raw-material lot ${str(p.rawMaterialLot) ?? "?"}; supplier claim: ${str(p.supplierName) ?? "not stated"}.` };
    case "BEARING_MANUFACTURED":
      return { ...base, category: "Material", title: "Bearing manufactured", detail: `Lot ${str(p.lot) ?? "?"}${str(p.serial) ? `, serial ${str(p.serial)}` : " (lot-level identity)"}; raw-material lot ${str(p.rawMaterialLot) ?? "?"}.` };
    case "WORK_ORDER_OPENED":
      return { ...base, category: str(p.orderType) === "REWORK" ? "Rework" : "Work order", title: `${humanize(str(p.orderType) ?? "work")} work order opened`, detail: "A work order was opened for this motor." };
    case "WORK_ORDER_CLOSED":
      return { ...base, category: "Work order", title: "Work order closed", detail: `Disposition: ${humanize(str(p.disposition) ?? "not stated")}.` };
    case "COMPONENT_INSTALLED":
      return { ...base, category: e.sourceId.startsWith("REWORK") ? "Rework" : "Assembly", title: `Bearing installed in ${slot ?? "?"}`, detail: `Lot ${str(p.lot) ?? "?"}${str(p.serial) ? `, serial ${str(p.serial)}` : " (lot-level identity)"}. A recorded claim.` };
    case "COMPONENT_REMOVED":
      return { ...base, category: "Rework", title: `Bearing removed from ${slot ?? "?"}`, detail: `Observed lot ${str(p.observedLot) ?? "?"}${str(p.observedSerial) ? `, serial ${str(p.observedSerial)}` : ""}.` };
    case "MOTOR_SHIPPED":
      return { ...base, category: "Shipment", title: "Shipment recorded", detail: "A shipment event was recorded. Recording a shipment is not a shipment authorization." };
    case "SLOT_STATE_VERIFIED":
      return { ...base, category: "Observation", title: `Slot observation recorded (${slot ?? "?"})`, detail: `Observed lot ${str(p.observedLot) ?? "?"}. Whether this observation is trusted is assessed by the recall evaluator, not by this passport.` };
    case "INSPECTION_RECORDED":
      return { ...base, category: "Inspection", title: "Inspection recorded", detail: `Result: ${str(p.result) ?? "not stated"}.` };
    default:
      return { ...base, category: "Other", title: humanize(e.eventType), detail: "Recorded event." };
  }
}

function evidenceLinks(c: Component, byId: Map<string, EventRecord>, replacedBy: string | null): EvidenceLink[] {
  const links: EvidenceLink[] = [{ relation: "Installation record", eventId: c.componentId }];
  const install = byId.get(c.componentId);
  const made = str((install?.payload as Record<string, unknown> | undefined)?.manufacturingEventId);
  if (made && byId.has(made)) {
    links.push({ relation: "Bearing manufacture record", eventId: made });
    const alloc = str((byId.get(made)?.payload as Record<string, unknown> | undefined)?.materialEventId);
    if (alloc && byId.has(alloc)) links.push({ relation: "Material allocation record", eventId: alloc });
  }
  if (c.removalEventId && byId.has(c.removalEventId)) links.push({ relation: "Removal record", eventId: c.removalEventId });
  if (replacedBy && byId.has(replacedBy)) links.push({ relation: "Correcting record", eventId: replacedBy });
  return links;
}

function captureGaps(unit: Unit): PassportNote[] {
  const bySource = new Map<string, Array<{ from: string; to: string }>>();
  for (const s of unit.captureSessions) {
    const list = bySource.get(s.sourceId) ?? [];
    list.push({ from: s.from, to: s.to });
    bySource.set(s.sourceId, list);
  }
  const notes: PassportNote[] = [];
  for (const [source, sessions] of bySource) {
    sessions.sort((a, b) => a.from.localeCompare(b.from));
    for (let i = 1; i < sessions.length; i++) {
      if (sessions[i].from > sessions[i - 1].to) {
        const role = roleOf(source);
        notes.push({
          kind: "GAP", id: `gap:${source}:${sessions[i - 1].to}`, title: `No capture session recorded for the ${SOURCE_ROLE_LABEL[role] ?? role} between ${sessions[i - 1].to} and ${sessions[i].from}`,
          detail: "Events from that source during this window, if any occurred, are not in the ledger. Absence of a record is not evidence that nothing happened.",
        });
      }
    }
  }
  return notes;
}

function notesFor(unit: Unit, snap: RecallSnapshot, lifecycle: Passport["lifecycle"]): PassportNote[] {
  const events = unit.events;
  const notes: PassportNote[] = [];
  if (!events.some((e) => e.eventType === "INSPECTION_RECORDED" || e.eventType === "QUALITY_INSPECTION_RECORDED")) {
    notes.push({ kind: "NOT_RECORDED", id: "inspection", title: "No inspection recorded", detail: "The ledger holds no inspection record for this motor." });
  }
  if (events.some((e) => e.eventType === "QUALITY_INSPECTION_RECORDED")) {
    notes.push({ kind: "UNVERIFIED", id: "inspection-claim", title: "Inspection recorded as a claim", detail: "The result is what the inspection source reported. It does not establish independent verification, certification or release authorization." });
  }
  notes.push({ kind: "NOT_RECORDED", id: "specification", title: "No structured product specification recorded", detail: "Only a free-text title is recorded; ratings, efficiency class and configuration are not captured as data." });
  notes.push({ kind: "NOT_RECORDED", id: "certification", title: "No certification recorded", detail: "No certificate, conformity declaration or test report is held in the ledger." });
  notes.push({ kind: "NOT_RECORDED", id: "manufacturer", title: "No manufacturer or facility identity recorded", detail: "Source streams are named by role (for example the assembly station); they are not authenticated identities of a factory." });
  if (events.length && events.every((e) => e.timeSource === "SYNTHETIC_SIMULATED")) {
    notes.push({ kind: "UNVERIFIED", id: "time", title: "No trusted time source", detail: "Every timestamp comes from a simulated clock. Ordering is as recorded; times are claims, not measurements." });
  }
  const lineage = (snap.lineage ?? []).filter((l) => l.unitId === unit.unitId);
  if (lineage.length) {
    notes.push({ kind: "UNVERIFIED", id: "supplier", title: "Supplier and raw-material origin are unverified claims", detail: "They are ledger-backed records of what a source stream stated. They are not independently verified, and quantities and physical origin are not certified." });
  }
  if (!lifecycle.assembled) notes.push({ kind: "NOT_RECORDED", id: "assembly", title: "Assembly completion not recorded", detail: "No completed build work order is present." });
  if (!lifecycle.shipped) notes.push({ kind: "NOT_RECORDED", id: "shipment", title: "No shipment recorded", detail: "No shipment event exists for this motor." });
  notes.push(...captureGaps(unit));
  return notes;
}

function recallContext(snap: RecallSnapshot, unitId: string, verified: boolean, reason: string, claim?: ClearanceOptions): RecallContext {
  if (!verified) return { state: "UNAVAILABLE", reason };
  const policy = snap.policies[0];
  if (!snap.recallAnnounced || !policy) return { state: "NO_RECALL" };
  const d = snap.decisions[unitId]?.[policy.policyId]?.current;
  if (!d) return { state: "UNAVAILABLE", reason: "No decision is available for this motor under the recall policy." };
  return {
    state: "CURRENT", policyId: d.policyId, recallId: d.recallId, decisionId: d.decisionId, version: typeof d.version === "number" ? d.version : null,
    finding: d.evidenceFinding, ...claimFor(d.operationalAction, unitId, claim), reviewRequired: d.reviewRequired, precautionaryHold: d.precautionaryHold === true,
    notificationPending: Boolean(d.notificationObligation) || (snap.notifications ?? []).some((n) => n.unitId === unitId),
    reasonCodes: [...d.reasonCodes],
  };
}

export interface BuildOptions extends ClearanceOptions {
  /** True only when the snapshot has just passed the application's verified-freshness check. */
  recallVerified: boolean;
  /** Shown when recallVerified is false. */
  unavailableReason?: string;
}

export function buildPassport(snap: RecallSnapshot, unitId: string, opts: BuildOptions): PassportResult {
  if (!UNIT_ID_PATTERN.test(unitId)) return { found: false, unitId, reason: "INVALID_IDENTIFIER" };
  const unit = snap.units.find((u) => u.unitId === unitId);
  if (!unit) return { found: false, unitId, reason: "UNKNOWN_UNIT" };

  const byId = new Map(unit.events.map((e) => [e.eventId, e]));
  const lineage = (snap.lineage ?? []).filter((l) => l.unitId === unitId);
  const installs = snap.components.filter((c) => c.unitId === unitId).slice().sort((a, b) => a.installedAt.localeCompare(b.installedAt) || a.componentId.localeCompare(b.componentId));
  const removalIndex = new Map<string, EventRecord>();
  for (const e of unit.events) if (e.eventType === "COMPONENT_REMOVED") removalIndex.set(e.eventId, e);

  const claims: ComponentClaim[] = installs.map((c) => {
    const install = byId.get(c.componentId);
    const made = str((install?.payload as Record<string, unknown> | undefined)?.manufacturingEventId);
    const l = lineage.find((x) => x.manufacturingEventId === made);
    const status: ClaimStatus = c.supersededBy ? "SUPERSEDED" : c.removedAt ? "REMOVED" : "CURRENT";
    return {
      claimId: c.componentId, slot: c.slot, status, part: c.part, lot: c.lot, serial: c.serial,
      identityGranularity: str((install?.payload as Record<string, unknown> | undefined)?.identityGranularity),
      installedAt: c.installedAt, removedAt: c.removedAt, rawMaterialLot: l?.rawMaterialLot ?? null, supplierClaim: l?.supplierName ?? null,
      evidence: evidenceLinks(c, byId, c.supersededBy), replacedByClaimId: null, replacesClaimId: null,
    };
  });
  // A replacement is the next install in the same slot after a removal.
  for (const slot of new Set(claims.map((c) => c.slot))) {
    const inSlot = claims.filter((c) => c.slot === slot);
    for (let i = 0; i < inSlot.length - 1; i++) {
      if (inSlot[i].status !== "CURRENT") {
        inSlot[i].replacedByClaimId = inSlot[i + 1].claimId;
        inSlot[i + 1].replacesClaimId = inSlot[i].claimId;
      }
    }
  }
  const slotNames = Array.from(new Set(["DE", "NDE", ...claims.map((c) => c.slot)]));
  const slots: SlotPassport[] = slotNames.map((slot) => {
    const inSlot = claims.filter((c) => c.slot === slot);
    const current = inSlot.filter((c) => c.status === "CURRENT").slice(-1)[0] ?? null;
    return { slot, current, history: inSlot.filter((c) => c !== current) };
  });

  const ordered = unit.events.slice().sort((a, b) => a.occurredAt.localeCompare(b.occurredAt) || a.recordedAt.localeCompare(b.recordedAt) || a.eventId.localeCompare(b.eventId));
  const evidence: Record<string, EvidenceItem> = {};
  for (const e of ordered) evidence[e.eventId] = evidenceOf(e);

  const lifecycle = {
    assembled: unit.events.some((e) => e.eventType === "WORK_ORDER_CLOSED" && e.workOrderId === `BUILD-${unitId}`),
    shipped: unit.events.some((e) => e.eventType === "MOTOR_SHIPPED"),
    reworkOrders: unit.events.filter((e) => e.eventType === "WORK_ORDER_OPENED" && (e.payload as Record<string, unknown>)?.orderType === "REWORK").length,
  };
  return {
    found: true, unitId, title: unit.title, family: unit.family, eventCount: unit.events.length,
    firstOccurredAt: ordered[0]?.occurredAt ?? null, lastOccurredAt: ordered[ordered.length - 1]?.occurredAt ?? null, lifecycle, slots,
    timeline: ordered.map(timelineEntry), evidence, notes: notesFor(unit, snap, lifecycle),
    recall: recallContext(snap, unitId, opts.recallVerified, opts.unavailableReason ?? "Current recall status unavailable.", opts),
  };
}
