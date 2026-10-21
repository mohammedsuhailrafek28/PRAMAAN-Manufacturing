# Legacy / v2 / v3 semantics comparison

Separate measurements, no blended score. E = engine profile, O = oracle version. Ground truth is synthetic and covers P1 only.

## Gates

- Zero false releases (v3): **PASS** (0 against 6 truth-AFFECTED cases; legacy 4, v2 1)
- Still releases motors: PASS (8 P1 releases, 9 overall)
- No safety regression v3 vs v2: PASS
- No behavioral regression / no unexplained disagreement: PASS
- Legacy and v2 oracles still reproduced by their own profiles: PASS
- Stored decisions replay exactly under their own profile: PASS
- An untrusted observation alone never yields AFFECTED: PASS

## 1. Behavioral agreement (decision-level | full)

| Engine / oracle | Evaluations | Decision | Full |
|---|---|---|---|
| E1/O1 | 25 | 25/25 | 25/25 |
| E2/O2 | 35 | 35/35 | 35/35 |
| E3/O3 | 54 | 54/54 | 54/54 |
| E3/O2 | 35 | 35/35 | 35/35 |
| E3/O1 | 25 | 24/25 | 23/25 |
| E2/O1 | 25 | 24/25 | 23/25 |
| E1/O2 | 35 | 32/35 | 27/35 |
| E1/O3 | 54 | 42/54 | 36/54 |
| E2/O3 | 54 | 46/54 | 46/54 |

Disagreements of the v3 engine with older oracles (classified, not defects when declared):

- E3/O1 case-06 P1: EXCLUDED -> UNRESOLVED - DECLARED_IN_V2_TRANSITION
- E3/O1 case-06 P2: AFFECTED -> AFFECTED - DECLARED_IN_V2_TRANSITION

## 2. False releases against ground truth

Truth AFFECTED: case-06, case-06b, case-06c, case-06d, case-08, case-08i

| Engine | False releases |
|---|---|
| E1 | case-06 P1, case-06c P1, case-08 P1, case-08i P1 (4) |
| E2 | case-08 P1 (1) |
| E3 | none (0) |

## 3. Unaffected motors

Truth UNAFFECTED: case-06e, case-06f, case-07, case-08e, case-08f, case-08g, case-08h, case-08j, case-08k, case-08l

| Engine | Correctly released | Held UNRESOLVED | Held AFFECTED |
|---|---|---|---|
| E1 | 10: case-06e, case-06f, case-07, case-08e, case-08f, case-08g, case-08h, case-08j, case-08k, case-08l | 0: - | 0: - |
| E2 | 9: case-06f, case-07, case-08e, case-08f, case-08g, case-08h, case-08j, case-08k, case-08l | 1: case-06e | 0: - |
| E3 | 6: case-06f, case-07, case-08f, case-08g, case-08h, case-08l | 4: case-06e, case-08e, case-08j, case-08k | 0: - |

## 4. Movements between profiles (full watermark)

**legacy -> v2** - released then held:
- case-06 P1: EXCLUDED -> UNRESOLVED - INTENDED (release was false)
- case-06c P1: EXCLUDED -> UNRESOLVED - INTENDED (release was false)
- case-06e P1: EXCLUDED -> UNRESOLVED - USEFULNESS COST (truth UNAFFECTED, now held)
- case-08i P1: EXCLUDED -> UNRESOLVED - INTENDED (release was false)

newly released: none
other finding changes: none

**v2 -> v3** - released then held:
- case-08 P1: EXCLUDED -> UNRESOLVED - INTENDED (release was false)
- case-08e P1: EXCLUDED -> UNRESOLVED - USEFULNESS COST (truth UNAFFECTED, now held)
- case-08j P1: EXCLUDED -> UNRESOLVED - USEFULNESS COST (truth UNAFFECTED, now held)
- case-08k P1: EXCLUDED -> UNRESOLVED - USEFULNESS COST (truth UNAFFECTED, now held)

newly released: none
other finding changes: none

## 5. Legacy replay

| Profile | Stored decisions | Reproduced exactly |
|---|---|---|
| P1_LEGACY | 25 | 25 |
| SLOT_ATTRIBUTION_V2 | 35 | 35 |
| UNTRUSTED_OBSERVATION_V3 | 54 | 54 |
