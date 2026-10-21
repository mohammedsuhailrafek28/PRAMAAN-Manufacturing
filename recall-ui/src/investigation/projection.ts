// Pure, deterministic investigation projection over an already validated RecallSnapshot.
//
// It reads decisions the recall engine already computed and copies them unchanged. It never
// evaluates, never creates a decision or outcome, keeps no state, and has no network, storage or
// clock access. Everything it emits is a view: a task exists only while the evaluator's own decision
// lists the reason, and disappears when a re-evaluated snapshot no longer lists it.
import type { Decision, EventRecord, Gap, RecallSnapshot, SlotView, Unit } from "../domain/types";
import { CLASSES, FLAG_HANDLING, REASON_HANDLING, type EvidenceClass, type EvidenceKind } from "./taxonomy";

export type GroundedValue = string | string[] | null;
export type Grounded = Record<string, GroundedValue>;

export interface DecisionRef {
  decisionId: string;
  version: number | null;
  policyId: string;
  finding: string;
  action: string;
  reviewRequired: boolean;
  reasonCodes: string[];
  flags: string[];
  precautionaryHold: boolean;
  withdrawnExclusion: boolean;
  /** Total ledger events the decision's watermark covers. */
  watermarkEvents: number;
}

export interface Task {
  taskId: string;
  unitId: string;
  policyId: string;
  cls: EvidenceClass;
  kind: EvidenceKind;
  trigger: { type: "REASON_CODE" | "FLAG" | "NO_LISTED_REASON"; code: string };
  /** True when a reason code lists it as part of the hold; false for flag-driven human-look items. */
  blocksHold: boolean;
  /** Reason codes this task accounts for (a code is never silently dropped). */
  coveredCodes: string[];
  /** False when the reason is listed but its detail could not be located in the snapshot. */
  detailFound: boolean;
  decision: DecisionRef;
  grounded: Grounded;
  evidenceEventIds: string[];
  key: string;
  clusterId: string;
}

export interface ComponentClaim {
  componentId: string;
  slot: string;
  part: string | null;
  lot: string | null;
  serial: string | null;
  installedAt: string;
  removedAt: string | null;
  claimedBy: string;
}

export interface MotorRef {
  unitId: string;
  title: string;
  taskIds: string[];
  decisions: DecisionRef[];
  components: ComponentClaim[];
  /** Recorded shipment claim; customer and destination are deliberately not carried. */
  shipment: { shipmentId: string; shippedAt: string } | null;
  withdrawnExclusion: boolean;
}

export interface Priority {
  family: number;
  serious: boolean;
  withdrawn: boolean;
  motors: number;
  classRank: number;
}

export interface Cluster {
  clusterId: string;
  family: "EVIDENCE_GAP" | "RAW_MATERIAL_LOT";
  cls: EvidenceClass;
  key: string;
  taskIds: string[];
  unitIds: string[];
  evidenceEventIds: string[];
  priority: Priority;
  rank: number;
}

export interface ObligationRef {
  unitId: string;
  decisionId: string;
  reason: string;
  required: boolean;
  status: string;
  deliveryStatus: string;
}

export interface Watermark {
  status: string;
  sequence: number | null;
  headHash: string | null;
  archiveId: string | null;
  verifiedAt: string | null;
  maxAgeSeconds: number | null;
  ledgerEvents: number;
  decisions: number;
}

export interface UntaskedMotor {
  unitId: string;
  title: string;
  finding: string;
  action: string;
}

export interface InvestigationView {
  recallAnnounced: boolean;
  recallId: string;
  watermark: Watermark;
  tasks: Task[];
  clusters: Cluster[];
  motors: Record<string, MotorRef>;
  untasked: UntaskedMotor[];
  obligations: ObligationRef[];
}

export const PRIORITY_RULES: string[] = [
  "Evidence-gap groups are listed before shared raw-material-lot context groups.",
  "Groups that contain an untrusted affected-lot observation that blocks a hold come first.",
  "Then groups with at least one motor whose earlier release-eligible decision was withdrawn.",
  "Then more distinct motors before fewer.",
  "Then the fixed class order: untrusted affected-lot observation, rejected evidence, conflicting records, ambiguous attribution, capture gap, no trusted baseline, completeness or inspection, unclassified.",
  "Then the group key as text, so equal cases always sort the same way.",
  "There is no numeric score. The order says where to look first, not how risky a motor is.",
];

const WITHDRAWN = "PRIOR_EXCLUSION_WITHDRAWN";
const GAP_KINDS_FOR: Record<string, string[]> = {
  MATERIAL_CAPTURE_GAP: ["SOURCE_OUTAGE", "UNRESOLVED_EXCEPTION"],
  SOURCE_SEQUENCE_GAP: ["SOURCE_SEQUENCE_GAP"],
  EVENT_ORDER_INTEGRITY: ["EVENT_ORDER"],
  EVENT_INTEGRITY_VIOLATION: ["EVENT_INVALID"],
  WORK_ORDER_UNRECONCILED: ["WORK_ORDER_OBLIGATION_UNMET", "WORK_ORDER_MISSING"],
};
const CONFLICT_KINDS_FOR: Record<string, string[]> = {
  DOUBLE_OCCUPANCY: ["DOUBLE_OCCUPANCY"],
  REMOVAL_OBSERVATION_MISMATCH: ["REMOVAL_OBSERVATION_MISMATCH"],
  REMOVAL_SERIAL_IN_OTHER_SLOT: ["REMOVAL_SERIAL_IN_OTHER_SLOT"],
  REMOVAL_RECORD_INCONSISTENT: ["REMOVAL_LINK_MISMATCH", "REMOVAL_NOT_LINKED", "REMOVAL_FROM_EMPTY"],
  VERIFIED_STATE_MISMATCH: ["VERIFIED_STATE_MISMATCH"],
  VERIFIED_STATE_MISMATCH_RISK_DECREASING: ["VERIFIED_STATE_MISMATCH"],
  LATE_CLAIM_RISK_INCREASING: ["LATE_CORRECTION"],
};
const BASELINE_CODES = ["NO_TRUSTED_BASELINE", "UNTRUSTED_SOURCE_CLAIM"];
const DEFERRED_BASELINE = "CURRENT_STATE_UNVERIFIED";

/** cyrb53: small deterministic non-cryptographic hash, for stable identifiers only. */
function hash53(text: string): string {
  let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
  for (let i = 0; i < text.length; i++) {
    const ch = text.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(16).padStart(14, "0");
}

const NONE = "∅";
const str = (v: unknown): string | null => (typeof v === "string" && v !== "" ? v : null);
const sorted = (xs: Iterable<string>): string[] => [...new Set(xs)].sort();
const show = (v: string | null | undefined): string => v ?? NONE;

interface Draft {
  cls: EvidenceClass;
  trigger: Task["trigger"];
  blocksHold: boolean;
  coveredCodes: string[];
  detailFound: boolean;
  grounded: Grounded;
  evidenceEventIds: string[];
  /** Exact-equality fields that define the group; shown to the user as the key. */
  keyParts: Array<[string, string]>;
}

const joinKey = (policyId: string, cls: EvidenceClass, parts: Array<[string, string]>): string =>
  [`policy=${policyId}`, `class=${cls}`, ...parts.map(([k, v]) => `${k}=${v}`)].join(" | ");

function eventOf(unit: Unit, id: string | null | undefined): EventRecord | undefined {
  return id ? unit.events.find((e) => e.eventId === id) : undefined;
}

function relevantSlots(d: Decision): Array<[string, SlotView]> {
  return Object.entries(d.slots)
    .filter(([, s]) => s.policyRelevance !== "NOT_IN_POLICY_SCOPE")
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
}

function codeOnly(cls: EvidenceClass, trigger: Draft["trigger"], d: Decision, blocksHold: boolean): Draft {
  return {
    cls, trigger, blocksHold, coveredCodes: trigger.type === "REASON_CODE" ? [trigger.code] : [], detailFound: false,
    grounded: { code: trigger.code },
    evidenceEventIds: sorted(d.evidenceEventIds),
    keyParts: [["trigger", `${trigger.type}:${trigger.code}`]],
  };
}

function observationDrafts(d: Decision, unit: Unit, code: string, trigger: Draft["trigger"], statuses: string[], blocksHold: boolean): Draft[] {
  const out: Draft[] = [];
  for (const o of d.untrustedObservations ?? []) {
    if (!statuses.includes(o.status)) continue;
    const slot = o.slot ?? null;
    const verification = slot ? (d.slots[slot]?.verifications ?? []).find((v) => v.eventId === o.eventId) : undefined;
    const event = eventOf(unit, o.eventId);
    const actor = str(verification?.actor) ?? str(event?.actorId);
    const method = str(event?.payload?.method) ?? str(verification?.method);
    const granularity = str(verification?.granularity) ?? str(event?.payload?.identityGranularity);
    const rejected = sorted(o.rejectedReasons ?? []);
    out.push({
      cls: "UNTRUSTED_AFFECTED_OBSERVATION", trigger, blocksHold, coveredCodes: trigger.type === "REASON_CODE" ? [code] : [], detailFound: true,
      grounded: {
        slot, observedPart: str(o.observed.part), observedLot: str(o.observed.lot), observedSerial: str(o.observed.serial),
        observedGranularity: granularity, rejectedReasons: rejected, actorClaim: actor, method, observationStatus: o.status,
        sourceId: str(event?.sourceId) ?? str(verification?.source), observedEventId: o.eventId,
      },
      evidenceEventIds: [o.eventId],
      keyParts: [
        ["slot", show(slot)], ["observedPart", show(str(o.observed.part))], ["observedLot", show(str(o.observed.lot))],
        ["observedSerial", show(str(o.observed.serial))], ["rejectedReasons", rejected.join(",") || NONE],
        ["actorClaim", show(actor)], ["method", show(method)], ["observationStatus", o.status],
      ],
    });
  }
  return out;
}

function attributionDrafts(d: Decision, code: string, trigger: Draft["trigger"]): Draft[] {
  const out: Draft[] = [];
  for (const a of d.slotAttribution ?? []) {
    if (!a.ambiguous || a.cleared) continue;
    const candidates = a.candidates.map((c) => `${c.slot}:${c.basis}${c.claimed ? ":claimed" : ""}`).sort();
    const unrulable = a.unrulableAlternatives.map((u) => `${u.slot}:${u.reason}`).sort();
    const ruledOut = sorted(a.ruledOutSlots);
    out.push({
      cls: "AMBIGUOUS_ATTRIBUTION", trigger, blocksHold: true, coveredCodes: [code], detailFound: true,
      grounded: {
        observedPart: str(a.observed.part), observedLot: str(a.observed.lot), observedSerial: str(a.observed.serial),
        observedGranularity: str(a.observed.granularity), claimedSlot: a.claimedSlot, candidates, ruledOutSlots: ruledOut,
        unrulableAlternatives: unrulable, assurance: a.assurance, removalEventId: a.removalEventId,
        labelScansRecorded: String(a.labelScans.length), rejectedLabelScans: a.rejectedLabelScans.map((r) => `${r.eventId}: ${r.reason}`),
      },
      evidenceEventIds: sorted(a.supportingEventIds),
      keyParts: [
        ["observedPart", show(str(a.observed.part))], ["observedLot", show(str(a.observed.lot))], ["observedSerial", show(str(a.observed.serial))],
        ["observedGranularity", show(str(a.observed.granularity))], ["claimedSlot", a.claimedSlot], ["candidates", candidates.join(",")],
        ["ruledOutSlots", ruledOut.join(",") || NONE], ["unrulable", unrulable.join(",") || NONE], ["assurance", a.assurance],
      ],
    });
  }
  return out;
}

function gapDrafts(d: Decision, code: string, trigger: Draft["trigger"], cls: EvidenceClass): Draft[] {
  const kinds = GAP_KINDS_FOR[code] ?? [];
  const groups = new Map<string, { slots: string[]; gap: Gap }>();
  for (const [slot, s] of relevantSlots(d)) {
    for (const g of s.gaps ?? []) {
      if (g.materiality !== "MATERIAL" || !kinds.includes(g.kind)) continue;
      const id = JSON.stringify([g.kind, g.sourceId ?? null, g.from ?? null, g.to ?? null, g.eventId ?? null, g.boundedByEventId ?? null]);
      const hit = groups.get(id);
      if (hit) hit.slots.push(slot); else groups.set(id, { slots: [slot], gap: g });
    }
  }
  return [...groups.values()].map(({ slots, gap }) => ({
    cls, trigger, blocksHold: true, coveredCodes: [code], detailFound: true,
    grounded: {
      slots, gapKind: gap.kind, materiality: gap.materiality ?? null, sourceId: str(gap.sourceId), windowFrom: str(gap.from), windowTo: str(gap.to),
      gapEventId: str(gap.eventId), boundedByEventId: str(gap.boundedByEventId),
    },
    evidenceEventIds: sorted([gap.eventId, gap.boundedByEventId].filter((x): x is string => typeof x === "string")),
    keyParts: [
      ["gapKind", gap.kind], ["materiality", show(gap.materiality)], ["sourceId", show(str(gap.sourceId))], ["from", show(str(gap.from))], ["to", show(str(gap.to))],
      ["eventId", show(str(gap.eventId))], ["boundedByEventId", show(str(gap.boundedByEventId))], ["slots", slots.join(",")],
    ] as Array<[string, string]>,
  }));
}

function conflictDrafts(d: Decision, code: string, trigger: Draft["trigger"], blocksHold: boolean, kinds: string[] | null): Draft[] {
  const out: Draft[] = [];
  for (const [slot, s] of relevantSlots(d)) {
    for (const c of s.conflicts ?? []) {
      if (kinds && !kinds.includes(c.kind)) continue;
      const fields = Object.keys(c).filter((k) => k !== "kind").sort();
      const flat = (v: unknown): string => (typeof v === "string" ? v : JSON.stringify(v));
      const ids = fields.flatMap((k) => {
        const v = c[k];
        return /eventid/i.test(k) ? (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : typeof v === "string" ? [v] : []) : [];
      });
      out.push({
        cls: "CONFLICTING_RECORDS", trigger, blocksHold, coveredCodes: trigger.type === "REASON_CODE" ? [code] : [], detailFound: true,
        grounded: { slot, conflictKind: c.kind, ...Object.fromEntries(fields.map((k) => [`conflict.${k}`, flat(c[k])])) },
        evidenceEventIds: sorted(ids),
        keyParts: [["slot", slot], ["conflictKind", c.kind], ...fields.map((k): [string, string] => [k, flat(c[k])])],
      });
    }
  }
  return out;
}

function baselineDraft(d: Decision, codes: string[], trigger: Draft["trigger"]): Draft {
  const slots = relevantSlots(d).map(([slot, s]) => `${slot}:baseline=${show(str(s.baseline))},state=${show(str(s.state))},identity=${show(str(s.identityGranularity))},reconciliation=${s.reconciliation}`);
  return {
    cls: "BASELINE_OR_STATE", trigger, blocksHold: true, coveredCodes: codes, detailFound: true,
    grounded: { reasonCodes: codes, slotStates: slots },
    evidenceEventIds: sorted(d.evidenceEventIds),
    keyParts: [["reasonCodes", codes.join(",")], ["slotStates", slots.join(";")]],
  };
}

function unclassified(code: string, type: "REASON_CODE" | "FLAG" | "NO_LISTED_REASON", d: Decision): Draft {
  const draft = codeOnly("UNCLASSIFIED", { type, code }, d, type !== "FLAG");
  draft.grounded = { code, note: type === "NO_LISTED_REASON" ? "The decision holds the motor unresolved but lists no evidence reason." : "Code is not in the reviewed taxonomy." };
  return draft;
}

function draftsFor(d: Decision, unit: Unit): Draft[] {
  const drafts: Draft[] = [];
  const codes = d.reasonCodes;
  const held = d.operationalAction === "RECALL_HOLD";
  let deferredCovered = false;

  if (held) {
    for (const code of [...new Set(codes)].sort()) {
      if (code === DEFERRED_BASELINE) continue;
      const handling = REASON_HANDLING[code];
      const trigger = { type: "REASON_CODE" as const, code };
      if (!handling) { drafts.push(unclassified(code, "REASON_CODE", d)); continue; }
      if (handling.handling !== "TASK") continue;
      if (BASELINE_CODES.includes(code)) continue; // one combined task below
      let found: Draft[] = [];
      if (code === "UNTRUSTED_AFFECTED_OBSERVATION") found = observationDrafts(d, unit, code, trigger, ["BLOCKING"], true);
      else if (code === "AMBIGUOUS_SLOT_ATTRIBUTION" || code === "LOT_LEVEL_SLOT_AMBIGUITY") found = attributionDrafts(d, code, trigger);
      else if (GAP_KINDS_FOR[code]) found = gapDrafts(d, code, trigger, handling.cls);
      else if (CONFLICT_KINDS_FOR[code]) found = conflictDrafts(d, code, trigger, true, CONFLICT_KINDS_FOR[code]);
      drafts.push(...(found.length ? found : [codeOnly(handling.cls, trigger, d, true)]));
    }
    const baseline = codes.filter((c) => BASELINE_CODES.includes(c)).sort();
    if (baseline.length) {
      const withState = codes.includes(DEFERRED_BASELINE) ? [...baseline, DEFERRED_BASELINE].sort() : baseline;
      deferredCovered = true;
      drafts.push(baselineDraft(d, withState, { type: "REASON_CODE", code: baseline[0] }));
    }
    if (codes.includes(DEFERRED_BASELINE) && !deferredCovered) {
      if (drafts.length) drafts[0].coveredCodes = sorted([...drafts[0].coveredCodes, DEFERRED_BASELINE]);
      else drafts.push(baselineDraft(d, [DEFERRED_BASELINE], { type: "REASON_CODE", code: DEFERRED_BASELINE }));
    }
  }

  for (const flag of [...new Set(d.flags)].sort()) {
    const handling = FLAG_HANDLING[flag];
    const trigger = { type: "FLAG" as const, code: flag };
    if (!handling) { drafts.push(unclassified(flag, "FLAG", d)); continue; }
    if (handling.handling !== "TASK") continue;
    let found: Draft[] = [];
    if (flag === "OUT_OF_SCOPE_UNTRUSTED_AFFECTED_OBSERVATION") found = observationDrafts(d, unit, flag, trigger, ["OUT_OF_SCOPE"], false);
    else if (flag === "UNATTRIBUTABLE_UNTRUSTED_AFFECTED_OBSERVATION") found = observationDrafts(d, unit, flag, trigger, ["UNATTRIBUTABLE"], false);
    else if (flag === "SLOT_RECORD_CONFLICT") found = conflictDrafts(d, flag, trigger, false, null);
    drafts.push(...(found.length ? found : [codeOnly(handling.cls, trigger, d, false)]));
  }

  // Rejected verifications that are not already an untrusted-observation task. Held decisions only.
  if (held) {
    const taken = new Set(drafts.flatMap((x) => (x.cls === "UNTRUSTED_AFFECTED_OBSERVATION" ? x.evidenceEventIds : [])));
    for (const [slot, s] of relevantSlots(d)) {
      for (const v of s.verifications ?? []) {
        const rejected = Array.isArray(v.rejectedReasons) ? (v.rejectedReasons as unknown[]).filter((x): x is string => typeof x === "string") : [];
        const eventId = str(v.eventId);
        if (v.trusted !== false || !rejected.length || !eventId || taken.has(eventId)) continue;
        const event = eventOf(unit, eventId);
        const actor = str(v.actor) ?? str(event?.actorId);
        const method = str(event?.payload?.method) ?? str(v.method);
        const r = sorted(rejected);
        drafts.push({
          cls: "REJECTED_EVIDENCE", trigger: { type: "REASON_CODE", code: "REJECTED_VERIFICATION" }, blocksHold: false, coveredCodes: [], detailFound: true,
          grounded: {
            slot, observedPart: str(v.part), observedLot: str(v.lot), observedSerial: str(v.serial), observedGranularity: str(v.granularity),
            rejectedReasons: r, actorClaim: actor, method, sourceId: str(v.source), observedEventId: eventId,
          },
          evidenceEventIds: [eventId],
          keyParts: [
            ["slot", slot], ["observedPart", show(str(v.part))], ["observedLot", show(str(v.lot))], ["observedSerial", show(str(v.serial))],
            ["rejectedReasons", r.join(",")], ["actorClaim", show(actor)], ["method", show(method)],
          ],
        });
        taken.add(eventId);
      }
    }
  }

  if (held && d.evidenceFinding === "UNRESOLVED" && !drafts.some((x) => x.blocksHold)) drafts.push(unclassified("NO_LISTED_EVIDENCE_REASON", "NO_LISTED_REASON", d));
  return drafts;
}

function decisionRef(d: Decision): DecisionRef {
  return {
    decisionId: d.decisionId, version: typeof d.version === "number" ? d.version : null, policyId: d.policyId, finding: d.evidenceFinding,
    action: d.operationalAction, reviewRequired: d.reviewRequired, reasonCodes: [...d.reasonCodes], flags: [...d.flags],
    precautionaryHold: d.precautionaryHold === true, withdrawnExclusion: d.reasonCodes.includes(WITHDRAWN),
    watermarkEvents: Object.values(d.watermark ?? {}).reduce((a, n) => a + (Number.isFinite(n) ? n : 0), 0),
  };
}

const cmp = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

export function buildInvestigation(snap: RecallSnapshot): InvestigationView {
  const recallAnnounced = snap.recallAnnounced !== false;
  const units = [...snap.units].sort((a, b) => cmp(a.unitId, b.unitId));
  const tasks: Task[] = [];
  const decisionsSeen: DecisionRef[] = [];
  const untasked: UntaskedMotor[] = [];

  for (const unit of units) {
    const bundles = snap.decisions[unit.unitId] ?? {};
    let unitHadTask = false;
    let firstRef: DecisionRef | null = null;
    for (const policyId of Object.keys(bundles).sort()) {
      const d = bundles[policyId].current;
      const ref = decisionRef(d);
      decisionsSeen.push(ref);
      firstRef ??= ref;
      if (!recallAnnounced) continue;
      for (const draft of draftsFor(d, unit)) {
        unitHadTask = true;
        const key = joinKey(policyId, draft.cls, draft.keyParts);
        const detail = hash53(JSON.stringify([unit.unitId, policyId, key, draft.evidenceEventIds, draft.grounded]));
        const taskId = `${unit.unitId}~${draft.cls}~${detail}`;
        tasks.push({
          taskId, unitId: unit.unitId, policyId, cls: draft.cls, kind: CLASSES[draft.cls].kind, trigger: draft.trigger, blocksHold: draft.blocksHold,
          coveredCodes: sorted(draft.coveredCodes), detailFound: draft.detailFound, decision: ref, grounded: draft.grounded,
          evidenceEventIds: draft.evidenceEventIds, key, clusterId: "",
        });
      }
    }
    if (!unitHadTask && firstRef) untasked.push({ unitId: unit.unitId, title: unit.title, finding: firstRef.finding, action: firstRef.action });
  }

  // Primary grouping: exact equality of the key text.
  const groups = new Map<string, Task[]>();
  for (const t of tasks) (groups.get(t.key) ?? groups.set(t.key, []).get(t.key)!).push(t);
  const used = new Set<string>();
  const idFor = (key: string): string => {
    let id = `g-${hash53(key)}`;
    while (used.has(id)) id += "x";
    used.add(id);
    return id;
  };
  const clusters: Cluster[] = [];
  for (const key of [...groups.keys()].sort()) {
    const members = groups.get(key)!;
    const clusterId = idFor(key);
    members.forEach((t) => { t.clusterId = clusterId; });
    clusters.push(makeCluster(clusterId, "EVIDENCE_GAP", members[0].cls, key, members));
  }

  // Secondary view: motors whose open items concern a lot that the ledger traces to one raw-material lot.
  const lotGroups = new Map<string, Task[]>();
  for (const t of tasks) {
    const lot = typeof t.grounded.observedLot === "string" ? t.grounded.observedLot : null;
    if (!lot) continue;
    const rows = (snap.lineage ?? []).filter((l) => l.unitId === t.unitId && l.lot === lot);
    const origins = sorted(rows.map((l) => JSON.stringify([l.rawMaterialLot, l.supplierName])));
    const lots = origins.map((o) => JSON.parse(o) as [string, string]);
    t.grounded = { ...t.grounded, rawMaterialLots: lots.map(([raw, supplier]) => `${raw} (supplier claim: ${supplier})`) };
    for (const [raw, supplier] of lots) {
      const key = `class=RAW_MATERIAL_LOT | rawMaterialLot=${raw} | supplierClaim=${supplier} | observedLot=${lot}`;
      (lotGroups.get(key) ?? lotGroups.set(key, []).get(key)!).push(t);
    }
  }
  for (const key of [...lotGroups.keys()].sort()) {
    const members = lotGroups.get(key)!;
    if (new Set(members.map((m) => m.unitId)).size < 2) continue;
    clusters.push(makeCluster(idFor(key), "RAW_MATERIAL_LOT", "RAW_MATERIAL_LOT", key, members));
  }

  clusters.sort((a, b) => comparePriority(a, b));
  clusters.forEach((c, i) => { c.rank = i + 1; });

  const motors: Record<string, MotorRef> = {};
  for (const unit of units) {
    const mine = tasks.filter((t) => t.unitId === unit.unitId);
    if (!mine.length) continue;
    const decisions = Object.keys(snap.decisions[unit.unitId] ?? {}).sort().map((p) => decisionRef(snap.decisions[unit.unitId][p].current));
    motors[unit.unitId] = {
      unitId: unit.unitId, title: unit.title, taskIds: mine.map((t) => t.taskId).sort(), decisions,
      components: snap.components.filter((c) => c.unitId === unit.unitId).sort((a, b) => cmp(a.slot, b.slot) || cmp(a.installedAt, b.installedAt) || cmp(a.componentId, b.componentId))
        .map((c) => ({ componentId: c.componentId, slot: c.slot, part: c.part, lot: c.lot, serial: c.serial, installedAt: c.installedAt, removedAt: c.removedAt, claimedBy: c.claimedBy })),
      shipment: unit.shipment ? { shipmentId: unit.shipment.shipmentId, shippedAt: unit.shipment.shippedAt } : null,
      withdrawnExclusion: decisions.some((x) => x.withdrawnExclusion),
    };
  }

  const f = snap.freshness;
  const watermark: Watermark = {
    status: f?.status ?? "NO_FRESHNESS_METADATA", sequence: f?.sequence ?? null, headHash: f?.headHash ?? null, archiveId: f?.archiveId ?? null,
    verifiedAt: f?.verifiedAt ?? null, maxAgeSeconds: f?.maxAgeSeconds ?? null,
    ledgerEvents: units.reduce((n, u) => n + u.events.length, 0), decisions: decisionsSeen.length,
  };
  const obligations: ObligationRef[] = (snap.notifications ?? [])
    .map((n) => ({ unitId: n.unitId, decisionId: n.decisionId, reason: n.reason, required: n.required, status: String(n.status ?? ""), deliveryStatus: n.deliveryStatus }))
    .sort((a, b) => cmp(a.unitId, b.unitId) || cmp(a.decisionId, b.decisionId));

  tasks.sort((a, b) => cmp(a.unitId, b.unitId) || cmp(a.taskId, b.taskId));
  return { recallAnnounced, recallId: snap.recall.recallId, watermark, tasks, clusters, motors, untasked, obligations };
}

function makeCluster(clusterId: string, family: Cluster["family"], cls: EvidenceClass, key: string, members: Task[]): Cluster {
  const unitIds = sorted(members.map((m) => m.unitId));
  return {
    clusterId, family, cls, key, taskIds: members.map((m) => m.taskId).sort(), unitIds,
    evidenceEventIds: sorted(members.flatMap((m) => m.evidenceEventIds)),
    priority: {
      family: family === "EVIDENCE_GAP" ? 0 : 1,
      serious: members.some((m) => m.cls === "UNTRUSTED_AFFECTED_OBSERVATION" && m.blocksHold),
      withdrawn: members.some((m) => m.decision.withdrawnExclusion),
      motors: unitIds.length, classRank: CLASSES[cls].rank,
    },
    rank: 0,
  };
}

function comparePriority(a: Cluster, b: Cluster): number {
  const p = a.priority, q = b.priority;
  return (p.family - q.family) || (Number(q.serious) - Number(p.serious)) || (Number(q.withdrawn) - Number(p.withdrawn))
    || (q.motors - p.motors) || (p.classRank - q.classRank) || cmp(a.key, b.key);
}
