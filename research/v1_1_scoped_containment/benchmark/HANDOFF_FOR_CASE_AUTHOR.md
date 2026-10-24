# Case-author handoff (v1.2 behaviour contract). Preparation only: no sealed case exists, nothing has been run.

You are asked to write test cases for a **synthetic** safety demonstrator for a bearing recall in electric-motor manufacturing. You are deliberately not shown the implementation, its tests or its outputs. Write from the physical story, not from how the software might behave. Cases you write are scored against the software later, once, by someone else.

## What the system is supposed to do (contract; stated from the owner's requirements)
1. A motor is **release-eligible** only if the system can establish, from recorded evidence, that it does not contain a recalled bearing. Anything it cannot establish is **held** (not shipped, not released). A hold is never a clearance.
2. A **lot** is identified by membership in a manufacturer-administered lot registry (canonical string, optional aliases, supplier, dates, status). A lot string that is not in the registry, is a placeholder (`UNKNOWN`, `N/A`, `-`, `0`, empty), is withdrawn, expired, not yet effective, for the wrong part, or ambiguous, does **not** establish identity. A motor whose recorded identity is not established is held.
3. A **checkpoint** is the reviewed, protected record that the evidence and the registry were accepted at a point in time. After new evidence or a registry change, no motor is eligible until a new checkpoint is reviewed and accepted. A checkpoint that predates a registry change never lets the change raise any motor's eligibility.
4. A worker's **sighting** of a label on a bearing is an unverified claim. It never installs, registers, excludes or clears anything. If the sighted label is not an established lot, the motor is held for investigation.
5. **Renewing the checkpoint after a sighting.** The motor that received the suspicious sighting must stay held. Other motors may be renewed (and therefore released if otherwise eligible) **only if** it is established that the sighting concerns only that motor. If a shared lot, cross-motor identity, a registry change, a recall-policy problem or any wider integrity problem makes that uncertain, the wider hold is preserved: nothing is renewed.
6. **Recovery while the checkpoint is out of date**: evidence can still be captured, a held slot can be reconciled by replacing its bearing with a registered lot, and a successor checkpoint can be *proposed*. None of these ships, releases or clears a motor; eligibility returns only after a reviewed checkpoint is accepted.
7. An operation (assembly, replacement) that was started and not completed leaves the motor held; further capture for that motor is refused.

Not claimed by the system: that a registered lot proves the physical identity of a bearing; that acknowledgements are authenticated; atomic multi-step capture; crash recovery; production readiness; independent custody.

## What to deliver
One JSON file per case, valid against `case.schema.v1_2.json`. Each case has: a story (what physically happened), a registry document in force at the first checkpoint, a recall (lot and positions), an ordered list of steps (`assemble`, `replace`, `sighting`, `ship`, `announce_recall`, `edit_registry`, `accept_checkpoint`), and for every motor your expectation after the last step (`mustHold`, reason class, optional `eligibleAfterAcceptedCheckpoint`). For each `accept_checkpoint` step you may state `expectAccepted` (should the renewal be accepted?). Use `acknowledgeAll: true` to mean "the reviewing operator acknowledges whatever the review asks about". Mark any expectation you are unsure about `contested: true` with a rationale; contested cases are reported separately and never counted as passes or failures.

Practical constraints: motor serials look like `MTR-91031`; use only lots from your registry or deliberately unregistered strings; a `bypass` assembly models a record that did not pass the validating commands (legacy or another system).

## Families to cover (include hard negatives: cases where nothing is wrong and everything should be released)
- Registry lots: unregistered, look-alike (`BR-2O4`, `BR204`, `br-204`), placeholder, withdrawn, expired, not yet effective, wrong part, aliases, ambiguous supplier scope, conflicting alias.
- Checkpoint and registry custody: registry edited after acceptance, rolled back, retroactive registration of a legacy lot, alias redirected, supplier changed, dates changed; renewal with and without acknowledgement.
- Unverified sightings: single motor, same label on several motors, label resembling a lot used elsewhere, label resembling the recalled lot, sighting before and after a replacement of that slot, sighting plus an unrelated problem on another motor.
- Renewal scope: one sighted motor with several unrelated healthy motors; two unrelated sightings; a sighting while a different motor has a registry problem, an open operation, or an unregistered installed lot.
- Recovery: replacement of a held slot with registered, unregistered and withdrawn lots; replacement in the wrong slot; replacement while the checkpoint is out of date, then renewal.
- Interrupted operations: stopped after each step of an assembly or replacement; retry; shipment afterwards.
- Combined problems.

## Rules for you
- Do not read any other file of the repository. Do not ask for, or read, any output of the software.
- Prefer externally cited scenarios (recall notices, standards, incident reports) and mark invented parts `INVENTED`.
- Deliver cases only. A separate ground-truth reviewer judges each case before the software is run; you do not see their verdicts either until scoring.
