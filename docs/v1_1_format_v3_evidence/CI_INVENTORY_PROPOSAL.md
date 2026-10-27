# CI source-inventory and count update: proposal (owner decision E: preparation)

Prepared on the research branch `research/v1-1-format-v3-registry-binding` only. Hosted CI was **not** run. `main` and its workflow are untouched. Nothing was weakened, skipped or deselected: every count is exact and every new test module is listed.

## 1. Changes made on this research branch (all in `ci/` and `docs/`, applied in separate commits so they can be reverted or re-derived)
| Item | Before (main) | Proposed | Why |
|---|---|---|---|
| `EXPECTED['application']` | 9 modules | + `test_lot_identity_ab=19`, `test_v11_hardening=17`, `test_format_v3=9` | the infra test `test_expected_counts_are_exact_and_cover_every_application_module` requires every `application/test_*.py` to be listed with an exact count; this was the single expected failure of the earlier candidates |
| `EXPECTED['vitest']` | 369 | **375** | clean-build count, see section 2 |
| `EXPECTED['playwright']` | 138 | **141** | three new real-browser tests in `tests/e2e/v11-hardening.spec.ts` (NDE replacement, provisional sighting on an excluded motor, provisional sighting on an affected motor) |
| `PORTS` | up to 4206 | + 4231, 4232, 4234 | ports the new owned-stack specs bind; the port-free preflight must cover them |
| `ci/frozen-source.json` | 294 files | 361 files (+67 added, 12 modified, 0 removed) | regenerated with `ci/freeze.py`; report in `docs/CI_INVENTORY_CHANGE.md` |

## 2. Vitest count under clean-build conditions (diagnosis)
`tests/unit/preview-privacy.test.ts` generates tests for `public/data` and, **only if it exists**, the untracked, git-ignored build output `dist/data`. Measured on this branch (JSON reporter, per-file counts; logs `vitest_nodist.json`, `vitest_withdist.json`):

| Condition | Files | Tests | `preview-privacy` |
|---|---|---|---|
| no `dist/` | 26 | 371 | 6 |
| after `npm run build` (what the CI gate does before `npm test`) | 26 | 375 | 10 |

The hosted gate runs `npm run build` (gate G) before `npm test` (gate H), so CI sees the with-`dist` number. The earlier 367/371 discrepancy on the candidate branch was this same file (371 = with `dist`). No test is flaky or random. The gate's expected number is therefore the clean-build number, 375 = (main's 369 at clean build) + 2 (lot-identity guard display, from the A+B candidate) + 4 (v1.1 display and validator tests).

## 3. Findings that matter for anyone re-freezing the manifest
1. **`ci/freeze.py` hashes working-copy bytes.** On Windows, files written with CRLF hash differently from the LF blobs that `.gitattributes` (`* text=auto eol=lf`) produces on a clean checkout, so a manifest generated in a CRLF working tree fails `run_gates.frozen()` on any clean clone. The manifest in this branch was therefore generated **from a fresh LF clone**, and `frozen()` was then verified on a second fresh clone. Procedure: commit all product/test/research changes; clone; run `ci/freeze.py --previous <old manifest>` in the clone; copy `ci/frozen-source.json` and `docs/CI_INVENTORY_CHANGE.md` back; commit; verify `frozen()` on another clone.
2. **Any tracked file outside `ci/`, `.github/`, `docs/` is in the manifest**, including `research/`. Editing a research document after freezing breaks the manifest. This branch therefore keeps reports, logs and evidence under `docs/` and freezes last.
3. The generated `docs/CI_INVENTORY_CHANGE.md` still prints the previous-manifest label from the earlier generation (`infra/phase31-ci-gates@04d974f`); the counts on its second line (294 to 361) are correct for this change.

## 4. What was and was not run locally
Run on a clean clone of the exact code SHA (see the owner report for the SHA and logs): all 12 application modules, integration (44), engine (127), exporter (7), CI infra (7), `frozen()`, `export_snapshot.py --check`, `tsc`, `npm run build`, Vitest, the full Playwright suite with the project's own config, mutation checks, the v1.0 reproduction.
**Not run:** the hosted workflow; gate B (foundation interop) and gate E (standards safety), which need the pinned GS1 checkout; the CI Playwright config with the pinned Chrome download (`PRAMAAN_CI_CHROME`). These need the pinned toolchain from `ci/prepare.py`. Their counts (foundation 21 checks) are unchanged by this branch's code, but that is a statement, not a measurement.

## 5. Approval needed
Review the `ci/run_gates.py` diff and the regenerated manifest, then decide whether the toolchain-dependent gates (B, E, pinned-Chrome Playwright) should be run locally with `ci/prepare.py` before any hosted run. No hosted run will be started without approval.
