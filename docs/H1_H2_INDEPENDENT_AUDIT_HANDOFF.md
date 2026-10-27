# H1/H2 Option A independent safety review handoff

Status: **REVISE — not safety closure, not ready to merge.** This review candidate deliberately does not turn failing historical acceptance criteria into PASS. No original regression test, evaluator, foundation adapter or integration ledger was edited. No merge, deployment or PR was performed.

## Provenance and separate CI work

Parent: audited A31 `f9282101159b6b6806974848d7c351999098d792`. Branch: `fix/phase31-h1-h2-checkpoint-closure`. The recovered October 21 Claude design and owner approval were preserved before implementation in `e9da7c4b164003bc287c3c65c4a3dde45bd7136c`, in [the authoritative specification](H1_H2_APPROVED_OPTION_A_SPEC.md). October 22 owner clarifications define R3 after restart and retain resolution-bearing archives as historical-only pending approved migration.

CI is separately reviewable at `infra/phase31-ci-gates@04d974fd6307fca1f129be6b5683f4468b5fcad7`. [Failed hosted run 39735037203](https://github.com/mohammedsuhailrafek28/PRAMAAN-Manufacturing/actions/runs/39735037203) failed its Vitest count parser on ANSI formatting, despite 33 passing tests and exit zero. The correction strips terminal control sequences only for count parsing; raw logs, exit checks, count assertions and source pins remain enforced. [Hosted retry 39736296447](https://github.com/mohammedsuhailrafek28/PRAMAAN-Manufacturing/actions/runs/39736296447) succeeded on that exact correction, including all A–K gates. That green run is **not** hosted verification of this H1/H2 branch. CI triage is documented independently in that branch's `docs/CI_TRIAGE_39735037203.md`.

## Implemented review boundaries

- `application/anchors.py`: candidate v2 commits actual ledger row digests, per-source last sequence/hash, journal prefix, archive, policy/profile/verifier/engine identity, predecessor checkpoint hash. Verification uses a consistent SQLite cut. Process-local high-water checking rejects regressions. A v1 checkpoint proves at most a prefix. Successor activation requires the supplied previous checkpoint. File bytes are pinned for the process, with no hot-swap or HTTP promotion.
- `application/audit.py`: pure A31 publication derivation shared by issuance and H2. H2 recomputes the recorded-watermark manifest, config/policy context, pinned v3 raw output and entire derived publication. Canonical digest comparison distinguishes booleans from integers. It checks version progression and adjacent obligation/evaluation pairing; unknown kinds, orphan obligations and resolutions fail closed. Legacy rows without manifests cannot establish current clearance. Replay progress is in memory and keyed by actual ledger/journal bytes plus verifier/profile/engine identity, rather than claimed head hashes.
- `application/service.py`: consistent issuance/read transaction; current eligibility is separate from immutable issued decisions. Every applicable publication must be current under the trusted checkpoint, H2-verified, and free of pending obligations. Prefix extensions globally withhold current eligibility. Unanchored envelopes carry no verification timestamp or lease.
- `application/server.py`: predecessor configuration; sanitized fixed errors; HTTP 503 `VERIFYING` carries `decisionsUnavailable: true`. The existing browser timeout remains four seconds.
- UI: live sources require strict state and eligibility metadata; prefix-only views show the checkpoint warning, holds, evidence reasons and pending obligations without release chips. Recorded exclusions remain historical. An excluded raw publication with a pending obligation cannot appear as current clearance. Fixture mode remains explicitly separate.
- `application/test_checkpoints.py`: disposable adversarial archives, rewritten hash-chain attacks, rollback, consistent export, partial-file failure, error sanitization and owner-approved historical compatibility behavior.
- `application/checkpoint_benchmark.py`: 100 synthetic motors and exactly 1,000 valid journal entries; actual evaluator issuance and real loopback HTTP requests. No synthetic truth enters the evaluator.

No new trust source is invented. Supplying `--trusted-anchor` remains an explicit operator assertion of independently established custody. The software cannot establish custody merely by reading a local file.

## Regression matrix

| Original case | Verification / result |
|---|---|
| R1 | In-process rollback after a held extension: `ROLLBACK_DETECTED`, invalid, no clearance. |
| R2 | Restart with a newer checkpoint against an older archive: `PREFIX_MISMATCH`. |
| R3 | Owner-confirmed restart with older checkpoint and intermediate archive: prefix-only. The same intermediate rollback in-process is invalid. |
| R4 | Exact trusted checkpoint restored after restart: current; intentionally **undetectable** rollback residual. |
| R5 | Legitimate capture: prefix-only globally; holds and checkpoint warning visible. Real browser coverage included. |
| R6 | Rewrite the newly issued evaluation to a release and recompute the journal chain: `EXTENSION_INVALID`. |
| R7 | Rewrite derived fields while retaining raw output and recompute the journal chain: `EXTENSION_INVALID`. |
| R8 | Orphan obligation: `EXTENSION_INVALID`. |
| R9 | Post-checkpoint resolution: `RESOLUTION_FORBIDDEN`. |
| R10 | Unevaluated captured event: prefix-only. |
| R11 | V1 checkpoint: prefix-only, never current. |
| R12 | Independent SQLite writer races export; resulting candidate verifies as current or a valid prefix. |
| R13 | Partial-write and fsync failures publish no checkpoint; existing files cannot be overwritten; staging files cleaned. |
| R14 | Local candidate creation leaves the application unanchored and current eligibility false. |
| R15 | Successor missing or contradicting explicit previous checkpoint: `PREFIX_MISMATCH`. |
| R16 | Evaluation without a manifest: `HISTORICAL_UNVERIFIABLE`, never current. |
| R17 | Sanitized constructor, HTTP integrity/availability/unexpected errors and CLI boundary; no raw SQL/path/payload response. |
| R18 | 12/12 HTTP 503 `VERIFYING`, eligibility withheld; fallback only, zero successful snapshots. See measured availability limitations below. |
| R19 | Policy added after an empty checkpoint: prefix-only. |
| R20 | Engine/integration/foundation remain 127/44/21 passing. Original application/UI acceptance is **not all green**, as detailed below. |

## Test results and unresolved compatibility

The final result inventory is recorded alongside this document. Original test files remain unchanged.

- Actual evaluator suite: 127 passed (includes original semantics/replay regressions).
- Integration: 44 passed. Foundation: 21/21 passed against the pinned GS1 checkout. Exporter: 7 passed.
- New checkpoint suite: 23 passed. Combined Python application/hardening/checkpoint run: 58 passed, 1 error across 59 tests (the unchanged historical-resolution acceptance conflict below). New UI checkpoint checks: 4 passed. New real-browser strict checkpoint scenario: 1 passed. Production TypeScript/build passed.
- Original Vitest: 30 passed, 3 failed. With the four new checks: 34 passed, 3 failed. `passes the local token...` and `late older concurrent request...` fabricate legacy response envelopes without the now-mandatory checkpoint/eligibility contract. `rejects a successful stale replay...` still rejects, but the expected `/expired/` reason is preempted by missing strict metadata. These failures cannot be called an unchanged baseline PASS.
- Original browser suite: 25 passed, 4 failed, zero skipped. `external capture writer withdraws...` expects a normal action chip after a prefix extension; strict mode shows holds in its withheld panel instead. `live manufacturing capture...` and `live long identifiers...` expect multi-command operation/current views without independently activating a covering checkpoint. `NDE-only affected motor...` likewise expects a normal finding chip after post-checkpoint writes. The new browser test separately verifies the real hold, notification and globally withheld eligibility.
- Original hardening test `test_historical_resolution_entries_are_not_rewritten` expects export to succeed over a historical resolution claim. The owner's explicit clarification now requires that export to remain blocked pending migration. Its original assertion is preserved and remains an expected reported **failure**, not silently skipped or rewritten. The new owner-clarification regression proves no historical bytes are rewritten and no candidate is exported.
- The original snapshot-idempotence test exposed changing wall-clock verification metadata on an unanchored envelope. Unanchored envelopes now truthfully carry an empty verification timestamp, resolving that failure without altering the test. Missing-file exceptions retain their public `FileNotFoundError` contract through a sanitized subtype.

## Performance evidence

Performance verification is tracked separately from functional passing tests. Dataset construction and checkpoint export are outside query timing. Requests include opening the application, actual-content integrity fingerprints, H2 verification/progress, projection and HTTP serialization. Explicit protected-checkpoint activation performs full verification before accepting HTTP traffic; its cold verification cost is measured separately as `activationVerificationMs`. This is not a claim that cold process startup takes less than 1.5 seconds. Report successful-response p95 separately from unavailable responses. A 503 is an availability fallback with eligibility withheld, not a successful recall decision or proof of adequate throughput. The four-second UI timeout was not increased.

The first large HTTP benchmark failed with a four-second client timeout. Structural journal checks and duplicate prefix-manifest verification were running before bounded H2 work. The revised path reuses only a structural proof keyed by **actual serialized journal/head/legacy bytes**, parses actual current payloads, and keeps H2 evidence verification separate. The trusted-prefix cache similarly hashes actual prefix rows and the full checkpoint body. Unchanged-content polls reuse a proof within their consistent request transaction; newly issued publications require a new cut verification. Duplicate manifest replay was moved to the complete H2 verifier, not discarded. A regression warms both caches, rewrites a publication with a valid hash chain and verifies rejection. The preliminary timed-out runs are failures, not successful samples excluded from a passing percentile.

The large archive was generated solely through actual application/evaluator calls. The initial generator was interrupted after copying a consistent, self-generated synthetic archive; the resumable generator then completed the remaining genuine publications to exactly 1,000 rows. No journal rows or verdicts were manufactured for the benchmark. This archive is under ignored `.local/` and is not committed. Original slow construction is an additional maintenance/performance concern, separate from HTTP timing.

Measured result: 100 motors, exactly 1,000 journal rows; 12/12 responses were HTTP 503 `VERIFYING` with `decisionsUnavailable: true`. Successful snapshots: **zero**. Successful-response p95: **undefined**, not zero and not a claimed sub-1.5-second result. Response times ranged **1,694.596–2,925.392 ms**. Full protected-checkpoint activation verification took **25,039.617 ms**, outside HTTP timing. The unchanged four-second client timeout did not fire in this final run. This satisfies only R18's explicitly permitted fail-closed fallback, and is inadequate application availability. Shared Windows developer hardware was concurrently running regression jobs; this is neither an isolated benchmark nor production capacity certification. The recorded raw artifact's early `acceptance: PASS` means fallback permitted; the runner now labels this situation `SAFE_503_FALLBACK_ONLY` to avoid a throughput claim. No timing sample was removed or altered.

## Independent-audit priorities and remaining work

1. Independently audit derivation parity, cache invalidation, transaction scope, predecessor chaining, high-water state and deadline handling. Passing synthetic tests are not an independent safety audit.
2. Resolve R20's explicitly conflicting legacy tests through an owner-approved contract/test migration. Do not weaken strict gating or merely reclassify red tests as green. Historical resolution migration requires separate explicit approval.
3. Review large-dataset availability, memory use and cold verification progress. Whole-content cache keys intentionally retain integrity work; they are not an authenticated persistent cache.
4. Strengthen adversarial coverage beyond the named examples: exhaustive per-field derivation corruption, longer checkpoint chains, crash/power-loss semantics and concurrent independent processes. No claim of exhaustive OS-level durability testing is made.
5. Review UI's conservative withholding of normal detailed action views when a recorded exclusion conflicts with pending obligations. Other motors can have individually true backend eligibility while the conservative review panel is displayed. No outcomes or evidence are fabricated.
6. CI integration/inventory evolution for this branch has not been approved or performed. The CI branch retains its frozen source inventory and assertions; its hosted PASS does not clear this candidate.

## Operator reproduction (local synthetic data only)

Install the pinned Python dependencies from `experiments/foundation/requirements.txt`; run `npm ci` in `recall-ui`. Tests: `python -m unittest application.test_checkpoints -v`; `npm run build`; `npx vitest run tests/unit/checkpoint.test.ts`; `npx playwright test checkpoint.spec.ts`. The Playwright configuration uses a test-only custody bootstrap, not production trust establishment.

`python -m application.anchors export --database <existing-db> --anchor <new-candidate>` publishes a candidate only. A successor export additionally supplies `--previous-anchor <protected-prior>`. Independent owner review and protection happen outside the mutable host. Stop and restart the application with `python -m application.server --database <db> --trusted-anchor <protected-current> --previous-anchor <protected-prior>` for a successor (omit previous only for a root). There is no HTTP activation or implicit file replacement. A legitimate subsequent capture withholds clearance until a covering checkpoint is independently accepted and explicitly activated in a new process.

Run `python -m application.checkpoint_benchmark` for the synthetic large-archive exercise. This is a research/regression workload, not production load certification.

## Mandatory residual limitations

Exact latest-checkpoint rollback after restart can be undetectable. Host/custody compromise and forged evidence together with forged decisions are outside the stated protection. Local freshness is bounded and is not cryptographic authentication. Locally written candidates are never automatically trusted. No general authenticated notification resolution or historical migration workflow is implemented.

**Recommendation: REVISE.** Keep both branches separate, do not merge, deploy or create a PR. Independent safety re-audit and resolution of the red compatibility/performance evidence are mandatory before claiming H1/H2 closure.
