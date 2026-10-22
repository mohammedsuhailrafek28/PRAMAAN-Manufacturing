// Shared, typed, fail-closed checkpoint/eligibility gate for the standalone pages.
//
// The gate never re-verifies anything the backend verifies (no hashing, replay or checkpoint
// logic). It only refuses to TRUST a response unless the backend's own statement is complete,
// closed-enum, self-consistent and CURRENT. Classification reads structured fields only (HTTP
// status, `state`, `checkpoint.state`, `freshness.status`); it never inspects exception or
// message text. Anything unrecognised is WITHHELD. Historical display is never a fallback for an
// exception: only a well-formed ANCHORED_PREFIX_ONLY / UNANCHORED envelope can be SEGREGATED.
import type { RecallSnapshot } from "../domain/types";
import { validateSnapshot } from "../domain/validate";
import { isCurrentClearance } from "./clearance";
import { clearanceOf, makeGated, makeHistorical, type GatedSnapshot, type HistoricalView, type Watermark } from "./gated";

export type { Watermark };

export type WithheldCause =
  | "ANCHOR_INVALID" | "VERIFYING" | "MISSING_METADATA" | "UNKNOWN_STATE" | "CONTRADICTORY"
  | "LEASE_EXPIRED" | "REGRESSION" | "INTEGRITY" | "TRANSPORT";
// ELIGIBILITY_WITHHELD is deliberately NOT a cause: it is a per-motor presentation outcome (clearanceOf).
export type SegregatedCause = "PREFIX_ONLY" | "UNANCHORED";

export type Gate =
  | { kind: "CURRENT"; view: GatedSnapshot; leaseMs: number }
  | { kind: "SEGREGATED"; cause: SegregatedCause; view: HistoricalView; reason: string }
  | { kind: "WITHHELD"; cause: WithheldCause; reason: string; lastAccepted: Watermark | null };

export const WITHHELD_LABEL: Record<WithheldCause, string> = {
  ANCHOR_INVALID: "the trusted anchor check failed",
  VERIFYING: "verification is still in progress",
  MISSING_METADATA: "required checkpoint or eligibility metadata is missing",
  UNKNOWN_STATE: "the checkpoint state is not recognised",
  CONTRADICTORY: "the checkpoint, freshness and eligibility metadata contradict each other",
  LEASE_EXPIRED: "the verification lease expired or the clocks disagree",
  REGRESSION: "the ledger moved backwards; owner review is required before reloading",
  INTEGRITY: "the response failed integrity validation",
  TRANSPORT: "the backend could not be reached or answered unexpectedly",
};

export const SEGREGATED_REASON: Record<SegregatedCause, string> = {
  PREFIX_ONLY: "Historical evidence only. A new independently protected checkpoint is required; current release eligibility is withheld for every motor.",
  UNANCHORED: "Unverified local historical claims only. No trusted external anchor; nothing here is externally verified or current.",
};

/** The only H2 values the backend contract defines (VERIFIED | UNVERIFIED for an unanchored archive | HISTORICAL_UNVERIFIABLE). Anything else is unknown. */
const KNOWN_H2 = ["VERIFIED", "UNVERIFIED", "HISTORICAL_UNVERIFIABLE"];

/** Thrown by adapters for a WITHHELD gate so pages show a neutral category, never motor findings. */
export class GateWithheldError extends Error {
  constructor(readonly gate: Extract<Gate, { kind: "WITHHELD" }>) { super(gate.reason); this.name = "GateWithheldError"; }
}

const STATES = ["ANCHOR_INVALID", "UNANCHORED", "ANCHORED_PREFIX_ONLY", "ANCHORED_CURRENT"] as const;
const STATUS_FOR: Record<string, string> = {
  ANCHORED_CURRENT: "VERIFIED_ANCHORED_SYNTHETIC",
  ANCHORED_PREFIX_ONLY: "VERIFIED_PREFIX_SYNTHETIC",
  UNANCHORED: "HISTORICAL_UNANCHORED",
};
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,3})?Z$/;

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

export function watermarkOf(snap: RecallSnapshot | null): Watermark | null {
  const f = snap?.freshness;
  return f ? { archiveId: f.archiveId, sequence: f.sequence, verifiedAt: f.verifiedAt } : null;
}

function withheld(cause: WithheldCause, previous: RecallSnapshot | null, detail = ""): Gate {
  const mark = watermarkOf(previous);
  const history = mark ? ` Last accepted watermark (historical, not currently verified): journal sequence ${mark.sequence}${mark.verifiedAt ? `, verified ${mark.verifiedAt}` : ""}.` : "";
  return { kind: "WITHHELD", cause, reason: `Current status unavailable (withheld): ${WITHHELD_LABEL[cause]}.${detail}${history}`, lastAccepted: mark };
}

/** True when `snap` shows the ledger going backwards relative to `previous` (same checks as the
 *  application gate: archive, journal version, head, evidence watermark, decision versions). */
function regressed(snap: RecallSnapshot, previous: RecallSnapshot): boolean {
  const f = snap.freshness!; const old = previous.freshness;
  if (!old) return false;
  if (f.archiveId !== old.archiveId || f.sequence < old.sequence || (f.sequence === old.sequence && f.headHash !== old.headHash)) return true;
  if (f.verifiedAt && old.verifiedAt && Date.parse(f.verifiedAt) < Date.parse(old.verifiedAt)) return true;
  for (const unit of previous.units) {
    const next = snap.units.find((u) => u.unitId === unit.unitId);
    if (!next) return true;
    for (const e of unit.events) {
      if (!next.events.some((x) => x.eventId === e.eventId && x.sourceId === e.sourceId && x.sourceSeq === e.sourceSeq)) return true;
    }
    for (const [policy, bundle] of Object.entries(previous.decisions[unit.unitId] ?? {})) {
      const cur = snap.decisions[unit.unitId]?.[policy]?.current;
      if (!cur || typeof cur.version !== "number" || typeof bundle.current.version !== "number" || cur.version < bundle.current.version
        || (cur.version === bundle.current.version && cur.decisionId !== bundle.current.decisionId)) return true;
    }
  }
  return false;
}

export interface Evaluated { gate: Gate; /** The raw snapshot behind a CURRENT/SEGREGATED gate, for the caller's regression bookkeeping only. */ snap: RecallSnapshot | null }

/** Pure evaluation of one HTTP response. `previous` is the last snapshot this page accepted
 *  (CURRENT or SEGREGATED); the caller (GateTracker) owns it. Any exception is WITHHELD/INTEGRITY. */
export function evaluateDetailed(res: { status: number; body: unknown }, previous: RecallSnapshot | null, now: number = Date.now()): Evaluated {
  try {
    return evaluate(res, previous, now);
  } catch {
    return { gate: withheld("INTEGRITY", previous), snap: null };
  }
}

export function evaluateEnvelope(res: { status: number; body: unknown }, previous: RecallSnapshot | null, now: number = Date.now()): Gate {
  return evaluateDetailed(res, previous, now).gate;
}

function evaluate(res: { status: number; body: unknown }, previous: RecallSnapshot | null, now: number): Evaluated {
  const out = (gate: Gate): Evaluated => ({ gate, snap: null });
  const body = res.body;
  // 1. Transport. Only 200 can carry a snapshot; error bodies are read by structured `state` only.
  if (res.status !== 200) {
    const state = isObj(body) ? body.state : undefined;
    if (res.status === 503 && state === "VERIFYING") return out(withheld("VERIFYING", previous));
    if (res.status === 409 && state === "ANCHOR_INVALID") return out(withheld("ANCHOR_INVALID", previous));
    return out(withheld("TRANSPORT", previous, ` HTTP ${res.status}.`));
  }
  if (!isObj(body)) return out(withheld("INTEGRITY", previous));
  // 2. Strict metadata must be present and typed.
  const cp = body.checkpoint; const el = body.eligibility; const fr = body.freshness;
  if (!isObj(cp) || !isObj(el) || !isObj(fr)) return out(withheld("MISSING_METADATA", previous));
  // 3. Closed enum.
  const state = cp.state;
  if (typeof state !== "string" || !(STATES as readonly string[]).includes(state)) return out(withheld("UNKNOWN_STATE", previous));
  if (state === "ANCHOR_INVALID") return out(withheld("ANCHOR_INVALID", previous));
  // 4. Structural validity of the snapshot itself (finding/action invariants etc.).
  const snap = validateSnapshot(body);
  const f = snap.freshness!; const c = snap.checkpoint!;
  if (typeof f.archiveId !== "string" || !f.archiveId || typeof f.headHash !== "string" || !f.headHash || !Number.isSafeInteger(f.sequence) || f.sequence < 1
    || typeof c.checkpointRequired !== "boolean" || typeof c.h2 !== "string") return out(withheld("MISSING_METADATA", previous));
  if (!KNOWN_H2.includes(c.h2)) return out(withheld("UNKNOWN_STATE", previous));
  // 5. Cross-field consistency.
  if (f.status !== STATUS_FOR[state] || c.checkpointRequired !== (state !== "ANCHORED_CURRENT")) return out(withheld("CONTRADICTORY", previous));
  const unitIds = snap.units.map((u) => u.unitId);
  const eligKeys = Object.keys(el);
  if (eligKeys.length !== unitIds.length || unitIds.some((id) => !isObj(el[id]) || typeof (el[id] as Record<string, unknown>).currentReleaseEligible !== "boolean")) return out(withheld("CONTRADICTORY", previous));
  const eligible = (id: string) => (el[id] as { currentReleaseEligible: boolean }).currentReleaseEligible;
  // 6. Regression is checked for every state that carries a ledger watermark.
  if (previous && regressed(snap, previous)) return out(withheld("REGRESSION", previous));
  const mark: Watermark = { archiveId: f.archiveId, sequence: f.sequence, verifiedAt: f.verifiedAt };

  if (state === "UNANCHORED") {
    // Explicitly unverified local claims: no anchor, no H2 claim, nothing eligible.
    if (c.anchoredSequence !== null) return out(withheld("CONTRADICTORY", previous));
    if (c.h2 !== "UNVERIFIED") return out(withheld("CONTRADICTORY", previous));
    if (unitIds.some(eligible)) return out(withheld("CONTRADICTORY", previous));
    return { gate: { kind: "SEGREGATED", cause: "UNANCHORED", view: makeHistorical("UNANCHORED", snap, mark, SEGREGATED_REASON.UNANCHORED), reason: SEGREGATED_REASON.UNANCHORED }, snap };
  }
  if (state === "ANCHORED_PREFIX_ONLY") {
    // Owner decision: segregated historical evidence only when the structured metadata establishes successful H2.
    if (c.anchoredSequence === null || c.anchoredSequence === undefined) return out(withheld("MISSING_METADATA", previous));
    if (!Number.isSafeInteger(c.anchoredSequence) || c.anchoredSequence < 1 || c.anchoredSequence > f.sequence) return out(withheld("CONTRADICTORY", previous));
    if (c.h2 !== "VERIFIED") return out(withheld("INTEGRITY", previous));
    if (unitIds.some(eligible)) return out(withheld("CONTRADICTORY", previous));        // eligibility must be withheld everywhere
    return { gate: { kind: "SEGREGATED", cause: "PREFIX_ONLY", view: makeHistorical("PREFIX_ONLY", snap, mark, SEGREGATED_REASON.PREFIX_ONLY), reason: SEGREGATED_REASON.PREFIX_ONLY }, snap };
  }

  // ANCHORED_CURRENT
  if (c.h2 !== "VERIFIED" || c.anchoredSequence !== f.sequence) return out(withheld("CONTRADICTORY", previous));
  for (const id of unitIds) {
    if (!eligible(id)) continue;
    const decisions = Object.values(snap.decisions[id] ?? {});
    if (snap.notifications?.some((n) => n.unitId === id) || decisions.length === 0 || decisions.some((b) => b.current.operationalAction !== "RELEASE_ELIGIBLE")) return out(withheld("CONTRADICTORY", previous));
  }
  const at = Date.parse(f.verifiedAt); const age = now - at;
  if (!ISO.test(f.verifiedAt) || !Number.isFinite(at) || !Number.isFinite(f.maxAgeSeconds) || f.maxAgeSeconds <= 0 || f.maxAgeSeconds > 5 || age < -1000 || age >= f.maxAgeSeconds * 1000) return out(withheld("LEASE_EXPIRED", previous));
  // A motor with a RELEASE_ELIGIBLE decision but no currentReleaseEligible stays in this CURRENT view:
  // its findings and reasons are kept, only its clearance is withheld (clearanceOf -> NOT_CLEARED).
  return { gate: { kind: "CURRENT", view: makeGated(snap, mark), leaseMs: Math.min(5000, f.maxAgeSeconds * 1000 - Math.max(0, age)) }, snap };
}

/** Holds the last accepted snapshot so regression and the last-accepted watermark are structural. */
export class GateTracker {
  private previous: RecallSnapshot | null = null;
  evaluate(res: { status: number; body: unknown }, now: number = Date.now()): Gate {
    const { gate, snap } = evaluateDetailed(res, this.previous, now);
    if (gate.kind !== "WITHHELD" && snap) this.previous = snap;
    return gate;
  }
  /** A fetch that never produced a response (network error, timeout, abort-by-timeout). */
  transport(detail = ""): Gate { return withheld("TRANSPORT", this.previous, detail); }
}

/** Per-motor current clearance for a gate result; false for every non-CURRENT gate. */
export function isCurrentRelease(gate: Gate, unitId: string): boolean {
  return gate.kind === "CURRENT" && isCurrentClearance(clearanceOf(gate.view, unitId));
}
