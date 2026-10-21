// Pure, deterministic recall-impact projection over an already validated RecallSnapshot.
//
// Every edge exists because a recorded ledger field names the link:
//   raw-material claim  -> manufacture   BEARING_MANUFACTURED.payload.materialEventId
//   bearing lot         -> manufacture   BEARING_MANUFACTURED.payload.lot
//   manufacture         -> component     COMPONENT_INSTALLED.payload.manufacturingEventId
//   bearing lot         -> component     COMPONENT_INSTALLED.payload.lot (a recorded lot claim, no manufacture link)
//   component           -> motor         the install event's own motorSerial
//   motor               -> shipment      MOTOR_SHIPPED event named by the unit's shipment record
//   bearing lot         -> observation   SLOT_STATE_VERIFIED.payload.observedLot (rejected evidence, shown dashed)
// Nothing is inferred from similar identifiers. A link that is absent is never drawn; it becomes an issue.
// The projection never evaluates anything: findings and actions are copied from the engine's decisions.
import type { Decision, EventRecord, RecallSnapshot, Unit } from "../domain/types";

export type SelectionKind = "BEARING_LOT" | "RAW_LOT";
export interface Selection { kind: SelectionKind; id: string }

export type NodeKind = "RAW_LOT" | "BEARING_LOT" | "MANUFACTURE" | "COMPONENT" | "MOTOR" | "SHIPMENT" | "OBSERVATION";
export type EdgeKind =
  | "ALLOCATION_TO_MANUFACTURE" | "LOT_TO_MANUFACTURE" | "MANUFACTURE_TO_COMPONENT" | "LOT_CLAIM_ON_COMPONENT"
  | "COMPONENT_IN_MOTOR" | "MOTOR_SHIPMENT" | "OBSERVED_LOT_CLAIM" | "OBSERVATION_ON_MOTOR";
export type EdgeStyle = "RECORDED" | "CONFLICT" | "LOT_CLAIM" | "UNTRUSTED_CLAIM";
export type Severity = "INFO" | "UNCERTAIN" | "CONFLICT";

export interface EvidenceRef { unitId: string; eventId: string; role: string }

export interface MotorStatus {
  finding: string; action: string; reviewRequired: boolean; decisionId: string; version: number | null;
  withdrawnExclusion: boolean; reasonCodes: string[];
}

export interface GNode {
  id: string;
  kind: NodeKind;
  label: string;
  sublabel: string;
  unitId: string | null;
  evidence: EvidenceRef[];
  issueIds: string[];
  /** Plain recorded facts, null when not recorded. Never contains operator or customer data. */
  attrs: Record<string, string | null>;
  slot: string | null;
  /** True when the slot is named by the recall's scope; null when not a slot node. */
  slotInScope: boolean | null;
  lifecycle: "CURRENT" | "HISTORICAL" | "SUPERSEDED" | "UNKNOWN" | null;
  /** Engine decision under the chosen policy; null when recall status is withheld or not a motor. */
  status: MotorStatus | null;
  /** For bearing-lot nodes: named by the recall; null when recall status is withheld. */
  recalled: boolean | null;
}

export interface GEdge {
  id: string; from: string; to: string; kind: EdgeKind; style: EdgeStyle;
  basis: string; evidence: EvidenceRef[]; historical: boolean;
}

export interface Issue {
  id: string; kind: string; severity: Severity; nodeIds: string[]; message: string; evidence: EvidenceRef[];
}

export interface ScopeInfo {
  recallId: string; policyId: string; affectedPart: string; affectedLots: string[]; affectedSlots: string[];
  exposureBasis: string | null; scopeDeclaration: string | null; announcedAt: string | null; announced: boolean;
  selectionNamedByRecall: boolean | null;
}

export interface Summary {
  motors: number;
  byFinding: Record<string, number> | null;
  claimOnlyMotors: number;
  shipmentsRecorded: number;
  shipmentsByFinding: Record<string, number> | null;
  unshippedMotors: number;
  currentComponents: number;
  historicalComponents: number;
  issues: Record<Severity, number>;
}

export interface Watermark {
  status: string; sequence: number | null; headHash: string | null; verifiedAt: string | null; ledgerEvents: number;
}

export interface ImpactGraph {
  selection: Selection;
  knownSelection: boolean;
  recallStatus: "CURRENT" | "WITHHELD";
  scope: ScopeInfo;
  nodes: GNode[];
  edges: GEdge[];
  issues: Issue[];
  summary: Summary;
  watermark: Watermark;
}

export interface BuildOptions { policyId?: string; recallStatusCurrent: boolean }

const cmp = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);
const str = (v: unknown): string | null => (typeof v === "string" && v !== "" ? v : null);
const FINDINGS = ["AFFECTED", "UNRESOLVED", "EXCLUDED_WITH_EVIDENCE"];

/** Raw-material lot choices come only from the ledger's own allocation records. */
export function lotChoices(snap: RecallSnapshot): { bearingLots: Array<{ id: string; named: boolean }>; rawLots: string[] } {
  const named = new Set(snap.recall.affectedLots);
  const bearing = new Set<string>(snap.lots.map((l) => l.lotId));
  const raw = new Set<string>();
  for (const u of snap.units) for (const e of u.events) {
    if (e.eventType === "BEARING_MANUFACTURED" && str(e.payload.lot)) bearing.add(String(e.payload.lot));
    if (e.eventType === "MATERIAL_ALLOCATED" && str(e.payload.rawMaterialLot)) raw.add(String(e.payload.rawMaterialLot));
  }
  return { bearingLots: [...bearing].sort().map((id) => ({ id, named: named.has(id) })), rawLots: [...raw].sort() };
}

interface UnitIndex {
  unit: Unit;
  byId: Map<string, EventRecord>;
}

export function buildImpactGraph(snap: RecallSnapshot, selection: Selection, opts: BuildOptions): ImpactGraph {
  const current = opts.recallStatusCurrent;
  const policy = snap.policies.find((p) => p.policyId === opts.policyId) ?? snap.policies[0];
  const policyId = policy?.policyId ?? "";
  const recallInfo = snap.recall as unknown as Record<string, unknown>;
  const choices = lotChoices(snap);
  const known = selection.kind === "BEARING_LOT" ? choices.bearingLots.some((l) => l.id === selection.id) : choices.rawLots.includes(selection.id);
  const units = [...snap.units].sort((a, b) => cmp(a.unitId, b.unitId));
  const index = new Map<string, UnitIndex>(units.map((u) => [u.unitId, { unit: u, byId: new Map(u.events.map((e) => [e.eventId, e])) }]));
  const compByKey = new Map(snap.components.map((c) => [`${c.unitId}|${c.componentId}`, c]));
  const decisionOf = (unitId: string): Decision | undefined => snap.decisions[unitId]?.[policyId]?.current;

  const nodes = new Map<string, GNode>();
  const edges = new Map<string, GEdge>();
  const issues = new Map<string, Issue>();

  const ref = (unitId: string, e: EventRecord, role: string): EvidenceRef => ({ unitId, eventId: e.eventId, role });
  const node = (n: Omit<GNode, "issueIds" | "slot" | "slotInScope" | "lifecycle" | "status" | "recalled" | "attrs"> & Partial<GNode>): GNode => {
    const hit = nodes.get(n.id);
    if (hit) {
      for (const e of n.evidence) if (!hit.evidence.some((x) => x.eventId === e.eventId && x.role === e.role)) hit.evidence.push(e);
      return hit;
    }
    const made: GNode = { issueIds: [], slot: null, slotInScope: null, lifecycle: null, status: null, recalled: null, attrs: {}, ...n };
    nodes.set(n.id, made);
    return made;
  };
  const edge = (e: Omit<GEdge, "id">): void => {
    const id = `${e.kind}|${e.from}|${e.to}`;
    if (!edges.has(id)) edges.set(id, { id, ...e });
  };
  const issue = (kind: string, severity: Severity, nodeIds: string[], message: string, evidence: EvidenceRef[]): void => {
    const id = `${kind}|${nodeIds.join(",")}|${evidence.map((e) => e.eventId).join(",")}`;
    if (issues.has(id)) return;
    issues.set(id, { id, kind, severity, nodeIds, message, evidence });
    for (const n of nodeIds) nodes.get(n)?.issueIds.push(id);
  };

  const affectedSlots = snap.recall.affectedSlots ?? [];
  const affectedLots = new Set(snap.recall.affectedLots ?? []);
  const selectionNamed = selection.kind === "BEARING_LOT" ? affectedLots.has(selection.id) : null;

  // ---------------------------------------------------------------- roots
  const mfgRoots = new Set<string>();   // `${unitId}|${eventId}` of BEARING_MANUFACTURED events in the trace
  const bearingLotsInTrace = new Set<string>();
  if (known) {
    for (const { unit, byId } of index.values()) {
      for (const e of unit.events) {
        if (e.eventType !== "BEARING_MANUFACTURED") continue;
        if (selection.kind === "BEARING_LOT") {
          if (e.payload.lot === selection.id) mfgRoots.add(`${unit.unitId}|${e.eventId}`);
        } else {
          const alloc = byId.get(String(e.payload.materialEventId ?? ""));
          const viaRef = alloc?.eventType === "MATERIAL_ALLOCATED" && alloc.payload.rawMaterialLot === selection.id;
          if (viaRef || e.payload.rawMaterialLot === selection.id) mfgRoots.add(`${unit.unitId}|${e.eventId}`);
        }
      }
    }
  }
  const selectedLots = (): Set<string> => {
    const s = new Set<string>();
    if (selection.kind === "BEARING_LOT") s.add(selection.id);
    else for (const key of mfgRoots) {
      const [u, id] = key.split("|");
      const lot = str(index.get(u)?.byId.get(id)?.payload.lot);
      if (lot) s.add(lot);
    }
    return s;
  };
  const traceLots = selectedLots();

  // ---------------------------------------------------------------- per unit
  const connected = new Set<string>();        // motors with a component in the trace
  const claimOnly = new Set<string>();
  const installRefCount = new Map<string, string[]>(); // `${unit}|${mfgId}` -> install ids

  for (const { unit, byId } of index.values()) {
    if (!known) break;
    const installs = unit.events.filter((e) => e.eventType === "COMPONENT_INSTALLED");
    for (const inst of installs) {
      const mRef = str(inst.payload.manufacturingEventId);
      const mEvent = mRef ? byId.get(mRef) : undefined;
      const linkedMfg = mEvent?.eventType === "BEARING_MANUFACTURED" ? mEvent : undefined;
      const inTraceViaMfg = !!linkedMfg && mfgRoots.has(`${unit.unitId}|${linkedMfg.eventId}`);
      const lotClaim = str(inst.payload.lot);
      const inTraceViaClaim = selection.kind === "BEARING_LOT" && lotClaim === selection.id;
      if (!inTraceViaMfg && !inTraceViaClaim) continue;

      const comp = compByKey.get(`${unit.unitId}|${inst.eventId}`);
      const slot = str(inst.payload.slot);
      const cid = `cmp:${unit.unitId}:${inst.eventId}`;
      const lifecycle: GNode["lifecycle"] = !comp ? "UNKNOWN" : comp.supersededBy ? "SUPERSEDED" : comp.removedAt ? "HISTORICAL" : "CURRENT";
      const removal = comp?.removalEventId ? byId.get(comp.removalEventId) : undefined;
      const c = node({
        id: cid, kind: "COMPONENT", label: `${slot ?? "slot ?"} · ${str(inst.payload.serial) ?? "lot identity only"}`,
        sublabel: `lot ${lotClaim ?? "not recorded"} · ${lifecycle === "CURRENT" ? "currently recorded" : lifecycle === "HISTORICAL" ? "removed (historical)" : lifecycle === "SUPERSEDED" ? "record superseded" : "no relationship row"}`,
        unitId: unit.unitId, evidence: [ref(unit.unitId, inst, "Installation record"), ...(removal ? [ref(unit.unitId, removal, "Removal record")] : [])],
        slot, slotInScope: slot ? affectedSlots.includes(slot) : null, lifecycle,
        attrs: {
          part: str(inst.payload.part), lot: lotClaim, serial: str(inst.payload.serial), identityGranularity: str(inst.payload.identityGranularity),
          installedAt: inst.occurredAt, removedAt: comp?.removedAt ?? null, timeSource: inst.timeSource,
          removalRecordedAfterShipment: removal && unit.shipment ? String(removal.occurredAt > unit.shipment.shippedAt) : null,
        },
      });
      connected.add(unit.unitId);
      const m = node({
        id: `motor:${unit.unitId}`, kind: "MOTOR", label: unit.unitId, sublabel: unit.title, unitId: unit.unitId, evidence: [],
        attrs: { motorSerial: unit.motorSerial, recordedEvents: String(unit.events.length) },
      });
      edge({ from: c.id, to: m.id, kind: "COMPONENT_IN_MOTOR", style: "RECORDED", basis: "COMPONENT_INSTALLED event of this motor", evidence: [ref(unit.unitId, inst, "Installation record")], historical: lifecycle !== "CURRENT" });

      if (mRef && linkedMfg) {
        const key = `${unit.unitId}|${linkedMfg.eventId}`;
        installRefCount.set(key, [...(installRefCount.get(key) ?? []), c.id]);
        const mfgId = `mfg:${unit.unitId}:${linkedMfg.eventId}`;
        const mfgLot = str(linkedMfg.payload.lot);
        const mismatch = mfgLot !== lotClaim;
        edge({
          from: mfgId, to: c.id, kind: "MANUFACTURE_TO_COMPONENT", style: mismatch ? "CONFLICT" : "RECORDED",
          basis: "COMPONENT_INSTALLED.payload.manufacturingEventId", evidence: [ref(unit.unitId, inst, "Installation record"), ref(unit.unitId, linkedMfg, "Manufacture record")], historical: lifecycle !== "CURRENT",
        });
        // node for the manufacture is created in the manufacture pass below
        if (mismatch) issue("LOT_MISMATCH", "CONFLICT", [c.id], `The installation records lot ${lotClaim ?? "none"} but the manufacture record it references records lot ${mfgLot ?? "none"}. The ledger contradicts itself; neither lot is confirmed.`, [ref(unit.unitId, inst, "Installation record"), ref(unit.unitId, linkedMfg, "Manufacture record")]);
        mfgRoots.add(key); // referenced manufacture belongs to the trace even when lots differ
      } else {
        issue("MISSING_MANUFACTURE_LINK", "UNCERTAIN", [c.id],
          mRef ? `The installation names manufacture record ${mRef}, which is not in this motor's records. The component is tied to lot ${lotClaim ?? "none"} only by the lot written on the installation.`
            : `The installation names no manufacture record. The component is tied to lot ${lotClaim ?? "none"} only by the lot written on the installation, so material origin cannot be traced from the records.`,
          [ref(unit.unitId, inst, "Installation record")]);
        if (lotClaim) {
          bearingLotsInTrace.add(lotClaim);
          edge({ from: `lot:${lotClaim}`, to: c.id, kind: "LOT_CLAIM_ON_COMPONENT", style: "LOT_CLAIM", basis: "COMPONENT_INSTALLED.payload.lot (no manufacture record linked)", evidence: [ref(unit.unitId, inst, "Installation record")], historical: lifecycle !== "CURRENT" });
        }
      }
      if (str(inst.payload.identityGranularity) === "LOT") issue("LOT_IDENTITY_ONLY", "INFO", [c.id], "This component is recorded at lot level only (no serial). The record cannot tie it to one physical bearing.", [ref(unit.unitId, inst, "Installation record")]);
      if (lifecycle === "HISTORICAL") issue("REMOVED_NOT_ELIMINATED", "INFO", [c.id], "Recorded as removed. The ledger does not record where the removed bearing went, so removal does not show that exposure ended.", removal ? [ref(unit.unitId, removal, "Removal record")] : []);
      if (lifecycle === "SUPERSEDED") issue("RECORD_SUPERSEDED", "UNCERTAIN", [c.id], "This installation record was later corrected by another record. Both are kept; the ledger does not say which reflects the physical state.", [ref(unit.unitId, inst, "Installation record")]);
      if (slot && !affectedSlots.includes(slot) && affectedSlots.length > 0) issue("SLOT_OUTSIDE_SCOPE", "INFO", [c.id], `Slot ${slot} is not named by this recall's scope (${affectedSlots.join(", ")}). It is shown because the lot is recorded there.`, [ref(unit.unitId, inst, "Installation record")]);
    }

    // manufacture nodes and their upstream links
    for (const key of [...mfgRoots].filter((k) => k.startsWith(`${unit.unitId}|`))) {
      const mfg = byId.get(key.slice(unit.unitId.length + 1));
      if (!mfg) continue;
      const mfgId = `mfg:${unit.unitId}:${mfg.eventId}`;
      const lot = str(mfg.payload.lot);
      const m = node({
        id: mfgId, kind: "MANUFACTURE", label: str(mfg.payload.serial) ?? "lot-level manufacture", sublabel: `lot ${lot ?? "not recorded"} · ${unit.unitId}`, unitId: unit.unitId,
        evidence: [ref(unit.unitId, mfg, "Manufacture record")], attrs: { part: str(mfg.payload.part), lot, serial: str(mfg.payload.serial), recordedAt: mfg.occurredAt, timeSource: mfg.timeSource },
      });
      if (lot) {
        bearingLotsInTrace.add(lot);
        edge({ from: `lot:${lot}`, to: m.id, kind: "LOT_TO_MANUFACTURE", style: "RECORDED", basis: "BEARING_MANUFACTURED.payload.lot", evidence: [ref(unit.unitId, mfg, "Manufacture record")], historical: false });
      }
      const matRef = str(mfg.payload.materialEventId);
      const alloc = matRef ? byId.get(matRef) : undefined;
      if (alloc?.eventType === "MATERIAL_ALLOCATED" && str(alloc.payload.rawMaterialLot)) {
        const raw = String(alloc.payload.rawMaterialLot);
        const supplier = str(alloc.payload.supplierName);
        const r = node({ id: `raw:${raw}`, kind: "RAW_LOT", label: raw, sublabel: "raw-material claim", unitId: null, evidence: [ref(unit.unitId, alloc, "Material allocation record")], attrs: { suppliers: supplier ?? "not recorded" } });
        const seen = new Set((r.attrs.suppliers ?? "").split("; ").filter((x) => x && x !== "not recorded"));
        if (supplier && !seen.has(supplier)) { seen.add(supplier); r.attrs.suppliers = [...seen].sort().join("; "); }
        edge({ from: r.id, to: m.id, kind: "ALLOCATION_TO_MANUFACTURE", style: "RECORDED", basis: "BEARING_MANUFACTURED.payload.materialEventId", evidence: [ref(unit.unitId, mfg, "Manufacture record"), ref(unit.unitId, alloc, "Material allocation record")], historical: false });
      } else {
        issue("MISSING_MATERIAL_LINK", "UNCERTAIN", [m.id], matRef ? `The manufacture record names material record ${matRef}, which is not in this motor's records.` : `The manufacture record names no material allocation record${str(mfg.payload.rawMaterialLot) ? `; it writes raw-material lot ${String(mfg.payload.rawMaterialLot)} on itself but that is not linked to an allocation record` : ""}. The raw-material origin cannot be traced from the records.`, [ref(unit.unitId, mfg, "Manufacture record")]);
      }
    }
  }

  for (const [key, comps] of installRefCount) {
    if (comps.length < 2) continue;
    const [u, id] = key.split("|");
    const e = index.get(u)?.byId.get(id);
    issue("DUPLICATE_REFERENCE", "CONFLICT", [...comps, `mfg:${u}:${id}`], `${comps.length} installation records reference the same manufacture record. One manufacture record cannot account for ${comps.length} installations; the ledger does not say which is right.`, e ? [{ unitId: u, eventId: id, role: "Manufacture record" }] : []);
  }

  // manufactured under the trace but with no installation record
  for (const key of mfgRoots) {
    const [u, id] = key.split("|");
    if ((installRefCount.get(key) ?? []).length === 0 && nodes.has(`mfg:${u}:${id}`)) {
      issue("MANUFACTURED_NOT_INSTALLED", "UNCERTAIN", [`mfg:${u}:${id}`], "A manufacture record exists under this lot but no installation record references it. Where this bearing went is not recorded.", [{ unitId: u, eventId: id, role: "Manufacture record" }]);
    }
  }

  // bearing-lot nodes
  for (const lot of [...bearingLotsInTrace].sort()) {
    const meta = snap.lots.find((l) => l.lotId === lot);
    node({
      id: `lot:${lot}`, kind: "BEARING_LOT", label: `Lot ${lot}`, sublabel: current ? (affectedLots.has(lot) ? "named by the recall" : "not named by the recall") : "recall status withheld", unitId: null, evidence: [],
      attrs: { part: meta?.part ?? null }, recalled: current ? affectedLots.has(lot) : null,
    });
  }
  // supplier claims that disagree for one raw-material lot
  for (const n of nodes.values()) {
    if (n.kind === "RAW_LOT" && (n.attrs.suppliers ?? "").includes("; ")) issue("SUPPLIER_CLAIM_CONFLICT", "CONFLICT", [n.id], `Different supplier names are recorded for raw-material lot ${n.label}: ${n.attrs.suppliers}. These are unverified claims.`, n.evidence);
  }

  // motors named only by a rejected observation of a lot in the trace (no component link)
  if (current && known) {
    for (const { unit, byId } of index.values()) {
      for (const o of decisionOf(unit.unitId)?.untrustedObservations ?? []) {
        const lot = str(o.observed.lot);
        if (!lot || !traceLots.has(lot) || !byId.has(o.eventId)) continue;
        node({ id: `motor:${unit.unitId}`, kind: "MOTOR", label: unit.unitId, sublabel: unit.title, unitId: unit.unitId, evidence: [], attrs: { motorSerial: unit.motorSerial, recordedEvents: String(unit.events.length) } });
      }
    }
  }

  // shipments and statuses (motors in the trace)
  for (const m of [...nodes.values()].filter((n) => n.kind === "MOTOR")) {
    const { unit, byId } = index.get(m.unitId!)!;
    const d = decisionOf(unit.unitId);
    if (current && d) {
      m.status = { finding: d.evidenceFinding, action: d.operationalAction, reviewRequired: d.reviewRequired, decisionId: d.decisionId, version: typeof d.version === "number" ? d.version : null, withdrawnExclusion: d.reasonCodes.includes("PRIOR_EXCLUSION_WITHDRAWN"), reasonCodes: [...d.reasonCodes] };
      if (m.status.withdrawnExclusion) issue("EXCLUSION_WITHDRAWN", "UNCERTAIN", [m.id], "An earlier release-eligible decision for this motor was withdrawn after later evidence arrived.", []);
      const missing = d.evidenceEventIds.filter((id) => !byId.has(id));
      if (missing.length) issue("DECISION_CITES_MISSING_RECORDS", "UNCERTAIN", [m.id], `The decision cites ${missing.length} record(s) that are not in this motor's records.`, missing.map((eventId) => ({ unitId: unit.unitId, eventId, role: "Cited by the decision" })));
      for (const a of d.slotAttribution ?? []) if (a.ambiguous && !a.cleared) issue("AMBIGUOUS_SLOT", "UNCERTAIN", [m.id], `A removal of this lot cannot be tied to one slot (candidates ${a.candidates.map((c) => c.slot).join(" or ")}). Nothing independent shows which slot it came from.`, a.supportingEventIds.map((eventId) => ({ unitId: unit.unitId, eventId, role: "Supports the attribution" })));
      for (const [slot, s] of Object.entries(d.slots)) {
        if (s.policyRelevance === "NOT_IN_POLICY_SCOPE") continue;
        for (const g of s.gaps ?? []) if (g.materiality === "MATERIAL") issue("CAPTURE_GAP", "UNCERTAIN", [m.id], `Capture gap in slot ${slot}${g.from ? ` from ${g.from}` : ""}${g.to ? ` to ${g.to}` : ""}. Records may be incomplete for that period; absence of records is not evidence that nothing happened.`, []);
      }
      // untrusted observations that name a lot in the trace
      for (const o of d.untrustedObservations ?? []) {
        const lot = str(o.observed.lot);
        const ev = byId.get(o.eventId);
        if (!lot || !traceLots.has(lot) || !ev) continue;
        const oid = `obs:${unit.unitId}:${o.eventId}`;
        node({ id: oid, kind: "OBSERVATION", label: `Rejected observation · ${o.slot ?? "slot ?"}`, sublabel: `claims lot ${lot} · ${o.status.toLowerCase()}`, unitId: unit.unitId, evidence: [ref(unit.unitId, ev, "Observation record")], slot: o.slot ?? null, slotInScope: o.slot ? affectedSlots.includes(o.slot) : null, attrs: { observedLot: lot, status: o.status, rejectedReasons: (o.rejectedReasons ?? []).join(", ") || null, method: str(ev.payload.method) } });
        bearingLotsInTrace.add(lot);
        node({ id: `lot:${lot}`, kind: "BEARING_LOT", label: `Lot ${lot}`, sublabel: affectedLots.has(lot) ? "named by the recall" : "not named by the recall", unitId: null, evidence: [], attrs: {}, recalled: affectedLots.has(lot) });
        edge({ from: `lot:${lot}`, to: oid, kind: "OBSERVED_LOT_CLAIM", style: "UNTRUSTED_CLAIM", basis: "SLOT_STATE_VERIFIED.payload.observedLot (rejected as evidence)", evidence: [ref(unit.unitId, ev, "Observation record")], historical: false });
        edge({ from: oid, to: m.id, kind: "OBSERVATION_ON_MOTOR", style: "UNTRUSTED_CLAIM", basis: "SLOT_STATE_VERIFIED event of this motor", evidence: [ref(unit.unitId, ev, "Observation record")], historical: false });
        issue("UNTRUSTED_OBSERVATION", "UNCERTAIN", [oid, m.id], `A record claims lot ${lot} in slot ${o.slot ?? "?"} but was rejected as evidence (${(o.rejectedReasons ?? []).join(", ") || "untrusted"}). It is shown as a claim, not as a confirmed link.`, [ref(unit.unitId, ev, "Observation record")]);
        if (!connected.has(unit.unitId)) claimOnly.add(unit.unitId);
      }
    }
    const sh = unit.shipment;
    if (sh) {
      const shipEvent = typeof sh.evidenceEventId === "string" ? byId.get(sh.evidenceEventId) : undefined;
      if (sh.backedByLedger === true && shipEvent?.eventType === "MOTOR_SHIPPED") {
        const sid = `ship:${unit.unitId}:${sh.shipmentId}`;
        node({ id: sid, kind: "SHIPMENT", label: sh.shipmentId, sublabel: `shipment recorded ${sh.shippedAt}`, unitId: unit.unitId, evidence: [ref(unit.unitId, shipEvent, "Shipment record")], attrs: { shippedAt: sh.shippedAt, timeSource: shipEvent.timeSource } });
        edge({ from: m.id, to: sid, kind: "MOTOR_SHIPMENT", style: "RECORDED", basis: "MOTOR_SHIPPED event named by the unit's shipment record", evidence: [ref(unit.unitId, shipEvent, "Shipment record")], historical: false });
      } else {
        issue("SHIPMENT_NOT_LEDGER_BACKED", "UNCERTAIN", [m.id], "A shipment is attached to this motor but no ledger shipment record backs it, so it is not drawn.", []);
      }
    }
  }

  // ---------------------------------------------------------------- summary
  const motorNodes = [...nodes.values()].filter((n) => n.kind === "MOTOR");
  const linked = motorNodes.filter((m) => connected.has(m.unitId!));
  const byFinding = current ? Object.fromEntries(FINDINGS.map((f) => [f, linked.filter((m) => m.status?.finding === f).length])) : null;
  const shipped = linked.filter((m) => nodes.has(`ship:${m.unitId}:${index.get(m.unitId!)!.unit.shipment?.shipmentId}`));
  const shipmentsByFinding = current ? Object.fromEntries(FINDINGS.map((f) => [f, shipped.filter((m) => m.status?.finding === f).length])) : null;
  const comps = [...nodes.values()].filter((n) => n.kind === "COMPONENT");
  const sev: Record<Severity, number> = { INFO: 0, UNCERTAIN: 0, CONFLICT: 0 };
  for (const i of issues.values()) sev[i.severity]++;
  const f = snap.freshness;

  const nodeList = [...nodes.values()].sort((a, b) => cmp(a.id, b.id));
  const edgeList = [...edges.values()].sort((a, b) => cmp(a.id, b.id));
  return {
    selection, knownSelection: known, recallStatus: current ? "CURRENT" : "WITHHELD",
    scope: {
      recallId: snap.recall.recallId, policyId, affectedPart: snap.recall.affectedPart, affectedLots: [...affectedLots].sort(), affectedSlots: [...affectedSlots],
      exposureBasis: str(policy?.exposureBasis), scopeDeclaration: str(recallInfo.scopeDeclaration), announcedAt: snap.recall.announcedAt, announced: snap.recallAnnounced !== false && !!snap.recall.announcedAt,
      selectionNamedByRecall: selectionNamed,
    },
    nodes: nodeList, edges: edgeList, issues: [...issues.values()].sort((a, b) => cmp(a.id, b.id)),
    summary: {
      motors: linked.length, byFinding, claimOnlyMotors: claimOnly.size, shipmentsRecorded: shipped.length, shipmentsByFinding,
      unshippedMotors: linked.length - shipped.length, currentComponents: comps.filter((c) => c.lifecycle === "CURRENT").length, historicalComponents: comps.filter((c) => c.lifecycle === "HISTORICAL" || c.lifecycle === "SUPERSEDED").length, issues: sev,
    },
    watermark: { status: f?.status ?? "NO_FRESHNESS_METADATA", sequence: f?.sequence ?? null, headHash: f?.headHash ?? null, verifiedAt: f?.verifiedAt ?? null, ledgerEvents: units.reduce((n, u) => n + u.events.length, 0) },
  };
}

// ------------------------------------------------------------------- tracing and filtering
export type TraceDirection = "FORWARD" | "BACKWARD" | "BOTH";

/** Nodes and edges reachable from a node along recorded edges (raw -> ... -> shipment is forward). */
const adjacency = new WeakMap<ImpactGraph, { out: Map<string, GEdge[]>; inn: Map<string, GEdge[]> }>();
function adjacencyOf(g: ImpactGraph) {
  let a = adjacency.get(g);
  if (!a) {
    a = { out: new Map(), inn: new Map() };
    for (const e of g.edges) {
      (a.out.get(e.from) ?? a.out.set(e.from, []).get(e.from)!).push(e);
      (a.inn.get(e.to) ?? a.inn.set(e.to, []).get(e.to)!).push(e);
    }
    adjacency.set(g, a);
  }
  return a;
}

/** Nodes and edges reachable from a node along recorded edges (raw -> ... -> shipment is forward). */
export function trace(g: ImpactGraph, nodeId: string, dir: TraceDirection): { nodeIds: Set<string>; edgeIds: Set<string> } {
  const { out, inn } = adjacencyOf(g);
  const nodeIds = new Set<string>([nodeId]);
  const edgeIds = new Set<string>();
  const walk = (forward: boolean) => {
    const queue = [nodeId];
    const seen = new Set(queue);
    while (queue.length) {
      const cur = queue.pop()!;
      for (const e of (forward ? out : inn).get(cur) ?? []) {
        const next = forward ? e.to : e.from;
        edgeIds.add(e.id);
        if (!seen.has(next)) { seen.add(next); nodeIds.add(next); queue.push(next); }
      }
    }
  };
  if (dir !== "BACKWARD") walk(true);
  if (dir !== "FORWARD") walk(false);
  return { nodeIds, edgeIds };
}

/** Keep motors with a chosen finding, plus everything recorded upstream and downstream of them. */
export function filterByFinding(g: ImpactGraph, keep: ReadonlySet<string>): { nodeIds: Set<string>; hiddenMotors: number } {
  const motors = g.nodes.filter((n) => n.kind === "MOTOR");
  const kept = motors.filter((m) => m.status && keep.has(m.status.finding));
  const nodeIds = new Set<string>();
  for (const m of kept) for (const id of trace(g, m.id, "BOTH").nodeIds) nodeIds.add(id);
  return { nodeIds, hiddenMotors: motors.length - kept.length };
}
