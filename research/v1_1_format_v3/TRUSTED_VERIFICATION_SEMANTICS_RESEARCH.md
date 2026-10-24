# Trusted investigation, correction and verification semantics (research only)

Owner decision C: document semantics. **No new clearance operation is added, nothing here authenticates a physical bearing, and no code in this branch implements any of it.** Facts below are read from the repository at `339649576c49158b38eb2496c98d6d88f8534ae3` (`recall-engine/pramaan_recall/{engine,ledger}.py`, `application/service.py`); the evaluator is pinned and untouched.

## 1. What "trusted" means today
A `SLOT_STATE_VERIFIED` event is a *trusted verification* only if the evaluator's replay says so. In `ledger.Replay.verify`:

1. `trusted = (event.sourceId in coverage.trustedVerifierSources) and (event.actorId not in the slot's earlier actors)`.
2. Under the attribution profile (v2/v3) it additionally fails with named reasons unless all hold (`_independence_failures`): source trusted; actor independent of the slot's previous actors; `method` in `approvedVerificationMethods`; actor in `authorizedVerifierActors`; source differs from every claim source for the slot; evidence references and `derivedFromEventIds` independent of operator claims. A passing event gets `assurance: CORROBORATED_SLOT`.
3. A trusted verification can fill an UNKNOWN slot, flag `VERIFIED_STATE_MISMATCH` against the recorded occupant, and corroborate late claims. A `provisional: true` trusted verification is used but warned (`PROVISIONAL_VERIFICATION_USED`).
4. Untrusted observations never clear anything; v3 makes an untrusted observation of an affected lot in a relevant slot a hold.

The **authority list is data supplied by the application**: `Manufacturing.create_unit` writes `trustedVerifierSources=[QA source]`, `authorizedVerifierActors=[QA-INDEPENDENT-03]`, approved methods, into the per-motor coverage record at registration. The ROLES table lets the `QA` role capture `SLOT_STATE_VERIFIED`, but **no application command authors a QA event**; the UI says "no command authors trusted verification".

## 2. What that does and does not establish
Established by the evaluator: *given* the event stream and coverage record, the stated independence rules hold. Not established:
- that the QA actor is a real, independent person (the producer-source string is set by the same process that holds the database; there is no authentication behind `actorId`);
- that the label that was read was on the bearing in that slot, or that the bearing is what the label says (physical identity);
- that the coverage record itself is honest (the application that is being checked writes it);
- that `occurredAt` is true (observation clock skew allowance 300 s; `trustedTimeSources` empty).
Therefore even a perfectly-formed trusted verification is **evidence under stated assumptions, not physical authentication**. Any UI or report wording must keep that.

## 3. Correction (supersession)
`supersedesEventId` removes the target from the replay (`active = events not in superseded`), but the superseded event stays in the ledger and in evidence output (`supersededEventIds`). The ledger profile validates the reference (target exists, is earlier, same slot for install/remove links). Consequences to settle before any correction feature:
- A correction can *erase an unfavourable record from the decision* (for example superseding the removal that showed the recalled lot). The evidence survives, but the decision no longer sees it. So corrections need their own authority class, stricter than verification.
- The identity guard in this branch reads events outside the evaluator: today it ignores superseded installs for the *current* basis and keeps everything under the historical basis. Any correction semantics must say how the guard treats a corrected record (this branch: not cleared by correction alone).
- Corrections are append-only; there is no "undo" and no expiry.

## 4. Proposed semantic model (for discussion; nothing implemented)
Three separate acts, never one button:

| Act | Purpose | Minimum requirement (proposed) | Effect on eligibility |
|---|---|---|---|
| **Investigation record** | Preserve what a person looked at and concluded, with evidence references | any authenticated role; free text and refs; unverified | none; may add uncertainty or open a review item |
| **Verification** | Independent observation of the bearing in a slot | role in `authorizedVerifierActors`, source in `trustedVerifierSources`, approved method, independence rules above, plus *authentication of the actor by something other than the application host* | may let the evaluator resolve the slot; still subject to the identity guard (registered lot) and checkpoint acceptance |
| **Correction** | Replace an erroneous earlier record | verification-level authority **plus** a second authorizer; the correction must cite the evidence that shows the error; the corrected event stays visible in history | never clears by itself; goes through review and a newly accepted checkpoint, with per-motor acknowledgement |

Rules that keep this safe:
1. **No act clears a motor alone.** Eligibility continues to require registered identity, checkpoint-bound registry, evaluator release, closed operations and an accepted checkpoint.
2. A verification of a lot the registry cannot establish does **not** establish identity (the guard still holds): the registry, not a label read, decides what a lot string means.
3. Two-person rule for correction: author and authorizer must be different authenticated actors and neither may be the original author.
4. Authority of actors must come from outside the host that holds the ledger (signed identity, hardware token, or a separate approval service). Without that, QA events are same-host assertions and must be labelled so.
5. Time: `recordedAt` (ledger) is authoritative for ordering; `occurredAt` claims are bounded by the skew allowance; back-dated verification that would change a past decision must raise a review, not silently flip history.
6. Every act that can lower risk (verification, correction) is recorded with who/what/evidence and appears in the decision explanation next to the guard's findings, never instead of them.

## 5. Threats and open questions
| Threat | Note |
|---|---|
| Colluding or compromised QA actor | independence rules cover accidental self-verification, not collusion; two-person rule and out-of-host authentication reduce but do not remove |
| Same-host forging of a QA event | possible today if capture were opened; that is why no command exists |
| Correction used to erase a recalled-lot record | needs second authorizer, mandatory evidence citation, review and acknowledgement |
| Replay of a valid old verification onto a new bearing | verification should bind slot, install event id and a time window; today binding is by slot and sequence only |
| Label read of a mislabelled or counterfeit bearing | outside software; verification is label evidence, not physical proof |
| Coverage record edited to add an authorized actor | coverage should be registry-like: bound into the checkpoint like the lot registry now is under FORMAT_V3 |

Questions for the owner: who may be an authorized verifier and how are they authenticated off-host; whether a second authorizer is mandatory for corrections or only for superseding a removal/install; whether the coverage record (trusted sources, authorized actors, approved methods) should be bound into the checkpoint in the same way as the lot registry; whether `PROVISIONAL_VERIFICATION_USED` verifications may count toward release at all.

## 6. Non-goals and stop line
No new event type, no change to the capture profile, no change to the pinned evaluator, no UI to enter verification or correction, no wording that implies physical authentication. Any implementation is a separate approval.
