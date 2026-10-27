// Daily Operations Report model. Pure functions of the gated snapshot: every number is a count of recorded fields, nothing is estimated, defaulted or back-filled.
// Day boundary: UTC calendar day, [00:00:00Z, 24:00:00Z). A missing or unparseable timestamp is "unknown", never assigned a date.
import { confirmationEvents, correctiveEvents } from "./trailModel";
import type { DecisionCurrent, LedgerEvent, Snapshot } from "./types";
import { ACTION_TEXT, FINDING_TEXT, humanize } from "./glossary";
import { currentOf } from "./ui";

export type Basis = "source" | "ingest";
export const BASIS: Record<Basis, { label: string; field: string; help: string }> = {
  source: { label: "Source event time", field: "occurredAt", help: "When the source claims the activity happened (a claim; the clock is not a trusted time source)." },
  ingest: { label: "Local ingestion time", field: "repository.localReceivedAt", help: "When this ledger received the event. It says nothing about when the activity happened." },
};

export const tsOf = (e: LedgerEvent, basis: Basis): string | undefined => (basis === "source" ? e.occurredAt : e.repository?.localReceivedAt) || undefined;
export const dayOf = (ts?: string): string | undefined => { if (!ts) return undefined; const t = Date.parse(ts); return Number.isNaN(t) ? undefined : new Date(t).toISOString().slice(0, 10); };

export type Row = { unitId: string; e: LedgerEvent; ts?: string; day?: string };
const sortRows = (a: Row, b: Row) => (a.ts ?? "").localeCompare(b.ts ?? "") || a.unitId.localeCompare(b.unitId) || (a.e.sourceSeq ?? 0) - (b.e.sourceSeq ?? 0);
export const allRows = (s: Snapshot, basis: Basis): Row[] => s.units.flatMap((u) => (u.events ?? []).map((e) => { const ts = tsOf(e, basis); return { unitId: u.unitId, e, ts, day: dayOf(ts) }; })).sort(sortRows);

const isInspection = (e: LedgerEvent) => e.eventType === "QUALITY_INSPECTION_RECORDED" || e.eventType === "INSPECTION_RECORDED";
const PASS = new Set(["PASS", "PASSED", "ACCEPT", "ACCEPTED", "OK"]), FAIL = new Set(["FAIL", "FAILED", "REJECT", "REJECTED", "NOK"]);
export const outcomeOf = (e: LedgerEvent): "PASS" | "FAIL" | "NO_OUTCOME" => { const v = String((e.payload as Record<string, unknown> | undefined)?.result ?? "").toUpperCase(); return PASS.has(v) ? "PASS" : FAIL.has(v) ? "FAIL" : "NO_OUTCOME"; };

export type Change = { unitId: string; from: DecisionCurrent; to: DecisionCurrent; trigger?: LedgerEvent; triggerTs?: string; day?: string; toCurrent: boolean; addedReasons: string[]; removedReasons: string[] };
const histories = (s: Snapshot, unitId: string): DecisionCurrent[] => {
  const per = s.decisions?.[unitId]; if (!per) return [];
  const key = Object.keys(per)[0]; const h = key ? ((per[key].history ?? []) as DecisionCurrent[]) : [];
  return [...h].sort((a, b) => (a.version ?? 0) - (b.version ?? 0));
};
/** Version transitions from the backend's own history. A change is dated only through its trigger event's timestamp on the chosen basis; the decision itself carries no timestamp. */
export function changesOf(s: Snapshot, basis: Basis): Change[] {
  const out: Change[] = [];
  for (const u of s.units) {
    const h = histories(s, u.unitId), byId = new Map((u.events ?? []).map((e) => [e.eventId, e]));
    for (let i = 1; i < h.length; i++) {
      const trigger = h[i].triggerEventId ? byId.get(h[i].triggerEventId as string) : undefined, ts = trigger ? tsOf(trigger, basis) : undefined;
      const a = h[i - 1].reasonCodes ?? [], b = h[i].reasonCodes ?? [];
      out.push({ unitId: u.unitId, from: h[i - 1], to: h[i], trigger, triggerTs: ts, day: dayOf(ts), toCurrent: currentOf(s, u.unitId)?.decisionId === h[i].decisionId, addedReasons: b.filter((c) => !a.includes(c)), removedReasons: a.filter((c) => !b.includes(c)) });
    }
  }
  return out;
}

export function buildReport(s: Snapshot, date: string, basis: Basis, allowed: boolean) {
  const rows = allRows(s, basis);
  const dates = [...rows.reduce((m, r) => (r.day ? m.set(r.day, (m.get(r.day) ?? 0) + 1) : m), new Map<string, number>())].sort((a, b) => a[0].localeCompare(b[0]));
  const unknown = rows.filter((r) => !r.day).length;
  const day = rows.filter((r) => r.day === date);
  const inDay = new Set(day.map((r) => r.e.eventId));

  const byType = [...day.reduce((m, r) => m.set(r.e.eventType, (m.get(r.e.eventType) ?? 0) + 1), new Map<string, number>())].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const motorsActive = [...new Set(day.map((r) => r.unitId))];

  const insp = day.filter((r) => isInspection(r.e)), inspOut = insp.map((r) => outcomeOf(r.e));
  const qc = { pass: inspOut.filter((x) => x === "PASS").length, fail: inspOut.filter((x) => x === "FAIL").length, noOutcome: inspOut.filter((x) => x === "NO_OUTCOME").length, total: insp.length,
    motorsWithoutRecord: s.units.map((u) => u.unitId).filter((m) => !insp.some((r) => r.unitId === m)) };

  const corr = s.units.flatMap((u) => correctiveEvents(u.events ?? []).filter((e) => inDay.has(e.eventId)).map((e) => ({ unitId: u.unitId, e })));
  const orders = new Set(corr.map((c) => `${c.unitId}|${c.e.workOrderId ?? ""}`).filter((k) => !k.endsWith("|")));

  const all = allowed ? changesOf(s, basis) : [];
  const changesDay = all.filter((c) => c.day === date), undated = all.filter((c) => !c.day);

  const motorRows = s.units.map((u) => {
    const ev = u.events ?? [];
    const cEv = correctiveEvents(ev).filter((e) => inDay.has(e.eventId)), vEv = confirmationEvents(ev).filter((e) => inDay.has(e.eventId));
    const ch = changesDay.filter((c) => c.unitId === u.unitId);
    const h = allowed ? histories(s, u.unitId) : [];
    return { unitId: u.unitId, corrective: cEv, verification: vEv, changes: ch, initial: h[0], current: allowed ? currentOf(s, u.unitId) : undefined, relevant: cEv.length > 0 || vEv.length > 0 || insp.some((r) => r.unitId === u.unitId) || ch.length > 0 };
  }).filter((r) => r.relevant);

  const cur = allowed ? s.units.map((u) => ({ unitId: u.unitId, d: currentOf(s, u.unitId) })) : [];
  const risks = {
    affected: cur.filter((x) => x.d?.evidenceFinding === "AFFECTED"), unresolved: cur.filter((x) => x.d?.evidenceFinding === "UNRESOLVED"),
    excluded: cur.filter((x) => x.d?.evidenceFinding === "EXCLUDED_WITH_EVIDENCE"), holds: cur.filter((x) => x.d?.operationalAction === "RECALL_HOLD").length,
  };
  return { rows, dates, unknown, day, byType, motorsActive, qc, corr, orders: orders.size, changesDay, undated, motorRows, risks };
}
export type Report = ReturnType<typeof buildReport>;

export const findingLabel = (v?: string) => (v ? FINDING_TEXT[v]?.label ?? humanize(v) : "No decision");
export const actionLabel = (v?: string) => (v ? ACTION_TEXT[v]?.label ?? humanize(v) : "");
/** A superseded decision that had made the motor release eligible: historical, no longer in force. */
export const isWithdrawnRelease = (d?: DecisionCurrent) => d?.operationalAction === "RELEASE_ELIGIBLE";
export const shortId = (id: string) => { const x = id.replace("urn:pramaan:", ""); return x.length > 22 ? `${x.slice(0, 10)}…${x.slice(-10)}` : x; };

export type Kpi = { id: string; label: string; value: string; sub: string };
/** The six executive KPIs. The page and the PDF both render this one list, so their numbers cannot differ. */
export function kpisOf(r: Report, allowed: boolean, motorCount: number, gateLabel: string): Kpi[] {
  return [
    { id: "kpi-events", label: "Events recorded", value: String(r.day.length), sub: `${r.motorsActive.length} of ${motorCount} motors` },
    { id: "kpi-motors", label: "Motors with activity", value: String(r.motorsActive.length), sub: r.motorsActive.join(", ") || "none" },
    { id: "kpi-insp", label: "Inspection outcomes", value: String(r.qc.pass + r.qc.fail), sub: `${r.qc.pass} pass · ${r.qc.fail} fail · ${r.qc.noOutcome} no outcome` },
    { id: "kpi-corr", label: "Corrective actions", value: String(r.orders), sub: `${r.corr.length} corrective events` },
    { id: "kpi-changes", label: "Decision changes", value: allowed ? String(r.changesDay.length) : "—", sub: allowed ? (r.undated.length ? `${r.undated.length} undated, not counted` : "dated by trigger event") : "withheld" },
    { id: "kpi-holds", label: "Active recall holds", value: allowed ? String(r.risks.holds) : "—", sub: allowed ? "current state, not this date" : `withheld · ${gateLabel}` },
  ];
}
