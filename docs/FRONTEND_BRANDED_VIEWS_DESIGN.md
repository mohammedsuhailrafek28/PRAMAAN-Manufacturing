# Branded `GatedSnapshot` / `HistoricalView` — design and regression specification (DESIGN ONLY)

Base: `feature/frontend-gate-phase-a@cf97c1d4998f45c5060bd8d33a7b00a8fa545ed9` (unchanged). Nothing here is implemented.
Owner inputs applied: Decision 1 (`ELIGIBILITY_WITHHELD` is a per-motor presentation outcome only), Decision 2 (segregated `ANCHORED_PREFIX_ONLY` only when complete structured metadata establishes successful H2).

## 1. What the code actually lets a developer do today (survey of cf97c1d)

| Fact | Where |
|---|---|
| Pages hand the **raw** `RecallSnapshot` (`last.snap`) to projections and components, plus a hand-set boolean (`recallVerified`, `recallStatusCurrent`, `mode`). | `PassportApp.tsx:74`, `InvestigationApp.tsx:64,112`, `ImpactApp.tsx:100`, `ImpactWorkspace.tsx:40` |
| `operationalAction` / `evidenceFinding` / `decisions[...]` are read in exactly three projection files, then re-exposed as `action`/`finding` fields that components render. | `passport/projection.ts:256-267`, `investigation/projection.ts:331,402-409,425,494`, `impact/projection.ts:128,331` |
| Components render the label from `action`/`finding` through the shared glossary and `ActionChip`-style spans. | `PassportExplorer.tsx:97-107`, `InvestigationWorkspace.tsx:72-76`, `NodeDetails.tsx:93-101`, `ImpactList.tsx:33`, `ImpactGraphView.tsx:16` |
| `eligibility` is never read by any projection or component; only the gate looks at it. | grep |
| Standalone pages use only `GET /api/snapshot`. | grep |
| Phase A makes ELIGIBILITY_WITHHELD a **snapshot-level** SEGREGATED cause, which downgrades unrelated eligible motors. **This contradicts Decision 1 and must be removed in the follow-up.** | `gate.ts` (`blocked` branch) |

So the unsafe label is prevented today only because adapters never mark a non-current snapshot `verified`. A future page that passes `last.snap` with a literal `true` re-opens D1/F2; no type or test stops it.

## 2. Types

All in a new `src/contract/gated.ts`; the **only** module allowed to read `decisions`, `eligibility`, `operationalAction`, `evidenceFinding` or `currentReleaseEligible` from a `RecallSnapshot`.

```ts
declare const GATED: unique symbol;      // not exported as a value: no code outside gated.ts can build the brand
declare const HISTORICAL: unique symbol;
declare const PREVIEW: unique symbol;
declare const CLEARED: unique symbol;

/** Per-motor, derived only from `eligibility[unit].currentReleaseEligible` (explicit, never from a decision). */
export type CurrentClearance = { readonly [CLEARED]: true };          // obtainable only via clearanceOf()
export type MotorClearance = CurrentClearance | "HOLD" | "NOT_CLEARED";

export interface Facts extends Omit<RecallSnapshot, "decisions" | "eligibility" | "comparison" | "notifications" | "freshness" | "checkpoint"> {}

export interface GatedSnapshot {           // gate === CURRENT
  readonly [GATED]: true;
  readonly facts: Facts;                  // no `decisions` property exists on this type
  readonly watermark: Watermark;
  readonly decisions: ReadonlyMap<string, GatedDecision>;   // per motor, already clearance-resolved
  readonly projectable: RecallSnapshot;   // §3 data-level layer; for core projections only, not importable by pages
}
export interface GatedDecision { clearance: MotorClearance; finding: Finding; reasonCodes: readonly string[]; reviewRequired: boolean; precautionaryHold: boolean; version: number | null; decisionId: string; /* NO action field */ }

export interface HistoricalView {           // gate === SEGREGATED (PREFIX_ONLY | UNANCHORED)
  readonly [HISTORICAL]: true;
  readonly cause: "PREFIX_ONLY" | "UNANCHORED";
  readonly facts: Facts;
  readonly watermark: Watermark;
  readonly reason: string;
  // deliberately NO decisions, NO clearance, NO finding/action fields
}
export interface PreviewView { readonly [PREVIEW]: true; readonly facts: Facts; readonly label: string; readonly projectable: RecallSnapshot }

export function clearanceOf(g: GatedSnapshot, unitId: string): MotorClearance;
```

Rules enforced by construction:

- `clearanceOf` is the single place that returns `CurrentClearance`. It requires `g` (so CURRENT), requires `snap.eligibility[unitId].currentReleaseEligible === true` **and** that the motor's decisions are all `RELEASE_ELIGIBLE`; a `RELEASE_ELIGIBLE` decision with eligibility `false` yields `"NOT_CLEARED"`; `RECALL_HOLD` yields `"HOLD"`. Per-motor: other motors are unaffected (Decision 1).
- `HistoricalView` has no decision data at all, so "RELEASE_ELIGIBLE from historical data" is unrepresentable. If the owner later wants holds shown in the historical frame, add `holdRecorded: boolean` only; never a release flag.
- Factories (`makeGated`, `makeHistorical`, `makePreview`) are module-private, called only from `gate.ts` and the preview adapters, and register every instance in a module `WeakSet`. Every entry point runs `assertBranded(x)`; a forged object (`{} as GatedSnapshot`, a `structuredClone`, a JSON round-trip) throws.
- A single `ClearanceChip` component (`src/contract/ClearanceChip.tsx`) is the only code that may render "Release eligible"/`action-RELEASE_ELIGIBLE`. Its prop type is `CurrentClearance`, which a string literal or boolean cannot satisfy.

## 3. Three enforcement layers (smallest set that survives developer error)

1. **Compile time.** Page-level props change from `RecallSnapshot` to `GatedSnapshot | HistoricalView | PreviewView`; `Facts` (no `decisions`) is what components such as `EventLink`/`EvidenceTable` take. A function that needs a decision must accept `GatedSnapshot` and call `clearanceOf`.
2. **Data level (defence in depth, lets the existing projection cores stay unedited).** New thin wrappers `projectPassport(view)`, `projectInvestigation(g)`, `projectImpact(view, selection)` call the unchanged cores with `projectable`, a sanitised copy: for a CURRENT snapshot, decisions of motors whose clearance is `NOT_CLEARED` are **removed** (core already uses `?.`/`?? {}` so the motor shows as "recall status withheld"), `eligibility`/`comparison` are removed, `RELEASE_ELIGIBLE` therefore survives only for motors with `currentReleaseEligible === true`. For `HistoricalView`, `projectable.decisions` is `{}`. Even a core that mis-reads `operationalAction` cannot produce current clearance for a non-cleared motor.
3. **Run time + architecture.** `assertBranded` registry check, and static tests (§4) that fail the build if pages import the cores directly, import `last.snap`, mention `operationalAction`/`RELEASE_ELIGIBLE`/`currentReleaseEligible` outside `src/contract/`, or construct the clearance chip elsewhere.

Why not edit the three projection cores now: they are covered by ~200 original tests that pass raw snapshots; keeping them as an unexported-by-pages "unsafe core" lets layers 1–3 land with **zero** edits to original projection tests. The cost is that the cores still *read* `operationalAction`; layer 2 is what makes that harmless. A later phase can move the cores onto `GatedSnapshot` directly once the owner approves migrating those tests.

## 4. Gate changes required by the owner decisions (spec delta to `gate.ts`)

| Item | Phase A (cf97c1d) | Follow-up |
|---|---|---|
| ELIGIBILITY_WITHHELD | snapshot-level SEGREGATED when any motor has a `RELEASE_ELIGIBLE` decision with eligibility false | **Removed as a gate cause.** CURRENT stays CURRENT; the motor gets `clearance: "NOT_CLEARED"` through `clearanceOf`. Not a checkpoint state, not a backend concept. |
| PREFIX_ONLY H2 | `h2 === "VERIFIED"` else INTEGRITY | Segregated **only if** all hold: `checkpoint.state === "ANCHORED_PREFIX_ONLY"`, `h2 === "VERIFIED"` (exact), `checkpointRequired === true`, `anchoredSequence` is an integer ≥ 1 and ≤ `freshness.sequence`, `freshness.status === "VERIFIED_PREFIX_SYNTHETIC"`, strict metadata complete, no eligibility true. Mapping of failures: `h2` missing/non-string → `MISSING_METADATA`; `h2` outside the closed set `{VERIFIED, UNVERIFIED, HISTORICAL_UNVERIFIABLE}` → `UNKNOWN_STATE`; known but ≠ `VERIFIED` (or `anchoredSequence` absent/inconsistent) → `CONTRADICTORY`/`INTEGRITY`. All are **WITHHELD**; none degrade to historical. |
| UNANCHORED | allowed, `h2` unconstrained | Allowed only with `anchoredSequence === null`, `checkpointRequired === true`, `h2 === "UNVERIFIED"`, all eligibility false; presented as *explicitly unverified local claims* (copy already says so). Any other `h2` → WITHHELD. |
| Return type | `{snap}` | `GatedSnapshot` / `HistoricalView` (§2). `liveLoad` returns them; Loads keep the legacy fields (`snap` removed from page use, see §6). |

## 5. Regression specification — tests that must fail if a future developer errs

Each row lists the **mutation** (what the bad change looks like), the test, and why it fails.

| # | Developer error | Test(s) | How it fails |
|---|---|---|---|
| T1 | Passes a raw snapshot into a standalone view | **Type tests** `tests/types/branding.test-d.ts` (compiled by `tsc --noEmit`, part of `npm run build`): `// @ts-expect-error` on `projectPassport(rawSnap)`, `<ImpactWorkspace snap={rawSnap}…/>`, `<PassportExplorer … />`, `buildPassport` imported from a page. An unused `@ts-expect-error` is itself a compile error, so removing the brand breaks the build. **Runtime**: `projectX({} as never)`, `structuredClone(g)`, JSON round-trip all throw `NotBranded`. **Static**: no file in `src/passport|investigation|impact` other than `*Source.ts`/wrappers may import `./projection` or reference `last.snap`/`.snap.`. | brand missing → compile error; forged cast → registry throw; direct core import → static test red |
| T2 | Renders RELEASE_ELIGIBLE from historical data | **Property test** over every real fixture state × every route × every tab of the three pages: DOM text must not match the CLEARANCE regex unless the motor's `clearanceOf` is `CurrentClearance`. **Data invariant**: for any gate result, `projectable.decisions` contains `RELEASE_ELIGIBLE` only for motors with `currentReleaseEligible === true`; `HistoricalView` has no `decisions` key (checked with `Object.keys`). **Mutation test** (kept in CI as a script): patch `makeHistorical` to include decisions → suite must go red. | any historical path that carries a decision or label fails the invariant and the DOM scan |
| T3 | Builds a current-clearance chip without `currentReleaseEligible` | Type: `// @ts-expect-error <ClearanceChip clearance="CLEARED_CURRENT" />` and `{} as CurrentClearance` rejected by the registry. Static: `ACTION_TEXT[`, `action-RELEASE_ELIGIBLE`, `"Release eligible"`, `RELEASE_ELIGIBLE` appear only in `src/contract/`. Behavioural fuzz: for every fixture, flip each motor's `currentReleaseEligible` to false (and to non-boolean) → zero clearance chips for that motor, other motors unchanged (Decision 1 test). | any new chip path is either a compile error, a static-grep failure, or a fuzz failure |
| T4 | Treats an unknown backend integrity state as merely historical | **Exhaustiveness**: `GateCause` switch in every page ends with `assertNever`; adding a cause without handling is a compile error. **Property/fuzz**: ≥10 000 mutated envelopes (unknown `checkpoint.state`, `h2`, `freshness.status`, missing/typed-wrong fields, extra whitespace, wrong case, null/array/object for each strict field, truncated bodies, HTTP 2xx/3xx/4xx/5xx with arbitrary bodies, thrown parse errors): invariant *result is `SEGREGATED` ⇒ (`state` ∈ {`ANCHORED_PREFIX_ONLY` with every Decision-2 condition, `UNANCHORED` with its conditions})*; everything else must be `WITHHELD` and the rendered page must satisfy MOTOR_SPECIFIC = none. **Type**: `makeHistorical` takes `cause: "PREFIX_ONLY"|"UNANCHORED"` so a new call site passing a generic cause fails to compile. **Mutation**: making the default branch return historical → fuzz red. | any fallthrough to historical |
| T5 | Bypasses the gate through deep links | Browser matrix: every route grammar entry (passport tabs/evidence/qr, investigation cluster/evidence, impact lot/graph/list/node) × every non-CURRENT state, opened as the first navigation *and* via `hashchange` after a CURRENT load; assert no clearance wording and (WITHHELD) no motor text. Unit: route parsers never touch data; `evidenceId`/`unitId` taken from the URL cannot select a decision. | a route that reads data outside the wrapper shows text → red |
| T6 | Bypasses the gate through preview mode | (a) Preview adapters return only `PreviewView`; a type test proves `PreviewView` is not assignable to `GatedSnapshot`/`CurrentClearance`. (b) `clearanceOf` rejects `PreviewView` (type + registry). (c) Preview JSON edited to contain `checkpoint.state: "ANCHORED_CURRENT"`, `eligibility: {...true}` → still `PreviewView`, still never a `ClearanceChip`, banner present. (d) A **live** page with the backend failing makes no request to `*-demo.json`/`passport-preview.json`/`snapshot.json` (already in Phase A matrix). (e) `?mode=preview` is read only from `location.search`, never from the hash or storage; test that hash `#/…mode=preview` and `localStorage.mode` do nothing. (f) Registry count: after a full preview session `makeGated` was called 0 times. | any preview→gated path trips (a)/(b)/(f) |
| T7 | (Decision 1) Per-motor outcome leaks to others | Fixture: CURRENT with motor A eligible, motor B `RELEASE_ELIGIBLE`-but-not-eligible. Expect A shows clearance, B shows "not cleared", gate kind still `CURRENT`, no banner on the whole page. Also assert no `ELIGIBILITY_WITHHELD` value in `GateCause`/`SegregatedCause`/any exported type. | regression to snapshot-level downgrade |
| T8 | (Decision 2) H2 evidence loosened | Table-driven: each Decision-2 condition removed one at a time from the real PREFIX_ONLY fixture → `WITHHELD`; `h2` ∈ {`""`, `"verified"`, `"VERIFIED "`, `null`, `1`, `{}`, `"HISTORICAL_UNVERIFIABLE"`, `"UNVERIFIED"`} → `WITHHELD`. | |
| T9 | Future code reads decisions on the raw type | ESLint-style static test on `no-restricted-properties` equivalent: `operationalAction`, `.decisions`, `.eligibility`, `currentReleaseEligible` forbidden outside `src/contract/**` and the three core `projection.ts` files (an allow-list, itself asserted to be exactly those three). Adding a fourth reader fails the allow-list test. | |

Regression fixtures are the existing real captures (`tests/fixtures/h1h2/*`), regenerated by `tools/capture_h1h2_envelopes.py` when the contract changes.

## 6. Changed-file list for the follow-up (new branch from `cf97c1d`; Phase A branch stays untouched)

New
- `src/contract/gated.ts` — brands, registry, factories, `clearanceOf`, `projectable` sanitiser, `assertBranded`.
- `src/contract/ClearanceChip.tsx` — the only clearance renderer.
- `src/contract/views.ts` — `projectPassport`, `projectInvestigation`, `projectImpact` wrappers over the unchanged cores.
- `src/contract/testing.ts` — test-only helpers (`currentViewForTest(snap, eligibility)`, `historicalViewForTest`); guarded by a static test that nothing under `src/` except tests imports it.
- `tests/types/branding.test-d.ts`, `tests/unit/branding.test.ts`, `tests/unit/gate-fuzz.test.ts`, `tests/unit/arch-guards.test.ts`, extensions to `tests/e2e/gate.spec.ts` (routes × states).

Modified (not original tests)
- `src/contract/gate.ts` — return branded values; delete the `ELIGIBILITY_WITHHELD` branch; tighten PREFIX/UNANCHORED per §4.
- `src/contract/liveLoad.ts` — return the branded gate result.
- `src/passport/passportSource.ts`, `investigationSource.ts`, `impactSource.ts` — `Load` gains required `view`; preview adapters return `PreviewView`; legacy fields (`snap`, `verified`, `reason`, `leaseMs`) kept as derived/readonly so existing consumers typecheck.
- `src/passport/PassportApp.tsx`, `PassportExplorer.tsx`; `src/investigation/InvestigationApp.tsx`, `InvestigationWorkspace.tsx`; `src/impact/ImpactApp.tsx`, `ImpactWorkspace.tsx`, `NodeDetails.tsx`, `ImpactList.tsx`, `ImpactGraphView.tsx` — take `view`/`Facts`, call the wrappers, render clearance only through `ClearanceChip`.
- `tests/unit/gate.test.ts`, `standalone-gate.test.tsx` (Phase A authored tests): the single ELIGIBILITY_WITHHELD expectation changes to the per-motor outcome.

Not modified: the three `projection.ts` cores, `domain/*`, `App.tsx`, `freshness.ts`, `RecallDataSource.ts`, backend, engine, ledger, CI, Codex's branches, `main`.

## 7. Test-migration implications (original tests)

- **Projection tests (`*-projection.test.ts`, ≈ 200 tests): no change** — cores keep raw-snapshot signatures.
- **Page tests that script a `Load` (`passport-app` 23, `investigation-app` 18, `impact-app` 25 tests; load construction is concentrated in about three factory helpers per file, plus the large-fleet case in `impact-app` and a few inline sites):** the scripted `{ snap, verified }` loads no longer satisfy the page contract by design (that is exactly T1). Migration is mechanical: the factories add `view: testing.currentViewForTest(snap, …)` / `historicalViewForTest(...)`; assertions stay unchanged. Requires owner approval (O4 step 3) because it edits original test files.
- **Adapter tests (7 already failing on legacy envelopes)** are migrated together with the strict-envelope fixtures, as already planned.
- **Original Playwright specs:** unchanged by this design; the 23 + 9 failures documented in `FRONTEND_PHASE_A.md` remain a separate step-3 decision.
- If the owner declines editing original page tests, the fallback is to leave `Load` as is and brand inside the page from a `verified` flag — rejected here because a literal `verified: true` would again defeat T1.

## 8. Residual risks and open owner decisions

1. **P1 — preview frame:** preview pages currently show findings/actions inside a labelled frame. Proposal: allowed only inside that frame, never through `ClearanceChip`. Confirm.
2. The data-level sanitiser removes a `NOT_CLEARED` motor's decisions, so Investigation/Impact show that motor without a finding ("recall status withheld"). Alternative: keep `finding` (non-clearing) and strip only `action`; needs a core change, so deferred.
3. The unexported-core approach leaves `operationalAction` readable inside three files; the allow-list test (T9) makes that set explicit and closed.
4. `Facts` omits `notifications` and `comparison`; if a standalone view needs obligations they must be re-added as an explicit, non-clearing field.
5. Main app `App.tsx` is out of scope and still has its own gate; unification stays Phase B.

## 9. Order of work (when approved)

(1) Gate delta + brands + wrappers + new type/unit/arch tests, no original test edits — standalone pages keep working because `Load` keeps its legacy fields during this step, and the wrappers are opt-in. (2) Switch the three pages to `view` (this is the step that needs the page-test migration approval). (3) Delete the legacy fields and turn on the allow-list/static tests as blocking. Each step lands as its own commit on the follow-up branch.
