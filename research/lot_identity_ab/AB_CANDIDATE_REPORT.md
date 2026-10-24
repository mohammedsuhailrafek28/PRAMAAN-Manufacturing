# Combined A+B lot-identity safety candidate: implementation and evaluation report

Branch `research/lot-identity-ab-candidate`, created from exactly `c25466c56e5724158d534ff7b59f01ac48643101`. **Isolated candidate. Not promoted, not merged, not tagged, not deployed.** `manufacturing-demo-v1.0`, the pinned v3 evaluator (`recall-engine/`), the ledger (`integration/`), `main`, and all earlier research branches are untouched. No architecture is frozen. No hosted-CI result is claimed (nothing was run on hosted CI). Synthetic data, loopback only. Not a production-readiness claim and not independent safety certification; independent custody is not demonstrated; registry membership does not prove any bearing's physical identity.

## 1. What the candidate does

### Identity contract (`application/lot_identity.py`, `application/lot_registry.synthetic.json`)
- **Registry**: JSON document administered by "the manufacturer (synthetic)". Each entry: canonical lot (fixture convention `BR-###`, not an industrial standard), part, **supplier id and name (supplier scope)**, issuer, aliases, `effectiveFrom`/`effectiveTo`, status (`ACTIVE`/`WITHDRAWN`), raw-material lot, and **provenance, which must be `LOCALLY_AUTHORED_SYNTHETIC`** (a registry that does not declare it is refused). The registry digest is reported in every snapshot.
- **Resolution** (exact string or exact declared alias; **never normalised to accept**): `REGISTERED`, or one of `UNREGISTERED`, `SENTINEL`, `MALFORMED`, `ALIAS_CONFLICT`, `AMBIGUOUS_SUPPLIER_SCOPE` (the same string declared by two suppliers), `WITHDRAWN`, `NOT_YET_EFFECTIVE`, `EXPIRED`, `PART_MISMATCH`. Nothing but `REGISTERED` supports an exclusion.
- **Look-alike detection** (edit distance, confusables, Unicode) is a hint attached only to lots that do **not** resolve (`resembles`), for investigation. It never reclassifies a lot that resolves, so legitimate adjacent registered lots (for example `BR-205` beside recalled `BR-204`) are never held by it (tested, 0 false holds).

### Capture side (A) (`application/service.py`)
`assemble`, `replace`, `observe` and `announce` resolve every lot to its canonical registered identity **before the first event is written**. Aliases are converted to the declared canonical form explicitly. Supplier attribution comes from the registry entry (v1.0 hard-coded it by comparing with `"BR-204"`). `replace` refuses up front when an interrupted operation exists.

### Read side (B+) (`application/lot_identity.py::motor_findings`, applied in `service._snapshot`)
For **every** motor, whatever route wrote its events (legacy, bypassed, other writers): each currently installed bearing (all installs when exposure basis is historical), each observation, and the recall policy's lots are resolved against the registry at the event time; the manufacturing record must exist, carry the same lot, and name the registry's supplier; an alias stored literally is a finding (the evaluator compares literals); an opened-but-never-closed work order is a finding. Any finding fixes the guarded action to `RECALL_HOLD` and makes `currentReleaseEligible` false. **The evaluator's report is kept separately**: each decision carries `evidenceFinding` (unchanged), `evaluatorOperationalAction` (what the evaluator said), `operationalAction` (guarded, what downstream gates use) and an `identityGuard` block (status, findings, `guardChangedAction`). Published journal history is not rewritten.

### Shared semantics
One module feeds capture, snapshot, `/api/snapshot`, `/api/motors/<id>/decisions`, `/api/lots/<lot>/investigation`, the UI (`DecisionExplanation` callout, `ProvenanceBar` registry note; UI gating already mints clearance only from explicit `currentReleaseEligible === true` plus all-`RELEASE_ELIGIBLE` decisions) and the checkpoint review. Test `test_guard_shared_by_snapshot_decisions_investigation_and_review` asserts the same finding reasons through the snapshot and the review for the same database.

### Checkpoint decision review (`application/checkpoint_review.py`, `checkpoint_ops.py`)
`propose` returns a per-motor review: evaluator finding/action, guarded action, previous values from the journal at the accepted checkpoint, `newlyExcluded`, `newlyReleaseEligible`, installed-lot identity findings, evidence event ids, registry digest. `accept` now refuses (a) any identity-unsafe exclusion, **regardless of acknowledgement**, (b) missing individual `--acknowledge MOTOR` for each newly excluded or newly release-eligible motor, (c) a registry digest that changed since `propose` (`--registry-digest`). The acceptance record stores acknowledged motors, registry digest and provenance, and states acknowledgement is an operator assertion, not authentication and not proof of physical lot identity. It is not a trust anchor.

### Interrupted operations (`CRASH_SAFETY_STRATEGY.md`)
Option 2 (explicit fail-closed + up-front refusal) is implemented; option 1 (transaction-level atomicity) is documented as a separately reviewed workstream. **No multi-event atomicity is claimed.**

## 2. Evidence

All commands run from the repository root with the project's Python 3.12.10; logs in `research/lot_identity_ab/results/`.

| Check | Result | File |
|---|---|---|
| Candidate tests `application.test_lot_identity_ab` | 19 tests OK (18 at the final full run; the 19th, `test_repair_path_for_legacy_unknown_lot`, was added afterwards and run alone) | `final_python_suites.txt`, `ab_evidence.json` |
| Bad lots refused at capture, zero events written | 240 cases (20 bad inputs: missing, empty, whitespace, UNKNOWN, unknown, N/A, `-`, `0`, lowercase, trailing space, letter O, en dash, zero-width, no dash, transposed, full-width, different well-formed, malformed, withdrawn, overlong; x assemble DE/NDE x 4 scopes + replace + observe) | `ab_evidence.json` `badLotMatrix` |
| Unintended holds on legitimate registered lots | **0 of 80** cases (BR-310, 312, 901, adjacent BR-205, BR-311; assemble DE/NDE, replace, observe; 4 scopes) | `falseHoldsOnRegisteredUnaffected` |
| Bypassed / legacy-style bad lots (events written without validation) | **102 of 102 held**; in all 102 the evaluator alone said `RELEASE_ELIGIBLE` | `bypassMatrix` |
| Real v1.0 database read by the candidate | 6 motors written by unmodified frozen code (`git archive` of c25466c) with its own checkpoint: v1.0 says eligible for 5 of 6 (UNKNOWN, `BR-2O4`, `br-204`, `BR-999`, clean `BR-310/312`); candidate holds the 4 unsafe ones with reasons (`SENTINEL`, `UNREGISTERED`), leaves the clean one eligible, and `propose` + `accept` **refuses all four even with every motor acknowledged** | `reproduce_v1_0.json` |
| Registry changes after capture | withdrawal, expiry, late effectiveness each flip the same motor to held with reason `WITHDRAWN`/`EXPIRED`/`NOT_YET_EFFECTIVE`; conflicting aliases and two-supplier scope refused at capture; recall naming a lot the current registry lacks holds every motor; missing or provenance-less registry fails closed (`LedgerBlocked`) | `test_lot_identity_ab.ReadSide` |
| Interrupted operations | crash after each of 8 assemble and 6 replace events: all held, retry writes zero events (no `LedgerBlocked`), clean retry when nothing was written | `interruptedOperations` |
| API | bad lots 400; `currentReleaseEligible`/`eligibility`/`trusted`/`identityGuard` body fields ignored; sentinel and look-alike recall lots 400; snapshot carries `lotIdentity` | `Api` tests |
| Checkpoint review | ack required for newly excluded/release-eligible; partial ack refused; identity-unsafe refused; digest mismatch refused; renewing a checkpoint does not launder an ambiguous motor | `CheckpointReview` tests |
| Mutation check (tests are sensitive) | 5 mutants (guard disabled, permissive capture, review ignores identity, interrupted ops ignored, look-alike holds registered adjacent lots) each fail 1 to 6 tests; the unmutated suite fails 0 (run on the previous commit's 17-test module) | `mutation_check.json` |
| Original application suites, unmodified | 9 modules, 93 tests OK | `final_python_suites.txt` |
| Integration / engine / exporter | 44 / 127 / 7 OK | same |
| CI infra tests | 6 of 7 OK; **1 expected failure**: `test_expected_counts_are_exact_and_cover_every_application_module`, because the new test module is not in the CI inventory (see section 4) | same |
| UI unit tests (vitest) | 25 files, 371 tests OK (CI expects 369 for the unmodified UI; this branch adds 2) | `final_vitest.txt` |
| UI typecheck | `tsc --noEmit` exit 0 | `final_typecheck.txt` |
| Browser tests (Playwright, system Chrome, 2 workers) | **138 of 138 passed** (4.3 min). The first run was 136 passed, 2 failed (`live.spec.ts`, `workspace.spec.ts`): the test helper `ownedStack.cycle` accepted checkpoints without acknowledgements and was refused by the new rule. The helper now acknowledges what `propose` lists and passes the registry digest (test-support change only); both tests then passed | `playwright_run1.txt` (first), `final_playwright.txt` |
| Latency | snapshot on the seeded demo, median of 15, 3 runs each: frozen 141.6 ms, candidate 146.6 ms (+3.5%), single machine, indicative only | `timing.json` |
| Clean-checkout reproduction | see section 6 | `clean_checkout.txt` |

## 3. Failure cases and design costs found

1. **Rejected observations lose evidence.** `observe` refuses a label that does not resolve (for example a worker reads `BR-2O4` off a bearing). The refusal is correct for capture hygiene, but a suspicious sighting of a possibly recalled bearing is then not recorded. A safe design needs an "unresolved sighting" event type, which means a profile/ledger change (out of scope).
2. **One identity-unsafe exclusion blocks every checkpoint renewal** (as instructed). Resolution path today: replace the DE bearing with a registered lot (`replace` works on an `UNKNOWN` DE occupant). **`replace` is DE-only, so an unknown NDE lot cannot be repaired in the application**; the demo would need a new database. Owner decision: a quarantine/repair command, or accept this limit.
3. **Slot-agnostic hold.** An unestablished lot in a slot outside a scoped recall still holds the motor (the owner's rule is unconditional). It is conservative, not minimal.
4. **Historical exposure.** Under the historical basis all installs and removals are checked, so a motor that once held an unregistered bearing stays held even after replacement.
5. **Registry is not custody-protected.** It is a local file; editing it changes read-side results immediately (retroactive registration could clear an old unknown lot). Mitigations present: digest in every snapshot, registry binding at `accept`, provenance label. Not present: anchoring the registry in the checkpoint (would change the anchor format).
6. **Supplier-scoped recalls are not supported.** The recall policy names lots, not (supplier, lot). Ambiguity is detected only when the registry itself declares the same string for two suppliers.
7. **Look-alike hints exist only for unresolved lots.** A typo that happens to equal another registered lot (`BR-310` typed for `BR-301` if both are registered) is invisible; that is physical mislabelling, which no software here can detect.
8. **Naming.** `OPERATION_INTERRUPTED` is reported inside the identity guard block; a separate integrity guard would be cleaner for v1.1.
9. **UI scope.** Only the decision explanation and the provenance bar show the guard. Counters and other views consume the guarded action but do not explain it.
10. **Two `vitest` counts**: an earlier run on this branch reported 367 tests and the final run 371, same code; I did not diagnose it (a property-based test is a likely cause; not verified).
11. **Caught while building tests (my own harness, not product):** an early classification bug in my prototype matrix counted rejected captures as unsafe; fixed before any conclusion was drawn (see the P0 branch history).

## 4. Regression impact on this branch

- Application source changed: `service.py` (+42/-15), `server.py`, `checkpoint_ops.py`; new `lot_identity.py`, `checkpoint_review.py`, `lot_registry.synthetic.json`; UI: `types.ts`, `DecisionExplanation.tsx`, `ProvenanceBar.tsx`, one test-support helper, one new unit test. The v3 evaluator, ledger, anchors, audit are unchanged.
- Behaviour changes by design: lots are validated against the registry (tests using other lot strings need registry entries; the original suites needed none because they use BR-204/310/312/901 and one policy-tamper string); `accept` has new refusals; decisions carry new fields.
- The frozen-source manifest (`ci/frozen-source.json`), the CI expected-count inventory (`ci/run_gates.py` `EXPECTED`) and the application-module list are **not** updated here (CI files were not to be modified). They will fail or need a deliberate refresh in a v1.1 promotion: this is why the one infra test above fails.

## 5. Residual risks

Single author for all tests (see `INDEPENDENT_REVIEW_HANDOFF.md`; nothing independent has been run); the registry is synthetic and locally authored; the syntax is a fixture convention; string identity only; no concurrency testing across processes; the UI is only partly adapted; crash-safety is fail-closed handling, not atomicity; checkpoint review and acknowledgement are operator assertions on the same host; hosted CI and the CI release gates were not run.

## 6. Clean-checkout reproduction

A fresh `git clone` of the pushed branch (HEAD `f22403b`) into an empty temporary directory, rerun with the same Python 3.12.10 interpreter and installed packages (no new virtual environment): the 9 original application modules (93 tests) and `test_lot_identity_ab` (19 tests) all OK; `reproduce_v1_0.py` reproduced the same outcome (v1.0 eligible for MTR-91001/02/03/05/06, candidate eligible only for the clean MTR-91003, `propose` refuses MTR-91001/02/05/06). `clean_checkout.txt` has the log. UI, browser, integration and engine suites were not rerun in the clean clone (they need `npm ci`); they ran in the working tree (section 2).

## 7. Proposed minimal v1.1 promotion plan (needs owner approval at each step)

1. Owner decisions listed in the final message (repair path for NDE, rejected-observation handling, registry custody).
2. From this branch, create a promotion branch; keep only the files in section 4 plus tests; no evaluator or ledger change.
3. Refresh deliberately: `ci/frozen-source.json`, the source inventory report, `EXPECTED` counts (application +19, vitest +2), the application-module list; review that diff by hand.
4. Run the full local gates and the hosted CI **on the exact SHA**; claim success only if the hosted run passes.
5. Independent benchmark (sealed, independently authored) run once against the frozen candidate commit; report failures as failures.
6. New annotated tag `manufacturing-demo-v1.1` only after approval; `manufacturing-demo-v1.0` stays as the vulnerable baseline; update the runbook known-issue notice to point to v1.1 once validated.
