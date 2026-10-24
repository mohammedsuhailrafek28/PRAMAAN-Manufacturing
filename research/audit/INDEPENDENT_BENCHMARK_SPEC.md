# Independent adversarial benchmark: pre-registered specification (DRAFT for owner approval)

Status: specification only. No candidate has been run against anything described here. The existing authored datasets (`research/counterfactual/scenarios/A01..A18`, `research/contradiction/fleets/B01..B18`) and their ground truth are not altered and are not reused as evidence for selection. No innovation is selected. Synthetic data only; read-only advisory modules; nothing here touches the frozen baseline.

## 1. Why a new benchmark

The earlier results (A: 18/18 vs oracle; B: P/R 1.0/1.0) were produced by one author who wrote the scenarios, the truth, the baselines and the candidates around the same rules. They show agreement with the specification, not discrimination ability. The lot audit (`UNKNOWN_LOT_AUDIT.md`) also shows the evaluator's own notion of "unaffected" is weaker than the spikes assumed, so an unaffected result must not be presented as robust.

## 2. Independent authorship protocol

1. Authors: at least one reviewer who has not read the candidate code (preferred: two, working separately); acceptable substitute: examples taken from externally documented sources (public recall notices, public quality/CAPA write-ups, standards on traceability such as EPCIS event semantics), cited per case with what was taken and what was invented.
2. Authors receive only: the data model (event types, fields), the evaluator's published semantics, and the oracle definition below. They do not receive candidate code or earlier datasets.
3. Each case is written as input history + recall policy + authored expected outcome + authored rationale + declared uncertainty ("the truth itself is arguable": yes/no). Expected outcomes are committed (hash recorded in this repository) before any candidate runs. Any later change is an amendment log entry with reason; amendments after candidate runs make that case non-confirmatory.
4. A case-reviewer (a different person) checks that each expected outcome follows from the stated physical facts, not from the candidate's logic. Disagreements are kept and scored as "contested" rather than resolved by the candidate's author.
5. Split: 30% development cases visible to candidate authors, 70% sealed until the single confirmatory run. Candidate code is frozen (commit hash) before the sealed split is opened.
6. If no independent author exists, the report states "no independent evidence", and the benchmark is used only to find failure modes, never to rank.

## 3. Assumptions to record before testing (each stated in the case file)

- What is physically obtainable: a per-case list of evidence that can and cannot exist (issuer, time window, cost), authored independently of the counterfactual catalog.
- Master data available: supplier serial scopes, lot aliases, removal-coverage claims, clock accuracy. Each case marks each item as present, absent, or wrong.
- What counts as a correct answer: a candidate output is scored against the authored outcome and also against the authored "must not claim" list.

## 4. Adversarial families (owner-listed items first)

| ID | Family | What is probed | Expected behaviour (to be authored; outline only) |
|---|---|---|---|
| F1 | Catalog incompleteness (A) | catalog omits a real clearing action; catalog includes actions that cannot physically occur (destructive tests on shipped goods, unreachable supplier, expired window) | no suggestion may rely on an unobtainable action; a missing real action must be disclosed as "search scope" not "no path"; "cannot be cleared" claims need a stated catalog scope |
| F2 | Physically unobtainable evidence | evidence requiring access that no longer exists (motor shipped and in service, scrapped part) | candidate must say "unobtainable" and not offer it as a path |
| F3 | Serial reuse | supplier legitimately reuses a serial across bearings/years; reuse across suppliers | no DEFINITE contradiction without supplier-scoped identity; POSSIBLE or INSUFFICIENT with the missing data named |
| F4 | Lot relabelling | alias, merge or split of lots by supplier or by internal rework | no DEFINITE lot conflict from alias; impact must show dependence on the alias table |
| F5 | Incomplete removal records | removal done but unrecorded (coverage gap), recorded without evidence, recorded late | overlap is POSSIBLE unless coverage is proven; DEFINITE only with a stated coverage claim |
| F6 | Clock disagreement | skew beyond declared tolerance, timezone errors, replayed or batch-uploaded events, device reset to epoch | ordering-dependent conclusions downgraded; undeclared skew must not produce a confident class |
| F7 | Missing issuer/master data | no supplier scope, no lot master, no policy owner | detection and impact must degrade to INSUFFICIENT with named missing data; no silent defaults |
| F8 | Over-claimed robustness | "unaffected" result that rests on a near-miss lot string, an unrecognised lot, a single untrusted observation, or the exact-match rule (see audit) | the candidate must not label such a result robust; the authoritative decision is not changed |
| F9 | Unknown/unrecognised identity | UNKNOWN, typo, case/dash/zero-width variants of a recalled lot (reachable per audit) | flagged as identity not established; never reported as independent confirmation of clearance |
| F10 | Valid-but-odd histories | legitimate rework cycles, swaps between motors, reinstallation of the same bearing, cancelled work orders | zero false contradictions |
| F11 | Scale and noise | fleets of thousands with sparse true contradictions; benign data-entry noise | precision at low prevalence; runtime; sampled results never labelled as proofs |
| F12 | Prompt/format hostility | evidence text containing instruction-like strings, oversized fields, unicode confusables | output unaffected; no execution; no leakage of internal state |

Cross-motor reading (approved by the owner) applies to B only, on copies of evidence, read-only and advisory. Cases may therefore span motors.

## 5. Oracle and baselines

- Oracle: authored expected outcome plus rationale; where a space is declared and small, an exhaustive search by the independent author (not a candidate) is allowed as a second oracle.
- Baselines (written by someone other than the candidate author, or a published tool script): B0 (A): static reason-code table; B0 (B): supplier-scoped duplicate check; and a human-expert baseline if any reviewer is willing to answer a subset blind.
- A "do nothing" baseline (the authoritative evaluator alone) is always reported.

## 6. Metrics (declared in advance)

- A: exact-match of minimal admissible clearing sets vs authored; rate of false promises; rate of suggested unobtainable evidence (must be 0 for acceptance); disclosure correctness of search scope; invalid-operation rejection.
- B: contradiction precision, recall, class accuracy (DEFINITE/POSSIBLE/INSUFFICIENT) per family; false-DEFINITE rate (must be 0 in F3 to F6 with missing/wrong master data to be acceptable); impact precision/recall; correct refusal rate when data is missing; F8/F9 over-claim rate.
- Both: contested-case share; runtime and memory; reproducibility from a clean clone; safety isolation checks (0 changed files, 0 guard violations, no write path, no `RELEASE_ELIGIBLE` string emitted by the advisory).
- Report confidence intervals (Wilson for proportions); no ranking claim below n = 30 per family.

## 7. Acceptance thresholds (proposed, owner to confirm before any run)

- Hard stops (any one fails the idea for further investment): a false DEFINITE or a suggestion that relies on unobtainable evidence in any F1 to F7 case; any change to authoritative state; any F8 over-claim.
- Soft: precision and recall at least 0.9 on independent confirmatory cases, with the baseline gap at least 0.2; zero false contradictions on F10.

## 8. Expected outcomes recorded before testing (predictions, to be checked, not to be tuned to)

- A: will do well on F1 where the catalog is complete and on F2 only if obtainability is in the catalog; expected to fail or over-promise when the independent author's catalog differs. Prediction: at least one hard-stop failure in F1/F2 on first contact.
- B: expected false DEFINITE in F3, F4, F5 and F6 when master data is absent unless the detector refuses to classify without it (the earlier probes P1 to P4 gave 3 false positives and 1 false negative). Prediction: at least one hard-stop failure unless the refusal rule is added before the confirmatory run.
- Both: F8/F9 handling is unspecified in both candidates; prediction: neither addresses it without a design change.
- The authoritative evaluator alone: expected to fail F9 (audit-confirmed on the production path).

## 9. Process

1. Owner approves this spec (thresholds, authors, any dataset sources).
2. Authors produce development and sealed splits; commit hashes of sealed files recorded.
3. Candidate code frozen by commit; one confirmatory run; results committed unchanged.
4. Failures reported as failures. No candidate re-tuning on sealed cases; any later change is a new candidate version evaluated on a fresh sealed split.
5. Nothing is selected or built from this benchmark without a separate owner decision.

## 10. Open questions for the owner

1. Who can be the independent author and reviewer? Are there real (anonymised) records or published recall write-ups the owner can supply?
2. Which master data would exist in a real deployment (supplier serial ranges, lot aliases, coverage claims)?
3. Are the proposed hard stops the right ones?
4. Should the lot-identity correction (see audit) land before any benchmark that depends on unaffected results?
