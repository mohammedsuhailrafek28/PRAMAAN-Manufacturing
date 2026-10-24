# F5 — Portable recipient-scoped evidence packages: implementation, evidence and limits

Branch `feature/hackathon-portable-evidence`. Synthetic data, loopback-free (no server, no network). Informational only. Independent of `manufacturing-demo-v1.1`, which is untouched.
Design: `F5_PORTABLE_EVIDENCE_DESIGN.md`. Raw evidence: `f5_evidence/`.

## 1. What it is

An issuer (the factory) turns the existing recall decision for **one held motor** into a signed package for a **named recipient** — customer, supplier or auditor — that the recipient can verify **offline, with no access to the ledger, server or network**, using only a pinned issuer public key.

* Issuing **reads** through the unchanged `Manufacturing.snapshot(trusted_anchor=…)` and the unchanged FORMAT_V3 checkpoint file and writes only the package file. Evaluator, ledger, checkpoint format and every existing source file are unmodified (`docs/CI_INVENTORY_CHANGE_F5.md`: 9 added, 0 modified; one expected-count line added to `ci/run_gates.py`).
* Decision values are the frozen ones, not remapped: `evidenceFinding ∈ {AFFECTED, UNRESOLVED, EXCLUDED_WITH_EVIDENCE}`, `operationalAction ∈ {RECALL_HOLD, RELEASE_ELIGIBLE}`. A test asserts the verifier constants equal the evaluator's own (`policy.py`, `engine.py`).
* **A package is never a clearance.** Issuance is refused for any motor whose action is not `RECALL_HOLD` (in particular `RELEASE_ELIGIBLE`), and the verifier rejects a signed package carrying any other action (`ACTION_NOT_ACCEPTABLE`) even if the real issuer key signed it. Verification outputs `clearance: NONE`. Nothing imported is loadable into a ledger; no HTTP route exposes issuance or import (tested).

## 2. Format: `PRAMAAN-EVIDENCE/1`, a labelled SUBSET of IETF RFC 9901 (SD-JWT)

| RFC 9901 feature | Status |
|---|---|
| Compact serialization `JWT~D1~…~Dn~` (trailing `~`) | implemented |
| `_sd` digests, `_sd_alg: sha-256`, digest over the Disclosure string exactly as received | implemented, checked against the 3 published RFC 9901 Disclosure/digest vectors |
| Object-property Disclosures `[salt, name, value]`, 128-bit random salts | implemented |
| Decoy digests (constant 24 digests per package, so claim count does not leak) | implemented |
| Rejections: duplicate digests, duplicate Disclosures, duplicate names, `_sd`/`...` as names, Disclosure not committed, plain-claim collision | implemented and tested |
| JWS `alg` EdDSA / Ed25519 (RFC 8037), pinned key + `kid` | implemented (library: `cryptography`) |
| Array-element Disclosures (`...`) and nested/recursive Disclosures | **not implemented** (rejected) |
| Key Binding JWT (holder possession proof) | **not implemented**. Recipient binding is the issuer-signed `aud` claim, which is **weaker**: it stops a package being *presented as* addressed to someone else when the verifier names the expected recipient, but anyone holding the file can show it. |
| Any `alg` other than EdDSA (`none`, HS*, ES*), `jwk/jku/x5c/crit` headers, JSON serialization, `_sd_alg` other than sha-256 | **not implemented** (rejected) |
| Issuer key discovery / metadata | **not implemented**: the verifier's operator pins the key out of band |

No Ed25519 is authored here. Signing and verification use `cryptography` 50.0.1 (cffi 2.1.1, pycparser 3.12), pinned with sha256 hashes in the **feature-isolated** `ci/requirements-f5-evidence.lock`. The frozen `ci/requirements-windows.lock` is untouched.

### Closed claim sets (verifier enforced; anything else is rejected)
* **customer**: `motorSerial, recallId, evidenceFinding, operationalAction`
* **supplier**: `recallId, part, lot, slot, supplierId, evidenceFinding, operationalAction` — only when the evaluator's own identity guard reports `IDENTITY_ESTABLISHED_LOCAL_REGISTRY` for an `AFFECTED` installation of an affected lot/slot; a look-alike (`BR-2O4`) or unresolved lot never yields a lot claim.
* **auditor**: the above plus `installEventId, decisionId, policyDigest, registryDigest, headHash, sequence`, and — only with the explicit `--authorize-event-row` flag — `eventRow` (the opened `events` row) and `eventRowIndex`.

## 3. Verification result (what each field means)

`python -B -m application.evidence_verify` prints and exits 0 only for cryptographic acceptance:

| Field | Values | Meaning |
|---|---|---|
| signature | `VALID_UNDER_PINNED_ISSUER_KEY` | Ed25519 over `header.payload` under the pinned key and `kid` |
| claim commitments | `VALID (n disclosed of 24 …)` | every Disclosure hashes to a signed `_sd` digest; closed set, no duplicates |
| intended recipient | `MATCHES` / `NOT_CHECKED` | only with `--recipient`; otherwise a warning, never a pass |
| validity window | `WITHIN_WINDOW_BY_VERIFIER_CLOCK` | iat/exp, ≤ 7 days, 60 s skew; the verifier's clock is not attested |
| checkpoint binding | `ISSUER_ASSERTED_ONLY` / `CHECKPOINT_DEMONSTRATED …` / `CLAIMS_BOUND_TO_CHECKPOINT_ROW …` | see below |
| freshness / revocation | `UNKNOWN_WITHOUT_EXTERNAL_EVIDENCE` | with a signed status list: `NOT_LISTED_AS_REVOKED_AS_OF_t` and "currency remains unconfirmed" |
| physical product truth | `UNVERIFIED` | always |

**Checkpoint binding is stratified honestly.** Customer and supplier hold no checkpoint (by design — measured in the design stage, the checkpoint lists every motor serial and per-table digests), so for them binding is **issuer-asserted only** and the verifier says so; complete independent checkpoint verification is *unavailable to them*. An auditor who is given the checkpoint gets the checksum re-computed (JCS-SHA256), the package's checksum/format/policy/head/sequence/registry digest cross-checked, and — if a row was authorised — the opened event row re-hashed to the checkpoint's row digest at that index, plus lot/slot/serial/event-id consistency with the row. Even then the checkpoint is **same-host custody, not independent verification**, and the claims are bound to *a* checkpoint, not to physical truth.

## 4. Offline verification (any machine with Python 3.12 + the F5 lock)

```
python -m venv v && v/Scripts/python -m pip install --require-hashes -r ci/requirements-f5-evidence.lock
# auditor row digests additionally need rfc8785 (already in ci/requirements-windows.lock)
v/Scripts/python -B -m application.evidence_verify customer.sdjwt --issuer-key issuer-ed25519.pub.json --recipient urn:demo:customer:pumpco
v/Scripts/python -B -m application.evidence_verify auditor.sdjwt  --issuer-key issuer-ed25519.pub.json --recipient urn:demo:auditor:regulator --checkpoint checkpoint.json
```
Exit 0 accepted, 2 rejected (`--json` for machine output). `evidence_verify.py` imports no ledger, service, server, anchor or evaluator code and no `sqlite3` (subprocess-tested). Issuing: `python -B -m application.evidence_package keygen|issue|status` (`--help`). The issuer key is created once and never overwritten.
Demo (3 recipients, 5 negative cases, 1 issuer refusal, privacy scan): `python -B research/portable_evidence/demo_f5.py` — transcript in `f5_evidence/demo_transcript.txt`.

## 5. Tests and evidence

* `application/test_evidence_package.py` — 36 tests (registered in `ci/run_gates.py` as `test_evidence_package=36`): RFC 8032 vectors 1–2; RFC 9901 vectors; frozen-schema equality; three profiles; payload tamper (aud, exp, iat, profile, jti, iss, `_sd` removal/addition); disclosure tamper (value, salt, renamed claim, duplicate, uncommitted, empty); wrong issuer key, attacker key under the victim `kid`, truncated/corrupted signatures; audience mismatch; expiry/not-yet-valid/overlong/non-integer; duplicate and unexpected claims, reserved names, plain-claim collision, extra payload field, weak salt; clearance values rejected even when signed by the real key; 32 hostile inputs (none raise); pinned-key validation; checkpoint tamper (modified body, self-consistent different checkpoint, altered row, shifted/out-of-range index, lot/slot/serial/policy/head/sequence mismatch, partial row); privacy substring scans (customer: no lot/supplier/other serials/checkpoint content; supplier: no motor or customer identity); constant digest count; no salt or digest reuse across issuances; issuance refusals (RELEASE_ELIGIBLE, unknown motor, stale checkpoint, look-alike/unresolved lot for supplier, row without authorization, key overwrite); ledger-binding and checkpoint bytes identical before/after issue and verify; no operational calls in the package code; status-list revocation; CLI exit codes.
* **Mutation** (`research/portable_evidence/mutation_check.py`): 17 in-process mutants (signature not verified, digest checks a prefix only, audience ignored, expiry ignored, clearance action accepted/issuable, customer set open, supplier sees motor serial, extra payload fields allowed, checkpoint binding skipped, checksum not recomputed, row digest not compared, revocation ignored, salts reused, digest count leaks claim count, stale checkpoint accepted, row opened without authorization, issuer writes the ledger). **All 17 killed, 0 survivors** (`f5_evidence/mutation.json`). Note: the ledger-writing mutant is killed at fixture setup (the write after the checkpoint makes issuance refuse as stale), i.e. by the checkpoint freshness guard, not by the dedicated read-only test.
* **Interoperability** (`research/portable_evidence/interop_check.py`): 17 packages (3 valid, 1 forged by the real key and valid, 13 tampered/forged) verified by three independent implementations — the reference (`cryptography`), a from-RFC Node verifier on OpenSSL (`verify_node.mjs`), and a PyNaCl/libsodium verifier (`verify_pynacl.py`) that shares no code. Verdicts and accepted claims agree on all 17 (`f5_evidence/interop.json`). Scope limit: the Node/PyNaCl verifiers cover signature, commitments, closed sets, action/finding, audience, expiry and binding state; **checkpoint-binding and status-list checks were not independently re-implemented**.
* **Existing regression gates** — full local A–K (`ci/run_gates.py`, pinned Windows/Python 3.12.10/Node/Chrome toolchain, clean LF clone of code SHA `28fdcfc7e7489092ce1ccd041030c4fa19baec37`): `status: PASSED` (K provenance incl. engine/foundation/integration trees unmodified; infra; A 127; B 21 checks; C 44; D all 16 modules incl. `test_evidence_package` 36; E/J standards; F 7; typecheck; G build; H Vitest 378; I Playwright 143) — `f5_evidence/gates_summary.json`, `gates_run.log`. This is a **local** run; no hosted-CI result is claimed (workflow does not trigger on this branch).
* **All mutation suites re-run on that SHA** (`f5_evidence/mutation_*.txt|json`): v1.1 hardening 8/8, lot identity 5/5, scoped containment 12/12, ship gate 4/4 killed (29 pre-existing mutants; the lot-identity suite file holds 5 mutants plus its unmutated baseline row, so an earlier "30" figure counted that baseline row), plus F5 17/17. 46 mutants, 0 survivors, every unmutated baseline clean.

## 6. Disclosure matrix (measured, `f5_evidence/unit_evidence.json`)

| | customer | supplier | auditor |
|---|---|---|---|
| bytes / committed digests | 2532 / 24 | 2702 / 24 | 6648 / 24 |
| disclosed claims | 4: motorSerial, recallId, evidenceFinding, operationalAction | 7: recallId, part, lot, slot, supplierId, evidenceFinding, operationalAction | 16: customer + supplier claims combined, plus installEventId, decisionId, policyDigest, registryDigest, headHash, sequence, eventRow, eventRowIndex |
| supplier / lot / other motors | none | lot, supplier | lot, supplier |
| motor serial / customer identity | own serial | **none** | serial |
| checkpoint content | none (checksum only) | none (checksum only) | row opened only if authorised; full checkpoint supplied separately for verification |
| checkpoint binding | issuer-asserted | issuer-asserted | claims bound to checkpoint row |

## 7. Limitations (stated, not hidden)

1. Informational. It proves the issuer signed these statements to this recipient within a window — **not** that the product is physically as described, that the ledger is true, or that nothing has changed since (freshness is unknown; revocation needs an external signed list).
2. Issuer key and checkpoint live on the same host as the ledger: **same-host custody is not independent verification**; H1/H2 independent validation is not claimed and there is no independent custody.
3. `aud` binding is weaker than holder key binding (no KB-JWT): a file can be forwarded; the verifier only checks the audience it is told to expect.
4. Linkability: packages from one recall/checkpoint share `recallId` and `checkpointChecksum`; recipients can correlate them. Package size reveals the profile, not the claim count.
5. The auditor package, when authorised, discloses the whole opened `events` row (including its native payload) — authorisation is a deliberate act and a full checkpoint is required to verify it.
6. Verifier clock is the verifier's own; `--now` exists for testing.
7. Not run in hosted CI: the workflow is not triggered on this branch and installs only the frozen lock, so `test_evidence_package` cannot pass there without installing the F5 lock. No hosted-CI result is claimed.
8. No browser verifier and no UI screenshots were produced (secondary requirement; WebCrypto verification was left out rather than shortcut). The terminal transcript is the demo artefact.
9. Revocation/status list is optional and proves nothing after its own `asOf`.
10. Library trust: Ed25519 is delegated to `cryptography` (OpenSSL) and cross-checked against OpenSSL-via-Node and libsodium; we did not audit those libraries.

## 8. Fallback

If the F5 lock cannot be installed on the demo machine: (a) show `f5_evidence/demo_transcript.txt` and the raw package files; (b) a package carrying a corpus-format wrapper can be checked by `verify_node.mjs` (Node, no dependencies; it reads the interop corpus JSON, not a bare package file, so this needs a few lines of glue and is not a ready-made fallback); (c) the signed package is still self-describing JSON/base64url a reviewer can inspect.
