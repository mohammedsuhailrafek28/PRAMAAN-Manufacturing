# F5 — Portable, selectively disclosed recall-evidence packages: Stage 1 design and feasibility

Branch `feature/hackathon-portable-evidence`, cut from `manufacturing-demo-v1.1` (`cf180a016f36b11a7fb5d552b3ae645c38c76326`). **Design only: nothing is implemented, no architecture is selected; the proposal below awaits owner choice.** Synthetic, loopback, hackathon scope. Same-host custody; no independently verified physical bearing identity; not production-ready.

## 0. Verdict in one paragraph
Feasible by Monday in a **narrow** form: a recipient-scoped package built on the **SD-JWT salted-digest pattern (IETF RFC 9901)** with an Ed25519 issuer signature, bound to the existing FORMAT_V3 checkpoint, plus a stand-alone offline verifier (Python CLI and a single-file browser page). It needs **no change** to the evaluator, `service.py`, `server.py`, `anchors.py`, registry binding, H1/H2 or the checkpoint format. The honest limit: a recipient can verify *who asserted what, that it was not altered, and that it is tied to a specific checkpoint*; a recipient cannot verify that it is current, not revoked, or physically true. Estimated 1–1.5 working days for the core, +0.5 day for the browser verifier. Main P1 risk: Ed25519 is not in the standard library or the hash-pinned CI lock.

## 1. User scenario
Aster Motors (the synthetic factory already in the demo) has recalled bearing lot BR-204 (DE slot). Three parties need different slices of the same fact and must not see each other's:
- **Pump customer** (motor `MTR-DEMO-2` was delivered to them): needs motor serial, "affected part present", the evaluator action (`RECALL_HOLD`), and the instruction "do not use / return". Must not see lot, supplier, timestamps, other motors.
- **Bearing supplier (Northstar, synthetic)**: needs lot, slot, and the supplier id it already knows. Must not see serials or customers.
- **Auditor / regulator (synthetic)**: needs everything the customer and supplier see **plus** the opened ledger event, so it can check the event against the factory's published checkpoint without the factory handing over its ledger.
Each receives one JSON/compact-token file and verifies it on an air-gapped laptop.

## 2. Technical architecture (proposed; not selected)
### 2.1 Redaction vs selective disclosure (the distinction the judges will probe)
- **Plain redaction** = delete or blank fields of a signed document. The signature then no longer verifies (or, if the issuer signs a redacted copy, the recipient trusts the issuer's *new* copy and nothing links it to the original). Easy, and not selective disclosure.
- **Selective disclosure** = the issuer signs *commitments* to every claim once (`digest = SHA-256(disclosure)`, disclosure = base64url(JSON `[salt, name, value]`), 128-bit random salt). A holder reveals any subset of the disclosures; the single issuer signature stays valid for every subset; undisclosed values stay hidden and cannot be brute-forced because of the salt; decoy digests hide the claim count. This is exactly RFC 9901 and is what we reuse. We do **not** invent cryptography.
- **Not offered (stated, not hidden):** unlinkability. All presentations from one issuance share the issuer signature; separate recipient packages are issued with fresh salts but are still linkable through `checkpointChecksum` and `packageSeries`. BBS-style unlinkable disclosure is out of scope (prior-art note §4).

### 2.2 Package (`PRAMAAN-EVIDENCE/1`, SD-JWT-compatible JWS, `alg: EdDSA`)
Signed payload (always visible): `iss` (issuer id), `kid`, `aud` (recipient id), `iat`, `exp` (default 24 h; demo 1 h), `jti`, `profile` (`customer|supplier|auditor`), `purpose: "RECALL_EVIDENCE_NOTICE"`, `_sd` (sorted digests incl. decoys), and a **binding block**: `checkpointChecksum` (the FORMAT_V3 `checksum` field, i.e. `digest(body)`), `checkpointFormat`, `registryDigest` (checkpoint `registryBinding.registryDigest`), `policyDigest` (checkpoint body `policyDigest`, already present), `engineTreeId`, `headHash`, `ledgerSequence` (checkpoint `sequence`), `state: "ANCHORED_CURRENT"` at issuance. All of these are copied from the checkpoint body that already exists; no checkpoint format change.
Selectively disclosable claims (enumerated closed set; unknown names are rejected by the verifier):
`motorSerial`, `part`, `lot`, `slot`, `supplierId`, `installEventId`, `installedAt`, `evaluatorAction` (enum `RECALL_HOLD | HOLD_FOR_INVESTIGATION | NO_AFFECTED_LOT_FOUND`, **never `RELEASE_ELIGIBLE`**), `evidenceFinding` (existing finding vocabulary), `instruction` (fixed text per action), and, auditor profile only, `eventRow` (the full ledger row for the install event, opened) plus `eventRowIndex`.
Hidden by construction: every other motor, lot, event, source, timestamp, supplier name, notification state, registry content, the ledger itself.

### 2.3 What the recipient can and cannot verify **offline, with no trusted third party**
| Check | Offline? | Trust needed |
|---|---|---|
| Ed25519 signature over header+payload under the issuer key | yes | the issuer public key, **pinned out of band** (demo: copied by hand; not an independent PKI) |
| Each disclosed claim hashes into `_sd`; unknown/duplicate/extra disclosures rejected | yes | none |
| `aud` equals this recipient; `iat ≤ now < exp` | yes | verifier's own clock (unsigned, can be wrong) |
| Package `checkpointChecksum` equals the given checkpoint file's `checksum`, and that file's checksum recomputes from its body | yes, **only if the checkpoint file is supplied**. **Measured on the v1.1 demo checkpoint: the file is NOT content-free** — `ledger.sourceHeads` is keyed `motor|source`, so it lists **every motor serial** and source id, and `ledger.rows` reveals per-table row counts plus one digest per row. Therefore it is given **only to the auditor profile**; customer and supplier recipients do not receive it and can check the binding only by comparing `checkpointChecksum` with a value the factory later publishes | none; the checkpoint itself is same-host custody |
| (auditor) the opened `eventRow` recomputes to the digest at `eventRowIndex` in the checkpoint's `ledger.rows.events`; its `native` JSON matches the disclosed lot/slot/event id | yes | none beyond the checkpoint |
| (auditor) `eventRowIndex` row belongs to a hash chain consistent with `sourceHeads` | partial (head only) | — |
**Cannot be verified offline, and the verifier prints this on every result:** that the checkpoint is the *latest* (freshness); that the package was not later **revoked or superseded** (revocation needs the issuer's status list, an online or out-of-band step; offline the best statement is "valid as of `iat`, currency unknown"); that custody was independent (it is same-host); H1/H2 replay and the evaluator's decision (both need the whole ledger — the customer/supplier profiles trust the issuer's assertion of the decision); physical bearing identity; issuer key authenticity beyond the pinned key.
Revocation design (limits explicit): short `exp`; monotone `packageSeries` + `seq`; optional issuer-signed `status.json` (list of revoked `jti` and the newest `seq`). If supplied and newer → verifier shows **SUPERSEDED/REVOKED**. If not supplied → "currency unknown". No central registry, no blockchain.

### 2.4 No new operational clearance
The verifier is a stand-alone, read-only tool: it never opens a ledger, never calls `announce/ship/snapshot`, and writes nothing. The schema has no field that can carry "release eligible", and the verifier UI states **"Informational evidence. Not a release clearance."** The issuer refuses to issue unless the live snapshot is `ANCHORED_CURRENT`, the motor is in the snapshot, and (for customer/supplier) the evaluator action is one of the three enumerated values. Importing a package into a ledger is explicitly **not** a feature.

## 3. Existing code reuse (unchanged files)
`application/anchors.py` (`export_anchor`, `TrustedAnchor`, `ledger_binding` row-digest definition — reused read-only), `integration/pramaan_integration/profile.py::digest` (RFC 8785 + SHA-256), `application/service.py::Manufacturing.snapshot(trusted_anchor=…)` for decisions, `application/lot_identity.py` registry resolution (so the lot claim is the canonical registered lot, look-alikes stay `HOLD_FOR_INVESTIGATION`), `registry_binding`/checkpoint `registryBinding` for `registryDigest`, `recall_announcements` row for `policyDigest`. Test scaffolding pattern: `application/test_ship_gate.py` (`world()` helper) and `research/*/mutation_check.py` (in-process mutants).

## 4. Novelty and prior-art risk (stated conservatively)
- **High overlap, do not claim novel cryptography:** IETF SD-JWT (RFC 9901, Nov 2025) is precisely the salted-digest mechanism; W3C Verifiable Credentials 2.0 + Data Integrity (incl. BBS and ECDSA-SD) cover selective disclosure and unlinkability better than we do; EU ESPR Digital Product Passport efforts and Catena-X (EDC connectors, contract-based traceability, SSI/VC) cover cross-party product data exchange; GS1 EPCIS 2.0/Digital Link cover the event vocabulary; in-toto/SLSA (DSSE) and IETF SCITT cover signed statements with transparency receipts; Certificate Transparency (RFC 6962/9162) covers inclusion proofs. I did one targeted search (SD-JWT status, Catena-X traceability); I did **not** perform a systematic patent or literature review.
- **Defensible novelty (modest):** binding a selective-disclosure package to a *recall-decision ledger checkpoint* whose decision semantics are one-way (holds only, never clearance), with an **auditor opening** that checks an event row against the factory's published checkpoint digests while customers/suppliers see only their slice, and a verifier that states the unverifiable limits on every result. Pitch it as an applied integration, not a new primitive.

## 5. Acceptance tests (Stage 2 will implement; all must be written before code claims pass)
1. Three profiles issued from one live staged ledger verify offline (Python CLI) and in the browser page.
2. Signature tamper (flip any payload byte) fails; swapped `aud` fails; unknown `kid` / wrong pinned key fails.
3. Disclosure tamper (alter value, salt or name; add an undisclosed or duplicate disclosure; drop `_sd` entry) fails; **plain redaction of a signed copy fails** (the demo's contrast).
4. Hidden claims are not derivable: customer package contains no lot/supplier/other-serial strings (substring scan of the whole file); decoy count constant across profiles.
5. Salt reuse across recipients is rejected at issuance (fresh CSPRNG salts; test fails if two packages share any disclosure string).
6. `exp` in the past → EXPIRED; `iat` in the future → rejected; status list newer than package → SUPERSEDED; no status list → "currency unknown" printed.
7. Checkpoint binding: wrong checkpoint file → mismatch; modified checkpoint body → checksum failure; auditor `eventRow` altered by one byte → digest mismatch; row index off by one → mismatch.
8. No-clearance: issuer refuses `RELEASE_ELIGIBLE`/`currentReleaseEligible` claims; verifier rejects any disclosed claim name outside the closed set; issuer refuses when snapshot is not `ANCHORED_CURRENT`, when the motor is unknown, and when the registry finding is not established (look-alike lot → only `HOLD_FOR_INVESTIGATION`).
9. Read-only proof: ledger file hash and checkpoint hash before/after issuing and verifying are identical (issuing reads only); verifier module imports nothing from `service`/`server`.
10. RFC 8032 test vectors pass for the vendored Ed25519; RFC 9901 example digest computations reproduce.
11. Mutation suite (in-process, same style as `research/v1_1_ship_gate`): signature check off, `aud` check off, digest check off, closed-set check off, expiry off, checkpoint-binding off, issuer-state check off, salt reuse allowed → each must be killed.
12. Existing gates A–K and all frozen counts unchanged except the new module counts.

## 6. Five-minute demo
0:00 State the limits (same-host, synthetic, informational only). 0:30 Staged ledger (existing demo): `MTR-DEMO-2` on the recalled lot, checkpoint current. 1:00 Issue three packages with one command; show that file sizes and contents differ. 1:30 Open `verify.html` from disk in an offline browser, drop the **customer** package: green "valid signature, issued by Aster (pinned key), audience OK, informational only", showing serial + `RECALL_HOLD` + instruction; hidden fields listed as "not disclosed". 2:15 **Supplier** package: lot + slot + supplier, no serial. 2:45 **Auditor** package with the checkpoint file: event row recomputes to the checkpoint digest. 3:30 Attacks, live: edit the lot in the customer file → red; strip a claim from the signed file by hand ("redaction") → red; present the supplier file to the customer slot → audience mismatch. 4:15 Currency: capture new evidence + operator cycle on the ledger, re-verify the old package → still cryptographically valid but shows "currency unknown / superseded" when the status list is added. 4:45 Close with the verifiable vs not-verifiable table.

## 7. Integration boundaries
Read-only against the ledger and checkpoint. New files only (no edits to `application/service.py`, `server.py`, `anchors.py`, `checkpoint_*`, `lot_*`, `registry_binding.py`, `recall-engine/`, `integration/`, `recall-ui/src`). No new server route (issuance is a CLI; a UI button is out of scope). No new event type, no evaluator change or re-pin, no FORMAT_V3 change, no H1/H2 change. The issuer key lives in a custody directory next to the ledger (**same host: a compromised host forges packages**; stated). Shared dependency with F6: the vendored Ed25519 module; the two branches should carry a byte-identical `application/ed25519_ref.py` so a later merge has no conflict.

## 8. Implementation proposal, file by file (Stage 2, awaiting approval)
| File | New/edit | Purpose | Est. |
|---|---|---|---|
| `application/ed25519_ref.py` | new | RFC 8032 reference Ed25519 (pure Python, public-domain reference algorithm; **not constant-time, demo only**) | ~120 LOC |
| `application/evidence_package.py` | new | issue / verify / profiles / closed claim set / checkpoint binding / status list / CLI (`keygen`, `issue`, `verify`) | ~350 LOC |
| `application/test_evidence_package.py` | new | acceptance tests 1–11 | ~350 LOC, ~25 tests |
| `research/portable_evidence/verify.html` | new | single-file offline verifier (WebCrypto Ed25519, SHA-256, no network) | ~250 LOC |
| `research/portable_evidence/mutation_check.py` | new | mutants of test 11 | ~100 LOC |
| `research/portable_evidence/demo_f5.py` | new | stage ledger, keygen, issue three packages, print commands | ~80 LOC |
| `docs/hackathon_features/F5_DEMO_RUNBOOK.md` | new | runbook + offline fallback | doc |
| `ci/run_gates.py`, `ci/frozen-source.json`, `docs/CI_INVENTORY_CHANGE_F5.md` | edit | add module count, re-freeze (from an LF clone) | small |
Schedule: day 1 crypto + issue/verify + tests; day 2 browser verifier, mutants, gates, rehearsal.

## 9. Risks
- **P0 (must not ship if unresolved):** (a) a package accepted after tamper (forged/unsigned) — covered by tests 2–3 + mutants; (b) a package readable as a **clearance** — closed schema, banner, issuer refusal; (c) hidden-claim leakage through weak commitments — random 128-bit salts, whole-file substring test; (d) vendored Ed25519 wrong — RFC 8032 vectors plus cross-check against Node's WebCrypto verifier.
- **P1:** pure-Python Ed25519 is unaudited and not constant-time (acceptable only because keys are demo keys; must be said); browser verifier depends on WebCrypto Ed25519 (supported in pinned Chrome 155 / Node 24; unknown for the judges' machine → Python CLI fallback); adding a second crypto implementation for the browser needs the digest/JWS code to be byte-compatible; staleness/revocation cannot be solved offline (message, not mechanism); the checkpoint file given to the auditor discloses **all motor serials, source ids, row counts and one digest per row** (measured); this is an auditor-scope disclosure that must be stated in the demo, and it means "customer/supplier" packages cannot be tied to the checkpoint by the recipient alone (they get issuer-asserted binding only). Whether to publish a **reduced checkpoint view** (checksum + body without `sourceHeads`) is not possible without changing the checkpoint format, which is out of scope; `exp`/clock is unsigned.
- **P2:** linkability across recipients; the `sourceHeads` consistency check is head-only.

## 10. Strict fallback (decide at the end of day 1)
If the browser verifier or Ed25519 cross-check is not green by Sunday evening: ship **Python-only** issue/verify with the same closed claim set and tests, drop the auditor `eventRow` opening to a documented "future work" **only if** tests 7–8 cannot pass, and demo from the terminal with the same attack sequence. If Ed25519 itself cannot be validated, **do not** substitute HMAC with a shared secret and call it signing; instead ship the digest-commitment layer unsigned and label every output "UNSIGNED: integrity vs. commitments only, no issuer authentication". If even that slips, ship this document and the acceptance tests only. F5 never blocks the protected v1.1 build; nothing here modifies it.

## 11. Remaining unknowns (to resolve in the first hours of Stage 2)
1. Exact byte layout of `ledger_binding` row digests for rows containing BLOBs (`captures`) vs the events table — verify with a recomputation test before relying on auditor opening.
2. Whether to carry the checkpoint file inside the auditor package (self-contained) or require it separately (smaller package, more steps). It leaks all serials, so it is auditor-only either way.
3. How many decoys and whether to pad all profiles to the same `_sd` length.
4. Which Python/Node/Chrome versions the judges' machine will have; whether `file://` pages may use WebCrypto (secure-context rules) in their browser.
5. Whether the owner wants a status list at all in the five minutes, or only the "currency unknown" message.
6. Naming/placement of the issuer key and the owner's stance on a vendored crypto reference in a repository that currently has no cryptography dependency.
