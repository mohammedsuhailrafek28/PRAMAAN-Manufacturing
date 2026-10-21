# v1 vs v2: slot attribution safety

Six separate measurements. Nothing here is a blended score. E1 = Phase 1 engine, E2 = slot-attribution engine; O1 = supplied oracle (frozen), O2 = oracle-v2. Ground truth is synthetic and covers P1 only.

## Gate

- **Zero false releases (E2): PASS** (0 against 7 cases with recorded truth)
- Releasing something at all: PASS (5 EXCLUDED decisions, 4 in P1)
- No safety regression vs E1: PASS
- No behavioral regression (E2 vs O2 and no unexplained E2-vs-O1 difference): PASS

## 1. Behavioral oracle agreement

| Engine vs oracle | Evaluations | Decision-level | Full (reasons, slots, lifecycle) |
|---|---|---|---|
| E1 vs O1 (Phase 1 contract) | 25 | 25/25 | 25/25 |
| E2 vs O1 (v2 engine, old expectations) | 25 | 24/25 | 23/25 |
| E2 vs O2 (v2 engine, v2 expectations) | 35 | 35/35 | 35/35 |
| E1 vs O2 (v1 engine, v2 expectations) | 35 | 32/35 | 27/35 |

E2 vs O1 disagreements, classified (not counted as implementation failures when declared):

- case-06 P1: O1 expected EXCLUDED, E2 returns UNRESOLVED - **INTENDED_SAFETY_DIVERGENCE (v1 expectation is a false release against ground truth)**
- case-06 P2: O1 expected AFFECTED, E2 returns AFFECTED - **DECLARED_DETAIL_ONLY_CHANGE (decision unchanged)**

E1 vs O2 disagreements (what the v2 oracle adds): case-06 P1, case-06 P2, case-06c P1, case-06c P2, case-06e P1, case-06e P2, case-06d P1, case-06d P2

## 2. False releases against synthetic ground truth

Cases with recorded truth AFFECTED: case-06, case-06b, case-06c, case-06d

| Engine | False releases | Count |
|---|---|---|
| E1 | case-06 P1, case-06c P1 | 2 |
| E2 | none | 0 |

Releases with no recorded ground truth are unverified, not known-good: E2 case-01 P1, case-04 P1, case-04 P2.

## 3. Unaffected motors (truth UNAFFECTED)

Motors: case-06e, case-06f, case-07

| Engine | Correctly released | Held UNRESOLVED | Held AFFECTED |
|---|---|---|---|
| E1 | case-06e, case-06f, case-07 (3) | - (0) | - (0) |
| E2 | case-06f, case-07 (2) | case-06e (1) | - (0) |

## 4. Case 06 family, P1, before and after

| Case | Truth | E1 (v1) | E2 (v2) | E2 reasons |
|---|---|---|---|---|
| case-06 | AFFECTED | EXCLUDED | UNRESOLVED | AMBIGUOUS_SLOT_ATTRIBUTION |
| case-06b | AFFECTED | AFFECTED | AFFECTED | VERIFIED_AFFECTED_LOT_PRESENT |
| case-06c | AFFECTED | EXCLUDED | UNRESOLVED | AMBIGUOUS_SLOT_ATTRIBUTION |
| case-06d | AFFECTED | UNRESOLVED | UNRESOLVED | REMOVAL_OBSERVATION_MISMATCH, CURRENT_STATE_UNVERIFIED, REMOVAL_SERIAL_IN_OTHER_SLOT |
| case-06e | UNAFFECTED | EXCLUDED | UNRESOLVED | AMBIGUOUS_SLOT_ATTRIBUTION |
| case-06f | UNAFFECTED | EXCLUDED | EXCLUDED | REPLACED_WITH_UNAFFECTED_LOT |

case-06: E1 releases a motor whose DE still holds an affected bearing (false release). E2 holds it with AMBIGUOUS_SLOT_ATTRIBUTION. case-06c shows a valid slot-label scan does not change that. case-06e has identical events to 06c but the technician really replaced DE: it stays held, which is the price of not guessing. case-06f adds an independent QA check and is released.

## 5. Regressions and differences between engines

- Safety regressions (E2 releases truth-AFFECTED that E1 did not): 0
- Behavioral regressions (E2 vs O2): 0
- Unexplained E2-vs-O1 differences: 0

Released by E1, held by E2:

- case-06 P1: EXCLUDED -> UNRESOLVED - INTENDED (v1 release was false)
- case-06c P1: EXCLUDED -> UNRESOLVED - INTENDED (v1 release was false)
- case-06e P1: EXCLUDED -> UNRESOLVED - USEFULNESS COST (truth UNAFFECTED, now held)

Held by E1, released by E2: none

Other differences (same finding):

- case-06d P1: same finding, reasons/flags differ
