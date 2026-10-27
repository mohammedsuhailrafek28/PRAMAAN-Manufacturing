# Oracle version transition: v1 -> v2

- v1 frozen at 72be2c9 (feature/phase1-recall-engine); 25 evaluations, files hashed in `VERSION_TRANSITION.json` and in `../MANIFEST.sha256` (v1 files are never edited).
- v2: 35 evaluations = 23 carried over unchanged + 2 changed + 10 added.

## Changed evaluations

### case-06 RC-009/P1 (DECISION_CHANGE)
- `/evidenceFinding`: `"EXCLUDED_WITH_EVIDENCE"` -> `"UNRESOLVED"`
- `/flags`: `["KNOWN_LIMITATION_LOT_LEVEL_SLOT_AMBIGUITY"]` -> `"<absent>"`
- `/notes`: `"Expected SYSTEM output, which is wrong against ground truth. This case documents an assurance limit; it must not be 'fixed' by tuning the engine to pass it."` -> `"v2: removal of an affected lot whose part+lot match more than one accessible slot; only CORROBORATED_SLOT clears it. Ambiguity is not proof of a wrong-slot removal."`
- `/operationalAction`: `"RELEASE_ELIGIBLE"` -> `"RECALL_HOLD"`
- `/reasonCodes`: `["REPLACED_WITH_UNAFFECTED_LOT"]` -> `["AMBIGUOUS_SLOT_ATTRIBUTION"]`
- `/reviewRequired`: `false` -> `true`
- `/slots/DE/reconciliation`: `"CLEAN"` -> `"AMBIGUOUS_ATTRIBUTION"`

### case-06 RC-009/P2 (DETAIL_ONLY_CHANGE)
- `/slots/DE/reconciliation`: `"CLEAN"` -> `"AMBIGUOUS_ATTRIBUTION"`

## Added evaluations

| Case | Policy | Finding | Action | Reasons |
|---|---|---|---|---|
| case-06c | P1 | UNRESOLVED | RECALL_HOLD | AMBIGUOUS_SLOT_ATTRIBUTION |
| case-06c | P2 | AFFECTED | RECALL_HOLD | HISTORICAL_EXPOSURE_CONFIRMED, DAMAGE_INSPECTION_MISSING |
| case-06e | P1 | UNRESOLVED | RECALL_HOLD | AMBIGUOUS_SLOT_ATTRIBUTION |
| case-06e | P2 | AFFECTED | RECALL_HOLD | HISTORICAL_EXPOSURE_CONFIRMED, DAMAGE_INSPECTION_MISSING |
| case-06d | P1 | UNRESOLVED | RECALL_HOLD | REMOVAL_OBSERVATION_MISMATCH, REMOVAL_SERIAL_IN_OTHER_SLOT, CURRENT_STATE_UNVERIFIED |
| case-06d | P2 | AFFECTED | RECALL_HOLD | HISTORICAL_EXPOSURE_CONFIRMED, DAMAGE_INSPECTION_MISSING |
| case-06f | P1 | EXCLUDED_WITH_EVIDENCE | RELEASE_ELIGIBLE | REPLACED_WITH_UNAFFECTED_LOT |
| case-06f | P2 | AFFECTED | RECALL_HOLD | HISTORICAL_EXPOSURE_CONFIRMED, DAMAGE_INSPECTION_MISSING |
| case-07 | P1 | EXCLUDED_WITH_EVIDENCE | RELEASE_ELIGIBLE | REPLACED_WITH_UNAFFECTED_LOT |
| case-07 | P2 | AFFECTED | RECALL_HOLD | HISTORICAL_EXPOSURE_CONFIRMED, DAMAGE_INSPECTION_MISSING |

## Vocabulary and parameters added

```json
{
  "vocabulary": {
    "reasonCodes": [
      "AMBIGUOUS_SLOT_ATTRIBUTION",
      "REMOVAL_SLOT_LABEL_MISMATCH",
      "REMOVAL_SERIAL_IN_OTHER_SLOT"
    ],
    "slotReconciliation": [
      "AMBIGUOUS_ATTRIBUTION (below CAPTURE_GAP, above INSUFFICIENT_EVIDENCE)"
    ],
    "eventTypes": [
      "SLOT_LABEL_SCANNED",
      "SLOT_ACCESS_EVIDENCE"
    ],
    "assuranceLevels": [
      "CLAIMED_SLOT",
      "OBSERVED_SLOT_LABEL",
      "CORROBORATED_SLOT"
    ],
    "coveragePolicy": [
      "slotAttribution block (policies.json in this directory)"
    ],
    "engineConfig": [
      "Config(slot_attribution=True)"
    ]
  },
  "retired": [
    "flag KNOWN_LIMITATION_LOT_LEVEL_SLOT_AMBIGUITY (replaced by reason code AMBIGUOUS_SLOT_ATTRIBUTION when slot_attribution is on)"
  ],
  "parameters": {
    "labelAssociationWindowSeconds": 60,
    "status": "prototype parameter, not a proven safety standard"
  }
}
```

The only decision that changed is case-06 / P1: EXCLUDED/RELEASE_ELIGIBLE (documented known-wrong in v1) -> UNRESOLVED/RECALL_HOLD. A v2 engine disagreeing with that v1 expectation is the intended safety improvement, not a regression.
