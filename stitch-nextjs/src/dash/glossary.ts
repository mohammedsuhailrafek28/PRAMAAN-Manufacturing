// Plain-language descriptions of engine vocabulary. Descriptive only: nothing here changes a decision.

export const NO_DESCRIPTION = "No description available for this code.";

export const REASONS: Record<string, string> = {
  AFFECTED_LOT_INSTALLED: "The recorded installation holds a bearing from the recalled lot in a slot the recall covers.",
  AS_BUILT_UNAFFECTED_LOT: "The as-built record shows only unaffected lots in the covered slot, with no later change recorded. This is evidence, not a shipment authorization.",
  AMBIGUOUS_SLOT_ATTRIBUTION:
    "A removal could belong to more than one slot (same part and lot recorded in several), and nothing independent shows which. The wrong slot may have been cleared.",
  CORROBORATED_BY_VERIFICATION: "An independent verification supports the recorded slot state.",
  CURRENT_STATE_UNVERIFIED: "The motor's current slot state is not verified after the last change.",
  DAMAGE_INSPECTION_MISSING: "The policy requires a qualifying damage inspection and none is on record.",
  DAMAGE_INSPECTION_PASSED: "A qualifying damage inspection passed after the recall announcement.",
  DOUBLE_OCCUPANCY: "Records show two components in the same slot at the same time.",
  EXPOSURE_REMEDIATED: "The affected component was replaced and the remediation is complete.",
  GAP_BOUNDED_BY_VERIFICATION: "A capture gap is closed on both sides by verified state, so it cannot hide a change.",
  HISTORICAL_EXPOSURE_CONFIRMED: "The motor held an affected lot at some point in its operating history.",
  IRRELEVANT_SLOT_GAP: "A capture gap exists but only in a slot the recall policy does not cover.",
  LATE_CLAIM_RISK_INCREASING: "A later-arriving record increases risk compared with an earlier decision.",
  MATERIAL_CAPTURE_GAP: "Data capture was down for a period that could have hidden a relevant change.",
  NO_TRUSTED_BASELINE: "There is no trusted as-built record to start from.",
  PRIOR_EXCLUSION_WITHDRAWN: "An earlier release-eligible decision no longer holds because new evidence arrived.",
  REMEDIATION_COMPLETENESS_UNCERTAIN: "A replacement was recorded but it is not certain every affected part was replaced.",
  REMOVAL_OBSERVATION_MISMATCH: "What was recorded as removed does not match what the slot held.",
  REMOVAL_SERIAL_IN_OTHER_SLOT: "The removed part's serial is recorded in a different slot than the one claimed.",
  REPLACED_WITH_UNAFFECTED_LOT: "The slot now holds a verified, unaffected lot.",
  UNTRUSTED_AFFECTED_OBSERVATION:
    "An unreliable record shows an affected lot in this slot and nothing later answers it. It is held for review, never auto-confirmed.",
  VERIFIED_AFFECTED_LOT_PRESENT: "A trusted verification shows an affected lot installed.",
};

export const FLAGS: Record<string, string> = {
  OUT_OF_SCOPE_UNTRUSTED_AFFECTED_OBSERVATION:
    "An unreliable affected-lot sighting concerns a slot outside this policy. It does not block, but needs a human look.",
  SLOT_RECORD_CONFLICT: "Slot records contradict each other.",
  UNATTRIBUTABLE_UNTRUSTED_AFFECTED_OBSERVATION: "An unreliable affected-lot sighting cannot be tied to a slot or motor.",
  UNTRUSTED_AFFECTED_OBSERVATION_SUPERSEDED: "An unreliable affected-lot sighting was answered by later, provable evidence.",
};

export const GAP_KINDS: Record<string, string> = {
  SOURCE_OUTAGE: "A data source was not capturing during this window.",
  UNRESOLVED_EXCEPTION: "A recorded exception was never resolved.",
};

export const CONFLICT_KINDS: Record<string, string> = {
  DOUBLE_OCCUPANCY: "Two components recorded in one slot at once.",
  LATE_CORRECTION: "A record was corrected after it had been used.",
  REMOVAL_OBSERVATION_MISMATCH: "Removed item does not match the slot's recorded occupant.",
  REMOVAL_SERIAL_IN_OTHER_SLOT: "Removed serial is recorded in another slot.",
  VERIFIED_STATE_MISMATCH: "A verification disagrees with the recorded state.",
};

export const RECONCILIATIONS: Record<string, string> = {
  AMBIGUOUS_ATTRIBUTION: "Which slot a removal belongs to is ambiguous.",
  CAPTURE_GAP: "Records have a material capture gap.",
  CLEAN: "Records agree and are complete.",
  CONFLICT: "Records contradict each other.",
  INSUFFICIENT_EVIDENCE: "Not enough evidence to reconcile.",
};

export const ASSURANCE: Record<string, string> = {
  CLAIMED_SLOT: "Slot taken from the work-order claim only.",
  OBSERVED_SLOT_LABEL: "A slot label was scanned near the removal, but not independently corroborated.",
  CORROBORATED_SLOT: "Slot independently corroborated. The only level that clears ambiguity.",
};

export const OBSERVATION_STATUS: Record<string, string> = {
  BLOCKING: "Blocks release. Unreliable, attributable and unanswered.",
  STALE: "Answered by a provably later install.",
  RESOLVED: "Answered by a corroborated verification.",
  UNAFFECTED: "Not an affected lot, so it never blocks and never releases.",
  OUT_OF_SCOPE: "Slot is outside the policy.",
  UNATTRIBUTABLE: "Cannot be tied to a slot or motor.",
};

export const FINDING_TEXT: Record<string, { label: string; explain: string }> = {
  AFFECTED: { label: "Affected", explain: "Evidence shows the motor holds an affected lot." },
  UNRESOLVED: { label: "Unresolved", explain: "Evidence cannot show the motor is clear. It stays held." },
  EXCLUDED_WITH_EVIDENCE: { label: "Excluded with evidence", explain: "Evidence shows the motor is not affected." },
};

export const ACTION_TEXT: Record<string, { label: string; explain: string }> = {
  RECALL_HOLD: { label: "Recall hold", explain: "Operational action: do not ship or release." },
  RELEASE_ELIGIBLE: { label: "Release eligible", explain: "Operational action: may be released." },
};

export const explain = (table: Record<string, string>, code: string): string => table[code] ?? NO_DESCRIPTION;

/** "SOME_CODE" -> "Some code". */
export const humanize = (code: string): string => {
  const t = code.toLowerCase().replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
};
