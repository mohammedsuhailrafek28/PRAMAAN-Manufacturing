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
