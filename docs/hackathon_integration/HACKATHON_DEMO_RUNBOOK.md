# Hackathon demo runbook — v1.1 + F5 portable evidence + F6 federated recall (combined candidate)

Branch `integration/hackathon-f5-f6`. Synthetic data, no network and no sockets in the F5/F6 parts, disposable temp state. **Read first:** all keys are generated locally on one machine; a valid signature is integrity under a pinned key, **not independent company authentication**. Same-host custody; scripted acknowledgements; not production-ready; physical product identity is not verified; H1/H2 independent validation is not claimed.

## Setup (once, before the event; no dev time assumed at the event)
```
python -m venv v
v/Scripts/python -m pip install --require-hashes -r ci/requirements-windows.lock -r ci/requirements-hackathon-crypto.lock
v/Scripts/python -B research/hackathon_integration/demo_combined.py WORKDIR     # WORKDIR new/empty, ~20 s; rehearse it twice
```
Saved transcript to fall back on: `docs/hackathon_integration/integration_evidence/demo_combined_transcript.txt`.

## Script (~5–6 min). The combined script prints a numbered banner per step.
0. **Open with v1.1 (30 s).** Say what the frozen product already does: an ANCHORED_CURRENT ledger, evaluator verdicts, recall holds, release eligibility. Then state the limits banner.
1. **Recall (banner 1).** Factory A recalls its drive-end bearing lot BR-204; existing checkpoint cycle; two motors held, the clean one untouched.
2. **Evidence and genealogy (banner 2).** For each held motor: evaluator finding, reason code, installed bearings with lots, supplier and raw-material lineage — straight from the frozen read model.
3. **Recipient-scoped package (banner 3, F5).** Customer / supplier / auditor packages for the same motor; the customer gets only four claims; offline verification with the issuer public key; show two negatives (wrong audience, wrong issuer key) and the issuer refusal for the clean motor. Say: "informational evidence, never a clearance".
4. **Supplier-triggered coordination (banners 4–7, F6).** Supplier S signs one alert for its own label `NSB-204`. Both factories authenticate it and map it through their OWN registries (A→BR-204, B→BR-771); nothing happens until a named operator types the confirmation; wrong confirmation refused; A already recalled the lot (idempotent, ledger unchanged); B adopts, answers **no counts while stale**, then after the real checkpoint cycle both answer counts only. Supplier board. Unmapped lot is refused, never "not affected".
5. **Close (banner 8).** Recap the safety design and the limits.

## What to say / not to say
Say: "synthetic", "local demo keys", "informational", "operator-adopted", "holds only". Do **not** say: production-ready, independently verified/attested, authenticated companies, certified, clearance, "proves the product is safe".

## Fallback ladder
1. Live combined demo.
2. Saved transcript + generated `board.html`-equivalent text in the transcript.
3. **Frozen v1.1 independently** (does not use anything from this branch): in a separate checkout of tag `manufacturing-demo-v1.1` (`cf180a0…`), follow its own `docs/v1_1_release_candidate/DEMO_RUNBOOK.md`; pre-stage with `python -B docs/v1_1_release_candidate/demo_prestage.py demo/ledger.sqlite demo/custody/root.json`. The v1.1 acceptance and rehearsal evidence under `docs/v1_1_release_candidate/` remains valid because the integration branch does not modify any v1.1 product file (0 modified in `docs/CI_INVENTORY_CHANGE_INTEGRATION.md`).
4. Tests and mutation results as proof if no live run is possible (`integration_evidence/`).

## Known demo limitations
* One adopted recall per factory ledger; strict alert chain (a lost alert blocks later ones at that factory; no resync).
* A look-alike lot already recorded in a factory's ledger makes the existing checkpoint accept refuse; that factory answers `PENDING_CHECKPOINT` without counts (safe, but silent).
* B's guard-only hold appears in F5 as `evidenceFinding=EXCLUDED_WITH_EVIDENCE` with `operationalAction=RECALL_HOLD`; explain it as "held by the identity guard".
* F5 supplier packages disclose the local lot; F6 responses deliberately do not. They are separate explicit channels.
