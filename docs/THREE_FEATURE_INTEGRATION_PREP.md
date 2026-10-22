# Three-feature integration preparation

Temporary branch `integration/three-features-prep`, based on `f9282101159b6b6806974848d7c351999098d792` (frozen A31 base). **Local only. Not pushed, not merged, no PR.**

Inputs, by exact SHA:

| Feature | SHA |
|---|---|
| Passport | `caf651f60ef9a6444239401cee4609ad9eaf188f` |
| Investigation | `899456252c74f76cd30527baaa7dc778686ff62d` |
| Impact graph | `68cdef8a507378bc291493c3bb0ce5ee6d22d45b` |

Codex owns CI and H1/H2. Nothing here touches them.

## Recommendation: **REVISE**

- The combined branch is clean, additive and fully green (section 5). It is fine as an isolated staging artifact for owner review.
- It is **not** ready to integrate past the H1/H2 contract. Three of the revisions below are required first:
  1. fail-closed freshness classification in the three standalone adapters (finding F1);
  2. one shared adapter module, so H1/H2 changes land in one place (section 3);
  3. a decision on whether standalone pages may show operational action labels at all (finding F2).
- No standalone page was found to display a recall finding or action outside the old verified state. The old gate is the only gate, though, and it is replicated three times (F1, F2).

## 1. Compatibility audit and conflict matrix

| # | Area | Result | Detail |
|---|---|---|---|
| 1 | Page entry points | OK | `index`, `passport`, `investigation` and `impact.html`, each with its own `src/<page>/main.tsx`. No page imports another page's source. Each HTML loads only the shared base stylesheet and its own CSS. |
| 2 | Vite multipage | **Conflict, resolved** | All three branches replace the same `build: {...}` line in `vite.config.ts`. Textual conflict twice (investigation, then impact). Resolved by one input map (section 2). The only file touched by more than one branch. |
| 3 | Snapshot types | OK | None of the branches touches `src/domain/*`. All three import `RecallSnapshot` and `validateSnapshot` unchanged. |
| 4 | Freshness and checkpoint assumptions | **Risk** | All three call `verifyFreshness` unchanged. All assume status is exactly `VERIFIED_ANCHORED_SYNTHETIC` and lease is at most 5 s, because `verifyFreshness` does. See F1, F4. |
| 5 | Error-string dependence | **Risk (F1)** | Each adapter decides "withhold everything" versus "show non-current" by testing the message with `/regression/i`. Same regex in all three. |
| 6 | Frontend timeouts | Consistent, duplicated | 4 s live, 6 s or 4 s preview, hard-coded in three `getJson` copies. Main app is 4 s. Main's timeout message says "capture outcome may be unknown"; standalone pages are read-only so they do not. |
| 7 | Package and lockfile | OK | Only passport changes them: `uqr 0.1.3` (dependency) and `jsqr 1.4.0` (devDependency). Git merges `package.json` and `package-lock.json` without conflict. `npm ci` succeeds, 0 vulnerabilities reported. |
| 8 | Navigation and deep links | **Gap** | Each page links only to `./index.html` and to itself. No cross-links among passport, investigation and impact, and the console does not link to them. Deep links are page-local hash routes. Per-unit console links (`./index.html#/unit/<id>/…`) work live. In preview mode they leave the preview and open the live console. |
| 9 | Privacy and shipment fields | **Inconsistent (F3)** | Customer and destination are omitted in every UI. Shipment id and time: passport omits both; investigation and impact show `shipmentId` and `shippedAt`. |
| 10 | Fixture/preview versus live | OK, with F5 | Preview is opt-in by `?mode=preview`. Live mode never fetches preview data and has no fixture fallback (each has a test). Preview files are static and served from the same origin. |
| 11 | Browser test ports | **Conflict, fixed on this branch (F6)** | Investigation spawns servers on 4191–4195. Impact also used 4191 and 4192, so under 2 parallel workers they could collide. Passed in two full runs by luck. Impact moved to 4196 and 4197 here. Existing: 4173 (shared), 4182–4184. |
| 12 | Build and test commands | OK | Same scripts for all: `tsc --noEmit`, `vitest run`, `npm run build`, `npx playwright test`. Playwright rebuilds and runs one shared seeded server. |
| 13 | Cross-feature accessibility | OK, with a gap | axe (WCAG 2.1 AA) passes on all pages at desktop and mobile in each feature's tests, and all 64 pass combined. Gap: primary nav differs on every page and no page offers the other two. Each has a skip link, one `h1`, `main`, and a nav labelled "Primary". |
| 14 | Regression and recovery | OK, with a gap (F7) | Each page withdraws on outage, regression and hidden tab, and recovers on the next verified snapshot. The monotonic `previous` watermark lives in one page instance, so a reload or a second page starts with none. |

## 2. Combined Vite input map (implemented)

```ts
const page = (file: string) => fileURLToPath(new URL(`./${file}`, import.meta.url));
input: { main: page("index.html"), passport: page("passport.html"),
         investigation: page("investigation.html"), impact: page("impact.html") }
```

Build output has all four HTML files. The shared React chunk is reused. Each page's own bundle is 50–55 kB, plus its own CSS.

## 3. Design: adapter strategy, navigation, test matrix

**Adapter strategy (proposed, not implemented).** The three `Live*Source` classes and three `getJson` copies are the same logic. Replace them with one module, for example `src/integration/publicationGate.ts`. It would hold:
- one GET-only `getJson` with a single timeout constant;
- one `loadVerified(previous)` returning `{snap, verified, reason, leaseMs}` or throwing;
- one **allow-list** of failure causes that may still show non-current genealogy (stale lease, unanchored, clock skew). Everything else throws, and the page withholds. This is fail-closed, unlike the current "everything except /regression/" rule;
- a typed error class from the gate, not message matching;
- one place to add the H1/H2 checkpoint, publication and eligibility checks.

It is a refactor of non-safety frontend files, so it was left for a decision. It must not edit `freshness.ts`, and it wraps `verifyFreshness` as a black box.

**Navigation (proposed).** A shared header listing Console, Passport, Investigation and Impact graph. Cross-links are unit-scoped and plain hrefs: console unit page to passport and investigation; impact motor node to passport; investigation cluster to impact lot. Preview pages must link only to preview pages of the same page (`?mode=preview`). The QR code keeps encoding only the passport URL.

**Test matrix.**

| Suite | Count combined |
|---|---|
| Vitest | 186: base 33, passport 47, investigation 58, impact 48 |
| Playwright | 64: base 29, passport 12, investigation 10, impact 13 |
| Cross-page (to add) | all pages × {verified, unanchored, stale, outage, regression, hidden tab, invalid journal version}, and one shared-gate test |

The cross-page probe in section 4 was run once as a throwaway test and not committed.

## 4. Findings

**F1: fail-open classification (REVISE).** Any freshness failure whose message lacks "regression" returns `verified: false` with the snapshot, and the page then shows non-current content. Checked by feeding six live-adapter variants to all three pages (throwaway probe; "finding" means engine finding or action):

| Variant | Passport | Investigation | Impact |
|---|---|---|---|
| anchored and fresh | shows recall context | shows tasks | shows findings |
| unanchored | content, recall withheld | withheld | genealogy, findings withheld |
| sequence 0 | content, recall withheld | withheld | genealogy, findings withheld |
| empty head hash | content, recall withheld | withheld | genealogy, findings withheld |
| hypothetical new status | content, recall withheld | withheld | genealogy, findings withheld |
| stale | content, recall withheld | withheld | genealogy, findings withheld |

Today no finding leaks. But "invalid journal version" (corrupt or missing sequence or head hash) is treated like "stale" and its record data is still shown. A future H1/H2 error (checkpoint mismatch, publication blocked) not containing "regression" would also be shown as non-current genealogy. That is the wrong default for a safety contract.

**F2: operational action labels in standalone pages.** Investigation and impact show the evaluator's `operationalAction` (including the text "Release eligible") when verified. Passport projects it too. They gate it only on `verifyFreshness`. If H1/H2 adds conditions for release eligibility, these pages would display the old state unless they use the same gate. Recommendation: either route through the shared gate or show findings without action labels until H1/H2 lands. Not changed here.

**Can a standalone page bypass the main app's verified publication gate?** Not found for live data. All three run the same `verifyFreshness`, withhold findings and actions otherwise, and have tests. Differences from the main app:
- The main app shows nothing on any freshness failure; the standalone pages may show non-current genealogy (F1).
- The main app skips polling while hidden; the standalone pages keep polling but withhold on hidden state.
- `GET /api/snapshot` itself is unauthenticated, loopback-only, and returns decisions and the full ledger to any client. That is a server property, and UI omission is not API-level access control.
- Preview mode is not gated by design (static, labelled). Its data uses the same unit ids as live (`MTR-26003`), with different decisions.

**F3: shipment and privacy consistency.** Pick one policy. Passport (strictest) omits shipment id and time; the other two show them. Static files `snapshot.json`, `passport-preview.json`, `investigation-demo.json` and `impact-demo.json` contain customer, destination and `OP-*` actor strings, and contain `RELEASE_ELIGIBLE` decisions. They are synthetic and served at `/data/*.json` from `dist`.

**F4: checkpoint assumptions.** Page logic assumes status `VERIFIED_ANCHORED_SYNTHETIC` and a lease of at most 5 s only through `verifyFreshness`. Tests in all three features build fixtures with that string.

**F5: preview versus live.** Preview and live pages share an origin and unit ids. Banners exist, but nothing prevents a preview link being followed by someone expecting live data.

**F6: port collision (fixed on this branch).** Section 1, row 11.

**F7: no cross-reload watermark.** A reload or a second tab starts with `previous = null`, so a rollback before first load is not detected. This also holds for the main app. A shared gate could keep the watermark in `sessionStorage`, which is a design decision.

## 5. Code changes on the branch

Merge commits of the three SHAs (git merges them without conflict, apart from the Vite file). Then:

1. `recall-ui/vite.config.ts`: combined input map (section 2).
2. `recall-ui/tests/e2e/impact.spec.ts`:
   - ports `4191`/`4192` to `4196`/`4197` (F6);
   - `test.setTimeout(90_000)` on the large-fleet test, which took 23 s alone and exceeded the 30 s default once under the combined suite load.

Files changed outside `recall-ui/src/{passport,investigation,impact}`, `recall-ui/tests`, `recall-ui/tools`, `recall-ui/public/data`, the three HTML entries, `vite.config.ts`, `package*.json` and `docs`: **none**. No change to `App.tsx`, `freshness.ts`, `RecallDataSource.ts`, `server.py`, journal, anchors, engine, ledger, backend or any release-state wiring.

The impact branch at `68cdef8` still has the 4191/4192 ports and the 30 s timeout. Fixing them there needs separate authorization.

## 6. Full combined results

| Check | Result |
|---|---|
| `tsc --noEmit` | clean |
| Vitest | 12 files, 186 passed |
| `npm run build` | OK, four HTML entries |
| Playwright | 64 passed, twice with the port fix |
| Backend `unittest` (36) | OK |
| `snapshot:check` | current |

One earlier combined run failed once: the impact large-fleet test hit the 30 s limit (see section 5). Generated screenshot and latency files were reverted after each run.

## 7. Expected H1/H2 integration points

1. `verifyFreshness` status and lease contract (`freshness.ts`): all three adapters, all fixtures in tests.
2. Any new error type or text from `verifyFreshness`: replaces the `/regression/i` test in three places (F1).
3. Release eligibility under H1/H2: the action labels in investigation, impact and passport (F2).
4. Snapshot shape: any new field for checkpoint, publication state or eligibility goes through `validateSnapshot`. The projections ignore unknown fields.
5. Server envelope: a changed `/api/snapshot` response or a new status endpoint changes the single shared adapter, if built.
6. Test fixtures: `freshDataset`, `freshStage`, `passportHelpers` hard-code `VERIFIED_ANCHORED_SYNTHETIC`, as does the live behaviour.
7. Lease and polling: 2 s poll, 5 s lease, 4 s timeout, duplicated in the three apps.

Ambiguities, documented and not resolved: whether H1/H2 keeps `VERIFIED_ANCHORED_SYNTHETIC` as a status (F4); whether non-current genealogy is acceptable after H1/H2 (F1); whether pages may show action labels (F2).

## 8. Known limitations

- Privacy: UI omission of customer, destination and actor identifiers is not access control. The API and static files include them.
- Shipment-field policy is inconsistent across pages (F3).
- Each page has its own watermark, which resets on reload (F7).
- Duplicated adapter code, and fail-open on unrecognized freshness errors (F1).
- No cross-links among the three pages, and inconsistent navigation.
- Impact large-fleet browser test is slow (about 23 s alone).
- The backend test `application/test_application.py:66 test_seed_safety_cases_and_idempotence` is a known flaky test (about 1 run in 4), unrelated and untouched. It passed in both runs here.
