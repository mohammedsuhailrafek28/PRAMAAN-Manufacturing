import { ACTION_TEXT, FINDING_TEXT } from "../domain/glossary";
import type { Decision } from "../domain/types";
import { useStale } from "./Freshness";

// Evidence finding, operational action and review flag are three separate facts.
// Each chip carries a glyph AND a text label; color is only reinforcement.

const FINDING_GLYPH: Record<string, string> = { AFFECTED: "▲", UNRESOLVED: "?", EXCLUDED_WITH_EVIDENCE: "✓" };
const ACTION_GLYPH: Record<string, string> = { RECALL_HOLD: "■", RELEASE_ELIGIBLE: "▶" };

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

export function ActionChip({ action }: { action: Decision["operationalAction"] }) {
  const t = ACTION_TEXT[action];
  const stale = useStale();
  return (
    <span className={`chip action-${action}${stale ? " is-historical" : ""}`} title={t?.explain} data-testid="chip-action">
      <span className="chip-cap">{stale ? "Last recorded action · not current" : "Operational action"}</span>
      <span className="chip-body">
        <span aria-hidden="true">{ACTION_GLYPH[action] ?? "•"}</span> {t?.label ?? action}
      </span>
    </span>
  );
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

export function DecisionChips({ d }: { d: Decision }) {
  return (
    <div className="chip-row">
      <FindingChip finding={d.evidenceFinding} />
      <ActionChip action={d.operationalAction} />
      <ReviewChip required={d.reviewRequired} />
      {d.precautionaryHold ? <PrecautionChip /> : null}
    </div>
  );
}

export function SyntheticTag({ children = "Synthetic" }: { children?: string }) {
  return <span className="tag synthetic" title="Not engine output and not real data">{children}</span>;
}
