# Operator rehearsal on the exact source SHA

Source: `c25466c56e5724158d534ff7b59f01ac48643101` (clean detached checkout, fresh `.venv`, `npm ci`, `npm run build`). Chrome (system, headless) driven by a script; **automated, not a human operator** (the Claude-in-Chrome extension was not connected, so it was not used). Loopback only, synthetic data. Raw log: `docs/demo-rehearsal/rehearsal-log.json`; screenshots alongside.

## Setup commands and times (Windows, Python 3.12, Node 24)
| Step | Command | Time |
|---|---|---|
| venv + dependencies | `python -m venv .venv` then `.venv\Scripts\python -m pip install -r experiments/foundation/requirements.txt` | 38 s |
| UI | `cd recall-ui; npm ci --ignore-scripts; npm run build` | 32 s |
| Seed synthetic ledger | `python -c "from application.service import Manufacturing as M;a=M('demo/ledger.sqlite');a.seed_demo();a.close()"` | 1.9 s |
| Root checkpoint (candidate; trust only once the owner holds it) | `python -m application.anchors export --database demo/ledger.sqlite --anchor demo/custody/checkpoint-001.json` | 0.9 s |
| Serve | `python app.py --database demo/ledger.sqlite --port 4173 --trusted-anchor demo/custody/checkpoint-001.json` | up in about 1 s |

## Results (all 12 steps passed; 15.8 s total for the scripted sequence, excluding setup)
| # | What was done | Visible result | Time |
|---|---|---|---|
| 1 | Start with checkpoint 001 | `ANCHORED_CURRENT`; only MTR-26003 eligible (others held/unresolved) | 1.0 s |
| 2a | Page 1 console | "Motor decisions"; 1 per-motor clearance chip, 4 recall-hold chips | 0.7 s |
| 2b | Page 2 passport MTR-26003 recall tab | "No recall hold recorded under this policy" | 0.5 s |
| 2c | Page 3 evidence investigation | 3 clusters; "Verified ledger journal sequence 10" | 0.5 s |
| 2d | Page 4 impact graph, lot BR-204 | "named by recall RC-026-014 for slot DE; 3 motors linked (1 affected, 2 unresolved)" | 0.8 s |
| 3 | Live capture through the UI workbench (late untrusted affected-lot observation on MTR-26003) | "Evidence captured. Backend capture-to-decision 477.8 ms" | 1.2 s |
| 4 | PREFIX_ONLY | Heading "Checkpoint required", bold **Do not ship or release any motor**; 0 decision chips and no Release/Hold/Excluded text; `GET /api/motors/MTR-26003/decisions` = 409; 0 eligible motors; passport shows "Current recall status unavailable"; impact page shows no release text | transition seen within 3.8 s step |
| 5a | Operator: stop server, `checkpoint_ops propose` | `CANDIDATE_PROPOSED_NOT_ACTIVATED`, 2 new journal entries (inert) | 1.5 s |
| 5b | Operator: `checkpoint_ops accept --custodian "Rehearsal Operator (local test custody)" --confirm-sha256 <typed digest>` | `LOCAL_CUSTODY_ACCEPTANCE_OPERATOR_ASSERTED_NOT_INDEPENDENT` | 0.6 s |
| 5c | Restart with `--trusted-anchor <accepted> --previous-anchor checkpoint-001` | `ANCHORED_CURRENT`; MTR-26003 now **Recall hold** (the capture withdrew its exclusion); 0 eligible motors | 1.6 s |
| 5d | Passport after activation | "Held under the recall policy" | 0.3 s |
| 6 | DE/NDE: separate ledger, recall scope unspecified (all compatible positions), motor with the recalled lot on the NDE bearing only | Affected / Recall hold (the reproduced NDE false-release defect does not occur) | 2.3 s |

Errors: no failed steps and no manual intervention. Browser console: 4 resource errors, all benign: 2 x `ERR_CONNECTION_REFUSED` (the open page polled while the operator stopped the server) and 2 x 404 for `/favicon.ico`.

## Not covered / caveats
* Scripted Chrome, one run, one machine; not a human or a judge-facing dry run with narration.
* The DE-scoped demo ledger does not show an NDE-only motor; that case is shown on the separate unspecified-scope ledger (the app allows one immutable recall scope per database).
* Checkpoint acceptance here is operator-asserted on the same host. Independent custody has not been demonstrated.
