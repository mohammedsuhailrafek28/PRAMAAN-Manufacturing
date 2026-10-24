# Scoped containment of an unverified sighting at checkpoint acceptance

Research branch `research/v1-1-scoped-containment-recovery` (from the FORMAT_V3 report tip `8555d61`). Synthetic demonstrator, loopback only. This is a candidate design, not a release, and not an independent safety certification. Same-host custody is not independent verification.

## 1. Problem
Before this change, `checkpoint_ops.accept` refused the **whole** candidate whenever any motor had an identity-unsafe exclusion (an identity finding on a motor the evaluator would exclude or release). An unverified sighting on one releasable motor therefore blocked checkpoint renewal for every motor, and any HANDHELD-role operator could cause that. The owner asked for per-motor containment: the sighted motor stays held, unrelated motors may advance, and the wider hold is preserved whenever isolation cannot be established. The owner also said not to suppress a failing row merely to make the checkpoint pass.

## 2. Two separate questions
| Question | Answered by | Changed here? |
|---|---|---|
| Is this motor release-eligible now? | The live read model: checkpoint `ANCHORED_CURRENT`, registry binding `OK`, evaluator action, and the identity/integrity **guards** (any finding turns `RELEASE_ELIGIBLE` into `RECALL_HOLD`). Evaluated on every snapshot. | **No.** A sighted motor is held by the guard whether or not a checkpoint was renewed. |
| May a successor checkpoint be accepted? | `checkpoint_review.build_review` and `checkpoint_ops.accept` | **Yes.** The refusal is now per-motor, with proof obligations. |

Containment never grants anything. It only decides whether one motor's held state is a reason to refuse the candidate for everybody. Because the guard is recomputed from the ledger on every request, a contained motor cannot become eligible through any checkpoint in the chain (tested across later cycles, the original checkpoint, and an accepted successor).

## 3. Global conditions (unchanged, always checked first)
Any one of these keeps the existing whole-candidate refusal or hold; none can be contained:
1. Ledger/H1/H2 verification of the candidate and chain (`TrustedAnchor.verify`); a changed ledger after proposal.
2. Candidate registry binding is not `OK` (`REGISTRY_BINDING_*`), or the registry digest changed since proposal.
3. A registry change relative to the current checkpoint without the registry acknowledgement.
4. Recall-policy findings (the recall names a lot the registry cannot establish).
5. Any identity-unsafe exclusion that is not contained (install, removal, alias, withdrawn, expired, wrong part, conflicting scope, mixed findings).
6. An integrity finding (interrupted operation) on a motor that would otherwise be excluded or released.

## 4. Proof obligations for containing motor M
`checkpoint_review.containment` evaluates **all** obligations, records each result in the review row (`row.containment.obligations`), and contains M only if every one holds. A failed obligation is a refusal reason, shown to the operator.

| # | Obligation (code name) | Why it is needed | Adversarial case that fails it |
|---|---|---|---|
| P1 | `HAS_FINDINGS_TO_CONTAIN` | containment is about a real finding | empty finding list is never "contained" |
| P2 | `ONLY_SIGHTING_FINDINGS` | only a per-motor operator claim about one slot is isolable; install/removal/policy/binding/operation findings can reflect shared data or registry state | a bypassed capture (unknown lot installed) plus a sighting on the same motor |
| P3 | `ONLY_UNESTABLISHED_STRINGS` (UNREGISTERED, SENTINEL, MALFORMED) | withdrawn, expired, wrong-part, alias and conflicting-scope results are registry matters that may touch other motors | a sighting of the withdrawn lot `BR-420` |
| P4 | `NO_INTEGRITY_FINDINGS_ON_MOTOR` | an interrupted operation on the same motor is a separate unresolved state | open work order plus sighting |
| P5 | `NO_RECALL_POLICY_FINDINGS` | the recall itself rests on unestablished identity: no exclusion anywhere can be trusted | recall naming a lot the registry cannot establish |
| P6 | `REGISTRY_BINDING_OK` | the registry accepted with the candidate must be the registry in force | registry edited between proposal and acceptance |
| P7 | `STRING_NOT_SHARED_WITH_ANOTHER_MOTOR` | the same unverified label on two motors may be a recurring unregistered lot or a batch issue; comparison uses the look-alike skeleton (case, dashes, O/0, I/1, spacing) | `ZZ-9` on one motor and `zz 9` on another |
| P8 | `NO_LOOKALIKE_OF_A_LOT_IN_USE_ELSEWHERE` | if the string resembles a registered lot used on other motors, cross-motor identity cannot be ruled out | `BR-31O` (resembles `BR-310`), or `BR-2O4` (resembles the recalled `BR-204`) |
| P9 | `MOTOR_REMAINS_HELD` | containment is meaningless unless the guarded action is not `RELEASE_ELIGIBLE` | a mutated guard that would release the motor |

Additionally, accept requires an individual acknowledgement for every contained motor (an operator assertion, recorded as `containedMotors` in the acceptance record), and the review is recomputed at accept time from the live ledger, so a sighting added after proposal changes the answer.

## 5. What the evidence shows
- `application/test_scoped_containment.py` (13 tests): safe isolation (sighted motor held, A/B/new unit eligible, contained motor needs its own acknowledgement; two unshared sightings both contained; held across later cycles and old checkpoints; sighting on an already-affected motor needs no containment); mandatory refusal (shared string, look-alike of a lot in use, an unsafe install finding on another motor, mixed findings, withdrawn lot, registry mutation, each obligation individually necessary via the pure function); no silent path (retroactive registration of the sighted string is held under the old checkpoint).
- Browser: `recall-ui/tests/e2e/v11-hardening.spec.ts` — sighting on excluded motor `MTR-26003` is contained, the other motors keep their baseline eligibility, the stale console shows the recovery workspace, and a later controlled replacement restores eligibility only after another reviewed checkpoint; a shared label on two motors is refused for the whole candidate ("isolation" in the refusal).
- Mutation: `research/v1_1_scoped_containment/mutation_check.py` (see results in the evidence directory).

## 6. Not claimed, and honest limits
1. Containment is an argument about **data dependencies in the ledger**, not about the physical world. Two motors can share a physical bin without any recorded link; P7 and P8 only cover what is recorded.
2. Acknowledgement is an operator assertion on this host, not authentication and not proof of a bearing's identity.
3. **Availability trade-off remains.** An operator-chosen string that is a look-alike of a lot in use (the most natural typo, for example `BR-2O4` for the recalled `BR-204`) or a string typed on two motors still blocks renewal for everyone. This is deliberate under "preserve the wider hold when uncertain", and the browser suite demonstrates it. Relaxing P8 (for example, treating look-alikes of the *recalled* lot as per-motor) is a one-line obligation change, but it is a safety judgement for the owner: see decisions requested.
4. Integrity findings (interrupted operations) are not containable here; the owner scoped this change to sightings.
5. Containment adds no new trust. It is as strong as the ledger prefix and the checkpoint file on this host.
