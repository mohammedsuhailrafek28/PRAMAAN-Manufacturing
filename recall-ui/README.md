# Recall Investigation UI

A standalone investigation UI over the Phase 1 recall engine (`../recall-engine`, semantics profile `UNTRUSTED_OBSERVATION_V3`).
All data is **synthetic fixtures**. Nothing here is real production data.

The UI never decides anything. `tools/export_snapshot.py` runs the real engine over the fixtures and writes
`public/data/snapshot.json`; the UI renders those decisions verbatim through a typed, replaceable adapter.

## Run

```
cd recall-ui
npm install
npm run snapshot        # re-run the engine and rewrite public/data/snapshot.json
npm run dev             # http://localhost:5173
npm run build && npm run preview
```

Requires Python 3 (engine, standard library only) and Node 20+. `npm run snapshot:check` fails if the committed snapshot is stale.

## Tests

| Command | What |
|---|---|
| `npm run typecheck` | TypeScript strict |
| `npm test` | Vitest + Testing Library component tests (22) over the real snapshot |
| `npm run test:e2e` | Playwright (system Chrome) browser tests + axe WCAG 2 A/AA in light and dark (19) |
| `python -m unittest recall-ui/tests/test_export_snapshot.py` (repo root) | Exporter: deterministic, verbatim engine output, no oracle files read (7) |
| `cd ../recall-engine && python -m unittest discover -s tests -t .` | Engine regression, v1/v2/v3 (127), untouched by this branch |

`SHOTS=1 npm run test:e2e` also refreshes `docs/screenshots/`.

## Demo workflow

1. **Motors** (`#/`): 24 synthetic motors with the engine's decision under the selected policy (P1 current installation, P2 operating history + damage inspection). Filter by finding, scenario family, or search.
2. Open **case-06** (wrong-slot scan). Three separate chips: *Evidence finding* (Unresolved), *Operational action* (Recall hold), *Review* (Review required). Each has a glyph and text, never color alone.
3. **Decision explanation**: reason codes in plain language, slot attribution and ambiguity (candidate slots, assurance level), per-slot capture gaps and conflicts, cited evidence events, untrusted observations, and decision provenance (engine version, semantics profile, coverage digest, watermark).
4. **Genealogy**: supplier lot → component install → motor → shipment. Removed or superseded records and the synthetic shipment overlay are dashed and labelled. A table alternative sits below.
5. **Decision history**: open **case-05**. Version 1 was release-eligible, version 2 supersedes it, with the notification obligation for anyone who was told version 1.
6. **Case 06 before / after** (`#/case06/case-06`): the original engine (`phase1-0.1`) against the current one, side by side across six variants, with a synthetic-truth safety label. Original: 2 false releases. Current: 0.
7. **Lot investigation** (`#/lot/BR-204`): every motor that ever held a lot, with its decision.

## Provenance and honesty rules

* Decisions, reasons, gaps, ambiguity, history and obligations are engine output copied verbatim.
* The validator refuses a snapshot whose decision contradicts the engine's invariants (release iff excluded; unresolved always needs review) and shows the problems instead of any data.
* A decision that cites events missing from the event log shows an *Incomplete evidence* warning.
* Shipments and suppliers come from `data/shipments.synthetic.json`, a labelled overlay the engine never sees.
* Synthetic ground truth is shown only for the case-06 safety comparison, P1 only. The expected-outcome oracle files are not read.

## Known limitations

* Shipments and suppliers are synthetic. The fixtures contain no shipment data.
* All fixtures reuse motor serial M-042, so a unit is identified by its case id.
* Decision versions are derived from event types (work-order close, verification, inspection, correction) recorded after the announcement, not from a real ingestion log.
  The late-arrival story of case-08 is therefore not reconstructable from events. Only case-05 and case-05b show withdrawals and notifications.
* Ground truth is synthetic and defined for P1 only.
* The snapshot is static. There is no live data, authentication, persistence, or write path (for example, recording that a notification was sent).
* Inherited engine limits apply (see `../recall-engine/README.md`): prototype 60 s label window, no physical-world identity beyond what records carry.

## Integration contract (for a future foundation)

The UI depends on exactly one seam, `src/data/RecallDataSource.ts`:

```ts
interface RecallDataSource { readonly label: string; load(signal?: AbortSignal): Promise<RecallSnapshot> }
```

To back the UI with another system, implement `load()` and return a `RecallSnapshot` (`src/domain/types.ts`), then change one line in `src/main.tsx`.
`validateSnapshot` runs on whatever you return.

* **Versioning:** `schemaVersion` (currently 1) gates the shape. Every decision carries `semanticsProfile`, `engineVersion` and `coverageDigest`, so a stored decision is replayable under its own profile.
* **Engine-provided (must be real output):** `decisions[unitId][policyId] = { current, history[] }` with `evidenceFinding`, `operationalAction`, `reviewRequired`, `reasonCodes`, `flags`, `slots`, `slotAttribution`, `untrustedObservations`, `supersedesDecisionId`, `triggerEventId`, `precautionaryHold`, `notificationObligation`, `evidenceEventIds`, `watermark`. History is oldest first and holds only versions where the outcome changed.
* **Record-derived:** `units[].events` (the event log), `components` (install and removal links), `lots`.
* **Overlay (replace with real systems):** `units[].shipment`, `lots[].supplier`.
* **Comparison (optional):** `comparison[]` pairs a legacy-profile decision with the current one, plus synthetic truth. A real backend can return `[]`; the page then says no comparison data is available.
* **Invariants the UI enforces:** release-eligible iff excluded with evidence; unresolved implies review required; every unit has a decision and a non-empty history for every listed policy.
* **Unknown codes** render with the fallback "No description available" rather than failing; add them to `src/domain/glossary.ts`.
