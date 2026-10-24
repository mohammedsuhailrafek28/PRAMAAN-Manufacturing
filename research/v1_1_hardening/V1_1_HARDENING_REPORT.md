# v1.1 safety hardening: owner-decision implementation report

Branch `research/v1-1-safety-hardening`, built on `research/lot-identity-ab-candidate` @ `1e7e571`. Research candidate. **Not promoted, not merged, no PR, no deployment, no tag.** Nothing is selected or frozen for release. `main`, MSME PRAMAAN, `recall-engine/`, the foundation, the integration ledger and the frozen tag `manufacturing-demo-v1.0` are untouched. Loopback only, synthetic data only. This is not production readiness and not independent H1/H2 safety certification. **Independent custody has not been demonstrated**; everything below that says "binding", "acknowledgement" or "registry" is same-host. **No independent validation is claimed**: every test was written by the candidate author.

Stop conditions respected: no new event type, no ledger-profile change, no pinned-evaluator change, no checkpoint/anchor format change, no promotion. Items that need one are written as designs and listed in section 6.

## 1. What was implemented, by owner decision

| # | Owner decision | Result | Detail |
|---|---|---|---|
| 3 (highest) | Registry custody | **Implemented** as checkpoint-bound registry snapshots in a sidecar; any discrepancy holds every motor | `REGISTRY_CUSTODY_DESIGN.md` |
| 1 | NDE quarantine / remediation | **Implemented** (derived quarantine block; controlled replacement of DE or NDE). Evidence-backed investigation/correction **blocked** | `NDE_QUARANTINE_AND_RECOVERY.md` |
| 2 | Suspicious observations | **Implemented** with the existing event type as an unverified, raw-preserving sighting; explicit event type left as a design | `UNVERIFIED_SIGHTING_DESIGN.md` |
| 4 | Interrupted operations | **Implemented**: separate operational-integrity guard, own reason, own UI explanation; fail-closed and retry refusal kept | `CRASH_RECOVERY_LIMITS.md` |
| 5 | Independent benchmark | **Prepared only**: handoff, v1.1 case schema, author-package builder, reviewer worksheet. Nothing run | `INDEPENDENT_BENCHMARK_HANDOFF_V1_1.md` |
| 6 | Crash atomicity | **Not touched** (separate ledger workstream); recovery limits documented | `CRASH_RECOVERY_LIMITS.md` |
| 7 | Quality | Vitest 367/371 explained; 240/102/80 cases preserved; guards consistent across snapshot, API, review, UI | sections 2 and 3 |

### Files changed
`application/registry_binding.py` (new), `anchors.py` (sidecar written next to the checkpoint; checkpoint bytes unchanged), `lot_identity.py` (integrity split, quarantine, sighting rule), `service.py` (binding enforcement, `replace(slot)`, `observe(slot, raw)`), `checkpoint_review.py` and `checkpoint_ops.py` (registry diff, registry acknowledgement, sidecar carried at accept), `server.py` (`slot`), UI (`types.ts`, `DecisionExplanation.tsx`, `ProvenanceBar.tsx`, `ManufacturingWorkbench.tsx`), test bootstraps (`recall-ui/tests/browser_server.py`, `owned_bootstrap.py` now publish with a sidecar), tests (`test_v11_hardening.py` new, 17 tests; `test_lot_identity_ab.py` updated as described below; `v11-hardening-display.test.tsx` new, 3 tests).

### Test expectations that changed (owner-requested semantics, not weakened)
1. `test_lot_identity_ab` bad-lot matrix, path `observe`: 32 of the 40 observe cases are now **accepted as unverified sightings** instead of refused (the owner decision). The assertion for those rows is stricter in effect: `eligible == false`, guard `IDENTITY_NOT_ESTABLISHED`, action `RECALL_HOLD`, for all 32. The 8 invalid ones (missing, empty, whitespace, over-long) are still refused with zero events. The 160 assembly and 40 replacement refusals are unchanged.
2. `Interrupted` test: the reason moved from `identityGuard` to the new `integrityGuard`; the test now asserts `integrityReasons == ["OPERATION_INTERRUPTED"]` and that identity reasons are empty.
3. `mutation_check.py` (v1.0 A+B mutants) signature updated for the new guard function.

## 2. Measured results (this machine, this commit)

| Check | Result | Log |
|---|---|---|
| Registry custody adversarial matrix | all attacks held (checkpoint stays `ANCHORED_CURRENT`, evaluator still `RELEASE_ELIGIBLE`, motor not eligible); valid update then explicit review then new accepted checkpoint makes both motors eligible | `v11_evidence.json`, `final_python_suites.txt` |
| New v1.1 module | 17 tests OK | `final_python_suites.txt` |
| 240 bad-lot captures | 200 refused with 0 events (160 assemble, 40 replace); 32 observe accepted as unverified sightings, **all 32 held, none eligible**; 8 observe refused (invalid input) | `ab_evidence.json` |
| 102 bypass cases | 102 of 102 held | `ab_evidence.json` |
| 80 legitimate registered lots | 0 false holds | `ab_evidence.json` |
| Real v1.0 DB (frozen c25466c) | v1.0 says eligible for 5 of 6; this branch holds all 6 (the 4 unsafe with `SENTINEL`/`UNREGISTERED`, all with `REGISTRY_BINDING_MISSING` because v1.0 wrote no binding); `propose` refuses 4 for identity; `accept` refuses even with every motor acknowledged | `reproduce_v1_0.json` |
| Mutation check (v1.1) | 7 mutants killed (1 to 7 failing tests each); unmutated fails 0 | `mutation_check.json` |
| Original application modules (9) | 93 tests OK | `final_python_suites.txt` |
| `test_lot_identity_ab` | 19 OK | same |
| Integration / engine / exporter | 44 / 127 / 7 OK | same |
| CI infra | 6 of 7; **1 expected failure** `test_expected_counts_are_exact_and_cover_every_application_module` (new test modules are not in the CI inventory; `ci/` not edited, inventory refresh requested in section 6) | same |
| `tsc --noEmit` | exit 0 | `final_typecheck.txt` |
| Vitest | 26 files, 370 tests OK | `final_vitest.txt` |
| Playwright | **138 of 138** passed (4.4 min), system Chrome. No new browser test was added; the new UI callouts and the slot select are covered by vitest and by HTTP-level tests only | `final_playwright.txt` |

### Vitest 367 versus 371: explained
Per-file counts from three consecutive runs on this branch's base were identical (367 tests, 25 files). Running the same commit `1e7e571` in the earlier worktree gave 371. The only file that differs is `tests/unit/preview-privacy.test.ts`: **10 tests in the worktree that had a `dist/` build, 6 in the one without**. The file iterates `public/data` and, if it exists, the untracked build output `dist/data`, generating 2 more tests per extra directory. CI's 369 for the unmodified UI (365 + 4) is the same effect. The count depends on whether `recall-ui/dist` exists; it is deterministic and no test is flaky or random. (Earlier note "a property-based test is likely" was wrong.) On this branch: 367 baseline without `dist`, plus 3 new tests = 370. Logs: `vitest_run1..3.json`, `vitest_ab_1e7e571.json`, `vitest_hd_final.json`.

## 3. Consistency across surfaces
The identity guard, integrity guard, registry-binding finding and quarantine are produced by one function (`lot_identity.guard_decision`) from one set of findings. They appear in the snapshot decisions, `/api/snapshot`, the post-command snapshot, the checkpoint review (same reason codes, tested), and the UI types and callouts. The UI is display only; API-level behaviour does not depend on the UI omitting anything (extra body fields such as `currentReleaseEligible` are ignored, tested).

## 4. Known risks and limits (updated)
1. **Registry binding is same-host and the sidecar is outside the checkpoint checksum.** Someone who can rewrite the registry and the sidecar consistently (leaving the accepted checkpoint file untouched) passes the check. Not independent custody. Closing it needs the registry digest inside the checkpoint body (approval request A).
2. Acknowledgements and the registry-change acknowledgement are operator assertions, not authentication.
3. A checkpoint made before this feature has no sidecar: every motor is held until a candidate is accepted with registry acknowledgement. This is intended and visible, but it is a migration cost.
4. Unverified sightings use the existing `SLOT_STATE_VERIFIED` field `observedLot` for free text. A sighting holds a motor until the slot is physically re-installed; there is no closed-investigation record because the evaluator has no clearance path for it.
5. Evidence-backed investigation or correction cannot clear a motor (blocked, section 6).
6. Quarantine is derived advice; it has no workflow, owner, or state.
7. Interrupted operations: no in-application reconciliation; multi-event capture is not atomic (unchanged ledger).
8. Still true from the A+B report: one identity-unsafe exclusion row blocks `accept` for the whole candidate; slot-agnostic hold is conservative, not minimal; historical basis keeps a motor held after replacement; supplier-scoped recalls unsupported; look-alike hints only for unresolved lots; physical mislabelling is undetectable by software.
9. `replace` now accepts NDE; a UI/Playwright test of the NDE form was not added.
10. Latency was not re-measured on this branch (the previous +3.5% figure belongs to 1e7e571). The binding check adds a file read and a registry digest compare per snapshot; not measured.

## 5. Reproduction
From a checkout of this branch's tip (SHA in the final message): `python -B -m unittest application.test_v11_hardening -v`; `python -B research/v1_1_hardening/mutation_check.py out.json`; `python -B research/lot_identity_ab/reproduce_v1_0.py out.json` (needs the frozen commit in the local object store); `LOT_AB_EVIDENCE=out.json python -B -m unittest application.test_lot_identity_ab`; `V11_EVIDENCE=out.json python -B -m unittest application.test_v11_hardening`; vitest and Playwright from `recall-ui`. `results/final_python_suites.txt`, `final_vitest.txt` and `final_playwright.txt` were taken before the last two small changes (the 17th v1.1 test, an HTTP check of the `slot` parameter, and moving the identity refusal ahead of the registry-acknowledgement check in `accept`); the post-change evidence is `results/clean_checkout.txt`, a fresh clone of the pushed tip at `11724e3`: 11 application modules OK (v1.1 module 17 tests, `test_lot_identity_ab` 19, the original 9 modules unchanged) and the frozen-v1.0 reproduction (v1.0 eligible: 5 motors; this branch eligible: none; 4 refused for identity). The UI suites and the mutation/legacy checks were not rerun after those two changes; neither touched UI code, and the mutation check and `reproduce_v1_0.json` above are from before the reorder (the reproduction was rerun after it, in the clean clone).

## 6. Precise next approval requests
A. **Anchor-format change (registry digest inside the checkpoint body).** Closes known risk 1. Needs `FORMAT_V3`, verifier and exporter changes, legacy-V2 compatibility path. Compatibility analysis and migration tests first; see `REGISTRY_CUSTODY_DESIGN.md` section 6.
B. **`UNVERIFIED_SIGHTING` event type.** Schema, permissions and evaluator-isolation analysis are in `UNVERIFIED_SIGHTING_DESIGN.md` section 7; it needs a capture-profile and pinned-evaluator change.
C. **Trusted-verification / investigation-correction semantics** (who may author them, how authority is established away from the same host, how they interact with the exclusion rule) before any "investigated and cleared" path exists.
D. **Ledger atomicity workstream** (single-transaction multi-event capture, or an abandon event, plus an in-application reconcile command held to the same review rule).
E. **CI inventory refresh** for the new modules (`test_lot_identity_ab` 19, `test_v11_hardening` 17) and vitest count; `ci/` was not edited.
F. **Independent benchmark go-ahead:** an independent case author and a separate ground-truth reviewer, then sealing; until then no independence claim.
G. Decide whether the sidecar candidate is acceptable as an interim measure or should wait for A.
