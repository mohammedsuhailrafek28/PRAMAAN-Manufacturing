# Registry custody: checkpoint-bound registry snapshots (v1.1 candidate)

Status: **implemented as a candidate on `research/v1-1-safety-hardening`, not promoted.** No anchor or checkpoint format was changed. Same-host only: this is not independent custody and not independent verification.

## 1. Problem (owner priority 1)

In the A+B candidate the lot registry was a local file read at process start. Editing it changed read-side eligibility immediately and silently, including under a checkpoint that a person had already accepted: retroactively registering an unknown legacy lot, redirecting an alias, changing a supplier or moving an effective date could turn a held motor into an eligible one with no review.

## 2. Mechanism

A checkpoint is exported together with a **sidecar** `<checkpoint>.registry-binding.json` (module `application/registry_binding.py`). The checkpoint bytes are untouched, so `anchors.py` verification, the H1/H2 proofs and the pinned evaluator are unaffected.

The sidecar holds: `format`, `checkpointSha256` (of the exact checkpoint bytes), `registryDigest`, the full `registryDocument` in force at export, and a custody note. It is created exclusively (never overwritten), staged and fsynced like the checkpoint. `accept` carries the identical sidecar to the accepted checkpoint (same bytes, same binding).

At every snapshot the server compares the **live** registry with the binding of the checkpoint it was pinned to with:

| Status | Meaning | Effect |
|---|---|---|
| `OK` | sidecar present, belongs to these checkpoint bytes, matches its own digest and provenance, equals the live registry | none |
| `MISSING` | no sidecar (for example a checkpoint from before this feature) | every motor held |
| `INVALID` | unreadable, wrong format, belongs to other checkpoint bytes, digest or provenance mismatch | every motor held |
| `DISCREPANCY` | valid binding, live registry differs | every motor held; a field-level difference is reported |

"Held" means a global identity-guard finding (`REGISTRY_BINDING_MISSING|INVALID|DISCREPANCY`) on every motor decision. The evaluator's own output is not modified (`evaluatorOperationalAction` is kept) and the checkpoint state stays `ANCHORED_CURRENT`, so H1/H2 fail-closed behaviour is preserved and the reason for the hold is precise. The finding reaches the snapshot, `/api/snapshot` decisions, `lotIdentity.registryBinding`, the checkpoint review and the UI (provenance-bar alert) through the same function.

Until the binding is proven (`OK`), any discrepancy prevents current eligibility. A registry change cannot raise eligibility under an older checkpoint.

## 3. Valid update path

1. The operator edits the registry and restarts. Every motor is held (`DISCREPANCY`), the UI says so.
2. `checkpoint_ops propose` now proposes a candidate even when the ledger did not move, if the binding is not `OK`. The review adds `registryChange` (field-level diff against the registry accepted with the **current** checkpoint: `ENTRY_ADDED/REMOVED`, `FIELD_CHANGED`, `ALIAS_ADDED/REMOVED/REDIRECTED`, `DOCUMENT_FIELD_CHANGED`, `DUPLICATE_DECLARATION_CHANGED`).
3. For each motor, identity findings are recomputed under the prior bound registry. A motor whose findings **disappear only because of the registry change** (retroactive registration) is flagged `identityResolvedByRegistryChange` and needs the same per-motor acknowledgement as a newly release-eligible motor.
4. `accept` additionally requires `--acknowledge-registry-change <live registry digest>` whenever the registry differs from the previously bound one (or no prior binding exists), refuses if the candidate's own binding is not `OK`, refuses identity-unsafe exclusions regardless of acknowledgement (unchanged), and records the registry changes and the acknowledgement in the acceptance record.
5. After the operator restarts with the accepted checkpoint, binding is `OK` and eligibility follows the normal rules.

## 4. Adversarial results

Tests: `application/test_v11_hardening.py` (class `RegistryCustody`), evidence `results/v11_evidence.json`. In every case the checkpoint stayed `ANCHORED_CURRENT`, the evaluator still said `RELEASE_ELIGIBLE`, and the motor was **not eligible**, action `RECALL_HOLD`, reason `REGISTRY_BINDING_DISCREPANCY` with the expected change kind.

| Attack | Result |
|---|---|
| registry field edited after acceptance (supplier name) | held, `FIELD_CHANGED supplierName` |
| rolled back (entry removed; version decremented) | held, `ENTRY_REMOVED`; `DOCUMENT_FIELD_CHANGED version` |
| unknown legacy lot registered retroactively | the legacy motor **and the unrelated legitimate motor** both held under the old checkpoint; `ENTRY_ADDED` shown |
| alias redirected to another lot | held, `ALIAS_REDIRECTED` |
| supplier identity changed | held, `FIELD_CHANGED supplierId` (and `SUPPLIER_SCOPE_MISMATCH` for that lot) |
| effective date altered; lot withdrawn | held, `FIELD_CHANGED effectiveFrom|status` |
| sidecar deleted | `MISSING`, held |
| sidecar garbage / digest altered / bound to other checkpoint bytes / provenance forged | `INVALID`, held |
| old checkpoint replayed with the new registry | `DISCREPANCY`, held |
| new checkpoint replayed with the old registry | `DISCREPANCY`, held |
| valid update then review then accept without registry acknowledgement | refused, nothing accepted |
| ... with a wrong registry digest | refused |
| ... with registry acknowledgement but without the per-motor acknowledgement for the retroactively resolved motor | refused |
| ... fully acknowledged | accepted; binding carried to the accepted file; new checkpoint `OK`, both motors eligible; re-propose returns `NO_CANDIDATE_NEEDED` |
| checkpoint from before this feature (no sidecar) | held until a candidate is accepted with registry acknowledgement |

Sensitivity: 7 in-process mutants (binding ignored, missing binding tolerated, diff blind, no registry acknowledgement, integrity guard off, sightings ignored by the guard, replacement forced to DE) each fail at least one test (`results/mutation_check.json`).

## 5. What this does **not** give

- **Not independent custody.** The checkpoint, the sidecar and the registry are files on one host. Whoever controls the host can rewrite all three (a new self-consistent checkpoint plus sidecar chained from the previous one is a normal accepted-checkpoint operation by definition). The binding detects unreviewed drift and accidental or silent edits; it does not authenticate who made a change.
- The sidecar is **not covered by the checkpoint's checksum or by H1/H2**. Replacing both the sidecar and the registry consistently while keeping the accepted checkpoint file untouched passes the binding check. This is the principal residual risk of the sidecar approach.
- The acceptance record and acknowledgements remain operator assertions.
- The registry document is loaded at process start; the check compares the loaded registry, so an on-disk edit only takes effect on restart (as before).
- Not proof of the physical identity of a bearing.

## 6. Proposal needing approval (not implemented)

To close the residual risk the registry digest should be **inside** the checkpoint body (covered by `checksum`, chained by `previousCheckpointHash`, replayed by the verifier). That changes the checkpoint/anchor format, requires `verify_anchor` and `export_anchor` changes and a compatibility path for existing v2 checkpoints, and touches `ENGINE_TREE`/`VERIFIER_VERSION` binding. Per the standing stop condition I am **not** doing this. If approved, the design would be: new optional body field `registryDigest` under a new `format` revision (`FORMAT_V3`), verifier accepts V2 (legacy: binding supplied by sidecar only, reported as `SIDECAR_ONLY`) and V3 (binding verified from the body), `export_anchor` fills the field, `propose/accept` unchanged otherwise. Compatibility analysis and migration tests would be submitted before any change.
