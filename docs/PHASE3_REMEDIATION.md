# Phase 3 safety remediation

Branch `phase3/safety-remediation`, from audit baseline `4a9e8f2c11e5e12bfd6926bfb9f9a0ee0dd3fa57`
(`phase3/unified-application`). Not merged, not deployed. `recall-engine/` and `experiments/foundation/` are
byte-identical to the baseline (git tree ids are asserted by the verification command).

The remediation was written by the same agent that raised the audit findings. It needs an independent re-audit.

## Findings, causes and fixes

| ID | Sev | Finding | Root cause | Fix |
| --- | --- | --- | --- | --- |
| F-1 | P0 | A motor with the recalled lot only in the NDE position was released (`EXCLUDED_WITH_EVIDENCE` / `RELEASE_ELIGIBLE`). | `Manufacturing.announce` hardcoded `affectedSlots=["DE"]`; the UI and API had no scope input. | `announce(lot, slots)` requires an explicit scope: a non-empty, duplicate-free subset of `DE`/`NDE`, anything else raises `ValidationFailure`. `POST /api/recalls` takes `slots`; the workbench has required DE/NDE checkboxes with no default and a disabled button. The ledger already refused unsupported stored scopes (`LedgerBlocked`). An empty snapshot reports `affectedSlots: []`, not `["DE"]`. Explicit DE-only, NDE-only and both-slot policies are all honoured by the unchanged engine. |
| F-2 | P0 | The notification obligation vanished on the next evaluation. | The engine's lifecycle attaches `notificationObligation` only to the withdrawing version; the next fresh evaluation can never contain it, so the lifecycle fabricated an identical "unchanged" copy without it, and `/api/notifications` read only the current decision. | Obligations are an append-only, hash-chained registry (`obligation_events`: `CREATED` by a decision version, `RESOLVED` only by an explicit attested transition). The API/UI list them from the registry. `resolve_obligation` is validated (known id, open, supported resolution, actor and note required) and records `deliveryAcknowledged: false`; `deliveryStatus` stays `NOT_SENT`. Nothing claims delivery. |
| F-3a | P0 | Material evidence/flag/attribution/policy changes with an unchanged headline were dropped. | `lifecycle._signature` covers only finding/action/review, reason codes and slot reconciliation. | `pramaan_integration/lifecycle.py` (lifecycle v2) versions on a signature of everything the engine derived from evidence plus the policy digest. Identical evaluations add no version and no stored run. |
| F-3b | P0 | A current snapshot showed a previous body under a newer watermark. | The engine returns `dict(prev, watermark=new, unchanged=True)`. | An unchanged evaluation is reported with the standing version's identity but its own freshly evaluated body and watermark (`issuedAtWatermark` records the issuing one). |
| F-3c | P0 | Deleting all stored decision history silently recreated v1. | `decide` treated "no rows" as "first evaluation"; append-only triggers do not survive dropped triggers or a copied-over file. | `decision_chain` hash-chains every stored run. `decide` verifies chain and runs first (`LedgerBlocked` on deletion, edit or an unchained run). `anchor()` / `verify_anchor()` export and check the chain head, so wholesale deletion of both tables is caught against an external anchor. Pre-chain databases are adopted once at open. |
| F-3d | P0 | Legacy replay must survive. | n/a | Engine `replay` is untouched. A standing lifecycle-v1 run stays as issued and replayable; the v2 layer continues it as an explicit `-r2` revision that supersedes the last v1 decision. |
| F-4 | P1 | `application.verify` failed on a clean clone. | Compared against commits `1620ed3`/`bc68dc0`, which are not in the destination history. | `integration/run_validation.py` pins git tree ids (engine `22d205d5…`, foundation `fe6f3929…`, the trees of those source commits) and also requires a clean working tree under both paths. Validation is not weakened: a changed byte changes the tree id. `application.verify --output-dir` added. |
| F-5 | P1 | After the backend died, the loaded screen kept showing old decisions as if current. | No liveness check after the first load. | `GET /api/heartbeat` and `GET /api/integrity`; snapshots carry `generatedAt` and `ledgerHead`. The UI probes every 5 s; a failed probe shows a persistent alert banner, relabels action chips "Last recorded action · not current", and disables commands. A changed ledger head reloads the snapshot. Every backend request has an 8 s timeout. Fixtures have no heartbeat and are never presented as live. |
| F-6 | P1 | Long identifiers overflowed the page on mobile (event log: 388 px). | Unbreakable text in table cells, `dd`, `li`, `pre`. | `overflow-wrap:anywhere` and `min-width:0` on those containers; `pre` wraps. |
| F-7 | P1 | The scrollable genealogy region was not keyboard accessible (axe `scrollable-region-focusable`). | `.graph-scroll` had no `tabindex`. | `role="region"`, accessible name and `tabIndex=0`, with a visible focus ring. |

## Audit-finding → test mapping

| Finding | Tests (before → after) |
| --- | --- |
| F-1 | `application/test_remediation.py`: `RecallScope.test_nde_only_recalled_lot_is_held_under_nde_scope`, `…_under_both_slot_scope`, `test_explicit_de_only_scope_is_preserved`, `test_missing_or_unsupported_scope_fails_closed`, `test_unsupported_scope_in_a_stored_policy_blocks_instead_of_releasing`, `test_different_scope_for_same_lot_is_not_silently_accepted`; `HttpRemediation.test_recall_without_or_with_bad_scope_is_rejected_over_http_and_nothing_is_announced`, `test_nde_scope_over_http_holds_the_nde_only_motor`; Vitest `recall scope control (P0)`; Playwright `live manufacturing capture…` (button disabled until a position is chosen) |
| F-2 | `ObligationPersistence.*` (repeated evaluation, reopen, unrelated later event, explicit resolution, invalid resolutions, tamper of the obligation log); Vitest `notification obligations (P0)`; Playwright `live manufacturing capture…` (survives a later event and a reload, then explicit attestation) |
| F-3a/b | `DecisionRevisions.test_identical_repeated_evaluation_adds_no_version_or_run`, `test_material_evidence_change_without_outcome_change_is_a_new_version`, `test_current_snapshot_content_matches_its_watermark`, `test_policy_identity_change_is_not_merged_into_the_old_series` |
| F-3c | `HistoryIntegrity.*` (whole-history deletion, edit, deletion of runs and chain vs the anchor, legitimate growth, pre-chain adoption) |
| F-3d | `LegacyLifecycle.test_v1_run_is_preserved_and_superseded_by_revision_2`; `DecisionRevisions.test_issued_versions_replay_and_match_their_stored_outcome` (compares replayed outcomes with the stored ones; the earlier audit's "replay OK" only showed no exception); engine suite (127) and integration suite (44) unchanged |
| F-4 | `python -m application.verify --gs1-checkout <pinned GS1 clone>` run from a fresh `git clone` |
| F-5 | Vitest `stale data after backend failure (P1)` (5 tests); Playwright `backend unreachable after a successful load…`, `a hung ledger on first load times out…`; `HttpRemediation.test_heartbeat_integrity_and_snapshot_head_agree` |
| F-6 / F-7 | Playwright `mobile` and `desktop: long identifiers never widen the page and every view passes axe`, `genealogy diagram region is reachable and scrollable by keyboard` |

## Before / after evidence

Before: `application/test_remediation.py` run against the untouched baseline (only `announce` given an ignored
`slots` parameter so the tests can call it) failed 17 of 22 (6 failures, 11 errors from the missing registry/chain API),
including the NDE-only false release, silent v1 recreation after deletion, and the dropped material revision. The
mobile/genealogy Playwright test failed on the baseline stylesheet (`scrollable-region-focusable`; events view overflow of
388 px). `application.verify` failed on a clean clone at the `bc68dc0` diff.

After (clean clone, documented command, exit 0): engine 127, foundation 21 checks, integration 44, application +
remediation 33, exporter 7, Vitest 34, Playwright 27, snapshot check, production build and GS1 schema validation of
generated documents pass; `engineTreeUnmodified` and `foundationTreeUnmodified` are true.

## Adversarial checks

NDE-only recalled lot; explicit DE-only; explicit NDE-only; both slots; missing/invalid scope; notification across repeated
evaluations; material evidence change without outcome change; identical repeated evaluation; backend unavailable after a
successful load; decision-history deletion and tampering. Each has a named test above.

## Remaining limitations

* **Tamper evidence, not tamper proof.** A holder of the SQLite file who deletes both `decision_runs` and `decision_chain`
  (dropping triggers) cannot be detected without an externally stored anchor. `Ledger.anchor()` / `GET /api/integrity` expose
  the head; nothing in this local demo stores it off-box automatically.
* Pre-chain databases are adopted once at open; tampering before adoption is not detectable.
* Obligation resolution is an operator attestation (the actor is the fixed demo role `ROLE:QUALITY`); no authentication,
  and no delivery is performed or acknowledged.
* A lifecycle-v1 → v2 revision re-issues the existing watermarks as `-r2` versions, so the UI history shows an extra revision
  with the same outcome. Obligations of a legacy run are not backfilled into the registry; a withdrawal that is re-derived
  under `-r2` creates a new obligation id.
* One immutable recall scope per database (unchanged); multi-recall features are out of scope.
* The heartbeat is polled (5 s), so staleness is bounded by about one interval plus the 8 s request timeout, not instantaneous.
* Browser tests share one seeded database and use system Chrome. An intermittent "port 4173 already used" appeared once
  on the first clean-clone run (a lingering local listener); the rerun passed with no change.
* Synthetic data only; the physical truth of any slot occupant is still not independently certified.
