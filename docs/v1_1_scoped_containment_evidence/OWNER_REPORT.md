# Owner report: scoped containment, restricted recovery, pinned-toolchain validation

Branch `research/v1-1-scoped-containment-recovery`. **Code SHA validated: `0b02fc7b09500e60c745798e4a428dad14ffbb3b`.** Commits after it are docs-only (evidence and this report). No merge, PR, tag, deployment, hosted CI or evaluator re-pin. Not production-ready; same-host custody is not independent verification; no independent benchmark has been scored.

## Validated at the code SHA (clean clone, local run of `ci/run_gates.py`, hash-pinned dependencies, pinned Chrome 155.0.8059.84)
`summary.json`: **status PASSED, gates A–K all green, no failures** (`gates/summary.json`, per-gate logs beside it).
Engine 127, integration 44, foundation interop B 21/21 checks, standards E, exporter 7, CI infra 7, snapshot check, typecheck, build, Vitest 378 (27 files), Playwright 143 (pinned Chrome, 10.4 min), application modules including the new `test_scoped_containment` (14) and `test_stale_recovery` (7), `frozen()` and provenance K.
The first attempt failed gates B and E only because the Python venv lacked the CI lock's packages (`pyld`); a separate venv was installed from `ci/requirements-windows.lock` with `--require-hashes` and the whole run repeated (first summary kept in `pre_freeze/`).

## Features completed
1. **FORMAT_V3** unchanged and re-validated (registry digest in the checkpoint body; V1/V2 history verifies but never grants eligibility; no V3→V2 downgrade); new test shows a V2 root migrating to V3 never releases a contained motor.
2. **Per-motor containment of an unverified sighting** at checkpoint acceptance: the sighted motor stays held, unrelated motors renew only when nine proof obligations hold; otherwise the whole candidate is refused as before (`SCOPED_CONTAINMENT_DESIGN.md`).
3. **Restricted stale-checkpoint recovery** (`/api/recovery`: observe, replace, propose only; no decision or eligibility in responses; nothing activated) plus a recovery workspace in the stale console; re-proposing is now idempotent (it used to crash).
4. Mutation coverage: obsolete mutant replaced by two FORMAT_V3 threats (substituted registry binding, altered legacy compatibility); 12 containment/recovery mutants. These ran at the pre-freeze commit, not re-run at the final SHA after the owner's priority change (`pre_freeze/mut_v11.txt`, `mut_sc.txt`): all killed except one that was an ineffective mutant (patched the wrong binding); after fixing the mutant it is killed (`mutation_fixed_mutant.json`).
5. Design-only deliverables written: B2 abandonment (with a measured finding that `CANCELLED` closes already exist and an abandoned BUILD never becomes eligible), trusted authority model, benchmark author/reviewer packages (not scored).

## Findings that matter
- **P1 – ordinary `ship` route is not gated by checkpoint state.** It records a shipment fact while stale (grants no eligibility; the stale console says do not ship). Documented with a test; gating needs your approval (existing tests ship while stale).
- **P1 – availability trade-off.** A sighting that looks like a lot in use elsewhere (for example `BR-2O4`, a typo of the recalled lot) or the same label on two motors still blocks renewal for all motors. Deliberate under "preserve the wider hold"; relaxing is a one-line owner decision.
- **P2 – a refused ship that references a cancelled close strands the unit** (a rejection row freezes further capture). Existing behaviour, measured, not fixed.
- Not done: independent benchmark scoring, authority model implementation, B2 implementation, hosted CI.

## Safe for a local hackathon demonstration?
**Yes, as a loopback, synthetic-data demonstration, with these caveats said aloud:** it is research code on a research branch; custody is same-host and operator-asserted; do not describe it as production-ready, independently certified or independently validated; avoid shipping from the API while the console shows "Checkpoint required"; avoid look-alike sightings of the recalled lot if you want to show containment (use a clearly different string such as `ZZ-9`). Demo path: run the app with `--trusted-anchor` and `--custody-dir`, record a sighting, show the recovery workspace, propose, accept with `checkpoint_ops`, restart, show the sighted motor held and others eligible.

## Open decisions
Gate ordinary `ship` on checkpoint state? Relax the look-alike obligation for the recalled lot? B2a vs B2b and authority-model prerequisites? Approve the final candidate for any hosted CI run.
