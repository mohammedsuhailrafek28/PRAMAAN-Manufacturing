// Reviewed static taxonomy for the investigation workspace.
//
// Every engine reason code and flag is mapped here, explicitly, to one of:
//   - an evidence class (becomes an investigation task),
//   - "INFORMATIONAL" (explains a decision; nothing to investigate),
//   - "OBLIGATION" (a notification matter; shown separately, never an evidence task).
// A code that is not in these tables is NOT dropped: the projection emits an UNCLASSIFIED task.
//
// Wording rule: text names an evidence CLASS and the rule that rejected or lacks it. It never names an
// expected value, never suggests what a record "should" say, never proposes changing a trust
// configuration, and never says that resolving an item releases a motor.

export type EvidenceClass =
  | "UNTRUSTED_AFFECTED_OBSERVATION"
  | "REJECTED_EVIDENCE"
  | "CONFLICTING_RECORDS"
  | "AMBIGUOUS_ATTRIBUTION"
  | "CAPTURE_GAP"
  | "BASELINE_OR_STATE"
  | "COMPLETENESS_OR_INSPECTION"
  | "RAW_MATERIAL_LOT"
  | "UNCLASSIFIED";

export type EvidenceKind = "MISSING" | "CONFLICTING" | "UNTRUSTED" | "AMBIGUOUS" | "SHARED_CONTEXT" | "UNCLASSIFIED";

export interface ClassInfo {
  label: string;
  kind: EvidenceKind;
  /** Fixed rank used by the published ordering; lower sorts first. */
  rank: number;
  /** What the ledger lacks, contradicts or distrusts. */
  statement: string;
  /** What a quality engineer should independently investigate. No values, no outcomes. */
  investigate: string[];
}

const NOT_PROOF = "Absence from the ledger is not evidence that nothing happened; paper or other records may exist outside it.";

export const CLASSES: Record<EvidenceClass, ClassInfo> = {
  UNTRUSTED_AFFECTED_OBSERVATION: {
    label: "Untrusted affected-lot observation",
    kind: "UNTRUSTED",
    rank: 0,
    statement:
      "A record shows a lot named in the recall in this slot, but the ledger rejected it as evidence and no later trusted record answers it. A rejected record is not shown to be false; it is not accepted as proof either way.",
    investigate: [
      "Find out independently, through your own quality procedures, what this slot actually holds. Do not rely on the rejected record to settle it.",
      "Review why the record was rejected (the listed source, method and actor findings) and whether what the ledger recorded about the source, method and actor matches what happened.",
      "Any new evidence has to come from independently trusted capture. Approving the rejected source, method or actor after the fact is not evidence.",
    ],
  },
  REJECTED_EVIDENCE: {
    label: "Evidence rejected for source, method or actor",
    kind: "UNTRUSTED",
    rank: 1,
    statement:
      "A verification record exists but the ledger did not accept it because of its source, method or actor. It therefore does not support or clear anything in the decision.",
    investigate: [
      "Establish independently whether the recorded observation is correct; the rejected record does not decide it.",
      "Review the listed rejection findings against what actually happened at capture.",
      "New evidence has to come from independently trusted capture. Approving the rejected source, method or actor after the fact is not evidence.",
    ],
  },
  CONFLICTING_RECORDS: {
    label: "Conflicting records",
    kind: "CONFLICTING",
    rank: 2,
    statement: "Records in the ledger contradict each other about what a slot held or what was removed from it.",
    investigate: [
      "Determine independently which record, if any, reflects the physical state.",
      "Do not reconcile by editing history: a correction has to arrive as new evidence, which the evaluator will weigh under the policy.",
    ],
  },
  AMBIGUOUS_ATTRIBUTION: {
    label: "Ambiguous slot attribution",
    kind: "AMBIGUOUS",
    rank: 3,
    statement:
      "A removal of a part that matches the recall could belong to more than one slot, and nothing independent shows which. The slot named by the work-order claim alone is not enough under the policy.",
    investigate: [
      "Establish, from independent records held outside the claim itself, which slot the removed part came from.",
      "Review whether the record that names the slot is only a work-order claim, and what other capture exists for that removal.",
      "The policy accepts only independently corroborated slot evidence as clearing this ambiguity.",
    ],
  },
  CAPTURE_GAP: {
    label: "Capture gap",
    kind: "MISSING",
    rank: 4,
    statement: "A source was not recording for a period in which a relevant change to the slot could have happened unseen. " + NOT_PROOF,
    investigate: [
      "Establish, from independent records (for example travelers, station logs or maintenance records), whether any change to this slot occurred in the window.",
      "Establish why capture was interrupted and whether other sources cover the window.",
      "Do not infer that nothing happened from the absence of records.",
    ],
  },
  BASELINE_OR_STATE: {
    label: "No trusted baseline or unverified current state",
    kind: "MISSING",
    rank: 5,
    statement: "The ledger has no as-built or verified record that the policy accepts for this slot's current state. " + NOT_PROOF,
    investigate: [
      "Establish, from independent build and inspection records, what this motor was built with and what it holds now.",
      "Review which records exist outside the ledger and how they could be captured as trusted evidence.",
    ],
  },
  COMPLETENESS_OR_INSPECTION: {
    label: "Completeness or inspection evidence",
    kind: "MISSING",
    rank: 6,
    statement: "A required inspection, completeness or exposure-history record is missing, invalid or inconclusive under the policy. " + NOT_PROOF,
    investigate: [
      "Establish independently what the policy requires here and what exists in your quality records.",
      "New evidence has to come from independently trusted capture.",
    ],
  },
  RAW_MATERIAL_LOT: {
    label: "Shared raw-material lot",
    kind: "SHARED_CONTEXT",
    rank: 8,
    statement:
      "Several motors with open evidence items hold, or held, bearings traced by the ledger to the same raw-material lot. This is shared context, not a gap in itself. The supplier and lot information is a claim made by the source stream, not independently verified.",
    investigate: [
      "Review the material allocation and manufacture records for this raw-material lot, and the supplier records you hold outside the ledger.",
      "Consider whether the same material evidence need applies to every listed motor; the ledger does not decide that.",
    ],
  },
  UNCLASSIFIED: {
    label: "Unclassified item",
    kind: "UNCLASSIFIED",
    rank: 7,
    statement:
      "The decision lists something that is not in the reviewed taxonomy, or a hold has no listed evidence reason. It is shown so that it cannot be missed. No investigation guidance has been reviewed for it.",
    investigate: ["Read the decision's own explanation and its supporting records, and consult the recall owner."],
  },
};

export type Handling =
  | { handling: "TASK"; cls: EvidenceClass }
  | { handling: "INFORMATIONAL" }
  | { handling: "OBLIGATION" };

const task = (cls: EvidenceClass): Handling => ({ handling: "TASK", cls });
const INFO: Handling = { handling: "INFORMATIONAL" };

/** Every reason code the pinned v3 engine can emit, plus the codes in the UI glossary. */
export const REASON_HANDLING: Record<string, Handling> = {
  // Evidence-need classes
  UNTRUSTED_AFFECTED_OBSERVATION: task("UNTRUSTED_AFFECTED_OBSERVATION"),
  AMBIGUOUS_SLOT_ATTRIBUTION: task("AMBIGUOUS_ATTRIBUTION"),
  LOT_LEVEL_SLOT_AMBIGUITY: task("AMBIGUOUS_ATTRIBUTION"),
  MATERIAL_CAPTURE_GAP: task("CAPTURE_GAP"),
  SOURCE_SEQUENCE_GAP: task("CAPTURE_GAP"),
  DOUBLE_OCCUPANCY: task("CONFLICTING_RECORDS"),
  REMOVAL_OBSERVATION_MISMATCH: task("CONFLICTING_RECORDS"),
  REMOVAL_SERIAL_IN_OTHER_SLOT: task("CONFLICTING_RECORDS"),
  REMOVAL_RECORD_INCONSISTENT: task("CONFLICTING_RECORDS"),
  VERIFIED_STATE_MISMATCH: task("CONFLICTING_RECORDS"),
  VERIFIED_STATE_MISMATCH_RISK_DECREASING: task("CONFLICTING_RECORDS"),
  LATE_CLAIM_RISK_INCREASING: task("CONFLICTING_RECORDS"),
  EVENT_ORDER_INTEGRITY: task("CONFLICTING_RECORDS"),
  EVENT_INTEGRITY_VIOLATION: task("CONFLICTING_RECORDS"),
  WORK_ORDER_UNRECONCILED: task("CONFLICTING_RECORDS"),
  NO_TRUSTED_BASELINE: task("BASELINE_OR_STATE"),
  CURRENT_STATE_UNVERIFIED: task("BASELINE_OR_STATE"),
  UNTRUSTED_SOURCE_CLAIM: task("BASELINE_OR_STATE"),
  DAMAGE_INSPECTION_MISSING: task("COMPLETENESS_OR_INSPECTION"),
  DAMAGE_INSPECTION_INVALID: task("COMPLETENESS_OR_INSPECTION"),
  DAMAGE_INSPECTION_FAILED: task("COMPLETENESS_OR_INSPECTION"),
  REMEDIATION_COMPLETENESS_UNCERTAIN: task("COMPLETENESS_OR_INSPECTION"),
  EXPOSURE_UNKNOWN: task("COMPLETENESS_OR_INSPECTION"),
  HISTORY_GAP_NOT_RECOVERED_BY_VERIFICATION: task("COMPLETENESS_OR_INSPECTION"),
  // A notification matter, handled in its own panel, never an evidence task.
  PRIOR_EXCLUSION_WITHDRAWN: { handling: "OBLIGATION" },
  // Explain a decision; nothing left to investigate
  AFFECTED_LOT_INSTALLED: INFO,
  VERIFIED_AFFECTED_LOT_PRESENT: INFO,
  HISTORICAL_EXPOSURE_CONFIRMED: INFO,
  CORROBORATED_BY_VERIFICATION: INFO,
  DAMAGE_INSPECTION_PASSED: INFO,
  EXPOSURE_REMEDIATED: INFO,
  REPLACED_WITH_UNAFFECTED_LOT: INFO,
  AS_BUILT_UNAFFECTED_LOT: INFO,
  VERIFIED_UNAFFECTED_LOT: INFO,
  GAP_BOUNDED_BY_VERIFICATION: INFO,
  IRRELEVANT_SLOT_GAP: INFO,
  SLOT_EMPTY: INFO,
  NO_HISTORICAL_EXPOSURE: INFO,
  LATE_CLAIM_RISK_DECREASING_NOT_APPLIED: INFO,
};

/** Flags are separate from reason codes; the same rule applies. */
export const FLAG_HANDLING: Record<string, Handling> = {
  OUT_OF_SCOPE_UNTRUSTED_AFFECTED_OBSERVATION: task("UNTRUSTED_AFFECTED_OBSERVATION"),
  UNATTRIBUTABLE_UNTRUSTED_AFFECTED_OBSERVATION: task("UNTRUSTED_AFFECTED_OBSERVATION"),
  SLOT_RECORD_CONFLICT: task("CONFLICTING_RECORDS"),
  UNTRUSTED_AFFECTED_OBSERVATION_SUPERSEDED: INFO,
  KNOWN_LIMITATION_LOT_LEVEL_SLOT_AMBIGUITY: INFO,
};

export const REJECTION_TEXT: Record<string, string> = {
  SOURCE_NOT_TRUSTED: "The capture source is not one the coverage policy trusts as a verifier.",
  METHOD_NOT_APPROVED: "The method named in the record is not an approved verification method.",
  ACTOR_NOT_AUTHORIZED: "The actor named in the record is not an authorized verifier.",
  ACTOR_NOT_INDEPENDENT: "The actor is not independent of the work being verified.",
  SOURCE_NOT_INDEPENDENT: "The source is not independent of the work being verified.",
  EVIDENCE_NOT_INDEPENDENT: "The evidence is not independent of the record it would confirm.",
  UNAUTHENTICATED_SESSION: "The capture session was not authenticated.",
  UNTRUSTED: "The record was rejected as untrusted; no specific rule is listed.",
};

/** Notification obligations stay separate from evidence tasks. */
export const OBLIGATION_NOTE =
  "Notification obligations are managed in the recall console. They are not evidence-gathering tasks and nothing here marks one as communicated.";

/** Always shown with the evidence watermark. */
export const LIMITATIONS: string[] = [
  "A task is a view of what the recall evaluator listed for a decision. It is not a full list of what would change the decision, and resolving a listed item does not by itself release a motor.",
  "“Not recorded” means not in the ledger as of the watermark shown. Records may exist elsewhere.",
  "Priority is a fixed, published ordering of the groups. It is not a risk score or a probability.",
  "All timestamps come from a simulated clock, and supplier and raw-material information are unverified claims by the source stream.",
  "This workspace is read-only. It cannot assign, complete, approve or resolve anything, and it never changes a decision.",
];
