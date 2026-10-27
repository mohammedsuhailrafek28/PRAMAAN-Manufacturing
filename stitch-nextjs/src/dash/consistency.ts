// Consistency of per-motor resources (decisions, lifecycle, provenance) with the verified snapshot they are shown beside.
// A resource is CURRENT only when its own metadata matches the snapshot. Timing (two requests finishing close together) is never evidence.
import type { Snapshot } from "./types";

export type Consistency = "CURRENT" | "UNVERIFIED" | "MISMATCH";
export type Verdict = { consistency: Consistency; reason: string };
export type ResourceKind = "lifecycle" | "provenance" | "decisions";

const NOT_DECISION_KEYS = new Set(["checkpoint", "eligibility"]);

/** Identity of the evidence a verified snapshot stands for. Any change starts a new request epoch and discards cached resources. */
export function epochOf(s: Snapshot | null | undefined): string | null {
  if (!s) return null;
  const f = s.freshness, c = s.checkpoint;
  return [f?.archiveId ?? "?", f?.sequence ?? "?", f?.headHash ?? "?", c?.state ?? "?", c?.anchoredSequence ?? "?"].join("|");
}

const ok = (): Verdict => ({ consistency: "CURRENT", reason: "" });
const unverified = (reason: string): Verdict => ({ consistency: "UNVERIFIED", reason });
const mismatch = (reason: string): Verdict => ({ consistency: "MISMATCH", reason });

type DecisionsBody = Record<string, unknown> & { checkpoint?: { state?: string; anchoredSequence?: number }; eligibility?: { currentReleaseEligible?: boolean } };

/** Decisions are shown only when the response was cut at the snapshot's own checkpoint and carries the snapshot's own decision versions. */
export function assessDecisions(body: DecisionsBody, s: Snapshot, motor: string, trusted: boolean): Verdict {
  if (!trusted) return mismatch("the snapshot is not trusted as current");
  const cp = body.checkpoint, scp = s.checkpoint;
  if (cp?.state !== "ANCHORED_CURRENT" || scp?.state !== "ANCHORED_CURRENT") return mismatch("the response is not from an anchored-current checkpoint");
  if (typeof cp.anchoredSequence !== "number" || cp.anchoredSequence !== scp.anchoredSequence) return mismatch(`the response is from checkpoint ${String(cp.anchoredSequence)}, the snapshot from ${String(scp.anchoredSequence)}`);
  const mine = Object.keys(body).filter((k) => !NOT_DECISION_KEYS.has(k)).sort();
  const theirs = Object.keys(s.decisions?.[motor] ?? {}).sort();
  if (mine.join() !== theirs.join()) return mismatch("the response covers different policies than the snapshot");
  for (const k of mine) {
    const a = body[k] as { current?: { decisionId?: string; version?: number }; history?: Array<{ decisionId?: string }> };
    const b = s.decisions[motor][k] as { current?: { decisionId?: string; version?: number }; history?: Array<{ decisionId?: string }> };
    if (!a?.current?.decisionId || a.current.decisionId !== b?.current?.decisionId || a.current.version !== b.current?.version) return mismatch("the decision version differs from the snapshot");
    if (Array.isArray(a.history) && Array.isArray(b.history) && (a.history.length !== b.history.length || a.history.at(-1)?.decisionId !== b.history.at(-1)?.decisionId)) return mismatch("the decision history differs from the snapshot");
  }
  const ea = body.eligibility?.currentReleaseEligible, eb = s.eligibility?.[motor]?.currentReleaseEligible;
  if (ea !== eb) return mismatch("release eligibility differs from the snapshot");
  return ok();
}

type LifecycleBody = { checkpoint?: { state?: string; anchoredSequence?: number }; eventCount?: number };

/** History is CURRENT only with matching checkpoint and event count under a trusted snapshot. A newer or older response is a mismatch, not a lesser label. */
export function assessLifecycle(body: LifecycleBody, s: Snapshot, motor: string, trusted: boolean): Verdict {
  const unit = s.units.find((u) => u.unitId === motor);
  if (!unit) return mismatch("the motor is not in the snapshot");
  const cp = body.checkpoint, scp = s.checkpoint;
  if (cp && scp && (cp.state !== scp.state || cp.anchoredSequence !== scp.anchoredSequence)) return mismatch(`the response is from checkpoint ${String(cp.state)}/${String(cp.anchoredSequence)}, the snapshot from ${String(scp.state)}/${String(scp.anchoredSequence)}`);
  if (typeof body.eventCount === "number" && typeof unit.eventCount === "number" && body.eventCount !== unit.eventCount) return mismatch(`the response has ${body.eventCount} events, the snapshot ${unit.eventCount}`);
  if (!trusted) return unverified("the snapshot is not current, so this history is recorded fact only");
  if (!cp || typeof cp.anchoredSequence !== "number" || typeof body.eventCount !== "number" || typeof unit.eventCount !== "number") return unverified("the response does not carry a checkpoint and event count to compare");
  return ok();
}

type ProvenanceRows = Array<{ id: string }>;

/** The provenance endpoint returns a bare array with no watermark. It can be rejected when it holds events the snapshot does not, but it can never be labelled CURRENT. */
export function assessProvenance(body: ProvenanceRows, s: Snapshot, motor: string): Verdict {
  const unit = s.units.find((u) => u.unitId === motor);
  if (!unit) return mismatch("the motor is not in the snapshot");
  if (!Array.isArray(body)) return unverified("the response has an unrecognised shape");
  const known = new Set((unit.events ?? []).map((e) => e.eventId));
  if (body.some((r) => !known.has(r.id))) return mismatch("the response holds events newer than the snapshot");
  return unverified("this endpoint carries no checkpoint or watermark, so its currency cannot be established");
}

export function assess(kind: ResourceKind, body: unknown, s: Snapshot, motor: string, trusted: boolean): Verdict {
  if (kind === "decisions") return assessDecisions(body as DecisionsBody, s, motor, trusted);
  if (kind === "lifecycle") return assessLifecycle(body as LifecycleBody, s, motor, trusted);
  return assessProvenance(body as ProvenanceRows, s, motor);
}
