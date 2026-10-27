# PS10 performance integration (isolated candidate)

Branch `integration/ps10-performance`, from the tested integration-hardening commit `bf0e87c50c52cee4c56c5db57951b84c096e30a1` with the performance candidate `e4d4ae6a3aade7b1de9dd9221b2641a6782f8370` merged (no textual conflicts: the candidate only adds files). Synthetic data only. The impact query is a conservative evidence projection, **not** a recall decision, clearance or authorization.

## What was integrated
The `performance/` package (`impact_query.py`, benchmark and validation tooling, `test_impact_query.py` with 19 tests) and `docs/ps10-performance/*`. It is **not** wired into `server.py`; nothing in the application calls it. No evaluator, F5/F6, A7, frontend, shipment-gate or checkpoint code was touched.

## Reconciliation with the updated lifecycle ledger and pins
- `ImpactQuery` uses the frozen `Ledger.watermark`, `snapshot` and `_config` through `object.__new__(Ledger)`. Against the final pinned `ledger.py` (`6674dfc0...`: lifecycle references checked for `MACHINING_RECORDED` / `QUALITY_INSPECTION_RECORDED` only) the candidate's 19 tests pass unchanged, and a ledger containing lifecycle machining/inspection events, imported records and legacy events with lifecycle-looking payload keys rebuilds and queries correctly.
- Lifecycle events carry no `slot` and no bearing lot, so the index ignores them as lot matches (tested); they are still part of the verified, hashed database image, so they invalidate the proof.
- No source pin changed in this round: `application/source-provenance.json` is unchanged from the hardening commit. `performance/` is deliberately outside the pinned roots (it is application-level, hashed by the frozen manifest instead).

## Inventory
- `ci/frozen-source.json`: 438 -> 446 files: 8 added, 0 removed, 0 modified (see `docs/CI_INVENTORY_CHANGE_PS10_PERFORMANCE.md`).
- `ci/run_gates.py`: new `EXPECTED['performance'] = {test_impact_query: 19, test_impact_integration: 21}`, executed under gate D as `performance.<module>` with the same exact-count pattern; `ci/test_infra.py` (7 tests, count unchanged) now also asserts every `performance/test_*.py` is registered.

## New cross-branch tests (`performance/test_impact_integration.py`, 21)
| Requirement | Tests |
|---|---|
| Imported records, machining and inspection events | rebuild verifies the whole fleet incl. the lifecycle unit; the lifecycle motor is found by its recorded bearing lot; a machining claim is never a lot match; a PASS inspection claim never removes a motor; legacy events with lifecycle-looking keys do not break the index |
| Uncertain sightings and historical exposure stay included | imported alias (NSB-204) of the recalled lot found; every motor the evaluator holds (`RECALL_HOLD`) is listed (superset check, run on a copy); look-alike `BR-2O4` sighting listed with `OBSERVATION_REQUIRES_EVALUATION`; unknown lot lists the whole fleet; removed lots from imported rework stay queryable; imported shipments are `recordedClaimOnly` / `releaseAuthorization: false` |
| New evidence invalidates stale projections | later import, lifecycle machining, lifecycle inspection, native observation each give `EVIDENCE_CHANGED_REBUILD_REQUIRED`, then `VERIFIED_INDEX_REQUIRED` for `query` and `query_json` until an explicit `rebuild()` (serialized cache warmed first) |
| Safety paths preserved | queries never change the database; evaluator outcomes identical with and without the reader; checkpoint stays `ANCHORED_CURRENT` through reads and rebuilds, new evidence ends it and the projection together; `ship()` is refused for every motor (including imported historical shipments) and no ticket is created; the response kind is never a decision and never says `operationalClearance` other than `NOT_ASSESSED` |

## Integration findings
1. **Compatible.** No conflict, no change needed to the candidate or to the ledger.
2. **Over-invalidation (limitation, fail-closed).** The proof key is a hash of the entire serialized SQLite image. Opening and closing the application (`Manufacturing(...)`, which a data-integration import, a lifecycle command or any server start does) changes that image even when no event is written, so the reader reports `EVIDENCE_CHANGED_REBUILD_REQUIRED`. A repeated or refused import adds no evidence but still voids the proof; the rebuilt projection is identical (tested, and the behaviour is pinned by a characterisation test so a future change is noticed). In a deployment where the application stays running and keeps writing (decision journal, snapshots, imports), the index would be rebuilt after nearly every operation; at 10K motors a rebuild is 127.64 s as reported by the candidate. Safe, not useful for live traffic, and consistent with the candidate's own disclosure ("ANY database write invalidates the full-image proof").
3. **Fleet precondition.** `rebuild()` requires `motors == app_units`; units provisioned without application registration make it unavailable (`FLEET_MEMBERSHIP_MISMATCH`).
4. **Pinned-implementation dependency.** The reader relies on frozen `Ledger` internals (`object.__new__`, `_config`). Any future ledger edit, including the two lifecycle pin changes, needs this suite re-run; it passed for the current pins.
5. **Lifecycle claims are not exposure data.** A passing quality-inspection claim neither removes a motor nor adds a match; machining events are only evidence retained in the verified image.

## Remaining performance limitations (from the candidate's report; nothing was optimized or re-measured here)
Warm ready-JSON p95: 13.45 ms at 100 motors, 102.80 ms at 1,000, **1,120.83 ms at 10,000 (not sub-second)**; first lot query 1,198 ms at 10K; cold verify/build 127.64 s at 10K (1.01 s at 100, 9.66 s at 1,000). Verification is O(database bytes) on every query (349.7 MB image at 10K); queries are serialized by an instance lock; long rebuild transactions retain a WAL snapshot; there is no continuous-ingestion story. The 10K query was deliberately **not** optimized in this round.
