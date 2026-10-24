# NDE quarantine and controlled recovery (v1.1 candidate)

## 1. Problem
Owner finding: in the A+B candidate an unknown NDE lot could not be repaired, because `replace` handled only DE. The motor stayed held with no in-application path.

## 2. Quarantine is derived, never a state
Every guarded decision now carries `quarantine` (or `null`):
```
status      QUARANTINED_NOT_CLEARED
clearance   NEVER_IMPLIED
steps[]     {slot, reason, option, instruction}
blockedPaths  text: investigation records do not clear under current evaluator semantics
note        "Derived from recorded events; writes nothing."
```
It is computed from the same findings as the guard, from recorded events only. It has no write path and no stored state, so nothing can mark a motor "released from quarantine". Options per finding: `CONTROLLED_REPLACEMENT` (unresolved installation), `INVESTIGATE_SIGHTING`, `HISTORICAL_BASIS_REVIEW`, `CORRECT_REGISTRY_OR_RECALL`, `REVIEW_REGISTRY_AND_ACCEPT_CHECKPOINT`, `MANUAL_RECONCILIATION` (interrupted operation).

## 3. Controlled replacement of DE or NDE
`replace(motor, lot, slot="DE"|"NDE")` (HTTP body field `slot`, default `DE`, UI slot select) uses the **existing** event contract (`WORK_ORDER_OPENED` REWORK with `expectedChanges REPLACE slot`, `COMPONENT_REMOVED` with `endsInstallEventId`, `BEARING_MANUFACTURED`, `COMPONENT_INSTALLED`, `WORK_ORDER_CLOSED`). No ledger, event-type or profile change.
- The replacement lot must resolve in the registry (otherwise refused before any event; no invented identity, no invented supplier attestation: supplier comes from the registry entry as in assembly).
- The removed bearing's raw recorded identity (`UNKNOWN`, `BR-2O4`, ...) is preserved verbatim in `COMPONENT_REMOVED.observedLot`. Original events are append-only and untouched; historical decisions remain in the decision history.
- New eligibility needs all of: a registered replacement identity, a **closed** work order (an interrupted replacement holds the unit under the integrity guard), and a **newly proposed, reviewed and accepted checkpoint** (the review requires per-motor acknowledgement of the newly release-eligible motor).

## 4. Evidence
`test_v11_hardening.NdeRecovery`: an unknown NDE legacy motor is held and quarantined with `CONTROLLED_REPLACEMENT` for slot `NDE`; replacing it with `UNKNOWN` or an unregistered lot is refused with zero events; replacing NDE with `BR-312` appends exactly one closed REWORK work order and leaves the earlier events byte-identical; the motor is still **not eligible** under the old checkpoint; `propose` lists it for acknowledgement; `accept` without acknowledgement is refused; after acceptance it is eligible and the quarantine block is gone. Replacing the wrong slot (DE) leaves the NDE finding and the hold.

## 5. Evidence-backed investigation or correction: blocked
The prompt asked to support "evidence-backed investigation or controlled replacement". Controlled replacement is implemented. An investigation/correction that **supersedes** a wrong record (trusted verification, `supersedesEventId`) does not clear a motor under the pinned evaluator's current semantics (untrusted claims never clear; trusted verification is not authored by any role here), and enabling it needs a trusted-verification capture role and probably evaluator or profile changes. Blocked pending approval; the design would first define who may author a trusted verification, how its authority is established (not by the same host that holds the registry), and how it interacts with the exclusion rule.

## 6. Limits
- Replacement writes new physical-work records; it does not establish what was physically in the slot before. The quarantine block says so by showing the preserved raw identity only.
- Replacement is multi-event and not atomic (see `CRASH_RECOVERY_LIMITS.md`).
- Only bearings (`BR-6205`) and slots DE/NDE.
