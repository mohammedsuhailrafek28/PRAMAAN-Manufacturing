# 5-minute live demo runbook (and offline fallback)

Loopback only (127.0.0.1), disposable synthetic data, no network, no notification delivery. Research prototype: say so first. Same-host custody, operator-asserted: say it is **not** independent verification, **not** production-ready, and the benchmark is **not** independently scored.

## Before going on stage (once, ~3 min, not part of the 5)
Run from the repository root of the exact release-candidate checkout (record `git rev-parse HEAD`):
```
python -B docs/v1_1_release_candidate/demo_rehearsal.py rehearsal.json      # API-level rehearsal; must print REHEARSAL PASSED
cd recall-ui && npm run build && cd ..                                         # the server serves recall-ui/dist
python -B recall-ui/tests/owned_bootstrap.py demo/ledger.sqlite demo/custody/root.json   # throw-away seeded ledger + root checkpoint (test-style bootstrap)
python -B app.py --database demo/ledger.sqlite --port 4173 --custody-dir demo/custody --trusted-anchor demo/custody/root.json
```
Open `http://127.0.0.1:4173/`. Use the repository's pinned Python 3.12 environment. Keep a second terminal for `checkpoint_ops` and `curl`.

## The five minutes
| t | Show | Say |
|---|---|---|
| 0:00 | Motor decisions console, all motors with a checkpoint chip "current" | "Synthetic motors, a bearing-lot recall (BR-204, drive end). Decisions are shown only while a trusted checkpoint covers the ledger exactly." |
| 0:45 | Capture workspace: create `MTR-DEMO-1`, assemble with clean lots BR-310/BR-312; create `MTR-DEMO-2` with BR-204 | "Any capture moves the ledger past the checkpoint. The console now withholds every decision: 'Checkpoint required'." |
| 1:30 | Terminal: `curl -s -X POST -H "X-Pramaan-Token: <token>" -H "Content-Type: application/json" -d "{}" http://127.0.0.1:4173/api/units/MTR-DEMO-1/ship` (token from `/api/session`) | "Even a clean motor cannot be shipped through the API while the checkpoint is stale: 409 SHIPMENT_REFUSED, nothing written. That was the gap we closed." |
| 2:15 | Terminal: `checkpoint_ops propose`, then `accept` with the typed digest and per-motor acknowledgements (the rehearsal script's `cycle()` shows the exact arguments); restart the server with `--previous-anchor` | "A human operator reviews the proposed successor and accepts it. Same-host custody, operator asserted." |
| 3:00 | Console: DEMO-1 release eligible, DEMO-2 recall hold | "Eligibility is a read model computed from the evidence, never from a client claim." |
| 3:30 | `curl` ship `MTR-DEMO-2` with body `{"currentReleaseEligible":true,"force":true}` → 409; ship `MTR-DEMO-1` → 200 | "Recall-held: refused even with forged claims. Eligible and current: recorded. The shipment itself is a ledger write, so the next checkpoint cycle is required." |
| 4:15 | Record a sighting `ZZ-9` on `MTR-26003`, show stale + recovery workspace, one cycle, that motor stays held while others renew | "Unverified evidence is contained per motor, and only when nine proof obligations hold; anything uncertain widens the hold." |
| 4:50 | Close | State the limits above. |

## What not to do on stage
- Do **not** click "Record synthetic shipment" in the workbench: on refusal the app currently shows its generic error view (known, no UI redesign in scope). Show shipment through `curl`/the rehearsal script.
- Use `ZZ-9`-style sightings. A look-alike of the recalled lot (for example `BR-2O4`) deliberately blocks renewal for **all** motors (conservative global refusal).
- Do not describe anything as production-ready, independently certified or independently validated. Do not say "safe to ship"; say "release eligible under the current checkpoint".
- Do not run the hosted-CI or benchmark claims: no hosted CI run exists unless the report says so, and nothing has been independently scored.

## Offline fallback (no browser, or the server will not start)
1. `python -B docs/v1_1_release_candidate/demo_rehearsal.py` needs no browser and no pre-built UI; it starts the real server on port 4290 and prints PASS/FAIL per step. Walk the audience through its 10 lines of output.
2. If even that fails, show the recorded run in `docs/v1_1_release_candidate/rehearsal/` (transcript JSON from the exact SHA) and the screenshots in `docs/v1_1_release_candidate/rehearsal/*.png` if present.
3. If Python itself is unavailable, show `docs/v1_1_release_candidate/OWNER_REPORT.md` and the gate summary under `docs/v1_1_release_candidate/gates/`.
Never switch to a hand-edited database or a pre-seeded "already eligible" ledger without saying so: that would be a fixture, not a demonstration.
