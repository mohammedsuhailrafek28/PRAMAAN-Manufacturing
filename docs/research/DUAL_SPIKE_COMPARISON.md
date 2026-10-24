# Dual feasibility spike: side-by-side comparison (no winner selected)

Research only; synthetic data; loopback; not production-ready; not independent safety certification; independent custody not demonstrated.
The frozen baseline `manufacturing-demo-v1.0` (`c25466c5...`) was not touched. This document selects nothing and freezes no architecture.

| Experiment | Branch | Scenarios frozen | Code | Raw results | Report (docs-only commit) |
|---|---|---|---|---|---|
| A Counterfactual Recall Intelligence | `research/counterfactual-recall-spike` | `6ba87ce` | `be32d25` | `a7c5fb1` | `88d30da`, `research/counterfactual/REPORT.md` |
| B Evidence Contradiction Intelligence | `research/contradiction-intelligence-spike` | `e641285` | `3c16c1b` | `e92e911` | `ee4c11c`, `research/contradiction/REPORT.md` |

Clean-clone reproduction: both branches were cloned into empty directories and rerun (scaling excluded); normalised summaries (timings and SHAs removed) were identical to the committed `results/run1/summary.json` for A and for B. Python 3.12.10, standard library only.

## Tradeoff matrix

Same criteria for both. "Not apples to apples" marks where the numbers cannot be compared directly.

| Criterion | A Counterfactual | B Contradiction | Comparability |
|---|---|---|---|
| Correctness vs reference | A1 equals an exhaustive oracle in 18/18 scenarios and 360 random catalogs; 30/30 independent replays agree | B1 matches authored truth: detection 17/17, class 17/17, sensitive motors 20/20, hold-flip motors 12/12; 54/54 interpretation replays agree with an independent process | Not apples to apples: A's reference is exhaustive over a declared space; B's is a hand-labelled truth set |
| Improvement over own baseline | vs static reason-code table: table is non-minimal in 3/12 resolvable and gives a false promise in 5/6 unresolvable; admissibility blocks a clerical clearance the evaluator accepts | vs naive checks: precision 0.53 to 1.00, recall 0.67 to 1.00; false positives on valid fleets 4 to 0; impact precision 0.61 to 1.00 | Baselines differ in strength; both baselines are simple and self-written |
| Technical differentiation / prior art | search is known (counterfactuals, how-to queries, diagnosis); differentiation rests on the admissibility model and replay discipline; novelty-risk medium-high | constraint checking and repair-invariant answers are known; differentiation is the decision-dependency view over a conservative evaluator; novelty-risk medium | Both: no evidence for invention claims |
| Adversarial robustness | 400/400 invalid ops rejected; unsound pruning misses outcomes (1/18); relies on a hand-declared catalog | detector fails when its assumptions are false: 3 false positives and 1 false negative in 4 assumption-violation probes; relies on master data and coverage claims | A's risk is a wrong catalog; B's risk is wrong master data |
| Engineering feasibility | needs expert-authored obtainability/issuer catalog (unvalidated) | needs supplier-scope, lot-alias, coverage and clock data (not present in the frozen model) | Both depend on data that does not exist yet |
| Runtime / scaling | exact search C(n,K) evaluator runs: 8,688 runs / 9.5 s at n=22, K=4; sound pruning saved nothing | detection ~0.5 s for 2,000 motors; per-motor reading space doubles per contradiction (sampled beyond 256) | Different growth drivers |
| Explainability | structured "to move X to Y you would need ..." with issuer, preconditions, outcome dependence, search scope and alternatives; rubric 6.33/8 vs 0.83/8 (structural rubric, not a user study) | per-contradiction event set, class, assumptions used, and which motors' findings or hold status depend on it | Neither tested with users |
| Demonstration value | conditional "what would clear this" panel; risk of being read as a promise | "this exclusion rests on contested records" is a concrete, checkable story on synthetic fleets | Judgement, not measured |
| Safety / integration risk | advisory only; main risk is hypotheses being misread as expected results | advisory only; main risk is overconfident DEFINITE labels on bad master data; also exposes cross-motor claims the current API does not | Both passed isolation: 0 changed files, 0 guard violations, negative controls blocked |

## Evaluator observations common to both (no change made)

1. An install record with missing/empty/unknown lot is evaluated as EXCLUDED_WITH_EVIDENCE (`research/counterfactual/results/probe_unknown_lot.txt`). Whether the production application can create such a record is unexamined.
2. Sequence-gap detection ignores a source with no visible events.
3. A correction record is a claim that even a matching trusted verification does not turn into a clearance (A06); risk-increasing corrections cannot be cleared by any admissible evidence in the searched space (A17).
4. The evaluator is single-motor; cross-motor impossibilities are invisible to it.

## Safe v2 integration boundaries (proposals, not implemented)

Common rules for either idea: separate read-only module or process; inputs are copies of already-published evidence; the pinned evaluator is called only as a library on copies; no write path to ledger, journal, checkpoint files or eligibility; advisory output only, no release control, fixed hypothetical/advisory wording, no operational action shown for a hypothetical reading; new code outside frozen-source paths so the CI inventory is unchanged; the same write-guard and hash-comparison safety check runs in CI before any merge is even proposed. The two ideas were not combined and no joint design was evaluated.

## Recommendations for deeper research (not a feature selection)

- A Counterfactual: REVISE (expert-authored catalog first; scaling and pruning unsolved; gain is mainly the admissibility layer and removal of false promises).
- B Contradiction: GO, conditional (needs master data or refusal to classify DEFINITE without it; independent authoring of fleets and truth; owner decision on the evaluator's unknown-identity behaviour).

These are recommendations about whether to research further, from self-authored synthetic evidence only. The owner chooses.

## Unresolved questions for the owner

1. Can the production application ever record an install with an unknown lot, and should the evaluator treat that as unresolved? (Both spikes hit this.)
2. Is cross-motor information allowed to leave the per-motor evaluator boundary in a future read-only module?
3. Who can independently author catalogs, fleets and ground truth (the current evidence is single-author)?
4. Is there appetite to look at how advisory text is read by operators before building anything?
