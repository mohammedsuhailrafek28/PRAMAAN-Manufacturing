"use client";

import { isCurrentClearance, type RecordedClaim } from "@/orig/contract/clearance";
import { ACTION_TEXT } from "@/orig/domain/glossary";

/** The only place a release chip can appear: it needs a clearance minted by the original gate (isCurrentClearance). Hold and withheld are always honest. */
export function ClaimTag({ claim }: { claim: RecordedClaim }) {
  if (claim.hold) return <span className="tag RECALL_HOLD" title={ACTION_TEXT.RECALL_HOLD?.explain}>[RECALL HOLD]</span>;
  if (isCurrentClearance(claim.clearance)) return <span className="tag RELEASE_ELIGIBLE" title={ACTION_TEXT.RELEASE_ELIGIBLE?.explain}>[RELEASE ELIGIBLE]</span>;
  return <span className="tag warn">[CLEARANCE WITHHELD]</span>;
}
export function ClaimSentence({ claim }: { claim: RecordedClaim }) {
  if (claim.hold) return <><b>Recall hold:</b> {ACTION_TEXT.RECALL_HOLD?.explain}</>;
  if (isCurrentClearance(claim.clearance)) return <><b>Release eligible:</b> {ACTION_TEXT.RELEASE_ELIGIBLE?.explain}</>;
  return <><b>Clearance withheld:</b> The recorded finding stands, but this is not current clearance for this motor.</>;
}
export const when = (iso: string | null | undefined) => (iso ? iso.replace("T", " ").replace(/:\d\dZ$/, " UTC").replace(/Z$/, " UTC") : "Not recorded");
export const short = (h: string | null | undefined) => (h ? `${h.slice(0, 12)}…` : "Not recorded");
