# PS10 performance and scalability: isolated implementation report

## Outcome

**Partial objective achieved.** Content-verified, non-authorizing bearing-lot impact retrieval is sub-second at100 and1000 motors on this machine. It is NOT sub-second at10000 at p95, and cold rebuild is never claimed as sub-second. No integrity shortcut was used to meet a timing target. Full release gates are not green: the frozen inventory intentionally rejects the added performance source files; source inventory integration requires separate review. No push, merge, new tag or deployment.

Starting HEAD was verified clean and exact `6709b0c6f521006cf6332caeecec6b08dbd44e84` (peeled manufacturing-demo-v1.2). Worktree `ps10-impact-performance`, branch `feature/ps10-performance`. Functional query code is committed in0343a3c572af466cf7bba96cdc1f13e7d82d6179; e4fd1d5 adds the historical replacement/correction test. Final delivery SHA accompanies this report. No other agent's changes were imported; no lifecycle branch merge/cherry-pick. The original frontend-v2 checkout and frozen tag were not rewritten or edited.

## Measurements

One read-only reader per dataset, full verification/index build first.21 warm query samples; p50/p95 use linear interpolation over sorted samples (21 samples: p95 is the second-highest). Ready JSON is a bounded immutable response cache, but EVERY request still serializes and SHA-256 hashes the entire SQLite snapshot plus registry digest. First request for a novel lot also constructs/encodes the response; its separate single-sample timing is not a percentile. No warm result is a persisted decision or a freshness proof.

| Motors | Native events | Original EPCIS documents | Database image MB (decimal) | Warm ready-JSON p50 ms | p95 ms | First lot JSON ms (n=1) | Cold verify/build s (n=1) | Missed / extra candidates | Missing / extra shipment links |
|---|---|---|---|---|---|---|---|---|---|
| 100 | 957 | 99 | 3.58 | 11.29 | 13.45 | 12.69 | 1.01 | 0 / 0 | 0 / 0 |
| 1,000 | 9,570 | 990 | 35.02 | 93.39 | 102.80 | 99.86 | 9.66 | 0 / 0 | 0 / 0 |
| 10,000 | 95,700 | 9,900 | 349.70 | 1050.28 | 1120.83 | 1198.08 | 127.64 | 0 / 0 | 0 / 0 |

Raw per-dataset metrics, response bytes, scenario counts, p50/p95/min/max and environment are in `benchmarks/n100.json`, `n1000.json`, `n10000.json`. Candidate counts:27/270/2700. No candidate or shipment-link discrepancy against the synthetic intent. Unknown/sighted, gap, empty-slot, double-installation, DE, NDE and historical replacement cases are retained. This is a positive-candidate/uncertainty oracle, not an engine clearance oracle.

The uncached dict+JSON method is also measured and disclosed in the same files; it includes deep copying the projected records and fresh JSON encoding every time. The ready-JSON method is `ImpactQuery.query_json`, returning immutable bytes after the same full input digest check. At10000 even ready JSON has p95 above1s; a best sample below1s is not treated as meeting the target.

### Hardware and conditions

AMD Ryzen 7 250 w/ Radeon 780M Graphics, 16 logical processors, 15.31 GiB physical RAM, Microsoft Windows 11 Home Single Language. CPython3.12.10, SQLite3.49.1, Node24.17.0, npm11.13.0. Pinned Chrome155.0.8059.84 is used for component browser verification, not the timed in-process impact query. Windows developer machine, no dedicated CPU, no forced OS cache flush; other processes may contend. Timings are local Python query/serialization timings, not network/browser rendering, physical ingestion, evaluator throughput or a portable performance SLA. Hardware raw metadata: `hardware.json`.


### Workload and truth

Eight hand-authored fixture intents, deterministic motor-index distribution; no production ground-truth/oracle enters the query. Prototypes use public frozen Manufacturing commands. Every target motor is provisioned through unchanged Ledger.register_motor and every captured document goes through unchanged Ledger.capture/decode/validation/hash-chain creation. No direct event/capture/hash insertion, disabled triggers or fake persisted verdicts in benchmark construction. The app_units membership row is fixture setup only.

To make10000 feasible the benchmark uses one explicitly authorized synthetic aggregator source and one multi-event EPCIS document per nonempty motor. Actor claims, references, separate producer times, DE/NDE positions, supplier/manufacturing/install/removal/shipment events remain. This is a valid supported ledger shape, NOT the shipped UI's one-document-per-event cadence or a distributed-factory authentication model. More documents, larger journals, unbounded histories, high uncertainty density and different capture/source distributions can cost more. The full-image key also hashes unrelated journal/policy tables, so real issued-decision archives may be much larger than these scaling fixtures. Do not generalize these numbers to them.

Fixture intent:5% DE hits,5% NDE hits,5% historical replacements,5% look-alike sightings,5% coverage gaps,1% unassembled motors,1% double installations; remaining73% clean nonmatches.26/260/2600 candidates have shipment claims; unassembled candidates have no recorded shipment. An unknown query lot conservatively returns the entire fleet. A recorded shipment is never a shipment authorization. No operational decisions are issued by this path, so no false-release or unnecessary-hold rate is claimed; candidate extras and misses are reported separately.

## Profile and smallest safe optimization

Existing PS10 audit scratch harness/results at `ps10-core-audit/research/ps10-core-audit` were inspected as reference, but they were untracked/unmerged and were not copied or imported. The shipped `application/checkpoint_benchmark.py` establishes the pre-existing verification/full-snapshot workload. Fresh profiling here is reproducible from the exact frozen tag; no dependence on that other worktree is needed.

`Ledger.watermark` and `Ledger.snapshot` both call `_verified_rows`. Each call rechecks original-document SHA, decoding/schema validation, native-to-wire equality, row identity and per-motor hash chain. `Manufacturing.snapshot/_snapshot` additionally prepares full-fleet decisions, comparison and read models. Fresh100-motor profile:400 `_verified_rows` calls consumed about6.05 cumulative seconds inside an8.33-second instrumented first snapshot (10.18 million calls). Profiling adds overhead: that8.33s is NOT an uninstrumented p95 or a like-for-like speedup claim. The unprofiled repeat and verified genealogy-only sweep are recorded separately in n100.json. `benchmarks/profile-100.txt` contains the30 highest cumulative entries.

1. Separate positive impact retrieval from full recall evaluation/read-model production. No new evaluator semantics or selective-release shortcut.
2. Build an in-memory inverted index ONLY after every motor passes the unchanged ledger watermark/snapshot verifier. Include every historical relationship, all slots, observation uncertainty and source/configuration evidence. No SQL predicate is allowed to pre-exclude a motor before integrity verification.
3. For every query, establish one SQLite read transaction and hash `Connection.serialize()`'s entire database image plus registry content. It includes WAL-visible committed pages, not just the main file; concurrent-commit tests verify snapshot linearization. Cache reuse requires cryptographically equal bytes. Counts, newest heads, file mtimes and PRAGMA data_version alone are not sufficient and are not used as trust proofs.
4. Any changed input makes the query unavailable until explicit rebuild. On rebuild retain an in-process high-water inventory/configuration/event-hash set; dropping known motors, rewriting provisioning or removing prior hashes is rejected. New legitimate append-only captures may extend it. No disk cache is trusted on restart.
5. Ready JSON is bounded to eight immutable payloads; it saves repeated deep copy/encoding but does NOT save the per-query full-image verification. Query object results are detached copies. No stale motor records or empty negative result are returned on failed proof.

The first row-digest experiment was slower, and a benchmark shipment-ID cloning defect was caught before accepting correctness. It was stopped/corrected, not scored as PASS; `exploratory-before.json` records the failures. Two early prototype-generation errors (missing work-order context and manufactured-identity mismatch) were fixed in the generator without weakening validation. `before-response-cache.json` preserves the correct10000 dict+JSON p95 of1.253s before the bounded JSON cache. Results were not tuned by deleting cases or changing expected shipment IDs to match a defect.

## API, contracts and unchanged safeguards

```python
from performance.impact_query import ImpactQuery, ImpactUnavailable

reader = ImpactQuery("factory.sqlite")  # opens EXISTING database mode=ro/query_only
try:
    reader.rebuild()  # cold complete verification; explicit operation, no trust promotion
    payload = reader.query_json("BR-204")  # bytes; full snapshot rehash every request
    # OR reader.query("BR-204") for a detached dict.
except ImpactUnavailable as exc:
    # Neutral code; never substitute an old response or an empty candidate list.
    print(exc.code)
finally:
    reader.close()
```

Response kind `CONSERVATIVE_LEDGER_IMPACT_NOT_A_RECALL_DECISION`; checkpoint and operational clearance are `NOT_ASSESSED`. Per motor: complete source watermark, evidence snapshot digest, matching event IDs/hashes/capture SHA, source IDs/sequences, occurrence/producer-record times, DE/NDE slot, uncertainty and observation evidence, and recorded shipment IDs/times backed by verified MOTOR_SHIPPED events. No fabricated trusted verification, release eligibility, policy verdict, notification obligation or current checkpoint state. No response is a RecallSnapshot or portable F5/F6 package.

Unknown registry/query identity includes ALL motors; it never implies no impact. Unresolved sightings are never installed or registered by the reader. Even a later reinstallation/correction retains historical evidence conservatively. Nonmatching omitted motors are NOT declared excluded, released or physically unexposed. This index must not be used to clear nonlisted motors, replace full applicable recall evaluation, resolve obligations or authorize shipments. Conservative over-inclusion of old or unrelated observations is intentional.

No existing tracked file changes: frontend, frozen evaluator, integration ledger, application, checkpoint/clearance code, shipment gate, F5 portable evidence, F6 federation, A7 and their tests are byte-for-byte the frozen baseline. No separately named A7 artifact was found in that tag; the zero-diff whole-baseline check is the basis for the no-A7-change statement, not certification of an unmerged implementation. Only new performance files and research documentation are added. Existing pinned source verification and baseline frozen-file comparison are included in validation. The focused shipment probe confirms a fresh assembled motor cannot use this query's output to ship without the ordinary trusted checkpoint/clearance workflow.

## Verification and required-gate status

Focused suite:19 tests. Covers direct exposure, unknown/near-match sightings, missing baseline, explicit unknown-lot full-fleet result, source/app-unit membership, rejection blocks, same-head/count raw tampering, changed native payload, configuration rewrite, rollback across rebuild, immutable results/bytes, late corrections/replacement history, registry edit, restart proof, sanitized errors, read-only operation and concurrency. `performance/test_impact_query.py` creates independent synthetic cases through frozen service APIs; no original test or fixture was edited. These are author-run tests, not a blinded external safety audit.

The ORIGINAL `ci/run_gates.py` was run unchanged and fails before A-K on unapproved tracked performance files. That failure is preserved in `required-gates.json`. **No frozen hashes/counts or workflow were relaxed or regenerated.** Separate `performance/run_validation.py` executes the unchanged underlying component commands with the pinned tools, exact original counts and process-exit checks, plus the new focused suite, source-provenance and unchanged-frozen-file check. Its output does not override the failed required summary. The first pass had missing-cryptography import errors for F5/F6 (the frozen workflow installs a second lock) and a foreign-owned4173 port block. Those exact failures are preserved in validation/first-attempt. Installing the already existing crypto lock fixes the environment; retry only failed/unexecuted components via --retry-incomplete. A test-only wrapper in performance/playwright.config.ts inherits the pinned CI configuration and every original assertion, moving only the shared server/base URL to4450. An ESM package marker in the performance test-wrapper folder is required to import the baseline CI configuration; the first CommonJS load failed before any test ran and is retained in first-attempt/playwright-config.txt. A retry-harness variable-shadowing defect failed before any checks and was corrected locally; no product/test assertion changed. It is not hosted CI or a release certification. The final component totals/failures are recorded in validation/components.json and the delivery summary.

### Final component results (all original assertions retained)

| Check | Result |
|---|---|
| Focused impact suite |19/19 passed|
| Original evaluator v1/v2/v3 |127/127 passed|
| Original integration |44/44 passed|
| Original application modules |257 passed across18 unchanged modules|
| F5 / F6 / F5-F6 integration (included above) |36 /34 /15 passed|
| Foundation |21/21 checks passed|
| Exporter / CI infrastructure |7 /7 passed|
| Frontend units / pinned-browser suite |378 /143 passed|
| Production build, typecheck, standards, snapshot export |PASS|
| Existing frozen-file hashes / source-provenance pins |405 /126 unchanged|
| Original required A-K wrapper |FAILED new-file inventory preflight; not overridden by component success|

The component summary has31 passed checks, no remaining component failure. The browser run uses unchanged tests on4450 with pinned Chrome155.0.8059.84;570.2 seconds. No browser test was disabled or skipped. First-attempt environment/import/port failures remain in validation/first-attempt. --retry-incomplete is a local evidence convenience for already executed checks on unchanged source, not permission for future release CI to trust a previous JSON file or skip tests. Future integration must run a fresh exact-commit required suite.

Reproduction (isolated Windows checkout at the reported commit):

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install --require-hashes -r ci/requirements-windows.lock -r ci/requirements-hackathon-crypto.lock
.venv/Scripts/python.exe ci/prepare.py
cd recall-ui
npm ci
cd ..
.venv/Scripts/python.exe -m unittest performance.test_impact_query -v
.venv/Scripts/python.exe -m performance.benchmark --sizes 100 1000 10000 --reps 21
.venv/Scripts/python.exe ci/run_gates.py  # expected fail-closed new-path inventory refusal
.venv/Scripts/python.exe -m performance.run_validation
```

Benchmark creates only synthetic temporary databases and removes completed runs. Successful output records all event/capture/candidate/shipment counts. Re-running intentionally replaces these research result files and is a new measurement, not an identical timing guarantee. Required/browser ports must be free; no other agent's server is stopped or reused. New source inventory and focused-gate integration are deferred to explicit owner integration/review.

## Limitations and integration risks

-10000-motor warm p95 remains above1s; first query and cold rebuild are also above target. Reported best samples do not override p95. No sub-second claim at that size.
- Long rebuild read transactions also retain a WAL snapshot; concurrent capture may increase WAL retention and memory/disk pressure.
- A cold restart or ANY database write (even unrelated policy/journal changes) invalidates the full-image proof. Under continuous capture, availability may be dominated by rebuilds. This is not yet a continuous-ingestion production solution.
- Verification is O(total database bytes) on EVERY query.349.7MB is serialized/hashed per10000-motor request, with transient memory plus the resident index and up to eight payloads. Query access is serialized by an instance lock; no parallel QPS/load SLA is established.
- SQLite serialize support is required. The read-only facade uses frozen Ledger methods without its mutating constructor and relies on that pinned implementation; future ledger changes require re-audit.
- Hash/chain verification proves consistency of recorded facts, not physical identity or independent authentication. Restart with a consistently rewritten/rolled-back archive cannot be detected by an empty in-process high-water mark. Existing independently protected checkpoint verification remains mandatory for operational use; the reader does not establish current checkpoint trust.
- No current/historical recall-policy evaluation, closure, clearance, notification or shipment authorization is performed. Conservative candidates cannot replace those functions. Histories/observations are deliberately over-included rather than silently cleared.
- The uncertainty union is a conservative investigation aid, not a complete duplicate of every v3 reason/completeness rule. Omitted motors still require the original applicable-recall evaluation and must never be cleared or removed from recall scope using this index. This performance work is NOT authorization for selective evaluation based on candidate omission.
- It is a library path, not a new HTTP/UX endpoint. Binding lifecycle, cache rebuild scheduling, budgets/backpressure, authorization, exact watermark labels and response-size limits needs a separately reviewed integration. No changes from feature/ps10-lifecycle were used.
- Required CI inventory has not approved these new files; no green overall gate claim. Production integration needs the new files/focused tests registered without modifying existing protected-source hashes or original assertions, then exact-commit required CI.

**Recommendation: retain the isolated candidate for review; REVISE for an all-scale sub-second or production-ready claim.** Consider a separately designed, authenticated incremental projection/checkpoint-bound index if10000 plus continuous capture requires sub-second service. Such a change needs explicit design review and lies outside this frozen-safeguard assignment. Do not trade away full input integrity, unknown/sighting inclusion or current-state semantics.

## Local delivery files

`performance/impact_query.py`: reader/query/JSON library. `performance/test_impact_query.py`:19 focused cases. `performance/benchmark.py`: reproducible fixture and measurements. `performance/run_validation.py`, `playwright.config.ts`, `package.json`: diagnostic test harness only. `change-inventory.json` lists every added path. `evidence-index.json` hashes the canonical Git bytes of this task's evidence (not a replacement source/trust baseline). No original tracked path is modified.
