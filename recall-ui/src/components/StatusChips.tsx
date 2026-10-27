import {ClaimChip} from "../contract/ClearanceChip";
import {useConsoleClaims} from "../contract/ConsoleClaims";
import { ACTION_TEXT, FINDING_TEXT } from "../domain/glossary";
import type { Decision } from "../domain/types";

// Evidence finding, operational action and review flag are three separate facts.
// Each chip carries a glyph AND a text label; color is only reinforcement.

const FINDING_GLYPH: Record<string, string> = { AFFECTED: "▲", UNRESOLVED: "?", EXCLUDED_WITH_EVIDENCE: "✓" };

export function FindingChip({ finding }: { finding: Decision["evidenceFinding"] }) {
  const t = FINDING_TEXT[finding];
  return (
    <span className={`chip finding-${finding}`} title={t?.explain} data-testid="chip-finding">
      <span className="chip-cap">Evidence finding</span>
      <span className="chip-body">
        <span aria-hidden="true">{FINDING_GLYPH[finding] ?? "•"}</span> {t?.label ?? finding}
      </span>
    </span>
  );
}

/** Legacy callers can show recorded actions only; current clearance needs ClaimChip. */
export function ActionChip({ action }: { action: Decision["operationalAction"] }) {
 return <span className="chip" data-testid="chip-action">Recorded action: {ACTION_TEXT[action]?.label ?? action} (not current clearance)</span>;
}

export function ReviewChip({ required }: { required: boolean }) {
  return (
    <span className={`chip review-${required ? "yes" : "no"}`} data-testid="chip-review">
      <span className="chip-cap">Review</span>
      <span className="chip-body">
        <span aria-hidden="true">{required ? "◆" : "◇"}</span> {required ? "Review required" : "No review flag"}
      </span>
    </span>
  );
}

export function PrecautionChip() {
  return (
    <span className="chip precaution" data-testid="chip-precaution">
      <span className="chip-cap">Precaution</span>
      <span className="chip-body"><span aria-hidden="true">⚑</span> Precautionary hold</span>
    </span>
  );
}

export function DecisionChips({ d, historical = false }: { d: Decision; historical?: boolean }) {
  const {claims,preview}=useConsoleClaims();
  const claim=historical ? undefined : claims?.byDecision.get(d.decisionId);
  return (
    <div className="chip-row">
      <FindingChip finding={d.evidenceFinding} />
      {claim ? <span data-testid="chip-action"><ClaimChip claim={claim} /></span> : <span><span className="sr-only">{preview ? "Synthetic evaluator output" : "Historical recorded action"}</span><ActionChip action={d.operationalAction}/></span>}
      <ReviewChip required={d.reviewRequired} />
      {d.precautionaryHold ? <PrecautionChip /> : null}
    </div>
  );
}

export function SyntheticTag({ children = "Synthetic" }: { children?: string }) {
  return <span className="tag synthetic" title="Not engine output and not real data">{children}</span>;
}
