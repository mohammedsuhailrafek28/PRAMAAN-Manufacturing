# Oracle version transition: v2 -> v3

- v2 (35 evaluations, sha256 `8f1e0778f80a...`) is unmodified; so is v1.
- v3: 54 evaluations = 35 carried over unchanged + 0 changed + 19 added.
- No existing decision changes: the new blocker only fires on untrusted affected-lot observations, which no v1/v2 fixture contains.

## Added evaluations

| Case | Policy | Finding | Reasons | Flags |
|---|---|---|---|---|
| case-08 | P1-v1 | EXCLUDED_WITH_EVIDENCE | REPLACED_WITH_UNAFFECTED_LOT |  |
| case-08 | P1-v2 | UNRESOLVED | UNTRUSTED_AFFECTED_OBSERVATION, PRIOR_EXCLUSION_WITHDRAWN |  |
| case-08 | P2 | AFFECTED | HISTORICAL_EXPOSURE_CONFIRMED, DAMAGE_INSPECTION_MISSING |  |
| case-08e | P1 | UNRESOLVED | UNTRUSTED_AFFECTED_OBSERVATION |  |
| case-08e | P2 | AFFECTED | HISTORICAL_EXPOSURE_CONFIRMED, DAMAGE_INSPECTION_MISSING |  |
| case-08f | P1 | EXCLUDED_WITH_EVIDENCE | REPLACED_WITH_UNAFFECTED_LOT | UNTRUSTED_AFFECTED_OBSERVATION_SUPERSEDED |
| case-08f | P2 | AFFECTED | HISTORICAL_EXPOSURE_CONFIRMED, DAMAGE_INSPECTION_MISSING | UNTRUSTED_AFFECTED_OBSERVATION_SUPERSEDED |
| case-08g | P1 | EXCLUDED_WITH_EVIDENCE | REPLACED_WITH_UNAFFECTED_LOT | UNTRUSTED_AFFECTED_OBSERVATION_SUPERSEDED |
| case-08g | P2 | AFFECTED | HISTORICAL_EXPOSURE_CONFIRMED, DAMAGE_INSPECTION_MISSING | UNTRUSTED_AFFECTED_OBSERVATION_SUPERSEDED |
| case-08h | P1 | EXCLUDED_WITH_EVIDENCE | REPLACED_WITH_UNAFFECTED_LOT | OUT_OF_SCOPE_UNTRUSTED_AFFECTED_OBSERVATION |
| case-08h | P2 | AFFECTED | HISTORICAL_EXPOSURE_CONFIRMED, DAMAGE_INSPECTION_MISSING | OUT_OF_SCOPE_UNTRUSTED_AFFECTED_OBSERVATION |
| case-08i | P1 | UNRESOLVED | AMBIGUOUS_SLOT_ATTRIBUTION |  |
| case-08i | P2 | AFFECTED | HISTORICAL_EXPOSURE_CONFIRMED, DAMAGE_INSPECTION_MISSING |  |
| case-08j | P1 | UNRESOLVED | UNTRUSTED_AFFECTED_OBSERVATION |  |
| case-08j | P2 | AFFECTED | HISTORICAL_EXPOSURE_CONFIRMED, DAMAGE_INSPECTION_MISSING |  |
| case-08k | P1 | UNRESOLVED | UNTRUSTED_AFFECTED_OBSERVATION |  |
| case-08k | P2 | AFFECTED | HISTORICAL_EXPOSURE_CONFIRMED, DAMAGE_INSPECTION_MISSING |  |
| case-08l | P1 | EXCLUDED_WITH_EVIDENCE | REPLACED_WITH_UNAFFECTED_LOT | UNATTRIBUTABLE_UNTRUSTED_AFFECTED_OBSERVATION |
| case-08l | P2 | AFFECTED | HISTORICAL_EXPOSURE_CONFIRMED, DAMAGE_INSPECTION_MISSING | UNATTRIBUTABLE_UNTRUSTED_AFFECTED_OBSERVATION |

## Vocabulary, parameters, defaults

```json
{
  "vocabulary": {
    "reasonCodes": [
      "UNTRUSTED_AFFECTED_OBSERVATION"
    ],
    "flags": [
      "UNTRUSTED_AFFECTED_OBSERVATION_SUPERSEDED",
      "OUT_OF_SCOPE_UNTRUSTED_AFFECTED_OBSERVATION",
      "UNATTRIBUTABLE_UNTRUSTED_AFFECTED_OBSERVATION"
    ],
    "semanticsProfiles": [
      "P1_LEGACY",
      "SLOT_ATTRIBUTION_V2",
      "UNTRUSTED_OBSERVATION_V3"
    ],
    "decisionFields": [
      "semanticsProfile",
      "coverageDigest",
      "untrustedObservations"
    ],
    "coveragePolicy": [
      "slotAttribution.observationClockSkewSeconds",
      "slotAttribution.trustedTimeSources"
    ],
    "engineConfig": [
      "Config(untrusted_observation=True) == Config.v3()"
    ]
  },
  "parameters": {
    "observationClockSkewSeconds": 300,
    "trustedTimeSources": [
      "DEVICE_SYNCED"
    ],
    "status": "prototype parameters, not a proven safety standard"
  },
  "defaultProfileForNewEvaluations": "UNTRUSTED_OBSERVATION_V3",
  "legacyReplay": "replay(case, policy, coverage, record) uses record.semanticsProfile (absent = P1_LEGACY)"
}
```
