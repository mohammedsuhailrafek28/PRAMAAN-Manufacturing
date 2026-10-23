# Safety and demo-readiness assessment: `integration/manufacturing-consolidated-candidate`

Tested source: `99e3a3b5afd8281d62c24cef69e30af0434c22db` (later commits are documentation only). Not merged to `main`; no PR, no deployment. Pinned v3 evaluator, foundation and integration ledger unchanged (gate K, 126 files verified). Option A R1-R20 preserved, with the owner-approved R5 UI amendment (`docs/R5_AMENDMENT.md`).

## Verdict: CONDITIONAL GO for a loopback, synthetic-data demo
Conditions: (1) show H1/H2 checkpoint behaviour from the prepared flow below, not as an ad-hoc live edit; (2) say that custody is local test custody, not independent custody (D8); (3) say `test_historical_resolution_entries_are_not_rewritten` fails by design pending an approved migration; (4) do not claim independent safety certification of H1/H2.

## Evidence (exact SHA)
| Check | Result |
|---|---|
| Hosted CI (Windows, pinned toolchain), run 40003889775 on `99e3a3b` | **FAILED, solely** on gate D `test_hardening` (the known D9 error, unmodified). Every other gate passed: K provenance, infra 7, engine 127, foundation 21 checks, integration 44, standards/safety, exporter 7, typecheck, build, Vitest 369/369, application modules, **Playwright 138/138 (serial, 6.8 min)**. |
| Earlier hosted runs | `eec4ca1`: browser gate hit the runner's 300 s limit. `b13b042`: 136/138 in parallel (two load timeouts, UI 4 s limit not raised). Both fixed by runner configuration only (timeout, serial); no assertion or count was relaxed. |
| Local | Python application 93 run (1 known error); Vitest 369; original Playwright 138/138; gate config 61/61; audit config 11/11; RC config 137/138 then the 1 failure (hard-coded port in a QR assertion) fixed and re-run. h1h2 config needs a separate unmodified backend checkout; superseded by the default config on this integrated tree. |
| Hosted-green | **Not achieved.** It cannot be until the D9 test is migrated or an expected-failure policy is approved. |

## What changed since checkpoint 1 (see `docs/UNIFIED_TEST_MIGRATIONS.md` for M1-M19)
* R5 amendment recorded and tested; M8 (PREFIX never earns or renews a lease) tested in unit (5) and browser (reload, navigation, visibility, back/forward).
* All 17 original Playwright failures investigated individually and resolved by contract-driven migrations with negatives, using owned per-test stacks (`recall-ui/tests/support/ownedStack.ts`) and explicit test-only custodian cycles. A full 6-step live capture journey now passes through 5 checkpoint generations.
* D5 implemented (`POLICY_NOT_ANNOUNCED`, `WATERMARK_REGRESSION`, `WATERMARK_BEYOND_LEDGER`), tests included (`application/test_d5.py`). Limit and alternatives in `docs/D5_D8_D9_STATUS.md`.
* D6 reduced and tested (`test_d6.py`); R18 evaluated (`docs/R18_LATENCY.md`).
* Reliability (6d177e8, scoped): fixed clock only around the two idempotence snapshots; owned-stack port/exit/cleanup hardening. CI (04d974f): ported with exact consolidated counts, collect-then-fail gates, regenerated manifest and `docs/CI_INVENTORY_CHANGE.md` (294 files; 98 added, 25 modified, 0 removed).

## Remaining defects and limits
* **D8** equivocation / latest-head: not solvable without a new custody model (blocker for any independent-custody claim).
* **D9** historical `OBLIGATION_RESOLVED`: app and export blocked by design; no read-only inspection path built.
* **D5** residual: a forged first publication at an old watermark is indistinguishable without a journal-to-ledger position binding (format change, needs approval).
* **D6** residual: the first read after new evidence publishes decisions (one append); needs an explicit publisher to remove.
* **R18**: at 100 motors / 1000 entries every request returns fail-closed 503 (about 20 s activation); demo scale p95 about 320 ms.
* Each capture puts the ledger in PREFIX_ONLY until a checkpoint cycle and server restart: correct per spec, but a live operator flow is slow. The browser journey was run by Playwright, not by a human operator.
* Genuine independent custody is not demonstrated: `checkpoint_ops accept` is operator-asserted on the same host.
* Not adopted from 6d177e8: opt-in diagnostics (latency/lifecycle specs, ports 4210-4212) and swapping the three feature specs' local helpers for its OwnedServer.

## Needs owner approval
1. The D9 test migration or an expected-failure CI policy (needed for hosted green).
2. D5 alternative (ledger-position binding) vs documenting the residual.
3. Whether to remove D6's remaining read-time publication (explicit publisher).
4. M9-M19 (new in this round) in addition to M1-M8.
5. Whether to adopt the per-cut verification memoization for R18.

## Demo flow (recorded captures at judging, per runbook)
Start from a seeded ledger with an owner-exported checkpoint (`checkpoint_ops` or `tests/owned_bootstrap.py` pattern), serve with `python app.py --database DB --trusted-anchor CHECKPOINT`. Show CURRENT console with per-motor clearance; run one capture; show PREFIX_ONLY (facts only, global DO NOT SHIP warning, API still 409 on decisions); run `checkpoint_ops propose`, then `accept` with the typed digest, restart with `--trusted-anchor <new> --previous-anchor <old>`; show CURRENT restored. `live.spec.ts` automates this end to end.
