# Manufacturing PRAMAAN: hackathon demo runbook (design only)

> **KNOWN ISSUE (P0): lot-identity clearance defect.** The demo builds named here treat any lot string that is not exactly the recalled lot as unaffected, so unknown or mistyped lots can show `RELEASE_ELIGIBLE`. Do not present eligibility as robust to wrong lot identities. Read `docs/demo-runbook/KNOWN_ISSUE_LOT_IDENTITY.md` before any demo.

Branch `plan/hackathon-demo-runbook`, based on the pushed audit commit `1f8671e`. This is a **design document plus two small preflight helpers**; it changes no application source and no one else's branch. Everything below was executed on 2026-10-23 on one Windows 11 machine (Python 3.12.10, Node 24.17, Chrome headless for captures) unless marked **not run**. Evidence: `docs/demo-runbook/reference-captures/` (logs, screenshots, page text) and the audit's `docs/demo-readiness-evidence/`.

## 0. Read this first: do not run the demo from `main`

> **WARNING. Current `main` (`6e772e8`) must not be used for the demo.** It is the pre-remediation Phase 3 app. With the recalled lot in the **NDE** position and the scope left unspecified, it reports `EXCLUDED_WITH_EVIDENCE / RELEASE_ELIGIBLE`, a **false release**. The remediated code reports `AFFECTED / RECALL_HOLD`. Its seeded demo hides this because `main` always writes a DE-only scope. `preflight.py scratch` fails on `main` (log: `logs/preflight_scratch_main_6e772e8_NEGATIVE_CONTROL.txt`) and passes on the demo SHA.

Before anything else, in the demo checkout: `git rev-parse HEAD` must print exactly `73f3bdbd78ee8bdf4b323457ba2f036f16fb82d9`. If it prints anything else, stop.

## 1. Source to use

| Item | Value |
|---|---|
| Repository | `https://github.com/mohammedsuhailrafek28/PRAMAAN-Manufacturing` |
| Branch (exists on origin) | `integration/three-features-prep` |
| **Exact SHA** | **`73f3bdbd78ee8bdf4b323457ba2f036f16fb82d9`** |
| Content | A31 hardened backend (`f928210`, recall scope fix, external anchor, five-second lease) plus the console and the three pages: passport, investigation, impact graph |
| Not used, and why | `main`: false release. `7482fc1` (branded frontend): its live pages show "withheld" on this backend. `f9dcf56` (H1/H2): backend and console only, no three pages, and the audit's REVISE verdict stands |

Known limits of this SHA, stated up front: it carries the A31 anchor model, not H1/H2; the three pages classify "withhold or show non-current" with the older rule the integration report flagged as fail-open for unforeseen errors (every case tested withheld correctly); the console does not link to the three pages.

## 2. Clean installation (PowerShell; measured 97 s with warm caches)

Prerequisites: Python 3.12+, Node 24+, npm, Git, Chrome. Pick an empty folder, e.g. `C:\demo`.

```powershell
git clone https://github.com/mohammedsuhailrafek28/PRAMAAN-Manufacturing.git C:\demo\pramaan
Set-Location C:\demo\pramaan
git checkout --detach 73f3bdbd78ee8bdf4b323457ba2f036f16fb82d9
git rev-parse HEAD                      # MUST equal the SHA above
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r integration/requirements.lock
Set-Location recall-ui
npm ci --ignore-scripts
npm run build
Set-Location ..
```

Measured on this machine: clone 5 s, venv 11 s, pip 67 s, npm ci 10 s, build 4 s. Caches were warm, so a cold network will take longer: do this the day before, not on stage. Get the two helpers (they are not part of the demo SHA):

```powershell
git clone --branch plan/hackathon-demo-runbook https://github.com/mohammedsuhailrafek28/PRAMAAN-Manufacturing.git C:\demo\runbook   # only after the owner has pushed this branch
$RB = "C:\demo\runbook\docs\demo-runbook"
```

(Until that branch is pushed, copy `preflight.py` and `prepare_db.py` from the review tree.) Never run the helpers from inside a different checkout's `.venv`; always use the demo checkout's.

## 3. Seeding, trusted-anchor preparation and activation

### 3.1 What the anchor is, and what it is not

The application refuses all current decisions and all commands unless started with `--trusted-anchor <file>`: a checkpoint of the ledger's identity and journal position. The README's own `--seed-demo` flow **omits this step and opens on a red "Recall data could not be loaded" screen** (audit F2); a fresh database returns HTTP 409 to every command.

`application.anchors export` itself prints `EXPORTED_UNTRUSTED_UNTIL_OWNER_CUSTODY_ESTABLISHED`. On a demo laptop, **you** are the custodian. The file is a stand-in for independently held custody. Say exactly that if asked; never say the ledger was independently verified. Keep the anchor outside the repository folder, set it read-only, and never re-export it during the demo.

### 3.2 Seeded ledger for the 3- and 5-minute scripts (measured: 2.8 s)

```powershell
New-Item -ItemType Directory -Force C:\demo\custody | Out-Null
.\.venv\Scripts\python.exe "$RB\prepare_db.py" seeded .local\demo.sqlite
.\.venv\Scripts\python.exe -m application.anchors export --database .local\demo.sqlite --anchor C:\demo\custody\demo-checkpoint.json
.\.venv\Scripts\python.exe -m application.anchors verify --database .local\demo.sqlite --anchor C:\demo\custody\demo-checkpoint.json   # expect "status": "VERIFIED_TRUSTED_PREFIX"
attrib +R C:\demo\custody\demo-checkpoint.json
```

`prepare_db.py` refuses to touch an existing file (tested: prints REFUSED, exit 1). Contents: 5 synthetic motors MTR-26001..26005, recall `RC-026-014` on lot `BR-204`, **DE explicitly**.

### 3.3 Empty ledger for the live-capture segment (5-minute script)

```powershell
.\.venv\Scripts\python.exe "$RB\prepare_db.py" empty .local\live.sqlite
.\.venv\Scripts\python.exe -m application.anchors export --database .local\live.sqlite --anchor C:\demo\custody\live-checkpoint.json
attrib +R C:\demo\custody\live-checkpoint.json
```

An anchor taken on the empty ledger is accepted as the ledger grows (valid extensions are tolerated on this SHA; tested over the 12-step capture). The recall can be announced **once per database**; prepare `live2.sqlite` and `live2-checkpoint.json` the same way as a retake.

### 3.4 Activation

Run the server in its own window; one process serves UI and API on loopback.

```powershell
.\.venv\Scripts\python.exe app.py --database .local\demo.sqlite --port 4173 --trusted-anchor C:\demo\custody\demo-checkpoint.json
```

Measured: answers in 0.7 to 1.3 s. For the live segment, stop it and start the same command with `.local\live.sqlite` and `live-checkpoint.json` (or run it on port 4174 for a second window; the pages use their own origin).

## 4. Preflight (do it twice: the day before and 30 minutes before)

All commands from the demo checkout root. Any `FAIL` or non-zero exit means **do not demo**; fix or fall back to section 11.

| # | Command | Must show |
|---|---|---|
| P1 | `git rev-parse HEAD` | `73f3bdbd78ee8bdf4b323457ba2f036f16fb82d9` |
| P2 | `.\.venv\Scripts\python.exe "$RB\preflight.py" scratch` | 12 PASS lines and `PREFLIGHT PASSED` (1.9 s) |
| P3 | `.\.venv\Scripts\python.exe "$RB\preflight.py" server http://127.0.0.1:4173` with the seeded server running | 15 PASS lines and `PREFLIGHT PASSED` |

**What P2 proves** (disposable databases built through the application's own service layer; it never touches the demo ledger). The same three motors are recalled under three scopes, lot `BR-901`:

| Scope | MTR-91001 (DE `BR-901`, NDE `BR-310`) | MTR-91002 (DE `BR-310`, NDE `BR-901`) | MTR-91003 (clean) |
|---|---|---|---|
| omitted (default both positions), policy slots `[DE, NDE]` | AFFECTED / RECALL_HOLD | **AFFECTED / RECALL_HOLD** (the NDE case `main` gets wrong) | EXCLUDED / RELEASE_ELIGIBLE |
| `[DE]` | AFFECTED / RECALL_HOLD | EXCLUDED / RELEASE_ELIGIBLE (correct for a DE-only policy) | EXCLUDED / RELEASE_ELIGIBLE |
| `[NDE]` | EXCLUDED / RELEASE_ELIGIBLE | AFFECTED / RECALL_HOLD | EXCLUDED / RELEASE_ELIGIBLE |

**What P3 proves** (GET only): freshness is `VERIFIED_ANCHORED_SYNTHETIC` with a 5 s lease; the live recall is `BR-204`, DE, `EXPLICIT_POSITIONS`; the five motors have exactly AFFECTED/hold (26001), UNRESOLVED/hold (26002, 26004, 26005) and EXCLUDED/release-eligible (26003); one pending notification obligation; the four HTML entry points return 200. **P3 proves the seeded DE policy only**; the NDE evidence is P2 (and the live segment, section 7). Do not claim more.

## 5. URLs (port 4173; substitute your port)

| Page | Live URL | Opens as |
|---|---|---|
| Console | `http://127.0.0.1:4173/index.html#/` | Motor decisions table; the capture workspace panel is closed once a ledger has motors |
| Passport (excluded motor) | `http://127.0.0.1:4173/passport.html#/passport/MTR-26003/recall` | seeded ledger |
| Passport (held motor) | `http://127.0.0.1:4173/passport.html#/passport/MTR-26004/recall` | seeded ledger |
| Passport index | `http://127.0.0.1:4173/passport.html#/` | list of motors |
| Investigation | `http://127.0.0.1:4173/investigation.html#/` | |
| Impact graph (seeded) | `http://127.0.0.1:4173/impact.html#/lot/bearing/BR-204/graph` | |
| Impact graph (live segment) | `http://127.0.0.1:4173/impact.html#/lot/bearing/BR-901/graph` | |
| Live segment passports | `.../passport.html#/passport/MTR-302/recall`, `.../MTR-301/recall` | |

The console has **no links** to the three pages. Pre-open them in numbered tabs before the audience arrives.

Authored preview and fixture URLs exist (section 10) and are **not** part of either script: `passport.html?mode=preview#/passport/MTR-26004`, `investigation.html?mode=preview#/`, `impact.html?mode=preview#/lot/bearing/BR-204/graph`, `index.html?mode=fixtures#/`.

## 6. Three-minute walkthrough (seeded ledger, no typing)

Expected strings are copied from the captures in `reference-captures/page-text/` (taken 2026-10-23). Journal sequence, head hash and "verified at" time differ on every run; do not read them aloud as fixed values.

| Time | Open | Say | Expect on screen |
|---|---|---|---|
| 0:00 | Tab 1, console | "Synthetic motors; one defective bearing lot is under recall. The decisions below come from a deterministic evaluator over an append-only record." | `Live ledger. Synthetic manufacturing data; not production.` `Recall RC-026-014 v1 ... lots BR-204, slots DE.` `Verified with local synthetic backend at <time>; lease 5 seconds, refresh every 2 seconds.` Counters: `5 motors`, `1 ▲ affected`, `3 ? unresolved`, `1 ✓ excluded with evidence`, `4 on recall hold`, `1 release eligible`, `3 review required`. Notification box: `PENDING ... no notifications are sent by this application.` |
| 0:40 | Tab 2, passport MTR-26003 | "This motor's records show it is not affected. The page says it is evidence only." | `No recall hold recorded under this policy` · `Excluded with evidence. Evidence shows the motor is not affected.` · `This is a statement about recall evidence only. It is not shipment authorization, a quality release or a certificate.` Banner: `Not a certified DPP` |
| 1:05 | Tab 3, passport MTR-26004 | "This one is held: capture was down for a period that could have hidden a change." | `Held under the recall policy` · `Unresolved. Evidence cannot show the motor is clear. It stays held.` · `Review is required.` · `Material capture gap: ...` |
| 1:30 | Tab 4, impact graph BR-204 | "Every motor linked to the recalled lot, and every link, with uncertainty drawn." | `Lot BR-204 is named by recall RC-026-014 for slot DE. 3 motors have a ledger-recorded link to it (1 affected, 2 unresolved). 3 motors have a recorded shipment record. 4 recorded links are uncertain, conflicting or missing.` and `These are ledger records, not a physical verification of any motor. Excluded with evidence does not mean safe ...` Tiles: `3 motors linked`, `1 Affected`, `2 Unresolved`, `1 named only by a rejected claim`. A dotted "rejected observation" node. |
| 2:15 | Tab 5, investigation | "Why each motor needs a person: grouped by the evidence gap, not by confidence scores." | Badges `Read-only`, `Not a release authorization`. `3 evidence items across 3 motors, in 3 evidence-gap groups.` Groups: Untrusted affected-lot observation (MTR-26005), Ambiguous slot attribution (MTR-26002), Capture gap (MTR-26004). `Covers 58 ledger records and 5 current decisions.` |
| 2:50 | Stay | Closing lines from section 9 | |

Measured: each page loaded within 4 s; the three pages held open together for 200 s all stayed current (120 of 120 samples).

## 7. Five-minute walkthrough (3-minute script compressed to 2:15, plus a live capture)

Run 0:00 to 2:15 as above, but skip the investigation tab. Then stop the seeded server and start the **live** one (section 3.3/3.4; 5 s). In the console, expand **Manufacturing capture workspace** (it is open by default on an empty ledger; a click would close it). Type exactly:

| Step | Input in the capture workspace | Measured | Expect |
|---|---|---|---|
| 1 | New motor serial `MTR-301` → Create unit | 0.8 s | 1 motor |
| 2 | Motor `MTR-301`; DE bearing lot `BR-901`; NDE bearing lot `BR-310`; Identity `Distinct serial markings` → Capture bearing assembly | 2.1 s | assembly recorded |
| 3 | Record synthetic shipment | 2.0 s | shipment `SHP-26-301` |
| 4 | Repeat 1–3 for `MTR-302`: DE `BR-310`, NDE `BR-901` (the **NDE-only exposure**) | ~5 s | |
| 5 | Repeat 1–3 for `MTR-303`: DE `BR-310`, NDE `BR-312` | ~5 s | |
| 6 | Defective bearing lot `BR-901`; Recall positions **Both DE and NDE (conservative default)** → Announce recall and evaluate | 2.3 s | `Recall RC-026-014 v1 ... lots BR-901, slots DE, NDE` |
| 7 | Motor `MTR-301`; Replacement DE lot `BR-312` → Capture authorized DE replacement | 2.4 s | |
| 8 | Motor `MTR-303` → Inject late untrusted affected-lot observation | 2.4 s | |

The whole sequence took 23.4 s through the real UI (12 steps, none failed). Final state, verified over the API and on the pages:

| Motor | Result | Passport text |
|---|---|---|
| MTR-301 (DE replaced) | EXCLUDED_WITH_EVIDENCE / RELEASE_ELIGIBLE (`REPLACED_WITH_UNAFFECTED_LOT`) | `No recall hold recorded under this policy` · `Replaced with unaffected lot: The slot now holds a verified, unaffected lot.` |
| MTR-302 (NDE lot recalled) | AFFECTED / RECALL_HOLD | `Held under the recall policy` · `Affected. Evidence shows the motor holds an affected lot.` |
| MTR-303 (late observation) | UNRESOLVED / RECALL_HOLD, review required; one pending obligation | `Held ... Precautionary hold` |

Then open the impact graph for `BR-901`: `Lot BR-901 is named by recall RC-026-014 for slots DE, NDE. 2 motors have a ledger-recorded link to it (1 affected, 1 excluded with evidence). ... 1 named only by a rejected claim`. Narrate: "the NDE exposure is held, which is what the preflight proved." Tiles `2 motors linked`, `1 Affected`, `1 Excluded with evidence`, `1 named only by a rejected claim`; scope list `DE NDE`. Investigation shows `1 evidence item across 1 motor` (MTR-303). Replacement works for the DE slot only; do not offer to replace NDE.

Timing budget: 2:15 + 0:10 switch + 0:25 capture steps (rehearse; type serials in advance in a notes file) + 0:40 narration of results + 0:30 impact + 0:20 investigation + 0:20 close = about 5:00.

## 8. Checkpoint-required behaviour and safe explanations

**On the demo SHA you should not see "checkpoint required".** That state belongs to the H1/H2 candidate (`f9dcf56`), which is a separate checkout and **console only**. If a judge asks about it, or you choose to show it as the safety design, use the recorded captures (`pf9_console_prefix_after_capture.png`, `pf9_console_current.png`, in the audit evidence) and say:

- "In the stricter candidate, any new capture makes the ledger newer than the trusted checkpoint. It then refuses to call any motor releasable until a new checkpoint is exported, independently protected, and the server is restarted with it. Holds and evidence are still shown."
- It is not a bug and not a crash; the screen says: `Checkpoint required ... ANCHORED_PREFIX_ONLY: current release eligibility is withheld for every motor ... Exporting a local candidate does not establish trust.`
- Measured there, for a 4-motor, ~43-record ledger: export 1.0 s, restart to first answer about 1.1 s. At 100 motors / 1,000 journal rows the audit measured only `503 VERIFYING` responses and 25 s activation: **do not claim scale**.

**Recorded captures only (owner decision, 2026-10-23).** The H1/H2 checkpoint segment is shown during judging from the recorded captures only. Do not run live H1/H2 transitions until the integrated backend has been independently safety-reviewed and the full demo has passed a complete rehearsal. This runbook makes no claim that H1/H2 has passed independent safety certification; the audit verdict on `f9dcf56` is REVISE.

On-screen states on the demo SHA, what they mean, what to say:

| Message | Meaning | Say | Do |
|---|---|---|---|
| `Recall data could not be loaded ... trusted external anchor required` (console) | Server started without `--trusted-anchor` | "The safety gate is working: without a checkpoint it will not show decisions." | Restart with the anchor (section 3.4). Do not use fixtures. |
| `Trusted anchor missing or unreadable` (API, pages show withheld) | Anchor does not match this ledger or cannot be read | Same | Check you started the right ledger/anchor pair. |
| `Current status unavailable (withheld): ...` / `unavailable` / `withdrawn` on a page | Backend stalled, stopped, or lease lapsed (5 s) | "The page withdraws current claims rather than showing stale ones." | Section 11. |
| `Not current` / `Preview: not current` | You opened a `?mode=preview` URL | "That is authored preview data." | Use the live URL. |

## 9. Claims judges may and may not be told

**May say** (each is backed by something run in this audit):
- The data is synthetic. Decisions are produced by a deterministic evaluator over an append-only, hash-chained record, and every decision shows its reason codes and cited records.
- Recall scope is explicit per position (DE, NDE or both), and the default is both. A motor with the recalled lot in the NDE position is held (preflight P2).
- A late, untrusted observation withdraws an earlier exclusion and puts the motor on hold for review.
- The pages show current status only while the server's five-second verified lease is valid, and withdraw it on outage; recovery needs no reload (measured: withdrawn within 1 s of the backend stopping, current again 1.5 s after it restarted).
- The system distinguishes finding, hold and review; "excluded with evidence" does not mean safe.
- The checkpoint step exists because we do not trust a database file merely because it is local; on this build the file is exported by the operator.
- No notification is sent; obligations are shown as pending.

**May not say:**
- That it is production-ready, certified, secure, authenticated, multi-user or deployed; or that it has been tested at factory scale.
- That the decisions or supplier links reflect physical truth, that a bearing was inspected, or that a "release eligible" motor is cleared to ship. Say "recall evidence permits release review".
- That raw-material lots and suppliers were captured: they are generated by the application (every lot except `BR-204` maps to the same supplier). Shipment customer and destination are constants, not captured data.
- That EPCIS events can be sent in from other systems (the profile is internal; no ingest endpoint), or that it implements split, merge, quantities, NDE replacement or partner-scoped sharing.
- That the ledger is "independently verified" or "tamper-proof": the anchor is operator-held; the CLI calls it untrusted until custody is established; exact-latest-checkpoint rollback is a documented residual.
- That the passport is a certified DPP or standards-conformant.
- Any accuracy or speed figure for real data. The recorded benchmarks are authored synthetic cases and a 6-motor local run.
- That H1/H2 is complete or merged, or that the three pages and H1/H2 run together: they have only been probed as assembled artifacts, not integrated.
- Anything about `main`.

## 10. Live ledger versus authored preview and fixtures

| | Live ledger (the demo) | `?mode=preview` pages | `?mode=fixtures` console |
|---|---|---|---|
| Source | SQLite ledger created in this session through the application | Captured JSON files shipped in the build | Fixture-backed snapshot |
| Labels | `Source: Live SQLite ledger (synthetic manufacturing demo)` | `Source: Preview: captured synthetic snapshot (not a live ledger)`; `Preview: not current`; `Records are not currently verified` | `Synthetic fixtures. Not real production data.` `Source: Fixture-backed snapshot.` |
| Content | The motors you created or seeded; recall `RC-026-014` | Includes **authored edits** (shared capture-gap id on MTR-26015/26016; link edits on four units; "Large stress data (authored)" clones) and extra units tagged by origin | 24 motors, recall `RC-009`, lots BR-204 **and** BR-207, two policies: not the live recall |
| Verification | Needs the anchor; five-second lease | None. Nothing is current | None |
| Safe to show as the product working? | Yes | **No.** Decisions are real evaluator output over authored data. Only for "how the pages look at scale" with the label read aloud | **No.** Different dataset and recall |

There is no silent fallback: when the backend fails the live pages show an error, not preview data (tested). Never reach for a preview URL to hide a failure; if you use one, say so first.

## 11. Recovery steps

| Failure | Detection | Action |
|---|---|---|
| Backend process died | Pages show `unavailable` within about 1 s | Restart the same command (section 3.4; 1.3 s). Pages recover by themselves about 1.5 s later. Say "it withdrew its claims and recovered". Tested: killed at +8 s, withheld at +8.3 s, current again at +20.6 s with the restart at about +19 s. |
| Port 4173 busy | Server fails to bind | `--port 4174` and use that origin in all URLs. |
| Browser hung or closed | | Reopen Chrome and the numbered URLs; state is server-side. |
| Wrong ledger or anchor | `Trusted anchor missing or unreadable` | Stop; start with the matching pair. Never re-export an anchor over a ledger you did not just create. |
| Live capture partially applied or recall typo | A capture failed, or recall announced with wrong lot | The recall is once per database. Switch to `live2.sqlite` with its own anchor; this takes 5 s. Do not edit the database. |
| Preflight `FAIL` | Section 4 | Do not demo live. Section 12. |
| Machine reboot | | Re-run section 3.4 and P3. |
| Laptop clock jumped | Lease errors | Restart the server; fix the clock; if it persists, section 12. |

Never: edit the anchor, run `?mode=preview` to mask an outage, start from `main`, or add a fixture fallback.

## 12. Backup recorded demonstration plan

Record **before** the event, on the exact SHA, from the same script, and label the video and every slide **"Recorded run of 73f3bdbd on <date>, synthetic data, not live"**.

1. Record screen plus voice for the 3-minute script (seeded) and for the 5-minute live segment, with the preflight output (P1–P3) shown first on screen.
2. Keep a still per beat: the reference captures in `reference-captures/screenshots/` (console, passports 26003/26004, investigation, impact for `BR-204`, and the live segment `rb_*`) are from the tested run and can be used as stand-ins; replace them with your own recording for the final deck.
3. If the live backend cannot be restored in 60 s, say: "The live demonstration is not available, so this is a recording of an earlier run of the same build", then play it. Do not open preview or fixture pages in its place.
4. Keep the three-line caption visible: SHA, date, "recorded".

## 13. Known presentation quirks (cosmetic, observed)

Some reason codes render as `No description available for this code.` (for example `As built unaffected lot`). Two messages end with a doubled full stop. Every page logs one 404 for `/favicon.ico` in the console. The impact graph is wider than a 1280 px window and scrolls sideways. The recall date shown (`2026-10-20 08:00:30 UTC`) is a fixed synthetic clock, not today. Newly created motors show the default description `IE3 11 kW electric motor`. The console's "Release eligible" chip is easy to over-read: always pair it with the passport sentence "not shipment authorization".

## 14. What was and was not run for this runbook

Run: clone, install and build of the demo SHA; seeding, anchor export and verify in PowerShell; refusal to overwrite; preflight P2 (pass on the demo SHA and `f928210`, fail on `main`); P3 against the seeded server; the 12-step live capture through the real UI on a fresh ledger with a default both-position recall; page captures for every URL above; backend kill and recovery with a page held open; missing and mismatched anchor; a 200-second three-page soak (in the audit). **Not run:** a second machine or a cold network; a live H1/H2 segment (now excluded from judging by owner decision); any browser other than Chrome; mobile; screen readers; a projector at lower resolution; the helpers under macOS or Linux. The helpers `prepare_db.py` and `preflight.py` are new review tooling, not application source.

## 15. Open items for the owner

1. Approve pushing `plan/hackathon-demo-runbook` (not pushed).
2. Decide whether to correct `main` or to name the demo SHA in the repository description (audit item 9.1).
3. ~~Decide whether to show the H1/H2 checkpoint behaviour live~~ Decided 2026-10-23: recorded captures only (see section 8).
