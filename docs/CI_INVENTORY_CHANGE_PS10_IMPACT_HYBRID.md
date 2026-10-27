# CI inventory change — PS10 impact hybrid proof

Base: `864393dbfe138b993f0671d196a6b46b1d0ce77f`. `ci/frozen-source.json` regenerated with `ci/freeze.py --previous` (old manifest: 446 files).

Expected change set (verified against the regenerated manifest in the commit that follows):

* Added: `performance/evidence_scope.py`, `performance/test_hybrid_proof.py`, `performance/benchmark_hybrid.py`.
* Modified: `performance/impact_query.py`, `performance/test_impact_query.py` (+2 Codex tests), `performance/test_impact_integration.py` (one test replaced), `performance/run_validation.py` (focused pattern 19→21), `ci/run_gates.py` (`EXPECTED['performance']`: 21 / 21 / 65).
* Docs and benchmark JSON are not part of the frozen source set.

No protected component (recall-engine, ledger, evaluator, checkpoint, shipment, application, frontend, pins) is changed. Gate behaviour is otherwise unchanged; no hosted CI used.
