# Crash-interrupted operations: strategy (open engineering workstream; no multi-event atomicity is claimed)

## Facts (v1.0 code, unchanged here)
- `Ledger.capture` opens its own `BEGIN IMMEDIATE` per call (`integration/pramaan_integration/ledger.py:140`), so each manufacturing event is a separate committed transaction. `assemble` is 8 events, `replace` is 6; nothing spans them.
- A rejected capture is recorded in `rejections` and blocks the whole motor for evaluation (`ledger.py:116-118`, "manual reconciliation required"). A retried `replace` after an interruption reuses the work-order id and is rejected as "Work order reopened under a new event ID" (`ledger.py:187`), which is how v1.0 turned a crash into a permanently blocked motor.
- Validation before the first event (this candidate) removes one cause of partial writes (invalid input). It says nothing about a process or machine fault between events. **Prevalidation is not atomicity and is not claimed to be.**

## Option 1: transaction-level atomicity (not implemented; needs separate review)
One outer transaction around all events of an operation, with `capture` joining it (savepoints). Questions to resolve before any change to ledger transaction semantics: how per-capture raw-byte archiving and hash chains behave on rollback; per-source sequence/watermark allocation inside a transaction; the rejected-evidence rule (a rejection currently commits a `rejections` row and blocks the motor); the audit journal and checkpoint interaction (journal appends occur in snapshots, not in captures); concurrency under the server's lock; and the evidence value of recording an interrupted attempt (rolling back erases the fact that it happened). The owner's instruction is not to change ledger transaction semantics without separate review; nothing here does.

## Option 2: explicit fail-closed handling (implemented in this candidate, application layer only)
1. **Detection.** A work order opened and never closed (`lot_identity.interrupted_operations`) is an interrupted operation, derived from the recorded events, whoever wrote them.
2. **Hold.** It is a finding in the identity guard (reason `OPERATION_INTERRUPTED`, source `OPERATION`): the motor cannot be current-eligible, and the evaluator's own report is kept separately. (The finding sits in the guard block for implementation convenience; a renamed `integrityGuard` would be cleaner in v1.1.)
3. **No second damaging write.** `replace` refuses up front when an interrupted operation exists ("requires manual reconciliation; no further capture is accepted for this unit") and writes nothing, so the retry cannot create the rejected-evidence block. `assemble` already refuses a unit with assembly evidence.
4. **Visible to the reviewer.** The checkpoint review lists the motor with the finding; an exclusion cannot rest on it.
5. **Tested** (`test_lot_identity_ab.Interrupted`): fault injection after each of the 8 assemble and 6 replace events: every interrupted unit is held, the retry writes zero events, nothing becomes eligible; a fault before any event leaves a clean retry. A mutant that ignores interrupted operations is caught by that test.

## Manual reconciliation (what exists today, honestly)
There is no application command that closes or cancels an interrupted work order. Today the only recovery is to treat the unit as quarantined and re-create the scenario in a new database. An in-app `reconcile` (append a `WORK_ORDER_CLOSED` with disposition `CANCELLED` from the MES source, record who and why, leave the partial installs visible and held until re-captured) is a candidate design, **not implemented and not reviewed**; it must not clear the hold by itself.

## Residual risks
- A motor with an interrupted operation stays held until a reconciliation design exists; the demo cannot repair it in place.
- A fault inside a single event capture is covered by that capture's own transaction (all or nothing for that event); a fault between events is not.
- The server serialises requests with a lock, but separate processes writing the same database can still interleave events; not tested here.
- Blocking behaviour already present for evidence rejected for other reasons is unchanged.

## Recommendation for v1.1 (owner to decide)
Ship option 2 as the fail-closed baseline, document the manual-reconciliation limit in the demo guidance, and open option 1 as a separately reviewed ledger workstream.
