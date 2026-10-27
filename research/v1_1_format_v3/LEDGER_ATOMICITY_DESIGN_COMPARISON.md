# Ledger atomicity: transaction-level multi-event capture versus fail-closed interruption reconciliation

Owner decision D: separate design workstream. **Design only: no ledger edit, no merge, no change to ledger transaction semantics in this branch.** Today's behaviour is described from the code at `339649576c49158b38eb2496c98d6d88f8534ae3`.

## 1. Problem as it exists
`assemble` writes 8 events (work order opened, material allocated and bearing manufactured ×2, installed ×2, work order closed); `replace` writes 6. Each event is a separate `ledger.capture(...)` call with its own commit. A crash or exception between two captures leaves a prefix: a work order that was opened and never closed, possibly with installed components. The application then (a) detects the open work order (`OPERATION_INTERRUPTED`, its own integrity guard) and holds the unit, (b) refuses every further capture for the unit, including retry, and (c) offers no way to close or cancel the operation. Measured earlier on the candidate: crash after each of the 14 write points leaves the unit held and a retry writes zero events.

What is safe today: no partial operation can create eligibility. What is not good: a transient fault permanently strands a unit; the only exit is a new database.

## 2. Option A: transaction-level multi-event capture
One database transaction covers the whole operation; either all events (and their capture and chain rows, and the per-source sequence advances) commit, or none.

Requirements and effects:
- The ledger's `capture` currently owns its transaction, per-source sequence numbers, hash-chain extension and archive bookkeeping. A multi-event API (`capture_many(motor, [raw...])`) must validate all events against the state that results from the earlier ones in the batch (work-order links, `endsInstallEventId`, `manufacturingEventId` references), then insert them under one `BEGIN IMMEDIATE`, then run the existing post-commit checks.
- Source heads: events in one operation come from several sources (MES, MATERIAL, ASSY, REWORK); each source's head must advance once per event inside the same transaction. Hash-chain rows are order sensitive, so batch order must be deterministic.
- Anchor interaction: checkpoints bind `ledger` row prefixes and `sourceHeads`. Atomic batches only add rows; prefix semantics are unchanged. A checkpoint can never fall inside a batch because the transaction is not visible before commit. Existing archives remain valid.
- Failure model after change: no partial operations from the application path. Pre-existing partial operations in old databases still need handling (Option B for legacy data).
- Costs: it changes ledger transaction semantics (explicitly out of scope today), needs engine-bridge and integration-ledger changes plus the H1/H2 verifier to be re-validated (replay cache keyed by capture), larger lock hold time (the snapshot path uses `BEGIN IMMEDIATE` too), and new fault-injection tests at the SQLite layer (crash during commit, WAL checkpointing).

Findings from `integration/pramaan_integration/ledger.py` (`Ledger.capture`):
- A capture is already atomic **per document**: it validates every event in the EPCIS document against the state built up by the earlier events of the same document (`known`, `seq`, `previous` are updated in the loop), then inserts all rows in one `with self.db` block. A rejection rolls back the whole document.
- But the document is bound to **one `producer_source`**: any event whose `sourceId` differs raises "Source/actor/motor/event capability mismatch". `assemble` interleaves MES, MATERIAL and ASSY sources (and `replace` MES, REWORK, MATERIAL), so one document cannot carry an operation today.
- The application sends one event per document (`encode_document([event], ...)`), each with its own `BEGIN IMMEDIATE` and commit.
- Therefore Option A is *not* just "send a bigger document". It needs either multi-source documents (a profile and capability-check change) or an outer transaction around several `capture` calls (savepoints; `capture` currently starts and commits its own transaction, and its failure path writes a `rejections` row in a separate `with self.db`, which an outer rollback must not erase or must replicate deliberately). Both are changes to ledger transaction semantics.

Pros: removes the failure class for new data; retry becomes a plain re-run. Cons: touches the most sensitive component; large blast radius; cannot fix history.

## 3. Option B: fail-closed interruption reconciliation
Keep per-event capture. Add a controlled way to *resolve* an interrupted unit without erasing anything.

Two sub-variants:
1. **Reconcile by completion** — a reviewed command that, for an open work order, appends the missing events (for example the missing `COMPONENT_INSTALLED` and `WORK_ORDER_CLOSED`) *only* if an independent physical check is recorded. Risky: it asserts physical work happened.
2. **Reconcile by abandonment** — a new event `WORK_ORDER_ABANDONED` (capture permission: MES only) referencing the open work order and the last event id. The unit stays held (the integrity guard keeps `OPERATION_INTERRUPTED` resolved-as-abandoned but the identity of any installed components is still judged by the identity guard); it never clears the unit. After abandonment a new controlled replacement can be performed.

Requirements: a new event type (profile and ledger change), an evaluator-isolation analysis (the pinned evaluator must ignore the type or treat it as informational), capture permissions, review-and-acknowledgement at checkpoint accept, UI explanation, and migration for databases with existing open work orders.

Pros: no change to transaction semantics; works for legacy data; keeps the audit trail explicit. Cons: needs a new event type (stop condition), relies on human judgment, leaves multi-event non-atomicity in place.

## 4. Comparison
| Criterion | A: atomic batch | B1: reconcile by completion | B2: abandon event |
|---|---|---|---|
| Prevents new partial operations | yes | no | no |
| Repairs existing partial operations | no | yes, by asserting work | yes, by recording abandonment |
| Ledger transaction change | yes | no | no |
| New event type / profile change | no | possibly | yes |
| Evaluator-isolation work | none | high | medium |
| Risk of recording false physical history | none | **high** | low |
| Effect on H1/H2 verifier | re-validation required | none | profile update |
| Blast radius | high | medium | medium |

## 5. Recommendation (for discussion, nothing selected)
Prefer **A for new data plus B2 for legacy and unavoidable faults**, in two separate approvals: first B2 design (small, no transaction change, makes stranded units recoverable under review), then A as its own ledger project with SQLite-level fault injection. B1 is not recommended: it lets the system assert physical work that nobody verified. Until either exists, the current fail-closed behaviour stands and is the documented limitation.

## 6. Tests any option must pass
Crash injection at every write point of assemble and replace (and mid-commit for A); retry idempotence; checkpoint taken before, during (impossible for A) and after; H2 replay of the resulting archive; guard behaviour (an abandoned operation never clears and never hides installed components from the identity guard); migration of a database with an existing open work order; no change to decisions of closed operations.
