// Snapshot helpers for the rule-based "Ask PRAMAAN" assistant: epoch, trust and identifier resolution over a snapshot read through GET only.
export type Snap = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export const MAX_QUESTION = 500;
export const MAX_HISTORY = 4;
// Identifier shapes used by the synthetic dataset. An answer may mention only identifiers that occur in its own context.
export const ID_PATTERNS: RegExp[] = [
  /\bMTR-\d{5}\b/g, /urn:pramaan:[A-Za-z0-9:_-]+/g, /\bBR-\d{3}\b/g, /\bSTEEL-\d{2}-\d{3}\b/g,
  /\bBRG-\d{5}-[A-Z]+-\d{2}\b/g, /\bWO-\d{4}\b/g, /\bRC-\d{3}-\d{3}(?:\/P\d+)?\b/g, /\bSHP-\d{4}\b/g, /\bA31-MTR-\d{5}-[0-9a-f]+-[0-9a-f]+-v\d+\b/g,
];
export const tokensIn = (text: string): string[] => ID_PATTERNS.flatMap((re) => text.match(re) ?? []);

export function epochOf(s: Snap | null | undefined): string | null {
  if (!s) return null;
  const f = s.freshness, c = s.checkpoint;
  return [f?.archiveId ?? "?", f?.sequence ?? "?", f?.headHash ?? "?", c?.state ?? "?", c?.anchoredSequence ?? "?"].join("|");
}

/** Server-side trust: the facts the dashboard gate needs. Anything else is recorded history only, never a current finding. */
export function trustOf(s: Snap): { trusted: boolean; reason: string } {
  const f = s.freshness, c = s.checkpoint;
  if (!f || !c) return { trusted: false, reason: "The snapshot carries no freshness or checkpoint information." };
  if (!/^VERIFIED_ANCHORED/.test(String(f.status))) return { trusted: false, reason: `The snapshot is not verified against an anchored checkpoint (${String(f.status)}).` };
  if (c.state !== "ANCHORED_CURRENT" || c.checkpointRequired === true) return { trusted: false, reason: `The checkpoint is ${String(c.state)}, not anchored-current.` };
  if (!s.decisions || !Object.keys(s.decisions).length) return { trusted: false, reason: "The snapshot carries no decisions." };
  return { trusted: true, reason: "" };
}

const hasUnit = (s: Snap, m: string) => (s.units ?? []).some((u: Snap) => u.unitId === m);

export function motorsIn(q: string): string[] { return [...new Set(q.toUpperCase().match(/\bMTR-\d{5}\b/g) ?? [])]; }

/** Identifiers in the question that look like PRAMAAN ids but do not exist in the snapshot. */
export function unknownIds(q: string, s: Snap): string[] {
  const out: string[] = [], up = q.toUpperCase();
  for (const t of up.match(/\bMTR-\d{3,6}\b/g) ?? []) if (!hasUnit(s, t)) out.push(t);
  const lots = new Set((s.lots ?? []).map((l: Snap) => l.lotId)), raws = new Set((s.lineage ?? []).map((x: Snap) => x.rawMaterialLot));
  for (const t of up.match(/\b(?:BR-\d{3}|STEEL-\d{2}-\d{3})\b/g) ?? []) if (!lots.has(t) && !raws.has(t)) out.push(t);
  return [...new Set(out)];
}
