# Trusted authority model for verification and correction (research; nothing implemented)

Owner decision 5. This extends `research/v1_1_format_v3/TRUSTED_VERIFICATION_SEMANTICS_RESEARCH.md` (what "trusted" means in the pinned evaluator, the three acts, the threat table) with the authority questions the owner listed. **No investigated-and-cleared pathway, no verification or correction command, no new event type and no UI exists or is proposed for implementation until this model is reviewed.** All statements about the current system are read from the repository; statements about a future system are proposals.

## 0. Ground truth today
- Actors are strings set by the same process that holds the database (`ROLES` in `application/service.py`, per-motor `coverage` written by `create_unit`). There is **no authentication**: `actorId` and `sourceId` are labels.
- The evaluator's trust rules (`trustedVerifierSources`, `authorizedVerifierActors`, `approvedVerificationMethods`, independence from earlier claim actors and sources) are data in the coverage record, authored by the application under test.
- The only protected artifact is the checkpoint (ledger prefix + registry digest under FORMAT_V3), whose custody is a file on the same host. Acknowledgements are operator assertions.
- No QA event can be created by any application command. This must stay true until the model below is approved.

## 1. Roles
| Role | May | May not |
|---|---|---|
| **Claim author** (operator, handheld, assembly, rework, supplier intake) | capture claims and unverified sightings; each is an assertion | verify, correct or acknowledge anything about their own claim or the slot it concerns |
| **Verifier** (independent QA) | record a verification of the bearing in one slot: method from the approved list, evidence references, the install event it concerns, a validity window | verify a slot they previously claimed on; verify through the application host's credentials; clear a motor |
| **Corrector** | propose a correction that cites the evidence showing the error | be the original claim author, the verifier of that slot, or the second authorizer of their own correction |
| **Second authorizer** | independently approve a correction or an abandonment | be any of the above for the same item |
| **Checkpoint custodian** | accept a successor checkpoint after reviewing the diff and acknowledging each affected motor | be the author of a change under review; custody is only as independent as the place the checkpoint lives (section 5) |
| **Registry administrator** | change the lot registry (manufacturer-side) | accept the checkpoint that binds their own change without a second person |
| **Supplier** | supply lot declarations and certificates as claims | author manufacturer-side verification or registry entries |

## 2. Separation from the original claim author
Required, not optional:
1. Verifier ≠ the author of any claim about the same slot, ≠ the actor of the install event, ≠ the actor who read the label in a sighting. The evaluator already enforces part of this (earlier actors on the slot); the proposal adds *person* identity, not just actor string, and applies it to sightings (which the evaluator ignores for independence).
2. Corrector ≠ claim author ≠ verifier of the slot. Second authorizer ≠ corrector.
3. Registry administrator ≠ custodian who accepts the checkpoint binding that registry.
4. Two persons, two credentials, two devices where practical; a shared login is a violation recorded as such.

## 3. Identity authentication and authorization
The system must be able to answer "which real person, authorized by whom, for what, until when" from evidence that does not depend on the host holding the ledger.
- **Authentication**: each human holds a credential that the ledger host cannot mint: an asymmetric key on a hardware token or a signature from a separate identity provider. The act (event body hash plus the item it concerns plus a validity window) is signed; the signature, public key id and certificate chain are stored with the event as evidence.
- **Authorization**: a roster (person → roles → scope → validity), itself a signed, versioned document. The roster hash is bound into the checkpoint the same way FORMAT_V3 binds the registry (a possible future FORMAT_V4 body field), so a roster edit after acceptance holds every motor until reviewed.
- **Binding**: a verification signs {motor, slot, install event id, observed lot string, method, evidence hashes, validity window}. A signature for one slot/install/time cannot be replayed onto another (current binding is by slot and sequence only).
- **Failure mode**: unknown signer, expired authority, revoked key, signature that does not cover the stated item → the act is recorded as an *unverified claim* and has no effect on the evaluator's trust inputs.

## 4. Supplier versus manufacturer responsibility
| Statement | Responsible | Treated as |
|---|---|---|
| "This lot is BR-204, made on date X" | supplier | claim; the manufacturer's registry decides whether the string is established |
| "This lot string denotes this supplier/part/dates" | manufacturer registry administrator | locally authored synthetic reference data today |
| "The bearing in slot S of motor M carries this marking" | manufacturer verifier | verification evidence (label), not physical authentication |
| "This recall covers lot L at positions P" | manufacturer recall owner (policy), possibly on supplier notice | policy; announced once per database in this demo |
| "This supplier certificate is genuine" | nobody in this system | out of scope; would need the supplier's own signing and a verification service |
A supplier statement never serves as the manufacturer's verification, and a manufacturer verification never certifies the supplier's process.

## 5. Off-host custody and signature assumptions
Assumptions a real deployment would have to satisfy; none holds in this demonstrator.
1. The accepted checkpoint, roster and registry digests are held where the ledger host's administrator cannot silently replace them: a second system with separate administration (append-only log, notary, or a signed publication that the verifier checks against a pinned public key).
2. Signing keys are non-exportable. Key ceremony, backup and loss procedures exist.
3. Time: ordering uses ledger `recordedAt`; claimed `occurredAt` is bounded by a skew allowance; signatures carry a trusted timestamp from a source the host does not control. Back-dated acts that would change a past decision raise a review instead of changing history.
4. The verifier of the checkpoint (the code that decides `ANCHORED_CURRENT`) is itself pinned and its source hash is part of what the custodian signs (already true for the engine tree under FORMAT_V2/V3; extended to the roster).
Until these hold, any custody acceptance remains "operator-asserted on this host" and the documents must keep saying so.

## 6. Revocation, expiry and audit
- **Expiry**: every authority and every verification carries a validity window. An expired verification stops counting (the slot returns to the evaluator's default for an unverified slot) without rewriting the ledger.
- **Revocation**: a signed revocation (key, person or roster entry) takes effect from its recorded time; verifications made under the revoked authority after its effective time are ignored; earlier ones are flagged `AUTHORITY_REVOKED_LATER` and reopened for review (never silently kept, never silently dropped). Revocation is a roster change and therefore holds the fleet until the new roster is accepted in a checkpoint.
- **Audit**: every act (claim, verification, correction, abandonment, acknowledgement, checkpoint acceptance) records who (verified identity), what (hash of the object), against which item, under which roster version, when (recorded time), and with what evidence. The audit trail is part of the hash-chained ledger; roster and revocation documents are retained append-only. A reviewer must be able to reproduce, from the archive alone, why a motor was considered verified at any past time.
- **Review of clearance-adjacent acts**: any verification or correction that lowers a hold is listed in the checkpoint review with the verifier, authorizer and evidence, and needs per-motor acknowledgement by a custodian who authored none of it.

## 7. What this model deliberately does not do
- It does not make a label read equal physical identity; a verifier records what they saw, and the registry still decides what a lot string means.
- It does not make an "investigated and cleared" pathway: a verification may let the evaluator resolve a slot, but eligibility still needs registered identity, bound registry and roster, closed operations, evaluator release, and an accepted checkpoint.
- It does not remove collusion risk between two authenticated people; it raises the cost and makes the act attributable.

## 8. Review questions for the owner
1. Who may hold the verifier and corrector roles, and who issues and revokes their credentials?
2. Is a second authorizer mandatory for every correction, or only for corrections that supersede an install, removal or sighting involving an affected lot?
3. Should the roster and the coverage record be bound into the checkpoint (FORMAT_V4), with the same hold-on-drift behaviour as the registry?
4. May a provisional verification ever count toward release?
5. What is the minimum off-host custody the owner will accept before any verification or correction command exists (separate administrator, notary, signed publication)?
6. Is a person-level separation check on sightings (not only on verifications) required?
