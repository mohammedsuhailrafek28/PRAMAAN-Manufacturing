# Owner report: FORMAT_V3 registry binding (research branch, not for merge)

Branch `research/v1-1-format-v3-registry-binding`, from `339649576c49158b38eb2496c98d6d88f8534ae3`.
**Code SHA tested: `c139802ec16776f7dcb8337af27bf96162e2e6ce`.** The commit after it adds only files under `docs/` (this report and evidence logs). No PR, merge, tag, deployment, hosted CI run or evaluator re-pin was done. `main`, the frozen tag `manufacturing-demo-v1.0`, `recall-engine/`, foundation and the integration ledger are untouched.

Scope limits that still apply: same-host custody is not independent verification; this is not a production-readiness or independent H1/H2 safety claim; no independent benchmark has been run.

## 1. FORMAT_V3 compatibility and threat analysis
`research/v1_1_format_v3/FORMAT_V3_COMPATIBILITY_AND_THREAT_ANALYSIS.md` (written before the code, commit 7a3d998). Summary: the checkpoint body now carries `registryBinding` (digest, id, version, entry count, provenance). V1/V2 checkpoints keep verifying as history but report `UNBOUND_LEGACY_FORMAT` and never grant current release eligibility. Chain rules: V2→V3 and V3→V3 are allowed, V3→V2 is refused. The sidecar file is advisory only.

## 2. Implementation and adversarial evidence
Evidence: `docs/v1_1_format_v3_evidence/v3_evidence.json`, `python_suites.txt`, `mutation_v3.json`.
- `test_format_v3` has 9 tests. They cover: 10 malformed or resealed binding blocks all rejected; V2 history verifying unchanged with no eligibility; the no-downgrade chain rules; a registry-only update accepted with 0 new journal entries; the replay, rollback and substitution matrix (old checkpoint + new registry and new checkpoint + old registry both give `DISCREPANCY`, not eligible); a missing or forged live registry giving `LedgerBlocked`; forged sidecar not trusted.
- Never-creates-eligibility: a motor with an UNKNOWN-lot identity bypass stays held across V2→V3 migration, a V3 root, and a relabelled V2 checkpoint resealed as V3. `accept` is refused even with every acknowledgement supplied.
- Mutation check: unmutated 26 tests, 0 failing; 6 of 6 V3 mutants killed (binding ignored, legacy grants eligibility, block validation off, legacy prior without ack, identity findings dropped, diff blind). The v1.1 mutation script on this branch kills 6 of 7. The survivor `missing_binding_tolerated` is obsolete because the MISSING status no longer exists. It is not a test gap. I did not edit `research/` after freezing.
- v1.0 reproduction (`reproduce_v1_0.json`): the v1.0 behaviour is reproduced with exit 0. On this branch all six sentinel motors are held (legacy format), and 4 are refused for identity at `accept`.
- Preserved counts: badLotCases 240, bypassCases 102, registeredUnaffectedCases 80, 0 false holds.
- Real defect found by the browser regression and fixed: `recall-ui/src/domain/validate.ts` rejected guarded decisions (EXCLUDED_WITH_EVIDENCE with RECALL_HOLD) as contradictory and blanked the console. It now accepts them only when a guard has `guardChangedAction===true` and the evaluator action was `RELEASE_ELIGIBLE`. Vitest tests added.
- Real-browser spec `recall-ui/tests/e2e/v11-hardening.spec.ts` (3 tests): NDE replacement through the form, provisional sighting on an excluded motor, provisional sighting on an affected motor.

## 3. Ledger atomicity design comparison
`research/v1_1_format_v3/LEDGER_ATOMICITY_DESIGN_COMPARISON.md`. `Ledger.capture` is atomic per document but bound to one producer source, while work-order assembly interleaves MES, MATERIAL and ASSY sources. Atomic multi-source capture therefore needs a ledger semantic change. Recommendation: design B2 (an explicit `WORK_ORDER_ABANDONED` event) first, then option A (atomic batch). No ledger edit was made.

## 4. Trusted verification semantics (research only)
`research/v1_1_format_v3/TRUSTED_VERIFICATION_SEMANTICS_RESEARCH.md`. Evaluator trust requires a source listed in `trustedVerifierSources`, actor independence and approved methods. No application command authors QA events, and no new clearance operation is proposed. Physical authentication is not implied.

## 5. CI inventory proposal
`docs/v1_1_format_v3_evidence/CI_INVENTORY_PROPOSAL.md`. EXPECTED counts: application += 3 modules (19, 17, 9), Vitest 375 (clean-build; 371 without `dist/`), Playwright 141, ports 4231/4232/4234, frozen manifest 294→361 files. Nothing weakened or skipped.

## 6. Independent benchmark preparation
Tooling only: generic runner, pre-registration template (unsigned), sealing script, 3 candidate-authored sample cases. The samples are harness self-checks (3/3 agree) and are **not evidence**. No blinded author, ground-truth reviewer or sealed case exists. No independent validation is claimed.

## 7. Commands and logs
Clean clone at the exact code SHA (`sha.txt`, status clean), via `battery2.sh`:
- Application modules (12): all OK, with counts 7, 4, 23, 12, 5, 3, 13, 16, 10, 19, 17, 9. Integration 44, engine 127, exporter 7, CI infra 7/7 (`python_suites.txt`).
- `frozen()` OK; `export_snapshot.py --check` current.
- `tsc` exit 0 (`typecheck.txt`); build exit 0 (`build.txt`).
- Vitest: 26 files, 375 passed (`vitest.txt`).
- Playwright: 141 passed (`playwright.txt`).

**Not run:** hosted CI; gate B (foundation interop) and gate E (standards), which need the pinned GS1 checkout; the CI Playwright config with the pinned Chrome.

## 8. Remaining risks and findings
1. A provisional sighting on an excluded or releasable motor is an identity-unsafe exclusion, so `accept` refuses the whole candidate. Any HANDHELD role can therefore block fleet-wide checkpoint renewal. This is fail-closed, an availability trade-off.
2. The console cannot capture while the checkpoint is stale, so recovery is API/operator only (a UI deadlock).
3. Retroactive registration plus operator acknowledgement can create eligibility through a reviewed checkpoint. That is an operator assertion.
4. V3 puts the registry at the same trust level as the ledger prefix. It is still same-host. Replacing the pinned checkpoint file and restarting defeats it, as it does for the ledger.
5. Existing deployments stay held until a V3 checkpoint is accepted.
6. `ci/freeze.py` hashes working-copy bytes, so the manifest must be generated from an LF clone. Any `research/` edit after freezing breaks the manifest.

## 9. Decisions requested
- Is V3 digest-in-checkpoint acceptable as the final safety boundary, given risk 4?
- Approve a UI/operator recovery path while the checkpoint is stale (risk 2)?
- Is the sighting-induced fleet-wide renewal block acceptable, or should it be scoped (risk 1)?
- Approve the B2 abandon-event design work?
- Who has verification and correction authority, and how is it authenticated off-host?
- Run the toolchain-dependent gates (B, E, pinned Chrome) locally before any hosted run?
- Go-ahead to recruit an independent author and reviewer?
- Update the obsolete mutant in the v1.1 script on a later branch?

Stopping here for owner review.
