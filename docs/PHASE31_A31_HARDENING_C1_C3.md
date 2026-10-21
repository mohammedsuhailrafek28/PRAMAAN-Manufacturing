# A31 safety hardening — C1–C3

## Identity, scope and ancestry

Repository: https://github.com/mohammedsuhailrafek28/PRAMAAN-Manufacturing

- Exact approved baseline: `ad7609873e0915eed6e1dd6bddd40d883e976034` (`fix/phase3-safety-remediation`).
- Hardening branch: `integration/phase31-a31-hardening`.
- Tested implementation commit: `903f37b8f06c572b19953e171b2176b09ebaf5e7`.
- Delivery is a documentation/evidence-only descendant; its exact SHA is returned in the delivery message rather than attempting to embed this report's own Git hash.
- Main at initial verification: `6e772e856aed7914c67e2a5e7e66bfb6fc0d27c0`.

The branch starts at the exact A31 SHA. Neither main nor Claude's remediation was merged. Original source SHAs and attribution remain in ancestry. Current main's merge commit is not an ancestor of this branch, although its tree equals the shared original Phase 3 tree. A future approved integration must explicitly review/test that ancestry; this task does not perform it.

No engine, fixture/oracle, foundation or integration source change; no new dependency; no MSME access; no Phase4/process-deviation implementation; no deployment, PR, main merge or settings changes. Only the hardening branch is eligible for the authorized push.

## C1 — external prefix commitment

**Before:** the local A31 head/schema marker catches partial deletion, but a consistent old DB, or joint table deletion plus schema reset, cannot be distinguished from an older/fresh archive without an independently retained reference.

**After — CONDITIONALLY SUPPORTED:** an explicit external anchor commits archive ID, sequence/head hash, sealed legacy history digest, policy digest, publication profile, hardening/obligation profile, all prefix publication records and pending obligations. Export uses RFC8785 canonical JSON and existing SHA256 digest machinery. The checksum detects corruption relative to its body; it is **not a signature** or source authentication.

`application.anchors.verify_anchor` requires the current hash-valid journal to contain the exact trusted sequence/hash, verifies archive/legacy identity and prefix publication/obligation commitments, and checks archived publication manifests/policy inputs. A valid extension is accepted. It rejects new resolution records beyond that prefix because this hardening profile authorizes no resolution workflow. Exact engine replay remains a separate regression gate; normal polling does not need to recompute every historical verdict.

An anchor made before any recall policy binds `None` and permits the first policy to be added during initial provisioning. Once a policy is anchored, a different policy digest fails verification and requires explicit owner review. The existing single immutable policy restriction remains unchanged. Neither initial provisioning nor exporting an anchor authenticates the policy author.

### Explicit command and enforcement points

Use an existing independently reviewed database. Export does not create a database implicitly. The owner must choose an external storage location whose custody is independently established:

```powershell
python -m application.anchors export --database .local/manufacturing.sqlite --anchor C:\owner-custody\checkpoint-001.json
python -m application.anchors verify --database .local/manufacturing.sqlite --anchor C:\owner-custody\checkpoint-001.json
python app.py --database .local/manufacturing.sqlite --trusted-anchor C:\owner-custody\checkpoint-001.json
```

Export evaluates/archives current supported application publications, then creates a NEW file exclusively; it refuses to overwrite a checkpoint. Successful export prints `EXPORTED_UNTRUSTED_UNTIL_OWNER_CUSTODY_ESTABLISHED`. To establish an empty synthetic database, use the existing explicit local service/demo seeding path first; do not invent an authenticated owner or treat a demo source as real factory identity.

`make_server(..., trusted_anchor=path)` explicitly loads an owner-supplied reference. The bytes are pinned for that server process; replacement or loss during the process fails verification. At every operational API request, `Manufacturing.snapshot(trusted_anchor=...)` verifies the prefix before publishing `VERIFIED_ANCHORED_SYNTHETIC` freshness. Mutation paths verify before capture as well. Failure returns unavailable/409, never an unanchored fallback.

Without an anchor, `/api/snapshot` is explicitly `HISTORICAL_UNANCHORED` with zero operational max-age. Bare decision/provenance read routes and operational commands are refused. The live UI rejects the historical envelope as current. Internal evaluator/publication APIs still return historical raw decisions for replay/tests; their `RELEASE_ELIGIBLE` field alone is not an operational authorization. This branch's enforcement boundary is the local application/API/UI, not the immutable evaluation kernel.

### Formal trust and availability limits

Let trusted checkpoint A bind archive identity I and journal prefix `(n,h)`. Verification succeeds only when the current archive proves the same prefix and committed state/inputs under the recorded profiles. An internally consistent archive with fewer than n records, a rewritten anchored prefix, or a different I fails. A later valid extension `(m>=n)` is not rejected merely because its current head differs.

- **TESTED:** old valid SQLite backup predating a newer hold/obligation checkpoint is rejected; deletion/reset cannot match the retained archive; valid extension/reopen succeeds.
- **CONDITIONALLY SUPPORTED:** rollback detection up to the supplied trusted checkpoint. A reference that predates a later hold cannot detect rollback of that **uncheckpointed** hold when the remaining DB still extends the old prefix. The operator must retain and advance the latest checkpoint independently. No claim of latest-state rollback protection is made without that operational discipline.
- **OUTSIDE TRUST MODEL:** attacker replaces both database and trusted reference; owner trusts a substituted reference at restart; host process/code or trusted reference custody compromised; attacker invents new uncheckpointed evidence; physical truth/issuer authentication. A writable JSON file or a different local path is not inherently trusted.
- **NOT IMPLEMENTED:** signed checkpoints, monotonic remote witness, automatic durable per-publication external checkpointing, secure storage, key/custody management or disaster recovery orchestration. These are production prerequisites, not simulated features.

Missing/unreadable reference is an availability failure for operational clearance. Reopening an archive without supplying any reference cannot establish rollback detection. Existing records are not rewritten to manufacture continuity. Retain old references; independently verify a prior checkpoint before accepting a successor, then restart explicitly against the newly custodied reference. The server deliberately does not hot-trust replacements.

## C2 — resolution remains disabled

**Before:** `Audit.resolve` accepted a caller-supplied callback as the authorization boundary. A permissive callback could grant a self-declared principal authority without authentication.

**After — TESTED:** `Audit.resolve` unconditionally raises `PermissionError`; no callback is executed, no mock identity is created, and there is no resolution HTTP endpoint. Compatibility calls are denied, including `authorize=lambda p: True`. Delivery stays `NOT_SENT`, acknowledgment remains unknown, and the UI labels obligations PENDING with resolution disabled.

Old `OBLIGATION_RESOLVED` entries are preserved verbatim as historical claims. Because this prototype has no independently authenticated resolution events, `Audit.outstanding` does not let those claims suppress a pending obligation. This can conservatively re-expose follow-up previously hidden by a legacy resolution claim. Original issued decisions/raw v1/v2/v3 semantics remain unchanged and replayable. The current obligation projection has its own hardening profile, bound by anchors; it does not retroactively certify legacy actors or rewrite journal history.

New evaluations, unrelated capture and process restart retain obligations. A raw database editor can rewrite an unprotected entire archive; C1 only protects independently checkpointed commitments. No authenticated future resolution workflow is implemented or authorized here.

## C3 — server-validated bounded freshness

**Before:** successful HTTP completion renewed a fresh five-second UI lease without examining the server's verification timestamp or max-age.

**After — TESTED within the prototype model:** both the backend datasource and App acceptance path check server freshness before displaying operational decisions. Checks require anchored status, UTC timestamp, positive max-age <=5 seconds, finite journal version and archive/head identity. Snapshot age consumes the lease; arrival does not reset its age. Timestamps older than max-age or more than one second in the future fail closed. The one-second future allowance accommodates timestamp precision/small clock skew, not assurance of synchronized devices.

Local monotonic request generations reject superseded responses. Browser timeout/body timeout remains four seconds; local lease timeout is capped at five seconds and invalidates earlier outstanding generations. Visibility changes revoke the lease; hidden tabs do not refresh it. Resume requires a new accepted snapshot. Capture invalidates current eligibility until its accepted result, and a superseded capture response cannot restore it.

Within a datasource session, archive change, sequence regression, same-sequence changed head, server timestamp regression, missing prior motor/event/source sequence, or decision version/identity regression fails closed. Existing event references/watermarks and publication versions provide continuity checks; the browser does not compute recall verdicts.

When verification is unavailable, action chips/current eligibility are hidden, controls disabled, and prior recorded decisions appear only in an explicitly historical disclosure. Recovery retries the live backend; it does not select fixtures. Full-snapshot polling notices an outside writer's new hold without relying on decision-head heartbeats.

**OUTSIDE TRUST MODEL:** malicious proxy or compromised backend can forge fresh timestamps/content; there is no cryptographic challenge/response, signed snapshot, or authenticated anti-replay transport protocol. A previously unseen, valid snapshot within the permitted five-second window may be accepted; the browser has no independently known newer state on its first load. Polling provides bounded verification, not an instantaneous release/ship interlock. Material arriving after the evaluated watermark requires reevaluation; the UI cannot predict it. Clock ambiguity fails closed and may reduce availability.

## Files changed and rationale

| Files | Purpose |
| --- | --- |
| application/anchors.py | Canonical external export/verification CLI, prefix/state/input binding and explicit file custody boundary |
| application/audit.py | Disable all new resolution; retain pending obligations despite legacy unauthenticated resolution claims |
| application/service.py | Anchor-qualified freshness and pending obligation read model; raw historical evaluator outputs retained |
| application/server.py | Owner-supplied anchor flag and operational API enforcement; no resolution endpoint |
| application/test_application.py | Explicit test-owned anchor provisioning for API tests |
| application/test_remediation.py | Replace prior callback-granted resolution expectation with mandatory denial; retain coverage |
| application/test_hardening.py | C1/C2 adversarial and CLI/HTTP regressions |
| application/verify.py | Add hardening test gate; write new evidence directory |
| recall-ui/src/data/freshness.ts | Server age/identity/version/watermark validation |
| recall-ui/src/data/RecallDataSource.ts | Acceptance checks and request generation ordering |
| recall-ui/src/App.tsx | Remaining-age lease, capture/resume ordering, historical fallback and pending labels |
| recall-ui/src/domain/types.ts | Freshness metadata type |
| recall-ui/tests/unit/backend-source.test.ts, freshness.test.ts | Stale/skew/regression/concurrent-response tests; valid explicit freshness on mutation mock |
| recall-ui/tests/browser_server.py, playwright.config.ts | Synthetic test-only anchor custody; controlled two-worker server load |
| recall-ui/tests/e2e/remediation.spec.ts | Existing standalone server tests use explicit synthetic anchors |
| recall-ui/tests/e2e/hardening.spec.ts | New replay, rollback, resume/timeout and external-writer browser cases |
| README.md, this report, phase31-hardening-validation/ | Usage, trust limits and preserved verification evidence |

No integration/foundation/engine byte inventory change. Existing historical screenshots/reports regenerated by tests are restored in the delivery worktree rather than overwriting prior evidence. New results are stored separately.

## Added regression coverage

C1 tests cover canonical CLI export/verify/no-overwrite, clean prefix, valid extension/reopen, old valid SQLite rollback, journal/head deletion plus user_version=0, truncation, locally hash-consistent journal/head rewrite, forged resolution extension, wrong archive/policy/head, tampered checksum, missing/replaced external file and unanchored HTTP enforcement.

- **Cryptographic commitment mismatch:** rewritten anchored prefix, wrong archive/policy/head/state, checksum corruption and rollback before the committed sequence.
- **Structural/version checks:** absent/truncated journal, count/head/genesis inconsistencies, disabled-resolution profile, missing/unreadable reference.
- **Custody assumption:** checksum recomputed after replacing both trusted reference and DB is not detected as an attack; the reference itself must already be trustworthy.

C2 tests deny missing/self-declared/permissive callback authority, require HTTP404 for attempted resolution, preserve follow-up across material changes/reopen, and replay historical entries while retaining pending follow-up.

C3 unit tests cover remaining-age lease, missing/unanchored/old/invalid/future metadata, journal/archive/evidence/decision regression and out-of-order concurrent responses. Browser tests cover old successful replay rejection/recovery, fresh timestamp plus lower journal version rejection, suspend/resume with delayed response, and outside-writer hold. Existing backend shutdown, body timeout, responsive long identifiers, keyboard and accessibility tests remain enabled.

## Verification evidence

Toolchain: Windows11 build26200; Python3.12.10, Node24.17.0, npm11.13.0, Git2.54.0.windows.1, Chrome155.0.8059.80. Python/npm locks unchanged. Playwright uses installed system Chrome, not an immutable browser image; production/CI browser pinning remains a limitation. External GS1 checkout is `6f71468231838e424bb5dfa836e006e8dc69615c`; verifier checks schema SHA256 `d5ca9b1cad2c403679d9b07fb768108142d73e1dd024198ed64774b56b62227b` and context `b5c7cc9367ab638ecb77feb0b9aea222a427d9740bf3dda1b183fc3d4390714f`.

Actual development checks:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r integration/requirements-validation.txt
npm.cmd ci --prefix recall-ui
.venv/Scripts/python.exe -m unittest application.test_hardening application.test_remediation -v
npm.cmd run build --prefix recall-ui
npm.cmd test --prefix recall-ui
.venv/Scripts/python.exe -m application.verify --gs1-checkout ../foundation-upstream/EPCIS
# After fixes, focused browser confirmation:
npm.cmd run test:e2e --prefix recall-ui -- tests/e2e/hardening.spec.ts
```

Failures are not concealed: the initial TypeScript build rejected optional version arithmetic; fixed with explicit fail-closed type checks. The initial full browser run had 4 failures/25 passes: timed-out requests under parallel local-server load. After reducing repeated historical replay in anchor checking (retaining prefix/input checks) and bounding workers to2, the next browser run had 1 failure/28 passes: the new disabled-control assertion targeted a collapsed capture panel. The test now opens it. Focused four-case browser rerun passed. These initial failures are retained as separate logs; none was skipped or converted to PASS. An initial local clone command used the wrong relative source path and failed before creating a clone; the corrected command below succeeded.

Final clean-clone command sequence (fresh venv/npm, shallow local Git pack transport, no shared objects/worktree dependencies):

```powershell
# From Manufacturing parent directory:
git clone --no-local --depth 1 --single-branch --branch integration/phase31-a31-hardening phase31-a31-hardening phase31-a31-hardening-clean
Set-Location phase31-a31-hardening-clean
git rev-parse HEAD
git rev-parse --is-shallow-repository
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r integration/requirements-validation.txt
npm.cmd ci --prefix recall-ui
.venv/Scripts/python.exe -m application.verify --gs1-checkout ../foundation-upstream/EPCIS
```

**TESTED: final complete clean-clone application.verify exit 0.** Fresh Git pack/shallow clone at 903f37b, fresh venv/npm installation, source diff after verification empty. The original engine/foundation originating commit objects are absent, and provenance still passes. Machine-readable results: [phase31-results.json](phase31-hardening-validation/phase31-results.json), [clean-clone proof](phase31-hardening-validation/clean-clone-proof.json), [full verifier output](phase31-hardening-validation/clean-clone-verifier.txt).

| Required gate | Final actual result |
| --- | --- |
| Pinned engine | 127 passed |
| Foundation | 21 interoperability checks passed |
| Integration | 44 passed |
| Application | 7 passed; 9.648s command time |
| A31 remediation | 16 passed; 19.920s |
| C1–C3 hardening | 13 passed; 9.918s |
| Exporter | 7 passed; 0.623s |
| Snapshot check | passed; 0.283s |
| Vitest | 33 passed; 4.946s |
| TypeScript + production build | passed; 3.280s |
| Playwright, including accessibility/responsive and 4 new cases | 29 passed; 45.167s command time |
| External pinned GS1 | 58 generated documents schema-valid; 19 retained events in 2 documents schema + JSON-LD roundtrip valid |
| Original content provenance | 126 files; engine, foundation and integration unchanged |
| Clean-clone full verifier | exit0; no source changes |

Retained synthetic safety: 12/12 behavior agreement, zero false releases among 6 unsafe cases, 3 unnecessary holds among 6 safe cases. Expanded synthetic safety: 25/25 agreement, **zero false releases among 14 unsafe cases**, **3 unnecessary holds among 11 safe cases**. These authored datasets are separate; do not combine them into a population safety rate or factory certification. The new anchor/freshness tests assert specific invariants rather than manufacturing ground-truth rates.

Individual logs, new adversarial tests and both failed-run logs are preserved in `phase31-hardening-validation/`. A development focused run additionally passed all 4 new browser scenarios. No failure was disabled or hidden to obtain the final green run.

## Migration and production boundaries

There is no database migration rewriting old records. Existing A31 archives retain archive IDs, original publications and evaluator semantics. The pending-obligation projection becomes more conservative for legacy resolution claims; a new current publication may therefore be issued while its old issued versions remain intact. Old undeclared recall scope still blocks live clearance. An external anchor must be reviewed/established before enabling operational mode; do not silently bootstrap it from a suspicious restored archive.

Creating a reference is not evidence the underlying records were correct. For real operations, owner-managed custody, checkpoint advancement/recovery and an independently authenticated resolution protocol remain required. A complete code/DB/reference compromise, arbitrary forged proxy responses, physical assurance, real supplier/station identity, signed evidence, external delivery/recipient acknowledgment, high-load guarantees and power-loss recovery certification are **NOT TESTED / OUTSIDE TRUST MODEL**, as applicable.

## Independent review checklist for Claude

- Confirm exact baseline, tested implementation and final documentation-only descendant; verify immutable source inventories and absence of main/competing merges.
- Reproduce old DB rollback against a NEWER trusted checkpoint; contrast rollback only within an uncheckpointed extension. Do not claim the latter is detected.
- Challenge schema reset, locally valid head/journal rewrite, forged resolution, archive mismatch, missing/replaced reference and initial null-policy anchor behavior.
- Confirm no public callback/HTTP path can resolve; legacy claims remain byte-preserved but cannot clear pending follow-up.
- Replay old raw semantics/publications unchanged; inspect hardening-profile commitment and pending projection compatibility.
- Inject stale/ambiguous/future metadata, old journal/version/watermarks, overlapping request generations and process restart; verify controls and release explanations remain hidden without current verification.
- Challenge browser suspension and network recovery; do not mistake timestamp checks for cryptographic proxy protection.
- Run every gate below from a fresh clone; review failed-run logs as well as final green evidence.

## Readiness

C1 is **CONDITIONALLY SUPPORTED** under independently established, current checkpoint custody; automatic authenticated latest-state anchoring is not implemented. C2 is disabled by design and C3 supplies bounded validation, not arbitrary anti-replay protection. The report makes no factory certification claim.

Recommendation is limited to independent review of this isolated hardening branch after complete clean-clone gates pass. No approval to integrate, merge, deploy, create a PR, change protections or begin other features is implied. Stop after the authorized branch push.
