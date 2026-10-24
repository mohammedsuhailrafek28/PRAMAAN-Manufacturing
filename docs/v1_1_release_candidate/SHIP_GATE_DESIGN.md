# Ordinary shipment gate: design, guarantees and limits

Branch `release/v1-1-demo-candidate`. Owner-approved narrow P1 fix. Research / hackathon prototype: loopback only, synthetic data, not production-ready, same-host custody is not independent verification.

## Rule
The ordinary shipment operation (`Manufacturing.ship`, reached by `POST /api/units/<motor>/ship`) records a `MOTOR_SHIPPED` fact only when, **at the moment of the write**, the motor has
1. a current trusted checkpoint (`ANCHORED_CURRENT`: the ledger is exactly the anchored prefix, registry binding verified), and
2. current operational release eligibility (`currentReleaseEligible`: evaluator action `RELEASE_ELIGIBLE` for every barrier, no recall hold, no identity guard finding, no unverified sighting, no registry discrepancy, no pending notification).

Anything else is refused: HTTP **409 `SHIPMENT_REFUSED`**, nothing written. There is no bypass in the operational API: no flag, header or body field changes the outcome (a test posts `currentReleaseEligible`, `force`, `trusted` and a forged `eligibility` object and is still refused).

## Mechanism (no time-of-check / time-of-use gap)
1. Existing preconditions run first (not already shipped, completed BUILD close exists), before any ledger call, so a precondition refusal creates nothing.
2. `snapshot(trusted_anchor=…, ship_ticket=motor)` runs under its normal single `BEGIN IMMEDIATE`: it verifies the anchor, evaluates eligibility, and **only if the motor is eligible** inserts one row into `app_ship_tickets(motor, fingerprint)` before committing. The fingerprint is a SQL expression over `motors`, `events`, `rejections`, `decision_runs`, `app_units`, `recall_announcements` (row count and newest rowid of each) and the newest event hash, read inside that same transaction, after any writes the snapshot itself made.
3. For the duration of the one `MOTOR_SHIPPED` write, a connection-local `TEMP` trigger on `main.events` evaluates the same fingerprint expression **inside the capture transaction** and `RAISE(IGNORE)`s the insert unless a ticket for that motor with an identical fingerprint exists. A second connection that appended anything after the ticket was issued changes the fingerprint, so the shipment insert is silently skipped. `IGNORE` (not `ABORT`) is deliberate: an abort makes `Ledger.capture` write a `rejections` row, which blocks the whole motor.
4. The caller checks that the shipment row exists; if not it raises the same refusal ("ledger or checkpoint state changed"). The trigger is dropped and the ticket deleted in a `finally`.

The decisive comparison happens in the same SQLite write lock as the insert, against the protected ledger state, not against a value the caller holds.

## Historical fixtures
`Manufacturing.record_historical_shipment_fixture(motor)` keeps the old behaviour for synthetic setup only (`seed_demo`, tests, demo generators, benchmark runner, `reproduce_v1_0.py`). `application/server.py` never references it; `test_ship_gate` scans the server source for it (and for any generic `.event(` route). It is a method on the same class, so it is not a security boundary against code that can already open the database: it exists so that the ordinary API cannot reach it.

## Behaviour changes the owner should know about
- Because eligibility needs a recall policy **and** a current checkpoint, ordinary shipment is refused before any recall is announced, and a motor assembled after the last checkpoint cannot ship until an operator checkpoint cycle covers it.
- A successful shipment is itself a ledger write, so the checkpoint is stale afterwards and the console withholds every current decision until the next cycle (this is existing behaviour for every capture).
- The workbench "Record synthetic shipment" button still exists; on refusal the app shows its existing generic error view (no UI redesign was in scope). During a demonstration show the refusal through the API or avoid the button; see the runbook.
- Two e2e specs and the former known-gap test changed from "shipment recorded" to "shipment refused". The assertions were not loosened: they now assert refusal, no ledger movement, and the remaining shipment-display checks run against a seeded fixture shipment.

## What this does not claim
- It does not make the checkpoint independent: custody is same-host and operator-asserted.
- Eligibility is only as good as the evaluator and the nine containment obligations already on this branch; conservative global refusal (look-alike evidence, uncertain dependencies) is unchanged and was not relaxed.
- It guards the ordinary shipment operation. Anyone with write access to the SQLite file can still insert events (as before); the anchor check detects this at the next verification, it does not prevent it.
- The external anchor file could in principle change between the ticket and the write; the ticket binds the ledger state, not the anchor file. The anchor is re-verified on every subsequent request.
