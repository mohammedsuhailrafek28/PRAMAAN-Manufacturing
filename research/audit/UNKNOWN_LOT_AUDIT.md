# Unknown-lot production-path safety audit

Audit of the frozen `manufacturing-demo-v1.0` (`c25466c56e5724158d534ff7b59f01ac48643101`). Disposable synthetic databases, loopback only, no real notification delivery.
No source, evaluator, ledger or tag was changed; this branch adds only `research/audit/`. Not a production-readiness claim, not an independent safety certification; independent custody is not demonstrated.

## Verdict

**P0 candidate confirmed (reproduced end to end).** A lot value that is not the literal recalled lot string, including `UNKNOWN`, `unknown`, `N/A`, and near-misses of the recalled lot (`br-204`, `BR-204 `, `BR-2O4`, en-dash, zero-width space), is accepted by the UI, the HTTP API, the service and the ledger. The pinned evaluator then reports `EXCLUDED_WITH_EVIDENCE` / `RELEASE_ELIGIBLE` (`AS_BUILT_UNAFFECTED_LOT`), and after the operator checkpoint step the motor is `currentReleaseEligible: true` in state `ANCHORED_CURRENT`, even though the installed bearing may physically be from the recalled lot.

The originally observed evaluator-level case (install event with a missing, empty or whitespace lot) is **not reachable through production capture**: the ledger rejects it. The reachable hazard is different and broader: the system treats "string not equal to a recalled lot string" as positive evidence of being unaffected. There is no lot master data, so "unknown" and "known unaffected" are indistinguishable.

## Layer results

| Lot input | (a) UI | (b) service | (c) ledger/profile | (d) pinned evaluator | (e) eligibility after checkpoint |
|---|---|---|---|---|---|
| missing (`null`/absent) | rejected by `required` | rejected: "Explicit valid DE/NDE bearing lots and identity required" (`service.py:135`); HTTP 400 `INVALID_REQUEST` | not reached | not reached | motor has no assembly: `UNRESOLVED` / `RECALL_HOLD`, not eligible |
| empty `""` | rejected by `required` | rejected (same) | not reached | not reached | same |
| whitespace `"   "` | **passes** `required` (`ManufacturingWorkbench.tsx:29-30,36`) | **passes** (`not x` is false) | **rejected** "Missing/invalid lot" (`profile.py:57-59`) after 2 to 5 events are already written (see S2) | n/a | `UNRESOLVED` / hold |
| literal `UNKNOWN`, `unknown`, `N/A` | passes | passes | accepted | `EXCLUDED_WITH_EVIDENCE`, `AS_BUILT_UNAFFECTED_LOT` | **`currentReleaseEligible: true`** |
| known unaffected `BR-310` (control) | passes | passes | accepted | same as above | eligible (intended) |
| known recalled `BR-204` (control) | passes | passes | accepted | `AFFECTED`, `AFFECTED_LOT_INSTALLED` | not eligible |
| near-miss of recalled lot (case, trailing space, letter O, en dash, zero-width) | passes | passes | accepted | `EXCLUDED_WITH_EVIDENCE` | **eligible** |

Why: the evaluator tests exact membership, `o.get("lot") in policy["affectedLots"]` (`recall-engine/pramaan_recall/policy.py:36-37`), and a non-member with a baseline of `AS_BUILT_VALIDATED` yields `AS_BUILT_UNAFFECTED_LOT` (`policy.py:162-164`).

Results are the same for every combination tested: the unknown/near-miss lot in the DE or the NDE position; recall scoped DE, scoped NDE, scoped DE+NDE, and unspecified scope (all compatible positions); and in three capture paths: initial assembly (`assemble`), DE replacement (`replace`, which also turns a held motor with a recalled DE bearing into `RELEASE_ELIGIBLE` when the new lot is `UNKNOWN`), and untrusted observation (`observe`). A scoped recall correctly ignores the other position, as designed (for example, a recalled lot in NDE under a DE-only recall is excluded). 84 service-level cases: `results/run1/matrix.json`, `results/run1.log`.

## End-to-end through the operator path

`results/e2e.json` (script `unknown_lot_e2e.py`): HTTP capture with token and same-origin checks, recall announced over HTTP, then `checkpoint_ops.propose`, `accept`, restart of the server with the accepted checkpoint, and `GET /api/snapshot` plus `/api/motors/<id>/decisions`.

| Case | Before checkpoint | After accepted checkpoint |
|---|---|---|
| `UNKNOWN` | `ANCHORED_PREFIX_ONLY`, eligible false | `ANCHORED_CURRENT`, `RELEASE_ELIGIBLE`, eligible **true**; decisions endpoint 200 eligible true |
| `BR-2O4` (typo of recalled) | same | same, eligible **true** |
| `BR-310` control | same | eligible true |
| `BR-204` control | same | `AFFECTED`, `RECALL_HOLD`, eligible false |

Existing mitigations that did work: until a checkpoint covers the new state, eligibility is false (`ANCHORED_PREFIX_ONLY`). The mitigation that did not: the checkpoint review. `propose` shows the reviewer only counts (`newRowsByTable: captures 9, events 9, recall_announcements 1`), never lots, decisions or findings, and `accept` asks only for the file hash and a custodian name. So the human step cannot be relied on to catch this. The HTTP-only run (`results/http.json`, 26 cases) confirms the decision label reaches API consumers immediately (eligibility false only because of the checkpoint state).

## Secondary findings

- **S1: ambiguous "known" status.** `lots` in the snapshot is derived from the same capture that is being judged (`service.py:306`): every lot string entered becomes a "known" lot with a supplier. Nothing external vouches for it.
- **S2: non-atomic capture.** `assemble` writes a work order, material and manufacturing events before the profile validation that rejects a whitespace lot; the failed request leaves 2 to 5 events (HTTP 400). The unit then reports "already has assembly evidence", so the capture cannot be retried. It fails closed (hold) but leaves a stuck unit. The service-level check (`service.py:135`) and the ledger check (`profile.py:57`) disagree on whitespace.
- **S3: checkpoint review is content-blind** (above).

## Severity and classification

- Reachability: yes, from the public UI form, the HTTP API (loopback, token) and the Python service, with no special privilege beyond the REWORK/ASSY operator role the demo already assumes.
- Preconditions: a recall announced with a specific lot string; an operator (or a scanner or typing error) records any other string; the owner accepts the next checkpoint.
- Impact: a possibly recalled bearing is cleared by the system's own current-eligibility field.
- Classification: **P0 candidate** under the owner's rule (a reachable case can produce current `RELEASE_ELIGIBLE`). It is a fail-open default of exact-match exclusion, not a bug in the evaluator's logic as specified. Whether the evaluator's behaviour is "correct" is an owner decision (see Decisions).
- Limits of this audit: synthetic data; one recall policy; no hosted CI; no physical lot master; the UI layer was checked by reading the form source (browser `required` semantics), not by driving a browser; no concurrency testing.

## Minimal fail-closed correction (recommended, NOT applied)

Smallest change that closes the reachable cases without altering the evaluator:

1. **Canonical lot form at capture** (service layer): trim-free, ASCII, no control or zero-width characters, configured lot pattern; reject sentinels (`UNKNOWN`, `N/A`, `NONE`, `TBD`, `-`, case-insensitive). Apply to `assemble`, `replace`, `observe` and `announce`, and make the validation atomic (validate before the first event is written).
2. **Normalized-match fail-closed at evaluation** (bridge layer, before the pinned evaluator): if an installed or observed lot is not byte-equal to a recalled lot but equal after normalization (case, whitespace, dash variants, `O`/`0`), mark the motor `UNRESOLVED` (hold) rather than excluded. This does not touch `recall-engine/`.
3. **Positive lot registry (owner decision)**: exclusion requires the lot to be a member of an externally supplied lot master; a lot outside it is `UNRESOLVED`. Without this, typos not resembling the recalled lot (for example a truly different but wrong string) still exclude. This needs master data the frozen model does not have.
4. **Checkpoint candidate review shows the decision delta** (motors whose finding or eligibility changed, and lots newly excluded) so the human step is informative.

Items 1 and 2 are small; 3 and 4 need owner decisions. Any fix needs new tests (the 84 + 26 + 4 cases here can seed them) and, because it touches frozen application source, a new tagged baseline, not a move of `manufacturing-demo-v1.0`.

## Decisions needed from the owner

1. Is exact-match exclusion acceptable as "unaffected", or must exclusion require positive lot identity from a registry?
2. Where does a lot master come from and who owns it?
3. Should the correction be applied in the application/bridge layer (new baseline) or in the evaluator (re-pin)?
4. Should checkpoint acceptance be gated on a decision-delta review?
5. Until then, should demos and the runbook state that a typo in a lot can clear a motor?

## Reproduce

```
python -B research/audit/unknown_lot_matrix.py research/audit/results/rerun
python -B research/audit/unknown_lot_http.py research/audit/results/http_rerun.json
python -B research/audit/unknown_lot_e2e.py research/audit/results/e2e_rerun.json
```
Python 3.12.10, standard library plus the repository's PyYAML venv; each case uses its own temporary database.
