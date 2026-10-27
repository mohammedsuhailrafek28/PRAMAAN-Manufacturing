# Consolidation report: `integration/manufacturing-consolidated-candidate`

Status: **CHECKPOINT 1, not a release candidate.** Not merged to `main`, no PR, no deployment, hosted CI not run on this SHA. Pinned v3 evaluator (`recall-engine/`), foundation and integration ledger are unchanged. Approved Option A R1-R20 semantics are unchanged.

Base: Codex `integration/manufacturing-release-candidate@75a65c2`. On top: Claude backend commits cherry-picked with `-x` from `integration/claude-unified-candidate` (`31cf2b0`, `7968b3e`), plus consolidation commit(s) listed in the branch log. Codex's `application/`, `recall-engine/`, `integration/` and `experiments/` were byte-identical to `f9dcf56`, so the backend transfer needed no conflict resolution.

## 1. Semantic conflict matrix

| # | Topic | Codex (75a65c2) | Claude (548e434) | Resolution here | Why |
|---|---|---|---|---|---|
| 1 | Console freshness/gate | `freshness.ts` is a thin wrapper over `evaluateEnvelope`; one implementation | Console moved onto `GateTracker`, own `ClearanceContext`, `CheckpointRequired` view | Codex's | Fewer parallel code paths; F1-F3 stricter validation (unique ids, exact key sets, structured obligations) |
| 2 | HTTP status | F6: actual status forwarded; 201 rejected | Literal 200 assumed | Codex's | Stricter; test `console-consolidated` proves 201 withheld |
| 3 | Per-motor clearance | `ConsoleClaims` branded claims (`contract/ConsoleClaims.tsx`) | `ClearanceContext` | Codex's | Same safety property (no bare release label without a current per-motor claim); covered by cross-surface tests |
| 4 | SEGREGATED view | `HistoricalFacts` | `CheckpointRequired` | Codex's component, **extended** with Claude's content: global no-shipment/no-release warning (`no-shipment-warning`), capture status, successor-checkpoint instructions stating they do not establish trust | Matches owner's proposed PREFIX_ONLY policy |
| 5 | REGRESSION wording | Not set | "moved backwards (snapshot regression)" | Claude's label in `gate.ts` | Keeps `standalone-gate` assertions |
| 6 | Passport QR / impact event match | F4 strips userinfo; F5 shipment id/time must match cited event | Not present | Codex's (kept as is) | Strictly additive |
| 7 | Backend D2/D3/D4/D7 | Proposed, not implemented | Implemented + tests | Claude's | Audit defects |
| 8 | Host / Fetch-Metadata checks | None | Implemented | Claude's | Documented as hygiene, **not authentication** (a local client can still read `/api/session`; tested) |
| 9 | Successor checkpoints | Manual | `checkpoint_ops` propose/accept, never activates, named custodian + typed sha256 | Claude's | Explicit, inert until operator restarts server with `--trusted-anchor` / `--previous-anchor` |
| 10 | Legacy-test migration | Left 21 Vitest failures unmigrated | M1-M8 migrated with negatives | Claude's, re-applied to Codex's code | See `docs/UNIFIED_TEST_MIGRATIONS.md` |
| 11 | R5 vs display policy | n/a | UI follows display policy | **Unresolved**, owner approval needed | Original R5 text and `checkpoint.spec.ts` preserved |

## 2. Transfer inventory

| Item | Source | State |
|---|---|---|
| Backend D2/D3/D4/D7 + `application/test_unified.py` (8) | `31cf2b0` | Transferred (cherry-pick) |
| Host/Fetch hygiene, `checkpoint_ops`, `test_checkpoint_ops.py` (4), migration registry | `7968b3e` | Transferred (cherry-pick), registry rewritten |
| Console-on-shared-gate (`81c79fc`) | Claude | **Not transferred**; superseded by Codex's console, behaviour re-covered by `console-consolidated.test.tsx` (47) |
| Legacy test migrations | Claude | Re-applied (M1-M8) |
| `application/test_consolidated_safety.py` (12) | New | Added |
| Codex F1-F6, harness isolation, audit/RC specs and configs | Codex | Kept |
| CI `04d974f`, reliability `6d177e8` | Other branches | **Not merged** |

## 3. Test results on this tree

| Suite | Result |
|---|---|
| `tsc --noEmit`, `vite build` | clean / OK |
| Python `application` (85) | 84 pass, 1 error: `test_hardening.AnchorTests.test_historical_resolution_entries_are_not_rewritten` (RESOLUTION_FORBIDDEN; owner-clarified, test unmodified, counted as failure) |
| recall-engine | 127/127 |
| integration | 44/44 |
| Vitest | 360/360 (23 files) |
| Playwright, original suite (`playwright.config.ts`) | 120 pass, **17 fail** |
| Playwright strict-gate / RC / audit / h1h2 configs, foundation and exporter suites | **Not yet run on this tree** |

### Playwright failures (17), classified from the first assertion in each, not yet individually fixed
- R5 conflict, **deliberately not migrated**: `checkpoint.spec.ts:7`.
- Owner decision O2 (preview pseudonym `ACTOR-04`, spec still expects `OP-OBSERVATION-21`): `workspace.spec.ts:15`. Needs investigation that this is the only cause.
- Live specs that write to the shared seeded server and then expect current decisions or a first-load view: hardening x2, impact live, live x2, passport x4 (`:16`, `:152`, `:161`, `:178`), remediation x2, workspace x4 (`:60` desktop/mobile, `:149`, `:187`). Hypothesis: the first capture flips the ledger to PREFIX_ONLY so later steps see the historical-only view, and the shared server starts unanchored. **This is a hypothesis; each still has to be confirmed individually** with an owned per-test stack (own DB, custody dir, root checkpoint, `checkpoint_ops` cycle and server restart between captures).

## 4. Remaining backend defects (unchanged from the audit)
D5, D6 (write-on-read), D8 (equivocation), D9 (historical OBLIGATION_RESOLVED), D10 / R18 (large-archive latency). None addressed here.

## 5. Demo acceptance status
**Not accepted.** Live end-to-end journey on the integrated stack has not been run on this SHA. Each capture moves the ledger to PREFIX_ONLY and needs a checkpoint cycle; this must be shown honestly. Until then the conditional demo baseline remains `integration/three-features-prep@73f3bdb` with recorded H1/H2 captures only. H1/H2 have not passed independent safety certification.

## 6. Needs owner approval
1. Amended R5 acceptance criteria (PREFIX_ONLY: backend holds still enforced; UI shows historical facts, no hold/release chips, global checkpoint-required warning, no current eligibility) before `checkpoint.spec.ts` is migrated.
2. Test migrations M1-M8, especially M8 (verified prefix earns no lease).
3. Semantics for D5, D8, D9 and the historical-resolution test.
4. Merging CI `04d974f` and reliability `6d177e8`, with CI inventory updated only for the exact reviewed SHA.
