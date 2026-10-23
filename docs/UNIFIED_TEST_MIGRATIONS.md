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

### M20: `test_historical_resolution_entries_are_not_rewritten` (owner-approved, narrowly scoped test-contract migration; production D9 behavior NOT changed)
* **Original behavior asserted** (kept here and in git history at `1ba1c70`): after appending a historical `OBLIGATION_RESOLVED` row, `export_anchor()` succeeded and `verify_anchor(...)['status'] == 'VERIFIED_TRUSTED_PREFIX'`:
```python
        self.app.audit.append('OBLIGATION_RESOLVED',dict(obligationId=oid,principal='legacy-unauthenticated-claim'))
        self.app.db.commit(); anchor=export_anchor(self.app)
        self.assertEqual(len(self.app.audit.outstanding()),1)  # legacy claim cannot clear pending follow-up
        self.assertEqual(self.app.audit.replay(entry),entry['decision'])
        self.assertEqual(verify_anchor(self.app,anchor)['status'],'VERIFIED_TRUSTED_PREFIX')
```
* **Conflicting approved contract:** owner clarification that archives holding a historical resolution are historical-only; export/activation is blocked with `RESOLUTION_FORBIDDEN`.
* **Replacement (same name, no skip/xfail/suppression):** (1) earlier journal rows byte-identical after the append; (2) `export_anchor` raises `IntegrityFailure('RESOLUTION_FORBIDDEN')`; (3) the obligation stays outstanding and `resolve()` raises `PermissionError` for every principal; (4) an unanchored snapshot is `UNANCHORED` with every `currentReleaseEligible` false and the notification still reported, and a snapshot with a previously valid trusted checkpoint raises `RESOLUTION_FORBIDDEN` (no CURRENT); historical `replay(entry)` still equals the issued decision; (5) `test_R9_resolution_forbidden`, `test_forged_resolution_extension_rejected` and `test_public_resolution_callback_cannot_authorize_and_obligation_persists` are unchanged and pass; (6) all journal rows are identical after every attempt (nothing rewritten, deleted or rehabilitated).
* **Negative:** the old expectation (export succeeds) is now asserted to raise.

## Owner review of M9-M19 (conditional approval; recorded after re-verification)
| Required property | Evidence it survives |
|---|---|
| No CURRENT lease from PREFIX_ONLY | `m8-prefix-no-lease.test.tsx` (5), `checkpoint.spec` (2 incl. reload/navigation/visibility/back-forward), `console-consolidated` |
| No stale motor data in WITHHELD | M9 (no workbench/commands), M11 (withdrawn: no svg/headline/decision), M14 (`load-error`, no motor record), M18 negatives |
| Current findings and holds visible when verified | M12 re-asserts the ORIGINAL row expectations (Recall hold, Affected, Excluded with evidence, Unresolved, SHP id) after each activation; M13 asserts "Held under the recall policy" after activation; M16, M17 likewise |
| Checkpoint cycles use explicit test-only custodian steps | `OwnedStack.cycle()`: `checkpoint_ops propose` -> `accept` with named custodian and typed sha256 -> restart with `--trusted-anchor/--previous-anchor`; never an HTTP promotion |
| DE/NDE recall behavior | M16 (NDE-only through the real API) and `test_consolidated_safety.RecallScopePermanentRegressionTests` |
| Privacy pseudonymization enforced | M2/M2b assert `ACTOR-04` and `not OP-OBSERVATION-21` in unit and browser |
| Keyboard, mobile, accessibility still execute | `workspace` keyboard + desktop/mobile axe, `live` responsive axe, `remediation` 390px axe all in the 138; a search found no `skip`, `fixme`, `xfail`, `.only` or `expectedFailure` in any migrated file (one pre-existing `skipIf` in pinned engine tests, untouched) |
| Shared-server isolation does not hide regressions | Only tests that WRITE moved to owned stacks; every read-only test still runs on the shared seeded server; the serial RC config and the hosted serial run also pass 138/138 |
| Replacement negatives remain active | Each registry row names its negative; all run in the 138 |


## Playwright (original suite, `playwright.config.ts`)

Method: each of the 17 failures reported at checkpoint 1 was re-run alone, then classified from its first assertion and the page snapshot. Evidence that shared-server contamination was NOT assumed: `hardening:7`, `impact:149`, `workspace:15/60/187/149` and `passport:152/161/178` still failed when run alone and were migrated for contract reasons below; `live:52`, `passport:16`, `remediation:23` passed alone and in the full run once the writing tests stopped using the shared server, which is the only evidence for contamination as their cause. New helper: `tests/support/ownedStack.ts` (+ `tests/owned_bootstrap.py`): own ledger, custody dir, root checkpoint and port per test; `cycle()` performs the explicit TEST-ONLY custodian steps via `application.checkpoint_ops` (propose -> accept with typed digest) and restarts `app.py` with `--trusted-anchor <successor> --previous-anchor <predecessor>`; `unanchored` starts a real server without an anchor. Local test custody is not independent custody.

| ID | Test | Original behavior | Conflicting approved contract | Replacement | Negative |
|---|---|---|---|---|---|
| M8b | `checkpoint.spec` (+1 new) | After a capture the page showed "Recall hold remains in effect" | R5 amendment (`docs/R5_AMENDMENT.md`) | Facts only + global warning; API still carries `RECALL_HOLD`, decisions endpoint 409; second test: reload/navigation/visibility/back-forward never restore clearance | Body text must not match `Release eligible\|Recall hold remains in effect\|Excluded with evidence` |
| M9 | `hardening` "old successful proxy snapshot ..." | Withheld console kept the workbench with `Create unit` disabled | Owner O3: WITHHELD shows nothing motor-specific, no command surface | Workbench and every command button are absent while withheld; recovery restores | `toHaveCount(0)` on the workbench and button |
| M10 | `hardening` "external capture writer ..." | PREFIX_ONLY console showed a `Recall hold` chip with `PRIOR_EXCLUSION_WITHDRAWN` | R5 amendment | Heading "Checkpoint required", no chips; API snapshot carries `RECALL_HOLD` and `PRIOR_EXCLUSION_WITHDRAWN` | No release/exclusion text in the page |
| M11 | `impact` "live anchored ledger ..." | (a) stale lease simulated by backdating `verifiedAt`; (b) genealogy stayed under a "Not current" label | (a) gate: an earlier timestamp is a REGRESSION; (b) owner O3 display policy | (a) replay the same snapshot unchanged so the lease expires; backdating is kept as an explicit regression negative; (b) page is withdrawn naming the lease | No `impact-svg`, headline or decision remains |
| M12 | `live` "live manufacturing capture ..." | One shared server; each click expected an immediate decision | R5/R10 + amendment: every capture is PREFIX_ONLY until a successor checkpoint is activated | Owned stack; after each capture assert PREFIX_ONLY (warning, no chips, no Release/Hold/Affected text), run the test-only cycle, reload, then assert the ORIGINAL row expectations unchanged. 5 successor generations; "Announce recall" is idempotent (journal sequence unchanged, stays CURRENT). Shared `browser-latency.json` no longer rewritten (not comparable: now includes a cycle) | Body text checked between capture and activation |
| M13 | `passport` "external writer ..." | Passport changed straight to "Held under the recall policy" | R5 amendment + O3 | PREFIX: `recall-unavailable`, no `recall-current`, banner "Historical evidence only"; after cycle the ORIGINAL "Held under the recall policy" is asserted | Neither "No recall hold recorded" nor "Held under" appears in PREFIX |
| M14 | `passport` "backend outage ..." | Stale passport kept under "may be outdated" with recall unavailable | O3 (also M4 unit) | `load-error`, no recall status or motor record; recovery restores | No "No recall hold recorded", no stale record |
| M15 | `passport` "an unanchored backend ..." | UNANCHORED faked on an anchored server | Fake is contradictory -> withheld | Real server started without `--trusted-anchor` | Old fake kept: it must show `load-error` and no recall status |
| M16 | `remediation` "NDE-only affected motor ..." | Console read right after four writes | R5 amendment | Same scenario on an owned empty stack, API assertion unchanged, assertions made after activation | Before activation: no finding or hold chip |
| M17 | `workspace` "live: an evidence update ..." | Listing changed within one poll of each write | R5 amendment | Listing disappears until the cycle, then the original 4-then-3 expectations hold | `cards` count 0 and no cluster text while withheld |
| M18 | `workspace` "an unanchored envelope ..." | Faked UNANCHORED on a CURRENT checkpoint | Contradictory -> withheld | Real unanchored server (no clusters, no verified watermark); the fake is kept as a negative (`load-error`) | cards 0 |
| M2b | `workspace` preview tests (3: walkthrough, desktop/mobile axe) | Expected raw operator id `OP-OBSERVATION-21` | Owner O2 pseudonym | `ACTOR-04` | `not.toContainText("OP-OBSERVATION-21")` |

`checkpoint.spec.ts` keeps its original title; its original body is at `b15285c`.
