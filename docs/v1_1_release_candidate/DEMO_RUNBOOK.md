# 5-minute live demo runbook (and offline fallback) — corrected after the browser acceptance audit

Loopback only (127.0.0.1), disposable synthetic data, no network, no notification delivery. Research prototype: say so first. Same-host custody, operator-asserted: **not** independent verification, **not** production-ready, benchmark **not** independently scored.

This version replaces the first runbook, which was wrong for the UI: while the checkpoint is stale the console hides the capture workbench (it shows only the recovery workspace), so captures cannot be chained in the UI without a checkpoint cycle between them. The flow below was executed in Chrome end to end (`acceptance/`).

## Before going on stage (not part of the 5 minutes)
From the repository root of the exact checkout (record `git rev-parse HEAD`), with the pinned Python 3.12 environment first on `PATH`:
```
python -B docs/v1_1_release_candidate/demo_rehearsal.py rehearsal.json          # must print REHEARSAL PASSED (offline fallback #1)
(cd recall-ui && npm run build)                                                  # the server serves recall-ui/dist
python -B docs/v1_1_release_candidate/demo_prestage.py demo/ledger.sqlite demo/custody/root.json   # refuses to overwrite; delete demo/ to restart
python -B app.py --database demo/ledger.sqlite --port 4173 --custody-dir demo/custody --trusted-anchor demo/custody/root.json
```
Open `http://127.0.0.1:4173/`. Keep a second terminal in the repo root. To reset the demo: stop the server, delete `demo/`, run the prestage line again.

Cycle commands for the second terminal (the audit script `acceptance/demo_browser_acceptance.cjs` shows the exact arguments; stop the server first, restart it afterwards with `--trusted-anchor <new> --previous-anchor <old>`):
```
python -B -m application.checkpoint_ops propose --database demo/ledger.sqlite --current demo/custody/root.json --custody-dir demo/custody
python -B -m application.checkpoint_ops accept  --database demo/ledger.sqlite --current demo/custody/root.json --custody-dir demo/custody --candidate <candidate> --custodian "Demo operator" --confirm-sha256 <candidateSha256> --registry-digest <review.registry.digest> [--acknowledge <motor> ...]
```
(For later cycles add `--current-previous <the checkpoint before current>`.) The propose output lists `review.requiresAcknowledgement`: pass each as `--acknowledge`.

## The five minutes (staged state: DEMO-1 clean and eligible, DEMO-2 on the recalled lot BR-204, checkpoint current)
| t | Show | Say |
|---|---|---|
| 0:00 | Motors console: current, DEMO-1 "Release eligible", DEMO-2 and the seeded motors "Recall hold" | "Synthetic motors, a bearing-lot recall (BR-204, drive end). Decisions are shown only while a trusted checkpoint covers the ledger exactly." |
| 0:30 | Product passports (`passport.html`, MTR-26003 / MTR-DEMO-2), genealogy of MTR-26001, Evidence investigation, Recall impact graph (BR-204) | "Same ledger, four views: passport, genealogy, investigation, impact." |
| 1:00 | Open "Manufacturing capture workspace", create unit `MTR-DEMO-3` | "Any capture moves the ledger past the checkpoint. The console now says 'Checkpoint required' and shows no decision." |
| 1:30 | Terminal: `curl` POST `/api/units/MTR-DEMO-1/ship` with header `X-Pramaan-Token` (from `/api/session`) and `Origin: http://127.0.0.1:4173` → `409 SHIPMENT_REFUSED` | "Even the clean motor cannot be shipped while stale. Nothing is written." |
| 2:00 | Recovery workspace on the stale console | "Recovery can record evidence and propose a successor. It cannot ship, release or activate anything." |
| 2:15 | Run propose + accept, restart the server | "A human operator accepts the successor. Same-host, operator asserted." |
| 3:00 | Console: DEMO-1 eligible, DEMO-2 hold; DEMO-2 passport "Held under the recall policy" | "Eligibility is computed from evidence, never from a client claim." |
| 3:30 | `curl` ship `MTR-DEMO-2` with body `{"currentReleaseEligible":true,"force":true}` → 409. Then workbench → select MTR-DEMO-1 → "Record synthetic shipment" → recorded; console returns to "Checkpoint required" | "Recall-held: refused even with forged claims. Eligible and current: recorded; the shipment itself needs the next checkpoint cycle." |
| 4:15 | Workbench is only available while current: select MTR-26003, "Record unverified sighting" `ZZ-9`, cycle, open MTR-26003 decision | "Unverified evidence is contained per motor: that motor stays held while others renew." |
| 4:50 | Close | State the limits below. |
Real-time budget: the two operator cycles take about 4 s each when scripted but a typed manual cycle takes a minute or more. To keep to five minutes, run the first cycle live and show the sighting step from the recorded screenshots, or run the cycle commands from shell history.

## Do not
- Click "Record synthetic shipment" on a motor you expect to be refused unless you want to show it: **measured** behaviour is a full-page red "Recall data could not be loaded … HTTP 409 … the backend could not be reached or answered unexpectedly" screen for about 1–2 s, after which the 2 s refresh restores the console (nothing was written). It is a generic error, not a purpose-built refusal message. Show refusals with `curl`.
- Use a look-alike of the recalled lot (for example `BR-2O4`): it deliberately blocks renewal for **all** motors. Use `ZZ-9`.
- Say "production-ready", "independently certified/validated" or "safe to ship"; say "release eligible under the current checkpoint".

## Offline fallback
1. **No network is needed at any point**: the built UI loads no external resource (the only URLs in `recall-ui/dist` are XML namespace strings), and the server binds 127.0.0.1. Not tested with the network physically disabled.
2. **No browser or UI build**: `python -B docs/v1_1_release_candidate/demo_rehearsal.py` starts the real server on port 4290 and prints PASS/FAIL for 10 steps; narrate its output.
3. **Server will not start or the demo ledger is corrupted**: stop everything, delete `demo/`, re-run the prestage line and the server line (about 10 s). Do not hand-edit a database.
4. **Nothing runs**: show `acceptance/*.png` (18 screenshots captured from the exact checkout) and `OWNER_REPORT.md`. Say they are recordings, not a live run. No screen recording exists (video capture needs an ffmpeg download that was not approved).
