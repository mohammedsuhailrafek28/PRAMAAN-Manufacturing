# CI inventory change: Render Free reliability

Branch `fix/ps10-free-reliability`, based on the deployed release `514834b`.

Changed: `application/audit.py` (the verification budget is read from `PRAMAAN_VERIFY_BUDGET_SECONDS`, default 1.25 s, accepted range 0.25-30 s, anything else falls back to 1.25 s), `application/service.py` and `application/anchors.py` (use that budget instead of a literal 1.25), `application/server.py` (queued read-only requests reuse a verification that started after they arrived; every command clears it; failures are never stored; the budget above), `Dockerfile` (`PRAMAAN_VERIFY_BUDGET_SECONDS=8`).
Added: `application/test_shared_reads.py` (9 tests).

No change to the evaluator, genealogy, simulator, ML model, assistant rules, recall policy, gate or evidence-integrity logic, and no verification step is skipped or shortened.
