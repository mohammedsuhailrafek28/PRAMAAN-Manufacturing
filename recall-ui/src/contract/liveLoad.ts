// The single live-load path for the standalone pages: fetch -> typed gate -> {verified snapshot |
// segregated historical snapshot | thrown GateWithheldError}. Adapters contain no classification.
import type { RecallSnapshot } from "../domain/types";
import { getEnvelope, TimeoutError } from "./envelope";
import { GateTracker, GateWithheldError } from "./gate";

export interface LiveResult {
  snap: RecallSnapshot;
  /** True only for a CURRENT gate. A SEGREGATED snapshot is historical and never verified. */
  verified: boolean;
  reason: string;
  leaseMs: number;
  /** "CURRENT" | "SEGREGATED" cause, for tests and neutral labelling only. */
  gate: "CURRENT" | "PREFIX_ONLY" | "UNANCHORED" | "ELIGIBILITY_WITHHELD";
}

export async function liveLoad(tracker: GateTracker, url: string, timeoutMs: number, signal?: AbortSignal): Promise<LiveResult> {
  let res;
  try {
    res = await getEnvelope(url, timeoutMs, signal);
  } catch (e) {
    if (signal?.aborted) throw e;                       // page teardown, not a verdict
    const gate = tracker.transport(e instanceof TimeoutError ? " Backend request timed out." : "");
    throw new GateWithheldError(gate as Extract<typeof gate, { kind: "WITHHELD" }>);
  }
  const gate = tracker.evaluate(res);
  if (gate.kind === "WITHHELD") throw new GateWithheldError(gate);
  if (gate.kind === "CURRENT") return { snap: gate.snap, verified: true, reason: "", leaseMs: gate.leaseMs, gate: "CURRENT" };
  return { snap: gate.snap, verified: false, reason: gate.reason, leaseMs: 0, gate: gate.cause };
}
