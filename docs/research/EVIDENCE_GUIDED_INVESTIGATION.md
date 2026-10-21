# Evidence-Guided Recall Investigation Workspace — research and design review

Branch `research/evidence-guided-investigation`, from audit baseline `4a9e8f2` (`phase3/unified-application`).
Research only: no code, no changes to any remediation branch, `main`, the v3 engine, publication, obligations,
authentication or freshness. Written by the same agent that audited A31, so it needs owner review.

## A. Capability gap versus existing Phase 3

What the baseline snapshot already exposes per motor (verified by running the seeded demo):

* `evidenceFinding` / `operationalAction` / `reasonCodes` / `reviewRequired` / `flags`
* per slot: `reconciliation`, `gaps[]` (kind, sourceId, window, materiality), `conflicts[]`, `verifications[]` (with `rejectedReasons`)
* `slotAttribution[]` (candidates, ambiguity, label scans, what would clear it), `untrustedObservations[]` (status, `rejectedReasons`), `workOrders` obligations, `evidenceEventIds`
* fleet board, lot investigation (which motors hold a lot), genealogy, history, notification obligations.

What it does **not** do:

1. It answers "why is this motor held?" one motor at a time. There is no "what evidence would I go and get?" view.
2. The reason is a coarse code. `MATERIAL_CAPTURE_GAP` merges `SOURCE_OUTAGE` and `UNRESOLVED_EXCEPTION`; the specific window, source and slot sit in nested fields a user must dig for.
3. There is no cross-motor view of *evidence gaps*. The lot view groups by lot, which is containment scope, not evidence need.
4. Nothing orders the work.

In the seeded demo (read-only run): `MTR-26002` `AMBIGUOUS_SLOT_ATTRIBUTION` (candidates DE/NDE, no label scan, no access evidence); `MTR-26004` `MATERIAL_CAPTURE_GAP` (`SOURCE_OUTAGE` on `ASSY:MTR-26004`, 2026-10-02 to 10-09, material); `MTR-26005` `UNTRUSTED_AFFECTED_OBSERVATION` (rejected for `SOURCE_NOT_TRUSTED`, `METHOD_NOT_APPROVED`, `ACTOR_NOT_AUTHORIZED`). **Important finding: the seeded demo contains no shared gap.** Source ids are per motor (`ASSY:MTR-xxxxx`), so every gap is unique. A cross-motor demo needs an authored scenario (see D and F).

## B. Three alternative designs

| | Design | What it adds | Novelty | Practical value | Risk |
|---|---|---|---|---|---|
| **A** | **Reason-to-task worklist.** Deterministic per-motor projection: each unresolved reason becomes a task naming the missing evidence class, with links to the reason code and ledger event ids. | Turns nested fields into readable tasks. | Low. Essentially a better-formatted explanation. | Moderate, immediate. | Lowest. |
| **B** | **Shared evidence-gap clusters (recommended).** A is computed for every held motor, then tasks are grouped by an *exact* ledger key (same gap kind and same source or window, same rejected-trust reason and actor/device, same raw-material lot). Each cluster lists the motors, components and shipments whose hold *lists* that gap, with a published, ordered priority key. | The cross-motor view: one investigation, many motors. | Moderate. Not found in the MES material I reviewed (below). | High if shared gaps occur; none occur in today's seed. | Low-moderate (clustering and ordering misread as risk). |
| **C** | **Counterfactual what-if.** For each gap, run the pure v3 `evaluate` on the case plus hypothetical evidence and show best and worst outcomes. | Shows which evidence could actually clear a hold. Strongest prioritisation. | Highest. | Highest. | Highest: looks like a release prediction, invites fabricating the "good" evidence, and requires authoring hypothetical events that the trust model must treat as untrusted. |

Recommendation: **B, built on A, with C deferred** as a separate decision after B is judged.

### Novelty challenge

Practitioner and vendor material I could retrieve ([SG Systems NCR/CAPA guide](https://sgsystemsglobal.com/?p=15697), [Critical Manufacturing genealogy](https://www.criticalmanufacturing.com/mes-for-industry-4-0/apps/genealogic/), [iFactory closed-loop genealogy](https://ifactoryapp.com/article/ifactoryai-closed-loop-spc-quarantine-corrective-action-genealogy), [Siemens Opcenter execution blog](https://blogs.sw.siemens.com/opcenter/whats-new-in-opcenter-execution-discrete-2601/)) describes: genealogy to scope affected lots, containment holds, NCR, root-cause and CAPA with owners. Siemens markets forward/backward genealogy for recall analysis. These are **marketing pages**, not documentation; the search returned nothing on shipped-lot or customer workflows and nothing on handling *missing* genealogy records as a task type. I have not verified product behaviour, so "not offered by MES" is **unproven**.

Honest positioning: CAPA/NCR track human-created tasks and owners; genealogy answers "which lots/units are in scope". The candidate novelty is narrower: **tasks derived mechanically from an evaluator's own reason codes, bound to ledger evidence ids, and clustered by shared missing evidence, with no manually maintained state.** That is a modest, defensible contribution. It is *not* a replacement for CAPA and must not claim to be.

## C. Strongest adversarial counterexamples

1. **Task as clearance.** Operators treat "task done" as "motor cleared". Mitigation: tasks carry no completion state and no button; they vanish only when new trusted ledger evidence changes the standing decision after re-evaluation. Labelled "quality-review task, not release authorisation". There is no shipment or release action.
2. **Coaching fabrication.** A task such as "scan the NDE label" could prompt someone to record the evidence that clears the hold. Mitigation: tasks name an evidence *class* and the rule that rejected the existing one, never an expected lot or outcome. Trust gates stay in the evaluator. Design C is the one that violates this and is why it is deferred.
3. **Wrong fix for untrusted evidence.** `ACTOR_NOT_AUTHORIZED` / `METHOD_NOT_APPROVED` invites "just approve the handheld". Retroactive trust approval is not evidence. Task text must say new, independently trusted evidence is needed; trust configuration changes are out of scope and not suggested.
4. **False clusters.** Fuzzy matching would join unrelated gaps. Mitigation: cluster keys are exact equality over ledger fields and are displayed with the key. Because current source ids are per motor, clusters on sources only appear if the data model gains a shared station/device id.
5. **"Sole blocker" overclaim.** The reason list shows what the evaluator printed, not what would clear the hold. Wording must be "listed blocker", never "resolving this releases the motor". Only design C could support the stronger claim.
6. **Priority bias.** Ordering by blast radius can starve a single motor with the most dangerous signal (untrusted affected observation). Mitigation: no single score; a fixed lexicographic key shown in the UI, with `untrusted affected observation` and `precautionary hold / withdrawn exclusion` pinned ahead of size.
7. **Absence read as non-existence.** "Missing" means "not in the ledger as of watermark W". Paper records may exist. All explanation text states this and cites the watermark.
8. **Staleness.** Tasks derived from an old snapshot mislead. Tasks must be recomputed server-side per request from the same snapshot as the decisions, carry its watermark, and hide when decisions hide. This depends on Codex's C1–C3 freshness work; the feature must not duplicate it, only consume it.
9. **Duplicating obligations.** `PRIOR_EXCLUSION_WITHDRAWN` is a notification matter, not an evidence-gathering task. It must link to the existing obligation and generate no investigation task of its own.
10. **Multi-recall creep.** Keys include `policyId` so a future multi-recall model stays compatible, but there is one immutable recall scope now and no cross-recall logic.
11. **Demo circularity.** If the shared-gap scenario is authored to fit the clustering, the demo proves nothing. State this; real value needs data from a real line.

## D. Data requirements and integration boundaries

Read-only inputs, all already in the decision/snapshot: `reasonCodes`, `slots[].gaps/conflicts/verifications`, `slotAttribution`, `untrustedObservations[].rejectedReasons`, `workOrders` obligations, `evidenceEventIds`, `watermark`, unit shipment, components, lineage, lots.

Not available today and needed for the cross-motor value: a **shared source dimension** — station, device or line id on events (actor exists; source ids are per motor). Adding it touches the integration/ledger event schema, which is outside this assignment and needs a separate decision. Without it, cluster keys reduce to rejected-trust reason plus actor, and the raw-material lot.

Boundary (hard):

* Pure function `investigations(snapshot) -> {tasks, clusters, watermark}`. No writes, no storage, no tables, no endpoints that mutate.
* Does not call or alter `evaluate`, lifecycle, the audit/publication journal, obligations, authentication or freshness.
* No task state means nothing to lose, replay or tamper with; a task is a view of a decision.
* Taxonomy mapping `reasonCode/gapKind -> evidence class text` is a reviewed static table; an unknown code yields an explicit "unclassified, see decision" task, never silence.

## E. Smallest useful implementation scope

Phase 1 (design B minimum): Python module with the pure projection and the static taxonomy, covering the reason codes the seed actually produces plus the gap kinds in `policy.py`; a read-only `GET /api/investigations` that reuses the existing snapshot; one UI page listing clusters, tasks, linked event ids, affected motors/components/shipments and the ordering key; tests proving determinism, no input mutation, one-to-one reason coverage, and that decisions are byte-identical with the feature present. Out of scope: assignment, due dates, comments, task state, CAPA export, notifications, counterfactuals, schema changes.

## F. Expected demo flow

1. Open the investigation page: held motors grouped into clusters, each with its published ordering key.
2. Open a cluster: the reason code, the exact gap, linked event ids, the motors/components/shipments whose hold lists that gap, and the watermark.
3. Capture evidence for one motor through the existing workbench; the standing decision changes (or not) on re-evaluation, and the task appears or disappears accordingly — with no manual closure.
4. Show a cluster with an untrusted affected observation pinned first, and a motor whose evidence arrives but is rejected, so the task stays.
5. Backend offline: the page hides with the decisions.
Requires an authored synthetic scenario with a shared gap (for example two motors with the same actor/device rejection, or two motors built in one outage window). It must be labelled as authored to demonstrate clustering, not evidence of frequency.

## G. Recommendation: **REVISE**, then GO for design B Phase 1

* GO for the narrow read-only projection (A + B). The risk is low and the boundary is clean.
* REVISE before freezing: (1) decide whether the shared-source dimension may be added to the synthetic event schema; without it the headline cross-motor value shrinks to lot and actor groupings; (2) approve the taxonomy and the "not a release / not a clearance" wording; (3) accept that the novelty is narrow and unverified against real MES/CAPA products.
* NO-GO for design C until A/B are judged, and for any task state, release or shipment action.
* Sequencing: build on the A31 C1–C3 freshness work after Codex lands it; do not start earlier.

## H. Approval requested

Before any freezing or coding I need your decisions on: (a) design B Phase 1 scope as in E; (b) whether to extend the synthetic event schema with a shared station/device id, which touches the integration layer; (c) the baseline for implementation (this branch is from `4a9e8f2`, not A31); (d) whether design C should be researched further, separately.
