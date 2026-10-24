# Experiment B: Evidence Contradiction Intelligence (feasibility spike)

Research only. Nothing here changes, extends or is wired into the frozen application. Synthetic data only. Not a production-readiness
claim, not an independent safety certification, no independent custody demonstrated. No feature has been selected.

- Base: tag `manufacturing-demo-v1.0` = `c25466c56e5724158d534ff7b59f01ac48643101` (pinned v3 evaluator unchanged; hashes in `results/run1/env.json`)
- Commits on `research/contradiction-intelligence-spike`: fleets frozen `e641285` (+ AM-1 folded into `3c16c1b`); code `3c16c1b`; raw results `e92e911`; this report is a later docs-only commit
- Environment: Python 3.12.10, Windows 11, standard library only. Seed 20261024 (invariance trials and interpretation sampling; fleets are hand-authored)

## 1. Question and what was built

Question: can PRAMAAN detect physically incompatible manufacturing claims and say which recall conclusions depend on the contested evidence,
without ever changing the authoritative decision?

| Piece | File | Notes |
|---|---|---|
| 18 frozen fleets with authored ground truth | `fleet.py`, `fleets/B01..B18.json`, `MANIFEST.json` | truth (contradiction event sets, class, decision-sensitive motors, hold-status-sensitive motors) written before any detector; AM-1 (B15 omitted a lot-identity conflict) logged in `fleets/AMENDMENTS.md`, made before any detector existed |
| B0 baseline | `baseline.py` | duplicate serial, timestamp order and hash checks, genealogy link checks |
| B1 candidate | `candidate.py` | six declared assumptions (A1-A6 in the module docstring): supplier-scoped identity, one place at a time, one lot per bearing, removal-coverage-gated proof of overlap, declared time uncertainty, superseded records make no claims. Classes DEFINITE / POSSIBLE / INSUFFICIENT. Dependency model: admissible alternative readings of each contradiction (drop an install claim, redact a removal's identity, adopt a lot) replayed through the pinned evaluator on edited copies of one motor's history |
| Probes | `probes.py` | four deliberate violations of B1's assumptions, outside the metrics |
| Tests | `run_experiment.py` | 8 metamorphic relations, 180 invariance trials (event order, motor renaming), scaling |
| Independent replay, safety | `independent_replay.py`, `safety_check.py` | same design as Experiment A |

B1 returns advisory data only: recorded findings re-derived on deep copies, hold-status shown as "depends on contested evidence" (never as an operational action), `authoritativeDecisionUnchanged: true`.

## 2. Results (official run `results/run1`, `--guard`)

| Measure | B0 baseline | B1 candidate |
|---|---|---|
| Contradiction detection vs authored truth (event-set match) precision / recall | 0.53 / 0.67 (10 TP, 9 FP, 5 FN) | 1.00 / 1.00 (17 of 17 strict, incl. kind) |
| Class correct (DEFINITE / POSSIBLE / INSUFFICIENT) | not available | 17 of 17 |
| False positives on the 5 valid-transition fleets (B02 reuse, B03 supplier collision, B06 superseded, B17 lot-level, B18 cycle) | 4 (every fleet but B17) | 0 |
| Which motors' findings depend on contested evidence, precision / recall | impacted = motors owning a flagged event: 0.61 / 1.00 (13 FP) | replay-based 1.00 / 1.00; static evidence-citation trace alone 0.80 / 1.00 (5 FP) |
| Which motors' hold status would flip (hold vs not-hold) under some reading, precision / recall | not available | 1.00 / 1.00 (12 motors) |
| Metamorphic relations passed (8) | 5 | 8 |
| Authoritative decision untouched | n/a | fleet hashes unchanged and recorded findings equal a fresh evaluator run in all 18 fleets |

Evaluator consistency across interpretations: 54 interpretation replays, 0 evaluator errors, 0 non-deterministic results, 0 mismatches against an independent process replay (that process rebuilds nothing; it evaluates the serialised edited cases). Invariance: 180 trials (10 per fleet, shuffled event order and renamed motors), 0 changes in B1's output.

Examples that the dependency model separates from a naive reading:
- B01/B09/B11: contested records on two affected motors; every reading changes their findings, but none changes the hold, so they stay on hold either way.
- B08: two currently excluded motors share a serial; both exclusions rest on contested records (drop either claim and the motor becomes unresolved).
- B05: only the reinstalling motor depends on the lot dispute; the other part of the same contradiction does not change its own finding.
- B07: a missing removal inside a rework-station coverage gap makes the overlap POSSIBLE, not DEFINITE.
- B10: a held motor and an excluded motor; the held motor's hold itself depends on a contested lot reading.

Cost: detection on a chain fleet of 1,000 motors 0.13 s, 2,000 motors 0.50 s (superlinear, roughly 3.7x for 2x). The joint reading space on one motor doubles with each contradiction it takes part in (hub motor: 2, 4, ... 256 readings for 1..8 contradictions, 1.6 s at 8); at 10 and 12 it exceeds the 256 budget and a seeded sample (about 225-250 replays) is used and marked `sampled`. A sampled result supports no robustness claim.

## 3. Failure analysis (assumption-violation probes, not counted in metrics above)

| Probe | Assumption broken | Physical truth | B1 | B0 |
|---|---|---|---|---|
| P1 | A1: supplier re-issues a serial | two distinct bearings | false positive (DEFINITE overlap and lot conflict) | false positive |
| P2 | A3: supplier relabels a lot | same lot, alias | false positive (DEFINITE lot conflict) | correct (does not check lots) |
| P3 | A4: removal done on paper only, coverage claimed complete | no contradiction | false positive (DEFINITE) | false positive |
| P4 | A5: device clock 40 minutes off, beyond declared skew | real overlap | false negative | caught, by accident (duplicate serial) |

So B1 is only as good as the master data and coverage claims it relies on (supplier serial ranges, lot alias tables, real capture coverage, clock discipline). With data that violates them, it misclassifies; the DEFINITE label would then be overconfident. B1's perfect scores on the 18 fleets are from a single author building both the fleets and the detector around the same rules and should be read as agreement with the specification only. One defect was found by the ground-truth comparison and fixed (`results/DEV_HISTORY.md`): hold-status recall was 0.917 because the joint-reading enumeration never left a contradiction unedited.

## 4. Observations about the evaluator (no changes made)

1. A contested install's identity reading matters: if the lot of a contested install were unknown, the pinned evaluator would read it as unaffected and exclude the motor (the same behaviour reported in Experiment A, observation 1). B1's diagnostic `diagnosticUnknownIdentityWouldBeReadAsUnaffected` is true for 9 motor-cases in the fleets where the recorded finding is a hold (for example B01 M101 and M102). It is a diagnostic only and is not part of the metrics.
2. The evaluator reads one motor's history at a time, so a cross-motor impossibility never reaches it. Today nothing in the reviewed code compares claims across motors.

## 5. Adversarial safety

Same design as Experiment A (`results/safety/safety.json`, passed): disposable synthetic SQLite ledger with journal and checkpoint file plus 479 hashed frozen-tree files; the experiment ran under the write guard; 0 changed files, 0 guard violations; negative controls (ledger append, `sqlite3.connect`, frozen-source write, checkpoint overwrite and delete, network connect, database path given to the evaluator wrapper) all blocked; static import scan clean. The advisory output contains no `RELEASE_ELIGIBLE` string (checked). Limits: in-process audit hook, not an OS sandbox; the child replay interpreter is covered by hash comparison only.

## 6. Prior-art comparison

| Contribution actually implemented | Closest published / commercial work | Class |
|---|---|---|
| Constraint violations over records, with violations grouped and interacting | Fan et al., conditional functional dependencies (TODS 2008, not re-checked here); Chu, Ilyas, Papotti, "Holistic Data Cleaning: Putting Violations Into Context", ICDE 2013, pp. 458-469 (denial constraints, conflict hypergraph) | (1) known technique |
| Conclusions that hold across alternative repairs | Arenas, Bertossi, Chomicki, "Consistent Query Answers in Inconsistent Databases", PODS 1999, pp. 68-79 (answers invariant across minimal repairs). B1's dependency model is a bounded, sampled, per-motor approximation of that idea with a fixed repair-operator set | (1) known technique, applied |
| Interval overlap with uncertain timestamps; open occupancy | temporal constraint reasoning (Allen 1983, Dechter-Meiri-Pearl 1991; cited from memory, not re-verified here) | (1) known technique |
| Supplier-scoped identity, removal-coverage-gated DEFINITE vs POSSIBLE, superseded records inert | manufacturing/traceability data quality; aerospace back-to-birth part histories exist as a requirement concept (record every installation and removal), but I did not verify any product flagging one serial installed in two places at once | (2) standard domain adaptation |
| Telling the owner that a hold or an exclusion rests on contested evidence, by replaying alternative readings through the production evaluator without touching the decision | no counterpart found in the sources checked | (3) possibly a distinctive combination; not established |
| Claims of invention, or of superiority over commercial MES / quality tools | no evidence | (4) unsupported |

Commercial side: verified only that Siemens Opcenter fact sheets describe forward and backward genealogy, where-used searches by component lot and quarantine actions. I did not verify any duplicate-installation or contradiction-impact capability in any commercial MES, quality or traceability suite, nor GS1 EPCIS validation behaviour (ISO/IEC 19987:2024 defines the event-exchange standard; I did not find its validation rules). Absence from a shallow search is not evidence of absence. Novelty-risk: medium. The detector uses standard ideas; the differentiator would be the dependency-on-decision view tied to a conservative evaluator.

## 7. Limitations

- Same author for fleets, truth and detector; small fleets (1-4 motors); one policy (P1, DE slot) and the lot-driven evaluator.
- B0 is a deliberately naive baseline; a competent data-quality script with supplier scoping would close much of the detection gap, though not the coverage-gated classes or the dependency view.
- Ground truth for decision-sensitivity was derived from the authored reading of evaluator semantics; B1's reading set (drop/redact/adopt) is what defines "sensitive". Different admissible readings could change the sets.
- Interpretation sampling beyond the budget gives no robustness guarantee.
- Not apples-to-apples with Experiment A: different baselines and metrics; B's ground truth is a labelled set, A's is an exhaustive oracle over a declared space.

## 8. Recommendation for deeper research: GO (conditional)

Reasons: the measured separation from the baseline is large on detection (precision 0.53 to 1.00), on valid-transition false positives (4 to 0) and on impact precision (0.61 to 1.00), the output is a read-only advisory with a clean isolation proof, and it surfaced a real hazard class (exclusions that rest on contested records). Conditions: (a) the supplier-scope, lot-alias and coverage master data must exist or the detector must refuse to classify as DEFINITE (probes P1-P4), (b) independent authoring of fleets and truth by someone other than the detector's author, (c) a decision on the evaluator's unknown-identity behaviour before any interpretation of "unknown" is shown, (d) real-data pilot on exported synthetic-to-real-shaped histories under the same isolation.

## 9. Safe v2 integration boundary (proposal only, not implemented)

A read-only sidecar over already-published evidence copies: no writes to the ledger, journal, checkpoint files or eligibility; no input to `currentReleaseEligible`; output as an audit panel ("this decision rests on contested records X and Y"), never as a clearance or a control; the evaluator is called only through the pinned library on edited copies; frozen-source CI inventory unchanged (new code outside frozen paths). Unresolved: where master data would come from, how cross-motor claims are exposed to the sidecar without widening the API, and how to present POSSIBLE vs DEFINITE without users over-reading either.

## 10. Reproduce

```
git checkout research/contradiction-intelligence-spike
python -B research/contradiction/run_experiment.py --out research/contradiction/results/rerun --seed 20261024 --guard
python -B research/contradiction/safety_check.py --out research/contradiction/results/rerun_safety
```
A clean-clone rerun (without the scaling table) produced a summary identical to `results/run1/summary.json` after removing timings and SHAs.
