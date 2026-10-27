// Branded page views. A standalone page never sees a raw RecallSnapshot: it receives exactly one of
//   GatedSnapshot  - the shared gate returned CURRENT (verified findings, holds AND per-motor clearance)
//   HistoricalView - the gate returned SEGREGATED (PREFIX_ONLY / UNANCHORED): facts only, no decisions
//   PreviewView    - an explicit ?mode=preview dataset: labelled synthetic, never trusted, never cleared
// This is the only module that reads `decisions`, `eligibility`, `operationalAction` or
// `currentReleaseEligible` from a RecallSnapshot to produce clearance.
//
// Brands and the WeakMap registry stop accidental misuse (casts, clones, JSON round-trips). They are
// NOT a security boundary against a malicious script in the page and do not replace the backend's
// integrity verification.
import type { RecallSnapshot } from "../domain/types";
import { mintCurrentClearance, type MotorClearance } from "./clearance";

declare const GATED: unique symbol;
declare const HISTORICAL: unique symbol;
declare const PREVIEW: unique symbol;

export interface Watermark { archiveId: string; sequence: number; verifiedAt: string }

/** Everything a component may look up (events, components, lots). No `decisions`, `eligibility`, `comparison`, `checkpoint`. */
export type Facts = Omit<RecallSnapshot, "decisions" | "eligibility" | "comparison" | "checkpoint">;

export interface GatedSnapshot { readonly [GATED]: true; readonly facts: Facts; readonly watermark: Watermark }
export interface HistoricalView {
  readonly [HISTORICAL]: true; readonly cause: "PREFIX_ONLY" | "UNANCHORED"; readonly facts: Facts; readonly watermark: Watermark; readonly reason: string;
}
export interface PreviewView { readonly [PREVIEW]: true; readonly facts: Facts; readonly label: string }
export type PageView = GatedSnapshot | HistoricalView | PreviewView;

type Kind = "GATED" | "HISTORICAL" | "PREVIEW";
const kinds = new WeakMap<object, Kind>();
const raws = new WeakMap<object, RecallSnapshot>();
const cleared = new WeakMap<object, ReadonlySet<string>>();

export class NotBranded extends Error { constructor(what: string) { super(`Not a branded view: ${what}`); this.name = "NotBranded"; } }

const kindOf = (x: unknown): Kind | null => (typeof x === "object" && x !== null ? kinds.get(x) ?? null : null);
export const isGated = (x: unknown): x is GatedSnapshot => kindOf(x) === "GATED";
export const isHistorical = (x: unknown): x is HistoricalView => kindOf(x) === "HISTORICAL";
export const isPreview = (x: unknown): x is PreviewView => kindOf(x) === "PREVIEW";
export function assertView(x: unknown): asserts x is PageView { if (kindOf(x) === null) throw new NotBranded(typeof x); }
export function assertGated(x: unknown): asserts x is GatedSnapshot { if (!isGated(x)) throw new NotBranded("expected a GatedSnapshot"); }

// ---- factories: allow-listed (by a static test) to gate.ts, the preview adapters and testing.ts ----

/** `snap` must already have passed the gate. Eligibility is read once, here, per motor. */
export function makeGated(snap: RecallSnapshot, watermark: Watermark): GatedSnapshot {
  const view = Object.freeze({ facts: snap, watermark }) as unknown as GatedSnapshot;
  const ok = new Set<string>();
  for (const u of snap.units) if (snap.eligibility?.[u.unitId]?.currentReleaseEligible === true) ok.add(u.unitId);
  kinds.set(view, "GATED"); raws.set(view, snap); cleared.set(view, ok);
  return view;
}

/** Decisions, eligibility and comparison are removed: a historical view cannot carry a release. */
export function makeHistorical(cause: "PREFIX_ONLY" | "UNANCHORED", snap: RecallSnapshot, watermark: Watermark, reason: string): HistoricalView {
  const clean: RecallSnapshot = { ...snap, decisions: {}, comparison: [], eligibility: undefined, checkpoint: undefined };
  const view = Object.freeze({ cause, facts: clean, watermark, reason }) as unknown as HistoricalView;
  kinds.set(view, "HISTORICAL"); raws.set(view, clean);
  return view;
}

export function makePreview(snap: RecallSnapshot, label: string): PreviewView {
  // A preview can never carry trust metadata, whatever the dataset file claims.
  const clean: RecallSnapshot = { ...snap, eligibility: undefined, checkpoint: undefined, freshness: undefined };
  const view = Object.freeze({ facts: clean, label }) as unknown as PreviewView;
  kinds.set(view, "PREVIEW"); raws.set(view, clean);
  return view;
}

/** For views.ts only (static test): the snapshot the unchanged projection cores run over. */
export function rawSnapshotOf(view: PageView): RecallSnapshot {
  assertView(view);
  return raws.get(view)!;
}

export const factsOf = (view: PageView): Facts => { assertView(view); return view.facts; };

/** The single source of current clearance, per motor: explicit `currentReleaseEligible === true` plus an all-release decision set. */
export function clearanceOf(g: GatedSnapshot, unitId: string): MotorClearance {
  assertGated(g);
  const snap = raws.get(g)!;
  const decisions = Object.values(snap.decisions[unitId] ?? {});
  if (decisions.length === 0) return "NOT_CLEARED";
  if (decisions.some((b) => b.current.operationalAction !== "RELEASE_ELIGIBLE")) return "HOLD";
  return cleared.get(g)!.has(unitId) ? mintCurrentClearance() : "NOT_CLEARED";
}
