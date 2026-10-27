# Branded views: implementation report

Branch `feature/frontend-branded-views`, based on Phase A `cf97c1d`. Design: `plan/frontend-branded-views@2bc303430fc98a1ac30dec8d8893e1feca69707a`
(`docs/FRONTEND_BRANDED_VIEWS_DESIGN.md`, **unchanged**). This document records the revisions made since that design, on owner decision.

## Revisions to the approved design (owner decisions)

1. **Decisions of a non-cleared motor are preserved** in a fully CURRENT snapshot. Findings, reason codes, evidence and holds stay visible. Only
   the clearance-permitting claim is withheld. The three projection cores were narrowly changed: `action` is replaced by three separate fields,
   `hold` (a recall hold is in effect), `clearance` (`CurrentClearance | "HOLD" | "NOT_CLEARED"`, minted only by `clearanceOf`) and, for an explicit
   preview only, `recordedAction`. No page infers clearance from a finding or from a historical action.
2. **`ELIGIBILITY_WITHHELD` is not a gate cause.** It is a per-motor presentation outcome (`clearanceOf` -> `NOT_CLEARED`). It never downgrades another motor.
3. **PREFIX_ONLY** is segregated only when structured metadata establishes H2 `VERIFIED` and an integer `anchoredSequence` in 1..sequence.
   Missing -> `MISSING_METADATA`, unknown value -> `UNKNOWN_STATE`, `UNVERIFIED`/`HISTORICAL_UNVERIFIABLE` -> `INTEGRITY`, out of range -> `CONTRADICTORY`.
4. **UNANCHORED** is only explicitly unverified local claims: `anchoredSequence === null`, `h2 === "UNVERIFIED"`, nothing eligible. Otherwise WITHHELD.
5. **Preview** (explicit `?mode=preview`) may show synthetic evaluator findings and recorded actions inside a visibly labelled synthetic preview
   ("Synthetic evaluator output ... (preview; not an authorization)"). It never uses `ClearanceChip`, never carries checkpoint/eligibility/freshness
   (stripped by `makePreview`, even if the dataset forges them), and never becomes live.

## What was built

`src/contract/`: `clearance.ts` (vocabulary, `claimFor`, fail-closed), `gated.ts` (branded `GatedSnapshot`/`HistoricalView`/`PreviewView`, WeakMap
registries, `clearanceOf`), `ClearanceChip.tsx` (the only renderer of release wording; `ClaimChip`/`ClaimText`), `views.ts` (the only place a view becomes a
projection), `testing.ts` (test-only constructors), `gate.ts` (returns branded views; `evaluateDetailed`), `liveLoad.ts` (returns `view`).
Loads from the three sources carry `view: PageView`, no `verified` boolean and no raw `snap`. Workspaces and tables take `Facts` (no decisions/eligibility/checkpoint).

## Test migrations of original tests

Factories in `passport-app`, `impact-app`, `investigation-app` tests: `{ snap, verified: true, ... }` became `{ view: gatedForTest(snap), ... }` and
`{ snap, verified: false, ... }` became `{ view: historicalForTest(snap), ... }`. `load.verified` checks became `isGated(load.view)` (preview adapter tests also
assert `isPreview`). No behavioural assertion was removed or skipped. Assertions that changed:

| # | Test | (a) original | (b) conflict | (c) replacement | (d) unsafe old behaviour rejected by |
|---|---|---|---|---|---|
| 1 | impact-projection "carries the evaluator's finding unchanged" | `status` matches `action: d.operationalAction` | copying the raw action lets a page treat it as clearance | `hold` and `clearance` (`NOT_CLEARED` without a resolver), no `action` property | `.not.toHaveProperty("action")`; branding `claimFor` fail-closed test; mutation M4 |
| 2 | investigation-projection "copies decisions unchanged" | `decision` matches `action` | same | same | same |
| 3 | passport-projection "copies the engine decision unchanged when verified" | `recall` matches `action` | same | same | same |
| 4-6 | "imports only ..." purity tests (passport, impact, investigation projection) | exact import list | cores now import the pure `../contract/clearance` | list plus `../contract/clearance`; no-I/O regexes unchanged | arch-guards (allow-lists for unwrapping/minting) |

Phase A tests of mine also changed: `gate.test.ts` ELIGIBILITY_WITHHELD test replaced by "stays CURRENT, only that motor `NOT_CLEARED`"; PREFIX H2 test now
distinguishes INTEGRITY / UNKNOWN_STATE / MISSING_METADATA. `standalone-gate.test.tsx` passed unchanged.

## New tests

`branding.test.tsx` (18; includes `@ts-expect-error` type cases), `gate-fuzz.test.ts` (12,000 mutated real envelopes plus the Decision-2 table),
`arch-guards.test.ts` (10), `branded-pages.test.tsx` (7), and 7 browser tests in `tests/e2e/gate.spec.ts` (per-motor `not_cleared`, forged-preview).
Mutation checks (all caught): PREFIX accepts any H2; historical keeps decisions; clearance without the per-motor set; unknown action treated as release;
UNANCHORED accepts H2 VERIFIED; withheld eligibility downgrading the gate.

## Results

- `tsc --noEmit`: clean. `npm run build`: ok. `snapshot:check`: ok.
- Vitest: 286 tests, 276 pass, 10 fail. The 10 are identical to the Phase A baseline (6 legacy-envelope adapter tests, 1 passport stale-records (O3), 3 OP-OBSERVATION-21 (O2)); none new.
- Gate browser matrix (`playwright.gate.config.ts`): 61/61 pass.
- Default Playwright vs the legacy 73f3bdb backend: 125 tests, 102 pass, 23 fail (same count and class as Phase A: the strict gate withholds that backend's legacy envelope).
- Not re-run in this task: the real H1/H2-backend Playwright run (Phase A: 9 class-A failures).

## Remaining H1/H2 integration dependencies

- `App.tsx`, `freshness.ts`, `RecallDataSource.ts` (Codex-owned) still need to use this one gate; not touched here.
- Backend items D2-D10 from the audit; live API privacy; the 23 + 9 original e2e failures need the legacy fixtures/backend updated by their owner.

## Security limitations

Brands and WeakMaps are developer-misuse protection, not a security boundary: a malicious script in the page can bypass them. `GatedSnapshot.facts` holds the
validated object typed as `Facts`; hiding fields in the UI is not API-level access control. There is no client-side cryptographic verification: the backend's
integrity and H2 checks remain authoritative, and the gate trusts their structured metadata.
