# Interrupted operations: separate integrity guard, and recovery limits (v1.1)

Ledger transaction semantics are **unchanged**. Multi-event atomicity (a crash between the events of one assembly or replacement) is a separate ledger workstream and is not attempted here. This document records what the application does and does not do about it.

## 1. Separate operational-integrity guard
`OPERATION_INTERRUPTED` no longer lives inside the lot-identity guard.
- `lot_identity.integrity_findings(events)` reports each work order that was opened and never closed (`workOrderId`, `orderType`, `openedEventId`).
- Every guarded decision has its own block `integrityGuard` (`OPERATIONALLY_CONSISTENT` | `OPERATION_INTERRUPTED`, findings, `guardChangedAction`) next to `identityGuard`; the snapshot has top-level `operationalIntegrity.motors`; `identityGuard` is not blamed (`IDENTITY_ESTABLISHED_LOCAL_REGISTRY` stays when only the integrity guard fires).
- Either guard turns an evaluator `RELEASE_ELIGIBLE` into `RECALL_HOLD`; `evaluatorOperationalAction` is kept.
- UI: its own callout (`data-testid="integrity-guard"`) that says it is an operational-integrity hold, explains why retry is refused, and says no in-application reconciliation exists.
- Checkpoint review lists `integrityFindings` per motor and treats an exclusion or release that rests on an interrupted unit as identity-unsafe (refused regardless of acknowledgement), as before.
- `quarantine` offers one option for these findings: `MANUAL_RECONCILIATION`.

## 2. Conservative retry refusal (unchanged)
`assemble`, `replace` and `observe` refuse capture for a unit with an interrupted operation (`ValidationFailure`, zero events written). A retry could duplicate or contradict the partial record, and the ledger has no cancel or compensate event. Measured previously (crash after each of 8 assemble and 6 replace events): all held, retry writes zero events. Re-checked on this branch for the new guard in `test_v11_hardening.IntegrityGuard` (snapshot, API, quarantine, three refused captures).

## 3. Recovery limitations, explicitly
1. **There is no in-application way to close, cancel or compensate an interrupted operation.** The unit stays held until a reviewed manual procedure exists. For a demonstration the practical remedy is a new database.
2. Writing a closing event by hand into the ledger would be a manual ledger edit and is not offered; the ledger has no event that says "this work order was abandoned".
3. A partially written assembly can leave a component installed without a closed work order. The record is preserved and the unit is held; the evaluator is not asked to interpret it.
4. A crash between the final event and the snapshot or archive step is not an interruption of the ledger operation (the work order is closed); the next snapshot archives the result.
5. An interrupted unit whose evaluator output would be an exclusion or a release is an identity-unsafe row in the checkpoint review, and (existing rule) one such row makes `accept` refuse the whole candidate, so it can block renewal for every unit until it is resolved. An interrupted unit that is already held by the evaluator does not.
6. Atomicity would need either one ledger transaction over the whole multi-event operation, or a compensating/abandon event type. Both are ledger changes, outside this task.

## 4. Approval request
Open the separate ledger-atomicity workstream with a decision between (a) single-transaction multi-event capture and (b) an explicit `WORK_ORDER_ABANDONED` event with its own capture permission and evaluator-isolation analysis, plus an in-application reconcile command that is itself held to the same review and acknowledgement rule.
