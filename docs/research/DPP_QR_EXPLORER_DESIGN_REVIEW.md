# Digital Product Passport + QR Explorer — repository audit and design review

Branch `research/dpp-qr-explorer`, from the exact reference `integration/phase31-a31-hardening@f9282101159b6b6806974848d7c351999098d792`.
Research only. No application code, no change to Codex's CI or H1/H2 work, `main`, the v3 evaluator, the foundation or
integration ledger, the audit journal, anchors, freshness, obligations or mutation endpoints, and no MSME PRAMAAN.
Nothing here is architecturally frozen. The author is the same agent that audited A31, so this needs owner review.

Evidence base: the code at the SHA above, plus a read-only run of the seeded demo (`Manufacturing.seed_demo()` +
`snapshot()`) in a disposable clone. External claims (DPP regulation, GS1, browser APIs) come from web searches that
returned mostly vendor explainers; they are marked where they matter and must be checked against primary texts.
**I have not seen the PS10 problem statement**; Section 15 asks for it.

## 1. Existing capabilities matrix

| Capability | Status | Where (exact) | Notes |
|---|---|---|---|
| Motor registration and identity | **PARTIAL** | `application/service.py` `Manufacturing.create_unit` (serial `MTR-[A-Z0-9-]{3,30}`, free-text `title`, default `"IE3 11 kW electric motor"`), table `app_units` | Identity is a serial plus a title string. There is no structured product configuration, no GTIN/GS1 key, no manufacturer entity. "11 kW" exists only inside the default title text. |
| Raw-material allocation | **EXISTS** | `Manufacturing.manufacture` → `MATERIAL_ALLOCATED` (rawMaterialLot, supplierId, supplierName), role `MATERIAL` | Supplier names are synthetic claims; every record carries `provenanceAssurance: "SYNTHETIC_UNVERIFIED_CLAIM"` (`Manufacturing.snapshot`). |
| Bearing manufacturing record | **EXISTS** | `BEARING_MANUFACTURED` (part, lot, optional serial, materialEventId) | Links allocation to manufacture. |
| DE/NDE installation and replacement | **EXISTS** | `Manufacturing.assemble`, `Manufacturing.replace`; `COMPONENT_INSTALLED` / `COMPONENT_REMOVED`; snapshot `components[]` (`removedAt`, `removalEventId`, `supersededBy`, `claimedBy`) | The seeded `MTR-26004` shows a removed DE bearing (`BR-204`, `…-DE-01`) and its replacement (`BR-312`, `…-DE-R9`). |
| EPCIS-compatible event capture | **EXISTS** | `Manufacturing.event` → `encode_document` → `Ledger.capture` | Documents were schema-validated against the pinned GS1 schema in the verification gates. This is "EPCIS-compatible", not certification. |
| Supplier/manufacturer claims | **PARTIAL** | `snapshot().lineage[]` (rawMaterialLot, supplierName, material and manufacturing event ids), `lots[]` | Supplier only. No manufacturer identity or facility. Actor ids (`OP-ASSEMBLY-07`, …) are roles, not people or certified identities. |
| Genealogy navigation | **EXISTS** | `recall-ui/src/views/GenealogyGraph.tsx`, `domain/derive.ts` `genealogyFor`, route `#/unit/<id>/genealogy` | Supplier lot → component → motor → shipment graph. A second genealogy tab would duplicate it. |
| Shipment evidence | **EXISTS, sensitive** | `Manufacturing.ship` → `MOTOR_SHIPPED`; snapshot `units[].shipment` includes `customer`, `destination`, `evidenceEventId` | Customer and destination are present for every motor in an unauthenticated `GET /api/snapshot`. |
| Capture hashes and chain references | **EXISTS** | snapshot `units[].events[].repository` = `{captureSha256, eventChainHash, localReceivedAt, recordTime}` (built in `Manufacturing.snapshot`); `GET /api/motors/<id>/provenance` (`application/server.py`) | Three clocks per event: `occurredAt`, `recordedAt`, repository `recordTime`, plus `localReceivedAt`. All `timeSource` values are `SYNTHETIC_SIMULATED`. |
| Recall findings | **EXISTS** | `snapshot().decisions[unit][policyId].current`; `views/DecisionExplanation.tsx`, `components/StatusChips.tsx` | Computed by the pinned v3 evaluator through `Audit.decide`. |
| Decision history | **EXISTS** | `decisions[...].history`; `views/DecisionHistory.tsx` | Includes supersession. |
| Existing provenance views | **PARTIAL** | `views/EventLog.tsx` (per event raw JSON in a `<details>`), `components/ProvenanceBar.tsx` | The event log shows hashes only inside raw JSON. There is no claim-to-evidence trail. |
| Motor-specific API routes | **EXISTS, constrained** | `application/server.py`: `/api/motors/<id>/genealogy`, `/decisions`, `/provenance` | Each route rebuilds the full snapshot. With no anchor they return 409; with an anchor they verify first. |
| Mobile navigation | **PARTIAL** | `styles.css` responsive tables (`table.grid.responsive`, `data-label`), hash-routed tabs in `views/UnitDetail.tsx` | Long identifiers wrap; no QR or scan entry point. |
| Frontend architecture | **EXISTS** | `App.tsx` (`parseRoute`, lease and freshness logic), `data/RecallDataSource.ts`, `data/freshness.ts` `verifyFreshness`, `domain/types.ts` `RecallSnapshot`, `domain/validate.ts` | Safety logic (lease, regression checks, eligibility hiding) lives in `App.tsx` and `freshness.ts`, which are Codex's area. |
| Inspections | **NOT AVAILABLE in the live ledger** | `ROLES["QA"]` allows `INSPECTION_RECORDED`, but no code path captures one; the seeded live units have none. The static fixture snapshot (`recall-ui/public/data/snapshot.json`) contains two. | A passport must show "no inspection recorded", not imply one. |
| QR generation or scanning | **MISSING** | no QR library in `recall-ui/package.json` | Both need a decision (Section 4). |
| Product specification, certifications, supplier verification, test results | **NOT AVAILABLE / NOT APPROPRIATE to invent** | none in the data model | The passport must say these are not recorded. |

Real seeded data for scale (read-only run): five units with 9, 15, 9, 15 and 10 events; five lineage chains; one replaced DE
bearing on two units (`MTR-26002`, `MTR-26004`); current findings `AFFECTED`, `UNRESOLVED`, `EXCLUDED_WITH_EVIDENCE`,
`UNRESOLVED`, `UNRESOLVED`.

## 2. Confirmed feature gaps

1. **No unit-centric identity-and-evidence page.** Information is spread across four tabs organised around the recall decision, not around "what is this product".
2. **No claim-level provenance.** The UI does not connect "bearing lot BR-312 is installed in DE" to the installing event, its capture hash, its source and actor claim, and what is unverified about it.
3. **No current-versus-historical component view as a first-class concept.** The graph styles removed components, but nothing states "as built" versus "as maintained" per slot.
4. **No explicit "not recorded" inventory.** Absent inspection, specification, certification and verified supplier data is never stated.
5. **No data carrier.** No QR, no stable shareable reference, no offline-verifiable artefact.
6. **No redaction boundary.** A passport for an external reader would have to drop `customer`, `destination` and operator ids, but the only API returns all of them to any caller (the server is unauthenticated GET on loopback).
7. **No separation of an immutable as-built record from live recall status.** This is the central design problem (Section 5).

## 3. Three passport designs (no selection)

| | **A. Evidence-backed passport viewer** | **B. Interactive QR passport explorer** | **C. Portable verification package** |
|---|---|---|---|
| What exists | All data and `genealogyFor`, `EventLog`, `DecisionChips`, `fmtTime`, `humanize` | Same, plus the hash route pattern | Hashes in `events[].repository`; checkpoint format in `application/anchors.py` |
| Newly built | One read-only view assembling identity, current and historical components, chronology, "not recorded" list and recall status | A: plus component drill-down, per-claim evidence trail (claim → event → capture hash → source claim → trust note), timeline, mobile-first layout, QR display and print | A canonical passport document, an offline verifier page or CLI, redaction profile, receipt format, hash binding to a journal head, optionally a signature |
| Unique user value | One page that answers "what is this motor and how do we know" | The user can follow any claim to its evidence and see exactly what is unverified | A passport that travels without the server and can be checked for tampering |
| Demo value | Moderate | High, if the QR hand-off works on a phone | High but hard to show convincingly without keys |
| Difficulty | Low | Medium | High |
| Backend-safety dependency | None if built client-side over `RecallSnapshot` | Same; recall panel depends on the future H1/H2 states | Strong: depends on the checkpoint design and key custody |
| Novelty versus traceability tools | Low | Moderate (claim-level provenance, honest uncertainty) | Moderate to high only if signing and custody are real; otherwise integrity-only |
| Security and privacy risk | Medium (shows shipment data if copied) | Medium (QR makes a route shareable) | Highest (an artefact leaves the host; stale and unrevocable) |
| Estimate | 2–3 days | 5–7 days | 8–12 days plus a key-custody decision |

Estimates assume one developer, the existing React/Vitest/Playwright toolchain, no new backend, a QR library approved, and
that Codex's `App.tsx` and `freshness.ts` are stable; they exclude review cycles and any change to those files that Codex lands.

## 4. Three QR architectures

| | **A. Stable route** | **B. Opaque reference resolved by backend** | **C. Hash-bound or signed receipt** |
|---|---|---|---|
| Payload | `https://<host>/#/passport/MTR-26004` | `https://<host>/p/<opaque>` | `{ref, digest, archiveId, sequence, headHash[, signature]}` |
| Feasibility | Trivial. Routing already exists as `#/unit/<id>` hash routes (`parseRoute` in `App.tsx`); the fragment is not sent to the server | Needs a new read route and a reference mapping, so `server.py` changes | Needs canonicalisation (RFC 8785 already a dependency), a verifier, and for authenticity a key |
| Phone access | **Only if the phone can reach the host.** The server binds `127.0.0.1` (`LocalServer(("127.0.0.1", port))`), so a phone reaches itself, not the laptop | Same | The *receipt* verifies offline; the *passport content* must also travel with it |
| Offline | No | No | Partly: integrity of a carried package, not live status |
| Privacy | Serial is guessable (`MTR-26001…`); identifier carries no data | Opacity adds little unless access control exists; with a derivable reference it is still enumerable | Minimal in the code; the package itself must be redacted |
| Revocation and expiry | Inherent (live page) | Inherent (server can disable a reference) | **Not revocable offline**; only expiry plus an online status check |
| Authentication | None. Unauthenticated loopback GET | None, unless a login is added | A hash does **not** authenticate its issuer. Authenticity needs a signature and an independently distributed public key |
| Tamper resistance | None for the code itself | Same | Strong for content integrity if the digest is trusted |
| Replay/staleness | Live lookup, bounded by C3 freshness | Same | A receipt is a snapshot in time and will go stale; it must never carry recall status |
| After a motor changes or a recall is announced | Page updates | Page updates | Receipt for the as-built record stays valid; recall status must be resolved live |

Critical distinctions:

- **A QR that opens a page** proves nothing; it is a pointer. Anyone can print a QR for any serial. It is also not anti-counterfeit: nothing binds the code to a physical motor.
- **A cryptographically verifiable portable passport** requires (i) a canonical document, (ii) a digest, (iii) an issuer signature, and (iv) a trust anchor the verifier already holds. A bare digest proves only that a file matches a number someone supplied. The repository has an RFC 8785 canonicaliser and a checkpoint format but **no signing keys and no identity**; the existing hardening docs explicitly say this is not invented.
- Even a correct receipt can only attest the passport at a journal head. If that head is past the last owner-custodied checkpoint (the H1 `ANCHORED_PREFIX_ONLY` situation), the receipt inherits that weakness.
- Industry practice (from vendor explainers, to be verified against primary texts): regulated DPP carriers resolve to a persistent product identifier, often a GS1 Digital Link, and the DPP regime describes tiered access control. The repository has no GTIN or GS1 key, so it can only claim an *EPCIS-compatible data model with a local identifier*, never DPP-standard conformance. Fabricating a GTIN is not acceptable.
- **Camera scanning.** The phone's native camera is enough to open a QR. In-browser scanning is separate work: `BarcodeDetector` is Chrome/Android-centred and absent or disabled on iOS Safari (caniuse), so iOS needs a JavaScript decoder; browsers generally treat `localhost` as a secure context but I did not confirm that for the camera API.
- **Demo reality.** Because the app is loopback-only and "no deployment" is a standing rule, a printed QR scanned by a judge's phone will not load a live passport unless the owner explicitly approves LAN exposure or a static public artefact. Section 15 asks.

## 5. Recommended provisional direction (not frozen)

**Two layers, never mixed:**

1. **As-built record** (identity, components current and historical, chronology, evidence trail, "not recorded"). It is derived from ledger events and stable once recorded. This is the only layer that could ever be portable.
2. **Live recall status** (current finding). It is resolved at view time, is shown only when the existing freshness and anchor checks pass (C3 now, H1/H2 later), is never embedded in a QR or exported record, and never calls anything "release". It uses wording like "No recall hold is currently recorded for this motor… not a shipment authorisation" only in the current verified state; otherwise "Current recall status unavailable".

**Provisional direction:** Option B built as a read-only client view over the existing snapshot, with QR architecture A for the MVP (QR renders the stable passport route), a hard separation of the two layers, and Option C kept as a later stage that is only pursued if the owner approves a key-custody model. Opaque references (QR B) add little without access control and are deferred.

## 6. Data contracts and reuse strategy

- **Source of truth:** the `RecallSnapshot` already fetched by `BackendRecallDataSource`, validated by `domain/validate.ts`. No direct DB reads, no new route required.
- **New pure module (illustrative):** `passport/buildPassport.ts: (snap: RecallSnapshot, unitId: string) => Passport`, where `Passport = { identity, components[], chronology[], claims[], notRecorded[], recallStatus }`. It only reshapes existing fields; it never evaluates.
- **Claim record:** `{ statement, eventId, eventType, sourceId, actorId, captureSha256, eventChainHash, recordedAt, timeSource, assurance: "SYNTHETIC_UNVERIFIED_CLAIM" | …, status: "CURRENT" | "SUPERSEDED" | "REMOVED" | "UNTRUSTED" }`.
- **Reuse:** `genealogyFor`, `fmtTime`, `humanize`, `DecisionChips`, `EventLog` summary logic, `ProvenanceBar` labelling. Do not reuse the SVG graph in the new view.
- **`recallStatus`** takes `decisions[unit][policy].current` unchanged, and is rendered only through the existing verified-lease path.
- **Not recorded list** is built from absence checks in the event set (no `INSPECTION_RECORDED`, no product specification fields, no manufacturer entity, `provenanceAssurance` all synthetic, all `timeSource` simulated).

## 7. Trust, privacy and freshness risks

1. **Unauthenticated read API.** `GET /api/snapshot` returns customer, destination, actor ids and raw events for all motors to any local process. A redaction profile in the UI is **not** a privacy control; it must not be described as one.
2. **QR makes a motor route shareable;** serials are guessable, so a QR gives no secrecy.
3. **Historic RELEASE_ELIGIBLE** must never render as clearance. The passport must show the hold-class finding or "unavailable", and only a verified-current eligible state as "no hold recorded".
4. **Stale or rolled-back data.** If the checkpoint chain is `ANCHORED_PREFIX_ONLY`, `UNANCHORED` or `ANCHOR_INVALID` (design from the H1/H2 spec), the recall panel is withheld and the as-built layer is labelled "not externally attested".
5. **Fixture fallback.** The existing "Fixture demo mode" link is user-initiated; the passport route must never be reachable as a silent fixture fallback in live mode.
6. **Synthetic provenance.** Every supplier, shipment and actor claim is a synthetic unverified claim; the passport must display that on every claim, not once in a footer.
7. **Counterfeit/cloned QR** is out of scope and must be stated.
8. **Time.** All clocks are simulated; the chronology order comes from recorded sequence and `occurredAt`, which is a claim, not a measured time.

## 8. Desktop and mobile UX structure

Journey: QR/route → identity header → overview → component genealogy → provenance evidence → chronology → recall context.

- **Identity header** (sticky on mobile): serial, title, "Synthetic demonstration data", ledger archive, snapshot time and a verification chip using the existing freshness states.
- **Overview cards:** Current components (DE, NDE) with lot, serial, supplier claim and status; "Recorded lifecycle" (assembled, shipped; reworked); "Not recorded" list; recall status card (or "unavailable").
- **Components:** per slot, current occupant first, then history ("removed by event … replaced by …"), each with a claim chip.
- **Evidence drawer:** from any claim, opens the event, capture hash, chain hash, source and actor claim, and the plain-language limitation. Reuses the data `EventLog` already shows.
- **Chronology:** a single ordered list (allocation → manufacture → install → close → ship → rework), with gaps and capture exceptions marked.
- **Recall context:** read-only link to the existing decision tab; the passport does not restate reasoning.
- **Data loading:** one snapshot load via the existing source; no extra requests; loading, empty (unknown serial), partial (no shipment, no assembly) and offline states each have a defined message.
- **Mobile/accessibility:** single column, evidence drawer as a full-screen sheet, 44 px targets, `overflow-wrap:anywhere` for URNs (already in `styles.css`), keyboard-reachable drawer with focus return, a text alternative for any diagram, axe in the existing Playwright setup.
- **QR display/print:** error correction M or higher, quiet zone, minimum printed size, label text showing the serial next to the code, and a statement that scanning needs access to the host.

## 9. Smallest useful MVP

A read-only `#/passport/<serial>` view: identity header, current and historical components per slot, ordered chronology, claim-level evidence trail with hashes, an explicit "not recorded" list, a gated recall-status card, and a QR (route payload only) with a print stylesheet. Pure builder + view + unit tests + a Playwright mobile and keyboard test over the live seeded data. **No backend change, no new dependency other than an approved QR encoder, no export.**

## 10. Adversarial counterexamples and acceptance criteria

| # | Counterexample | Acceptance criterion |
|---|---|---|
| 1 | Old `RELEASE_ELIGIBLE` shown as clearance after a hold | In any state other than verified-current, no "eligible" wording or green status anywhere on the passport |
| 2 | Replaced bearing shown as current | `MTR-26004` shows BR-312 as current DE and BR-204 `…-DE-01` as removed, with the removal event |
| 3 | Backend killed with the passport open | Recall card replaced by "unavailable"; no fixture data; as-built layer labelled "last loaded, not current" |
| 4 | Unknown serial in the QR | A clear not-found state, no data from other motors |
| 5 | Partially recorded motor | Missing blocks listed as "not recorded", no empty or zero values presented as facts |
| 6 | Untrusted observation (`MTR-26005`) | The claim chip says untrusted and unresolved, and the passport does not use it to describe the current occupant |
| 7 | Hash shown without limits | Every hash is accompanied by what it proves (capture integrity) and what it does not (issuer, physical truth) |
| 8 | Inspection implied | With no `INSPECTION_RECORDED`, the passport says none is recorded |
| 9 | QR payload leakage | The QR contains only the route and serial; test that it contains no customer, lot, event or hash |
| 10 | Customer and destination | Not rendered by default; not claimed to be protected |
| 11 | Cloned QR | Documentation states the QR does not bind to the physical motor |
| 12 | Receipt tamper (stage C only) | Altering one byte of the package fails verification; a receipt without a trusted key is labelled integrity-only |
| 13 | Long URN on 320 px width | No horizontal scroll; keyboard reachable; axe clean |
| 14 | Recall announced later | The as-built layer is unchanged; only the status card changes |
| 15 | Passport tries to compute eligibility | A test asserts the builder imports no evaluator and that recall status equals the snapshot's `current` unchanged |

## 11. Demo storyline

- **First 15 seconds:** a printed QR for `MTR-26004`; open it; the header says "synthetic, last verified N s ago".
- **First minute:** the DE bearing was replaced; the passport shows the current BR-312 and the removed BR-204 with the exact removal event, and an evidence drawer with the capture hash and "what this proves / does not prove".
- **Three minutes:** a recall is announced (existing workbench); the as-built record is unchanged but the status card turns to hold with the existing explanation; kill the backend and the status card withdraws rather than going stale; the "not recorded" list shows no inspection, no certification. Close on the two-layer idea and, if approved, a verified portable package.

## 12. Estimated implementation effort

Per Section 3: MVP (A+B-lite, QR route only) about 4–6 days including tests; full B about 5–7 days; C 8–12 days plus a key-custody decision. The estimates exclude conflict resolution with Codex's changes to `App.tsx`.

## 13. Changes that would conflict with Codex or violate the boundaries

| Proposed change | Boundary | Verdict |
|---|---|---|
| New route handling in `recall-ui/src/App.tsx` | Codex's C3/H1 area; the lease and freshness logic lives there | **Conflict risk.** Keep to the smallest possible diff (one route case) and rebase after Codex lands H1/H2 |
| Any edit to `data/freshness.ts` or `RecallDataSource.ts` | Operational freshness | **Violates.** Do not touch |
| New `GET` route in `application/server.py` | Codex's area (anchor enforcement) | **Avoid**; the client-side builder needs none |
| New fields in `Manufacturing.snapshot` (e.g. passport data) | Publication/freshness path | **Violates**; use existing fields only |
| `domain/types.ts` additions | Shared types | **Low risk**, additive only |
| `package.json`/lockfile for a QR encoder | Dependency policy | **Needs owner approval** |
| Mutating passport endpoint, release or shipment authorisation, resolution | Constraints | **Prohibited** |
| Signing keys or identity | Not in repository, not invented | **Prohibited** without owner design |

## 14. Residual risks

QR does not bind to the physical product; the app has no authentication, so redaction is cosmetic; all evidence is synthetic
and unverified; clocks are simulated; a phone cannot reach a loopback server; passport value for a real factory depends on
data that does not exist yet (inspections, specifications, manufacturer identity); novelty against commercial DPP products
is unverified.

## 15. Questions requiring owner approval

1. Provide the **PS10 text** so the requirements can be mapped; I have not seen it.
2. Is a QR whose page is reachable only from the host machine acceptable for the demo, or may LAN exposure or a static public synthetic artefact be approved (both contradict the loopback-only/no-deployment rules)?
3. May a QR encoder dependency be added (lockfile change)?
4. Should stage C (portable package) be in scope, and if so who owns a key-custody model? Without one it must be described as integrity-only.
5. Is a minimal edit to `App.tsx` acceptable after Codex's H1/H2 lands, and on which base should the branch be rebased?
6. Should the passport expose customer/destination at all in the demo, given no access control?
7. Which of Options A, B, C and which QR architecture to pursue; nothing is selected.

## 16. Assessment

**REVISE, then GO for a bounded MVP.** GO for the read-only passport view (Option B-lite, QR route payload, two-layer
model), because it reuses existing data with no backend change and has real differentiators: claim-level evidence trail,
explicit "not recorded", and recall status that withdraws instead of going stale. REVISE before freezing: the phone-access
and QR-dependency questions, the PS10 mapping, and the dependency on Codex's `App.tsx` changes. **NO-GO** for anything
described as a signed or portable passport until a key-custody model exists, and for any wording that implies release
authorisation or DPP-standard conformance.
