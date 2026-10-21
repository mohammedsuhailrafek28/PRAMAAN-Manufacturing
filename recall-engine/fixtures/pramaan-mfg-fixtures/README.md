# Manufacturing PRAMAAN — recall classification fixtures

Synthetic test histories for one motor (M-042) under recall RC-009, plus the
expected outcome for each. Built to be the engine's first test target.

## Files

- `cases/*.json` — one event history per case: capture sessions + events in the
  common envelope (`sourceId`, `sourceSeq`, `occurredAt`, `timeSource`,
  `recordedAt`, `supersedesEventId`, typed `payload`).
- `policies.json` — two recall policies and the capture-coverage policy.
  - **RC-009/P1**: DE bearing, lots BR-204 and BR-207, *current installation*.
  - **RC-009/P2**: same scope, *historical operation*; requires damage
    inspection RC-009-DMG-01 after the 2026-10-01 announcement.
- `oracle.json` — expected evidence finding, operational action, reason codes,
  per-slot results and watermark for every case × policy (and, for cases 05/05b,
  every decision version).
- `validate.py` — checks the fixtures are internally consistent (references,
  gap-free per-source sequences, events inside capture sessions, watermarks,
  decision supersession, finding/action pairing). It does **not** test an engine.

## Cases

| Case | Scenario | P1 | P2 |
|---|---|---|---|
| 01 | DE replaced; slot-scoped NDE missed scan | EXCLUDED | AFFECTED |
| 02 | No baseline; removal + install only | UNRESOLVED | AFFECTED |
| 03 | Install into occupied DE | UNRESOLVED | AFFECTED (conflict) |
| 04 | Outage bounded by QA verification; inspection passed | EXCLUDED | EXCLUDED |
| 04b | Outage, no verification, no inspection | UNRESOLVED | AFFECTED |
| 04c | Outage, inspection passed, no verification | UNRESOLVED | UNRESOLVED |
| 05 | Late correction to BR-207 after exclusion | EXCLUDED → UNRESOLVED (hold) | AFFECTED |
| 05b | As 05, then QA verifies BR-207 | → AFFECTED | AFFECTED |
| 06 | Wrong-slot scan, lot-level identity | EXCLUDED *(known-wrong)* | AFFECTED |
| 06b | As 06, caught by QA verification | AFFECTED | AFFECTED |

Case 06 records the system output we expect, which is wrong against its
`groundTruth`. It documents an assurance limit of lot-level identity. Do not
tune the engine to "pass" it.

## Conventions and open items

- Every UNRESOLVED evaluation has `reviewRequired: true` and action
  `RECALL_HOLD`. Review is modelled as a flag alongside the hold, not as a third
  action, so a held motor can also be queued for review.
- `SLOT_STATE_VERIFIED` and `INSPECTION_RECORDED` payloads are marked
  `provisional` until we define an independent verifier and a valid inspection.
- All bearings are lot-identified (`identityGranularity: LOT`).
- Not modelled yet: hashes and signatures, stores issue feed, test-rig results.

Regenerate with `python build_fixtures.py`; validate with `python validate.py`.
