// Per-motor clearance vocabulary shared by the projections and the one clearance renderer.
//
// A projection never decides clearance. It records whether a recall HOLD is in effect and asks the
// resolver it was given; with no resolver the answer is NOT_CLEARED (fail closed). Only
// gated.ts may mint a CurrentClearance, and only from `eligibility[unit].currentReleaseEligible`.
//
// Brands and registries here are protection against developer misuse, not a substitute for the
// backend's cryptographic/integrity verification.
declare const CLEARED: unique symbol;

/** Valid current clearance for one motor. Unforgeable by a type assertion: see isCurrentClearance. */
export interface CurrentClearance { readonly [CLEARED]: true }
export type MotorClearance = CurrentClearance | "HOLD" | "NOT_CLEARED";

const minted = new WeakSet<object>();

/** Allow-listed to gated.ts by a static test. */
export function mintCurrentClearance(): CurrentClearance {
  const c = Object.freeze({}) as CurrentClearance;
  minted.add(c);
  return c;
}

export const isCurrentClearance = (x: unknown): x is CurrentClearance => typeof x === "object" && x !== null && minted.has(x);

export interface ClearanceOptions {
  /** Supplied by views.ts from the branded snapshot. Absent => every non-hold motor is NOT_CLEARED. */
  clearance?: (unitId: string) => MotorClearance;
  /** Preview only: also carry the recorded action as labelled synthetic evaluator output. */
  previewRecorded?: boolean;
}

/** What a projection may say about one recorded decision, with finding, hold and clearance kept apart. */
export interface RecordedClaim {
  hold: boolean;
  clearance: MotorClearance;
  /** Present only for an explicit preview: synthetic evaluator output, never authorization. */
  recordedAction?: string;
}

export function claimFor(action: string, unitId: string, opts?: ClearanceOptions): RecordedClaim {
  // Fail closed: anything that is not exactly a release claim is treated as a hold.
  const hold = action !== "RELEASE_ELIGIBLE";
  let clearance: MotorClearance = hold ? "HOLD" : "NOT_CLEARED";
  if (!hold) {
    const asked = opts?.clearance?.(unitId);
    if (asked === "HOLD") clearance = "HOLD";
    else if (isCurrentClearance(asked)) clearance = asked;
  }
  return { hold, clearance, ...(opts?.previewRecorded ? { recordedAction: action } : {}) };
}
