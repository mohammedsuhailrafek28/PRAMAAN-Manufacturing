# Recall engine (Phase 1)

Deterministic, pure recall-decision library for HORIZONXT PS10. Python 3 standard library only: no network, no AI, no database, no framework. Not connected to the MSME PRAMAAN repository.

Scope is deliberately small: replay a motor's event history up to per-source ingestion watermarks and decide, per recall policy, whether the motor is `EXCLUDED_WITH_EVIDENCE`, `AFFECTED` or `UNRESOLVED`. No API, UI, database or auth.

## Run

```bash
python -m unittest discover -s tests -t .     # 57 tests (from recall-engine/)
python harness/run_reports.py                 # behavioral + safety reports -> reports/
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
