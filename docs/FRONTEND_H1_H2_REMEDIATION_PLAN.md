# Frontend Remediation Plan — shared strict checkpoint/eligibility contract (DESIGN ONLY)

Status: proposal for owner approval. Nothing here is implemented.
Contract basis: H1/H2 Option A at `f9dcf56ae52b095a3af05b8fc45a2568cd5642fe`. Frontend basis: combined branch `integration/three-features-prep @ 73f3bdbd78ee8bdf4b323457ba2f036f16fb82d9`. Audit: `review/h1-h2-independent-audit @ e63bf90919b1765ef9d7d00f60a69c713323c82c`.
Out of scope: backend findings D2–D10; Codex's H1/H2 branch; main; merges/PRs/deploys.

## 1. Findings addressed

| ID | Finding | Root cause (verified in code) |
|---|---|---|
| D1 | Standalone pages bypass the strict gate | `freshness.ts` validates `checkpoint`/`eligibility` only `if (snap.checkpoint)` and accepts `VERIFIED_PREFIX_SYNTHETIC`; the unconditional `!snap.checkpoint \|\| !snap.eligibility` rejection is only in `BackendRecallDataSource.accept`. Passport/Investigation/Impact call `validateSnapshot` + `verifyFreshness` directly, so `ANCHORED_PREFIX_ONLY` becomes `verified: true`. |
| F1 | Integrity failures distinguished by exception text | All three adapters: `if (/regression/i.test(message)) throw …; else return {verified:false, reason: message}`. Any other error text (including a new integrity message) fails *open* into a "verified:false, snap still handed to the page" path; the classification depends on message wording. |
| F2 | Old release labels survive on standalone pages | Projections read `decision.operationalAction` / `evidenceFinding` directly (`passport/projection.ts:264`, `investigation/projection.ts:331,409`, `impact/projection.ts:331`); none consult `snap.eligibility`. |
| F3 | Preview JSON carries unnecessary identifiers | `public/data/{passport-preview,investigation-demo,impact-demo,snapshot}.json` contain `customer`, `destination`, `shipmentId` and `OP-*` operator ids, and are served to anyone who can reach the origin. |

Fact that narrows the work: all four pages read **only** `GET /api/snapshot` (and POST commands on the main app). They never call `/decisions` or `/investigation`, so audit D2 does not affect the frontend.

## 2. Design: one typed, fail-closed gate

### 2.1 New module `src/contract/gate.ts` (pure, no I/O, no backend re-verification)

The gate never recomputes hashes, replays, or checkpoints. It only **refuses to trust** a snapshot unless the backend's own statement is complete, self-consistent and CURRENT.

```ts
type GateCause =
  | 'PREFIX_ONLY' | 'UNANCHORED' | 'ANCHOR_INVALID'
  | 'VERIFYING' | 'MISSING_METADATA' | 'UNKNOWN_STATE' | 'CONTRADICTORY'
  | 'LEASE_EXPIRED' | 'REGRESSION' | 'INTEGRITY' | 'TRANSPORT' | 'PREVIEW';

type Gate =
  | { kind: 'CURRENT';  view: GatedSnapshot; leaseMs: number }
  | { kind: 'SEGREGATED'; cause: 'PREFIX_ONLY'|'UNANCHORED'; view: HistoricalView; reason: string }
  | { kind: 'WITHHELD'; cause: Exclude<GateCause,'PREFIX_ONLY'|'UNANCHORED'|'PREVIEW'>; reason: string; lastAccepted?: { archiveId; sequence; verifiedAt } }
  | { kind: 'PREVIEW'; view: HistoricalView; reason: string };       // only constructed by explicit preview sources

function evaluate(envelope: Envelope, previous: Accepted | null, now: number): Gate
```

Rules (first match wins, **default = WITHHELD/INTEGRITY**; the function body is a total `switch` and the whole call is wrapped so any thrown exception yields `WITHHELD/INTEGRITY`):

1. Transport/HTTP: 200 required. 503 with `state: VERIFYING` → `WITHHELD/VERIFYING` (transient, not an invalid verdict, never shown as current, never promotes the previous snapshot). 409 with `state: ANCHOR_INVALID` → `WITHHELD/ANCHOR_INVALID`. Any other status/body → `WITHHELD/TRANSPORT`. Status handling reads the **structured body field** (`state`, `error`), never message text.
2. Structure: `schemaVersion`, `freshness`, `checkpoint`, `eligibility` all present and typed; absent → `WITHHELD/MISSING_METADATA` (a legacy envelope, even with `VERIFIED_ANCHORED_SYNTHETIC`, is never CURRENT).
3. `checkpoint.state` must be one of the closed enum; any other string (including case/whitespace variants) → `WITHHELD/UNKNOWN_STATE`.
4. Cross-field consistency: `ANCHORED_CURRENT ⇔ freshness.status === VERIFIED_ANCHORED_SYNTHETIC ⇔ !checkpointRequired`, `h2 === VERIFIED` for CURRENT, `PREFIX_ONLY ⇔ VERIFIED_PREFIX_SYNTHETIC`, `UNANCHORED ⇔ HISTORICAL_UNANCHORED` → else `WITHHELD/CONTRADICTORY`.
5. State dispatch: `ANCHOR_INVALID` → WITHHELD; `UNANCHORED` / `ANCHORED_PREFIX_ONLY` → `SEGREGATED` (§3); `ANCHORED_CURRENT` → continue.
6. Eligibility invariant (for CURRENT only): every unit has a boolean `currentReleaseEligible`; `true` requires no notification for the unit, ≥1 decision, and all decisions `RELEASE_ELIGIBLE`; eligibility for an unknown unit id is `CONTRADICTORY`.
7. Lease: ISO-8601 Z timestamp, `0 < maxAgeSeconds ≤ 5`, age in `[-1 s, maxAge)` → else `WITHHELD/LEASE_EXPIRED`.
8. Regression vs `previous`: archive id, sequence, head hash, verifiedAt, events, decision versions — **structural comparison inside the gate** (not via exception text) → `WITHHELD/REGRESSION`, which also clears the stored `previous`. A CURRENT→PREFIX_ONLY transition is *not* a regression; it is `SEGREGATED` immediately (the sequence check uses the same archive and non-decreasing sequence).

Single source of truth question: `freshness.ts` (Codex-owned) already implements rules 6–8 with thrown `Error`s. To avoid two diverging gates, the final state should be **one** implementation. Phase A (§5) implements `gate.ts` independently and calls the existing `verifyFreshness` only as an *additional* tripwire (any throw → WITHHELD, never parsed). Phase B (needs Codex) makes `freshness.ts` and `BackendRecallDataSource.accept` delegate to `gate.evaluate`, deleting the duplicate.

### 2.2 Branded views — make the unsafe label unrepresentable

Projections stop receiving raw `RecallSnapshot`. They receive one of:

- `GatedSnapshot` (only `gate.evaluate` can construct it; `unique symbol` brand): decisions are re-expressed as `displayAction: 'HOLD' | 'ELIGIBLE_CURRENT'`. `ELIGIBLE_CURRENT` is produced **only** when `eligibility[unit].currentReleaseEligible === true` **and** the decision is `RELEASE_ELIGIBLE`; a `RELEASE_ELIGIBLE` decision with eligibility false becomes `'NOT_CLEARED'` (shown as "Not cleared — current eligibility withheld").
- `HistoricalView`: genealogy/event facts plus decisions as `recorded: { finding, action }` with no component able to render an action chip or "Release eligible" from it; holds are carried as `HOLD_RECORDED`.

A repo-wide test (§4, FE-ARCH-1) fails if any file under `src/passport|investigation|impact|views` references `.operationalAction`, `RELEASE_ELIGIBLE`, or `currentReleaseEligible` outside `src/contract/`. This also moots F2: there is no old label to leak.

### 2.3 Adapters

`LivePassportSource / LiveInvestigationSource / LiveImpactSource / BackendRecallDataSource` become thin: fetch → `gate.evaluate` → return `Gate`. The `/regression/i` branches are deleted. Pages switch on `gate.kind`/`gate.cause` (closed unions; TypeScript `never` exhaustiveness check), not on strings. Preview sources are the only constructors of `kind: 'PREVIEW'` and are selected only by an explicit `?mode=preview` (existing), never as a failure fallback (FE-PRV-1).

## 3. Segregation policy (explicit; requires owner review)

| Gate | Genealogy / events | Decision labels | Action chips, "Release eligible", "Excluded with evidence" as outcome, task lists, counts of cleared | Banner |
|---|---|---|---|---|
| CURRENT | full | full | per `displayAction` | none |
| SEGREGATED / PREFIX_ONLY | shown inside a labelled **"Historical — checkpoint required"** frame (facts, lots, events, source ids) | shown only as "Recorded (historical): <finding>", never an action; holds shown as "Hold remains in effect" (conservative) | **none** | persistent, role=alert: "Current release eligibility withheld for every motor. A new independently protected checkpoint is required." |
| SEGREGATED / UNANCHORED | same frame, label "Historical — no trusted anchor" | same | none | "No trusted external anchor." |
| WITHHELD (ANCHOR_INVALID, REGRESSION, INTEGRITY, CONTRADICTORY, MISSING_METADATA, UNKNOWN_STATE, LEASE_EXPIRED, TRANSPORT) | **hidden** | hidden | none | fixed-code message; for REGRESSION/LEASE_EXPIRED only the last-accepted `{archiveId, sequence, verifiedAt}` and "not current" |
| WITHHELD / VERIFYING | hidden (do not reuse previous) | hidden | none | "Verification in progress" (distinct from invalid) |
| PREVIEW | shown | shown | chips allowed only inside a "PREVIEW — synthetic, not a ledger" frame with a different visual treatment; **eligibility is never asserted** | persistent preview banner |

Policy rationale: under PREFIX_ONLY the backend still attests the hash chain is a verified extension of a trusted prefix, so facts are trustworthy but not current-clearing; under any integrity-type cause we cannot say the facts are the ledger's. Open owner decision O1: whether PREFIX_ONLY should show the historical frame (proposed) or hide genealogy as the main app's "withheld" panel does today. The main app's current behaviour (hiding everything on prefix-only) is retained as the conservative default until O1 is answered.

## 4. Adversarial regression matrix

Pages: M = main app, P = passport, I = investigation, G = impact graph. Expected result is the same for every page unless noted. "Absent" = text `Release eligible`, `Excluded with evidence` (as an outcome), `cleared`, any action chip, any task list, any eligible count.
Harness: the existing browser server fixture from f9dcf56 (`tests/browser_server.py`) with its own ports (≥4301) and a config without `webServer`; plus mocked envelopes for envelope-level cases. Each case must fail on the current `73f3bdbd` code where noted (★ = reproduces today, by the audit probe).

| ID | Input | Expected on M/P/I/G |
|---|---|---|
| FE-01 | CURRENT, eligible motor | Eligible label only on that motor; others per decision |
| FE-02 ★ | PREFIX_ONLY after a capture on another motor; decision raw `RELEASE_ELIGIBLE`, eligibility false | Segregated frame; no eligible label/chip/"Excluded" outcome; banner present; holds visible |
| FE-03 | UNANCHORED (server without checkpoint) | Segregated "no trusted anchor"; absent set |
| FE-04 | 409 `ANCHOR_INVALID` (rollback/tamper) | Withheld; genealogy hidden; fixed code only; no stack/path text |
| FE-05 | 503 `VERIFYING` | Withheld/VERIFYING, distinct text; previous CURRENT view not retained |
| FE-06 | 400 `INVALID_REQUEST` | Withheld/TRANSPORT |
| FE-07 ★ | Legacy envelope: status `VERIFIED_ANCHORED_SYNTHETIC`, no `checkpoint`/`eligibility` | Withheld/MISSING_METADATA on all four (today P/I/G accept) |
| FE-08 | `checkpoint` present, `eligibility` missing | Withheld/MISSING_METADATA |
| FE-09 | `checkpoint.state` = `"ANCHORED_CURRENT "`, `"anchored_current"`, `""`, `null`, number, object | Withheld/UNKNOWN_STATE for each |
| FE-10 | CURRENT with `freshness.status` = PREFIX | Withheld/CONTRADICTORY |
| FE-11 | PREFIX_ONLY with `freshness.status` = ANCHORED | Withheld/CONTRADICTORY |
| FE-12 | CURRENT with `h2 != VERIFIED` | Withheld/CONTRADICTORY |
| FE-13 | `checkpointRequired` inconsistent with state | Withheld/CONTRADICTORY |
| FE-14 | `currentReleaseEligible:true` while decision is `RECALL_HOLD` | Withheld/CONTRADICTORY; never an eligible label |
| FE-15 | eligible true while unit has a notification obligation | Withheld/CONTRADICTORY |
| FE-16 | eligibility key for a unit not in `units`; unit missing from eligibility; non-boolean values (`"true"`, 1) | Withheld |
| FE-17 | Decision `RELEASE_ELIGIBLE`, finding contradicts action | Withheld (validateSnapshot) |
| FE-18 | Unknown `operationalAction` string | Withheld; no default-to-eligible |
| FE-19 | Poll: CURRENT → PREFIX_ONLY | Previous eligible view removed on the same render; no flash retained by cache |
| FE-20 | Poll: PREFIX_ONLY → CURRENT (new checkpoint) | Eligible labels return only after a full CURRENT gate pass |
| FE-21 | Poll: CURRENT → 409 → CURRENT | During 409 nothing shown; after, as FE-01 |
| FE-22 | Regression: lower sequence / same sequence different head / different archiveId / older `verifiedAt` / removed event / lower decision version | Withheld/REGRESSION; `previous` cleared; reload requires owner review text; no message-text dependence (run with the localized/renamed message to prove it) |
| FE-23 | Lease: expired, > 5 s, ≤ 0, non-finite, malformed timestamp, skew > 1 s | Withheld/LEASE_EXPIRED |
| FE-24 | Hidden tab for > lease | Withdrawn; returns only after a fresh CURRENT |
| FE-25 | Network failure / abort / timeout (4 s limit unchanged) | Withheld/TRANSPORT; **no preview fallback** |
| FE-26 | Live server unreachable and `preview` assets present | Live page stays withheld; preview only with explicit `?mode=preview` (FE-PRV-1) |
| FE-27 | Unrecognized extra top-level fields / extra enum states | Ignored fields do not alter result; unknown state per FE-09 |
| FE-28 | Deep link (`#/unit/MTR-26003/decision`, passport QR route, impact node route) opened while SEGREGATED/WITHHELD | Route resolves to the withheld/segregated frame; no unit-level eligible text; invalid routes stay invalid |
| FE-29 | Print / "copy link" / QR render paths under non-CURRENT | QR encodes only the stable passport URL, never a status |
| FE-30 | Persistence: `localStorage/sessionStorage/history.state` hold last view | Reload under non-CURRENT shows nothing from storage; (assert no key contains decisions) |
| FE-31 | Screenshot/doc fixtures (`docs/phase31-screenshots`) | Not used as runtime inputs |
| FE-32 | Concurrent responses out of order (older CURRENT arrives after newer PREFIX_ONLY) | Older is dropped (sequence regression), view stays segregated |
| FE-33 | Mixed fleet: one motor eligible, one held, state PREFIX_ONLY | No motor eligible |
| FE-34 | Mixed fleet in CURRENT: one RELEASE_ELIGIBLE decision with eligibility false (notification) | That motor "Not cleared"; others unaffected; no global blank unless O1 says so |
| FE-35 | Large fleet (100 motors) CURRENT/PREFIX gating cost | Gate evaluation < 20 ms; UI remains responsive |
| FE-PRV-1 | Preview selected explicitly | Preview frame + banner; no eligibility assertion; never reachable by failure |
| FE-PRV-2 | `dist/` scan after build | No `customer`, `destination`, `OP-*`, unneeded `shipmentId` values in any served JSON/JS/map |
| FE-PRV-3 | Preview JSON validates through the gate as `PREVIEW` only (never as CURRENT) | Pass |
| FE-ARCH-1 | Static check: no direct use of `operationalAction`/`RELEASE_ELIGIBLE`/`currentReleaseEligible` outside `src/contract/` | Pass |
| FE-ARCH-2 | Static check: no `/regression/i` or `.message` classification in adapters | Pass |
| FE-ARCH-3 | Exhaustiveness: adding a new `GateCause` fails compilation until every page handles it | Pass |
| FE-A11Y-1 | Banner `role=alert`, focus order, colour-independent state marker, mobile 390 px layout | Pass |

Existing Vitest/Playwright suites (186 / 64) stay and must remain green; **no assertion is weakened**. The 3 Vitest + 4 browser tests incompatible with the strict contract (audit §5) are migrated only in new files after owner approval.

## 5. What can be done before backend fixes vs what depends on Codex

### Phase A — safe now (new files and feature-branch pages only; no edit to `App.tsx`, `freshness.ts`, `RecallDataSource.ts`, backend, evaluator)
1. `src/contract/gate.ts`, `types`, branded views, unit tests for FE-07…FE-18, FE-22, FE-23, FE-27 (mocked envelopes), FE-ARCH-1/2/3.
2. Passport / Investigation / Impact adapters switched to `gate.evaluate`; `/regression/i` removed; pages rendered from `Gate` with the §3 policy.
3. Projections taking `GatedSnapshot`/`HistoricalView`; F2 labels removed structurally.
4. Preview sanitiser + regenerated preview JSON + FE-PRV-*.
5. Browser matrix against the unmodified f9dcf56 backend (FE-02…FE-06, FE-19…FE-21, FE-24…FE-26, FE-28…FE-34) using separate ports.
Prerequisite: the combined branch must contain the f9dcf56 envelope. A clean scratch merge exists (`be1fab6`); the owner must choose whether to merge H1/H2 into the integration line (not done here).

### Phase B — depends on Codex / owner
1. Make `freshness.ts` and `RecallDataSource.accept` delegate to `gate.evaluate`, and `App.tsx` use `Gate` (removes the duplicate gate and the main app's separate `withheld` logic). Codex owns these files.
2. Optional typed error codes exported by `freshness.ts` (not required by Phase A, which never parses messages).
3. Backend-declared structured error bodies for 409/503 beyond today's fixed codes (today `state` and `error` are present; Phase A relies only on those).
4. Live-API privacy (customer/destination/shipmentId/operator ids in `/api/snapshot`): UI minimisation is not access control; needs a backend/owner decision (audit D-class backend item).
5. Test migration of the 8 legacy tests; the O1 policy decision on global vs segregated withholding for the main app.
6. CI wiring (Codex owns CI).

## 6. Open owner decisions
- O1: PREFIX_ONLY/UNANCHORED → segregated historical frame (proposed) vs full withholding on all pages.
- O2: Preview identifier policy: remove `customer`/`destination`/`OP-*` entirely and pseudonymise `shipmentId` (proposed) vs retain pseudonymous tokens; confirm whether preview must still demonstrate shipment impact.
- O3: Should holds be shown while WITHHELD (e.g. last-accepted hold list)? Proposed: no; show only the watermark.
- O4: Merge order of H1/H2 relative to the integration line (owner action).

## 7. Acceptance criteria for implementation approval
Every FE-* row has an automated test; FE-02/07 fail on `73f3bdbd`/`be1fab6` and pass after; full existing suites green with no weakened assertions; `dist/` privacy scan clean; no Phase B file touched; no network I/O outside `/api/snapshot`.
