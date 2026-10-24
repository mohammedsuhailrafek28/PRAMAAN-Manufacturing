# P0 lot-identity safety remediation: research report (no candidate selected)

Branch `research/p0-lot-identity-remediation`, created from exactly `c25466c56e5724158d534ff7b59f01ac48643101`. `manufacturing-demo-v1.0` is untouched and remains the reproducible, known-vulnerable historical baseline. Everything below is an isolated research prototype under `research/lot_identity/`; nothing is promoted into the demo application, the pinned v3 evaluator (`recall-engine/`) is not edited or re-pinned, and nothing is merged, deployed or tagged. Synthetic data, loopback only. Not a production-readiness claim, not independent safety certification; independent custody is not demonstrated. Innovation selection remains paused.

## 1. Exact reachability-to-release failure

1. UI (`recall-ui/src/views/ManufacturingWorkbench.tsx:29,30,36,46`): lot inputs are `required maxLength=80`; no syntax check; whitespace satisfies `required`.
2. HTTP (`application/server.py:112-128`): bodies pass straight to the service; `deLot`/`ndeLot`/`lot` are taken as given.
3. Service (`application/service.py:135,160,194,217`): only "non-empty string, at most 80 characters". `UNKNOWN`, `N/A`, `br-204`, `BR-2O4`, `BR-204` plus a zero-width space all pass. A hard-coded supplier is attached by comparing the lot to `"BR-204"` (`service.py:124-126`): every other lot is attributed to Kaveri.
4. Ledger/profile (`integration/pramaan_integration/profile.py:57-59,75-78`): `text()` rejects blank values only, after earlier events of the same operation are already committed.
5. Evaluator (`recall-engine/pramaan_recall/policy.py:36-37,162-164`): exact membership `lot in affectedLots`; a non-member with an as-built baseline becomes `EXCLUDED_WITH_EVIDENCE` / `AS_BUILT_UNAFFECTED_LOT` / `RELEASE_ELIGIBLE`.
6. Eligibility (`service.py:~250-258`): `currentReleaseEligible` is true iff the checkpoint is `ANCHORED_CURRENT`, the motor has no pending obligation and every decision is `RELEASE_ELIGIBLE`. The lot string is never examined.
7. Checkpoint step (`application/checkpoint_ops.py:36-66`): `propose` shows only row counts; `accept` requires a file hash and a name. No content review.

So: any string not byte-equal to a recalled lot is accepted as positive evidence of "unaffected", and nothing between capture and the owner's checkpoint acceptance tests that claim. Original reproduction evidence: branch `research/audit-unknown-lot-safety` (`UNKNOWN_LOT_AUDIT.md`, `ecc93e4`), re-reproduced here by the negative tests below on the unmodified code.

## 2. Positive lot-identity safety requirements (draft contract)

| Req | Statement |
|---|---|
| R1 | Absence of a match with the recalled lot is never positive evidence. "Unaffected" requires positive identity. |
| R2 | A lot identity has states `REGISTERED`, `UNREGISTERED`, `SENTINEL`, `MALFORMED`, `NEAR_MISS`, `ALIAS_CONFLICT`, `OUT_OF_WINDOW`, `WITHDRAWN`. Only `REGISTERED` can support exclusion. The others hold or reject. |
| R3 | Canonical identifier: one syntax (synthetic here: `[A-Z]{2}-[0-9]{3}`); stored in canonical form only; aliases are declared, resolved once at capture, and a conflicting alias (two canonical targets or collision with a canonical id) is `ALIAS_CONFLICT`, never guessed. |
| R4 | A registry entry carries: canonical id, part, issuer (who asserts it), supplier id and name (the supplier scope), aliases, effective-from/to, state, provenance. Supplier attribution on events comes from the registry, not from code. |
| R5 | Provenance is declared and never overstated. Here every entry is `LOCALLY_AUTHORED_SYNTHETIC`: it shows a string is in a file the local operator wrote. It is not independently authenticated supplier evidence and not proof of physical identity. A future entry may carry `SUPPLIER_ASSERTED_UNVERIFIED` or `SUPPLIER_SIGNED` only when a real verification path exists. |
| R6 | Malformed values are rejected before the first manufacturing event of an operation is written. |
| R7 | Recalled lots must themselves be registered/canonical at announcement (no recall of a typo). |
| R8 | A decision that depends on an unestablished identity can never produce current release eligibility, whatever the checkpoint state, and a checkpoint acceptance cannot launder it. |
| R9 | The published decision history is not rewritten; a safeguard acts on the derived read model and records why. |
| R10 | Any acknowledgement by an operator is recorded as an operator assertion, not authentication. |

## 3. Candidate correction designs (prototypes, not selected)

Both subclass `application.service.Manufacturing` (`research/lot_identity/lotid.py`); neither edits frozen files.

### Strategy A: strict capture validation + positive registry membership
- Write side only. `assemble`, `replace`, `observe`, `announce` resolve every lot through the registry before the first event; only `REGISTERED` canonical results are used; supplier attribution comes from the entry.
- Prevents: sentinels, malformed, near-misses, unregistered, withdrawn, not-yet-effective, conflicting aliases, wrong supplier attribution, partial writes caused by invalid lots, recall of an unregistered lot.
- Cannot detect: records that did not pass through the service (v1.0 databases, other capture paths, direct ledger writes: the legacy `UNKNOWN` database stays eligible under A); a wrong registry entry (a typo registered as a real lot, a lot registered under the wrong supplier); a registry that is itself unverified; a correct registered but physically wrong lot (a mislabelled bearing); the registry going stale.
- Assumptions: the registry is complete and correct; all captures use the service; registry changes are controlled; effective-date checks use the application clock.

### Strategy B: capture validation + fail-closed bridge-level safeguard (no registry)
- Write side: syntax, sentinel and emptiness checks before the first event (same atomic pre-validation). Read side: `apply_guard` post-processes the snapshot and sets `currentReleaseEligible=false` and the read-model action to `RECALL_HOLD` for any motor with a current install or observation whose lot is non-canonical, a sentinel, or a look-alike of a recalled lot (normalisation, confusable characters, one edit or transposition). Published history is untouched.
- Prevents: all sentinel/malformed/near-miss cases, including records already in a database (legacy data), and checkpoint renewal cannot launder them.
- Cannot detect: a well-formed lot that is simply not registered or is wrong (`BR-999`), a lot that is withdrawn or not yet effective, wrong supplier attribution, conflicting aliases, an arbitrary typo that is not near the recalled lot. By design B has no positive identity: it narrows the unsafe set but keeps "no match = unaffected" for well-formed strings.
- Assumptions: the syntax rule is right; the recalled lot list is right; near-miss heuristics are acceptable; false holds on genuinely different adjacent lots are tolerable (measured: with recall on `BR-204`, a legitimate `BR-205` is held by B).
- Observation: A and B are complementary; a combined design (A write-side registry plus B read-side guard over legacy and bypassed data) is evident but was not evaluated and is not proposed as selected.

## 4. Adversarial tests and results

All reproducible from this branch (Python 3.12.10, repository `.venv` as in the earlier audit):
`python -B research/lot_identity/harness.py <out>` (matrix); `python -B -m unittest research.lot_identity.test_lot_identity research.lot_identity.test_decision_review`; `python -B research/lot_identity/run_original_suites.py A|A_FIXTURE|B|BASELINE`.

Matrix (`results/matrix/`): 24 lot inputs x (assemble: DE/NDE x scoped DE/scoped NDE/unspecified; replace and observe: scoped DE/unspecified) = 240 cases per implementation. Inputs: missing, empty, whitespace, UNKNOWN, unknown, N/A, `-`, `0`; recalled-lot look-alikes (lowercase, trailing space, letter O, en dash, zero-width, no dash, adjacent transposition, full-width letters); well-formed unregistered `BR-999`; malformed text; registered future-effective, registered withdrawn, a declared alias of the recalled lot; registered unaffected (two), registered recalled. "UNSAFE" = the unit ends current-eligible although its lot identity was not a valid registered unaffected lot or was recalled in scope.

| Implementation | UNSAFE | held/rejected safely | utility controls (registered unaffected, or recalled out of scope, still eligible) |
|---|---|---|---|
| v1.0 baseline (negative reproduction) | **180** | 38 | 22 |
| A | **0** | 216 | 24 |
| B | **30** (all in three classes: well-formed unregistered, not-yet-effective, withdrawn) | 188 | 22 |

Other tests (`results/extra_tests.log`, 12 tests + 1 review test, all passing; they assert the vulnerability on v1.0 and the known limits of A and B so the limits cannot silently disappear):
- Negative: frozen-code assertions that v1.0 clears `UNKNOWN`, `BR-2O4`, `br-204`, zero-width and `BR-999`.
- Candidates never clear 11 bad lots x 2 positions x 3 scopes.
- Legacy database with an `UNKNOWN` lot (captured by v1.0): baseline eligible, **A still eligible**, B held.
- Supplier scope: v1.0 attributes `BR-401` to the Kaveri supplier by hard-coding; A takes it from the registry (Northstar).
- Alias handling: declared alias resolves to the canonical recalled lot; a conflicting alias is rejected (`ALIAS_CONFLICT`) with zero events written.
- API: extra body fields (`currentReleaseEligible`, `eligibility`, `trusted`) have no effect; an `UNKNOWN` assembly returns 200 on v1.0 and 400 on A and B; a sentinel recall lot is rejected by A and B. Eligibility stays false until the checkpoint is renewed in all three.
- Static previews: `recall-ui/public/data/*.json` contain no `currentReleaseEligible` key; `recall-ui/src/contract/gated.ts:50` mints clearance only from an explicit `currentReleaseEligible === true`, so the static previews cannot show current clearance.
- Checkpoint renewal after ambiguity: an `UNKNOWN` install accepted before the fix is `ANCHORED_CURRENT` and eligible under v1.0; under B it stays held after `propose` + `accept`.

## 5. Capture atomicity analysis

- Each manufacturing event is its own committed ledger transaction (`ledger.capture` opens `BEGIN IMMEDIATE` per call). An `assemble` is 8 events, a `replace` 6; nothing spans them.
- Reproduced: whitespace lot on v1.0 leaves 2 events (DE) to 5 (NDE); retry fails with "already has assembly evidence".
- Prevalidation (both A and B): all lot arguments are checked before the first event; whitespace/invalid lots leave 0 events and the retry succeeds (tested).
- Crash injection (a fault between events, `test_partial_writes_never_clear_a_recalled_lot`, results in `extra_evidence.json`): for assemble crashed after k=1..7 events, and replace after k=2..4 (k=0..4 were tested), the unit is `UNRESOLVED` / hold and never eligible, with recalled lots and with safe lots; retry of assemble is refused ("already has assembly evidence"), so the unit is stuck; **replace crashed after 1 event, then retried, drives the motor to `LedgerBlocked: Rejected evidence exists; manual reconciliation required`** (fails closed, but unrecoverable without manual repair). Crash at k=0 writes nothing and the retry is clean.
- Conclusion: partial writes fail closed (no false eligibility observed) but are a liveness defect. Pre-validation closes the lot-input source only. Crash-safe atomicity needs a multi-event ledger transaction (one `BEGIN IMMEDIATE` around the whole operation) or an idempotent resume; both touch `integration/` and are outside this stage. No claim of atomicity under process crash is made by either prototype.

## 6. Mandatory checkpoint decision-change review (design + prototype)

Prototype `decision_review.py` (`results/decision_review_example.json`). Between the current accepted checkpoint and the candidate it computes, per motor from the audit journal: `NEWLY_EXCLUDED`, `NEWLY_HELD`, `NEWLY_UNRESOLVED`, `NEW_MOTOR`, `CHANGED`, `UNCHANGED`, with before/after finding and action, reason codes, evidence event ids, every currently installed lot and whether its identity is established under the guard rules.

Rules in the prototype `accept_with_review`: (1) every changed motor must be acknowledged individually by id; (2) acceptance is refused outright when a newly excluded motor depends on a lot whose identity is not established (tested: `UNKNOWN` motor refused even with every motor acknowledged, no accepted file created); (3) the output states that acknowledgement is not authentication and not proof of physical identity. Not implemented: displaying the review in the UI, a record of the review inside the acceptance record, and independent reviewer authentication. The owner decides whether `checkpoint_ops.accept` should require this (it is currently a separate wrapper).

## 7. Regression impact

Original suites run unmodified against the branch tree (frozen source unchanged): baseline 9 application modules (93 tests), integration 44, engine 127: all OK (`results/baseline_suites.log`). With `Manufacturing` replaced by a candidate (`results/original_suites_*.json`):
- B: 93/93 application tests pass.
- A with the demo registry: 4 errors in `test_consolidated_safety.test_scope_matrix`, because the test uses a recall lot `BR-901` that is not registered. A with `BR-901` added: 93/93 pass (`A_FIXTURE`). Impact: fixtures need registry data; the logic does not regress.
- Not run on the candidates: `integration/` and `recall-engine/` suites (they do not import the service, so they are unaffected by construction), the UI Playwright suites, and the CI gate scripts (hosted CI was not run; no claim).
- Adopting either candidate means changing frozen application source: it needs a new tag (v1.1 candidate), updated frozen-source manifest and inventory, and new tests. `manufacturing-demo-v1.0` is not moved.

## 8. Minimal proposed path to a corrected v1.1 (for owner review, nothing started)

1. Owner chooses the identity model: write-side registry (A), read-side guard (B), or both. Evidence here favours "both" for defence in depth but that combination is unevaluated.
2. Decide registry ownership and provenance wording (R4, R5); until then it stays synthetic and labelled as such.
3. Implement in the application/bridge layer on a new branch from `c25466c`: shared `lotid` module, validation before the first event in `assemble/replace/observe/announce`, atomic pre-validation, registry-derived supplier attribution, read-side guard on eligibility and displayed action, `identityGuard` in the snapshot and a UI surface for it.
4. Checkpoint acceptance requires the decision-change review (section 6).
5. Atomicity: owner decides whether crash-safe multi-event capture belongs in v1.1 (ledger change) or is documented as a known liveness limit.
6. Tests: promote the negative reproductions and the matrix to permanent regression tests; run the full original suites, the UI suites and the hosted CI on the exact SHA before any claim; refresh `ci/frozen-source.json` and the inventory deliberately.
7. New annotated tag `manufacturing-demo-v1.1` only after owner approval; the demo guidance below stays until then.

## 9. Demo guidance for v1.0

`V1_0_KNOWN_ISSUE_NOTICE.md` is the proposed wording. It states that v1.0 is affected, that its eligibility output is not robust to erroneous lot identities, and gives presenter rules. It has not been added to any other branch; applying it to the runbook branch is a separate small step awaiting your go-ahead.

## 10. Residual risks and limits

- Everything is synthetic and single-author; both prototypes were tested only against cases I wrote. The independent benchmark (separate document) exists for that reason and was not run.
- The syntax rule, sentinel list, confusable table and distance threshold are assumptions; the real lot format must come from the owner.
- B's near-miss heuristic produces false holds on legitimately adjacent lots.
- A's and B's guarantees are about string identity only. Neither detects a mislabelled physical bearing; no software here can.
- The matrix covers the three capture paths and two slots; it does not cover concurrent writers, replay of the same lot across motors, or the full UI in a browser.
- Hosted CI was not run for this branch.
