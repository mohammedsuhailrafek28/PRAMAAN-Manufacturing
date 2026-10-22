# Frontend Phase A — shared fail-closed checkpoint/eligibility gate

Branch `feature/frontend-gate-phase-a`, based on `integration/three-features-prep@73f3bdbd78ee8bdf4b323457ba2f036f16fb82d`.
Design: `docs/FRONTEND_H1_H2_REMEDIATION_PLAN.md` (`plan/frontend-h1-h2-remediation@9c65fa88`). Audit: `review/h1-h2-independent-audit@e63bf90`.
Contract basis: H1/H2 Option A at `f9dcf56` — **not merged, cherry-picked or vendored**. Its real `/api/snapshot` responses were *captured* (synthetic, disposable DB) as test fixtures.

## 1. What changed

| Area | Change |
|---|---|
| `src/contract/gate.ts` (new) | Pure typed gate. `evaluateEnvelope(response, previous, now)` returns `CURRENT`, `SEGREGATED` (`PREFIX_ONLY`, `UNANCHORED`, `ELIGIBILITY_WITHHELD`) or `WITHHELD` (`ANCHOR_INVALID`, `VERIFYING`, `MISSING_METADATA`, `UNKNOWN_STATE`, `CONTRADICTORY`, `LEASE_EXPIRED`, `REGRESSION`, `INTEGRITY`, `TRANSPORT`). Classification reads HTTP status, `state`, `checkpoint.state`, `freshness.status` only — never message text. Any thrown exception is `WITHHELD/INTEGRITY`. `GateTracker` keeps the last accepted snapshot for structural regression checks and the last-accepted watermark. |
| `src/contract/envelope.ts`, `liveLoad.ts` (new) | GET-only fetch that keeps status + structured error body; one shared live-load path. |
| `passportSource.ts`, `investigationSource.ts`, `impactSource.ts` | Live adapters now call `liveLoad`. The `/regression/i` branches and `verifyFreshness` calls are gone (F1, D1). Preview adapters are unchanged and only reachable by explicit `?mode=preview`. |
| `PassportApp.tsx` | On a WITHHELD gate it drops the held snapshot (O3: no "stale" motor records). Investigation/Impact already hide everything unless verified. |
| `domain/types.ts` | The same two optional fields (`checkpoint`, `eligibility`) the H1/H2 branch adds, character-for-character, so a later merge is trivial. |
| `public/data/*.json`, `tools/preview_sanitize.py`, generators | O2: customer, destination and operator identifiers removed from the four publicly served JSON files. `customer`/`destination` → `[not included in preview]`; operator/employee/system actor ids → per-file `ACTOR-NN` pseudonyms (equality preserved); `shipmentId` kept (synthetic, needed). The sanitiser is wired into `export_snapshot.py` and both demo generators (`npm run snapshot:check` passes). `passport-preview.json` has no generator; run `python tools/preview_sanitize.py`. |
| Tests | `tests/unit/gate.test.ts` (25), `standalone-gate.test.tsx` (37), `preview-privacy.test.ts` (10), `tests/e2e/gate.spec.ts` (54); real captured fixtures in `tests/fixtures/h1h2/` (`tools/capture_h1h2_envelopes.py`). |

Not touched: `App.tsx`, `freshness.ts`, `RecallDataSource.ts`, `server.py`, `anchors.py`, `audit.py`, `service.py`, the engine, the ledger, Codex's branch, CI.

## 2. Policy as implemented (owner decisions O1–O3)

| Gate | Passport | Investigation | Impact |
|---|---|---|---|
| CURRENT | full | full | full |
| PREFIX_ONLY / UNANCHORED / ELIGIBILITY_WITHHELD | provenance/genealogy facts under a "not currently verified" banner; recall status "unavailable"; no action label | tasks withheld, neutral reason shown | graph withheld, neutral reason shown |
| WITHHELD (all causes) | nothing motor-specific; neutral reason + last accepted watermark (historical) | same | same |

Notes. (1) For PREFIX_ONLY, O1 *allows* a historical evidence frame; Investigation and Impact already withhold everything when not verified and I did not widen that — only the Passport shows historical facts. (2) `ELIGIBILITY_WITHHELD` is my addition, consistent with the main app: a CURRENT snapshot that contains a `RELEASE_ELIGIBLE` decision whose motor is not eligible (e.g. pending notification) is never shown as cleared. (3) PREFIX_ONLY additionally requires `h2 === "VERIFIED"` ("evidence has passed the available checks"); otherwise `WITHHELD/INTEGRITY`.

Invariant the gate establishes: in a CURRENT snapshot every `RELEASE_ELIGIBLE` decision belongs to an eligible motor and vice-versa, so the existing projections cannot emit a current-clearance label from a non-current snapshot. The planned *branded* `GatedSnapshot` type (compile-time removal of `operationalAction` from page code) was **not** implemented; the plan's FE-ARCH-1 is therefore enforced only for the adapters, not for projections. That is the main design reduction versus the plan.

## 3. Test evidence

All commands run from `recall-ui/`.

| Check | Result |
|---|---|
| `npx tsc --noEmit` | clean |
| `npm run snapshot:check` | "snapshot is current" |
| `npx vitest run` | **258 tests: 248 pass, 10 fail** (baseline at `73f3bdb`: 186/186; new tests: 72, all pass) |
| `npx playwright test` (default config, shared seeded server = the `73f3bdb` backend) | **118 tests: 95 pass, 23 fail** (baseline 64/64; new gate matrix 54 of 54 pass in the default run) |
| Same existing feature specs against the **real H1/H2 backend** (`playwright.h1h2.config.ts`, backend checkout used read-only, specs run with cwd in that checkout so their own spawned servers are H1/H2 too) | passport 9/12, impact 12/13, workspace 5/10 pass → **9 fail** (all explained below) |

Mutation checks (not committed): making the gate treat `ANCHORED_PREFIX_ONLY` as CURRENT fails the unit tests (9) and all four browser FE-02 tests; an earlier, looser FE-02 assertion missed three of four pages, so FE-02/03 now require the page to *say* "checkpoint is required" / "no trusted external anchor".

### 3.1 The 10 failing Vitest tests (all pre-existing tests, none edited)

| Test(s) | Cause | Class |
|---|---|---|
| passport-app ×3, impact-app ×2, investigation-app ×2 (live adapter) | Their mocked envelopes are legacy (anchored status, no `checkpoint`/`eligibility`); the strict gate returns `WITHHELD/MISSING_METADATA` (verified from the thrown `GateWithheldError`) | A — expected incompatibility with the strict contract |
| passport-app "withdraws recall status and marks records stale…" | Asserts the stale-records banner after a backend failure; O3 now forbids keeping motor records | A — owner decision O3 |
| investigation-projection ×2, investigation-app ×1 | Assert the literal actor id `OP-OBSERVATION-21` from the preview data; O2 pseudonymises it (`ACTOR-NN`) | A — owner decision O2 |

No failure is class B (product regression) or C (new weakness) as far as I can tell; I did not run migrated copies, so "for the stated reason" is established from error messages, not from re-passing tests.

### 3.2 The 23 failing Playwright tests against the `73f3bdb` backend

That backend predates H1/H2 and emits no `checkpoint`/`eligibility`, so every live standalone-page test is `WITHHELD/MISSING_METADATA` by design (passport 9, impact 6, workspace 8). Three workspace tests also assert `OP-OBSERVATION-21` (O2). These pass or change classification only once the H1/H2 contract is the backend (Phase B).

### 3.3 The 9 failures against the real H1/H2 backend

| Test | Cause | Class |
|---|---|---|
| workspace "authored scenario walkthrough", "desktop…axe", "mobile…axe" | preview data contains `OP-OBSERVATION-21` which O2 removes | A (O2) |
| workspace "live: an evidence update changes the listing…" | issues a POST command; under strict R5 the ledger is then PREFIX_ONLY, so no task cards | A (H1/H2 R5; shared-state/workflow) |
| workspace "an unanchored envelope is withheld…", passport "an unanchored backend yields records labelled unverified…" | The test forges `HISTORICAL_UNANCHORED` on an otherwise CURRENT envelope; the gate returns `CONTRADICTORY` and (O3) shows nothing, while the test expects labelled records (passport) / a `withdrawn` element (workspace) | A (O3) |
| impact "live anchored ledger… then withheld on outage" | after an outage the test expects genealogy labelled "not current"; O3 withholds it | A (O3) |
| passport "backend outage withdraws recall status, labels records stale…" | expects stale records after outage; O3 forbids | A (O3) |
| passport "external writer: recall context changes…" | an external write makes the ledger PREFIX_ONLY; the test expects an updated *current* recall card | A (H1/H2 R5) |

## 4. Remaining blockers / backend and Codex dependencies (Phase B)

1. `App.tsx`, `freshness.ts`, `RecallDataSource.ts` (Codex-owned) must delegate to `gate.evaluateEnvelope`; today there are two gates (main app: legacy `verifyFreshness` + strict `accept`; standalone pages: this gate). They agree on the fixtures tested but are not a single implementation.
2. Branded `GatedSnapshot`/`HistoricalView` types (plan §2.2) are not implemented; projections can still read `operationalAction` in non-current mode, guarded only by the adapters never passing a non-current snapshot as verified.
3. The live `/api/snapshot` still exposes customer/destination/shipment data. Sanitising the static preview is minimisation, not access control (O2); an API decision belongs to the backend/owner.
4. Backend findings D2–D10 (e.g. `/decisions` and `/investigation` endpoints without state; PREFIX_ONLY after any external capture requires a restart with a new checkpoint) are unchanged. The browser matrix covers only `/api/snapshot`, the sole endpoint these pages use.
5. Acceptance-test compatibility (the 10 + 23 + 9 above) needs the deliberate, owner-approved migration (step 3 of O4); no original test or assertion was changed or weakened.
6. Environment note: the full default Playwright suite needs port 4173 free; `playwright.gate.config.ts` runs only the new matrix on port 4321. `playwright.h1h2.config.ts` needs `H1H2_BACKEND` (a separate H1/H2 checkout with its own `.venv`) and copies this build into that checkout's git-ignored `recall-ui/dist`.
7. Not covered: the main fleet app's own behaviour (unchanged), hidden-tab and 4 s timeout behaviour beyond the existing tests, and axe/mobile checks for the new withheld messages (they reuse existing panels).
