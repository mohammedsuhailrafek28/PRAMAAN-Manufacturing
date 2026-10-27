// The ONLY renderer of current clearance. Its prop is a CurrentClearance minted by clearanceOf();
// a string, a boolean or a cast object renders nothing.
import { ACTION_TEXT, humanize } from "../domain/glossary";
import { isCurrentClearance, type MotorClearance, type RecordedClaim } from "./clearance";

export function ClearanceChip({ clearance }: { clearance: MotorClearance }) {
  if (!isCurrentClearance(clearance)) return null;
  return (
    <span className="chip action-RELEASE_ELIGIBLE" data-testid="clearance-chip">
      <span className="chip-cap">Action</span><span className="chip-body">{ACTION_TEXT.RELEASE_ELIGIBLE?.label ?? "Release eligible"}</span>
    </span>
  );
}

/** Honest wording for the two non-cleared outcomes; never mentions release. */
export function clearanceNote(clearance: MotorClearance): string {
  if (isCurrentClearance(clearance)) return "";
  return clearance === "HOLD" ? "A recall hold is in effect." : "Current clearance is withheld for this motor.";
}

/** Preview only. Synthetic evaluator output, never authorization, never rendered through ClearanceChip. */
export function PreviewRecordedAction({ action }: { action: string | undefined }) {
  if (!action) return null;
  return (
    <span className="chip" data-testid="preview-recorded-action">
      <span className="chip-cap">Synthetic evaluator output</span>
      <span className="chip-body">{ACTION_TEXT[action]?.label ?? action} (preview; not an authorization)</span>
    </span>
  );
}

const PREVIEW_NOTE = "preview: synthetic evaluator output, not an authorization";

/** Chip for one recorded claim. Hold and withheld are always honest; the release chip needs a minted clearance. */
export function ClaimChip({ claim }: { claim: RecordedClaim }) {
  if (claim.recordedAction !== undefined) return <PreviewRecordedAction action={claim.recordedAction} />;      // explicit preview only
  if (claim.hold) return <span className="chip action-RECALL_HOLD"><span className="chip-cap">Action</span><span className="chip-body">{ACTION_TEXT.RECALL_HOLD?.label ?? "Recall hold"}</span></span>;
  if (isCurrentClearance(claim.clearance)) return <ClearanceChip clearance={claim.clearance} />;
  return <span className="chip action-WITHHELD" data-testid="clearance-withheld"><span className="chip-cap">Action</span><span className="chip-body">Clearance withheld</span></span>;
}

/** Sentence form of a recorded claim, for explanations. */
export function ClaimText({ claim }: { claim: RecordedClaim }) {
  if (claim.recordedAction !== undefined) {
    const a = ACTION_TEXT[claim.recordedAction];
    return <><strong>{a?.label ?? humanize(claim.recordedAction)} ({PREVIEW_NOTE}):</strong> {a?.explain}</>;
  }
  if (claim.hold) return <><strong>{ACTION_TEXT.RECALL_HOLD?.label ?? "Recall hold"}:</strong> {ACTION_TEXT.RECALL_HOLD?.explain}</>;
  if (isCurrentClearance(claim.clearance)) return <><strong>{ACTION_TEXT.RELEASE_ELIGIBLE?.label ?? "Release eligible"}:</strong> {ACTION_TEXT.RELEASE_ELIGIBLE?.explain}</>;
  return <><strong>Clearance withheld:</strong> The recorded finding stands, but this is not current clearance for this motor.</>;
}
