# FORMAT_V3: registry digest inside the checkpoint's verified boundary — compatibility and threat analysis

Branch `research/v1-1-format-v3-registry-binding`, from `research/v1-1-safety-hardening` @ `339649576c49158b38eb2496c98d6d88f8534ae3`. **Written before any FORMAT_V3 code**, as the owner required. Isolated research. No evaluator re-pin, no tag, no promotion. The frozen `manufacturing-demo-v1.0` tag and the existing candidate branches are untouched. `recall-engine/` and `application/audit.py` (`ENGINE_TREE`, `VERIFIER_VERSION`) are not modified.

## 1. What FORMAT_V2 is today (read from `application/anchors.py`)
A checkpoint is `{body, checksum}`, `checksum = digest(body)` (canonical JSON). V2 body fields: `format publicationProfile hardeningProfile archiveId sequence headHash legacyDigest policyDigest state verifierVersion engineTreeId ledger previousCheckpointHash`. `verify_anchor` checks the exact field set, the checksum, the chain link (`previousCheckpointHash == digest(previous)`, same archive, non-decreasing sequence, predecessor format/profile/engine tree, ledger-row extension), the journal prefix (via the V1 verifier on a derived body) and the H2 replay proof. `TrustedAnchor` pins the checkpoint bytes (and the predecessor's) for the life of the process and enforces monotone progress (`ROLLBACK_DETECTED`). State is `ANCHORED_CURRENT` only when the ledger equals the checkpoint's ledger binding and H2 verified.

The registry is **not** in this boundary. The v1.1 sidecar candidate (`<checkpoint>.registry-binding.json`) records it beside the checkpoint, outside `checksum`; the owner did not approve that as the final boundary.

## 2. FORMAT_V3 definition (proposed)
V3 = V2 plus one field, covered by `checksum` and therefore by `previousCheckpointHash` of every successor:

```
registryBinding: {
  format:          "PRAMAAN_REGISTRY_DIGEST_V1",
  registryDigest:  64 lowercase hex  (LotRegistry.digest of the registry document in force at export),
  registryId, version, entryCount, provenance  (descriptive; provenance must equal LOCALLY_AUTHORED_SYNTHETIC)
}
```
`body.format = "PRAMAAN_A31_ANCHOR_V3"`. Exact field set = V2 set + `registryBinding`. The registry document itself stays out of the body (it can be large and is not a ledger fact); the sidecar may carry it purely so a reviewer can see a field-level difference. The sidecar is **advisory only** under V3: it never creates, preserves or removes eligibility.

`verify_anchor` stays purely a ledger/archive verifier. It validates V3 structure and the chain rules below but does **not** compare the live registry (a registry discrepancy must not look like ledger corruption and withdraw every view with a generic code). The comparison is made by the application read model immediately after verification, against the digest that `verify_anchor` has just authenticated, and produces a precise hold (`REGISTRY_BINDING_DISCREPANCY`) while the checkpoint state remains truthfully `ANCHORED_CURRENT`.

## 3. Compatibility rules
| Case | Rule |
|---|---|
| V2 historical verification | **Unchanged.** V2 checkpoints verify exactly as today (ledger prefix, H2). Historical views and all non-eligibility fields still work. |
| V2 current eligibility | **Refused.** A V2 checkpoint cannot prove which registry was accepted, so every motor is held with `REGISTRY_BINDING_UNBOUND_LEGACY_FORMAT` even if a sidecar exists and matches. Not an integrity failure; the checkpoint state is reported unchanged. |
| V1 checkpoint | Same as V2 for eligibility (already never `ANCHORED_CURRENT`). |
| V2 to V3 migration | A V3 candidate may chain from a V2 predecessor (`previousCheckpointHash` = digest of the V2 checkpoint). Ledger-row extension and journal prefix rules are the same as V2-to-V2. Migration goes through `propose`/`accept`; review treats a V2 (or sidecar-only) prior as "registry never verified" and requires registry acknowledgement. |
| V3 to V2 (downgrade) | **Refused** as a chain link: a V3 predecessor requires a V3 successor (`PREFIX_MISMATCH`). |
| V3 to V3 | Normal chain; `registryBinding` may differ between links (that is a registry update, reviewed at accept). |
| Pinned evaluator | Not touched. `engineTreeId`/`verifierVersion` keep their values. Old verifiers reject V3 (unknown format/field set), which is fail closed. |
| Anchor CLI | `export` writes V3 by default; the programmatic `export_anchor(..., version=2)` remains for compatibility tests only. |
| Existing deployments | First start on this code holds every motor until a V3 checkpoint is accepted. Intended and visible; a migration cost. |

## 4. Threat analysis
Custody statement used throughout: V3 raises the registry to **the same trust level as the ledger prefix**: as strong as the custody of the accepted checkpoint file and nothing more. Independent custody has not been demonstrated; whoever controls the host controls the checkpoint, the database and the registry.

| Threat | V3 behaviour | Residual |
|---|---|---|
| Registry edited after acceptance | live digest != authenticated digest: all motors held, state stays `ANCHORED_CURRENT`, reason and field diff (when a valid sidecar is present) | none beyond custody |
| Registry rollback (older registry restored) | digest mismatch: held | none |
| Retroactive registration of an unknown legacy lot | held under the old checkpoint; after reviewed V3 accept the per-motor acknowledgement rule applies; identity-unsafe exclusions are still refused regardless | none |
| Alias redirect, supplier change, effective-date change | digest mismatch: held; diff names the change | none |
| Sidecar deleted | eligibility unaffected (digest decides); reviewer loses the diff, review says so and requires acknowledgement | reviewer sees less |
| Sidecar forged or corrupted | ignored for eligibility; flagged `sidecar INVALID`; its document is only used for diff if `LotRegistry(doc).digest` equals the authenticated digest | none for eligibility |
| Checkpoint body edited (binding digest changed) | `checksum` mismatch: `PREFIX_MISMATCH`, view withheld (existing behaviour) | none |
| Checkpoint body edited and checksum recomputed | pinned checkpoint bytes no longer equal (`TrustedAnchor`); successor links via `previousCheckpointHash` also break | an actor who replaces the trusted file *and* restarts the server defeats this, exactly as for the ledger prefix |
| Old V3 checkpoint substituted | ledger prefix rule: not `ANCHORED_CURRENT` (or `ROLLBACK_DETECTED` within a process); registry digest mismatch also holds | restart with a substituted reference is the documented H1 limit |
| V2 checkpoint substituted for a V3 one | held `UNBOUND_LEGACY_FORMAT` | none |
| Candidate downgrade V3 to V2 | chain refused | none |
| Registry-only update, no new ledger events | candidate V3 at the same sequence with a new `previousCheckpointHash` and new `registryBinding`; verifies; `accept` requires registry acknowledgement; motors whose findings vanish only because of the registry change require per-motor acknowledgement | none |
| Missing live registry / unreadable / provenance not declared | `LedgerBlocked` at start (existing fail closed) | none |
| A format change used to launder an identity-unsafe motor | the guard is computed from events and the live registry, never from checkpoint format; `accept` refuses identity-unsafe exclusions regardless of format or acknowledgement; tests below | none known |
| Operator mints a V3 checkpoint outside the reviewed `propose`/`accept` flow (CLI `export`) | already possible for V2; the server only trusts the file the operator pins | custody, not format |
| Confusing "registry digest present" with "registry is truthful" | the registry is locally authored synthetic data; digest binding proves *which* registry, not that it is correct or that any bearing has that identity | stated in UI and docs |

## 5. H1/H2 invariants to preserve (each gets a test)
1. V2 checkpoint verification result and `ANCHORED_*` state are byte-for-byte unchanged by this branch.
2. `verify_anchor` raises `IntegrityFailure` for any structural fault in V3 and never returns a state for one.
3. Pinned bytes, predecessor pinning, monotone `high` mark and `ROLLBACK_DETECTED` are unchanged.
4. `ANCHORED_CURRENT` is reached only when ledger equals the binding and H2 verified; registry never influences it.
5. Eligibility requires `ANCHORED_CURRENT`, no pending obligations, evaluator `RELEASE_ELIGIBLE`, **and** registry binding OK, **and** no identity or integrity finding.
6. A format change never makes an identity-unsafe motor eligible (tested with V2 to V3 migration, V3 renewal, and forged V3).

## 6. Explicit non-claims
Same-host custody is not independent verification. Acknowledgements are operator assertions. Registry membership is not proof of physical identity. This analysis does not certify H1/H2 and does not select or freeze an architecture.
