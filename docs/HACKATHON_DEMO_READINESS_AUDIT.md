# Manufacturing PRAMAAN: independent hackathon demo-readiness audit (HORIZONXT PS10)

Date: 2026-10-23. Auditor: Claude (independent of Codex's integration work). Branch: `review/hackathon-demo-readiness`, review-only: this document and `docs/demo-readiness-evidence/` are the only additions. No application source was changed; no merge, PR, deploy or integration branch was created. Synthetic data only; everything ran on loopback.

## 0. Verdicts and the five findings that drive them

| Scope | Verdict |
|---|---|
| A. Original baseline demo (A31 `f928210`, same app as CI-green `04d974f`) | **CONDITIONAL GO**, if the anchor step in section 5 is done before the demo. **NO-GO from the default branch `main`** (section 1, F1). |
| B. Isolated product-feature demos | **CONDITIONAL GO** for the three live pages on `73f3bdbd`. **GO (preview only)** for `7482fc1`; its live pages are blank against the A31 backend. **CONDITIONAL GO** for H1/H2 `f9dcf56` as a safety-gate demo, not a recall-journey demo. |
| C. Fully unified demo | **NO-GO**: no unified branch exists. Only an assembled-artifacts probe was possible (section 3, probe P). |
| D. Real-factory pilot | **NO-GO** |
| E. Production deployment | **NO-GO** |

Findings, each reproduced here:

1. **F1 (blocker for the default branch).** `main` (`6e772e8`, the merge of PR #1) is the pre-remediation Phase 3 app. Following its README, a motor with the recalled lot in the NDE position is reported `EXCLUDED_WITH_EVIDENCE / RELEASE_ELIGIBLE`, a false release. The same inputs on `f928210` give `AFFECTED / RECALL_HOLD`. Anyone who clones the default branch gets the defective version.
2. **F2.** On `f928210` the README's own run flows do not work as written. `--seed-demo` without `--trusted-anchor` opens on "Recall data could not be loaded". A fresh database refuses every command with HTTP 409 until a checkpoint is exported and the server restarted with it.
3. **F3.** The branded frontend `7482fc1` cannot show live data from its own backend. Its strict gate needs checkpoint and eligibility metadata that only `f9dcf56` emits, so all three live pages show "withheld" against the A31 backend.
4. **F4.** On H1/H2 `f9dcf56`, every capture leaves the ledger `ANCHORED_PREFIX_ONLY` and every motor ineligible until a successor checkpoint is exported, protected and the server restarted. A live "capture then recall then see the result" demo cannot show current clearance without that choreography.
5. **F5.** The live API is not access-controlled. Customer and destination are served unauthenticated; any `Host` header is accepted; `/api/session` gives the write token to any caller. Pages omit those fields, but omission in a page is not access control.

## 1. Method, pins and evidence

Every pin was cloned fresh from GitHub into its own directory and set up with the README steps (`git clone`, `python -m venv`, `pip install -r integration/requirements.lock`, `npm ci --ignore-scripts`, `npm run build`). Chrome 1280 px headless via Playwright for screenshots. The driver scripts are in `docs/demo-readiness-evidence/tools/`; raw results in `results/`, page text in `page-text/`, screenshots in `screenshots/`.

| Pin | SHA | What it is |
|---|---|---|
| main | `6e772e8` | Default branch: PR #1 merge of `phase3/unified-application` (`4a9e8f2`). Does **not** contain `f928210`. |
| A31 base | `f928210` | A31 hardened backend plus original console. `04d974f` adds only CI files to it (`git diff --stat`: 14 files, all under `ci/`, `.github/`, `docs/`), so it is not run separately. |
| Three features | `73f3bdbd` | Base plus passport, investigation and impact pages, live and preview. |
| Branded frontend | `7482fc1` | `73f3bdbd` plus the typed gate and branded views. Backend unchanged from A31. |
| H1/H2 | `f9dcf56` | Base plus strict checkpoint backend and console. **Does not contain the three feature pages.** |
| Audit | `e63bf90` | Documents only; its verdict (REVISE, D1/D2 open, R18 fails) is taken as given and not re-derived. |

**Fresh-checkout setup, measured (this machine, Windows 11, warm npm and pip caches, so network time is understated):**

| Pin | clone | venv | pip | npm ci | build | total |
|---|---|---|---|---|---|---|
| `f928210` | 5 s | 14 s | 54 s | 10 s | 4 s | 87 s |
| `73f3bdbd` | 5 s | 11 s | 67 s | 10 s | 4 s | 97 s |
| `7482fc1` | 5 s | 13 s | 7 s | 9 s | 5 s | 39 s |
| `f9dcf56` | 5 s | 12 s | 37 s | 10 s | 4 s | 68 s |
| `6e772e8` | 7 s | 18 s | 9 s | 13 s | 4 s | 51 s |

Server start to first answer: 0.7 to 1.2 s. Setup failures: none in the commands themselves. The failures are in the documented run flows (F2).

Two first-run mistakes of mine are kept because they affect reproducibility: my first background setup script collided with itself and was discarded and rerun sequentially; my first UI driver failed because the capture panel is `open` only while the ledger is empty (a click closed it), which is a usability trap for anyone operating it live.

## 2. The synthetic end-to-end walkthrough

`tools/walkthrough.py` drives only the documented HTTP API. Journey: register 4 motors; assemble with DE/NDE lots (`BR-901`, `BR-310`, `BR-312`; one lot-level identity); ship; announce recall of `BR-901` for DE only; replace the DE bearing on `MTR-27001` with `BR-312`; inject a late untrusted observation of `BR-901` on `MTR-27003`; read genealogy, provenance and lot investigation. Then the pages (impact trace, evidence investigation, passport) were opened over the same ledger. A separate run drove the **real UI** (`tools/uiwalk.mjs`, 12 operator steps through the capture workspace, no API shortcuts) on `f928210`: 12/12 steps succeeded, 21.7 s of step time, 23.5 s wall.

Expected outcomes were derived by hand before looking: `27001` replaced with an unaffected lot is excluded; `27002` and `27004` carry the recalled lot in DE and are affected; `27003` was as-built unaffected, so excluded, then the untrusted observation withdraws the exclusion and it must be held and flagged for review. Every pin's evaluator output matched:

| Motor | After recall | After replacement | After late observation |
|---|---|---|---|
| MTR-27001 | AFFECTED / hold | EXCLUDED_WITH_EVIDENCE / release eligible | same |
| MTR-27002 | AFFECTED / hold | AFFECTED / hold | same |
| MTR-27003 | EXCLUDED / release eligible | same | **UNRESOLVED / hold**, review required, 1 pending notification obligation |
| MTR-27004 | AFFECTED / hold | AFFECTED / hold | same |

API timing per call (one client, no load): register 18 to 39 ms, assemble 91 to 152 ms, ship 101 to 134 ms, recall 172 ms, replace 341 to 543 ms, snapshot 136 to 190 ms. Whole 27-call script: 3.3 to 3.8 s on all pins. These are single-client local figures, not a performance claim.

### 2.1 Step-by-step classification

Categories: **R** real local application and evaluator code; **F** only fixture or preview data; **I** only on an isolated frontend branch; **B** blocked by checkpoint activation or safety contract; **N** not implemented.

| Step | Status | Evidence and limits |
|---|---|---|
| 1 Motor registration | R on all pins | `POST /api/units`. Serial must match `MTR-[A-Z0-9-]{3,30}`. On A31-and-later it needs the anchor flow (F2). |
| 2 Material allocation | **Partly N, partly demo-only** | There is no allocation command. `assemble` emits `MATERIAL_ALLOCATED` itself, with raw lot and supplier hard-coded in `service.py`: `BR-204` maps to `STEEL-26-410`/Northstar, **every other lot** to `STEEL-26-518`/Kaveri. In this walkthrough the recalled lot `BR-901` was traced to Kaveri by code default, not by anything the operator entered. |
| 3 Bearing manufacture | Same as 2 | Emitted inside `assemble`; operator supplies only the lot. |
| 4 DE/NDE installation | R | Lots and identity granularity (serial or lot) are operator inputs. |
| 5 Shipment capture | R, **fixed content** | `ship` takes no input; customer "Aster Pump Systems" and destination "Coimbatore distribution centre" are constants. No carrier, quantity, date or consignee can be captured. |
| 6 Defective-lot recall | R, **one per database** | A second recall returns HTTP 400. Scope DE, NDE or both works on A31 and later; `main` hard-codes DE (F1). |
| 7 Impact trace | R on `73f3bdbd` and mixed probe P; **blocked on `7482fc1`** against A31 backend (F3); **absent** on `f928210`/`f9dcf56` except the console's lot view | Screenshot `p73_impact_graph.png`. |
| 8 Evidence investigation | Same as 7 | `p73_investigation.png`. |
| 9 Bearing replacement | R on all pins | `replace` supports the DE slot only. NDE replacement is not implemented. |
| 10 Passport inspection | R on `73f3bdbd`; blocked on `7482fc1` vs A31; absent on `f928210`/`f9dcf56` | `p73_passport_27003.png`. QR is route-only, labelled "Not a certified DPP". |

Probed and absent: EPCIS capture over HTTP (`POST /api/capture`: 404), material-receipt command (404). The EPCIS-compatible capture exists as a library inside the ledger; no external system can post to it.

## 3. What each pin shows a judge

| Pin | Run path | Result |
|---|---|---|
| `6e772e8` main | README flow | Fresh-database walkthrough works with no anchor (27 calls, none refused; `--seed-demo` on `main` was not run). **False release in the NDE case (F1).** `announce()` on `main` always writes `affectedSlots=['DE']`, so any DE-position scenario looks correct. |
| `f928210` | README literal: `--seed-demo` | Opens on a red "Recall data could not be loaded ... trusted external anchor required" (`base_readme_home.png`). Fresh DB: all commands 409. |
| `f928210` | With anchor (section 5) | Full console works: capture workspace, 5 seeded motors, notification obligation, "Verified ... lease 5 seconds" line (`base_anchored_home.png`). UI-driven journey 12/12. |
| `73f3bdbd` | With anchor | Console plus three live pages. Impact graph for `BR-901`: 3 motors linked, 2 affected, 1 excluded, 2 uncertain links, with the rejected observation drawn as an untrusted claim. 200 s soak, three pages open concurrently, sampled every 5 s: 120 of 120 samples current, none withdrawn. |
| `7482fc1` | Live, A31 backend | Console works. All three pages show "Current status unavailable (withheld): required checkpoint or eligibility metadata is missing." (`p74_*`). |
| `7482fc1` | `?mode=preview` | Works and is labelled "Preview ... nothing here is current", "Units are tagged by origin", including authored edits. |
| `f9dcf56` | After any capture | Console shows "Checkpoint required: ANCHORED_PREFIX_ONLY: current release eligibility is withheld for every motor", holds and the obligation (`pf9_console_prefix_after_capture.png`). |
| `f9dcf56` | After successor checkpoint | `ANCHORED_CURRENT`; only `MTR-27001` eligible (`pf9_console_current.png`, `pf9_snapshot_after_checkpoint_activation.json`). Export 1.0 s; restart to first `200` 1.06 s, for 4 motors and about 43 records. |
| **Probe P** (assembled artifacts, not a merge) | `7482fc1` `dist/` served by the `f9dcf56` Python tree | Activated checkpoint: all three pages show current findings (`mix_*`). Prefix-only: the three pages correctly show historical evidence only, but the **console** (its `App.tsx` is not the H1/H2 one) shows the wrong message "trusted external anchor required" (`mixp_console.png`). This shows the two branches are compatible for the new pages and **not** for the console. It is not evidence for an integration branch. |

Preview data on every pin is authored and labelled. It is the only thing that works on all feature pages without an anchor, which is its value as a fallback and its danger as a headline.

## 4. Wording and unsupported claims a judge could meet

- **"Release eligible" / "Eligible under this recall policy"** (console chip). The text beside it says "not shipment authorization", but the chip alone reads as a release. Say "recall evidence permits release review", never "cleared to ship".
- **"Verified ... lease 5 seconds"**: verification means the anchored ledger prefix and the evaluator replay match, locally, against a file the operator supplied. It is not source authentication. The CLI itself says `EXPORTED_UNTRUSTED_UNTIL_OWNER_CUSTODY_ESTABLISHED`.
- **Raw-material lot and supplier** shown in the graph are generated by the application, not captured (section 2.1, step 2). Never present them as supplier traceability.
- **Customer, destination, shipment id** are constants. Never present as shipment capture.
- **"Excluded with evidence"** the pages themselves say it "does not mean safe"; keep it that way in narration.
- **Recall date** "announced 2026-10-20 08:00:30 UTC" is a fixed synthetic clock, not the real date.
- **"Digital product passport"**: the page says "Not a certified DPP"; there is no GS1 Digital Link, DPP schema or registry.
- Nothing in the UI or docs reviewed claims physical proof or factory certification; the docs repeatedly disclaim it. The risk is narration, not text. Minor: "withheld).." and "historical.." double full stops in two messages.

## 5. The smallest reliable demo today (no source changes)

Use `73f3bdbd`, not `main`, not `7482fc1`. Do these **before** the audience arrives; total about 3 s plus the first page load.

```powershell
git checkout 73f3bdbd                         # setup as README: venv, pip, npm ci, npm run build
.venv/Scripts/python.exe -c "from application.service import Manufacturing as M; m=M('.local/demo.sqlite'); m.seed_demo(); m.close()"
.venv/Scripts/python.exe -m application.anchors export --database .local/demo.sqlite --anchor <protected-dir>/demo-checkpoint.json
.venv/Scripts/python.exe app.py --database .local/demo.sqlite --trusted-anchor <protected-dir>/demo-checkpoint.json
```

Measured: seed plus anchor 2.6 s, server up 0.7 s. Seeded ledger gives 5 motors, recall `BR-204` DE-only, 3 evidence groups, 4 uncertain links. **Do not capture new data on stage** unless you accept section 6 R3: the A31 anchor tolerates extensions, but on H1/H2 it does not.

**3-minute script (verified order):** console decision table, then `passport.html#/passport/MTR-26003/recall` (excluded, "not shipment authorization"), `impact.html#/lot/bearing/BR-204/graph` (trace and the untrusted claim), `investigation.html#/` (evidence groups, "Not a release authorization"). Type the page URLs in advance; the console does not link to them (R5). **5-minute script:** add the live capture on a **fresh** database: register, assemble, ship, recall, replace, observe (12 UI steps, about 23 s), then switch to the impact page. The recall can be announced only once per database, so prepare a second database for a retake (3 s).

## 6. Demo risk register

Likelihood and impact are my judgement from the evidence, stated as H/M/L.

| # | Risk | L / I | Evidence | Fallback (no safety bypass, nothing fabricated) |
|---|---|---|---|---|
| R1 | Judge or script clones default branch `main`: false NDE release | H / **Critical** | F1; `nde_probe.py` | Always state the SHA. Run `73f3bdbd`. If asked, show the probe on both and say `main` predates the fix. |
| R2 | Following the README gives an error screen or 409s | H / H | F2; `base_readme_home.png` | Pre-provision the anchor (section 5). If it appears live: stop, restart with the anchor, reload; say the screen is the safety gate working. |
| R3 | After a capture on H1/H2, everything shows "Checkpoint required" | H / M | F4 | Demo H1/H2 only as the gate: capture, show the warning, export successor with `--previous-anchor`, restart (about 3 s for a small ledger). Never promise instant clearance. |
| R4 | Large ledger: availability. Audit R18: 100 motors / 1,000 rows gave 12/12 `503 VERIFYING`, zero successes, 25.0 s activation | M / H if scaled | `H1_H2_INDEPENDENT_AUDIT_HANDOFF.md`, `e63bf90` | Keep the demo under about 10 motors. Say no scale claim is made. Not re-measured here. |
| R5 | Judge cannot find the three pages; console has no links | H / M | `App.tsx` has no links to them | Pre-open three tabs with the URLs from section 5. |
| R6 | `7482fc1` pages blank against A31 backend | H if chosen / M | F3; `p74_*` | Do not use `7482fc1` live. Use `?mode=preview` there and say "preview". |
| R7 | Network or CPU stall longer than 4 s: pages show "withheld"; lease is 5 s | L / M | soak ran clean 200 s | Reload. Withdrawal is by design; say so. |
| R8 | Hard-coded supplier, raw lot, customer, destination misread as real capture | M / M | section 2.1 | Say "synthetic constants" and avoid the supplier view. |
| R9 | "Release eligible" read as authorization | M / H | section 4 | Narration line from section 4. |
| R10 | Question: "can another system send EPCIS events?" | M / M | probe 404 | Honest answer: the ledger accepts EPCIS-profile documents internally; there is no HTTP ingest yet. |
| R11 | Question: splits, merges, quantities, NDE replacement | M / M | section 7 | State as not implemented. |
| R12 | Local-server exposure shown or discovered (F5) | L / H | `Host: evil.test` still served; token from any `GET /api/session`; POST succeeded without `Origin` | Run on an isolated demo machine; do not present as secure. |
| R13 | One recall per database; a retake needs a new database | M / L | HTTP 400 on second recall | Keep a second prepared database. |
| R14 | Port 4173 busy; Windows `HTTPServer` backlog; Chrome required only for tests | L / L | none seen | `--port`. |
| R15 | Preview data mistaken for live | M / M | preview banners present | Narrate "preview" before opening; the pages say so. |
| R16 | Original-suite failures: 23 Playwright and 10 Vitest failures on `7482fc1` are known and mine to disclose | L / M | Phase A and branded-views reports | Do not cite "all tests pass" for the isolated branches. |

## 7. PS10 directive review

The official PS10 problem statement is not in the repository. I used the repository's own PS10 gap analysis (`docs/PRAMAAN_REUSE_AUDIT.md`, 13 capabilities) as the directive list; if the official text differs, this table needs re-checking. Labels: COMPLETE / PARTIAL / DEMO-ONLY / MISSING / BLOCKED. No percentages are given because the directives are not weighted.

| # | PS10 capability | Label | Basis |
|---|---|---|---|
| 1 | Material batch/lot identity | **DEMO-ONLY** | Raw and bearing lot ids exist in events; raw lot and supplier are generated by two hard-coded rules. No receipt, quantity or SKU/GTIN. |
| 2 | Component and assembly genealogy | **PARTIAL** | Motor to component to lot with slot, serial or lot identity and removal history, verified live. Only bearings, DE/NDE; no multi-level assemblies. |
| 3 | Manufacturing event capture | **PARTIAL** | Events recorded as an append-only EPCIS-profile journal; exposed only through 5 fixed commands. No external ingest. |
| 4 | Split, merge, consume, rework | **PARTIAL (rework) / MISSING (rest)** | DE replacement is implemented; split, merge, consume and quantities are not. |
| 5 | Finished-product traceability | **PARTIAL** | Per-motor passport on `73f3bdbd`; non-standard, not a certified DPP. |
| 6 | Shipment and custody traceability | **DEMO-ONLY** | One constant destination and customer; no carrier or custody chain. |
| 7 | Forward/backward graph traversal | **PARTIAL** | Impact graph with trace direction on `73f3bdbd`. No depth or result limit controls beyond the page; scale untested live. |
| 8 | Defect impact analysis | **PARTIAL** | Lot recall to affected, unresolved, excluded motors, with reasons and untrusted-claim handling; one recall per database; bearings only. |
| 9 | Tamper-evident production events | **PARTIAL / BLOCKED at integration** | Hash-chained journal plus an external checkpoint on A31; stronger v2 on `f9dcf56`, which still fails audit items D1/D2 and R18 and is not merged. Checkpoint custody is an operator assertion. |
| 10 | Evidence-linked recall explanations | **PARTIAL** | Per-decision reason codes and cited evidence in console, passport, investigation. |
| 11 | Recall accuracy benchmarking | **DEMO-ONLY** | Authored synthetic cases (recorded 25/25 agreement, zero false releases in 14 unsafe cases). The repo itself says this is not a population rate. The one real escape (F1) was outside those cases. |
| 12 | Query-speed benchmarking | **PARTIAL** | Recorded local figures at 6 motors (capture-to-decision p50 1.46 s, p95 3.06 s) and the failed 100-motor run. No production dataset. |
| 13 | Partner-scoped sharing | **MISSING** | No authorization, consent or partner model; customer fields are in the unauthenticated API. |

## 8. Production readiness (separate from the demo)

| Area | State |
|---|---|
| Identity and authentication | **Absent.** No users. Session token is handed to any caller. |
| Permissions / partner scoping | **Absent** (PS10 #13). |
| Interoperability | EPCIS profile internally; no ingest, no EPCIS query API, no DPP standard. |
| Source authenticity | Producer identities are synthetic claims (`SYNTHETIC_SIMULATED` clocks, actors). Nothing authenticates a real device or system. |
| Performance | Local single-client only; the one scale run failed to serve (R4). |
| Availability | Single process, loopback, SQLite file; restart needed for checkpoint activation; 4 s client timeout. |
| Monitoring | None found. |
| Secure deployment | Loopback by design; no TLS, no Host validation, no rate limits. |
| Operational checkpoint custody | Manual file export, copy, restart. The software states it cannot establish custody. Exact-latest-checkpoint rollback is undetectable after restart (documented). |
| Customer privacy | Customer and destination in unauthenticated API; UI omission is not control. |

## 9. Smallest changes for a reliable hackathon demo (priority order, independent of the production roadmap)

None is done here. Owners decide; Codex owns the safety branches.

1. **Make `main` safe or stop pointing at it**: advance `main` to a remediated commit, or set the README/repo description to the demo SHA. Fixes R1, the only critical item.
2. **One-command demo launcher** (seed, anchor, serve, open) and a README section that says an anchor is required. Fixes F2/R2. About 30 lines, no safety change.
3. **A "demo index" page linking console, passport, investigation, impact** (the integration prep already proposed shared navigation). Fixes R5.
4. **Decide which frontend the demo shows.** Either `73f3bdbd` (works now, with the fail-open classification the integration report flagged) or `7482fc1` plus H1/H2 (safer, not yet assembled). Probe P shows the pages work; the console needs the H1/H2 `App.tsx`. That is Codex's integration, not mine.
5. **Relabel the chip** "Release eligible" to "No recall hold: review for release" (wording only).
6. **Label hard-coded material and shipment values** as synthetic constants in the UI, or remove supplier from the demo path.
7. **Keep an offline fallback**: the `?mode=preview` pages and recorded screenshots, clearly captioned.

## 10. Limits of this audit

Done once, on one Windows machine, with warm caches, Chrome headless; no mobile or screen-reader pass; no hosted CI re-run (hosted run results are cited, not reproduced); R18 and large-scale behaviour not re-measured; no real security test beyond the three loopback probes in F5; official PS10 text unavailable (section 7). Passing test suites were **not** used as evidence of any step; the table in section 2.1 rests on executed journeys. Screenshots in the evidence folder are a subset; every captured page text is in `page-text/`.

## Reproduce

`tools/setup_pin.sh <dir> <sha>` (fresh clone and README setup, timed), `tools/serve.sh`, `tools/walkthrough.py <url> <out.json>`, `tools/uiwalk.mjs`, `tools/run_a31pin.sh`, `tools/nde_probe.py`, `tools/soak.mjs`. They assume Git Bash on Windows and a Chrome install; paths in them are those of the audit machine's scratch directory and need adjusting.
