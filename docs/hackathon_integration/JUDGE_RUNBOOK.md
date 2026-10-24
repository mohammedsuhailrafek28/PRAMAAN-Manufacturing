# Judge-facing runbook — PRAMAAN Manufacturing, enhanced hackathon candidate

**Say first:** research prototype, synthetic data only. Keys are generated on one machine, so a valid signature shows integrity under a pinned key, **not** independent company authentication. Custody is same-host and operator-asserted; acknowledgements in the demo are scripted. Not production-ready. Physical bearing identity is not verified. Nothing here clears a motor for shipment.

**Transport honesty:** F6 is **file-based**. "Publishing" an alert means writing a signed file that the demo hands to each factory; there is no network, socket or live service between supplier and factories. Do not call it live communication.

## Before the event (once; no dev time assumed at the event)
```
git clone <repo> && cd PRAMAAN-Manufacturing && git checkout <final candidate SHA>
python -m venv v && v/Scripts/python -m pip install --require-hashes -r ci/requirements-windows.lock -r ci/requirements-hackathon-crypto.lock
v/Scripts/python -B research/hackathon_integration/demo_combined.py W1     # rehearse twice; each run needs a NEW empty directory
```
Open the saved transcripts (below) in a second window as the instant fallback.

## Timeline (~6 min narration; the script itself runs in ~20 s, so pause at each banner)
| t | Run / show | Say |
|---|---|---|
| 0:00 | Limits banner (printed first) | "Prototype, synthetic, local keys, same-host custody." |
| 0:30 | v1.1 base. Banners 1–2 of the combined demo: factory A recalls bearing lot BR-204; two motors held, one clean motor untouched; genealogy per motor (bearing serial, lot, supplier, raw-material lot) | "This is the frozen v1.1 evaluator output: AFFECTED means an affected lot is installed." |
| 1:30 | Banner 3 (F5): customer / supplier / auditor packages for one motor, each verified offline with only the issuer public key. Point at the customer package: four claims, 20 undisclosed digests | "Recipient-scoped, selective disclosure, informational only." |
| 2:30 | Negatives for F5: in the same banner (wrong audience, wrong issuer key, refusal to issue for the clean motor). Optionally run `demo_f5.py` for tampered disclosure, expired and ledger-contradicting claims | "Tamper, forge, wrong recipient: rejected. A clean motor gets no package." |
| 3:30 | Banners 4–5 (F6): supplier signs one alert for its label NSB-204; both factories map it through their OWN registries; wrong operator confirmation refused; adoption; no counts while stale; counts after the checkpoint cycle; supplier board | "Each factory decides; counts only; no serials or lots leave the factory." |
| 4:45 | F6 negatives: run `demo_f6.py` (forged key, edited text, attacker signature under the supplier key id, replay, expired) or show its saved transcript. Banner 7: unmapped lot refused, never "not affected" | "A zero or missing count is not a clearance." |
| 5:30 | Banner 8 recap | "F5 and F6 each state no-clearance on their own; neither can release a motor." |

## Fallbacks
1. Saved transcripts: `docs/hackathon_integration/clean_clone_acceptance/` (combined demo, F5 negatives, F6 attacks) and `integration_evidence/demo_combined_transcript.txt`. No screenshots exist; these transcripts are the visual fallback.
2. **Frozen v1.1, independent of this branch:** clone and check out tag `manufacturing-demo-v1.1` (`cf180a0`), then follow its `docs/v1_1_release_candidate/DEMO_RUNBOOK.md`; `python -B docs/v1_1_release_candidate/demo_rehearsal.py out.json` prints `REHEARSAL PASSED` (transcript: `frozen_v1_1_tag_rehearsal.txt`).
3. Tests and mutation results in `integration_evidence/` if no live run is possible.

## Do not say
Production-ready; independently verified/attested; authenticated companies; certified; "clearance"; "live network"; "proves the product is safe".

## Known limits to volunteer if asked
Strict alert chain without resync; one adopted recall per ledger; a look-alike lot in a ledger silences that factory's F6 answer (safe, silent); F5 supplier packages disclose the local lot while F6 responses do not; a motor held only by the identity guard shows `EXCLUDED_WITH_EVIDENCE` with `RECALL_HOLD` in F5; counts are factory-asserted.
