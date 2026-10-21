# Evidence-Guided Investigation Workspace: implementation (Design B, Phase 1)

Status: implementation for owner review. Not merged, not deployed, no pull request. Synthetic data only. Loopback only (127.0.0.1).

| | |
|---|---|
| Baseline | `integration/phase31-a31-hardening@f9282101159b6b6806974848d7c351999098d792` |
| Branch | `feature/evidence-guided-investigation` |
| Code commit | `0b7d9c893ff1db4b2cbd96e23c3d3890c2bca9b1` (the commit that contains everything except this file) |
| Final SHA | the head of the branch, reported in the delivery message (a commit cannot contain its own hash) |
| Design | `research/evidence-guided-investigation@4c93077`, `docs/research/EVIDENCE_GUIDED_INVESTIGATION.md` |

The passport branch (`feature/dpp-qr-explorer@caf651f`) and the research branch were not merged, cherry-picked or imported.

## What was built

A standalone, read-only page `recall-ui/investigation.html` (second Vite entry, same pattern as a standalone page). It reads `GET /api/snapshot` only, validates it with the existing `validateSnapshot`, and accepts it only through the existing, unmodified `verifyFreshness`. A pure projection turns the decisions the pinned v3 engine already computed into:

1. evidence **items** (one per listed reason with ledger detail),
2. exact-key **groups** of identical items across motors,
3. a published priority order,
4. a watermark and a fixed list of verification limits.

No backend code, `App.tsx`, `freshness.ts`, `RecallDataSource.ts`, `server.py`, the engine, the ledger, the integration layer, notifications or anchors changed.

## Changed files

New: `recall-ui/investigation.html`; `recall-ui/src/investigation/` (`taxonomy.ts`, `projection.ts`, `diff.ts`, `route.ts`, `investigationSource.ts`, `InvestigationWorkspace.tsx`, `InvestigationApp.tsx`, `main.tsx`, `investigation.css`); `recall-ui/public/data/investigation-demo.json`; `recall-ui/tools/generate_investigation_demo.py`; tests `tests/unit/investigation-projection.test.ts`, `investigation-app.test.tsx`, `investigationHelpers.ts`, `tests/e2e/workspace.spec.ts`; screenshots `docs/investigation-screenshots/`; this document.
Modified: `recall-ui/vite.config.ts` only (multi-page input). `package.json` and `package-lock.json` are unchanged: no new dependency.

## Mapping taxonomy

Every engine reason code and flag is classified explicitly in `taxonomy.ts` (a test checks all 39 reason codes the engine can emit, all glossary codes and all 5 flags). Handling is one of: evidence class, informational (nothing to investigate), or obligation (separate panel).

| Evidence class | Kind | Reason codes / flags |
|---|---|---|
| Untrusted affected-lot observation | untrusted | `UNTRUSTED_AFFECTED_OBSERVATION`; flags `OUT_OF_SCOPE_…`, `UNATTRIBUTABLE_…` (non-blocking) |
| Rejected evidence (source, method or actor) | untrusted | verifications with `trusted:false` and rejection reasons that are not already an untrusted-observation item |
| Conflicting records | conflicting | `DOUBLE_OCCUPANCY`, `REMOVAL_OBSERVATION_MISMATCH`, `REMOVAL_SERIAL_IN_OTHER_SLOT`, `REMOVAL_RECORD_INCONSISTENT`, `VERIFIED_STATE_MISMATCH(_RISK_DECREASING)`, `LATE_CLAIM_RISK_INCREASING`, `EVENT_ORDER_INTEGRITY`, `EVENT_INTEGRITY_VIOLATION`, `WORK_ORDER_UNRECONCILED`; flag `SLOT_RECORD_CONFLICT` (non-blocking) |
| Ambiguous slot attribution | ambiguous | `AMBIGUOUS_SLOT_ATTRIBUTION`, `LOT_LEVEL_SLOT_AMBIGUITY` |
| Capture gap | missing | `MATERIAL_CAPTURE_GAP`, `SOURCE_SEQUENCE_GAP` |
| No trusted baseline or unverified state | missing | `NO_TRUSTED_BASELINE`, `UNTRUSTED_SOURCE_CLAIM`, `CURRENT_STATE_UNVERIFIED` (see below) |
| Completeness or inspection | missing | `DAMAGE_INSPECTION_MISSING/INVALID/FAILED`, `REMEDIATION_COMPLETENESS_UNCERTAIN`, `EXPOSURE_UNKNOWN`, `HISTORY_GAP_NOT_RECOVERED_BY_VERIFICATION` |
| Shared raw-material lot | shared context | derived from ledger lineage; not a reason code |
| Unclassified | unclassified | any code or flag not in the table; a held unresolved decision that lists no evidence reason |
| (obligation) | n/a | `PRIOR_EXCLUSION_WITHDRAWN`: never a task; shown in a separate panel with a link to the console |
| (informational) | n/a | `AFFECTED_LOT_INSTALLED`, `VERIFIED_AFFECTED_LOT_PRESENT`, `HISTORICAL_EXPOSURE_CONFIRMED`, `CORROBORATED_BY_VERIFICATION`, `DAMAGE_INSPECTION_PASSED`, `EXPOSURE_REMEDIATED`, `REPLACED_WITH_UNAFFECTED_LOT`, `AS_BUILT_UNAFFECTED_LOT`, `VERIFIED_UNAFFECTED_LOT`, `GAP_BOUNDED_BY_VERIFICATION`, `IRRELEVANT_SLOT_GAP`, `SLOT_EMPTY`, `NO_HISTORICAL_EXPOSURE`, `LATE_CLAIM_RISK_DECREASING_NOT_APPLIED`, flags `UNTRUSTED_AFFECTED_OBSERVATION_SUPERSEDED`, `KNOWN_LIMITATION_LOT_LEVEL_SLOT_AMBIGUITY` |

Rules that keep nothing from disappearing:
- A reason is listed but its detail is not found in the snapshot: a code-only item with `detailFound: false`.
- `CURRENT_STATE_UNVERIFIED` often follows conflicts or gaps. It is folded into the item that explains it (recorded in the item's `coveredCodes`) and gets its own baseline item only when nothing else explains it.
- Items are produced only for decisions with action `RECALL_HOLD`, except flag-driven items, which are produced for any decision and marked non-blocking. Motors that are held as `AFFECTED` with only informational reasons are listed under "Motors with no listed evidence item", not as items (they need remediation, not evidence).

Each item shows four parts: what the existing decision says (copied unchanged, with the glossary text), which evidence class is missing, conflicting or untrusted, which ledger records support it (exact source, window, actor claim, method, component, lot, evidence IDs where recorded; "Not recorded" otherwise), and what a quality engineer should independently investigate. The investigation text is static and reviewed in `taxonomy.ts`. It names an evidence class and the rule that rejected or lacks it. It never names an expected value, never says what a record should say, never proposes changing a trust configuration (it says approving a rejected source, method or actor after the fact is not evidence) and never says an item releases a motor. Unit tests enforce this wording.

## Exact cluster keys

A group is a set of items with identical key text. Keys are shown in the UI. Matching is exact string equality of these fields; nothing is fuzzy. Every key starts with `policy=<policyId> | class=<class>`.

| Class | Fields (after `policy`, `class`) |
|---|---|
| Capture gap | `gapKind`, `materiality`, `sourceId`, `from`, `to`, `eventId`, `boundedByEventId`, `slots` (relevant slots, sorted) |
| Ambiguous attribution | `observedPart`, `observedLot`, `observedSerial`, `observedGranularity`, `claimedSlot`, `candidates` (`slot:basis[:claimed]`, sorted), `ruledOutSlots`, `unrulable`, `assurance` |
| Untrusted observation | `slot`, `observedPart`, `observedLot`, `observedSerial`, `rejectedReasons` (sorted), `actorClaim`, `method`, `observationStatus` |
| Rejected evidence | `slot`, `observedPart`, `observedLot`, `observedSerial`, `rejectedReasons`, `actorClaim`, `method` |
| Conflicting records | `slot`, `conflictKind`, then every other field of the recorded conflict |
| Baseline or state | `reasonCodes`, `slotStates` (per relevant slot: baseline, state, identity granularity, reconciliation) |
| Code-only / unclassified | `trigger` (`REASON_CODE:` or `FLAG:` plus the code) |
| Raw-material lot (context) | `class=RAW_MATERIAL_LOT`, `rawMaterialLot`, `supplierClaim`, `observedLot` |

`sourceId` is shown for observation items but is **not** in their key: under the current schema every source id is per motor (for example `HANDHELD:MTR-26005`), so including it would make every group a single motor. Actor claim and method are the grounded shared fields. If the event schema gains a shared station or device id, add it to these keys; that is a separate decision.

The raw-material-lot group is a second, overlapping view. Each item is in exactly one primary group (tested) and may also appear in a lot group. A lot group is emitted only when at least two motors share it, and the lot comes only from the ledger's own lineage rows for that motor and that observed lot. If a rejected record claims a lot the ledger never traced to that motor (as with MTR-26005 and BR-204), no lot context is shown for it.

## Priority rules

A fixed lexicographic key, shown in the UI. There is no numeric score, probability or release prediction (tested).

1. Evidence-gap groups before raw-material-lot context groups.
2. Groups containing an untrusted affected-lot observation that blocks a hold.
3. Groups with at least one motor whose earlier release-eligible decision was withdrawn (`PRIOR_EXCLUSION_WITHDRAWN`).
4. More distinct motors before fewer.
5. Fixed class order: untrusted observation, rejected evidence, conflicting records, ambiguous attribution, capture gap, no trusted baseline, completeness or inspection, unclassified.
6. Group key text.

Rules 2 and 3 are deliberately above cluster size, so one motor with the most serious signal is not starved by a larger group (tested).

## Demonstration scenario

Generated by `tools/generate_investigation_demo.py` through the real application service and the pinned v3 evaluator, using only existing commands. Decisions are real engine output. There is **one authored edit**, and it is labelled in the data and the UI: for `MTR-26015` and `MTR-26016`, the capture-gap `sourceId` inside decisions is rewritten to `ASSY:SHARED-DEMO-STATION`, because the schema scopes every source to one motor. The ledger event schema is unchanged and no shared station identity was introduced.

| Motors | Origin | Shows |
|---|---|---|
| MTR-26001 to MTR-26005 | actual seeded | MTR-26002 ambiguous attribution, MTR-26004 capture gap, MTR-26005 untrusted observation; no shared gap exists here |
| MTR-26011, MTR-26012 | engine demo extra | same exact untrusted-observation key as MTR-26005: 3-motor group |
| MTR-26013, MTR-26014 | engine demo extra | same exact ambiguity key as MTR-26002: 3-motor group, and a shared raw-material-lot group (STEEL-26-410) |
| MTR-26015, MTR-26016 | authored source edit | shared capture-gap key: 2-motor group; MTR-26004's gap stays separate |
| MTR-26017 | engine demo extra | identity only, then gets an assembly record in the "after" stage |

Stage "after" applies two existing commands: a later install on MTR-26012 and the assembly record for MTR-26017. Result: MTR-26017's item disappears (no manual closure), and MTR-26012's item stays under a newer decision version (2 to 3) because the engine still treats the untrusted observation as unanswered. The page shows this as a change list. Evidence arriving does not close an item; only the engine's re-evaluation does.

The scenario is partly authored to demonstrate clustering. It is not evidence of how often shared gaps occur.

The outage case is demonstrated live: stopping the backend withdraws every item and the page shows no fixture data (browser test).

## Safety boundaries

- Read-only: only `GET /api/snapshot`. A browser test asserts all page requests are GET to that URL, and the page has no form, input (other than a native select filter) or button.
- No assignment, completion, approval or resolution control; the interactive-element labels are tested.
- No database tables, endpoints or evaluator. The projection imports only the snapshot types and the taxonomy and makes no I/O (tested by reading the source).
- Never computes a hypothetical outcome. Decisions are copied unchanged into items; a test compares each item's decision to the input decision.
- Current claims are shown only while `verifyFreshness` has just accepted the snapshot and its lease has not expired. An unverified or unanchored snapshot, a failed refresh, an expired lease, a hidden tab or a regression withdraws all items. Only the last accepted watermark is shown, labelled not current.
- Preview mode is an explicit `?mode=preview`, always labelled "Preview: not current", never given a verified watermark. A failed live backend never switches to it.
- Notification obligations are listed in a separate panel with the console link; no item or control marks one as communicated.
- Customer and destination are not carried. The shipment ID and ship time are shown as a recorded claim, with a note that a shipment record is not an authorization. This is UI omission, not API access control; `/api/snapshot` still carries those fields.
- Actor identifiers appear only where they are the grounded actor claim of the cited record.
- All wording says "not recorded in the ledger as of the watermark", never "does not exist"; resolving a listed item "does not by itself release a motor".

## Test results

Run in `recall-ui` and the repository root of the new worktree at the code commit.

| Check | Result |
|---|---|
| `tsc --noEmit` | clean |
| Vitest | 7 files, 91 tests passed (33 existing + 58 new: 40 projection, 18 app and adapter); repeated three times |
| `npm run build` | succeeds; `investigation.html` added |
| Playwright | 39 passed (29 existing + 10 new) |
| `snapshot:check` | "snapshot is current" |
| Backend `application.test_application`, `test_remediation`, `test_hardening` | 36 tests; passed on 6 of 8 runs. Each of the 2 failing runs had one failing test; I captured one of them (see below) and did not capture the other |

Intermittent backend failure, pre-existing and unrelated: `test_seed_safety_cases_and_idempotence` (`application/test_application.py:66`) compares two consecutive `snapshot()` calls, and fails when the wall-clock second in `freshness.verifiedAt` rolls over between them (`…:01:07Z` vs `…:01:08Z`). That is the failure I captured. The test file and backend are untouched by this branch. It is a flaky test on the baseline; fixing it is out of scope.

The new browser tests: authored-scenario walkthrough with screenshots; desktop and mobile overflow and axe on overview, cluster and evidence pages; keyboard flow; invalid and unknown addresses; live seeded ledger (three actual single-motor groups, untrusted observation first); live evidence update with no manual closure and GET-only requests; backend outage and recovery with no fixture requests; unanchored envelope withheld; read-only invariance: journal sequence, head, archive id, every decision (including decision IDs), notifications, ledger event counts and the external owner-anchor file are identical before and after viewing every page.

Screenshots are in `docs/investigation-screenshots/` (generated by the Playwright spec).

## Known limitations

- No real shared source gap exists in seeded data; the shared-gap group in the demo depends on one authored edit.
- The taxonomy and investigation text were written by the same agent that designed the feature. A quality engineer or the owner should review them before anyone relies on them.
- Items come from client-side projection of the snapshot. The research draft proposed a server module and a `GET /api/investigations`; the owner's scope chose pure TypeScript, so there is no server-side recompute, and correctness rests on the snapshot validation and freshness gate.
- Several classes (conflicts, rejected verifications, completeness/inspection, unknown codes) are exercised only with synthetic edits to decisions in unit tests, because the seeded data does not produce them.
- The pinned engine currently runs only policy P1; P2 codes are mapped but not exercised on real P2 data.
- The existing console has no event-level deep link, so event links open the workspace's own evidence page; unit links go to the console's decision/events/history tabs.
- Group IDs are a hash of the key, so a link to a group stops working when its decisions change (the page says so). Evidence links are stable.
- The "no listed evidence item" list shows engine decisions, including release-eligible ones, in verified mode. It is labelled "not a clearance", but a reader could still misread it.
- A rejected record claiming a lot the ledger never traced to the motor gets no raw-material lot context.
- The preview stage switch is a page reload; it is a captured evidence update, not a live one. The live update is shown by the browser test using existing commands.
- This is a proposal for an ordering, not validated in a real plant.

## Compatibility requirements with Codex H1/H2

- The live adapter reuses `verifyFreshness` and `validateSnapshot` unchanged. If H1/H2 introduces new status values (for example `ANCHORED_CURRENT`, `ANCHORED_PREFIX_ONLY`) or changes what `verifyFreshness` accepts, the workspace follows without change, but it must show items **only** for the fully current state. Anything else must throw or be reported as unverified, which withdraws all items. Check this explicitly against H1's "journal past checkpoint" case.
- If `verifyFreshness` changes its return value (currently the remaining lease in ms) or snapshot shape, `LiveInvestigationSource.load` is the single place to adapt.
- `tests/unit/investigationHelpers.ts` `freshStage` hard-codes `VERIFIED_ANCHORED_SYNTHETIC`; update it to the new current status.
- If H2 changes decision fields (for example withholding `RELEASE_ELIGIBLE` or adding a status), `validateSnapshot` and `ACTION_TEXT` will decide whether the page loads; the projection copies `action` as a string and falls back to a humanised label for unknown values.
- If snapshot latency grows (the audit saw 3 s at 50 entries), the shared 4 s client timeout applies here too and the page would withdraw items.
- Text conflicts to expect: `recall-ui/vite.config.ts` only. This branch touches no file Codex owns (`App.tsx`, `freshness.ts`, `RecallDataSource.ts`, `playwright.config.ts`, verification scripts). The new Playwright spec shares the existing web server on port 4173 and starts isolated servers on ports 4191 to 4195.

## Interaction with the independent passport feature

- Neither branch imports the other. No shared source file; each has its own adapter (a small duplicate of the GET helper, to be consolidated only after both are approved).
- Both edit `recall-ui/vite.config.ts` to add `build.rollupOptions.input`. On merge, keep one input map with all pages (`main`, `passport`, `investigation`). The passport branch also adds `uqr` and `jsqr` to `package.json` and the lockfile; this branch adds none, so only the passport changes the lockfile.
- Display policy differs and should be unified by the owner: the passport omits the shipment ID, the workspace shows it as a recorded claim.
- A passport could link to the workspace root (`investigation.html#/`) or to an evidence record (`#/evidence/<unit>/<eventId>`, stable). It should not link to `#/cluster/<id>`, which changes with the decisions.
- Both rely on the same freshness boundary, so a Codex change there affects both identically.

## Demo walkthrough

1. Build (`npm run build`), start `recall-ui/tests/browser_server.py <db>` (seeded, anchored) and open `/investigation.html`. The watermark shows the verified journal sequence. Three single-motor groups appear: MTR-26005 untrusted observation first (rank 1, withdrawn exclusion), MTR-26002 ambiguity, MTR-26004 capture gap. The notification obligation for MTR-26005 is in its own panel.
2. Open `/investigation.html?mode=preview&stage=before#/`: banner "Preview: not current" and the origin tags. Six groups: the 3-motor untrusted group, 3-motor ambiguity group, the 2-motor shared capture gap (`ASSY:SHARED-DEMO-STATION`), MTR-26004's gap, MTR-26017's baseline item, and the raw-material-lot group (STEEL-26-410).
3. Open the untrusted group: for each motor read the four parts, the rejection reasons, actor claim `OP-OBSERVATION-21`, method `HANDHELD_LABEL_READ`; open the record link for the evidence page with hashes and the note that hashes do not show the content is true.
4. Open `?stage=after#/`: MTR-26017's item is gone and the change list says MTR-26012 was re-evaluated (version 2 to 3) but is still listed. Nothing was closed by hand.
5. Live update: with the live server, create a unit through the existing API; a baseline item appears within seconds; assemble it; the item disappears and the change list says so.
6. Stop the backend: every item is withdrawn, the page says current tasks are unavailable, shows only the last watermark labelled not current, and requests no fixture. Restart: items return after verification.
