# Independent benchmark: preparation status (owner decision 7)

**Nothing has been scored. No independent case exists, no reviewer verdict exists, no sealed manifest exists, and nothing in this repository is independent validation.** Every test on this branch was written by the candidate engineer (Claude).

## Prepared
| Item | Where | State |
|---|---|---|
| Author-facing behaviour contract (stated from the owner's requirements, not from the implementation) | `research/v1_1_scoped_containment/benchmark/HANDOFF_FOR_CASE_AUTHOR.md` | ready |
| Case schema v1.2 (adds `acknowledgeAll` and `expectAccepted` on `accept_checkpoint` steps) | `research/v1_1_scoped_containment/benchmark/case.schema.v1_2.json` | ready |
| Two separate hand-off packages (`author/`, `reviewer/`), each with its own sha256 MANIFEST; no implementation, test or candidate output is copied | `research/v1_1_scoped_containment/benchmark/make_packages.py`, output hashes in `packages_manifest.json` | built from the clean clone at the candidate SHA |
| Generic runner (no case knowledge); now checks `expectAccepted` and reports disagreements | `research/v1_1_format_v3/benchmark/run_cases.py` | ready |
| Sealing and verification by sha256 | `research/v1_1_format_v3/benchmark/seal_manifest.py` | ready; refuses to re-seal |
| Pre-registration template (roles, frozen items, hypotheses H1–H4, procedure, disclosures) | `research/v1_1_format_v3/benchmark/PREREGISTRATION_TEMPLATE.md` | unsigned template |
| Harness self-checks (candidate-authored, 2 new + 3 earlier) | `research/v1_1_scoped_containment/benchmark/samples/`, `research/v1_1_format_v3/benchmark/samples/` | only prove the runner executes; **not evidence, never to be shown to the author** |

## Roles still to be filled (all must be different parties)
1. **Blinded case author** (for example Codex, as the owner suggested): receives only `author/`.
2. **Ground-truth reviewer**: a different party; receives `reviewer/` plus the delivered cases; records AGREE / DISAGREE / CONTESTED per case **before** any run.
3. **Candidate engineer** (Claude): sees only the development split (30 percent, assigned by a party other than the engineer) and the runner.

## Sequence still to happen
author delivers cases → reviewer verdicts recorded → split assigned by a third party → `seal_manifest.py seal` for the sealed set, manifest committed → candidate SHA frozen → one confirmatory run → results published unchanged. Any candidate change afterwards is a new version and a new split.

## What the contract tells the author about the owner's decision 3
It states the owner's rule in the owner's words (sighted motor stays held; other motors renewed only if isolation is established; otherwise preserve the wider hold) and does **not** list the implementation's obligations, so the author cannot tune cases to them. The candidate's obligations are in `SCOPED_CONTAINMENT_DESIGN.md`, which the author must not read.

## Disclosure to carry into any later report
The candidate engineer wrote the runner, the schema extension and all samples. If the author or reviewer is not independent of the candidate engineer, results are exploratory only. Same-host custody is not independent verification.
