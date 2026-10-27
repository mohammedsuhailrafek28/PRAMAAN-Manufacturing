// Pure derivations for the overview charts. Every value comes from fields the backend snapshot returned; nothing is estimated or defaulted to a measurement.
import type { LedgerEvent, Snapshot } from "./types";

export const EVENT_LABEL: Record<string, string> = {
  WORK_ORDER_OPENED: "Work order opened", WORK_ORDER_CLOSED: "Work order closed", MATERIAL_ALLOCATED: "Material allocated", BEARING_MANUFACTURED: "Bearing manufactured",
  COMPONENT_INSTALLED: "Component installed", COMPONENT_REMOVED: "Component removed", SLOT_STATE_VERIFIED: "Slot state verified", MOTOR_SHIPPED: "Motor shipped",
};
export const EVENT_COLOR: Record<string, string> = {
  WORK_ORDER_OPENED: "#6b7a89", WORK_ORDER_CLOSED: "#3c4a58", MATERIAL_ALLOCATED: "#0b5f9e", BEARING_MANUFACTURED: "#2f7fb8", COMPONENT_INSTALLED: "#ad7944",
  COMPONENT_REMOVED: "#ba1a1a", SLOT_STATE_VERIFIED: "#8a5300", MOTOR_SHIPPED: "#17663a",
};
const ORDER = Object.keys(EVENT_LABEL);
export const evLabel = (t: string) => EVENT_LABEL[t] ?? t.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase());
export const evColor = (t: string) => EVENT_COLOR[t] ?? "#6b7a89";

export type Flat = { unitId: string; e: LedgerEvent; t: number | null };
export const flatEvents = (s: Snapshot): Flat[] => s.units.flatMap((u) => (u.events ?? []).map((e) => ({ unitId: u.unitId, e, t: e.occurredAt && !Number.isNaN(Date.parse(e.occurredAt)) ? Date.parse(e.occurredAt) : null })));
export const eventTypes = (f: Flat[]) => [...new Set(f.map((x) => x.e.eventType))].sort((a, b) => (ORDER.indexOf(a) + 1 || 99) - (ORDER.indexOf(b) + 1 || 99) || a.localeCompare(b));
export const timeSources = (f: Flat[]) => [...new Set(f.map((x) => x.e.timeSource).filter(Boolean) as string[])];

/** Heatmap: record count per motor per event type. 0 means no such record in the ledger snapshot, not proof that it never happened. */
export function completeness(s: Snapshot, f: Flat[]) {
  const types = eventTypes(f);
  const rows = s.units.map((u) => ({ unitId: u.unitId, cells: types.map((t) => f.filter((x) => x.unitId === u.unitId && x.e.eventType === t).length) }));
  return { types, rows, max: Math.max(1, ...rows.flatMap((r) => r.cells)) };
}

export type QcState = "PASS" | "FAIL" | "NO_RECORD";
const PASS = new Set(["PASS", "PASSED", "ACCEPT", "ACCEPTED", "OK"]), FAIL = new Set(["FAIL", "FAILED", "REJECT", "REJECTED", "NOK"]);
/** A QC result exists only if the ledger holds an inspection/quality/test event whose payload carries an explicit outcome. Anything else is "no record", never a pass. */
export function qcStates(s: Snapshot, f: Flat[]) {
  const per = s.units.map((u) => {
    const evs = f.filter((x) => x.unitId === u.unitId && /INSPECT|QUALITY|TEST|MEASURE/.test(x.e.eventType)).sort((a, b) => (a.t ?? 0) - (b.t ?? 0));
    let state: QcState = "NO_RECORD", eventId: string | undefined;
    for (const x of evs) {
      const p = (x.e.payload ?? {}) as Record<string, unknown>;
      const v = String(p.result ?? p.outcome ?? p.verdict ?? p.disposition ?? "").toUpperCase();
      if (PASS.has(v)) { state = "PASS"; eventId = x.e.eventId; } else if (FAIL.has(v)) { state = "FAIL"; eventId = x.e.eventId; }
    }
    return { unitId: u.unitId, state, eventId };
  });
  const count = (k: QcState) => per.filter((p) => p.state === k).length;
  const related = {
    workOrdersClosed: f.filter((x) => x.e.eventType === "WORK_ORDER_CLOSED").length,
    labelReads: f.filter((x) => x.e.eventType === "SLOT_STATE_VERIFIED").length,
    provisionalLabelReads: f.filter((x) => x.e.eventType === "SLOT_STATE_VERIFIED" && (x.e.payload as Record<string, unknown> | undefined)?.provisional === true).length,
  };
  return { per, PASS: count("PASS"), FAIL: count("FAIL"), NO_RECORD: count("NO_RECORD"), related };
}

const STEPS = [60e3, 120e3, 300e3, 600e3, 900e3, 1800e3, 3600e3, 3 * 3600e3, 6 * 3600e3, 12 * 3600e3, 86400e3];
export const stepLabel = (ms: number) => (ms >= 86400e3 ? `${ms / 86400e3} d` : ms >= 3600e3 ? `${ms / 3600e3} h` : `${ms / 60e3} min`);
export type Bin = { a: number; b: number; events: Flat[]; count: number };
export type Burst = { a: number; b: number; first: number; last: number; bins: Bin[] };

/** Bursts are runs of events separated by <= gapMs. The gaps between bursts hold no events and are never binned or drawn as activity. All bursts share one bin width. Counts honour the type filter; the burst layout does not, so the axis stays put while filtering. */
export function activity(flat: Flat[], hidden: Set<string>, gapMs = 6 * 3600e3) {
  const timed = flat.filter((x) => x.t !== null).sort((p, q) => (p.t as number) - (q.t as number));
  const groups: Flat[][] = [];
  for (const x of timed) { const g = groups[groups.length - 1]; if (g && (x.t as number) - (g[g.length - 1].t as number) <= gapMs) g.push(x); else groups.push([x]); }
  const widest = Math.max(0, ...groups.map((g) => (g[g.length - 1].t as number) - (g[0].t as number)));
  const step = STEPS.find((s) => widest / s <= 20) ?? STEPS[STEPS.length - 1];
  const bursts: Burst[] = groups.map((g) => {
    const a = Math.floor((g[0].t as number) / step) * step, b = Math.floor((g[g.length - 1].t as number) / step) * step + step;
    const bins: Bin[] = [];
    for (let s0 = a; s0 < b; s0 += step) { const ev = g.filter((x) => (x.t as number) >= s0 && (x.t as number) < s0 + step); bins.push({ a: s0, b: s0 + step, events: ev, count: ev.filter((x) => !hidden.has(x.e.eventType)).length }); }
    return { a, b, first: g[0].t as number, last: g[g.length - 1].t as number, bins };
  });
  return { bursts, step, untimed: flat.length - timed.length, max: Math.max(1, ...bursts.flatMap((u) => u.bins.map((n) => n.count))) };
}
