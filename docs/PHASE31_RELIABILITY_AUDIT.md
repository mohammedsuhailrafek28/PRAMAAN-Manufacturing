# Phase 3.1 reliability investigation — owner review

**Scope:** test reproducibility and integration contracts, not an independent safety verdict. Claude remains the independent reviewer of `fix/phase31-h1-h2-checkpoint-closure@f9dcf56ae52b095a3af05b8fc45a2568cd5642fe`. This branch starts at exact `integration/three-features-prep@73f3bdbd78ee8bdf4b323457ba2f036f16fb82d9`; it contains no H1/H2 implementation changes or feature merges.

## Results

| Check | Before | After / investigation |
|---|---|---|
| Original browser assertions | 64/64 passed, no skips | 64/64 passed, no skips |
| Original frontend unit tests | Integration baseline expected 186 | 186/186 passed, 12 files |
| Production build / typecheck | Build passed | Both passed; four HTML entries |
| Feature-owned temporary directories left behind | 10 | 0 |
| All observed new test temporary directories | 17 | 6; remaining ownership gaps described below |
| Additive reliability diagnostics | Not present | 3 passed; failure-path cases rerun 2/2 after strengthening the intentional-throw scenario |
| Source provenance | Existing pins | All 126 engine/foundation/integration files verified unchanged |

Browser durations were 159.45 seconds before and 141.20 seconds after. These are separate runs on a shared machine, **not evidence that the harness accelerated the application**. Captured metadata is in [reliability-evidence/summary.json](reliability-evidence/summary.json). No screenshots, databases, anchor files or source datasets are copied into this deliverable.

## 1. Backend snapshot-idempotence flakiness

Confirmed code path: [test_application.py:66](../application/test_application.py#L66) compares the complete initial snapshot with the next snapshot. [service.py:289](../application/service.py#L289) generates `freshness.verifiedAt` using `Ledger._now()`, which formats the real UTC wall clock to whole seconds ([ledger.py:121](../integration/pramaan_integration/ledger.py#L121)). Two semantically identical snapshots can therefore differ when their reads cross a second boundary.

Measured with the original test file unchanged, each case using its normal new SQLite database:

| Mode | Runs | Failures | Interpretation |
|---|---:|---:|---|
| Original test, no observation wrapper or clock patch | 20 | 9 (45%) | Natural wall-clock run; detailed diff locations were not recorded in this first batch. |
| Original test, unpatched retry with assertion-stage diagnostics | 10 | 2 (20%) | Both failures occurred at the whole-snapshot equality assertion; zero errors. |
| Natural clock, snapshot observation wrapper | 30 | 11 (36.7%) | Every failed pair differed **only** at `/freshness/verifiedAt`; zero errors. |
| Forced boundary between the compared snapshots | 5 | 5 (100%) | Deterministic reproduction of that same timestamp-only difference. |
| Fixed clock during this test's snapshot calls | 10 | 0 | Every original assertion, including findings and reason codes, still executed. |

These finite samples have different instrumentation and machine load. Do not combine them into a universal failure probability. The observation wrapper copies results and can affect timing. There is **no observed manufacturing-history or decision inconsistency** in the instrumented failed pairs; that is a bounded finding, not a proof against all inconsistencies.

Bounded remedy: [backend_probe.py](../reliability/backend_probe.py) offers an explicit `fixed` test-only clock mode without editing the original test. It patches `Ledger._now` only while that test calls `Manufacturing.snapshot`; capture/producer timestamps outside those calls retain their normal behavior. `boundary` and `natural` modes retain failing results. The probe now exits nonzero if any original test fails; forced-boundary exit 1 and fixed-clock exit 0 were checked separately.

**Remaining issue:** the unchanged original CI command can still flake. This report does not silently replace it, suppress it or modify production clock semantics. Owner review is needed before adopting a scoped deterministic-clock runner for this one equality test. Freshness expiry/skew tests must continue using controlled advancing clocks and retain their existing assertions.

## 2. Browser concurrency, state reuse and cleanup

Confirmed port map on the exact integration base:

| Purpose | Ports |
|---|---|
| Shared seeded Playwright server | 4173 |
| Legacy outage / unspecified scope / external writer | 4182 / 4183 / 4184 |
| Passport isolated tests | 4185–4187 |
| Investigation workspace isolated tests | 4191–4195 |
| Impact isolated tests | 4196–4197 |
| New opt-in reliability diagnostics | 4210–4212 |

There is no within-suite feature port overlap. The earlier impact 4191/4192 conflict was already fixed at `73f3bdb`; this branch does not claim that fix. Concurrent **separate suite invocations** still request the same fixed ports and are not supported as isolated parallel runs. They should fail on occupied ports, never kill someone else's listener. No collision was observed in either full 64-test run.

Confirmed storage behavior:

- Every isolated feature helper originally called `mkdtempSync`, so its SQLite database and test-owner anchor path were unique. Restart tests deliberately reuse **their own** database/anchor to test recovery; this is intentional.
- Tests using the default base URL share one seeded server/database. The main live scenario writes to that database. Read-only tests therefore have some order/state coupling even though both full runs passed; a fresh per-test fixture is a future improvement requiring careful test-contract review.
- `passport.spec.ts`, `workspace.spec.ts` and `impact.spec.ts` killed their child processes without awaiting closure and never removed their temporary directories. Startup failure in the old passport/workspace helper could occur before its `finally` block. Missing cleanup is confirmed; a restart race from unawaited shutdown is a **code-supported risk**, not a reproduced test failure in these runs.
- `playwright.config.ts` creates a temporary directory while evaluating its configuration. Repeated evaluations can create roots even when only one is used by the actual server.

Bounded fix: [OwnedServer](../recall-ui/tests/support/ownedServer.ts) is used only by the three feature test files. It preserves the same ports and seeded/unanchored fixture behavior, awaits shutdown before restart/removal, retains bounded child diagnostics, checks port availability, and deletes only its own generated root under the OS temporary directory. Cleanup also covers startup/body failures. The feature assertions, timeout thresholds and read-only database/anchor comparisons were retained. Database/anchor reuse is confined to one helper's explicit restart.

The before-run directory delta was 17: four configuration roots, ten feature roots, three legacy roots. The after-run delta was six: three configuration roots and three legacy roots; **zero new owned-helper roots remained**. Configuration evaluation count differs between runs, so the total reduction of eleven must not be described as eleven repaired ownership paths. Ten feature roots were addressed. Two extra diagnostics verify refusal to reuse an occupied listener and cleanup after an intentionally thrown test-body error; neither kills the foreign listener.

Remaining cleanup gaps were deliberately not rewritten: configuration-owned roots and the legacy hardening/remediation test roots. Their files/assertions are preserved. Existing old roots from other runs were not recursively removed. Fixed-port preflight is not atomic port reservation; its small check-to-bind race remains a limitation of the test harness, not a claimed ownership/security guarantee.

## 3. Frontend timing and the large impact dataset

Measured using the actual production build and actual synthetic backend, with a separate test-owned server. Timing boundaries and samples are in [latency.json](reliability-evidence/latency.json).

| Phase | Observed result |
|---|---|
| Process spawn through `/api/session` readiness | 1,873.96 ms, one startup |
| Snapshot HTTP request through response receipt, 10 samples | 315.99–513.46 ms; median 408.06 ms |
| Additional response JSON parsing | 1.92–9.56 ms |
| `validateSnapshot` call after parsing | 0.0267–0.5103 ms |
| Navigation through visible live fleet plus two animation frames | 1,129.48 ms, one navigation |
| 1,500-motor preview, fresh document each time | 1,540.24 / 1,366.14 / 1,372.01 ms through graph-window visibility |
| Visible graph nodes | 156 in every sample, below the original 400-node bound |
| Next graph page, three samples | 620.91–822.24 ms |
| Switch to list with remaining-record control visible | 1,068.49–1,156.10 ms |

The combined-suite original large-data case took 37.36 seconds before and 29.07 seconds after; its logged first-graph times were only 4,472 and 4,640 ms respectively. This demonstrates why whole-case duration cannot be attributed to initial rendering. Screenshot, assertion, paging and list phases remain inside that larger envelope; the current probe does not precisely attribute all of its cost. It retains its original `<15,000 ms` first-render assertion and the integration-prep 90-second **test-case** budget. A longer test-case budget does not change the live network/freshness timeout. The three timing samples navigate through `about:blank` first; this avoids incorrectly measuring an already-present graph as a new render. An earlier exploratory probe reused an existing document and is not used for these fresh-document results.

`PreviewImpactSource` loads the small authored dataset, validates it, then creates the 1,500-motor scale locally. Cloned decisions are explicitly labelled copies, not 1,500 new evaluator decisions. These preview/render results are **not** large-ledger performance results. Startup, backend work, parsing, validation, React rendering and screenshot/test orchestration are different timing boundaries; a whole-case duration must not be labelled graph-render latency. The isolated schema timing runs in the test process, not an instrumented browser validation stack; exact browser attribution is not claimed.

No production timeout, freshness lease, source class, graph projection or render implementation changed. Live requests remain bounded by four seconds; the impact preview retains its existing six-second fetch timeout. A large synchronous post-fetch projection/render could consume time outside the fetch timeout or delay timers on the browser thread: this is a production-code investigation/approval item, not fixed here. Measurements are local, finite and partly under concurrent regression load, not a production SLA or a controlled before/after speed comparison.

## 4. Hosted-green CI compatibility — read-only audit

Reference: `infra/phase31-ci-gates@04d974fd6307fca1f129be6b5683f4468b5fcad7`. Neither that branch nor its workflow, pins, manifest or assertions changed. [ci-inventory-final.json](reliability-evidence/ci-inventory-final.json) is generated by the read-only [inventory comparison](../reliability/ci_inventory.py). It first confirms zero differences for the original `f928210` manifest baseline.

The 196-file `ci/frozen-source.json` needs explicitly reviewed evolution after integration, **not automatic regeneration to obtain PASS**:

- Integration-prep differs in exactly `recall-ui/package.json`, `recall-ui/package-lock.json` and `recall-ui/vite.config.ts`. The two added packages are `uqr` and `jsqr`; four Vite entry pages replace the old single-entry setup. Fifty additional application/UI paths relative to the frozen baseline need coverage review; the artifact lists them individually.
- H1/H2 separately differs in eight frozen files: `application/{anchors,audit,server,service}.py`, `recall-ui/src/App.tsx`, `recall-ui/src/data/{RecallDataSource,freshness}.ts`, and `recall-ui/src/domain/types.ts`. Four additional application/UI paths need review. These are not imported into this branch.
- This reliability branch adds test-support/diagnostic files and changes three previously new feature e2e files; these also need explicit coverage decisions if later integrated into CI.
- Keep the independent 126-file `application/source-provenance.json` engine/foundation/integration inventory unchanged unless separately authorized. It verifies successfully here.

Reviewed test expectations must distinguish old baseline, integrated features, H1/H2 and opt-in diagnostics:

| CI expectation today | Integration consideration |
|---|---|
| 33 Vitest / 29 Playwright | Three-feature base has 186 / 64, actually verified here. Do not simply relax exact-count assertions. |
| Python application modules 7 / 16 / 13 | Existing counts unchanged; H1 adds its own 23-test module and still has a reported historical-resolution conflict. |
| Engine 127, integration 44, foundation 21, exporter 7, infrastructure 5 | No reason established here to reduce or change them. |
| Port preflight: 4173, 4182–4184 | Expand approved coverage to feature ports 4185–4187 and 4191–4197. Diagnostics 4210–4212 only if separately adopted. |

H1's four additional UI checks and one browser scenario cannot be treated as an automatic additive green total: original compatibility failures remain unresolved. The CI browser override uses the pinned Chrome executable and imports the normal Playwright configuration; preserve its exact browser/dependency/GS1 checks, raw logs, fail-closed summary and source checks before/after testing. No hosted CI success for this new research branch is claimed.

## 5. Original H1/H2 compatibility failures reproduced separately

A detached disposable checkout of exact `f9dcf56` was used. No production file or original test was edited; no H1 implementation was copied here.

| Original test group | Reproduced result | Reliability classification |
|---|---|---|
| `application.test_hardening` | 12 passed, 1 error | `test_historical_resolution_entries_are_not_rewritten` expects export over a resolution claim; new code returns `RESOLUTION_FORBIDDEN`. Confirmed conflict with the owner's explicit historical-only/migration requirement. |
| `backend-source.test.ts` | 4 passed, 3 failed | Two accepted-response tests provide legacy envelopes without checkpoint/eligibility metadata. The stale-response test still rejects, but missing metadata preempts its expected `/expired/` reason. Confirmed fixture/contract and error-precedence conflicts. |
| Four selected original browser tests | 0 passed, 4 failed; no skips | External writer, multi-step manufacturing flow, long identifiers, and NDE-only scope expect normal finding/action views after post-checkpoint writes. Strict mode withholds the normal views/next operations. Contract breaking behavior and an operational workflow/usability limitation relative to the old flow; not permission to weaken gating. |

The browser results do not independently certify that all underlying safety behavior is correct. Selector failures alone cannot establish correctness. Claude's safety audit must judge that implementation. This investigation confirms reproducibility and identifies the specific acceptance-contract disagreement; it does not preempt Claude's conclusions.

### Minimal proposed migration, requiring owner/safety-review approval

1. Keep original failing tests and reports visible until an explicit contract change is approved. Track exact superseded expectations and their replacement coverage; do not delete tests to manufacture green counts.
2. For backend-source positive tests, use a genuine synthetic response from a test-owned archive and explicitly configured test custody, with the full reviewed envelope. Do not hand-fill trust/replay/eligibility flags to make fixtures pass. Then vary only the intended field for stale/sequence/concurrency negative tests, so missing metadata cannot preempt the behavior under test.
3. For browser flows, separate immutable recorded decisions from current eligibility. Assert prefix withholding and visible holds after capture. If testing renewed clearance, use an explicit out-of-band, test-owned approval/activation and server restart with predecessor chaining; never add HTTP trust promotion or implicit local-anchor trust. Retain ambiguity, provenance, pending-obligation and scope assertions.
4. For historical resolution archives, preserve every stored row and digest, verify historical access separately, and retain export/current-clearance blocking until a separately approved migration exists.
5. Before combining the three pages with H1/H2, approve one explicit current-eligibility contract for all live adapters. Confirmed source fact: standalone adapters treat a successful `verifyFreshness` return as `verified: true`; H1's verifier also accepts prefix-only snapshots for hold visibility, while its console has a separate eligibility gate. **Inferred integration risk:** an unadapted standalone page could confuse a freshness lease with operational clearance. No combined production experiment or fix was performed. This issue requires production/safety-code changes, so work stops on that issue for owner/Claude review.

## Reproduction

From this branch's repository root, use Python 3.12 and Node/npm versions matching the project. Create `.venv`, install `experiments/foundation/requirements.txt`, and run `npm ci --prefix recall-ui --ignore-scripts`. System Chrome is required by the existing local browser configuration.

```powershell
.venv/Scripts/python.exe reliability/backend_probe.py --mode original --runs 20 --output .tmp-reliability/backend-original.json
.venv/Scripts/python.exe reliability/backend_probe.py --mode natural --runs 30 --output .tmp-reliability/backend-natural.json
.venv/Scripts/python.exe reliability/backend_probe.py --mode boundary --runs 5 --output .tmp-reliability/backend-boundary.json
.venv/Scripts/python.exe reliability/backend_probe.py --mode fixed --runs 10 --output .tmp-reliability/backend-fixed.json
.venv/Scripts/python.exe reliability/ci_inventory.py --output .tmp-reliability/ci-inventory-final.json
```

Natural/boundary modes intentionally return nonzero when they reproduce a failure. From `recall-ui`, run `npm run typecheck`, `npm test`, `npm run build`, `npx playwright test` (the unchanged 64 cases), and `npx playwright test --config reliability.config.ts` (three opt-in diagnostics). Run diagnostic timing separately from the main browser suite for a less-contended measurement. Build before diagnostics; the diagnostic server serves the real `dist` build. The checked-in summary is a recorded result inventory, not an executable test gate. For cleanup comparison, record `Get-ChildItem -LiteralPath ([IO.Path]::GetTempPath()) -Directory -Filter 'pramaan-*'` before and after each complete run; compare only new names, and do not delete directories belonging to other runs.

## Owner review boundary

The isolated cleanup fix and test-only diagnostic clocks are ready for review. Remaining issues: default/legacy temporary-root cleanup, shared seeded-server state coupling, fixed-port conflicts across concurrent suite invocations, clock-sensitive original CI invocation, unreviewed frozen-inventory/count migration, and H1/H2 response/workflow contract migration. No production change is proposed as already approved. No PR, merge, deployment or main change is authorized or performed. Safety conclusions remain with Claude's independent audit.
