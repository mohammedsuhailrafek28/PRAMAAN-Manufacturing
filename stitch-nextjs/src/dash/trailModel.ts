// Pure derivation of the Resolution Trail for one motor. Everything is selected from recorded events or backend decisions; nothing is inferred, defaulted or invented.
import type { DecisionCurrent, LedgerEvent } from "./types";

export type Kind = "WO" | "REM" | "MAT" | "MFG" | "INS" | "OBS" | "QC";
const KIND: Record<string, Kind> = {
  WORK_ORDER_OPENED: "WO", WORK_ORDER_CLOSED: "WO", COMPONENT_REMOVED: "REM", COMPONENT_INSTALLED: "INS", MATERIAL_ALLOCATED: "MAT", BEARING_MANUFACTURED: "MFG",
  SLOT_STATE_VERIFIED: "OBS", SLOT_LABEL_SCANNED: "OBS", SLOT_ACCESS_EVIDENCE: "OBS", QUALITY_INSPECTION_RECORDED: "QC", INSPECTION_RECORDED: "QC",
};
export const kindOf = (e: LedgerEvent): Kind => KIND[e.eventType] ?? "WO";
const byTime = (a: LedgerEvent, b: LedgerEvent) => (a.occurredAt ?? "").localeCompare(b.occurredAt ?? "") || (a.recordedAt ?? "").localeCompare(b.recordedAt ?? "") || (a.sourceSeq ?? 0) - (b.sourceSeq ?? 0);

const p = (e: LedgerEvent) => (e.payload ?? {}) as Record<string, unknown>;

/** Events of rework work orders (orderType REWORK), plus the replacement part's manufacture and material events they cite. */
export function correctiveEvents(events: LedgerEvent[]): LedgerEvent[] {
  const byId = new Map(events.map((e) => [e.eventId, e]));
  const wos = new Set(events.filter((e) => e.eventType === "WORK_ORDER_OPENED" && p(e).orderType === "REWORK" && e.workOrderId).map((e) => e.workOrderId as string));
  const out = new Map<string, LedgerEvent>();
  for (const e of events) if (e.workOrderId && wos.has(e.workOrderId)) out.set(e.eventId, e);
  for (const e of [...out.values()]) {
    const m = typeof p(e).manufacturingEventId === "string" ? byId.get(p(e).manufacturingEventId as string) : undefined;
    if (m) { out.set(m.eventId, m); const mat = typeof p(m).materialEventId === "string" ? byId.get(p(m).materialEventId as string) : undefined; if (mat) out.set(mat.eventId, mat); }
  }
  return [...out.values()].sort(byTime);
}

/** Inspection or verification records of any date. They are claims; none is treated as independent confirmation or clearance. */
export const confirmationEvents = (events: LedgerEvent[]): LedgerEvent[] => events.filter((e) => KIND[e.eventType] === "OBS" || KIND[e.eventType] === "QC").sort(byTime);

export type Assurance = { label: string; weak: boolean };
export function assuranceOf(e: LedgerEvent): Assurance {
  const pl = p(e);
  if (KIND[e.eventType] === "QC") return { label: `Inspection claim: ${String(pl.result ?? "no result stated")}. Not recall clearance`, weak: true };
  if (pl.provisional === true) return { label: `Provisional claim${pl.method ? ` (${String(pl.method).replace(/_/g, " ").toLowerCase()})` : ""}. Untrusted`, weak: true };
  return { label: "Recorded claim", weak: true };
}

export function describe(e: LedgerEvent): string {
  const pl = p(e), slot = pl.slot ? ` ${pl.slot}` : "";
  switch (e.eventType) {
    case "WORK_ORDER_OPENED": return `${String(pl.orderType ?? "").toLowerCase() === "rework" ? "Rework" : "Work"} order opened${e.workOrderId ? ` · ${e.workOrderId}` : ""}`;
    case "WORK_ORDER_CLOSED": return `Work order closed (${String(pl.disposition ?? "no disposition")})${e.workOrderId ? ` · ${e.workOrderId}` : ""}`;
    case "COMPONENT_REMOVED": return `Removed${slot}: lot ${String(pl.observedLot ?? "not recorded")}`;
    case "COMPONENT_INSTALLED": return `Installed${slot}: lot ${String(pl.lot ?? "not recorded")}`;
    case "MATERIAL_ALLOCATED": return `Raw-material lot ${String(pl.rawMaterialLot ?? "not recorded")} allocated`;
    case "BEARING_MANUFACTURED": return `Bearing lot ${String(pl.lot ?? "not recorded")} manufactured`;
    case "SLOT_STATE_VERIFIED": return `Slot${slot} observed: lot ${String(pl.observedLot ?? "not recorded")}`;
    case "QUALITY_INSPECTION_RECORDED": case "INSPECTION_RECORDED": return `Inspection recorded: ${String(pl.result ?? "no result stated")}`;
    default: return e.eventType.replace(/_/g, " ").toLowerCase();
  }
}

export type DecisionPair = { prev?: DecisionCurrent; cur?: DecisionCurrent; versions: DecisionCurrent[] };
/** Backend history only; `cur` is the backend's current decision. Nothing is reconstructed. */
export function pairOf(current: DecisionCurrent | undefined, history: DecisionCurrent[]): DecisionPair {
  const versions = [...history].sort((a, b) => (a.version ?? 0) - (b.version ?? 0));
  const cur = current ?? versions[versions.length - 1];
  const prev = [...versions].reverse().find((v) => v.decisionId !== cur?.decisionId && (v.version ?? 0) < (cur?.version ?? Infinity));
  return { prev, cur, versions };
}
