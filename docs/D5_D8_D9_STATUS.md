# D5, D8, D9: owner decisions applied and residual limits

Owner decisions after consolidation checkpoint 1. Pinned v3 evaluator, event-integrity format, checkpoint custody and recall policy semantics are unchanged.

## D5: H2 binds publication validity to recorded authority (IMPLEMENTED, `application/audit.py` `verify_publications`)
Added checks, each fail-closed with a fixed code:
| Code | Rule |
|---|---|
| `POLICY_NOT_ANNOUNCED` | The EVALUATION's policy digest must equal the stored hash of an immutable `recall_announcements` row, and every row's stored hash must match its own content. A policy recomputed locally by a journal writer is therefore not accepted. |
| `WATERMARK_REGRESSION` | A motor's later publication may not carry a per-source receipt position lower than that motor's earlier publication. Legitimate publications are made at the ledger's current (only-growing) position. |
| `WATERMARK_BEYOND_LEDGER` | No source position may exceed what the ledger currently holds for that motor. (The ledger refuses to build a manifest above what it holds, so such an entry cannot be forged through it; the bound is exercised by making the ledger report lower positions than a legitimate publication claims, with an unpatched negative control.) |
Legacy manifest-less rows stay historical (`HISTORICAL_UNVERIFIABLE`); legitimate multi-capture sequences, checkpoint export and the 5-generation chain still verify. Tests: `application/test_d5.py` (the two forgeries are accepted by the code before this change and rejected after).

**Limit that needs an owner choice (not implemented):** a forged entry for an *old* watermark that is the motor's *first* publication cannot be told apart from a legitimate early one, because journal entries do not record which ledger position existed when they were appended. Alternatives:
1. Add a `ledgerPosition` (e.g. count/hash of events visible at append time) to new EVALUATION entries and require `watermark == position` for new entries; legacy entries unchanged. Changes the publication format (trust specification), so needs approval.
2. Accept and document the residual: the entry cannot create eligibility (a journal change makes the checkpoint PREFIX_ONLY and `decide` re-derives at the current watermark); it can only add spurious history, and only for a host-level journal writer.

## D8: latest-head / equivocation (DEFERRED, tracked as a limitation)
A successor that skips an intermediate generation is rejected (`PREFIX_MISMATCH`), but nothing proves a presented chain is the *only* chain the custodian issued: an actor holding two valid successors of the same predecessor, or an old valid head, can present either. Detecting that needs an out-of-band latest-head witness (central authority, transparency log, or independent custodians), i.e. a new custody model. No such authority, automatic promotion or new cryptography was added. The approved in-process high-water mark (rollback after a head was seen by a running process) and checkpoint ancestry validation are preserved. Remains an explicit blocker for any claim of independent custody.

## D9: historical OBLIGATION_RESOLVED (HISTORICAL-ONLY PRESERVED)
Rows remain byte-for-byte unchanged and never authorize anything; the existing `RESOLUTION_FORBIDDEN` block on checkpoint export/activation is kept; `test_historical_resolution_entries_are_not_rewritten` is unmodified and still errors (counted as a failure, no migration proposed here). No read-only inspection path has been built yet; if wanted it must be a separate path that cannot mint eligibility.
