# B2: work-order abandonment, design only

Owner decision 4: develop the semantics, authority requirements, negative tests and migration implications. **No ledger event contract, profile, evaluator or application command was changed.** The only code added is a read-only experiment on a disposable database (`b2_experiment.py`, output `b2_experiment.json` in the evidence directory). Nothing here is selected or approved.

## 1. What the existing contract already does (measured)
The integration profile already accepts `WORK_ORDER_CLOSED` with `disposition` `COMPLETED` or `CANCELLED` (`integration/pramaan_integration/profile.py:128`), and the synthetic MES source is already permitted to capture `WORK_ORDER_CLOSED` (`application/service.py` `ROLES["MES"]`). The application never writes `CANCELLED`. The experiment closes an interrupted BUILD (crash after 0, 1 and 2 of the two installs) with `CANCELLED` through the existing ledger path:

| Measurement | Result |
|---|---|
| Ledger accepts a `CANCELLED` close of the open work order | yes, in all three cases |
| Application integrity guard afterwards | **`OPERATIONALLY_CONSISTENT`** (`lot_identity.interrupted_operations` counts any close as closed) |
| Motor still held? | yes, held by the evaluator, not by the application guard: `WORK_ORDER_UNRECONCILED` (0 installs) or `NO_TRUSTED_BASELINE` + `CURRENT_STATE_UNVERIFIED` (1 or 2 installs: the evaluator trusts a baseline only from a `COMPLETED` BUILD) |
| Shipment referencing the cancelled close | refused by the profile ("Shipment references incomplete assembly") |
| That refusal's side effect | it leaves a rejection record and **every further capture for the unit is refused** ("Rejected evidence exists; manual reconciliation required"): a second way for a unit to be stranded, independent of interruption |
| Controlled replacement after a cancel | accepted when the slot has an occupant (1 or 2 installs), refused with no occupant |
| After cancelling and replacing **both** slots (2 installs) | still `RECALL_HOLD`: `NO_TRUSTED_BASELINE`, `CURRENT_STATE_UNVERIFIED` |

Conclusions that follow from these measurements:
1. **Abandonment is already expressible without a new event type.** A new `WORK_ORDER_ABANDONED` type is therefore not necessary for the audit trail; its only advantage would be semantic clarity and a distinct capability. Choosing the existing `CANCELLED` close (call it B2a) keeps the ledger contract and the pinned evaluator untouched; a new type (B2b) is a profile change and needs an evaluator-isolation analysis. Recommendation: evaluate B2a first.
2. **The application guard currently forgets an abandoned operation.** Today the only reason the motor stays held after a cancel is the evaluator's conservative baseline rule. A B2 implementation must not rely on that: the integrity guard needs a distinct, persistent state (`OPERATION_ABANDONED`) that holds the unit until it is retired.
3. **An abandoned BUILD unit never becomes release-eligible under the pinned evaluator**, even after both bearings are replaced through the controlled path (no `COMPLETED` BUILD, so no trusted baseline). So B2 is *containment and retirement*, not recovery to service. If recovery to service is wanted, it needs a different and separately reviewed mechanism (for example a fresh trusted baseline), which this task does not address. Whether the evaluator would accept a second BUILD work order for the same motor is an open question that was not tested.

## 2. Proposed semantics (B2a)
`abandon(motor, workOrderId, reasonCode, evidenceRef)`:
- Preconditions: the work order is `OPENED` and not closed; the unit has no rejection record; the caller holds the abandonment authority below.
- Effect: append one event, `WORK_ORDER_CLOSED` with `disposition: CANCELLED`, source `MES:<motor>`, `evidenceRefs` carrying the reason and authorizing reference, `supersedesEventId: null`. Nothing is deleted, edited or superseded; partial installs, material events and the original open event remain visible and still judged by the identity guard.
- Resulting state: `OPERATION_ABANDONED` (integrity guard) until the unit is **retired**. It is a hold, never a clearance. Further `assemble` stays refused; `replace` stays available (it is the only way to re-establish a registered identity for a slot); the unit can never be shipped; `ship` of an abandoned unit is refused at the application layer **before** the ledger is asked, so no rejection record is created.
- `observe` (sightings) stays allowed and stays unverified.
- Checkpoint review: an abandoned unit is an integrity row. It is acknowledged individually and, being held by both the evaluator and the application guard, is not an identity-unsafe exclusion, so it does not block renewal for other units.

## 3. Authority requirements
Abandonment destroys no evidence but retires a unit, so it should require more than any capture:
1. A named human with an MES supervisor role who is **not** the author of the open work order or of any event in it (separation from the original actor).
2. A second named reviewer for abandonment of a unit that has shipped, or that carries installed components, recorded as a second authorization reference.
3. A reason code from a closed list (`POWER_LOSS`, `CAPTURE_FAULT`, `OPERATOR_ERROR`, `SCRAP_DECISION`) plus free text, stored in the event's evidence reference, never interpreted by the evaluator.
4. Authentication and signatures are **not** available in this demonstrator (synthetic source identities only); see `TRUSTED_AUTHORITY_MODEL.md`. Until that exists, abandonment would be an operator assertion like every other acknowledgement.

## 4. Negative tests any implementation must pass
1. Abandon a work order that is already closed, unknown, or belongs to another motor: refused, zero events.
2. Abandon without authority, or by the author of the work order: refused.
3. Abandon, then try to ship: refused at the application layer; the ledger records no rejection; capture for the unit is not frozen.
4. Abandon, then check the guard: `OPERATION_ABANDONED` persists across restarts and checkpoint renewals; deleting the cancel event is impossible (ledger append-only; H1/H2).
5. Abandon a unit with installed affected-lot components: the identity guard and evaluator still hold it; nothing clears.
6. Abandon, replace both slots, renew checkpoint: still held (matches the measurement above).
7. Retry `assemble` after abandonment: refused.
8. Concurrent abandon and capture on the same unit: exactly one wins, no partial state.
9. Registry change or checkpoint-format change never turns an abandoned unit eligible.
10. A refused ship must not create a rejection row (this also fixes the stranding mechanism found above for non-abandoned units, if ship preconditions are checked first).

## 5. Migration implications
- Databases with existing open work orders keep `OPERATION_INTERRUPTED`; abandonment is the new exit. No historical data is rewritten; the new event is appended.
- A database containing a `CANCELLED` close written by some other producer would, today, show `OPERATIONALLY_CONSISTENT`; the new guard must derive `OPERATION_ABANDONED` from any `CANCELLED` close with unmet obligations, so legacy cancels are recognised without a migration of data.
- Checkpoints bind ledger prefixes, so existing checkpoints stay valid; the added event appears as a normal ledger extension and needs a normal renewal.
- Evaluator pin: B2a changes no evaluator input kind (the evaluator already reads `CANCELLED`). B2b would add an input kind and must be shown inert to the pinned evaluator, or the pin must change (a stop condition).
- UI: the console needs the abandonment explanation and a way to see who authorized it; it must not present abandonment as a repair.

## 6. Decisions requested
1. B2a (reuse `CANCELLED`) versus B2b (new event type); recommendation B2a.
2. Accept that abandonment is retirement, not recovery to service.
3. Approve fixing the "refused ship strands the unit" mechanism separately (check preconditions before the ledger call).
4. Authority model prerequisites (section 3) before any abandon command exists.
