# R18 latency evaluation (consolidated candidate)

R18 (spec): 100 motors and 1,000 journal entries; snapshot p95 below 1.5 s **or** HTTP 503 `VERIFYING` with eligibility withheld; the existing 4 s UI timeout is not raised. Nothing here weakens that.

Measured on Windows, Python 3.12, one run each, `python -m application.checkpoint_benchmark` (synthetic, disposable archive):

| Tree | Entries | Activation verification | 12 snapshot requests | Result |
|---|---|---|---|---|
| `548e434` (before D5) | 1000 | 19.4 s | all 503 `VERIFYING`, 1.66-2.14 s | `SAFE_503_FALLBACK_ONLY` |
| consolidated tree with D5 | 1000 | 20.4 s | all 503 `VERIFYING`, 1.64-1.90 s | `SAFE_503_FALLBACK_ONLY` |

* D5 adds about 5% to verification (one extra ledger watermark read per motor per verify).
* R18 is met by its fail-closed branch, **not** by the 1.5 s branch: at 100 motors / 1000 entries the application serves no decisions. That is an availability limitation, never a safety failure (503 carries no decisions and no eligibility).
* Where the time goes (profile of a warm, deadline-free snapshot, about 6 s unprofiled): `Audit.decide` is run for every motor on every snapshot, and each run verifies that motor's whole event chain 3-4 times (`watermark`, `snapshot`, and again in `_snapshot`) with canonical-JSON hashing (`rfc8785`). Roughly two thirds of the time is this repeated verification, not the replay cache.
* Proposed optimization (not applied): memoize `_verified_rows` per consistent cut inside `Manufacturing.snapshot()` (one write transaction, nothing can change), returning copies. Expected about 3x on the dominant term, still above 1.5 s at this size. It stays in the application layer (the integration ledger is untouched) but sits on an integrity-verification path, so it should be a separately reviewed change with a test proving a tampered row is still detected inside one cut.

Demo scale (seeded demo, 6 motors, deadline 1.25 s as in the server): 12 consecutive snapshots 165-352 ms, p95 about 320 ms, all `ANCHORED_CURRENT`. The demo is far below the limit.

Status (owner decision): memoization of integrity verification is DEFERRED; the 100-motor/1000-entry safe 503 is a documented availability limitation; the 4 s UI timeout is not raised to hide verification latency. The roughly 320 ms demo-scale p95 is a measurement on one machine, not a production performance guarantee.
