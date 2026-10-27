# PS10 impact projection — hybrid proof (full image proof + evidence generation)

Status: **prototype, not merged, not deployed, not production-ready.** Branch `prototype/ps10-impact-hybrid`, based on the tested commit `864393dbfe138b993f0671d196a6b46b1d0ce77f` (`integration/ps10-performance`). Imported or recorded data remain claims, not authenticated physical facts; nothing here clears a motor.

## 1. What changed

| Item | Behaviour |
|---|---|
| Every normal query | Recomputes the **whole-image proof** (`serialize()` + SHA-256, domain `PRAMAAN_IMPACT_DATABASE_IMAGE_V1`) exactly as in `864393db`. Equal → serve. The full-image proof is not weakened. |
| Image-proof mismatch | Computes the complete **evidence-content generation** (`evidence_scope.fleet_state`) in one read transaction. Equal to the verified generation → only bytes the projection cannot read changed: the image proof is re-anchored, JSON cache cleared, projection reused. Different → `_key = _gen = None`, `EVIDENCE_CHANGED_REBUILD_REQUIRED`, then `VERIFIED_INDEX_REQUIRED` until a verified `rebuild()`. A stale projection is never served. |
| `rebuild()` | Image key + generation in one read transaction. Per-motor verification memo (Option A) keyed by (registry digest, motor digest): unchanged motors are not re-decoded; changed/new motors are verified once. Fleet membership, rollback and configuration-rewrite checks are kept. |
| Reader connection | `PRAGMA query_only` and `PRAGMA mmap_size = 1 GiB` (Codex `3811d782`), with Codex's two regression tests, byte-identical. |
| Maintenance | `close()` (idempotent) and `maintenance()` context manager close the read connection (and so its mapping) before VACUUM / truncate / replace and reopen afterwards; the next query re-anchors or fails closed. |
| Not added | No leases, no parallel workers, no weakened hashing, no change to ledger, evaluator, checkpoint, shipment gate, identity guard, release eligibility, frontend, pins. |

Response: `contentDigest` is the current image proof; new field `evidenceGeneration`; `integrity = FULL_IMAGE_PROOF_EVERY_REQUEST_EVIDENCE_GENERATION_ON_MISMATCH`.

## 2. Why the generation covers every input

`performance/evidence_scope.py` defines `SCOPE` (columns of `motors`, `events`, `captures`, `rejections`, app-unit rows) and digests all of it per motor, the registry/fleet membership, and the schema. Evidence for coverage (`test_hybrid_proof.py`, 65 tests):

* **Authorizer test**: every column read by the genealogy, snapshot and watermark paths ⊆ `SCOPE`; the full `app.snapshot()` reads only scope plus documented decision inputs.
* **Table classification**: every ledger table is in `SCOPE` or in the explicit non-evidence set `{app_clock, decision_runs, recall_announcements, app_ship_tickets, app_audit, app_audit_head}`; a new unclassified table fails the test.
* **Each scope column** is mutated individually: generation changes, and restores when the value is restored.
* **Inert tables**: writes to every non-evidence table leave impact output unchanged and re-anchor only.
* **Adversarial**: every `events` column, changed `received`, deleted tail/middle/whole motor, reordered rows, substituted captures, swapped motor rows, configuration rewrite, injected rejection, restored older DB, registry change (re-verifies all), fleet membership, schema change.
* **WAL**: WAL-only harmless write → re-anchored with the main file unchanged; WAL-only evidence write → rejected; checkpoint after an evidence write cannot make the old projection current; single snapshot while a writer commits.
* **Concurrency**: harmless/evidence commit during verification, between publication and first use, inside the mismatch decision; two writers + reader stress.
* **Restart / tamper**: restart verifies all motors; 13 malformed/tampered cases fail closed without crash; tampering never becomes a re-anchor.

Test counts: `test_impact_query` 21, `test_impact_integration` 21, `test_hybrid_proof` 65.

### Updated test
Exactly one pre-existing test changed: `test_merely_opening_the_application_voids_the_proof` → `test_merely_opening_the_application_does_not_void_the_verified_evidence`. The old test pinned the very limitation this work removes (open/close invalidating the projection). The replacement asserts the same answer, a re-anchored image proof, and that a real evidence change still raises `EVIDENCE_CHANGED_REBUILD_REQUIRED`. (`test_a_repeated_or_refused_import…still_voids_the_proof` is untouched; its name is stale.)

## 3. Measured results

Same ledger per size; this machine (16 logical CPUs, Windows, SQLite 3.49.1); all answers equal across variants. `baseline` = `864393db`; `baseline+mmap` = legacy reader plus only the mmap pragma (Codex-equivalent). Raw JSON: `docs/ps10-performance/benchmarks/hybrid-n{100,1000,10000}.json`; harness `performance/benchmark_hybrid.py`.

Warm ready-JSON query p50 / p95 (ms):

| Motors | Hybrid | Baseline | Baseline+mmap |
|---|---|---|---|
| 100 | 5.2 / 5.8 | 8.5 / 9.6 | 5.5 / 6.2 |
| 1,000 | 49.8 / 53.6 | 85.0 / 93.8 | 50.3 / 53.3 |
| 10,000 (349.7 MB) | 496.1 / 518.7 | 795.9 / 879.1 | 503.1 / 566.7 |

Other operations (ms):

| Motors | Cold rebuild hybrid / baseline / +mmap | Harmless-write recovery: first query → next | Evidence rejection | Incremental rebuild (1 changed) vs baseline rebuild |
|---|---|---|---|---|
| 100 | 442 / 757 / 763 | 28–29 → 7 | 20 | 29 vs 1,052 |
| 1,000 | 5,081 / 9,319 / 8,771 | 189–213 → 57–64 | 184 | 179 vs 8,876 |
| 10,000 | 49,525 / 86,345 / 93,870 | 2,067–2,287 → 562–755 | 1,908 | 1,929 (1 verified, 9,999 reused) vs 87,379 |

Baseline after open/close: `EVIDENCE_CHANGED_REBUILD_REQUIRED` (full rebuild needed). Hybrid: recovers in one slow query.

Concurrent 30 s (one evidence writer at 4/s for 100 and 1,000 motors, 1/s for 10,000; plus a harmless writer and one reader):

| Motors | Evidence events | Served | Refused → rebuilt | Rebuild p50 | Re-anchors |
|---|---|---|---|---|---|
| 100 | 102 | 2,457 | 102 | 38 ms | 50 |
| 1,000 | 111 | 16 | 64 | 223 ms | 4 |
| 10,000 | 30 | 1 | 7 | 2,130 ms | 0 |

In every run: no other errors, served event counts non-decreasing and within the ledger, final reader events equal ledger events, no stale answer served.

Reading: steady-state ≈ baseline+mmap (so Codex's gain is preserved while the full-image proof stays); the hybrid's value is harmless-write recovery (~1 query instead of a 87 s rebuild at 10K) and incremental rebuild after one evidence change (1.9 s vs 87 s). Availability under continuous evidence writes at 10K is poor (a rebuild takes ~2 s, so almost every query is refused).

## 4. mmap failure characteristics

* `mmap_size` is a connection-local upper bound, not an allocation; the OS maps lazily.
* An I/O fault on the mapped file (device error, truncation by another process) can raise a signal and terminate the process instead of a catchable `sqlite3.Error`. Plain reads would return an error.
* On Windows an open mapping can block `VACUUM`, truncation or file replacement. Close readers, or use `ImpactQuery.maintenance()`, before DB maintenance; tests cover checkpoint, VACUUM and `os.replace` through it, and that `close()` releases the file.
* `serialize()` + SHA-256 still cover the whole snapshot; mapped and unmapped reads give identical proofs and payloads (Codex test). Only the pinned Windows / SQLite 3.49.1 was measured.

## 5. Remaining risks

1. First query after a harmless write costs image proof + generation (≈2.1–2.3 s at 10K).
2. Availability under ≥1 evidence write/s at 10K is poor.
3. A registry change re-verifies every motor.
4. Cold rebuild is serial: 49.5 s at 10K (no workers by instruction).
5. No external anchor: a coherent forged rewrite is caught in-process (generation differs) but accepted after restart; a restart verifies from scratch. Documented in tests.
6. Pin coupling: the reader refuses with `READER_PIN_MISMATCH` unless `ledger.py`/`profile.py` match `application/source-provenance.json`.
7. Schema binding is conservative: any schema change forces a rebuild.
8. Stale test name noted above; response field changes (`evidenceGeneration`, `integrity`) may affect consumers.
9. Single machine, single SQLite build; no hosted CI.

## 6. Rollback

Nothing is merged, pushed, tagged or deployed. Discard by deleting branch `prototype/ps10-impact-hybrid`; the tested baseline remains `integration/ps10-performance` at `864393dbfe138b993f0671d196a6b46b1d0ce77f`. Option A (`prototype/ps10-impact-option-a`, `e0bb116b…`) is a separate branch.
