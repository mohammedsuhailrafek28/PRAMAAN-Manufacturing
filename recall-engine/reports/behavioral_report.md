# Behavioral agreement report: engine vs supplied expected outcomes

Measures only whether the engine reproduces `oracle.json`. **This is not a safety measure.** Case 06 passes here by design and is a false exclusion in the safety report.

## Summary

- Evaluations compared: **25** (10 cases, both policies, every decision version)
- Decision-level pass (finding + operational action + reviewRequired): **25/25 (100.0%)**
- Full pass (decision + reason codes + watermark + per-slot reconciliation, gaps, conflicts, supersession link, trigger, notification): **25/25 (100.0%)**
- Flag agreement (informational flags compared separately): 25/25 (100.0%)

## By recall policy

| Policy | Evaluations | Decision-level pass | Full pass |
|---|---|---|---|
| RC-009/P1 | 13 | 13/13 (100.0%) | 13/13 (100.0%) |
| RC-009/P2 | 12 | 12/12 (100.0%) | 12/12 (100.0%) |

## Every evaluation

| Case | Policy | Ver | Expected (finding / action / review) | Engine | Decision | Full |
|---|---|---|---|---|---|---|
| case-01 | P1 | v1 | EXCLUDED / RELEASE_ELIGIBLE / false | EXCLUDED / RELEASE_ELIGIBLE / false | pass | pass |
| case-01 | P2 | v1 | AFFECTED / RECALL_HOLD / false | AFFECTED / RECALL_HOLD / false | pass | pass |
| case-02 | P1 | v1 | UNRESOLVED / RECALL_HOLD / true | UNRESOLVED / RECALL_HOLD / true | pass | pass |
| case-02 | P2 | v1 | AFFECTED / RECALL_HOLD / false | AFFECTED / RECALL_HOLD / false | pass | pass |
| case-03 | P1 | v1 | UNRESOLVED / RECALL_HOLD / true | UNRESOLVED / RECALL_HOLD / true | pass | pass |
| case-03 | P2 | v1 | AFFECTED / RECALL_HOLD / false | AFFECTED / RECALL_HOLD / false | pass | pass |
| case-04 | P1 | v1 | EXCLUDED / RELEASE_ELIGIBLE / false | EXCLUDED / RELEASE_ELIGIBLE / false | pass | pass |
| case-04 | P2 | v1 | EXCLUDED / RELEASE_ELIGIBLE / false | EXCLUDED / RELEASE_ELIGIBLE / false | pass | pass |
| case-04b | P1 | v1 | UNRESOLVED / RECALL_HOLD / true | UNRESOLVED / RECALL_HOLD / true | pass | pass |
| case-04b | P2 | v1 | AFFECTED / RECALL_HOLD / false | AFFECTED / RECALL_HOLD / false | pass | pass |
| case-04c | P1 | v1 | UNRESOLVED / RECALL_HOLD / true | UNRESOLVED / RECALL_HOLD / true | pass | pass |
| case-04c | P2 | v1 | UNRESOLVED / RECALL_HOLD / true | UNRESOLVED / RECALL_HOLD / true | pass | pass |
| case-05 | P1 | v1 | EXCLUDED / RELEASE_ELIGIBLE / false | EXCLUDED / RELEASE_ELIGIBLE / false | pass | pass |
| case-05 | P1 | v2 | UNRESOLVED / RECALL_HOLD / true | UNRESOLVED / RECALL_HOLD / true | pass | pass |
| case-05 | P2 | v1 | AFFECTED / RECALL_HOLD / false | AFFECTED / RECALL_HOLD / false | pass | pass |
| case-05 | P2 | v2 | AFFECTED / RECALL_HOLD / false | AFFECTED / RECALL_HOLD / false | pass | pass |
| case-05b | P1 | v1 | EXCLUDED / RELEASE_ELIGIBLE / false | EXCLUDED / RELEASE_ELIGIBLE / false | pass | pass |
| case-05b | P1 | v2 | UNRESOLVED / RECALL_HOLD / true | UNRESOLVED / RECALL_HOLD / true | pass | pass |
| case-05b | P1 | v3 | AFFECTED / RECALL_HOLD / false | AFFECTED / RECALL_HOLD / false | pass | pass |
| case-05b | P2 | v1 | AFFECTED / RECALL_HOLD / false | AFFECTED / RECALL_HOLD / false | pass | pass |
| case-05b | P2 | v2 | AFFECTED / RECALL_HOLD / false | AFFECTED / RECALL_HOLD / false | pass | pass |
| case-06 | P1 | v1 | EXCLUDED / RELEASE_ELIGIBLE / false | EXCLUDED / RELEASE_ELIGIBLE / false | pass | pass |
| case-06 | P2 | v1 | AFFECTED / RECALL_HOLD / false | AFFECTED / RECALL_HOLD / false | pass | pass |
| case-06b | P1 | v1 | AFFECTED / RECALL_HOLD / false | AFFECTED / RECALL_HOLD / false | pass | pass |
| case-06b | P2 | v1 | AFFECTED / RECALL_HOLD / false | AFFECTED / RECALL_HOLD / false | pass | pass |

## Disagreements

None.

## Strict lot-ambiguity profile (optional `Config(strict_lot_ambiguity=True)`)

- Decision-level pass: 24/25 (96.0%); full pass: 24/25 (96.0%)
- Disagreements with the supplied expectations under this profile:
  - case-06 RC-009/P1 v1: ['evidenceFinding: expected EXCLUDED_WITH_EVIDENCE got UNRESOLVED', 'operationalAction: expected RELEASE_ELIGIBLE got RECALL_HOLD', 'reviewRequired: expected False got True', "reasonCodes: expected ['REPLACED_WITH_UNAFFECTED_LOT'] got ['LOT_LEVEL_SLOT_AMBIGUITY']"]

The default profile follows the agreed lot-level semantics. The strict profile is the engine declining to exclude when a lot-level scan cannot be told apart from a sibling slot holding the same lot; it is the only expectation it breaks (see safety report).
