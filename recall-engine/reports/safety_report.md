# Safety agreement report: engine vs independently recorded ground truth

Compares the engine's final finding (full watermark) with `groundTruth` recorded in the case files, **not** with `oracle.json`. Only case-06 carries a `groundTruth` block (`trueP1Finding` = AFFECTED, P1 only). Everywhere else no independent truth exists, so the table says so rather than assuming the oracle is right.

## Headline

- Final decisions evaluated: **20** (10 cases x 2 policies)
- Decisions with independently recorded ground truth: **1**
- **Safety false exclusions (default profile): 1** - case-06 RC-009/P1
- Safety false exclusions (strict lot-ambiguity profile): 0
- Total EXCLUDED_WITH_EVIDENCE decisions: 4; of which backed by recorded ground truth: 1 (the rest are unverified against reality)
- Unresolved classifications: **6** of 20 (P1 5, P2 1)
- Case 06 is **not** counted as a safety success. The behavioral pass for case 06 is the documented unsafe exclusion: lot-level identity cannot tell a wrong-slot scan from a correct one.

## Final decision per case and policy

| Case | Policy | Engine | Oracle (final) | Ground truth | Safety verdict |
|---|---|---|---|---|---|
| case-01 | RC-009/P1 | EXCLUDED | EXCLUDED | - (none recorded) | no ground truth (exclusion unverified) |
| case-01 | RC-009/P2 | AFFECTED | AFFECTED | - (none recorded) | no ground truth |
| case-02 | RC-009/P1 | UNRESOLVED | UNRESOLVED | - (none recorded) | no ground truth |
| case-02 | RC-009/P2 | AFFECTED | AFFECTED | - (none recorded) | no ground truth |
| case-03 | RC-009/P1 | UNRESOLVED | UNRESOLVED | - (none recorded) | no ground truth |
| case-03 | RC-009/P2 | AFFECTED | AFFECTED | - (none recorded) | no ground truth |
| case-04 | RC-009/P1 | EXCLUDED | EXCLUDED | - (none recorded) | no ground truth (exclusion unverified) |
| case-04 | RC-009/P2 | EXCLUDED | EXCLUDED | - (none recorded) | no ground truth (exclusion unverified) |
| case-04b | RC-009/P1 | UNRESOLVED | UNRESOLVED | - (none recorded) | no ground truth |
| case-04b | RC-009/P2 | AFFECTED | AFFECTED | - (none recorded) | no ground truth |
| case-04c | RC-009/P1 | UNRESOLVED | UNRESOLVED | - (none recorded) | no ground truth |
| case-04c | RC-009/P2 | UNRESOLVED | UNRESOLVED | - (none recorded) | no ground truth |
| case-05 | RC-009/P1 | UNRESOLVED | UNRESOLVED | - (none recorded) | no ground truth |
| case-05 | RC-009/P2 | AFFECTED | AFFECTED | - (none recorded) | no ground truth |
| case-05b | RC-009/P1 | AFFECTED | AFFECTED | - (none recorded) | no ground truth |
| case-05b | RC-009/P2 | AFFECTED | AFFECTED | - (none recorded) | no ground truth |
| case-06 | RC-009/P1 | EXCLUDED | EXCLUDED | AFFECTED | **FALSE EXCLUSION** |
| case-06 | RC-009/P2 | AFFECTED | AFFECTED | - (none recorded) | no ground truth |
| case-06b | RC-009/P1 | AFFECTED | AFFECTED | - (none recorded) | no ground truth |
| case-06b | RC-009/P2 | AFFECTED | AFFECTED | - (none recorded) | no ground truth |

## Differences by recall policy

| Policy | Engine EXCLUDED | AFFECTED | UNRESOLVED | Oracle EXCLUDED | AFFECTED | UNRESOLVED | Engine≠oracle (final) |
|---|---|---|---|---|---|---|---|
| RC-009/P1 | 3 | 2 | 5 | 3 | 2 | 5 | 0 |
| RC-009/P2 | 1 | 8 | 1 | 1 | 8 | 1 | 0 |

P1 and P2 differ because P2 adds historical exposure + damage-inspection requirements: any history that touched an affected lot is AFFECTED unless a valid post-recall PASS inspection *and* verified remediation exist. P2 exclusions therefore require strictly more evidence than P1's.

## Effects of slot verification (ablation: QA-02 events not ingested)

| Case | Policy | With verification | Without | Effect |
|---|---|---|---|---|
| case-04 | RC-009/P1 | EXCLUDED | UNRESOLVED | loses exclusion (more cautious) |
| case-04 | RC-009/P2 | EXCLUDED | UNRESOLVED | loses exclusion (more cautious) |
| case-05b | RC-009/P1 | AFFECTED | UNRESOLVED | loses information, still held |
| case-06b | RC-009/P1 | AFFECTED | EXCLUDED | hides risk: finding becomes EXCLUDED |

Verification both *releases* (04 P1/P2: bounds the outage gap) and *catches* (06b, 05b: observes an affected lot the records hid). Without it, 06b degrades to exactly case 06's unsafe exclusion.

## Effects of late corrections (ablation: QUALITY-PORTAL events not ingested)

| Case | Policy | With correction | Without | Effect |
|---|---|---|---|---|
| case-05 | RC-009/P1 | UNRESOLVED | EXCLUDED | hides risk: finding becomes EXCLUDED |

### Exclusions invalidated by later evidence (lifecycle)

- case-05 RC-009/P1: D-case-05-P1-v1 (EXCLUDED) superseded by D-case-05-P1-v2 (UNRESOLVED, RECALL_HOLD, reviewRequired=true); notification obligation: PRIOR_EXCLUSION_WITHDRAWN if D-case-05-P1-v1 was communicated
- case-05b RC-009/P1: D-case-05b-P1-v1 (EXCLUDED) superseded by D-case-05b-P1-v2 (UNRESOLVED, RECALL_HOLD, reviewRequired=true); notification obligation: PRIOR_EXCLUSION_WITHDRAWN if D-case-05b-P1-v1 was communicated

In both cases the earlier exclusion was a valid output *for the evidence ingested at the time* (P1 v1 EXCLUDED at watermark W1). The late claim withdrew it, applied RECALL_HOLD immediately, kept v1 in history, and recorded a notification obligation. Whether v1 was a true or false exclusion depends on whether the late claim is correct, which no ground truth in the archive settles.

## Known unsafe case

- **case-06 / RC-009/P1**: engine returns EXCLUDED (RELEASE_ELIGIBLE); ground truth AFFECTED. Technician replaced NDE but scanned DE; both slots hold lot BR-204 and the records are internally consistent. The engine emits flag `KNOWN_LIMITATION_LOT_LEVEL_SLOT_AMBIGUITY`. A scan-consistent record cannot be distinguished from reality at lot granularity without serials or independent verification (case 06b shows verification catches it; `tests/test_regressions.py` shows serial identity catches it).
- Optional `strict_lot_ambiguity` profile returns UNRESOLVED for case 06 and removes the false exclusion at the cost of one behavioral disagreement. Whether to make it the default is a product decision, not something to tune away silently.
