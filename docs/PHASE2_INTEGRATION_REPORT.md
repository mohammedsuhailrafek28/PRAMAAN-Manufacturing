# Phase 2: EPCIS and recall-engine integration

Date: 21 October 2026. Delivery branch: `feature/epcis-recall-integration`.

**GO for this bounded local end-to-end integration. REVISE before factory or
production use.** No safety rule was weakened and no merge/deployment occurred.

## Baselines and isolation

The branch starts at engine v3 `1620ed3a8c78d7ea41063107666d9482fd93dff9` and
cherry-picks the research changes from `bc68dc0ca54f4e35b7e14c6ad09f7af28ab3b00c`
as `ded1f38`. Both pinned workstreams passed independently before implementation:
127 engine tests and 21 foundation checks. [Baseline gate](PHASE2_BASELINE.md)
records contract differences and their conservative handling.

Worktree: `PRAMAAN-Manufacturing/phase2-integration`. The safety, foundation and
active UI worktrees were not written to. MSME PRAMAAN was not accessed. Engine
and foundation experiment trees still exactly match their respective pinned
commits. All Phase 2 implementation is in new files under `integration/`; no
existing engine, fixture, oracle, UI, API or migration file is modified.

## What was built

| New files | Purpose |
|---|---|
| `integration/pramaan_integration/profile.py` | Self-authored restricted EPCIS-compatible profile; lossless native-envelope mapping; strict timestamps, identity, references and core/trace consistency |
| `integration/pramaan_integration/ledger.py` | Durable SQLite capture, trusted provisioned configuration, source/session permissions, append-only evidence, historical genealogy, explicit snapshots and persisted decision lifecycle |
| `integration/pramaan_integration/engine_bridge.py` | Imports the actual in-tree v3 package and calls its evaluator/lifecycle/replay; no duplicated decision logic |
| `integration/integration_tests/` | 44 integration tests and authored synthetic input generator; never imported by production decision code |
| `integration/run_validation.py` | Reproducible test/demo/safety/performance harness; synthetic truth lives here, outside the engine and adapter |
| `integration/requirements*`, `integration/README.md` | Pinned runtime and separate validation dependencies; operating contract and reproduction commands |
| `integration/reports/` | Full test transcripts and machine-readable experimental evidence |
| `docs/PHASE2_BASELINE.md`, this file | Contract gate, results, methodology and blockers |

The production runtime reuses `jsonschema==4.26.0`, `rfc8785==0.1.4`, and Python's
SQLite/hash/time libraries. It uses no blocked upstream source, OpenEPCIS service,
Maven dependency, Java service, Trace-X or Industry Core Hub installation.

## End-to-end demonstration

[demo.json](../integration/reports/demo.json) records the actual decisions,
native input, policy, coverage, source watermarks, event evidence and digests.
The file-backed SQLite database is closed and reopened to verify reproducibility.

1. Provision motor `M-DEMO` with explicit DE/NDE position bindings, five
   motor-scoped source capabilities, capture sessions and a v3 coverage policy.
   Position bindings identify possible slots; they do not assert their contents.
2. Capture BUILD open, affected DE bearing installation, distinct-lot NDE
   installation and BUILD close as EPCIS-compatible documents.
3. Query the ledger: two component→motor relationships, with slot and source
   provenance. The actual v3 evaluator returns `AFFECTED` / `RECALL_HOLD`, reason
   `AFFECTED_LOT_INSTALLED`, recall policy `RECALL-DEMO/P1`, version 1.
4. Capture REWORK open, source/actor-authorized removal referencing the original
   DE installation, unaffected replacement and REWORK close.
5. Query the same ledger: four historical association claims, including removal
   and replacement; no original event is deleted.
6. Invoke actual `evaluate_series` under `Config.v3()`. It returns
   `EXCLUDED_WITH_EVIDENCE` / `RELEASE_ELIGIBLE`, reason
   `REPLACED_WITH_UNAFFECTED_LOT`, engine `phase1.2-untrusted-observation`, profile
   `UNTRUSTED_OBSERVATION_V3`. It supersedes the prior decision and cites the
   supporting event IDs. No outcome is hardcoded in integration code.
7. Reopen the database and reproduce the decision series exactly; replay both
   recorded snapshots under their stored semantics.

RELEASE_ELIGIBLE is the engine's evidence finding/action pairing, not a physical
release command. No action is executed by this integration.

## Safety and contract preservation

The adapter preserves original event IDs, supersession and removal references;
motor/position; part, lot and optional serial; source ID/sequence; producer
occurred/recorded times separately from upstream repository recordTime and local
receipt time; work orders, capture-session identity, evidence refs, verifier
method/actor, provisional/derived-evidence metadata and identity granularity.

Trusted source/actor/event capabilities and coverage are provisioned outside wire
events. A permitted handheld is not promoted to a trusted verifier. Caller
configuration requires conservative v3 settings and both slot bindings; a missing
sibling record remains UNKNOWN and a candidate for ambiguous attribution.

Invalid/contradictory representations, bad timestamps, sequence holes, unknown
references, unauthorized actors and hash/content changes reject atomically and
persist a motor block. A rejected event cannot disappear while an older exclusion
remains usable. Domain-conflict claims such as double installation remain immutable
evidence and the engine holds them. Independent verification can resolve current
state; labels or derived checks cannot independently clear ambiguity.

Every decision uses a complete motor snapshot, never only component-query results.
Full watermarks retain explicit zero entries; a requested prefix with no source
rows is rejected. Watermarks cannot hide referenced evidence or regress the
standing decision history. Decision issuance is serialized with capture/rejection
writes. Persisted runs preserve withdrawal, precautionary hold and notification
obligations across separate calls and restarts. Modified/unissued replay bundles
and policy/configuration/evidence drift are refused.

## Verification results

Full command records and exit statuses: [test-results.json](../integration/reports/test-results.json).

| Gate | Result | Evidence |
|---|---|---|
| Existing v1/v2/v3 engine tests | **127/127 pass**, including the mutation gate | [engine-tests.txt](../integration/reports/engine-tests.txt) |
| Legacy/v2/v3 oracle agreement under their own profiles | **25/25, 35/35, 54/54** | Existing engine comparison tests and pinned engine reports |
| Existing foundation checks | **21/21 pass**, unchanged source | [foundation-results.json](../integration/reports/foundation-results.json) |
| New integration tests | **44/44 pass** | [integration-tests.txt](../integration/reports/integration-tests.txt) |
| New profile vs external GS1 schema and JSON-LD trace round-trip | **2 documents / 19 events pass** | [external-conformance.json](../integration/reports/external-conformance.json) |
| Engine/foundation source preservation | Both trees unchanged | Recorded Git-diff checks in test-results.json |

The new tests cover every requested regression: clean replacement, missing
baseline, double installation, same-lot ambiguity, independent verification,
untrusted affected observation, session gaps, late correction withdrawal,
incorrect sequences, invalid timestamps and changed content/hash. Additional
checks cover unknown sibling slots, label-only evidence, authorized access
evidence, uncertain clocks, derived verifications, actor spoofing, idempotency,
atomic rollback, durable rejection, storage tampering and decision replay.
An additional P2 flow preserves `inspectorQualifiedFor` and reaches the actual
evaluator's `DAMAGE_INSPECTION_PASSED` result after independent slot verification.

`pip-audit` 2.10.1 found no known vulnerabilities in the six explicitly pinned
runtime packages; [runtime-dependency-audit.json](../integration/reports/runtime-dependency-audit.json)
records the result. The scan used `--no-deps --disable-pip` against
`integration/requirements.lock`; this is not a complete application, operating
system or future-version security clearance. Pins are not wheel hashes.

External GS1 schema/context files remain outside the repository. The exact
digests are recorded. This verifies the generated subset, not complete EPCIS
conformance, all semantic-model combinations or a running EPCIS service.

## Behavioral agreement versus synthetic safety

[safety.json](../integration/reports/safety.json) contains **12 newly authored P1
histories**, expected behavior and separate physical-truth labels. The adapter and
engine cannot read those truth labels.

* Behavioral agreement: **12/12** expected findings.
* Synthetic unsafe histories: **6**; false releases: **0/6**.
* Synthetic safe histories: **6**; unnecessary holds: **3/6**.
* The three safe motors held are: missing baseline, correct same-lot removal with
  indistinguishable records, and a false untrusted affected-bearing observation.
* The wrong-slot and correct same-lot scenarios intentionally have equivalent
  evidence content apart from identifiers. Both are held until independent
  evidence distinguishes them. True and false untrusted observations likewise
  cannot be distinguished from the claims alone.

The original engine's synthetic ground-truth evaluation is separate: v3 has zero
false releases there too, but its case set and unnecessary-hold counts are not
combined with this integration dataset. Neither dataset establishes factory-level
correctness, regulatory conformity or a measured real-world failure rate.

## Performance and methodology

[performance.json](../integration/reports/performance.json) records Python
3.12.10, SQLite 3.49.1, Windows 11; file-backed SQLite with WAL; deterministic
**100 motors × 8 events = 800 captures/events**, four genealogy relationships per
motor. Each motor uses explicit motor-scoped producer streams. No random seed or
external dataset is involved.

After 20 warm-up iterations, 300 samples per operation run round-robin over the
100 motors in one process. Timings use `perf_counter_ns`; reported percentile
indices are floor((N−1)×p). Genealogy and decision timings include profile,
original-byte, derived-record and hash-chain validation; decisions also include
the actual engine/lifecycle and persisted-run handling. Cached-engine timings
exclude database retrieval/validation. There are no concurrent writes, cold-cache
claims, network calls or load-generation clients.

| Operation | p50 ms | p95 ms | p99 ms |
|---|---:|---:|---:|
| Validated genealogy query | 5.7193 | 10.3078 | 14.5919 |
| Validated end-to-end decision | 7.2937 | 12.8824 | 18.2887 |
| Actual v3 evaluator, cached native input | 0.3500 | 0.6929 | 1.0173 |

Synthetic provisioning/capture took 4.128 seconds on this run. All 300 measured
decision queries returned their expected clean-history finding; query cardinality
was checked. Measurements describe this small warm local workload only. Genealogy
validation currently scans a motor's full history; decision-run replay grows with
recorded horizons. Large histories, retention and concurrent factory traffic need
separate profiling before optimization or production sizing.

## Remaining integration blockers

1. **Source and clock authentication:** provisioned local capabilities and session
   flags are not credentials, signatures, device attestation or proven clock sync.
   The transport digest detects content changes; it does not authenticate a sender.
2. **Real station sequence model:** this slice requires motor-scoped streams.
   Global factory source sequences cannot be renumbered locally; define a complete
   cross-motor evidence/export contract before using them.
3. **Rejected-evidence reconciliation:** durable rejection blocks have no automatic
   unblock path. A reviewed reconciliation/resubmission process is needed; silently
   clearing a block is prohibited. No release is emitted for blocked captures.
4. **Profile breadth:** whole-second UTC, bearing slots DE/NDE and this private
   identity namespace are the supported subset. Arbitrary GS1 aliases, fractional
   or offset timestamps, empty-slot verification, quantities, transformations,
   split/merge and general EPCIS subscriptions remain outside scope.
5. **Physical assurance:** same-lot ambiguity, verifier collusion, source/clock
   trust and prototype timing assumptions remain the v3 engine's stated limits.
   A safe synthetic case can correctly remain held for insufficient evidence.
6. **Production integrity/operations:** hashes and SQLite triggers do not defeat
   an administrator rewriting the whole database and recomputing hashes. External
   anchoring, key management, authorization services, backup/recovery, multi-process
   concurrency/load testing and data-retention policy remain unverified.
7. **Interoperability scope:** no full OpenEPCIS repository was started. This is
   real local ledger/evaluator integration with external schema/JSON-LD checks,
   not demonstrated external repository or partner-dataspace interoperability.
8. **UI boundary:** no active UI code or API was changed. The CLI/library returns
   evidence-backed bundles, but a later approved API/UI integration must preserve
   snapshot horizon, blocking and replay semantics.

**Recommendation: GO for review/demo of this local slice; REVISE before expanding
scope or deployment.** No merge, deployment, full architecture freeze or UI
integration is performed by this delivery.
