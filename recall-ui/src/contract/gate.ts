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

export interface Watermark { archiveId: string; sequence: number; verifiedAt: string }

export type WithheldCause =
  | "ANCHOR_INVALID" | "VERIFYING" | "MISSING_METADATA" | "UNKNOWN_STATE" | "CONTRADICTORY"
  | "LEASE_EXPIRED" | "REGRESSION" | "INTEGRITY" | "TRANSPORT";
export type SegregatedCause = "PREFIX_ONLY" | "UNANCHORED" | "ELIGIBILITY_WITHHELD";

export type Gate =
  | { kind: "CURRENT"; snap: RecallSnapshot; leaseMs: number }
  | { kind: "SEGREGATED"; cause: SegregatedCause; snap: RecallSnapshot; reason: string }
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
  ELIGIBILITY_WITHHELD: "Historical evidence only. A recorded exclusion is not current clearance while another motor or obligation needs review.",
};

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

/** Pure evaluation of one HTTP response. `previous` is the last snapshot this page accepted
 *  (CURRENT or SEGREGATED); the caller (GateTracker) owns it. */
export function evaluateEnvelope(res: { status: number; body: unknown }, previous: RecallSnapshot | null, now: number = Date.now()): Gate {
  try {
    return evaluate(res, previous, now);
  } catch {
    return withheld("INTEGRITY", previous);
  }
}

function evaluate(res: { status: number; body: unknown }, previous: RecallSnapshot | null, now: number): Gate {
  const body = res.body;
  // 1. Transport. Only 200 can carry a snapshot; error bodies are read by structured `state` only.
  if (res.status !== 200) {
    const state = isObj(body) ? body.state : undefined;
    if (res.status === 503 && state === "VERIFYING") return withheld("VERIFYING", previous);
    if (res.status === 409 && state === "ANCHOR_INVALID") return withheld("ANCHOR_INVALID", previous);
    return withheld("TRANSPORT", previous, ` HTTP ${res.status}.`);
  }
  if (!isObj(body)) return withheld("INTEGRITY", previous);
  // 2. Strict metadata must be present and typed.
  const cp = body.checkpoint; const el = body.eligibility; const fr = body.freshness;
  if (!isObj(cp) || !isObj(el) || !isObj(fr)) return withheld("MISSING_METADATA", previous);
  // 3. Closed enum.
  const state = cp.state;
  if (typeof state !== "string" || !(STATES as readonly string[]).includes(state)) return withheld("UNKNOWN_STATE", previous);
  if (state === "ANCHOR_INVALID") return withheld("ANCHOR_INVALID", previous);
  // 4. Structural validity of the snapshot itself (finding/action invariants etc.).
  const snap = validateSnapshot(body);
  const f = snap.freshness!; const c = snap.checkpoint!;
  if (typeof f.archiveId !== "string" || !f.archiveId || typeof f.headHash !== "string" || !f.headHash || !Number.isSafeInteger(f.sequence) || f.sequence < 1
    || typeof c.checkpointRequired !== "boolean" || typeof c.h2 !== "string") return withheld("MISSING_METADATA", previous);
  // 5. Cross-field consistency.
  if (f.status !== STATUS_FOR[state] || c.checkpointRequired !== (state !== "ANCHORED_CURRENT")) return withheld("CONTRADICTORY", previous);
  const unitIds = snap.units.map((u) => u.unitId);
  const eligKeys = Object.keys(el);
  if (eligKeys.length !== unitIds.length || unitIds.some((id) => !isObj(el[id]) || typeof (el[id] as Record<string, unknown>).currentReleaseEligible !== "boolean")) return withheld("CONTRADICTORY", previous);
  const eligible = (id: string) => (el[id] as { currentReleaseEligible: boolean }).currentReleaseEligible;
  // 6. Regression is checked for every state that carries a ledger watermark.
  if (previous && regressed(snap, previous)) return withheld("REGRESSION", previous);

  if (state === "UNANCHORED" || state === "ANCHORED_PREFIX_ONLY") {
    if (unitIds.some(eligible)) return withheld("CONTRADICTORY", previous);        // eligibility must be withheld everywhere
    if (state === "ANCHORED_PREFIX_ONLY" && c.h2 !== "VERIFIED") return withheld("INTEGRITY", previous); // evidence must pass the available checks
    const cause: SegregatedCause = state === "UNANCHORED" ? "UNANCHORED" : "PREFIX_ONLY";
    return { kind: "SEGREGATED", cause, snap, reason: SEGREGATED_REASON[cause] };
  }

  // ANCHORED_CURRENT
  if (c.h2 !== "VERIFIED" || c.anchoredSequence !== f.sequence) return withheld("CONTRADICTORY", previous);
  for (const id of unitIds) {
    if (!eligible(id)) continue;
    const decisions = Object.values(snap.decisions[id] ?? {});
    if (snap.notifications?.some((n) => n.unitId === id) || decisions.length === 0 || decisions.some((b) => b.current.operationalAction !== "RELEASE_ELIGIBLE")) return withheld("CONTRADICTORY", previous);
  }
  const at = Date.parse(f.verifiedAt); const age = now - at;
  if (!ISO.test(f.verifiedAt) || !Number.isFinite(at) || !Number.isFinite(f.maxAgeSeconds) || f.maxAgeSeconds <= 0 || f.maxAgeSeconds > 5 || age < -1000 || age >= f.maxAgeSeconds * 1000) return withheld("LEASE_EXPIRED", previous);
  // A recorded exclusion with no current eligibility (e.g. a pending obligation) is not clearance.
  const blocked = unitIds.some((id) => Object.values(snap.decisions[id] ?? {}).some((b) => b.current.operationalAction === "RELEASE_ELIGIBLE") && !eligible(id));
  if (blocked) return { kind: "SEGREGATED", cause: "ELIGIBILITY_WITHHELD", snap, reason: SEGREGATED_REASON.ELIGIBILITY_WITHHELD };
  return { kind: "CURRENT", snap, leaseMs: Math.min(5000, f.maxAgeSeconds * 1000 - Math.max(0, age)) };
}

/** Holds the last accepted snapshot so regression and the last-accepted watermark are structural. */
export class GateTracker {
  private previous: RecallSnapshot | null = null;
  evaluate(res: { status: number; body: unknown }, now: number = Date.now()): Gate {
    const gate = evaluateEnvelope(res, this.previous, now);
    if (gate.kind !== "WITHHELD") this.previous = gate.snap;
    return gate;
  }
  /** A fetch that never produced a response (network error, timeout, abort-by-timeout). */
  transport(detail = ""): Gate { return withheld("TRANSPORT", this.previous, detail); }
}

/** Tests/adapters: the only place an action is allowed to be treated as current clearance. */
export function isCurrentRelease(gate: Gate, unitId: string): boolean {
  return gate.kind === "CURRENT" && gate.snap.eligibility?.[unitId]?.currentReleaseEligible === true;
}
