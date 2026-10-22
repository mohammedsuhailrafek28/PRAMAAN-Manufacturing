# H1/H2 Option A — Independent Safety Audit Report

Reviewer role: read-only auditor (no fixes implemented). All probes ran on disposable databases/worktrees.
Evidence scripts and raw outputs: `docs/h1-h2-independent-audit/`.

## 1. Audited SHA

`fix/phase31-h1-h2-checkpoint-closure @ f9dcf56ae52b095a3af05b8fc45a2568cd5642fe` (parent e9da7c4 spec commit; baseline f9282101159b6b6806974848d7c351999098d792). Review branch `review/h1-h2-independent-audit` derives from that SHA. CI branch `infra/phase31-ci-gates@04d974f` was not re-audited.

## 2. Source-diff inventory (f928210..f9dcf56, 16 files)

| Area | Files |
|---|---|
| Backend | `application/anchors.py` (+216), `audit.py` (+218), `checkpoint_benchmark.py` (new), `server.py`, `service.py`, `test_checkpoints.py` (new, 23 tests) |
| Docs | approved spec, audit handoff, `h1-h2-validation/R18-measured.json`, `summary.json` |
| UI | `App.tsx` (+8, `withheld` panel), `data/RecallDataSource.ts` (+1, strict `accept`), `data/freshness.ts` (+14), `domain/types.ts` (+2), `tests/unit/checkpoint.test.ts` (4), `tests/e2e/checkpoint.spec.ts` (1) |

Evaluator (`recall-engine/`), integration, foundation, ledger and original tests are untouched.

## 3. R1–R20 assessment

Method: independent scripts (`adversarial_audit.py`) using the real modules; "observed" is measured, not read from Codex's report.

| R | Scenario (setup) | Expected | Observed | Result |
|---|---|---|---|---|
| R1 | In-process rollback to exact-checkpoint state after a verified extension | ROLLBACK_DETECTED | `ROLLBACK_DETECTED`; also over live HTTP (X10): 200 CURRENT → 200 PREFIX_ONLY → 409 ROLLBACK_DETECTED | PASS |
| R1b | In-process rollback to an intermediate head | ROLLBACK_DETECTED | `ROLLBACK_DETECTED` | PASS |
| R2 | Restart, newest checkpoint, older archive | PREFIX_MISMATCH | `PREFIX_MISMATCH` | PASS |
| R3 | After restart, older checkpoint, intermediate archive | PREFIX_ONLY, no eligibility | PREFIX_ONLY, all eligibility false | PASS |
| R4 | After restart, archive rolled back to exactly the checkpoint | CURRENT (declared undetectable residual) | CURRENT | PASS as documented residual (not a detection claim) |
| R5 | Legitimate capture after checkpoint | PREFIX_ONLY, eligibility withheld for all motors, holds shown, checkpoint required | exactly that; raw decision for held motor `RECALL_HOLD` | PASS |
| R6/R7 | Forged EVALUATION (decision-only, raw+decision, version bump) with recomputed hash chain | EXTENSION_INVALID | `EXTENSION_INVALID` ×3 | PASS |
| R8 | Orphan OBLIGATION_CREATED | EXTENSION_INVALID | `EXTENSION_INVALID` | PASS |
| R9 | OBLIGATION_RESOLVED in extension | RESOLUTION_FORBIDDEN | `RESOLUTION_FORBIDDEN` | PASS |
| — | Unknown journal kind | EXTENSION_INVALID | `EXTENSION_INVALID` | PASS |
| R10 | Event appended, not evaluated | PREFIX_ONLY | PREFIX_ONLY | PASS |
| R11 | v1 checkpoint over a fully current archive | never CURRENT | PREFIX_ONLY | PASS |
| R12–R14, R17, R20 | Covered by Codex's `test_checkpoints.py` (all 23 pass in my run); I did not find a contradiction, but did not build separate reproductions for each | — | — | PARTIAL (not independently re-derived) |
| R15 | Successor without / correct / wrong previous | PREFIX_MISMATCH / CURRENT / PREFIX_MISMATCH | as expected | PASS (one hop only; see D4) |
| R16 | Legacy manifest-less row mid-journal | degrade to HISTORICAL_UNVERIFIABLE | H2 status `HISTORICAL_UNVERIFIABLE`, but the service then crashes when it has to publish again (see D3) | PARTIAL / FAIL (availability) |
| R18 | 100 motors / 1000 journal entries, p95 <1.5 s | no 503 | 12/12 HTTP 503 VERIFYING (1.80–2.17 s); activation verification 37.9 s (Codex measured 25.0 s) | FAIL (see §6) |
| R19 | Checkpoint before policy exists, policy added later | PREFIX_ONLY | PREFIX_ONLY | PASS |

Additional attack probes (all in-model unless noted):

- Warm-cache mutation matrix under a fixed trusted checkpoint (append event, new motor, new announcement, edit `captures.received`, edit `app_units.title`, equal-length ledger-row edit, rehashed journal truncation): none yields CURRENT (PREFIX_ONLY or ROLLBACK_DETECTED). Editing the unbound `app_clock` leaves CURRENT (it is not in `ledger_binding`; benign, but noted).
- 111 checkpoint-field mutations with recomputed checksums: CURRENT only for the three mutants that are no-ops (root `previousCheckpointHash=None`; dropping the last row of the two empty tables). No crash, only fixed codes.
- Independent writer process while the server polls: withdrawal is monotonic (CURRENT ×9 → PREFIX_ONLY, never back).
- Startup with truncated/empty/non-JSON/other-archive/missing checkpoint: refuses to start, fixed codes only.
- Corrupted/substituted archive id at runtime → 409 with fixed code, no path/SQL leakage in any response.

## 4. Confirmed safety defects (with repro)

None found that grants a false CURRENT / release eligibility inside the approved attack model on the main app. The following are confirmed defects of weaker severity, ordered by importance.

**D1 (Medium–High, cross-page safety) Standalone pages do not enforce the strict contract.**
`freshness.ts` now accepts `VERIFIED_PREFIX_SYNTHETIC` and only validates checkpoint/eligibility `if (snap.checkpoint)`; the `!snap.checkpoint || !snap.eligibility` rejection lives only in `BackendRecallDataSource.accept`. The Passport/Investigation/Impact adapters bypass `accept`.
Repro (scratch merge be1fab6, `docs/h1-h2-independent-audit/xprobe.spec.ts.txt`): seeded server, write a capture for MTR-26001 → `ANCHORED_PREFIX_ONLY`, eligibility false for all, `/api/snapshot` still reports MTR-26003 `RELEASE_ELIGIBLE`. Main fleet shows the withheld banner; the Passport page renders the "Excluded with evidence" chip for MTR-26003 with no non-current banner at all, and Impact/Investigation likewise show no banner. A legacy snapshot with `VERIFIED_ANCHORED_SYNTHETIC` and no checkpoint/eligibility is also accepted by `verifyFreshness`.

**D2 (Medium, API) Sub-resource endpoints carry no checkpoint/eligibility state.**
Repro: after the same write, `GET /api/motors/MTR-AAA2/decisions` and `GET /api/lots/BR-310/investigation` return 200 with `RELEASE_ELIGIBLE` and no `checkpoint`/`eligibility`/`currentReleaseEligible` key (only a generic `state`). A client that does not call `/api/snapshot` cannot tell the answer is not current. (UI omission is not API access control.)

**D3 (Medium, availability/classification) Legacy manifest-less EVALUATION row followed by any new evidence bricks the app.**
Repro: append a manifest-less EVALUATION (the legacy shape), then record a new capture and call `/api/snapshot` → HTTP 400 `INVALID_REQUEST` (underlying `KeyError: 'manifest'` in `derive_publication`, `prior[-1]['manifest']`). H2 itself degrades correctly to HISTORICAL_UNVERIFIABLE; the publication path does not. Server-side integrity faults are also mapped to 400 (client error).

**D4 (Medium, functional) Checkpoint chain cannot extend past two links.**
`export_anchor(app, previous)` calls `verify_anchor(app, previous)` with no previous of its own, so a non-root `previous` raises `PREFIX_MISMATCH`. A third-generation checkpoint can therefore never be exported. Consequence: after one successor, no further checkpoint can be created through the supported path; operators are pushed to re-root, which is a custody action with no chain.

**D5 (Low) H2 does not enforce per-motor watermark monotonicity or bind `policy` to `recall_announcements`.**
Repro (X1/X2): a derivation-consistent EVALUATION for an older watermark, or for a never-announced policy, appended with a valid chain is accepted by `verify_publications` (VERIFIED). It cannot create eligibility (journal sequence changes → PREFIX_ONLY, and `decide` re-derives at the current watermark), but it can inject spurious history/obligations. Within the declared model only a host-level journal writer can do this.

**D6 (Low) Write-on-read.** `GET /api/snapshot` appends journal entries (journal 3 → 5 on an evidence-extended archive); the `export` CLI runs `snapshot()` first. Failures roll back, but a GET with side effects complicates replication and audit.

**D7 (Low) Error conflation.** `verify_anchor` maps every unexpected exception to `PREFIX_MISMATCH`; `verify_publications` maps generic exceptions to `EXTENSION_INVALID`; the server returns 409 `ANCHOR_INVALID` for any non-VERIFYING `LedgerBlocked`. An internal fault is reported as an integrity verdict. Responses are sanitised (no leakage observed).

**D8 (Low) No equivocation detection.** Skip-link successors are accepted (X3: a successor that skips `s1` verifies CURRENT against the root). This is a custody/out-of-band concern; recommend documenting it as residual.

**D9 (Low) Historical `OBLIGATION_RESOLVED` anywhere in the journal makes the whole app 409** (not only export). The owner clarified these archives are historical-only; the implementation blocks everything rather than degrading.

**D10 (UX/availability) Global withholding.** Any prefix-only state, or any RELEASE_ELIGIBLE decision whose eligibility is false, replaces all main views with the "withheld" panel; evidence detail is inaccessible until a new checkpoint and restart.

## 5. Test-compatibility findings (1 Python + 3 Vitest + 4 browser failures)

| Failure | Class | Rationale / safe resolution |
|---|---|---|
| `test_hardening.AnchorTests.test_historical_resolution_entries_are_not_rewritten` (`RESOLUTION_FORBIDDEN`) | A | Owner-clarified: historical resolutions are export-blocked pending a separately approved migration. Keep the original; add a new test for the approved behaviour. |
| Vitest `backend-source` ×3 (valid mutation snapshot; stale replay expects `/expired/`; late older concurrent request) | A | Legacy mocked envelopes lack `checkpoint`/`eligibility`; the strict metadata error now fires first. I did not run migrated copies; the safe resolution is to add the two fields to the fixtures in new tests and keep the original assertions. |
| hardening.spec "external capture writer withdraws displayed exclusion" | A | Expects the chip after a prefix extension; strict R5 withholds it. Update only with owner approval. |
| live.spec "live manufacturing capture, genealogy, recall, replacement and late withdrawal" | A/D | Multi-command flow; workbench is disabled unless ANCHORED_CURRENT, so after the first write further commands cannot be driven. Needs a restart-with-new-checkpoint step or an owner decision on workflow. |
| remediation.spec "live long identifiers" | A (shared state) | Shared seeded server is pushed to prefix-only by earlier writes → order dependence. |
| remediation.spec "NDE-only affected motor" | A | `--empty` server is PREFIX_ONLY after the first POST; REST commands succeed, chips are withheld. |

No failure classified B (product regression) or C (new weakness); D1 shows the UI contract is nevertheless inconsistent across pages. Assertions must not be weakened.

## 6. Performance diagnosis (R18)

Reproduced: 12/12 requests returned 503 VERIFYING at 100 motors / 1000 journal entries. Warm cost is the problem, not only cold replay:

- COLD `TrustedAnchor.verify` 26.7 s (H2 evaluator replay), `export_anchor` 29.7 s.
- WARM verify ≈ 1.06 s even fully cached (above the 1.25 s deadline once combined with the rest of the request): `ledger_binding` is computed twice (≈0.3 s each), `verify_publications` content key ≈0.3 s, prefix key ≈0.3 s, `journal_bytes_key` 0.12 s, dominated by RFC 8785 canonicalisation of ≈7,200 digests.
- A full warm request ≈ 10 s: open ≈2.1 s, verify ≈1.2 s, `_snapshot` ≈6.5 s (`ledger.snapshot` ×400 at ≈38 ms; `decide` ×100 ≈110 ms each, re-evaluating the engine before checking input identity). Much of this is pre-existing O(motors) work, so <1.5 s is infeasible without reducing baseline per-poll work.
- The replay cache key hashes the full table content, so any append resets progress and forces a full cold replay; incremental progress is useless across appends. Hashing steps lack deadline checks (overshoot to ≈2 s).
- 503 responses are correctly not counted as throughput.

Safe optimisations (full replay preserved): compute `ledger_binding` once per verify; cheaper whole-content fingerprint as the cache key (sha256 of DB+WAL bytes ≈33 ms for 21 MB); per-entry memoised H2 results keyed by content-addressed inputs so only new entries run the evaluator; in `decide` compute identity first and reuse the verified prior entry; reuse per-motor `ledger.snapshot`; deadline checks inside hashing; accept one-time cold activation verification before listening.

## 7. Remediation recommendations

1. One shared strict gate (checkpoint + eligibility mandatory, state-aware banner) used by every adapter and page, enforced in `verifyFreshness`/`validateSnapshot`, not only in `BackendRecallDataSource.accept`.
2. Add `checkpoint`/`eligibility` to every API that returns decisions, or withhold RELEASE_ELIGIBLE there when not CURRENT.
3. Fix the legacy-row publication path (D3) so it degrades to HISTORICAL_UNVERIFIABLE; map server integrity faults to typed 5xx/409, not 400.
4. Make `export_anchor` accept an arbitrary-depth chain (or verify previous against its own predecessor) (D4).
5. Optionally add watermark-monotonicity and policy-binding checks to H2 (D5).
6. Typed error codes instead of catch-all mappings (D7); consider moving issuance off GET (D6).
7. Performance changes listed in §6 before any R18 claim.
8. Owner-approved migration for historical OBLIGATION_RESOLVED archives and the 8 legacy tests.
9. Reduce global UI withholding (D10) to hold lists plus evidence detail, if the owner agrees.

## 8. Remaining attack-model limitations

- Declared residual (out of model): R4 exact-checkpoint rollback after restart; checkpoint custody and equivocation (D8); host-level writers with SQLite file access who can also replace the checkpoint; the unbound `app_clock`/`app_audit_head` tables; process-local high-water mark.
- In-model gaps found: D1, D2, D3, D4 (availability/consistency, none a false CURRENT); D5 is in-model only for a journal writer.

## 9. Verdict

**REVISE.** The core H1/H2 mechanism holds against everything I tried: no path to a false CURRENT or false release eligibility on the main app inside the approved model, and R1–R11, R15, R19 reproduce as specified. However R18 fails (systematic 503 at the target scale), and integrating with the standalone Passport/Investigation/Impact pages is **NO-GO** until D1 and D2 are closed, because those surfaces can present prefix-only data without any non-current signal.

## 10. Prioritised, bounded plan for Codex

1. (Blocker) D1 + D2: shared strict gate and state on all decision-bearing endpoints; add tests that run the standalone adapters against PREFIX_ONLY and legacy-status snapshots.
2. (Blocker) R18: items from §6 in the order `ledger_binding` once → cheap cache key → per-entry H2 memo → `decide` identity-first; re-measure with 503s excluded from throughput.
3. D3 + D7: legacy-row degrade path and typed errors.
4. D4: depth-N chains.
5. Owner decisions: migration of historical resolutions and the 8 legacy tests; whether to reduce global withholding; whether D5 hardening is wanted.

Stop here for owner approval; nothing has been merged, pushed, or deployed.
