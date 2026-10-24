# Experiment A: Counterfactual Recall Intelligence (feasibility spike)

Research only. Nothing here changes, extends or is wired into the frozen application. Synthetic data only. Not a production-readiness
claim, not an independent safety certification, no independent custody demonstrated. No feature has been selected.

- Base: tag `manufacturing-demo-v1.0` = `c25466c56e5724158d534ff7b59f01ac48643101` (pinned v3 evaluator unchanged; hashes in `results/run1/env.json`)
- Commits on `research/counterfactual-recall-spike`: scenarios frozen `6ba87ce`; code `be32d25`; raw results `a7c5fb1`; this report is a later docs-only commit
- Environment: Python 3.12.10, Windows 11, standard library only. Seed 20261024 (fuzz and catalog ablation; scenarios are hand-authored, no randomness)

## 1. Question and what was built

Question: can PRAMAAN identify the minimum admissible additional evidence that would change a motor's recall classification, while the
pinned evaluator stays the only authority?

| Piece | File | Notes |
|---|---|---|
| 18 frozen scenarios | `scenarios.py`, `scenarios/A01..A18.json`, `MANIFEST.json` | committed before any candidate ran; one logged amendment (`scenarios/AMENDMENTS.md` AM-1, also before any result) |
| Operation catalog and admissibility rules | `ops.py` | six op classes, each with issuer, chronology, identity and obtainability rules checked on the concrete event parameters |
| A0 baseline | `methods.py` (`A0_TABLE`, `a0`) | reason code to predetermined request class; written before A1 |
| A1 candidate | `methods.py` (`search`) | exact level-wise search over subsets of the admissible catalog, sizes 1..3, every candidate replayed through the pinned evaluator in a sandbox |
| A1p variant | `run_experiment.py` | same search restricted to op classes the A0 table names (a relevance heuristic) |
| Oracle | `methods.brute_force_oracle` | enumerates every subset with no memo, no pruning, no early exit; also run over a catalog that includes inadmissible ops |
| Independent replay | `independent_replay.py` | separate interpreter, consumes only serialised JSON, imports no experiment code |
| Safety | `safety.py`, `safety_check.py`, `build_fixture.py` | write guard, hash comparison, negative controls, static import scan |

A1 output is always labelled hypothetical, never contains `RELEASE_ELIGIBLE` (checked), and minimality is claimed only within the
declared operation set and size bound (K=3).

## 2. Results (official run `results/run1`, `--guard`)

Scenarios: 12 resolvable (a path to EXCLUDED_WITH_EVIDENCE exists in the space), 6 not (A06, A08, A10, A11, A13, A17).

| Measure | A0 baseline | A1 candidate |
|---|---|---|
| Minimal and correct, resolvable scenarios (12) | 9 | 12 (equal to oracle: 18/18 scenarios, all targets) |
| Correct but not minimal | 3 (A01, A14, A15) | 0 |
| Insufficient or missed | 0 | 0 |
| False promise on the 6 unresolvable scenarios | 5 (A06, A08, A11, A13, A17) | 0 (reports no solution in the searched space, search complete) |
| Equally minimal alternatives preserved (A04: verification or archive access evidence) | no | yes |
| Rubric score (8 structural items, see caveat) | 0.83 | 6.33 |

Correctness and robustness of A1:
- A1 equals the brute-force oracle in 18/18 scenarios; over 360 randomly ablated catalogs (seed 20261024) there were 0 disagreements.
- Independent full-evaluator replay in a separate process: 30 reported minimal solutions, 0 mismatches.
- A1p (relevance heuristic) matched the oracle in 17/18. It missed that an affected-lot verification can reach AFFECTED in A08, because the heuristic only follows op classes the baseline table names. Unsound pruning loses outcomes.
- Admissibility: 400/400 mutated ops (11 mutation kinds: wrong issuer, unauthorised or non-independent actor, back-dating, recorded-before-occurred, wrong motor, lot outside domain, missing evidence reference, tampered envelope, unapproved method, wrong protocol) were rejected; 0 missed. The catalog rejected exactly the 3 ops expected (A09 clerical closure; A10 two repeat verifications by the same verifier).
- 18 of the 400 mutants would have been accepted by the evaluator alone as clearing the motor. In A09 the evaluator accepts a clerical `CAPTURE_EXCEPTION_RESOLVED` as a size-1 clearance; the admissibility layer rejects it. An evaluator-only counterfactual search would recommend it.

Cost (demo scale): A1 551 evaluator runs / 0.70 s in total for 18 scenarios; oracle 548 runs / 0.75 s. Sound subset-dominance pruning saved nothing (0 skipped at every size tested) because most subsets are distractors, not supersets of solutions. Growth with a padded catalog (A18 plus synthetic admissible distractors), exact search:

| catalog size | K=2 | K=3 | K=4 |
|---|---|---|---|
| 6 | 20 runs | 32 | 36 |
| 14 | 104 | 444 | 1,314 (1.6 s) |
| 22 | 252 | 1,752 | 8,688 (9.5 s) |

Cost is C(n,K) evaluator runs (about 1 ms each here). Beyond a few dozen admissible operations or K>4 the exact search is not viable without a sound pruning idea that was not found.

## 3. What the experiment found about the evaluator (observations, no changes made)

1. An install record with a missing, empty or `"UNKNOWN"` lot is evaluated as `EXCLUDED_WITH_EVIDENCE` (`AS_BUILT_UNAFFECTED_LOT`); reproduce with `python -B research/counterfactual/probe_unknown_lot.py` (output in `results/probe_unknown_lot.txt`; the control with an affected lot gives AFFECTED). This contradicts the policy module's stated rule that missing evidence never produces an exclusion. Whether the production application can ever produce such a record was not examined.
2. `integrity.check` reports sequence gaps only for sources that have at least one visible event, so a source whose records are all missing produces no `SOURCE_SEQUENCE_GAP` (reason for AM-1).
3. A correction record keeps a motor UNRESOLVED even when a trusted verification agrees with it (A06), and a risk-increasing correction cannot be cleared by any admissible evidence in the space (A17). The engine is more conservative than the author's intent for A06 ("corroboration may clear"); that intent was wrong.
4. Late records from a mandatory-capture source open a capture outage between sessions, so a hypothetical correction can make things worse.

## 4. Limitations and what the numbers do not show

- Same author wrote scenarios, catalog and candidates. Perfect agreement with the oracle shows the implementation matches its specification, not that the specification matches factory reality.
- The operation catalog is hand-declared. Its correctness (what is really obtainable, who may issue it) is the dominant unknown and would need domain experts.
- Counterfactuals are conditional on hypothesised evidence content (for example "if the inspected bearing is not from an affected lot"). They say what would suffice, not that it will be found.
- Scenarios are small (catalog 0-10 ops). The rubric is structural (are fields present), not a human usability test; A0 scores low partly by construction.
- A0 is a plausible but simple baseline; a stronger one (per-slot rules, obtainability knowledge) would narrow the gap on non-minimality, though not on the false promises, which need replay.
- Minimality holds within K=3 and the declared space only. Larger evidence bundles were not searched.

## 5. Adversarial failure analysis

| Attack / failure | Result |
|---|---|
| Counterfactual built from invalid ops (mutations above) | 400/400 rejected |
| Evaluator-only search would propose clerical closure (A09) | caught by admissibility rules |
| Unsound pruning (A1p) | misses outcomes (1/18) |
| Output mistaken for evidence | outputs carry a fixed HYPOTHETICAL disclaimer; no `RELEASE_ELIGIBLE` string in any output (checked); but a UI could still misuse it, which is a product risk not a code property |
| Write to ledger / journal / checkpoint / network / database | blocked and unchanged, see section 6 |
| Hypothesis laundering: a favourable hypothesis presented as expected result | possible; the report format states outcome dependence, but nothing technical prevents misreading |
| Large catalog | exact search blows up (table above) |

## 6. Isolation proof (`results/safety/safety.json`, passed)

A disposable synthetic SQLite ledger (with journal publication) and a checkpoint file were created, plus 479 hashed files of the frozen tree. The full experiment ran as a child process under a write guard (audit hook: no write outside the results dir, no `sqlite3.connect`, no socket, no subprocess except the independent replay interpreter). After the run, 0 files changed; the guard recorded 0 violations. Negative controls show the guard is real: appending to the ledger file, `sqlite3.connect` on it, writing into frozen source, overwriting or deleting the checkpoint, a network connect, and passing a database path to the evaluator wrapper were all blocked. A static scan found no import of `application`, `sqlite3`, socket or HTTP modules in the experiment modules (only the fixture builder, which is outside the experiment, imports `application`). Limits: the guard covers this process, not the child interpreter (covered by the hash comparison), and it is an in-process audit hook, not an OS sandbox.

## 7. Prior-art comparison

| Contribution actually implemented | Closest published / commercial work | Class |
|---|---|---|
| Search for the smallest change that flips a decision | Wachter, Mittelstadt, Russell, "Counterfactual Explanations without Opening the Black Box", Harvard JOLT 31(2), 2018 (arXiv 1711.00399); Mothilal, Sharma, Tan, DiCE, FAT* 2020 (arXiv 1905.07697) | (1) known technique |
| "What input changes give the desired output" over a database, with minimality | Meliou and Suciu, "Tiresias: the database oracle for how-to queries", SIGMOD 2012, pp. 337-348 | (1) known technique |
| Minimal sets that explain or repair, level-wise by cardinality | Reiter, "A theory of diagnosis from first principles", Artificial Intelligence 1987 (minimal hitting sets, breadth-first by size; Greiner et al. 1989 corrected it) | (1) known technique |
| Declared actionability constraints on what may be changed | recourse literature (same papers: feasibility and actionability constraints) | (2) standard domain adaptation |
| Operations carrying issuer, chronology, identity, obtainability rules; replay through a conservative evaluator; no clearance minted; completeness reported against a declared space | no direct counterpart found in the sources checked | (3) possibly a distinctive combination; not established |
| Any claim that this is new, first, or superior to commercial tools | no evidence | (4) unsupported |

Commercial side: the sources I could verify describe recall scoping and genealogy, not evidence planning. Siemens Opcenter Execution fact sheets describe configurable where-used searches to find suspect material by component lot and actions such as hold, quarantine and forward/backward genealogy; the Opcenter Intelligence Electronics fact sheet describes automated traceability reports by component lot or reel to limit recall exposure. I did not find a "what evidence would clear this unit" feature in what I read, but my search was shallow (web summaries, no product documentation or trials) and absence in it is not proof of absence. Other vendors (quality/recall suites) were not examined. Novelty-risk assessment: medium to high. The technique is established; defensible differentiation would rest on the admissibility model and on the safety discipline (replay-only, conservative authority), not on the search.

## 8. Recommendation for deeper research: REVISE

Why not NO-GO: the measured, safety-relevant gain over a static table is concrete (5 of 6 unresolvable cases get a false promise from the table; the table is non-minimal in 3 of 12 resolvable ones; admissibility blocks a clerical clearance the evaluator would accept). Why not GO: the catalog is the real product and is unvalidated; A1's differentiation is mostly the admissibility layer; exact search does not scale; the dominant evidence is self-authored. Revise before deeper work: (a) have manufacturing/quality staff author an independent obtainability/issuer catalog and scenarios, (b) decide the stance on evaluator observation 1 with the owner, (c) find a sound pruning or limit scope to small per-motor spaces, (d) test whether users act correctly on conditional counterfactuals.

## 9. Safe v2 integration boundary (proposal only, not implemented)

Read-only, separate process or module; input is a copy of a motor's already-published evidence; evaluator invoked only through the pinned library on copies; no write path to the ledger, journal, checkpoint files or eligibility; output rendered only as an advisory panel with the hypothetical disclaimer and no release control; no new data in the audit journal; the frozen-source CI inventory must stay unchanged (new code lives outside frozen paths). Unresolved: how obtainability facts would be sourced, and how to prevent the advisory from being read as a clearance.

## 10. Reproduce

```
git clone <repo> && cd <repo> && git checkout research/counterfactual-recall-spike
python -B research/counterfactual/run_experiment.py --out research/counterfactual/results/rerun --seed 20261024 --guard
python -B research/counterfactual/safety_check.py --out research/counterfactual/results/rerun_safety
```
A clean-clone rerun (without the scaling table) produced a summary identical to `results/run1/summary.json` after removing timings and SHAs (see the comparison document for the check result).
