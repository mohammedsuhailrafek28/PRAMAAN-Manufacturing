# F6 — Cross-factory federated recall intelligence: Stage 1 design and feasibility

Branch `feature/hackathon-federated-recall`, cut from `manufacturing-demo-v1.1` (`cf180a016f36b11a7fb5d552b3ae645c38c76326`). **Design only: nothing is implemented, no architecture is selected; the proposal below awaits owner choice.** Synthetic, loopback, hackathon scope. **All "organizations" run on one machine with locally generated keys: that is NOT independent organization authentication.** Same-host custody; no independently verified physical bearing identity; not production-ready.

## 0. Verdict in one paragraph
Feasible by Monday only in a **reduced** form, and clearly larger and riskier than F5. The reduced core: a supplier plant issues a **signed, sequence-numbered recall alert** for a supplier-qualified lot; two motor factories (each with its own private ledger, registry and checkpoint) authenticate it, let an operator **adopt** it into their existing local recall policy, match against their own genealogy with the **unchanged evaluator**, and return a **scoped response** (counts per evaluator category, nothing about unrelated lots or units). A **correction** from the supplier propagates as an advisory that can never clear a hold. Estimated 2–2.5 working days; P1 risk is the per-factory checkpoint cycle needed before a response can be computed. Two existing constraints shape it (§2.6): the evaluator supports **one immutable recall scope per database**, and there is **no retraction** of a recall.

## 1. User scenario
Northstar Bearings (synthetic supplier plant "S") finds a defect in its lot `NSB-204` of part `BR-6205` (drive-end slot). S supplies two independent motor factories: **Aster Motors ("A")** and **Kaveri Drives ("B")**. Each factory keeps its ledger private. S broadcasts one signed alert. A and B each (1) verify it, (2) after an operator adopts it, find which of *their* motors contain the lot using their own registry (A calls the lot `BR-204` with alias `NSB-204`; B has a typo-prone label `BR-2O4` on a motor), (3) answer S with only counts by category. S sees a federated picture (A: 2 held, B: 1 held + 1 unresolved) without ever seeing a ledger. Later S narrows the scope; both factories see the correction, **keep their holds**, and show "supplier correction pending operator review".
(The three factories here are S, A, B. A downstream customer chain — A→pump maker — needs a new event type for "component = motor" and is out of scope.)

## 2. Technical architecture (proposed; not selected)
### 2.1 Topology options (recommendation marked)
| Option | Pros | Cons |
|---|---|---|
| **P2P loopback HTTP, one small sidecar per node (recommended)** | No central party, each node is visibly separate, easy to demo three terminals/browser tabs | Three more processes and ports |
| Shared mailbox directory | Trivial, offline-friendly, great as the **fallback** | Looks like a hub; no live feel |
| Central relay/hub | Easiest to build | Hub becomes a trusted party; contradicts "keep ledgers private / no central custody" story |

### 2.2 Nodes
Each of A and B is the **existing application unchanged** (`app.py` + UI for its own console) plus a **federation sidecar** `application/federation/node.py` that (a) accepts signed messages at `/fed/inbox`, (b) keeps a separate **federation store** (`federation.sqlite`: inbox, high-water marks, adoption records, outbox), (c) on **operator adoption** calls the existing `Manufacturing.announce(...)`, and (d) builds responses from the existing `snapshot(trusted_anchor=…)`. S has a key, a private list of lot dispatches (plain JSON, not the evaluator) and an aggregator view; it does not run the evaluator.

### 2.3 Message types (all JCS-canonical JSON, Ed25519-signed, one envelope `PRAMAAN-FED/1`)
- `ALERT`: `alertId`, `issuer`, `seq` (strictly increasing per issuer), `prevHash` (hash of the issuer's previous message → tamper-evident chain), `iat`, `exp`, `lot = {supplierId, part, supplierLot}` (**supplier-qualified identity**, not a factory label), `affectedSlots`, `severity`, `humanText`, `recipients` (optional list).
- `CORRECTION`: `supersedes: alertId`, `effect ∈ {NARROW, WITHDRAW, WIDEN}`, reason, own `seq`/`prevHash`.
- `RESPONSE`: `alertId`, `responder`, `status ∈ {PENDING_OPERATOR, PENDING_CHECKPOINT, ANSWERED, LOT_UNMAPPED}`, `asOfCheckpoint` (checkpoint checksum), `counts` per **evaluator category** (`RECALL_HOLD`, `HOLD_FOR_INVESTIGATION`, `NOT_AFFECTED_WITH_EVIDENCE`), `unresolvedFlag`, **no serials, no lots, no event data**.
- `ACK` of a correction (`seen`, `appliedLocally: false`).

### 2.4 Supplier-lot identity (reuses the registry; no bypass)
The alert carries `(supplierId, part, supplierLot)`. A node maps it to a **local canonical lot** through its existing `LotRegistry` (`entries[].supplierId`, `part`, `canonical`, `aliases`; `lot_identity.LotRegistry.resolve`). Outcomes: exactly one active registered match → eligible for adoption; **no match → `LOT_UNMAPPED`** (the node reports "cannot resolve", never "not affected"; the operator may extend the registry only through the existing registry-binding/checkpoint-acknowledgement flow); **look-alike of a registered lot** (e.g. `BR-2O4`) → remains an unresolved identity finding and holds the motor under the **unchanged** guard. Nothing in F6 edits the registry or the guard.

### 2.5 Local genealogy matching and scoped responses
1. Authenticate (§2.7), check `seq`/`prevHash`/`exp`, store in the federation inbox. Status `PENDING_OPERATOR`. **Nothing touches the ledger yet.**
2. Operator "adopts" (CLI or one button/one command): the sidecar calls `Manufacturing.announce(localLot, slots)` — a **hold-increasing** action already available today. This writes a `recall_announcements` row, so the ledger is newer than the checkpoint; the node is now `PENDING_CHECKPOINT`.
3. The operator performs the existing checkpoint cycle (`checkpoint_ops propose/accept`, FORMAT_V3, H1/H2 verification, acknowledgements). Only when the snapshot is `ANCHORED_CURRENT` does the sidecar compute `counts` from `snapshot()` decisions and send `RESPONSE`.
4. The response is **scoped**: categories and counts only; optional per-unit pseudonyms are **not** included in the minimal build (unknown #4). Unrelated lots and motors are never mentioned.

### 2.6 Corrections and the two existing constraints (honest)
- `service.announce` allows **one immutable recall scope per database**; policies cannot be edited or retracted (`recall_announcements` is trigger-immutable and part of the anchored tables). Therefore: **NARROW/WITHDRAW** corrections are recorded and shown as "supplier correction pending operator review"; they **never** lift a hold and never edit the policy (a human decision outside the system; the existing system has no retraction). **WIDEN** (a second lot or more slots) cannot be applied automatically: response status `UNSUPPORTED_SECOND_SCOPE`, operator must provision a new database (existing behaviour). We recommend **not** relaxing this in the feature branch: it would touch `service.py`, anchored tables and H1/H2 expectations.
- Correction safety rule (monotone): *imported information may add holds, never remove them; it may never create `currentReleaseEligible`.*

### 2.7 Trust assumptions (stated on screen in the demo)
Each node has a **pinned trust-root file** of peer public keys generated by a local `keygen` on the same machine. This proves message **integrity and consistency with a pinned key**, not that a real, independent organization sent it. Key compromise, key rotation and revocation are out of scope. The relay (if any) is untrusted for integrity but sees metadata. Replay/rollback: `seq` high-water marks and `prevHash` chain per issuer, `exp`, and `alertId` uniqueness. The **federation store is not covered by H1/H2 or checkpoints**; its integrity is weaker than the ledger's (a local attacker can edit it); effects on the ledger only occur through the existing, anchored paths. Clock skew is a stated limit.

## 3. Existing code reuse
`application/service.py` (`announce`, `snapshot`, existing event writers used only to build the staged factories), `application/lot_identity.py` + `lot_registry.synthetic.json` + `registry_binding.py` (supplier-lot mapping and registry digest), `application/anchors.py` / `checkpoint_ops.py` / `checkpoint_review.py` (acknowledged checkpoint cycle, unchanged), `application/server.py` and the React console for each factory's own UI (unchanged), `integration/pramaan_integration/profile.py::digest` (JCS + SHA-256). `application/test_ship_gate.py` patterns for tests and `research/*/mutation_check.py` for mutants. The shipment gate already ensures an imported alert cannot enable shipping.

## 4. Novelty and prior-art risk (conservative)
- **High overlap:** recall/traceability data spaces already exist or are in standardisation: Catena-X Traceability (Trace-X, EDC connectors, contract-based exchange where each party knows only its direct suppliers and customers), Gaia-X/IDS connectors, GS1 EPCIS 2.0/CBV and Digital Link, EU DPP (ESPR) pilots, EU Safety Gate/RAPEX and national recall portals, commercial supply-chain platforms, plus blockchain-consortium traceability pilots. Signed alerting itself is standard (CAP/OAuth-style signatures, SCITT-like transparency). One targeted search was run; no systematic prior-art or patent review was done.
- **Defensible, modest novelty:** *evaluation* stays local under a one-way safety lattice: federated messages can only add holds; supplier-qualified lot identity is resolved through each factory's own registry with look-alike safety; the response reveals only evaluator-category counts as of a verified, H1/H2-checked checkpoint; and corrections are monotone. Pitch as an applied safety discipline on top of existing federation concepts, not a new protocol.

## 5. Acceptance tests (Stage 2)
1. Authentic alert → accepted into inbox only; ledger and checkpoint hash unchanged until adoption.
2. Forged signature, unknown issuer key, altered body, expired alert, replayed `seq`, rolled-back `seq`, broken `prevHash` → each rejected with a distinct recorded reason; none touches the ledger.
3. Adoption on A: `announce` called once with the **canonical local lot**; ledger newer than checkpoint; status `PENDING_CHECKPOINT`; no response with counts is ever produced while stale.
4. After the existing checkpoint cycle, response counts equal the evaluator's own snapshot on A and on B (independently computed in the test from `snapshot()`), including B's look-alike motor counted as `HOLD_FOR_INVESTIGATION`, never `NOT_AFFECTED_WITH_EVIDENCE`.
5. Privacy: the full response/outbox contains no serial, lot, supplier-name or event string from either ledger (substring scan); A's response reveals nothing of B and vice versa; S's aggregate holds only counts.
6. `LOT_UNMAPPED`: alert for a supplier lot absent from the registry → status `LOT_UNMAPPED`, no announce, no "not affected" claim.
7. No-clearance: no message type can create or alter eligibility; with every message type fed in any order the set of held motors never shrinks (property test); `currentReleaseEligible` is false for every motor of the adopted lot at all times.
8. Corrections: NARROW/WITHDRAW recorded, ACK sent with `appliedLocally:false`, holds unchanged; WIDEN → `UNSUPPORTED_SECOND_SCOPE`; out-of-order/older corrections ignored.
9. Authentication boundary: tests assert the sidecar listens on 127.0.0.1 only and that every `/fed/*` write requires a verified signature (no unauthenticated path).
10. H1/H2, FORMAT_V3, registry binding behave exactly as before: all existing application test modules pass unchanged; the evaluator tree check (gate K) is unchanged.
11. Mutation suite: signature check off, `seq` check off, `prevHash` off, expiry off, adoption without operator, response while stale, lot mapping by label equality instead of registry, look-alike treated as no-match, correction clears hold → each killed.
12. Three-process end-to-end run (S, A, B) reproducible from a script with recorded transcript.

## 6. Five-minute demo
0:00 Limits slide: one machine, demo keys, not independent organizations. 0:30 Three tabs: A's console, B's console, S's federation board (all `ANCHORED_CURRENT`; A and B have private seeded ledgers). 1:00 S issues the signed alert for `NSB-204`; both factories show "Alert received, signature OK — PENDING OPERATOR; ledger untouched". 1:45 Attack on camera: a forged copy and a replayed alert are rejected with reasons. 2:15 Operators adopt (one command each): consoles go to "Checkpoint required" (existing behaviour); run the checkpoint cycle (scripted, shown briefly). 3:00 Consoles current: A: two motors on recall hold; B: one hold plus one **unresolved look-alike held**. 3:30 S's board shows only counts per factory and categories; point at "no serials, no lots, no ledger". 4:00 S sends a NARROW correction: both factories show "correction pending operator review — hold remains". 4:30 Close with the trust-assumption table.

## 7. Integration boundaries
New code only under `application/federation/` and `research/federated_recall/`; **no edits** to `service.py`, `server.py`, `anchors.py`, `checkpoint_*`, `lot_identity.py`, `registry_binding.py`, `recall-engine/`, `integration/`, or the UI source. The existing consoles are reused as-is (no new UI in the minimal build; the S board is a static page or terminal table). The sidecar uses only public `Manufacturing` methods (`announce`, `snapshot`). No new event type, no evaluator change or re-pin, no FORMAT_V3/H1H2 change, no change to the shipment gate. Shares a byte-identical `application/ed25519_ref.py` with F5 (so branches merge cleanly); this branch uses it for message signatures.

## 8. Implementation proposal, file by file (Stage 2, awaiting approval)
| File | New | Purpose | Est. |
|---|---|---|---|
| `application/ed25519_ref.py` | yes | RFC 8032 reference Ed25519 (demo-grade; same file as F5) | ~120 LOC |
| `application/federation/__init__.py` | yes | package marker | trivial |
| `application/federation/messages.py` | yes | envelope, canonicalisation, signing/verification, chain/seq checks | ~200 |
| `application/federation/trust.py` | yes | pinned trust roots, `keygen`, key id handling | ~80 |
| `application/federation/store.py` | yes | `federation.sqlite` (inbox, hwm, adoptions, outbox) | ~120 |
| `application/federation/lotmap.py` | yes | supplier-qualified lot → local canonical via `LotRegistry` | ~80 |
| `application/federation/node.py` | yes | loopback sidecar (`/fed/inbox`, `/fed/status`), adopt, respond, CLI | ~300 |
| `application/federation/aggregate.py` | yes | S-side counts-only board | ~100 |
| `application/test_federation.py` | yes | acceptance tests 1–10 | ~450, ~30 tests |
| `research/federated_recall/mutation_check.py`, `demo_f6.py` | yes | mutants; stage 3 ledgers + keys, run script | ~250 |
| `docs/hackathon_features/F6_DEMO_RUNBOOK.md`; `ci/run_gates.py`, `ci/frozen-source.json`, `docs/CI_INVENTORY_CHANGE_F6.md` | yes/edit | runbook, counts, re-freeze from an LF clone | small |
Schedule: day 1 messages/trust/store/lotmap + tests; day 2 node, adopt/respond against real ledgers + checkpoint cycle; day 3 morning mutants, gates, rehearsal. **Given the Monday afternoon deadline this is tight; see fallback.**

## 9. Risks
- **P0:** (a) an imported or forged message changes the ledger or any eligibility (mitigation: operator adoption gate, signature/seq checks, property test, mutants); (b) response or board leaks ledger content (privacy substring test, counts-only schema); (c) a look-alike or unmapped supplier lot reported as "not affected"/cleared (never produced; mapped by registry only); (d) a correction lifts a hold (monotone rule, test 7/8).
- **P1:** per-node checkpoint cycle latency and operator steps make the five-minute demo fragile (pre-script, rehearse, offline replay); one immutable recall scope per DB blocks WIDEN and multiple alerts (accepted limitation); vendored Ed25519 is unaudited and not constant-time; three processes plus ports (use a reserved port range, add to `ci/run_gates.py` PORTS); the federation store is outside H1/H2 so replay-state tampering is possible; effort estimate may be optimistic (2–2.5 days).
- **P2:** metadata leakage (who received what, when); clock skew; no key rotation.

## 10. Strict fallback
Decide at the end of day 2. **Level 1 (still federated):** S → A and S → B with signature, replay protection, adoption and counts-only responses; drop corrections (documented) and drop the live checkpoint cycle by pre-staging each factory's post-adoption, post-cycle state, **labelled as pre-staged**. **Level 2:** single-factory A only (alert → verify → adopt → local match → scoped response) with B simulated by a recorded transcript that is labelled as a recording. **Level 3:** ship this design and the acceptance tests only. Any level keeps the invariant that no imported information can clear or release anything. If authentication cannot be validated (RFC 8032 vectors fail) the build does **not** fall back to a shared-secret MAC presented as organisation authentication.

## 11. Remaining unknowns
1. Whether checkpoint-cycle latency for three nodes fits a live five minutes (needs a measured rehearsal early in Stage 2).
2. Whether to ever relax the single-recall-scope constraint (recommended no).
3. Whether S needs any evaluator/ledger of its own (recommended no; a dispatch list is enough).
4. Per-unit pseudonyms in responses for later dispute handling: omitted in the minimal build; the privacy trade-off needs an owner decision.
5. Whether the supplier-qualified identity should be exactly `(supplierId, part, supplierLot)` or include a `rawMaterialLot` (present in the registry) for stronger matching.
6. The owner's stance on a vendored crypto reference; whether F5 and F6 should share the identical module (recommended).
7. Port and process budget on the demo machine; whether Windows firewall prompts appear for three listeners (loopback only should not, to be confirmed).
