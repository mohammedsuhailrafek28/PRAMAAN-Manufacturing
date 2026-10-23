# Unified candidate: checkpoints and resume notes

Branch `integration/claude-unified-candidate`. Isolated; not merged to `main`, no PR, no deployment. Owner authorization: 2026-10-23 (integration of H1/H2 `f9dcf56` into this branch only). Approved Option A R1-R20 semantics (`docs/H1_H2_APPROVED_OPTION_A_SPEC.md`) are preserved; any change to them needs separate owner approval.

## Pinned sources (verified by content and ancestry)

| Component | Commit | Notes |
|---|---|---|
| A31 baseline | `f928210` | ancestor of every other source below except the CI line |
| Three features | `73f3bdb` | ancestor of `7482fc1` |
| Frontend Phase A | `cf97c1d` | ancestor of `7482fc1` |
| Branded frontend | `7482fc1` | **start of this branch** |
| H1/H2 candidate | `f9dcf56` | merged in Checkpoint A (merge-base with `7482fc1` is `f928210`) |
| Reliability investigation | `6d177e8` | sits on `73f3bdb`; not yet merged |
| Hosted-green CI | `04d974f` | branches from `f928210`; not yet merged (Checkpoint D) |
| Independent audit | `e63bf90` | defects D1-D10 are the remediation list |

## Checkpoint A: integration assembled (merge commit `90f08e5`)

Parents `7482fc1` and `f9dcf56`. Git reported **no textual conflicts**. 15 files changed by the merge: `application/{anchors,audit,server,service}.py`, new `application/{checkpoint_benchmark,test_checkpoints}.py`, H1/H2 spec/handoff/validation docs, and `recall-ui/src/{App.tsx,data/RecallDataSource.ts,data/freshness.ts}` plus two new H1/H2 tests. `recall-ui/src/domain/types.ts` already carried the checkpoint types from Phase A.

Semantic overlap (textual merge hides it): two gates now coexist. The legacy console gate (`freshness.ts`, `App.tsx`, `RecallDataSource.accept`) and the shared contract gate (`recall-ui/src/contract/*`, used by the three pages). Unifying them is Checkpoint B/C work.

Results on the merged tree (Windows, Python 3.12, Node 24):

| Check | Result |
|---|---|
| `tsc --noEmit` | clean |
| Python (`application.test_application`, `test_hardening`, `test_remediation`, `test_checkpoints`) | 59 run, 58 pass, 1 error: `test_hardening.AnchorTests.test_historical_resolution_entries_are_not_rewritten` (RESOLUTION_FORBIDDEN; owner-clarified historical-only behavior; kept unmodified) |
| Vitest | 297 run, 284 pass, 13 fail = the 10 failures already recorded at `7482fc1` (6 legacy-envelope adapter tests, 1 passport stale-records, 3 OP-OBSERVATION-21) + 3 `backend-source` legacy-fixture tests identified by the audit as class A. No assertion changed. |

## Open work (in order)

B. P0: D1/D2 (shared gate, state on every decision endpoint), D3 (legacy manifest-less row crash), D4 (depth-N checkpoint chain), per-motor clearance, forged-preview cases.
C. Four frontend views against one live backend; fixtures migrated with documented negative tests (original behavior, conflicting contract, replacement, negative test).
D. Full regression, reliability (`6d177e8`) and CI (`04d974f`) merges; hosted CI only claimed after a green run on the exact SHA.
E. End-to-end browser demo journey; setup and demo instructions; GO / CONDITIONAL GO / NO-GO.

Known conflict to report when reached: owner display policy (PREFIX_ONLY shows no current holds) versus spec R5 wording ("holds visible"). Resolve by showing holds only as labelled historical facts unless the owner says otherwise; ask before changing backend semantics.

## Progress at owner pause (2026-10-23)

Owner paused this line because Codex pushed `integration/manufacturing-release-candidate@75a65c2` (verdict REVISE). Nothing here was reset or merged to `main`; this branch is preserved for transfer of its unique fixes.

Commits on this branch after Checkpoint A (`90f08e5`/`f371334`):

| Commit | Content |
|---|---|
| `31cf2b0` | Backend D2 (decisions/investigation 409 `CHECKPOINT_REQUIRED` outside CURRENT; checkpoint+eligibility on payloads), D3 (manifest-less rows no longer seed derivation or crash), D4 (arbitrary-depth chain export via `predecessor` verification; skip-link and missing-previous still `PREFIX_MISMATCH`), D7 (internal read faults 500 `SNAPSHOT_UNAVAILABLE`). `application/test_unified.py`, 8 tests that fail on the old code. |
| `81c79fc` | Console on the shared gate (`BackendRecallDataSource` uses `GateTracker`; `SegregatedSnapshotError`; `CheckpointRequired` view; `ClearanceContext` per-motor clearance; stale decision list removed). 12 assertions migrated, 10 new `console-gate` tests. |
| `7968b3e` | Host/Fetch-Metadata request hygiene (`HOST_NOT_ALLOWED`, `CROSS_SITE_REQUEST_REFUSED`); `application/checkpoint_ops.py` (propose/accept successor checkpoint, never activates); `test_checkpoint_ops.py`; `docs/UNIFIED_TEST_MIGRATIONS.md`. |

Test status at `7968b3e`: Vitest 307/307. Python 67 + 2 new test files (`test_unified` 10, `test_checkpoint_ops` 4); the only failing Python test is the owner-clarified `test_historical_resolution_entries_are_not_rewritten` (kept unmodified). `tsc` clean.
Playwright (full original suite, run before the last commit): 109 pass, 17 fail. Not yet migrated; classes: (a) live specs that write to the shared seeded server and then expect current decisions (the audit's class A: `hardening` x2, `live` x2, `remediation` x2, `passport` live x4, `impact` live, `workspace` live x2); (b) `checkpoint.spec` expects holds shown under PREFIX_ONLY, which conflicts with the approved display policy; (c) `workspace` x3 still expect the live operator id `OP-OBSERVATION-21` from preview data (owner decision O2). Planned fix: an owned per-test stack (own DB, custody dir, root checkpoint, `checkpoint_ops` cycle + restart between captures) in `recall-ui/tests/support`.

Unique value to carry onto Codex's candidate: the D2/D3/D4/D7 fixes and tests, Host/Fetch-Metadata hygiene, `checkpoint_ops`, the console-on-shared-gate change with per-motor clearance and `console-gate` tests, the migration registry, and this analysis. Open conflict for the owner: spec R5 says "holds visible" under PREFIX_ONLY; the approved display policy says no holds. The UI follows the display policy; the API still carries decisions.

Not done: R18 latency work, CI merge (`04d974f`), reliability merge (`6d177e8`), end-to-end demo journey, Playwright migrations.
