# Independent frontend audit and controlled integration

Date: 2026-10-23. Verdict: **REVISE - blocked; not ready to merge**.

This is a controlled review candidate, not H1/H2 safety closure. Claude remains the independent backend safety reviewer. No backend remediation D2-D10, source pin regeneration, main merge, PR, deployment or branch-protection changes are included. No MSME repository was used. Tests passing on captured synthetic envelopes do not certify live replay, policy authority or checkpoint custody.

## A. Frontend audit

Reviewed the original DPP, Evidence-Guided Investigation and Impact Graph implementation reports, three-feature integration report, Phase A report and branded-view implementation report, plus the pinned design branches and independent H1/H2 audit e63bf90919b1765ef9d7d00f60a69c713323c82c. The independent new challenge source is `recall-ui/tests/unit/independent-audit.test.tsx`; original failures were captured before fixes in `release-candidate-evidence/` and committed in d199e00. Proposed semantics and R1-R20 review were recorded before edits in [the pre-change review](RELEASE_CANDIDATE_PRECHANGE_REVIEW.md), including owner clarification in c31a035.

| Audit question | Confirmed code / experiment result | Limit |
|---|---|---|
| Standalone release without current eligibility? | Captured CURRENT with that motor's eligibility false preserves finding but no clearance. `contract/gated.ts:clearanceOf` requires an all-release decision set plus explicit eligibility; `ClearanceChip.tsx` checks registry-minted token | Brands are developer-misuse protection, not malicious-JavaScript protection |
| PREFIX_ONLY as current? | `gate.ts:evaluateDetailed` returns SEGREGATED/HistoricalView. `gated.ts:makeHistorical` removes decisions, eligibility and comparison. New main transitions prove no decision chips in PREFIX | Owner explicitly retained facts-only PREFIX, not historical hold records |
| Forged preview trust? | Explicit preview strips checkpoint, eligibility and freshness; cast into current Impact projection throws. Existing browser forged-preview tests retained | Public JSON remains synthetic raw evaluator output, not a trusted authorization document |
| Unknown checkpoint state? | Closed enum -> WITHHELD. New control confirms otherwise-valid forged state is refused | Backend state remains authoritative; browser does not verify hashes or replay |
| Per-motor independence? | CURRENT withheld motor does not downgrade another motor; new main test retains excluded finding and another motor's hold | Global fleet clearance must still satisfy backend policies/obligations |
| Contradictory/incomplete metadata? | Three confirmed validation omissions F1-F3 fixed; errors/hidden/expired main no longer retain raw last motor records | Not exhaustive malformed-data fuzz coverage of every event field |
| Deep links? | New browser invalid-anchor challenges cover main unit, Passport components/records, Investigation evidence and Impact node routes; original gate matrix retained | Not every possible URL string is individually tested |
| Raw data outside wrappers? | Standalone components receive branded views; static guards restrict mint/unwrap. Main's existing evidence components still inspect validated raw records, but current action claims/counts/explanations come from branded `consoleClaims`, not raw actions | `Facts` is a TypeScript omission; GatedSnapshot.facts aliases the underlying snapshot. Exported factories/WeakMaps do not isolate hostile code in the same JS realm. No XSS/security sandbox claim |
| Genuine evidence links? | Graph relationships cite recorded event fields. F5 proved a contradictory shipment read model could name a different shipment; now ID/time must match actual cited MOTOR_SHIPPED event | This audit does not authenticate supplier identity, physical contents or every hostile read-model payload |
| QR/privacy? | F4 removes userinfo along with query/fragment; encoded route retains only necessary motor ID. Four production public JSON bundles pass identifier scan | Route motor IDs and synthetic event/shipment IDs remain intentionally visible; deny-list scan is not proof of anonymization |
| Synthetic factory claims? | Preview is explicit and labelled; no current clearance token. Supplier/raw-material records are synthetic unverified claims; a ledger link is not factory authentication | Actor pseudonymization preserves within-file grouping, not cross-file identity |
| Mobile/accessibility? | Four new CURRENT 390x844 entry checks pass axe and no page overflow; screenshots attached. Existing keyboard/mobile assertions retained | Full original suite still has failures; no blanket accessibility certification |

Additional post-run observation: the RC-owned4340 and4337 listeners were gone after tests. A4321 listener belonged to Claude's separate scratch checkout; it was left untouched. Shared developer machines can collide on auxiliary ports even with an isolated primary port. Future CI must reserve every helper port, not reuse existing servers.

### Defects and bounded fixes

F1-F5 reproduction, severity and affected code are preserved in the pre-change report and `adversarial-before.json`: 10 challenges, 5 passed/5 failed at exact 748. After fixes all original 10 challenges pass, plus duplicate-current-decision-ID rejection (11 total). Scope: malformed browser read models/privacy, not cryptographic bypass.

- F1/F2: unique nonempty unit and policy IDs; exact eligibility, unit-decision and policy-decision key sets; current policy identity; existing finding/action invariants remain enforced. Unique current decision IDs prevent claim-map aliasing.
- F3: notification list must contain structured required known-motor obligations with identity and delivery-context fields. Unknown/incomplete evidence is rejected, not treated as irrelevant.
- F4: `passport/qr.ts:passportUrl` clears username/password; no credential copied to a QR.
- F5: `impact/projection.ts:buildImpactGraph` requires shipment ID and occurredAt to match cited shipment event. Contradiction withholds the edge and emits SHIPMENT_NOT_LEDGER_BACKED.
- Main gap: removed older parallel freshness implementation and global motor-withholding panel. The shared typed gate governs loads and command snapshots; four-second request timeout, generation ordering, regression memory, visibility and five-second lease remain. CURRENT preserves findings/holds with per-motor clearance. PREFIX is facts-only; WITHHELD drops motor records. Historical versions/comparison/fixtures explicitly show recorded output, never current authorization. Existing console evidence/history/genealogy functionality and links to all three features remain.

F6: diff review found main discarded successful HTTP status and supplied literal200 to the gate. A complete201 snapshot was accepted; the red reproduction is http-status-before.json. Commit75c3d77 forwards actual status for both loads and commands; additive source tests now reject201 in both paths.

Frontend remediation is in 26249a7 and75c3d77; it requires owner/independent review. This is not a claim that Codex's own H1/H2 code was independently approved.

## B. Ancestry and conflict record

Branch: `integration/manufacturing-release-candidate`, new worktree. Start exact 7482fc1fab759bfd7c3a3eedd7946eae62895a18. `release-candidate-evidence/pins.json` records reference pins.

Verified 748 ancestors: audited baseline f9282101159b6b6806974848d7c351999098d792; DPP caf651f60ef9a6444239401cee4609ad9eaf188f; Investigation 899456252c74f76cd30527baaa7dc778686ff62d; Impact 68cdef8a507378bc291493c3bb0ce5ee6d22d45b; three-feature integration 73f3bdbd78ee8bdf4b323457ba2f036f16fb82d9; Phase A cf97c1d4998f45c5060bd8d33a7b00a8fa545ed9. No redundant original-feature merges.

Separate no-fast-forward merge 8419351 imports exact H1/H2 candidate f9dcf56ae52b095a3af05b8fc45a2568cd5642fe. No textual conflicts. This does NOT resolve semantic conflicts: main/standalone gate divergence, historical-hold contract, old envelopes, historical resolution and chain-generation defect. Original authorship and source ancestry remain intact. Main, Claude's original branches, CI, reliability and independent-audit branches were not merged or modified. The latter reports informed this review.

Before protected frontend edits: d199e00 documents original findings; c31a035 records owner's facts-only PREFIX clarification and explicit main interface/R1-R20 review. Frontend fix 26249a7 is separately reviewable from H1 merge. Harness isolation 6cd6612 is separate again. Final delivery SHA is reported with the pushed branch; no self-referential commit hash is embedded in this document.

## C. Changed-file inventory

Machine-readable full inventory relative to 748 and relative to the audited f928 baseline is in `release-candidate-evidence/changed-files.json` (Git names/status, including documentation/evidence). Production changes since H1 are exclusively frontend. `git diff f9dcf56 -- application recall-engine integration experiments` is empty. Original test files were not edited; new tests/configurations were added. Engine/foundation/integration source provenance verifies 126 files without changes. Source-provenance manifest was not regenerated.

Frontend edits: App; StatusChips; contract gate/views/new ConsoleClaims; RecallDataSource/freshness; QR; Impact projection; FleetBoard, DecisionExplanation, DecisionHistory and Case06Comparison. They do not author verdicts, notifications, trust states or policy. New browser configurations isolate existing assertions from concurrent audits; they do not alter product timeout or trust.

## D. Test evidence and reproduction

Final full-unit result:296 passed/21 failed of317. Full browser replay:119 passed/18 failed of137, no skips; runtime bundle predates bounded F6 HTTP-status delta. Final delta has successful build and11/11 focused browser follow-up. Full137 was not repeated after F6; no exact-final hosted certification is claimed. Generic post-capture confirmation is hidden in PREFIX with the current console: this is a remaining usability gap, not grounds to restore unsafe operational views.

See [complete result/migration matrix](RELEASE_CANDIDATE_TEST_MATRIX.md). Every original and integrated failure is individually listed; raw JSON/transcripts retain assertion detail. PASS is never assigned to a failed suite. No test deletion, deliberate skip, assertion weakening, original H1 regression rewrite or source-fixture edit.

Local Windows: Python 3.12.10, Node 24.17.0, npm 11.13.0; system Chrome 155.0.8059.80 (not hosted pinned .84). `npm ci` preserved lock bytes. Foundation/runtime Python package versions match checked-in locks; PyLD validation dependencies are not product runtime. External GS1 checkout exact 6f71468231838e424bb5dfa836e006e8dc69615c, not vendored.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r experiments/foundation/requirements.lock
# Run from recall-engine, using ../.venv/Scripts/python.exe:
# -m unittest discover -s tests -t . -v
# Run from integration, using ../.venv/Scripts/python.exe:
# -m unittest discover -s integration_tests -t . -v
.venv/Scripts/python.exe -m unittest discover -s application -t . -v
.venv/Scripts/python.exe -m unittest discover -s recall-ui/tests -p test_export_snapshot.py -v
.venv/Scripts/python.exe experiments/foundation/interop.py --gs1-checkout <external-pinned-GS1-checkout>
# interop regenerates its tracked research result; compare and restore only that generated artifact.
cd recall-ui
npm ci
npm test -- --reporter=json
npm run build
npx playwright test --config=playwright.audit.config.ts
npx playwright test --config=playwright.rc.config.ts
```

RC config uses 4340, own adversarial server 4337, existing gate server 4321. One worker serializes unchanged auxiliary 4185 owners. It intentionally cannot satisfy the old assertion hardcoding a 4173 QR URL; this is reported, not fixed by weakening assertions. The default full run correctly refused Claude's occupied 4173; no process was stopped/reused. Temporary-directory ownership gaps from reliability research remain, not a claim of cleanup completion.

For backend probes: use `.venv/Scripts/python.exe docs/release-candidate-evidence/backend_probe.py <disposable-exact-f9-checkout>`; they create only synthetic temporary SQLite archives and loopback servers. No production engine copy or edits. Results are independent reproductions of that pinned implementation, not new backend fixes.

## E/F. Backend dependency blocker matrix

Exact backend source is unchanged from f9. Code locations refer to that implementation and the RC import. Probes/results are in `release-candidate-evidence/backend_probe.py` and `backend-results.json`. Proposed fixes below are NOT implemented or approved into RC.

| ID | Independent evidence / classification | Minimal proposed remediation, separate review | Acceptance requirement |
|---|---|---|---|
| D2 | Confirmed: motor decisions and lot investigation return HTTP200 raw release after extension while whole snapshot is PREFIX; subresources omit checkpoint/eligibility. High integration safety-contract blocker. `server.py:127-139` | Return an authoritative same-snapshot typed envelope on every status-bearing resource, or disable decision-bearing projections until such contract exists. Never synthesize eligibility in client | CURRENT/PREFIX/UNANCHORED/INVALID/VERIFYING endpoint matrix; no raw release can be interpreted as current outside same-transaction state/eligibility; unchanged engine |
| D3 | Confirmed: manifestless legacy EVALUATION then later evidence causes GET400 INVALID_REQUEST. Internal derive_publication accesses prior manifest. Compatibility/availability blocker; not evidence of false release. `audit.py:55,181-183` | Separate historical-only legacy publication from derivation inputs; no invented manifest. Add explicit migration boundary after owner review | Archive rows byte-preserved; historical-only marker; no current clearance from legacy; later capture produces clean typed historical/unavailable result, no KeyError/400 misclassification |
| D4 | Confirmed: root and successor work; third-generation export fails PREFIX_MISMATCH. Checkpoint workflow blocker. `anchors.py:131-141,168-177` | Design full predecessor-chain handling or independently verified compact custody history. Do not accept missing ancestors or simply suppress previous checks | Root plus at least three successors export/activate/restart correctly; wrong, missing, reordered and cross-archive predecessors fail; R1-R20 maintained; independent review |
| D5 | Confirmed subset: evaluator-consistent EVALUATION for an unannounced policy, appended with recomputed chain, passes H2 VERIFIED. Prefix still globally withholds current clearance; do not claim this achieved release. H2 publication-authority concern. Original audit also flags watermark chronology; not newly reproduced here. `audit.py:228-247` | Explicitly bind each publication to authoritative policy/configuration revision and valid recorded evaluation horizon; enforce approved monotonicity/ordering rules | Recomputed-chain policy substitution, unannounced policy, regressed/equal/incomparable horizon cases rejected according to owner-approved semantics; legitimate historical replay retained |
| D6 | Confirmed GET snapshot after external capture changes journal rows 3 -> 5. Backend mutation/read-only contract mismatch. `service.py:240,314-318`; `audit.py:171-190` | Move publication to explicit ingestion/evaluation transaction or approved coordinator; GET only reads verified published state | Repeated and first post-capture GETs leave ledger/journal/obligations/anchor unchanged; pending evaluation withholds status; ingestion-to-publication ordering atomic |
| D7 | Confirmed D3 server fault classified INVALID_REQUEST400; sanitized text does not leak internals. Availability/integrity diagnostics concern. `server.py:141-147` | Typed domain error classification for malformed request vs stored historical/integrity/availability failures | Correct neutral structured codes/status; SQL, payload, host path and raw exceptions absent; failed proof never becomes usable data |
| D8 | Confirmed: successor skipping a known intermediate but linking older supplied anchor can be CURRENT. Owner-custody/equivocation limitation; not automatically an in-model cryptographic bypass. `anchors.py:168-177` | Owner must decide authoritative latest-head custody/revocation/monotonic trust-history contract; separate design review | Reject known stale predecessor when custody history establishes a newer checkpoint; document what restart cannot detect with only an older externally supplied anchor. Preserve exact-checkpoint rollback residual |
| D9 | Confirmed: post-checkpoint historical OBLIGATION_RESOLVED causes409 RESOLUTION_FORBIDDEN. Original checkpoint-export test also fails. Owner explicitly chose historical-only archives pending migration approval | Read-only quarantined archive/report workflow after approved migration design; never reinterpret old claims as authenticated resolution | Original rows immutable; no current authorization; forged resolution still rejected; no export/activation laundering; notification obligations preserved |
| D10 | Confirmed source gap: H1 main globally hides normal views when any release is withheld. Bounded CURRENT frontend correction included; PREFIX behavior is now owner's facts-only contract. Large-archive availability remains unresolved | Independent review of new per-motor main claims; separately review replay/cache/index/deadline optimization without shortcutting verification | Mixed CURRENT hold/excluded-withheld/cleared motors retain independent views. Hidden/expired/invalid drop records. Large workload must yield usable verified responses or truthful 503, never timeout inflation |

D1 standalone legacy-gate bypass is addressed by upstream branded frontend plus these stricter malformed-envelope checks and main convergence; this does not resolve D2-D10. No backend fixes have been smuggled into the RC. No new backend-remediation branch was necessary because this deliverable contains proposals only; any implementation must be separately branched, approved and independently reviewed before inclusion.

## G. Original-test migration boundary

Per-failure matrix records old assertions, approved conflict, new expected behavior and replacement safety proof. No original tests were migrated in this delivery. Existing red tests remain visible, so this candidate cannot satisfy release gates. Typed error-category migrations must continue asserting rejection; complete CURRENT envelopes are required for positive-path tests. Privacy migrations must test equality-preserving pseudonyms without resurrecting operator IDs. PREFIX positives test historical facts with no decisions; CURRENT tests preserve hold/finding without implying clearance. Historical resolution needs explicit owner migration authorization, not a changed test expectation disguised as repair. Additive backend-current-contract.test.ts proves complete CURRENT token handling, latest-request ordering, typed expired-lease rejection and body-read timeout without altering the originals.

Reliability reference: 6d177e8113b73212d7d39faf3208868c119d50f4, `docs/PHASE31_RELIABILITY_AUDIT.md`. Its unchanged original snapshot-equality test naturally failed 11/30 observed comparisons, all differences only verifiedAt; forced boundary5/5; test-only clock control10/10 passed. These are attributed prior measurements, not this run's counts. Current application run had the historical-resolution error and no verifiedAt failure. No production clock or source fixture was changed here. Test-owned resource cleanup recommendations remain separately reviewable.

## H. CI update proposal (not implementation)

[Read-only inventory comparison](release-candidate-evidence/ci-inventory-comparison.json): CI04 froze196 files at f928; all196 canonical baseline hashes match. Current candidate changes18 frozen paths and adds88 non-document paths outside its approved inventory. Detailed names are in JSON. This comparison is NOT a replacement manifest and does not change the old one. Backend changes are solely the explicitly imported H1 candidate. New feature trees, QR dependency, public sanitization, four Vite entries, gate/brand modules, H1 tests and new audit tests/configurations must receive explicit review.

Required future reviewed workflow changes:

1. Resolve backend blockers and approve all historical/test contract migrations before updating a frozen inventory. Hash only the exact independently reviewed future source tree; preserve source-provenance126 and original fixture/oracle pins. Never allow blanket unpinned paths merely to pass.
2. Retain Python3.12.10, Node24.17.0, npm11.13.0, Chrome-for-Testing155.0.8059.84 archive SHA, GS1 commit/file hashes, npm integrity checks and pinned Actions SHAs. Hosted browser verification must use that binary, not this machine's .80.
3. Approve locked uqr0.1.3 (production, installed LICENSE/package metadata: MIT, Project Nayuki and Anthony Fu copyright) and jsqr1.4.0 (test, installed LICENSE/package metadata: Apache-2.0), plus existing React/Vite closure; verify lock integrity and license/notice obligations. The minified JS attribution scan did not find the uqr copyright names; review a distribution notice bundle before publishing. No Java upstream dependencies introduced.
4. Gate all four HTML builds and preview sanitization/export checks, original/adversarial/unit/browser suites; use structured result counts and zero unexpected skip/missing suite checks plus process exit. Keep exact counts only after reviewed migrations, never reinterpret this run's21 unit failures as PASS. Engine127/integration44/foundation21/exporter7 remain. Application requires all59, including23 checkpoint cases, with historical conflict unresolved. Frontend317 currently executed; browser137 under isolated config. Future migrations may add tests, so counts must be explicitly recomputed/reviewed.
5. Reserve disjoint host ports and separate databases/custody files, fail if occupied, no server reuse. Current default4173 belongs to another audit; H1/Passport4185 collision must be resolved by reviewed test harness isolation. Serialize until distinct owned ports are approved. Dedicated4321 and4337 gate servers, RC4340, other auxiliaries4182-4197. Cleanup only test-owned resources and wait for exit.
6. Preserve fail-closed A-K aggregate with always-run summary, no continue-on-error or skipped drafts. Upload original failures, provenance/inventory verification, browser traces, sanitized metadata and build/evidence hashes bound to exact tested commit/run ID. Retain pre/post source checks and standards validation. Add backend endpoint-state, chain-generation and publication-authority adversarial gates when fixes are independently approved.
7. Run hosted CI against the exact future reviewed integration SHA. Hosted green run39736296447 verifies only CI04; it does not verify this RC. No hosted-green status is claimed here. No CI workflow/inventory edits were imported.

## I. Performance and availability

Original exact748 browser run:125 tests,332.586 seconds on shared developer machine. Large synthetic graph reports4435ms to first bounded window,156 nodes drawn; original15-second graph assertion passed. This is a UI synthetic projection, not evaluator throughput or full unbounded graph completeness.

New isolated browser current-envelope mobile first-navigation-to-visible-record samples: main263.3ms; Passport200.3ms; Investigation229.0ms; Impact list249.9ms. One sample per page; captured synthetic five-motor/58-event response, local Chrome, shared Windows hardware. Includes network/load/validation/render observation as a whole; not separately instrumented stages, not p95 and not backend capture-to-decision latency. Attachments in audit-browser.json preserve exact measurements. No inference about production or 100-motor replay performance.

H1 R18 prior artifact `docs/h1-h2-validation/R18-measured.json`:100 motors/1000 journal entries,12/12 HTTP503VERIFYING,zero successful snapshots,successful p95 undefined; activation25.04s. Claude independent audit e63 reports separate activation37.9s and similarly503-only behavior. Those are attributed previous measurements on exact f9, not fresh throughput tests here. Backend bytes unchanged. This is fail-closed availability failure, not success. Four-second operational client timeout was not raised.

Additional new actual-backend measurement (disposable exact f9, five seeded motors/58 events): server activation169.1ms; five serial HTTP200 ANCHORED_CURRENT snapshots226.6-413.3ms. An actual untrusted observation capture took21.4ms; next HTTP200 snapshot503.0ms, ANCHORED_PREFIX_ONLY, currentReleaseEligible false. This demonstrates truthful withholding after a write, not a covering checkpoint or release workflow. `latency_probe.py` and `latency-results.json` record methodology/results. It is not a browser-visible or production p95 measurement.

Synthetic safety reporting: these challenges observed no unauthorized current clearance in their asserted cases. They do not estimate a population false-release rate. Unnecessary holds were not scored against an independently authored synthetic oracle in this frontend audit; fail-closed PREFIX/invalid/unknown states are not counted as unnecessary holds. The unchanged evaluator/oracle regressions pass, but no new safety certification is inferred from them.

## J/K. Decision and owner-review sequence

**REVISE / blocked.** Bounded frontend repairs and coherent shared presentation are reviewable. Unresolved H1/H2 policy authority, endpoint envelopes, historical compatibility, checkpoint chaining, GET mutation and large-archive availability prevent safety/readiness approval. Known original test failures and unreviewed inventory changes also prevent release certification.

1. Review preserved original failures and independent frontend fixes/semantic proposal; have an independent reviewer audit protected main interface and per-motor/historical claims.
2. Claude completes backend audit; owner approves precise separate remediation boundaries and migration semantics. No own-code self-certification.
3. Implement/review D2-D10 remediation only in separate branches, then explicitly approve exact pinned imports. Re-run R1-R20 plus endpoint/chain/policy/read-only/availability regressions and historical replay without mutating originals.
4. Approve original-test migrations and owned-port cleanup; require original unsafe behaviors to remain prohibited by additive regressions.
5. Approve a new exact CI inventory and counts, run pinned hosted A-K on the future reviewed SHA, inspect all evidence. Only then consider a PR/merge under separate owner authorization.

Stop for owner review. Branch/SHA and remote verification accompany delivery. Main/original branches have not been rewritten, merged into, deleted or force-pushed. No deployment or PR.
