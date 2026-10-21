# Interactive Recall Impact Graph

Branch `feature/recall-impact-graph`, based on `f9282101159b6b6806974848d7c351999098d792`.
Code commit: `030c6734a79e55943cabba48ef1a8bddaea72529`. The final SHA is reported with the push; a commit cannot contain its own hash.

Standalone page `recall-ui/impact.html` (`/impact.html`). It is read-only, evaluates nothing, and adds no dependency.

## 1. Gap against the existing genealogy

| Existing | Limit |
|---|---|
| `GenealogyGraph.tsx` | One motor at a time (supplier lot, component, motor, shipment). No cross-motor view. It shows the customer name and draws a "synthetic overlay" shipment edge. |
| `LotInvestigation.tsx` / `investigateLot` | A flat table of motors that ever held a lot. No propagation graph, no raw-material backward trace, no DE/NDE scope, no link-integrity issues, no evidence-gap indicators. |

The impact graph starts from a lot (bearing lot or raw-material lot) and follows recorded links to every motor and recorded shipment, in both directions.

## 2. Data contract and projection

`src/impact/projection.ts` is pure. It imports only `../domain/types`. Input is one validated `RecallSnapshot`, a selection `{BEARING_LOT|RAW_LOT, id}` and `{policyId?, recallStatusCurrent}`. Output is `ImpactGraph`: nodes, edges, issues, summary, scope and watermark.

- Engine findings and actions are copied from the snapshot's decisions. Nothing is re-evaluated.
- Operator ids, customer and destination are never carried into the graph.
- `recallStatusCurrent: false` (withheld mode) removes statuses, recalled flags, decision-derived issues, observation nodes and per-finding counts.
- Deterministic: output is sorted and unit-tested for stability. Inputs are deep-frozen in tests.

### Node kinds
Raw-material claim, bearing lot, manufacture record, installed component (current or historical), motor, recorded shipment, rejected observation.

### Edge kinds and the ledger reference that justifies each
| Edge | Ledger field |
|---|---|
| raw claim → manufacture | `BEARING_MANUFACTURED.payload.materialEventId` → `MATERIAL_ALLOCATED` |
| bearing lot → manufacture | `BEARING_MANUFACTURED.payload.lot` |
| manufacture → component | `COMPONENT_INSTALLED.payload.manufacturingEventId` (style CONFLICT if the lots disagree) |
| bearing lot → component (dashed) | install record's own `lot`, with no manufacture link |
| component → motor | the install event's motor |
| motor → shipment | a `MOTOR_SHIPPED` event named by the unit's shipment record, only when ledger-backed |
| lot → observation → motor (dotted) | `SLOT_STATE_VERIFIED.payload.observedLot`, a rejected, untrusted claim |

No edge is drawn from similar identifiers. A missing link is never drawn; it becomes an issue.

### Issues (INFO / UNCERTAIN / CONFLICT)
Always: missing manufacture link, missing material link, lot mismatch, duplicate reference, supplier-claim conflict, manufactured but not installed, lot identity only, removed not eliminated, record superseded, slot outside scope.
Current mode only: exclusion withdrawn, decision cites missing records, ambiguous slot, capture gap, untrusted observation, shipment not ledger-backed.

## 3. Evidence linking rules
1. Every visible edge cites recorded events; the unit test re-verifies each edge against the raw ledger.
2. A claim-only motor (named only by a rejected observation) is shown separately and counted separately.
3. Removal is shown as historical and is never treated as elimination.
4. A shipment record is not delivery or authorization. Customer and destination are omitted.
5. "Excluded with evidence" is scoped to the recall and is never called safe. A lot not named by the recall carries no quality statement.
6. Out-of-scope slots are tagged, not hidden.

## 4. Interaction design
- Custom SVG: no graph library, so no licence, maintenance or bundle question (impact chunk 53.6 kB, 16.7 kB gzip).
- Layered columns (raw, lot, manufacture, component, motor, shipment). Rows are grouped by motor, ordered by finding then id. Position carries no other meaning.
- Pan by drag or arrow keys; zoom by buttons, `+`/`-` or Ctrl+wheel; fit and reset. Nodes are focusable `role=button`, and Enter or Space selects. Line style (solid, dashed, double, dotted) plus the legend carry meaning, not colour alone.
- Trace backward, forward or both along recorded edges. Filter by engine finding (hidden motors are stated as not cleared). Search by record.
- Above 400 nodes the graph draws a window of 40 motors with a pager; the list always has every record, paginated by 100.
- The list view is the accessible equivalent (a table with each record's recorded links). It is the default on narrow screens.
- Details panel: engine finding and action (labelled as copied), issues with cited events, recorded links with their basis, slot history, and the ledger records (type, source and sequence, times, record hash).
- Hash routes: `#/lot/<bearing|raw>/<lot>[/<graph|list>[/<node>]]`. Identifiers are validated and rendered as text only.
- Not-current handling: unverified, expired lease, hidden tab or outage withholds recall status. Unverified or expired data keeps the genealogy, labelled "Not current". An outage or regression withdraws everything. There is no fixture fallback in live mode.

## 5. Adapters
- `LiveImpactSource`: GET `/api/snapshot` only, `validateSnapshot`, unmodified `verifyFreshness`, 4 s timeout, regression throws.
- `PreviewImpactSource`: explicit `?mode=preview&dataset=de|nde|large`. Never verified, always bannered as not a live ledger.

## 6. Real evaluator output versus authored data
`public/data/impact-demo.json` is made by `tools/generate_impact_demo.py`. Decisions in it are real output of the pinned v3 evaluator over a synthetic ledger. Each unit has an origin tag, shown on the page.

| Dataset | Origin tags |
|---|---|
| `de` | SEEDED: 26001–26005. ENGINE_DEMO_EXTRA: 26021–26023. AUTHORED_LINK_EDIT: 26031–26034 |
| `nde` | ENGINE_DEMO_EXTRA: 26101–26105 |

The four AUTHORED_LINK_EDIT units had their link fields edited after capture to create a missing manufacture link, a duplicate reference, a lot mismatch and a missing material link. Their hashes no longer match, and this is recorded in the file.

`large` is AUTHORED stress data (`syntheticScale.ts`). It clones motors under `MTR-S#####` identifiers, and the cloned decisions are copies, not new evaluator output. It is used only in preview and tests.

## 7. Screenshot gallery (`docs/impact-screenshots/`)
01 chooser · 02 graph overview · 03 trace and details · 04 historical removal · 05 list with issues · 06 raw lot · 07 NDE scope · 08 mobile list · 09 mobile graph · 10 large window · 11 live verified · 12 live not current · 13 live withdrawn · 14 unanchored.

## 8. Performance observations
- Projection of 5,627 nodes and 7,125 edges (about 1,500 motors): 268 ms in jsdom/Node.
- Browser: preview `large` first render 4.4 s on the test machine, drawing 156 nodes. This includes loading and validating the stress snapshot. The test asserts under 15 s.
- The draw cap and the motor window bound the SVG cost. The list is paginated.

## 9. Test results
- `tsc --noEmit`: clean.
- Vitest: 81 passed (33 pre-existing, 23 projection, 25 app).
- Playwright: 42 passed (29 pre-existing, 13 new).
- Backend `unittest` (36 tests): OK.
- `snapshot:check`: current.
- `npm run build`: OK, with a second entry.

Coverage:
- Projection: edge justification against the raw ledger; DE-only and NDE-only scope; historical removals; ambiguity; missing links; conflicts; untrusted observations; unshipped motors; withheld mode; no identifier leaks; raw-lot trace; out-of-scope lot; unknown lot; duplicates; scale.
- App: verified, unverified, lease expiry, hidden tab, outage, regression, GET-only, no mutating control, keyboard, list fallback.
- Browser: desktop and mobile overflow plus axe, live outage and stale lease, rollback, hidden tab, unanchored ledger, read-only invariance (SQLite table hashes and anchor file unchanged, only GET requests), large fleet.

Late evidence needs no special handling here: the projection is a pure function of the snapshot, so a refreshed snapshot recomputes. The live test withdraws and then recovers.

## 10. Remaining risks
- Ledger-recorded links are not physical verification. The page says so, but the headline is still a summary.
- Layout is a fixed layered grid. Very wide fan-in (many components per motor) lengthens rows. Windowing bounds this but does not remove it.
- The browser large-fleet timing is dominated by parsing and validating the stress snapshot. A real fleet of that size has not been measured.
- `verifyFreshness` is used unchanged. If Codex's H1/H2 work changes its contract or its error wording (the regression match is a text test), the adapter's classification must be re-checked.
- The pre-existing flaky backend test `application/test_application.py:66 test_seed_safety_cases_and_idempotence` fails about 1 run in 4 when the freshness second rolls over between two `snapshot()` calls. It is unrelated to this change and was not touched.
- Tests that run the full Playwright suite rewrite tracked `docs/phase31-screenshots/*` and `docs/phase31-validation/browser-latency.json`. They were reverted before commit.
- `freshDataset` in tests hard-codes `VERIFIED_ANCHORED_SYNTHETIC`. Live verification is covered by the browser tests against the anchored test server.

## 11. Integration differences
- **Codex / H1–H2 / CI gates:** untouched. No changes to `App.tsx`, `freshness.ts`, `RecallDataSource.ts`, `server.py`, the recall engine, the ledger, audit/anchors or any mutation endpoint. The only shared dependency is `verifyFreshness`, as a black box.
- **`recall-ui/vite.config.ts`:** modified to add a multi-page `build.rollupOptions.input` (`main` and `impact`). The passport branch and the investigation branch edit the same file for their own pages (investigation: `main` plus `investigation`). The three edits conflict textually at the same lines. The resolution is one `input` map with all pages. This branch did not attempt it.
- **Package files:** unchanged on this branch. The passport branch adds `uqr` and `jsqr`. No overlap.
- **Passport and investigation branches:** not merged or cherry-picked. Each page is standalone with its own entry, CSS and tests. The nav links point only to `./index.html`. Consistent cross-links between the three pages are left to integration.
- **Playwright:** each branch's specs use their own page; the seeded server ports used here are 4191 and 4192 (plus the shared 4173).
