# Consolidated candidate: migrated test assertions

Rule applied: no test is deleted, skipped or has a count relaxed. Where an assertion encodes behavior that an approved contract has since superseded, it is migrated in place (same test name) and each migration records (1) the original behavior, (2) the conflicting approved contract, (3) the replacement expectation, and (4) a negative check proving the unsafe old behavior is now rejected. Fixture-only changes keep every assertion and are listed as such.

Branch `integration/manufacturing-consolidated-candidate` = Codex `75a65c2` + Claude backend commits. Codex's candidate left 21 original Vitest tests failing and migrated none; every migration below is new in this branch. Nothing here amends R1-R20.

## Vitest (360 run, 360 pass, 23 files)

| ID | Test(s) | Original behavior | Conflicting approved contract | Replacement | Negative proving the old behavior is rejected |
|---|---|---|---|---|---|
| M1 (fixture only) | `backend-source` x3, `freshness` x3; live adapters of passport/impact/investigation (`freshSnapshot`, `freshDataset`, `freshStage`) | "Fresh" envelopes carried only `freshness` | Option A / FE contract: current trust needs the full checkpoint + per-motor eligibility metadata | `withStrictCurrent()` adds an honest `ANCHORED_CURRENT` checkpoint and per-motor eligibility; assertions unchanged | `gate.test` FE-07 and `console-consolidated` "legacy envelope ... withheld" |
| M2 | `investigation-projection` x2, `investigation-app` "links a supporting record" | Preview data exposed the operator id `OP-OBSERVATION-21` | Owner decision O2 (Phase A): preview data is pseudonymised (`ACTOR-04`) | Assert `ACTOR-04` | `not.toContain("OP-OBSERVATION-21")` in all three |
| M3 | `passport-app` "live adapter ... classifies results", `investigation-app` "marks an unanchored snapshot ...", `impact-app` "live adapter marks an unverified snapshot ..." | An envelope with no checkpoint/eligibility was accepted as labelled historical records | Owner decision O3 + FE contract: missing metadata is WITHHELD | Assert the load rejects with "checkpoint or eligibility metadata is missing" | The same tests no longer observe a non-gated view for such an envelope |
| M4 | `passport-app` "withdraws recall status and marks records stale ..." | After a backend failure the page kept stale motor records under a "may be outdated" banner | Owner decision O3: a WITHHELD page shows no motor-specific record | Assert `load-error`, no `passport-banner`, no MTR heading | `not.toMatch(/may be outdated\|No recall hold recorded\|RECALL_HOLD/)` |
| M5 | `checkpoint.test` "never accepts a backend snapshot omitting strict checkpoint metadata" | Error text "Strict checkpoint state and eligibility projection required" | Console uses the shared gate's typed reason | Regex `/checkpoint or eligibility metadata is missing/` | The load still rejects |
| M6 (product text) | `impact-app`, `passport-app`, `investigation-app` regression tests | Expected word "regression" | Shared gate label for REGRESSION | Label reads "the ledger moved backwards (snapshot regression); owner review is required before reloading"; assertions unchanged | `standalone-gate` still matches "moved backwards" |
| M7 | `backend-source` unavailable/invalid/expired mocks; `freshness` watermark and version cases | Free-text errors ("Ledger unavailable", "Invalid recall snapshot", "watermark", "version"); mocks had no HTTP status | F6: the actual HTTP status is forwarded through the gate; typed causes | Mocks add `status:200`; unavailable -> typed WITHHELD message naming HTTP 409; invalid/contradictory -> `gate.cause` INTEGRITY; watermark/version -> `REGRESSION` | Status 201 is rejected (`console-consolidated`); the load still rejects in every case |
| M8 (conditionally approved; R5 amended, see `docs/R5_AMENDMENT.md`) | `checkpoint.test` "accepts verified prefix for hold visibility with every current eligibility withheld"; H2 and obligation cases | A verified prefix earned a lease so holds stayed visible (R5 wording) | Owner display policy: PREFIX_ONLY shows historical facts only, no current decisions/holds/clearance | Prefix never earns a lease ("Historical evidence only"); eligibility inside PREFIX -> `CONTRADICTORY`; H2/obligation cases use typed CONTRADICTORY | Eligibility in PREFIX is refused outright. R5 UI clause amended by owner (`docs/R5_AMENDMENT.md`); original preserved in git history. Direct tests: `m8-prefix-no-lease.test.tsx` (5) and `checkpoint.spec.ts` |

New tests: `console-consolidated.test.tsx` (47: console states with real H1/H2 envelopes, plus the same eight withheld envelopes and PREFIX_ONLY applied to console, passport, investigation and impact); `application/test_consolidated_safety.py` (12); `application/test_unified.py` (8); `application/test_checkpoint_ops.py` (4).

## Python

`application.test_hardening.AnchorTests.test_historical_resolution_entries_are_not_rewritten` still errors with `RESOLUTION_FORBIDDEN`. This is the owner-clarified behavior (archives holding a historical `OBLIGATION_RESOLVED` stay historical-only; export is blocked pending an approved migration). The test is kept unmodified and unmasked and counted as a known failure.

## Playwright

`recall-ui/tests/e2e/checkpoint.spec.ts` is migrated under the owner-approved R5 amendment (`docs/R5_AMENDMENT.md`); a second browser test covers M8. Remaining live specs are listed in `docs/CONSOLIDATION_REPORT.md`.
