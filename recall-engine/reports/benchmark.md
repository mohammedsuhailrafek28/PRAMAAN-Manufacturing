# Benchmark: evaluation latency

Synthetic data only, derived from the supplied fixtures. Measures the pure `evaluate()` function (single thread, no I/O, no database, no network). **Not** a statement about production load, real event volumes, storage latency, or factory-scale correctness.

Environment: Python 3.12.10, Windows-11-10.0.26200-SP0 (AMD64 Family 25 Model 117 Stepping 2, AuthenticAMD).

## A. Supplied fixtures

25 oracle evaluations (10 cases, both policies, all watermarks) x 200 passes after 5 warm-up passes = 5000 timed calls. Histories are 4-12 events each.

| mean | p50 | p95 | p99 | max |
|---|---|---|---|---|
| 185.7 us | 145.3 us | 391.4 us | 590.9 us | 1244.4 us |

## B. Latency vs history length

case-01 plus K extra NDE rework cycles (4 events each, fully reconciled, still EXCLUDED). Median of repeated calls.

| Events | Median latency | us / event |
|---|---|---|
| 9 | 0.141 ms | 15.64 |
| 109 | 0.849 ms | 7.79 |
| 1009 | 9.67 ms | 9.58 |
| 5009 | 59.602 ms | 11.9 |
| 20009 | 272.685 ms | 13.63 |

Near-linear: per-event cost stays within roughly 8-15 us from 100 to 20,000 events. A profile at ~20,000 events shows time spread across linear passes with no quadratic hotspot; the mild per-event growth at the largest sizes was not investigated further.

## C. Fleet batch

10000 motors (the 10 fixture cases x 1000, re-keyed by motorSerial), both policies = 20000 evaluations over 87000 events, evaluated one after another.

- Wall time: **3.67 s**; mean **183.5 us** per evaluation; 5450 evaluations/s
- Findings produced: {'EXCLUDED_WITH_EVIDENCE': 4000, 'AFFECTED': 10000, 'UNRESOLVED': 6000}

These motors are copies of 10 histories, so this tests throughput, not diversity.
