# Unified candidate — integration handoff

Design base: `d90306c07b52b839ece5296d7cd4869f55a3bd4d` (approved frozen Batch 3). Reviewed compatibility source: `93f31f9366afba098c9d320f621ee5c793f535f0`. Both source worktrees were clean at initial inspection. New branch: `integration/ps10-unified-candidate`, new worktree `ps10-unified-candidate`. No motion-branch changes are incorporated.

## Selective changes

Exactly nine runtime files differ from the design base: trace GET proxy allowlist; passport machining/QC claim projection; bounded disconnected graph; two scoped graph containment rules and genealogy class/SVG minimum width; dynamic motor/event labels in Recall, Performance, Daily Report and PDF. Recall retains its approved `.inv` wrapper; Passport and Performance retain `.ops`, and all approved design CSS remains byte-identical apart from the two reviewed additive containment rules. No evaluator/backend/import/ledger/checkpoint/shipment source change. EDA, Resolution Trail, report calculations, export verification, typography, spacing and animations are preserved.

Engineering-only files selectively carried from compatibility source: `compatibility/`, `review2/`, `stitch-nextjs/tests/`, `stitch-nextjs/tsconfig.compat.json`, `recall-ui/vitest.unified.config.ts`. Two test-only extensions create an explicit synthetic successor checkpoint and characterize the existing history-cache mismatch. No old branch merge or cherry-pick, database copy from live services, or source fixture modification.

## Confirmed evidence-history consistency blocker

`stitch-nextjs/src/dash/data.tsx:useMotorResource` caches by `${kind}:${motor}` and its effect has no evidence watermark dependency. A real same-archive fixture is captured, evaluated and checkpointed; one additional observation is then captured in an owned test copy, reevaluated, and an explicitly simulated successor is chain-verified. With the component mounted, the shared snapshot accepts the newer current decision, but the same-motor resource still shows its previous decision ID and has issued only one history GET. `compatibility/tests/unified.test.tsx:ConsistencyProbe` reproduces this without inventing evaluator results or modifying production code.

`Trail.tsx` and Recall reasoning/history consume that resource; Passport/Genealogy provenance and lifecycle requests share the cache mechanism. Thus the application cannot yet claim atomic/coherent live history across updates. This is an existing frontend risk, not introduced by the compatibility patch. Withholding still wins when the common gate becomes noncurrent; no test establishes an unauthorized shipment or backend clearance. Do not infer safety of every possible response race from that fact: subresource response metadata is not independently joined to the snapshot watermark. A late-response/epoch mismatch must be addressed in a separately approved change.

Smallest proposed remediation for approval: bind resources to archive and evidence/publication watermark; invalidate on change and reject late responses from a prior epoch; compare decision/checkpoint metadata before presenting a resource as current. Lifecycle/provenance may need a backend envelope to provide a comparable watermark (provenance currently returns an array). Keep this distinct from the unchanged five-second lease and fail-closed evaluator. No such remediation is implemented here.

For a constrained read-only synthetic demonstration only, select one unchanged backend archive before loading and fully reload the browser following any controlled write, checkpoint activation or server restart. This is an explicit operational limitation, not closure of the defect. Do not present unrestricted live corrective updates as verified.

## Validation

Reproduce from this worktree with existing pinned Python lockfiles, both npm lockfiles and verified CI artifacts:

```
.venv/Scripts/python.exe ci/prepare.py
.venv/Scripts/python.exe ci/run_gates.py
.venv/Scripts/python.exe -B -m compatibility.run
npm.cmd run typecheck --prefix stitch-nextjs
npm.cmd run build --prefix stitch-nextjs
python -B -m compatibility.verify_pdfs --render
```

The compatibility runner starts only owned temporary backends on ephemeral ports, never Next or a unified frontend preview. It keeps the imported nine-motor/47-event dataset and original five-motor/58-event dataset independent. Its 48-event same-archive successor is an owned test-only extension of manufacturing evidence, not a mixture of datasets. Local demo references are not independent protected custody or release authorization.

Actual release-run logs and statuses are retained in `.local/unified-candidate/` and `.tmp-ci-results/`, bound to the source commit. A separate non-browser runner records executable gates independently if the unchanged A-K preflight is blocked by occupied fixed browser ports. It never reports full A-K PASS without gate I. Do not stop existing processes or weaken the port isolation check. PDF QA dependencies are test tooling only.

## Inventory

See `CI_INVENTORY_CHANGE_UNIFIED_CANDIDATE.md`. The inherited old inventory is extended explicitly; all original 449 frozen pins and 126 evaluator/foundation/integration provenance pins must remain unchanged. Test counts and original runner assertions are unchanged. Registration does not substitute for passing release gates.

## Proposed launch — NOT STARTED

After owner approval and final acceptance:

1. Verify availability of 3010 and 4420 without stopping other services; leave 3002–3006, 4400, 4411 unchanged.
2. Use this isolated worktree and choose a new empty data directory. Run `.venv/Scripts/python.exe -B -m review2.demo prepare --workdir .local/unified-manufacturing`. This imports manufacturing records and adds the two labelled native claims (47 events); repeating an import is idempotent. Do not seed the 58-event fixture into this database.
3. Explicit synthetic demo only: `.venv/Scripts/python.exe -B -m review2.demo serve --workdir .local/unified-manufacturing --port 4420 --demo-reference-only`. For independently protected operation, use the existing reviewed custody/activation process instead; never promote a local candidate implicitly.
4. Set `$env:PRAMAAN_API_URL='http://127.0.0.1:4420'` in the new frontend process, build under that explicit environment, then `npm.cmd run start --prefix stitch-nextjs -- --hostname 127.0.0.1 --port 3010`. Do not fall back to 4411 or hot-swap datasets. All routes use the same selected ledger and DataProvider.
5. Browser acceptance: all nine surfaces, correct claims/provenance, disconnected motors, affected/unresolved findings, holds despite QC PASS, replacement/history, trace links, source/ingestion report days and fresh PDF export; desktop/mobile graph containment and approved visual design. Verify prefix/unanchored/expired/invalid/unavailable withdrawal and concurrent update handling. The confirmed history issue must be resolved or demonstration scope explicitly approved before claiming live-update readiness.
6. Run the five-motor regression separately in temporary test stores/fresh session, never blending source registries/anchors/events. On completion stop only the new owned processes; no existing service changes.

Recommendation: review candidate only; full release qualification, history consistency remediation and unified preview remain gated by the recorded evidence and owner approval. No main merge, push, deployment or preview is authorized by creation of this candidate.
