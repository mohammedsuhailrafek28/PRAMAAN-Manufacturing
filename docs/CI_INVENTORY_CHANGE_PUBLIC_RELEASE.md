# CI inventory change: privacy-cleaned public release tree

This tree is the verified deployment tree `fe43f5a` as a single commit with no development history. Machine-specific absolute paths (user home, workspace, and the encoded workspace name) were replaced by `<USER_HOME>`, `<WORKSPACE>` and `<WORKSPACE_ID>` in text evidence, validation logs and one design note. Hashes recorded for those redacted files in `docs/ps10-performance/evidence-index.json` and `docs/release-candidate-evidence/evidence-files.json` were updated to the redacted bytes; the other fields of those indexes still describe the earlier development commits.

The `ci/frozen-source.json` pins of the redacted pinned files (`research/*`, `stitch-nextjs/docs/WORKFLOW_SPEC.md`) were re-pinned. Four provenance-protected report files (`experiments/foundation/java-*-results.json`, `integration/reports/foundation-tests.txt`, `integration/reports/test-results.json`) were deliberately left byte-identical so `application/source-provenance.json` stays unchanged; they were already published in the base branch.

No change to application code, the ledger bundle, the evaluator, genealogy, simulator, ML model, assistant rules, evidence integrity or recall logic.
