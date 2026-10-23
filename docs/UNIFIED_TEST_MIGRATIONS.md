# Unified candidate: migrated test assertions

Rule applied: no test is deleted, skipped or has a count relaxed. Where an assertion encodes behavior that an approved contract has since superseded, it is migrated in place (same test name) and each migration records (1) the original behavior, (2) the conflicting approved contract, (3) the replacement expectation, and (4) a negative check proving the unsafe old behavior is now rejected. Fixture-only changes keep every assertion and are listed as such.

## Vitest (all 307 pass after migration; 297 existed before this branch's new tests)

| ID | Test(s) | Original behavior | Conflicting approved contract | Replacement | Negative proving the old behavior is rejected |
|---|---|---|---|---|---|
| M1 (fixture only) | `backend-source` x3 (valid mutation snapshot, stale replay, late older request); live adapters of passport/impact/investigation (`freshSnapshot`, `freshDataset`, `freshStage`) | "Fresh" envelopes carried only `freshness` | Option A / FE contract: current trust needs the full checkpoint + per-motor eligibility metadata | `withStrictCurrent()` adds an honest `ANCHORED_CURRENT` checkpoint and per-motor eligibility; assertions unchanged | `gate.test` FE-07 and `console-gate` "legacy envelope ... withheld" |
| M2 | `investigation-projection` x2, `investigation-app` "links a supporting record" | Preview data exposed the operator id `OP-OBSERVATION-21` | Owner decision O2 (Phase A): preview data is pseudonymised (`ACTOR-04`) | Assert `ACTOR-04` | `not.toContain("OP-OBSERVATION-21")` in all three |
| M3 | `passport-app` "live adapter ... classifies results", `investigation-app` "marks an unanchored snapshot ...", `impact-app` "live adapter marks an unverified snapshot ..." | An envelope with no checkpoint/eligibility was accepted as labelled historical records | Owner decision O3 + FE contract: missing metadata is WITHHELD (nothing shown) | Assert the load rejects with "checkpoint or eligibility metadata is missing" | The same tests no longer observe a non-gated *view* for such an envelope |
| M4 | `passport-app` "withdraws recall status and marks records stale ..." | After a backend failure the page kept stale motor records under a "may be outdated" banner | Owner decision O3: a WITHHELD page shows no motor-specific record | Assert `load-error`, no `passport-banner`, no MTR heading | `not.toMatch(/may be outdated\|No recall hold recorded\|RECALL_HOLD/)`; poll widened 30 -> 250 ms only so the good state is observable first |
| M5 | `checkpoint.test` "never accepts a backend snapshot omitting strict checkpoint metadata" | Error text "Strict checkpoint state and eligibility projection required" | The console now uses the shared gate's typed reason | Regex `/checkpoint or eligibility metadata is missing/` | The load still rejects (never accepted) |
| M6 (product text) | `impact-app`, `passport-app`, `investigation-app` regression tests | Expected word "regression" | Shared gate label for REGRESSION | Label reads "moved backwards (snapshot regression)"; assertions unchanged | `standalone-gate` still matches "moved backwards" |

New tests: `console-gate.test.tsx` (10, real H1/H2 envelopes, console on the shared gate); `application/test_unified.py` (8).

## Python

`application.test_hardening.AnchorTests.test_historical_resolution_entries_are_not_rewritten` still errors with `RESOLUTION_FORBIDDEN`. This is the owner-clarified behavior (archives holding a historical `OBLIGATION_RESOLVED` stay historical-only; export is blocked pending an approved migration). The test is kept unmodified and unmasked; it is counted as a known failure, not a pass.

## Playwright

See the "Playwright migrations" section appended by the end-to-end checkpoint.
