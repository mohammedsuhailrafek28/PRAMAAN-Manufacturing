# PRAMAAN frontend reconstruction: source inventory and workflow specification (Phase 0 + 1)

Branch `feature/ps10-claude-frontend-reconstruction`, from Copilot's final commit `0b2929f1a59181feeffcbe767e233985be11274e` (tracked tree clean; only untracked screenshots in its worktree). Backend: anchored `http://127.0.0.1:4411` (commit `9da1de30`), read-only through the existing same-origin GET proxy. Synthetic data only.

**Rule of authority:** Stitch controls appearance. The original `recall-ui` controls functionality. The anchored backend controls truth.

## 1. Source A: Stitch landing page

Export: `<USER_HOME>\Downloads\stitch_pramaan_manufacturing_intelligence_platform\stitch_pramaan_manufacturing_intelligence_platform\`

| Folder | Content | Role |
|---|---|---|
| `pramaan_landing_page_with_live_three.js_exploded_gearbox/` | `code.html` (84 KB, 7 sections, inline Tailwind config, Three.js r125 exploded-gearbox scene, `screen.png` 303x1600 downscaled full page) | **The approved landing page (only full landing page in the export; the folder name states it)** |
| `three.js_2/` | `code.html` (13 KB): standalone exploded-gearbox scene (`STITCH_THREEJS ANIMATION_24`) | The same scene as the landing's hero, as a standalone asset (landing carries its own copy marked "PRESERVED") |
| `three.js_1/` | `code.html` (8 KB): standalone motor-assembly scene (`ANIMATION_1`) | Also embedded in `unified_motor_workspace_mtr_26002` (dashboard design), not the landing |

Landing sections (ids): `hero`, `passport-section`, `genealogy-section`, `impact-analysis-section`, `lifecycle-section`, `audit-trail-section`, `cta-section`; scripts: Tailwind CDN (play, v3) with inline `tailwind.config`, `three.min.js` r125, one inline script `initExplodedGearbox()` (canvas `#gearbox-canvas`, container `#threejs-canvas-container`) plus the page's interaction script. Confidence that this is the approved version: high (single full landing page with a matching screenshot). If the owner meant a different candidate, name it; nothing else in the export is a landing page.

Port plan (Phase 2): reuse the file's own markup, inline Tailwind config and Three.js scene code; build Tailwind v3 (same major as the CDN) locally with the file as content; load `three@0.125.2` (same r125) from npm so there is no CDN dependency; Hanken Grotesk / JetBrains Mono via the same Google Fonts the file requests.

## 2. Source B: Stitch dashboard designs (visual system only)

`DESIGN.md` (Industrial Evidence Intelligence): surfaces `#f5faff` family, `primary #000`, `primary-container #141c24`, tertiary bronze `#ad7944`/`#2d1600`, error `#ba1a1a`; Hanken Grotesk (headline/body), JetBrains Mono (label-code), sharp 0-2 px radii, hairline borders, bracketed mono status tags (`[HOLD]`, `[REVW]`, `[EXCL]`).

Screens: `pramaan_overview` (graphite left rail with numbered nav, top bar, recall banner, 4 metric cards, filterable motor table with finding/action/review columns, expandable technical disclosure), `unified_motor_workspace_mtr_26002` (identity header, finding/action chips, tabs: Decision & Evidence Lens / 3D Digital Passport / Genealogy / History & Audit Log, 3D motor scene, reasoning panel with observations / claims / derived conclusions, evidence reference table), `recall_reveal_lot_br_204` (stepper of recall stages, node-and-edge genealogy graph, right inspection panel, summary metric tiles), `traceability_identity_reconciliation` (query + forward/backward trace table, discrepancy cards).

### Content in the mockups that MUST NOT be reproduced as data (not backed by the backend)
18 motors / 4 plants / PLANT_nn tags; block numbers `#492,108`, `#88204`; "HSM-99" Merkle root signature; "PRAMAAN-Deterministic-Eval v2.4.1"; ISO 9001 / IATF 16949 / ISO_10816 conformance and "18/18 passports attested"; carbon footprint, recycled steel %, warranty; telemetry (thermal 94.2 C, vibration, torque); technician/rework-ticket claims; "100% physical confirmation"; EU-DPP-compliant badge; forensic "fraud" cases, barcode collisions, speed-of-light clone detection (labelled "Future capability demonstration"); write actions ("Confirm operational recall hold", "Simulate operator upload", "Enforce quarantine hold", "Simulate resolution"); 99.8% determinism score; "Ambiguity 0.85" coefficient. Their *layout and styling* are used; their *numbers and claims* are not.

## 3. Source C: original Manufacturing PRAMAAN application (`recall-ui/`, 60 source files, same repo)

Reachable against the anchored backend 4411 today: `GET /api/snapshot`, `/api/motors`, `/api/motors/{id}/genealogy|decisions|lifecycle|provenance`, `/api/lots/{lot}/investigation`, `/api/trace/{bearingLot|rawMaterialLot|machineId|componentId}/{value}`, `/api/notifications`, `/api/session`.
NOT reachable: import/ingestion and mapping (CLI only: `python -m application.dataintegration`), `/api/deviations` (separate branch, not in `9da1de30`), any command route (writes are out of scope), server-side timing for GETs (responses carry no `Server-Timing`).

| Original module | What it does | Reuse |
|---|---|---|
| `src/contract/*` (`envelope`, `gate`, `gated`, `liveLoad`, `clearance`, `ClearanceChip`, `ConsoleClaims`) | Fail-closed gate: only a 200 + `ANCHORED_CURRENT` + fresh snapshot may show current decisions; PREFIX_ONLY -> historical facts only; 503 VERIFYING, 409 ANCHOR_INVALID, transport errors withheld; clearance chip wording | **Port as pure TS** (safety logic must not be re-invented) |
| `src/data/freshness.ts`, `RecallDataSource.ts` | Freshness / regression detection / lease; same-origin fetch | Port freshness; new GET-only source |
| `src/domain/{types,validate,derive,glossary}.ts` | `RecallSnapshot` schema validation, derived counts, human glossary of reason codes | **Port** |
| `views/FleetBoard`, `UnitDetail` (tabs decision/genealogy/history/events), `DecisionExplanation`, `DecisionHistory`, `EventLog`, `GenealogyGraph`, `LotInvestigation`, `Case06Comparison` | Fleet table, per-motor workspace, explanation of reasons, decision versions, event list, one-motor graph, lot investigation | Rebuild in Stitch style over ported domain code |
| `ManufacturingWorkbench`, `RecoveryWorkspace` | Capture / recovery **commands (writes)** | **Excluded** (no writes) |
| `src/impact/*` | Cross-motor recall impact graph: nodes (raw-material claim, bearing lot, manufacture record, installed component, motor, shipment, rejected observation), cited edges, issues (INFO/UNCERTAIN/CONFLICT), filter/trace/search, list equivalent | **Port projection + layout, rebuild view** |
| `src/investigation/*` | Evidence-guided investigation: evidence items by taxonomy of all engine reason codes, exact-key groups, priority order, verification limits | **Port taxonomy + projection** |
| `src/passport/*` | Per-motor passport: overview, components, evidence, timeline, recall context (gated), QR label, "not recorded" list | **Port projection + QR** |
| `docs/R18_LATENCY.md`, `ProvenanceBar` | Latency stance: 4 s UI timeout, safe 503 above ~100 motors; provenance bar shows source/policy | Performance panel (measured browser timings only) |

## 4. Workflow map (one investigation, one sequence)

`Overview -> select motor -> genealogy -> evidence -> recall impact -> passport`, with `Data & provenance` and `Performance & integrity` as supporting views. Selected motor persists in the URL (`?motor=MTR-26001`) across all views.

| # | Workflow | Original source | Data fields (backend) | Endpoint | Stitch component | Interaction | Loading / error / unknown / stale | Verification |
|---|---|---|---|---|---|---|---|---|
| 1 | Overview | `FleetBoard`, `ProvenanceBar`, `derive` | `units[].unitId/title/shipment/eventCount`; `decisions[m][policy].current.evidenceFinding/operationalAction/reasonCodes`; `recall`; `checkpoint`; `freshness`; `eligibility` | `/api/snapshot` | Overview rail, recall banner, metric cards, motor table | Filter by finding, row -> motor workspace | skeleton; gate states per `contract/gate`; PREFIX_ONLY shows historical facts only | counts equal snapshot; no derived clearance |
| 2 | Data & provenance | `ProvenanceBar`, provenance endpoint | per motor: `source`, `seq`, `capture hash`, `event chain hash`, `received`; `provenance.dataKind/adapter/engine`; `lotIdentity` | `/api/motors/{id}/provenance`, snapshot | Evidence reference table | Per-event hash view | Import outcomes / mapping / accepted-rejected counts are NOT live: shown as "Not available from this backend (CLI import layer)" | no invented counts |
| 3 | Motor investigation | `UnitDetail` + `DecisionExplanation` | `current.*` incl. `reasonCodes`, `flags`, `slotVerdicts`, `untrustedObservations`, `identityGuard`, `integrityGuard`, `evidenceEventIds` | `/api/motors/{id}/decisions` | Motor workspace with tabs, reasoning panel | Tab per view, reason -> evidence | 409 `CHECKPOINT_REQUIRED` => decisions withheld | reasons text from glossary |
| 4 | Genealogy | `GenealogyGraph`, `impact/projection` | `components[]`, `lineage[]` (rawMaterialLot, supplier, materialEventId, manufacturingEventId), `units[].shipment`, `lots[]` | snapshot, `/genealogy` | Recall-reveal graph (nodes/edges, right panel) | Node select -> evidence + provenance + lifecycle; pan/zoom; trace direction | Missing links shown as issues, never edges | every edge cites an event id; raw steel batch not labelled bearing lot |
| 5 | Recall impact | `LotInvestigation`, `impact/*`, `investigation/*` | `recall`, decisions of all motors, notifications | snapshot, `/lots/{lot}/investigation`, `/api/trace/...` | Stepper + graph + metric tiles | Filter by finding, lot trace, evidence groups | withheld when not current | numbers equal backend counts; hold != finding |
| 6 | Passport | `passport/*` | identity, components, lifecycle, material provenance, shipment claim, recall finding (gated), unknown fields | snapshot, `/lifecycle`, `/provenance` | Passport tabs in Stitch style | Tabs, QR route | unknown fields rendered "Not recorded" | no certification invented; shipment is a claim |
| 7 | Performance & integrity | `R18_LATENCY`, `freshness` | measured browser request duration per endpoint; checkpoint + freshness block; row counts | all GETs (timed in browser) | Metric tiles + sparkline | "Re-measure" (GET only) | Backend processing time: unavailable (no `Server-Timing` on GETs) | values are measurements taken in this browser session |

## 5. Constraints carried into every phase
No write requests (the proxy allows GET only; the UI has no command controls). No mock fallback (backend failure -> explicit unavailable). Never compute clearance in the browser: `currentReleaseEligible` is displayed from the snapshot, and only while `ANCHORED_CURRENT`. "Evidence-supported exclusion" is never "safe" and never shipment authorization. Synthetic label visible on dashboard. Backend 4411 and the Copilot preview 3001 are not touched.
