# Release-candidate report: ordinary shipment gate (final pre-freeze correction)

Branch `release/v1-1-demo-candidate`, cut from `research/v1-1-scoped-containment-recovery` @ `5169db5`. **Validated code SHA: `f7027bf385bb35fd4a7de64dacedda8f3dec4872`.** Commits after it are docs and, if present, a CI trigger line (`.github/`); nothing under `application/`, `recall-ui/`, `research/`, `integration/` or `recall-engine/` changes after it. No merge, PR, tag, deployment or evaluator re-pin. Research / hackathon prototype: loopback, synthetic data, **not production-ready, same-host custody is not independent verification, no independent benchmark has been scored.**

## 1. Safety fix (owner decision 1)
Ordinary `ship` now records a shipment only if the motor has a current trusted checkpoint **and** current operational release eligibility, checked in the same SQLite transaction cut as the write (single-use ticket bound to the ledger state + connection-local insert guard; a concurrent ledger change makes the shipment insert a no-op, which is reported as a refusal and writes no rejection row). Refusal is HTTP 409 `SHIPMENT_REFUSED`. Historical shipments for synthetic setup use the separately named `record_historical_shipment_fixture`, which `application/server.py` never references (tested). Design, guarantees and limits: `SHIP_GATE_DESIGN.md`. Diff of the two product files: `safety_fix_service_server.diff` (+52/-7 lines in `application/service.py`, `application/server.py`; the rest of the 30-file diff is tests, renamed fixture call sites, CI counts and the manifest).

## 2. Local validation at `f7027bf` (clean clone, hash-pinned dependencies, pinned Chrome 155.0.8059.84)
`gates/summary.json`: **status PASSED, gates A–K, no failures.** Engine 127, integration 44, foundation interop 21/21, vitest 378, Playwright 143 (9.3 min), every application module including the new `test_ship_gate` (13); `frozen()` and provenance K. Raw logs: `gates/`. An earlier identical-code run at `1de70bc` also passed but exposed a defect of mine (below); it is not the validated SHA.

Defect found by the post-gate battery and fixed before the validated SHA: my bulk rename of `.ship(` also hit `research/lot_identity_ab/reproduce_v1_0.py`, which runs the **unmodified v1.0 source** where only `ship()` exists, so that reproduction exited 1. Restored; it exits 0 at `f7027bf` (`mutation/python_suites.txt`). The gates did not catch it because no gate runs that script — an evidence-script regression, not a product regression.

## 3. Negative tests (all in `application/test_ship_gate.py`, plus the flipped stale test)
Unanchored · PREFIX_ONLY · registry discrepancy · unresolved lot identity · unverified sighting · recall hold · ledger change between eligibility check and write (second connection appends; shipment not recorded, no rejection row, no ticket left) · replay of a stale ticket · direct API with forged client claims (`currentReleaseEligible`, `force`, `trusted`, `eligibility`) vs the state the UI would show · server source never references the fixture path or a generic event route · normal current-eligible shipment succeeds (and leaves the checkpoint stale, as every capture does) · repeat shipment refused. `test_stale_recovery` now asserts the stale-checkpoint ship is refused (was a documented gap).

## 4. Mutation results at `f7027bf` (all run on the clean clone; `mutation/`)
| Suite | Mutants | Survivors |
|---|---|---|
| v1.1 hardening | 8 | 0 |
| FORMAT_V3 | 6 | 0 |
| scoped containment / recovery | 12 | 0 |
| **ship gate (new)**: gate disabled, anchor optional, eligibility ignored, ticket not bound to ledger state | 4 | 0 |
Baseline (unmutated) failures: 0 in each. The ship-gate mutants are in-process and check the tests, not the production file.

## 5. Hosted CI
Reported in the review message for the pushed tip SHA (it is not written into the repository so that the tip equals the SHA that ran). Workflow triggers are limited to PRs to `main` and a list of branches; this branch was added to the push list in a `.github/`-only commit. If the message says nothing about a hosted run, none was observed green.

## 6. Demo
`DEMO_RUNBOOK.md` (5 minutes + offline fallback) and `demo_rehearsal.py`. **Rehearsal status:** the scripted API-level rehearsal ran 10/10 steps at `f7027bf` (`rehearsal/`): stale refusal, operator cycle, recall-held refusal with forged claims, eligible shipment, sighting containment. Not done: a human or browser walkthrough of the exact runbook; the UI parts rest on the 143 Playwright tests.

## 7. Remaining issues (none hidden)
1. **P1 for the demo script, not the invariant:** the workbench "Record synthetic shipment" button, on refusal, is expected to drop into the app's generic error view (from reading `App.tsx`; not exercised). Runbook says to show shipment via `curl`/script. No UI redesign was done.
2. **Behaviour change to expect:** ordinary shipment is impossible before a recall policy exists and before an operator checkpoint cycle covers the motor; each shipment makes the checkpoint stale.
3. Conservative global refusal is unchanged: a look-alike of the recalled lot or a shared label still blocks renewal for all motors.
4. P2 (existing, unfixed): a refused ship that references a cancelled close strands the unit via a rejection row.
5. The gate covers the ordinary operation, not a writer with direct database access (detected at next verification, not prevented); the ticket binds the ledger state, not the anchor file.
6. Gates rewrite tracked screenshots and `docs/phase31-validation/expanded-safety.json` in the checkout they run in (existing behaviour); those changes are not committed.
7. Not done by design: B2 abandonment, new trusted authority, evaluator changes, new event types, benchmark scoring, independent custody.
