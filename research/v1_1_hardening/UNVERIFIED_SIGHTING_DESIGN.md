# Unverified sightings (v1.1 candidate, no new event type)

## 1. Problem
In the A+B candidate `observe` refused any label the registry could not resolve. A worker who reads `BR-2O4` off a bearing in a recalled batch produced **no record at all**: the possibly most important sighting was lost.

## 2. Pathway implemented
`Manufacturing.observe(motor, label, slot="DE"|"NDE")` records every non-blank printable label (up to 80 characters, no control characters) as the **existing** event type `SLOT_STATE_VERIFIED`, source role `HANDHELD`, with:

```
payload: componentType BEARING, slot DE|NDE, observedPart BR-6205,
         observedLot <raw string exactly as reported, or the canonical lot if the registry resolves it>,
         identityGranularity LOT, method HANDHELD_LABEL_READ, provisional true
```
`eventId`, `sourceId`, `occurredAt` and the actor are the ledger's own. Blank, whitespace-only, `None`, non-string, over-long or control-character input is refused with no event.

Read side (`lot_identity.motor_findings`): an observation whose label is not a registered canonical lot becomes an identity finding with source `OBSERVATION` (reasons `UNREGISTERED`, `SENTINEL`, `MALFORMED`, `ALIAS_NOT_CANONICALISED`, ... plus look-alike hints). The motor is held (`RECALL_HOLD`, quarantined, not cleared) and the checkpoint review refuses an exclusion that rests on it. The sighting stops holding the motor when the same slot is physically re-installed later (`COMPONENT_INSTALLED` after the sighting; the sighting concerned the previous bearing). Under the historical-exposure basis every sighting is kept.

## 3. Invariants and how they are tested
| Invariant | Test (`test_v11_hardening.UnverifiedSightings`) |
|---|---|
| raw identity, source, time preserved | event payload equals the reported string; `sourceId` and `occurredAt` present |
| never verified installation | no new `COMPONENT_INSTALLED`; component list unchanged |
| never a registry entry | registry digest unchanged |
| never a lot | snapshot lot list unchanged |
| never exclusion evidence | sightings naming the recalled lot, `UNKNOWN`, `N/A` cannot make a motor eligible |
| evaluator isolation | `evidenceFinding`, `reasonCodes`, `evaluatorOperationalAction` are identical with and without the sighting; only the guard changes the action |
| may raise uncertainty / trigger investigation | motor goes `RELEASE_ELIGIBLE` (evaluator) to `RECALL_HOLD` (guard) with an investigation hint |
| registered unaffected label is not held | `BR-205` sighting leaves the motor eligible |
| later physical re-installation supersedes | `replace(NDE)` after an NDE sighting restores eligibility; the sighting stays in the ledger |
| invalid input | refused, zero events |

## 4. Capture permissions
The `HANDHELD` role is the existing untrusted claim role: it can already capture `SLOT_STATE_VERIFIED` with `provisional: true` and cannot author trusted verification. The pathway adds no capability: no new role, no new source, no change to the capture profile. The interrupted-operation rule applies (no capture after an interrupted operation for that unit).

## 5. Evaluator-isolation analysis
The pinned evaluator already treats `provisional: true` handheld `SLOT_STATE_VERIFIED` as an untrusted observation (it appears under `untrustedObservations`, it never clears or excludes). The label string is not interpreted by the evaluator beyond comparison with the recalled lot; a raw non-matching string behaves like any other non-matching observation. All holds come from the application-layer read guard, not from the evaluator. No `recall-engine/` change, no ledger profile change, no new event type. Measured: finding, reason codes and evaluator action are unchanged by a sighting (test above).

## 6. Limits
- The raw string is stored in an existing field named `observedLot`, so the ledger cannot tell a canonical sighting from an unresolved one without the registry (the application knows because it resolves at read time). A registry change can therefore change whether an old sighting holds the motor, which the registry-binding check turns into a reviewed event.
- A sighting holds the motor until a physical re-installation in that slot; there is no "investigation closed" record, because closing one would be a clearance path that the current evaluator semantics do not support.
- Free text is stored verbatim; the UI renders it as text only.

## 7. What an explicit `UNVERIFIED_SIGHTING` event type would add (needs approval, **not done**)
A distinct event type would let the ledger and any future evaluator distinguish an unresolved sighting by schema instead of by registry resolution, and would carry structured fields. Proposed schema: `eventType UNVERIFIED_SIGHTING`; payload `componentType`, `slot|null`, `reportedLabel` (string, 1-80), `reportedPart|null`, `reportedSerial|null`, `method` enum (`HANDHELD_LABEL_READ`, `PHOTO_REFERENCE`, `VERBAL_REPORT`), `reporterRole`, `provisional: true` (const). Capture permission: `HANDHELD` only; never `MES`/`ASSY`/`REWORK`. Evaluator isolation requirement: the pinned evaluator must either ignore the type or surface it only in `untrustedObservations`, which means a change to the capture profile and to the pinned evaluator's accepted type list. Both are stop conditions, so this is submitted as a design only.
