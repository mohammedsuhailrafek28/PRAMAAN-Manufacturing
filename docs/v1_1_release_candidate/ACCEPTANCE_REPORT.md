# Final demo acceptance audit

Audited checkout: fresh clone of `release/v1-1-demo-candidate` @ tip `7b31fecad58b690fd5a3cead38bc215be1096573` (validated code SHA `f7027bf385bb35fd4a7de64dacedda8f3dec4872`), pinned Python 3.12.10, `npm run build`, pinned Chrome 155.0.8059.84 driven by Playwright (automated, **not a human operator**). Loopback, synthetic data. No application, evaluator, integration or UI source was changed. Only `docs/` was added/edited afterwards (this report, the corrected runbook, `demo_prestage.py`, `acceptance/`).

## Defects found in my own runbook (fixed, docs only)
1. **Runbook flow was impossible in the UI.** While the checkpoint is stale the console hides the capture workbench (only the recovery workspace shows), so "capture DEMO-1, capture DEMO-2, then ship" cannot be done without a cycle between captures. Runbook rewritten around a pre-staged ledger (`demo_prestage.py`), then re-executed end to end.
2. The first runbook's pre-flight used a test bootstrap that did not stage DEMO-1/DEMO-2; replaced by `demo_prestage.py` (refuses to overwrite).
3. Timing: the cycle is two CLI commands plus a server restart; a human typing them needs far more than the scripted ~4 s. The runbook now says to run it from history or show later steps from screenshots.

## Item 3: workbench "Record synthetic shipment" button (measured, no UI change)
- On a **refused** shipment (recall-held MTR-DEMO-2, checkpoint current): **yes, a generic full-page error screen**: "Recall data could not be loaded … the backend could not be reached or answered unexpectedly. HTTP 409 … No decisions are shown" with a "Reload verified ledger" link (`acceptance/11-workbench-ship-MTR-DEMO-2-0.8s.png`). It is transient: the 2-second refresh restored the normal console by 7 s (`12-…-7s.png`). Nothing was written (`shipment: false`). The text is misleading (the backend was reachable and answered correctly) but it fails closed. No UI change applied.
- On an **eligible** motor (MTR-DEMO-1, current): shipment recorded, console switches to "Checkpoint required" (`13`, `14`), next cycle shows the shipment (`15`).
- The button exists only while the checkpoint is current; it is absent while stale.

## Other observations
- Browser console: `Pattern attribute value MTR-[A-Z0-9-]{3,30} is not a valid regular expression` (the serial input's `pattern` is invalid under the browser's `v` flag, so client-side validation of the serial is silently skipped; the server still validates). Cosmetic. The other console errors are `ERR_CONNECTION_*` during the scripted server restarts and one expected 409.
- Offline: the built UI references no external resource (only XML namespace strings); startup needs no network. **Not** tested with the network physically disabled.
- No screen recording: Playwright video needs an ffmpeg download I did not make without approval. 18 screenshots + a step log instead.

## Release checklist
| # | Item | Result |
|---|---|---|
| 1 | Original runbook executes as written from a clean setup | **FAIL** (defects above) |
| 1b | Corrected runbook executes end to end in Chrome from a clean setup (17/17 steps, 43 s scripted) | **PASS** (automated; not a human run) |
| 2a | Motors console current: eligible vs recall hold | PASS |
| 2b | DPP / passport (MTR-26003 no hold; MTR-DEMO-2 "Held under the recall policy") | PASS |
| 2c | Genealogy incl. shipment note | PASS |
| 2d | Evidence investigation (3 clusters, 5 after sighting) | PASS |
| 2e | Recall impact graph | PASS |
| 2f | Stale console "Checkpoint required", no decision text | PASS |
| 2g | Recovery workspace + operator cycle + restart on successor | PASS |
| 2h | Shipment refusal via API (stale; recall hold with forged claims) | PASS |
| 2i | Shipment refusal via workbench button | PASS (fails closed) with generic error screen |
| 2j | Eligible shipment via workbench button, then checkpoint required, then cycle | PASS |
| 2k | Unverified sighting contained per motor | PASS |
| 3 | Workbench button error behaviour reported | PASS (reported above) |
| 4a | Screenshots | PASS (18) |
| 4b | Offline demo recording | **NOT VERIFIED** (not produced) |
| 5a | Offline startup / recovery instructions work (prestage, server, cycle, delete-and-restage, script fallback) | PASS |
| 5b | Works with the network physically disabled | **NOT VERIFIED** |
| 6 | Hosted run exact SHA and result | PASS: run 40094032654, https://github.com/mohammedsuhailrafek28/PRAMAAN-Manufacturing/actions/runs/40094032654, head `7b31fecad58b690fd5a3cead38bc215be1096573`, conclusion `success`. The run for any later docs-only tip is reported in the review message |
| 7 | No application/evaluator/integration/UI source differs between `f7027bf` and the hosted tip | **PASS**: `git diff f7027bf 7b31fec` outside `docs/` is one line in `.github/workflows/phase31-release-gates.yml` (branch added to push triggers). Re-checked for the docs-only tip |
| 8 | Local A–K, mutation 30/30, API rehearsal 10/10 at `f7027bf` | PASS (see `OWNER_REPORT.md`) |
| 9 | Human (non-scripted) rehearsal within five minutes | **NOT VERIFIED** |
| 10 | Independent verification / production readiness | **NOT CLAIMED** |

## Known prototype limitations (for the judges)
- Research prototype on synthetic data, loopback only; not production-ready.
- Checkpoint custody is same-host and operator-asserted; it is not independent verification.
- Decisions rest on a locally authored synthetic lot registry and unverified supplier/physical claims; the system does not prove a bearing's physical identity.
- Any capture (including a shipment) makes the checkpoint stale until an operator cycle; the console then shows no decisions by design.
- Conservative holds: look-alike or shared labels hold all motors; unverified sightings hold the sighted motor.
- Shipment gating covers the application's operation, not someone editing the database file directly.
- No notifications are sent; the independent benchmark has not been scored; hosted CI proves the repository's own gates only.
- The workbench shows a generic error for a refused shipment.
