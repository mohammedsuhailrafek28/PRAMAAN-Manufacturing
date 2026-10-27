/** Pure poll/lease decisions for the dashboard data provider (no React, no clock reads: callers pass monotonic `performance.now()` values).
 *  Neither function lengthens a lease or accepts a response; the strict gate (src/orig/contract/gate.ts) remains the only judge of a response. */

export const POLL_MS = 2000;

/** A response the gate rejected ONLY on freshness (cause LEASE_EXPIRED: stamp too old, or stamp in the future by more than the 1 s skew allowance)
 *  is still not accepted and its body is never shown, but it does not revoke a lease an earlier ACCEPTED response still holds.
 *  That lease was measured when it was accepted and ends at the same instant as before. Any other cause (prefix-only, unanchored, VERIFYING,
 *  anchor invalid, regression, contradictory, transport, ...) always withdraws immediately. */
export function keepsHeldLease(gate: { kind: string; cause?: string }, leaseUntil: number | null, now: number): boolean {
  return gate.kind === "WITHHELD" && gate.cause === "LEASE_EXPIRED" && leaseUntil !== null && now < leaseUntil;
}

/** Delay before the next snapshot request, measured from the START of the previous one: a request slower than the interval is followed
 *  immediately instead of waiting for the next tick (a skipped tick adds up to a full interval to the gap between accepted responses). */
export function nextPollDelay(startedAt: number, now: number, interval: number = POLL_MS): number {
  return Math.max(0, interval - (now - startedAt));
}
