# Phase 3.1 safety remediation

Baseline: `phase3/unified-application` at `4a9e8f2c11e5e12bfd6926bfb9f9a0ee0dd3fa57`. Remediation branch: `fix/phase3-safety-remediation`. Date: 2026-10-21. Destination: `mohammedsuhailrafek28/PRAMAAN-Manufacturing`.

**Recommendation: GO for Claude's independent remediation audit; REVISE before production use.** The critical unspecified-scope false release is reproduced and fixed. New behavior is tested without changing the v1/v2/v3 engine, original foundation experiment or integration source trees. No merge, deployment, multi-recall feature, source HORIZONXT change or MSME access is part of this work.

## Reproduction before changing logic

The isolated worktree began at the exact baseline. Python probes used disposable SQLite files; browser probes used a disposable local server. A separate shallow baseline clone reproduced the verification failure. Source logic was not modified until these reproductions were recorded.

| Audit finding | Confirmed root cause | Before evidence | Remediation / after expectation |
| --- | --- | --- | --- |
| CRITICAL NDE false release | `Manufacturing.announce()` silently authored `affectedSlots=['DE']` for an unpositioned lot recall. V3 correctly answered that narrower policy; application scope was wrong. | Shipped DE BR-310 / NDE BR-204 motor: `EXCLUDED_WITH_EVIDENCE / RELEASE_ELIGIBLE`. [before.json](phase31-validation/before.json), [matched four-case matrix](phase31-validation/before-matched-scope.json). | Missing scope means both compatible positions. Explicit DE-only, NDE-only or both are validated, canonicalized and recorded with scope origin. The same NDE motor becomes AFFECTED / RECALL_HOLD. |
| HIGH disappearing obligation | V3's original series signature compares an already lifecycle-augmented previous result to a fresh kernel result. A later event can emit a version without recreating the original withdrawal transition. The application projected only the current decision's obligation. | `/notifications` equivalent projection went from one conditional obligation to `[]` after an unaffected observation. | Independent append-only obligation events; current projection derives outstanding obligations from the journal, not transient decision fields. HTTP persistence/reopen/resolution tests cover it. |
| HIGH stale material details / identity | Original `_signature()` omits observations, flags, attribution detail, cited evidence, policy context and obligations. The unchanged branch copies old decision fields and only advances the watermark. Local engine IDs use only motor + last policy-ID segment + ordinal. | A new unaffected untrusted observation left the same decision ID and `untrustedObservations=[]`, while fresh v3 output contained that observation. Deleting legacy runs recreated plausible v1. | Versioned A31 publication layer retains fresh full raw v3 results, material fingerprints, scoped IDs, receipts and immutable history. Separate anchors detect missing/truncated history. |
| HIGH clean-clone verification | The old verifier used `git diff <source SHA>` as a content gate. Unavailable source objects produced false integrity failures even though tests passed. | Shallow baseline clone: engine/foundation flags false; full command failed. [failure log](phase31-validation/clean-baseline-failure.txt). | Pin 126 original file hashes and original tree references. Check byte content and file set without requiring source commit ancestry; preserve all runtime test gates. A deliberately changed source hash fails the new verifier. |
| MEDIUM-HIGH stale UI release | Live data loaded once; neither bounded requests nor subsequent backend health/freshness checks existed. | After successful load, blocked API access for 6.5 seconds: Release eligible remained displayed. [browser-before.json](phase31-validation/browser-before.json). | Four-second request/body deadline, two-second refresh, five-second verification lease; errors/expiry hide operational decision views. Last verification time and historical/current distinction are explicit. Real backend kill regression included. |
| MEDIUM mobile/accessibility | Long plain URNs inside compact attribution tables and metadata exceeded the panel's intrinsic width. Genealogy overflow region was not keyboard focusable. | Decision tab at 390px: 31px horizontal page overflow; genealogy `tabindex=null`. | Wrap long identifiers, constrain panel/table layout, name/focus the graph scroller and show focus. Live mobile WCAG checks and ArrowRight scrolling test included. |

The historical baseline's passing tests were insufficient: the critical NDE-only/default-scope combination was absent. No claim is made that previous zero-false-release counts covered this newly discovered case.

## Recall scope contract

`POST /api/recalls` accepts `lot` and optional `affectedSlots` only:

```json
{"lot":"BR-204","affectedSlots":["NDE"]}
```

- Omitted `affectedSlots`: `['DE','NDE']`, `scopeDeclaration='ALL_COMPATIBLE_POSITIONS'`.
- Explicit `['DE']`, `['NDE']`, or both: `EXPLICIT_POSITIONS`; both are canonicalized DE then NDE.
- Empty lists, duplicates, unknown/lowercase/non-string positions, wrong shapes, explicit JSON null and competing/unsupported fields such as `slot` or `scope` are rejected. Invalid input never falls back to DE.
- The direct control-plane helper's optional `None` means omitted scope; HTTP distinguishes absent from explicit null.
- One immutable recall scope remains the limit. An attempted scope/lot change after announcement is rejected, not silently treated as a new policy revision. Phase 4A was not implemented.
- The existing seeded DE demonstration now declares DE explicitly. Newly unpositioned recalls are conservative by default, and the UI exposes all three scope choices.

Existing Phase 3 stored policies have no scope-origin attestation and may contain the faulty generated DE restriction. They are **not** automatically broadened or reissued under old IDs. Current clearance from those databases is blocked with a legacy-scope error. Preserve the original database for historical replay; start a new named synthetic database for this remediation. An authorized live-data migration/scope confirmation is a follow-up, not an implicit repair of historical policy bytes.

## A31 publication lifecycle and exact revision criteria

The evaluator remains unchanged. New application publications use **`APPLICATION_PUBLICATION_A31`** over fresh `pramaan_recall.evaluate(..., Config.v3())` results. The journal separately retains the raw result (including its original engine version/profile) and the application publication. Lifecycle annotations do not change an engine exposure finding or operational action.

`application/audit.py` introduces an append-only SHA-256/RFC8785 hash chain, a separately persisted counter/head/legacy-history digest, an archive identity and SQLite `user_version=31` marker. The genesis entry binds archive identity and legacy digest. Each transaction verifies the chain/head and prior legacy-run bytes before evaluation/publication. Removing/truncating the journal fails rather than issuing v1; removing both journal and head still fails while the database-version marker remains. New IDs include motor, **full policy digest**, archive identity and publication version, avoiding the original suffix-only collision. Journal append, head update and obligation creation commit atomically under `BEGIN IMMEDIATE`.

| Change | Publication behavior |
| --- | --- |
| Exact same verified input and obligation state | Reuse the existing evaluation/publication; no redundant journal receipt or decision version. |
| New source watermark / provenance-only uncited event, with identical material kernel output | Append a receipt with the new manifest and complete fresh kernel fields; keep decision ID/version, mark `unchanged`. Preserve the original immutable publication at its original watermark. |
| Any change in the raw kernel result except `watermark` | New publication version: finding, action, review, reasons, flags, slots, coverage/policy/profile fields, evidence IDs/refs, conflicts, observations, attribution and work-order details all count. |
| Outstanding obligation set changes | New material publication even if exposure result is unchanged. Resolution is explicit, not inferred from reevaluation. |
| A timestamp on an ignored provenance claim changes receipt horizon only | No version just for the clock tick. If that horizon changes v3's completeness/gaps/reasoning, it is a material result change and does receive a version. |
| Policy/configuration context differs | Different fully scoped history identity; original records remain immutable. The application API does not authorize policy evolution or multiple recalls. |

Canonical dictionary key ordering is not material. Kernel list/evidence ordering and all fresh result fields other than the source vector are deliberately conservative material inputs; this is not a heuristic that discards explanations to save versions. Cache identity includes policy/configuration, complete manifest and outstanding obligation IDs. Cache reuse is distinct from material-version criteria.

Every evaluation receipt binds exact policy bytes/digest, manifest/source vector and raw kernel output. `Audit.replay()` validates issuance and journal integrity, reconstructs the original manifest, and uses the original raw record's engine semantics profile; it checks the reproduced raw result before returning the original publication verbatim. Original `Ledger.decide/replay` and v1/v2/v3 lifecycle semantics are unchanged. A legacy-bundle regression checks that opening the new application does not rewrite old `decision_runs` rows and that original replay still agrees. No old decision is retroactively relabelled A31.

### Durable notification obligations

An exclusion-to-held transition appends `OBLIGATION_CREATED`, referencing the prior scoped release and triggering context. Later unaffected observations, provenance receipts, new holds, process restarts or current-display changes do not erase it. `/api/notifications` lists outstanding journal obligations. Viewing is not communication; `communicated=null` and `deliveryEvidence=null` remain unknown. `NOT_SENT` means this application has sent nothing, not that nobody received an earlier release through some external channel.

Resolution is a separate `OBLIGATION_RESOLVED` journal event through a trusted control-plane method. It denies all callers by default; an integrating authenticated authority must explicitly supply an authorizer, principal, reason and archived same-motor event references. Tests exercise denial, explicit authorization and persistent resolution. There is **no HTTP resolution endpoint**, no invented owner identity and no automatic delivery acknowledgement. Resolution does not convert a held kernel result to release eligibility.

## Freshness and provenance behavior

Live reads and commands bound both transport and response-body decoding. Snapshot requests use `no-store`; polling skips in-flight/active capture work and generation checks prevent a pre-capture response from overwriting newer state. A successful command renews the lease. An offline/error/expired lease removes all operational decision views, shows last successful verification and explains that previous decisions are historical. Cached form inputs survive a transient failure, but controls are disabled until verified connectivity returns. There is no automatic fixture fallback. Explicit fixture mode stays labelled synthetic and retains its original semantics.

The UI's local verification lease describes a recent backend integrity read, **not physical factory truth, producer clock trust, shipment permission or an atomic release action**. This application implements no shipment-release authority. A stopped browser, device sleep or independent writer requires a fresh backend read before operational reliance; a future release command must independently recheck current evidence server-side.

New synthetic events use `SYNTHETIC_SIMULATED`, with no trusted clock sources registered. Existing historical clock claims are not rewritten. Supplier/material/shipment projections carry `SYNTHETIC_UNVERIFIED_CLAIM`; UI text explicitly distinguishes ledger integrity from supplier identity, origin, quantities and synchronized time. `backedByLedger` means a supporting integrity-checked claim exists, not independently verified provenance.

## Reproducibility, provenance and clean-clone commands

`application/source-provenance.json` pins baseline file bytes and these original Git tree references:

| Tree | Baseline tree ID |
| --- | --- |
| recall-engine | `22d205d5b2d42e609e8b872c564c7283ffd758e9` |
| experiments/foundation | `fe6f39294e10b077785ed3afb27806af51acc50c` |
| integration | `401d19ab2bdb1cc6cd474754faffbf1f1f4e9022` |

The runtime content check uses SHA-256 bytes and file inventory, not Git object availability. Missing, changed or unexpected source files fail; Python bytecode is excluded. Pin provenance itself is reviewed repository content, not an external signature or defense against wholesale repository replacement. External GS1 schema/context bytes are checked against their original hashes before validation. No integrity check is disabled to obtain a PASS. Historical `integration/run_validation.py` remains untouched; the supported complete entry point is the application verifier.

Windows PowerShell, from a clean checkout of this remediation branch (Python 3.12+, Node 24+, installed Chrome):

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r integration/requirements-validation.txt
Push-Location recall-ui
npm ci --ignore-scripts
Pop-Location
git clone https://github.com/gs1/EPCIS.git ../gs1-epcis
git -C ../gs1-epcis checkout 6f71468231838e424bb5dfa836e006e8dc69615c
.venv/Scripts/python.exe -m application.verify
```

Alternatively set `PRAMAAN_GS1_CHECKOUT` to an existing external pinned checkout, or pass `--gs1-checkout`. Missing artifacts cause a visible prerequisite failure, never skipped validation. An activated environment can use exactly `python -m application.verify`. The external artifacts stay outside the repository. On macOS/Linux substitute `.venv/bin/python`; browser tests still require Chrome.

Run the remediated local demo on a new path:

```powershell
.venv/Scripts/python.exe app.py --seed-demo --database .local/phase31.sqlite
```

No deletion or overwrite of an earlier database is required. Reports are written under `docs/phase31-validation/verification`; original Phase 2/3 reports and screenshots are preserved. Clean-clone evidence is recorded separately under `docs/phase31-validation/clean-clone`.

## Regression gates and synthetic safety

| Gate | Clean-clone result |
| --- | --- |
| Existing engine suite | 127 passing; original source bytes unchanged |
| Foundation interoperability | 21 passing |
| Existing integration suite | 44 passing; original source bytes unchanged |
| Original application tests | 7 passing |
| New remediation tests | 16 passing, including 16 scope subcases, scope contradictions, notification endpoint persistence, material/identical/receipt behavior, resolution, deletion/tamper and legacy replay |
| Fixture exporter | 7 passing; original snapshot current |
| UI | 25 original + 2 request/body-timeout regressions = 27 passing |
| Browser | 22 original + 3 live remediation tests = 25 passing |
| Build/typecheck | TypeScript + Vite production build passing |
| GS1 | 58 live seed documents plus retained 2 documents / 19 events validated with pinned external schema/context |
| Clean clone | Complete verifier passed without imported source commit objects; see committed clean-clone proof/logs |

The expanded [25-case synthetic suite](phase31-validation/expanded-safety.json) includes the scope Cartesian product, ambiguity, capture gaps, untrusted affected observations, clean replacement, late withdrawal, unknown baseline and double installation. Expected behavior and physical truth live only in test/reporting modules. **25/25 behavioral agreement; 0 false releases among 14 unsafe cases; 3 unnecessary holds among 11 safe cases.** “Unsafe” is relative to the declared recall policy/scope, not every possible manufacturing defect. Cases include successive states and are not independent factory trials.

The complete clean-clone run tested code commit `3cf6bc9d91aef92c170feb2a6de1f80ba455cdbe`, with fresh venv/npm installations and no imported engine/foundation commit objects. The clone used Git pack transport from the local Manufacturing repository with `--no-local --depth 1`, not a shared worktree or borrowed object store. The final evidence commit changes documentation only; runtime sources match the tested code. [Proof](phase31-validation/clean-clone/proof.json), [full summary](phase31-validation/clean-clone/phase31-results.json), and [individual logs](phase31-validation/verification/). Per-database archive IDs intentionally differ across fresh runs; within one history exact reevaluations retain identity and semantic results remain reproducible.

Matched default-scope comparison: baseline four DE/NDE lot combinations had **1 false release among 3 unsafe cases, 0 unnecessary holds among 1 safe case**. After remediation the same four combinations have **0 false releases and 0 unnecessary holds**. The separate, broader 25-case suite intentionally retains three conservative holds where external synthetic truth says safe but evidence is ambiguous/gapped/missing. The retained Phase 2 suite separately has 0 false releases and 3 unnecessary holds across 12 histories; do not add these overlapping synthetic counts as independent trials. Zero in these tests does not prove real factory safety.

## Additional investigations and remaining limits

1. **Fleet availability after one rejected capture — reproduced, intentionally retained fail-closed.** In a disposable seeded database, reject a bad hash for MTR-26003; the next fleet snapshot raises `LedgerBlocked` and the UI removes decisions for all motors. A regression preserves this explicit failure rather than serving stale releases. Per-motor quarantine/error projections are a follow-up requiring a completeness-aware fleet contract; this remediation does not invent safe decisions for blocked/missing motors. Composite command interruption still leaves durable partial evidence and an incomplete/held result. No unblock or crash-resume shortcut was added.
2. **Local integrity is not independent attestation.** A journal, separate head and database-version marker detect deletion/truncation/ordinary tampering, including removal of journal plus head. An attacker who rewrites the entire database and all anchors/version metadata, or replaces the whole repository and pins, can defeat local checks. External authenticated anchoring, backups, access controls and signed source identity remain production follow-ups; no cryptographic authenticity claim is made.
3. **Legacy scope migration is deliberately blocked.** Historical rows replay unchanged, but the application does not automatically issue fresh clearance from old generated DE scope. A reviewed migration/owner scope confirmation and legacy-obligation import are needed before operational use of existing live data. Use a new synthetic database for the demo. This is a visible safety block, not a silent data reset.
4. **No production owner identity or notification delivery.** Default resolution authorization denies everyone; the trusted callback boundary is tested but no identity-provider integration or HTTP resolution workflow is shipped. Obligations stay outstanding until explicitly authorized; no notification is sent.
5. **Current read scope remains local/single recall.** Full history verification and two-second polling have cost that grows with evidence/history/fleet. The service serializes its own requests, not arbitrary independent SQLite writers. Multi-case publication, cross-policy evolution and selective invalidation are out of scope and remain unimplemented.
6. **Synthetic assertions are not trusted factory evidence.** Clock trust and supplier labels are corrected for new demo data, but synthetic actor/session/baseline assertions still exist for repeatability. Real provisioning, physical verification, data access controls and factory validation remain necessary.

## Affected files and review boundary

- Application: `service.py`, `server.py`, new `audit.py`, `provenance.py`, `source-provenance.json`, `safety31.py`, `test_remediation.py`, and `verify.py`.
- UI: `App.tsx`, `RecallDataSource.ts`, styles, decision explanation/history, genealogy, manufacturing scope controls, request tests and live browser regressions.
- Documentation/artifacts: README, this report, visual review, before/after measurements, test logs, clean-clone proof and new screenshots.
- Unchanged: original engine/fixtures/oracles, foundation and integration trees, original application tests, historical snapshot/exporter data, original Phase 3 branch and prior research branch.

The visual finish review judged the scoped interface **ship**, with no material visual blocker; this is not an independent safety certification. Final merge remains subject to Claude's independent audit and explicit owner approval. Stop after pushing this remediation branch; do not merge or deploy.
