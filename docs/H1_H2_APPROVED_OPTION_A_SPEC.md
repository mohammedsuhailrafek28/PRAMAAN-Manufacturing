# H1/H2 closure: design and regression specification

## Provenance and approval

Authoritative recovered design: Claude's **October 21, 2026** review, originally supplied as the ChatGPT attachment `Pasted text(20261021-164006).txt`, titled “H1/H2 closure: design and regression specification”. It was not previously committed. The owner recovered and supplied the requirements below and explicitly approved **Option A: STRICT CHECKPOINT GATING**, independently protected checkpoint custody, and mandatory independent safety re-audit before merging.

Preserved before implementation on the isolated H1/H2 branch based on exact `f9282101159b6b6806974848d7c351999098d792`. This document records the owner's recovered specification; it does not claim access to the original attachment bytes or invent missing approval history. The separate CI correction is `04d974fd6307fca1f129be6b5683f4468b5fcad7`, hosted run39736296447 SUCCESS; it is not merged into this branch.

## Authoritative design requirements

States, in failure precedence:

`ANCHOR_INVALID > UNANCHORED > ANCHORED_PREFIX_ONLY > ANCHORED_CURRENT`.

Current `RELEASE_ELIGIBLE` requires ALL four:

1. State `ANCHORED_CURRENT`.
2. Existing C3 freshness checks pass.
3. The EVALUATION entry passes H2 replay verification in the current profile, in this process.
4. The motor has no outstanding obligation.

`ANCHORED_PREFIX_ONLY` must WITHHOLD current eligibility globally. Holds remain visible.

Checkpoint v2 must bind the event-ledger per-source chain heads, journal head, archive, policy, profile, verifier version and engine tree ID, linking previous checkpoint hashes. A v1 checkpoint cannot establish `ANCHORED_CURRENT`.

A local checkpoint export creates a CANDIDATE, not trust. Only an independently owner-custodied checkpoint can be activated. No HTTP trust promotion or implicit hot-swap. Use `--trusted-anchor` and `--previous-anchor` for chain-verified activation. Maintain an in-process high-water mark to detect regression.

H2 must recompute policy and configuration digests, ledger snapshot manifest at the recorded watermark, pinned v3 evaluator raw output, and the entire derived decision (ID, version, supersession, trigger, hold, reasons and obligations). Verify per-context version continuity and atomic EVALUATION/OBLIGATION_CREATED pairing. Reject orphan obligations, forged resolutions and unknown journal entry kinds.

Export checkpoints using a consistent SQLite transaction, complete verification and atomic, no-overwrite file publication. Return structured, sanitized integrity/availability errors: no SQL, payloads, raw exceptions or host paths.

## Exact original R1–R20 matrix, as recovered by the owner

| ID | Scenario | Required result |
| --- | --- | --- |
| R1 | Hold after checkpoint rolled back in-process | ANCHOR_INVALID; ROLLBACK_DETECTED; no eligibility |
| R2 | Same rollback, restart with latest checkpoint | ANCHOR_INVALID; PREFIX_MISMATCH |
| R3 | Rollback to between checkpoint and prior head | ANCHORED_PREFIX_ONLY; eligibility withheld |
| R4 | Rollback to exactly the checkpoint, restart using only that checkpoint | ANCHORED_CURRENT; documented UNDETECTABLE residual risk; do not claim detection |
| R5 | Legitimate capture after checkpoint | ANCHORED_PREFIX_ONLY; eligibility withheld, holds visible, checkpoint-required banner |
| R6 | Forged EVALUATION with recomputed hash chain and release decision | ANCHOR_INVALID; EXTENSION_INVALID |
| R7 | Forged derived decision fields with unchanged raw evaluator output | ANCHOR_INVALID; EXTENSION_INVALID |
| R8 | Orphan OBLIGATION_CREATED | ANCHOR_INVALID; EXTENSION_INVALID |
| R9 | Forged OBLIGATION_RESOLVED after checkpoint | ANCHOR_INVALID; RESOLUTION_FORBIDDEN |
| R10 | Ledger event appended but not yet evaluated | ANCHORED_PREFIX_ONLY; eligibility withheld |
| R11 | v1 checkpoint | ANCHORED_PREFIX_ONLY at best; never ANCHORED_CURRENT |
| R12 | Checkpoint export racing a concurrent writer | Complete success or clean failure; successful result verifies |
| R13 | Export fails midway through file writing | No partial checkpoint and no overwrite |
| R14 | Candidate checkpoint created locally on mutable host | UNANCHORED or unchanged state; no trust effect |
| R15 | Successor checkpoint does not link to previous checkpoint | ANCHOR_INVALID; PREFIX_MISMATCH |
| R16 | Legacy evaluation row without manifest | HISTORICAL_UNVERIFIABLE; never current clearance |
| R17 | Errors from every failure above | No leaked paths, payloads, SQL or exception text |
| R18 | 100 motors and 1,000 journal entries | Snapshot p95 below1.5s OR HTTP503 VERIFYING with eligibility withheld; do not raise existing4s UI timeout |
| R19 | Checkpoint before policy exists; policy subsequently added | ANCHORED_PREFIX_ONLY; report it, never silently accept it |
| R20 | Full baseline regression gates | Engine127, integration44, foundation21, plus existing application/UI tests passing |

## Approved file boundaries

- `application/anchors.py`: checkpoint v2, state machine, high-water mark, typed errors, atomic export/chaining.
- `application/audit.py`: pure decision-publication derivation, H2 verifier, verify-once-per-request and integrity-preserving in-memory cache.
- `application/service.py` and `application/server.py`: state, anchored sequence, eligibility gating, previous-anchor configuration.
- `recall-ui`: state/checkpoint-required warnings; no current eligibility outside ANCHORED_CURRENT.

Do not modify the pinned evaluator, foundation or integration ledger. Keep CI and H1/H2 separately reviewable; no competing lifecycle or architecture restart.

## Residual limitations (mandatory)

- Rollback to exactly the latest independently trusted checkpoint can be undetectable after restart.
- Host or owner-custody compromise is outside this protection.
- Forged evidence together with forged decisions is outside the stated attack model.
- Freshness is bounded, not cryptographic authentication.
- No locally generated anchor is automatically trusted.

## Acceptance interpretation requiring explicit reporting

The original live UI scenarios were authored before strict gating and expect current eligibility immediately after writes against an older checkpoint. R5/R10 now require that state to be prefix-only. This conflict must be surfaced in implementation/test reporting: preserving an old release assertion without a separately activated current checkpoint would violate this approved design. Historical raw v3 results and issued decisions must remain unchanged. No test will be silently skipped or an altered expectation represented as an unchanged baseline PASS.

Stop for independent safety review. No merge, deployment or PR is authorized.

## Owner clarifications recovered October 22, 2026

- R3 is after restart using the older checkpoint. In-process regression to an intermediate head is invalid under R1.
- Archives containing historical `OBLIGATION_RESOLVED` claims remain historical-only. Preserve the rows and block checkpoint export pending an explicitly approved migration. Do not reinterpret those claims as resolution authority or modify the original regression test to conceal this compatibility conflict.
