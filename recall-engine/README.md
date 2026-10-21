# Recall engine (Phase 1)

Deterministic, pure recall-decision library for HORIZONXT PS10. Python 3 standard library only: no network, no AI, no database, no framework. Not connected to the MSME PRAMAAN repository.

Scope is deliberately small: replay a motor's event history up to per-source ingestion watermarks and decide, per recall policy, whether the motor is `EXCLUDED_WITH_EVIDENCE`, `AFFECTED` or `UNRESOLVED`. No API, UI, database or auth.

## Run

```bash
python -m unittest discover -s tests -t .     # 127 tests (from recall-engine/): 57 Phase 1 + 42 v2 + 28 v3
python harness/run_reports.py                 # behavioral + safety reports -> reports/
python harness/compare_versions.py              # v1 vs v2 comparison -> reports/v1_v2_comparison.*
python harness/compare_profiles.py              # legacy/v2/v3 comparison + replay -> reports/v1_v2_v3_comparison.*
python harness/mutation_check.py                # 15 safety mutants must all be killed
python bench/benchmark.py                     # latency benchmark -> reports/benchmark.*
python -I fixtures/pramaan-mfg-fixtures/validate.py   # original fixture validator
```

## Layout

| Path | Role |
|---|---|
| `pramaan_recall/ledger.py` | Slot replay: `UNKNOWN`/`EMPTY`/`OCCUPIED`, baselines, conflicts, verification, gaps. **Policy-free.** |
| `pramaan_recall/policy.py` | P1 (current installation) and P2 (historical exposure + damage inspection) on top of the ledger |
| `pramaan_recall/workorders.py` | Obligations computed from events, never from a close disposition |
| `pramaan_recall/integrity.py`, `coverage.py` | Source-sequence / event-order checks; capture sessions and outages |
| `pramaan_recall/engine.py` | `evaluate(case, policy, coverage, watermark, config)` |
| `pramaan_recall/lifecycle.py` | `evaluate_series(...)`: versions, supersession, precautionary hold, notification obligation |
| `harness/` | Test harness. **The only code that reads `oracle.json`.** |
| `tests/` | Oracle agreement, harness meta-tests, fixture preservation, regression tests |
| `fixtures/pramaan-mfg-fixtures/` | Supplied archive, byte-for-byte (`MANIFEST.sha256`, `.gitattributes` disables EOL conversion) |
| `reports/` | Generated behavioral, safety, benchmark, test and validator outputs |

## Decision semantics (as implemented)

* **Watermarks.** `watermark = {sourceId: highest ingested sourceSeq}`. Later events are invisible. Sequences must be gap-free from 1 up to the watermark; a hole, duplicate, non-monotonic `recordedAt`, event recorded before it occurred, event outside every capture session, or dangling `supersedesEventId` is an unboundable material gap on every slot.
* **Slot state / trust.** A slot starts `UNKNOWN`. Only an install from a mandatory-capture source under a `BUILD` work order that reconciles to `COMPLETED` is a trusted as-built baseline. Removal/install claims without a baseline never establish current contents (`NO_TRUSTED_BASELINE`). `endsInstallEventId` must resolve to the current occupant; a removal whose observed part/lot (or serial) disagrees with the occupant is a conflict.
* **Verification.** A `SLOT_STATE_VERIFIED` counts only from a `trustedVerifierSources` source **and** an actor who is not in that slot's record history. It re-establishes a slot's *state*, which bounds capture gaps that precede it; it does not recover *history* (so it never proves "no historical exposure" across a gap). An observed affected lot always wins over the records. An observed unaffected lot never overrides records that may show an affected lot (`UNRESOLVED`, review).
* **Capture gaps.** Gaps between consecutive sessions of a mandatory-capture source (any length), unresolved `CAPTURE_EXCEPTION_RAISED`, unmet/pending work-order obligations, and integrity issues. Material unless bounded by verification. A gap on a slot outside the policy scope is reported (`IRRELEVANT_SLOT_GAP`) but does not block.
* **Corrections.** `supersedesEventId` replaces the old event in the replay; the old event stays in evidence and in exposure history. Every install correction is a *claim* until verified, regardless of source: risk-increasing means hold + review; risk-decreasing is not applied (original stays in force) and is queued for review; neutral keeps the original.
* **Identity.** `identityGranularity` `LOT` or `SERIAL`. Serial identity cross-checks removal scans against the occupant; lot identity cannot. With `Config(strict_lot_ambiguity=True)` an exclusion that rests on a lot-level scan while a sibling slot holds the same lot becomes `UNRESOLVED`; by default it is `EXCLUDED` with flag `KNOWN_LIMITATION_LOT_LEVEL_SLOT_AMBIGUITY` (the agreed semantics, and the supplied expectation).
* **Finding vs action vs review.** `operationalAction` is derived from the finding (`EXCLUDED`→`RELEASE_ELIGIBLE`, otherwise `RECALL_HOLD`). `reviewRequired` is separate: any `UNRESOLVED`, or an unverified late claim that is not already settled by a stronger finding. Nothing is ever auto-released; `RELEASE_ELIGIBLE` only means no recall-relevant evidence to hold on.
* **Lifecycle.** A new version is issued only when the outcome changes; it supersedes (never edits) the prior one and records `triggerEventId`. A withdrawn exclusion gets `PRIOR_EXCLUSION_WITHDRAWN`, `precautionaryHold`, and a `notificationObligation` conditional on the earlier decision having been communicated.

## Where the supplied fixtures and the agreed semantics needed interpretation

Fixtures and oracle are unmodified. Nothing below was patched; each was resolved in the engine and is documented here.

1. **`reviewRequired` on AFFECTED with an unverified risk-increasing claim.** The task asks for review on unverified risk-increasing evidence; the oracle has `reviewRequired=false` for `case-05` P2 v2 (AFFECTED, late claim present) because the generator derives `reviewRequired == (finding == UNRESOLVED)`. Engine follows the oracle: review attaches to the decision the claim could change (P1), not to a P2 finding already settled by confirmed exposure. If review should attach to every decision that mentions the claim, `case-05` P2 v2 and `case-05b` P2 v2 flip to `true`.
2. **`SLOT_RECORD_CONFLICT` flag** is on `case-03` P2 but not P1. Rule inferred: emitted when a hard record conflict exists and no reason code already names it (P1 has `DOUBLE_OCCUPANCY`). Matches all cases; it is an inference, not a documented rule.
3. **`IRRELEVANT_SLOT_GAP`** appears only when no policy-scope slot has a material gap (absent from 04b/04c where the NDE gap also exists). Inferred.
4. **P2 secondary reasons.** P2 lists gap and late-claim reasons (`MATERIAL_CAPTURE_GAP`, `LATE_CLAIM_RISK_INCREASING`) beside the exposure reasons but not structural ones (`DOUBLE_OCCUPANCY`, `NO_TRUSTED_BASELINE`). Inferred as "evidence-completeness reasons only".
5. **`case-05b` has no P2 v3** in the oracle although verification arrives. The engine, evaluated at that watermark, would issue one (AFFECTED, reasons drop `LATE_CLAIM_RISK_INCREASING` once corroborated). Not compared, not a mismatch.
6. **Ground truth** exists only in `case-06` (P1). `case-06b` describes the true state in prose but has no `groundTruth` block.
7. **`provisional`** verification/inspection payloads are accepted and surfaced via `assuranceWarnings`; the fixtures leave "independent verifier" and "valid inspection" undefined. This implementation's definitions (source + actor independence; protocol, strictly after announcement, qualified, PASS, scope prefix-matches the slot) are assumptions.
8. `build_fixtures.py` on Windows writes CRLF, so regenerating reproduces the content but not the bytes of the LF archive. Preserved files are the archive's bytes.

## Remaining assumptions and known limits

* One motor per history; grouping a fleet is the caller's job.
* Operations outside any capture session are invisible; a wrong-slot scan inside a session is only detectable with serials or verification.
* An outage of any length between sessions is treated as a gap for every slot (conservative; multi-day shift patterns will need session semantics clarified). Gaps are only reported once the evaluation horizon (latest visible `recordedAt`) has reached their start.
* `timeSource` (e.g. `OPERATOR_ENTERED`) is not used for trust; trust comes from source, mandatory coverage, and verification.
* Not modelled (as in the fixtures): hashes/signatures, stores issue feed, test-rig results.
* Synthetic tests do not establish factory-level correctness.

## Phase 1.1: slot attribution safety (opt-in, `Config(slot_attribution=True)`)

Phase 1 behaviour is the default and is unchanged (`fixtures/pramaan-mfg-fixtures/` and its oracle are **version 1**, byte-for-byte; `Config()` still reproduces all 25 expectations). Version 2 adds `fixtures/v2/` (new cases, `policies.json` with a `slotAttribution` block, `oracle-v2.json`, `ground-truth.json`, `VERSION_TRANSITION.{md,json}`, `build_v2.py`). The exact v1 -> v2 transition (2 changed evaluations, 10 added, 23 carried over unchanged, v1 file hashes) is in `fixtures/v2/VERSION_TRANSITION.md`.

**AMBIGUOUS_SLOT_ATTRIBUTION.** A removal scan is ambiguous when its observed part and lot (or serial) match the recorded occupants of more than one slot at that time, or match the claimed slot while another slot's state is unknown. All other slots are treated as accessible; unknown state and coverage gaps never rule a slot out. Only trusted `SLOT_ACCESS_EVIDENCE` (approved source and method, same work order, earlier than the removal, different actor) can. Candidates and supporting event ids are listed in `slotAttribution`. Ambiguity is not a wrong-slot finding: it creates no conflict. It blocks an exclusion only when the removed lot is affected and the removal was claimed for the slot being evaluated. The slot's reconciliation shows `AMBIGUOUS_ATTRIBUTION` while it stands.

| Assurance | What it is | Clears ambiguity |
|---|---|---|
| `CLAIMED_SLOT` | operator-selected position | no |
| `OBSERVED_SLOT_LABEL` | provisioned motor+slot label, valid binding, same motor / work order / capture session, within `labelAssociationWindowSeconds` (60, a prototype parameter) of the removal scan | no |
| `CORROBORATED_SLOT` | `SLOT_STATE_VERIFIED` after the removal from a trusted verifier source, authorized actor, approved method, and independent of the operator claim (actor not in the slot's history, source and evidence refs distinct from the claim events, not derived from them) | yes, for P1 current state |

A label for a different slot than the claim is a `REMOVAL_SLOT_LABEL_MISMATCH` conflict. Corroboration re-establishes current state only; historical exposure (P2) is not erased. A verification that fails independence is recorded with `rejectedReasons` and counts for nothing.

**Serial identity.** A removal serial that matches the installed serial of a *different* slot is a `REMOVAL_SERIAL_IN_OTHER_SLOT` conflict (UNRESOLVED, reconciliation `CONFLICT`), even when the claimed slot has no record. Serial agreement with the claimed slot neither proves position nor repairs an untrusted baseline.

**Fail-safe configuration.** With `slot_attribution=True` but no `slotAttribution` block in the coverage policy, nothing can clear an ambiguity (no approved methods, no labels).

**Policy switch to decide.** `unknownSlotIsCandidate` (default true) makes a sibling slot with no usable record a candidate. Setting it false is the less safe reading (a missing sibling record can then not trigger ambiguity). It changes no v1 fixture.

### v1 vs v2 results (`reports/v1_v2_comparison.md`)

Zero false releases against synthetic ground truth (v1 engine: 2, case-06 and case-06c); 5 EXCLUDED decisions remain (4 in P1); one correct replacement (case-06e) is now held because its records are indistinguishable from the wrong-slot case-06c; no regressions.

### Limits that remain (physical world)

* A label scan shows a scanner read a label near the removal, not where the bearing came from. Labels can be scanned away from the slot, moved or copied. Records for 06c and 06e are identical; the engine cannot know which is true, so both are held.
* `CORROBORATED_SLOT` is metadata-level independence (source, actor, evidence refs, method). A careless or colluding verifier at an approved source clears an ambiguity. The authorized-actor list and approved methods are static prototype configuration.
* The 60 s window is a prototype parameter, not a proven safety standard. Session "authentication" is a flag on the session record (default true), not a verified credential.
* Serial associations are the installation records. If both the install scan and the removal scan are wrong the same way, nothing contradicts them.
* An untrusted verification that observes an affected lot is still ignored (Phase 1 behaviour), not turned into a hold.
* Ground truth is synthetic and covers P1 only. Zero false releases here is a property of 7 authored cases, not evidence about a factory.

## Phase 1.2: untrusted affected-bearing observations (semantics profile v3)

**Semantics profiles.** A decision records `semanticsProfile` and a `coverageDigest`: `P1_LEGACY` (Phase 1, `Config.legacy()` == `Config()`), `SLOT_ATTRIBUTION_V2` (`Config.v2()`), `UNTRUSTED_OBSERVATION_V3` (`Config.v3()`). `evaluate()` and `evaluate_series()` with no config now use `Config.default()` = v3, **for new evaluations only**. `replay(case, policy, coverage, record)` re-runs a stored decision under the profile it names (records without one are legacy) and refuses if the coverage policy changed. Explicit configs, the v1/v2 fixtures, and their oracles are untouched and still agree 25/25 and 35/35 under their own profiles.

**UNTRUSTED_AFFECTED_OBSERVATION.** A `SLOT_STATE_VERIFIED` that is not trusted (untrusted source, or fails the v2 independence checks) and reports an affected lot:

* in a policy-relevant slot of this motor -> P1 `UNRESOLVED` + `RECALL_HOLD` + review, **never `AFFECTED`**, unless something answers it:
  * *stale*: a later install in that slot, or
  * *resolved*: a later `CORROBORATED_SLOT` verification.
  "Later" is proven only if `occurredAt` is later by more than `observationClockSkewSeconds` (300, prototype) **and** `recordedAt` is later **and** both events carry a clock in `trustedTimeSources`. A late-arriving, operator-clocked or near-simultaneous observation therefore keeps blocking.
* P2: an affected-lot sighting counts as unconfirmed historical exposure, so P2 is `UNRESOLVED`, not an exclusion.
* in a slot outside the policy scope -> does not block; flag `OUT_OF_SCOPE_UNTRUSTED_AFFECTED_OBSERVATION` and review.
* not attributable (other motor or no slot) -> does not block; flag `UNATTRIBUTABLE_UNTRUSTED_AFFECTED_OBSERVATION` and review.
* an observation of an unaffected lot is recorded and never releases anything or blocks.

Arriving after a release, it supersedes the exclusion through the existing lifecycle: `RECALL_HOLD`, `precautionaryHold`, `PRIOR_EXCLUSION_WITHDRAWN`, notification obligation. Missing time parameters in the coverage policy fail safe (nothing is stale or resolved).

Fixtures `fixtures/v3/` (cases 08 .. 08l, `oracle-v3.json` = the 35 v2 evaluations unchanged + 19 new, `VERSION_TRANSITION.md`). Results: `reports/v1_v2_v3_comparison.md`; mutation run: `reports/mutation_v3.txt`.

### Limits that remain (v3)

* Only `SLOT_STATE_VERIFIED` is treated as an observation. A bad reading carried by any other event type is not seen.
* A coherent but false reading is held, not disproved; held false alarms need a human or an independent check (cases 08e, 08j, 08k).
* Trust of a source, an actor, a clock and the 300 s margin are static prototype configuration.
* Observations about a different motor are surfaced but never block; a mistyped serial can hide a real risk behind a flag.
* Ground truth is synthetic (P1 only); zero false releases describes the authored cases, not a factory.
