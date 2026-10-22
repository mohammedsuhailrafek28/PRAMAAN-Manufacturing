# Phase 3.1 CI and release gates

## Status and boundaries

Repository: https://github.com/mohammedsuhailrafek28/PRAMAAN-Manufacturing

Frozen audited implementation: `integration/phase31-a31-hardening@f9282101159b6b6806974848d7c351999098d792`. Approved earlier A31 baseline: `ad7609873e0915eed6e1dd6bddd40d883e976034`. Main verified at task start: `6e772e856aed7914c67e2a5e7e66bfb6fc0d27c0`.

Infrastructure branch: `infra/phase31-ci-gates`, created directly from exact f928210. Initial CI implementation commit: `25cbb3ad4d2661846f0e59b090d5458259390dc4`. Exact final delivery SHA is supplied in the delivery message; documentation cannot embed its own commit hash.

This branch adds only `.github/workflows/`, `ci/` verification tooling and CI/release documentation. It changes no safety implementation, evaluator, fixture/oracle, foundation/integration logic, original remediation branch, hardening branch or main. It creates no PR, performs no integration operation and changes no repository settings. Process-Deviation/Phase4 work and MSME are untouched.

**Local verification is not GitHub Actions verification, independent safety approval, operational custody or factory certification.** Claude's exact-f928210 review and owner approval remain required. A workflow's existence does not establish a passing required check.

## Workflow architecture

Workflow: **Phase 3.1 release gates**, `.github/workflows/phase31-release-gates.yml`.

Triggers:

- Pull requests targeting main, including draft creation/synchronization and later ready-for-review updates.
- Pushes to `infra/phase31-ci-gates`, `integration/phase3-reviewed` and main.
- No path-filter skips, `pull_request_target`, deployment, PR approval or PR creation.

Stable check/job names intended for later owner configuration:

1. **Phase 3.1 verification (Windows)** — one fresh Windows2025 environment executes all A–K prerequisites/gates sequentially, with logs per gate.
2. **Phase 3.1 required gates** — always-run dependent summary, succeeds only when the entire verification job succeeded. Failed, cancelled or skipped verification cannot become a green summary.

A single verification job avoids sharing live databases/ports or pretending a matrix job's missing dependencies passed. Each command propagates nonzero exit, has a timeout, and records its actual invocation. Test counts are checked against the frozen reviewed baseline, so zero discovered tests is not success. Missing artifacts/tools or hash mismatches fail, not warn. Subsequent gates after a failure are unexecuted, not passed.

The job uses read-only repository permissions, no privileged secret, no checkout credentials persisted and no permission to approve PRs. Official Actions are pinned to full immutable SHAs. Evidence upload runs on success/failure and retains the runner summary, logs and failure traces for14 days. Concurrency cancels superseded runs; cancellation is not PASS.

## Pinning and prerequisites

| Input | Pin/verification |
| --- | --- |
| CPython | 3.12.10 x64; runner rejects any other version |
| Node | 24.17.0; runner checks exact version |
| npm | 11.13.0; runner checks exact version rather than silently accepting another bundled npm |
| Python wheels | `ci/requirements-windows.lock`, exact existing validation closure plus CI-only PyYAML6.0.3, per-wheel SHA256, binary-only and `--require-hashes` |
| npm packages | Frozen original package-lock.json, mandatory SHA512 integrity per package; `npm ci --ignore-scripts --no-audit --no-fund` avoids unchecked dependency install-script downloads |
| Chrome for Testing | 155.0.8059.84 win64, archive SHA256 `507f2a031441d10c62b5e3d4e863f09ac1198a571c1419976cbd8387f639afde` |
| GS1 | Official gs1/EPCIS commit `6f71468231838e424bb5dfa836e006e8dc69615c`, detached checkout plus both existing schema/context byte hashes |
| Frozen source | `ci/frozen-source.json`, all non-documentation files from f928210; original application 126-file provenance verifier also runs |
| Actions checkout v6 | `d23441a48e516b6c34aea4fa41551a30e30af803` |
| Actions setup-python v6 | `ece7cb06caefa5fff74198d8649806c4678c61a1` |
| Actions setup-node v6 | `249970729cb0ef3589644e2896645e5dc5ba9c38` |
| Actions upload-artifact v6 | `b7c566a772e6b6bfb58ed0dc250532a479d7789f` |

Major-version tags were resolved against official GitHub repositories when authoring, but the workflow uses their SHA values, not movable tags. Python wheel pins were obtained from public PyPI; no wheels/browsers are vendored. The exact Google artifact URL and GS1 hashes are in `ci/pins.json`. The browser version was selected from the official [Chrome for Testing catalog](https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json); previous system Chrome155.0.8059.80 is not a published CfT entry. A newer reviewed pin must be explicitly tested before updating.

Hashes establish integrity relative to reviewed pins; they are not vendor signatures or independent attestation of every download. The pin files/tooling themselves require owner review. Hosted Windows images, underlying OS patches and public download availability remain infrastructure dependencies; this is not bit-for-bit VM reproducibility. Setup Actions provide their own pinned-version installation/manifest checks. The workflow needs no custom credentials or privileged secrets.

The frozen product Playwright config selects system `channel:chrome`. To avoid modifying that audited file or relying on a runner's mutable Chrome, `ci/playwright.config.ts` imports its tests, worker count, fixtures and server setup, overriding only browser executable selection, explicit config-relative paths and CI trace output location. The ZIP digest is checked before every extraction and actual launched browser version is checked. Missing pinned browser is fatal; there is no system-Chrome fallback.

`application.verify` bundles its original system-Chrome invocation. CI therefore runs the same underlying gates explicitly, with the CI-only browser wrapper. It does not patch/monkey-patch the product verifier, change product config or suppress assertions. `ci/standards.py` calls the existing external_conformance/synthetic helpers and reproduces the verifier's live seeded-document schema loop. The full frozen product verifier's earlier hardening evidence remains separate; this task's new evidence is for these CI commands.

## Exact local and hosted command sequence

Run from a new shallow checkout on Windows x64 with the pinned Python/Node/npm. Do not reuse an existing database or live server. Port4173 and standalone test ports4182–4184 must be free; the runner refuses to take over existing listeners.

```powershell
$env:PYTHONUTF8='1'
$env:PIP_DISABLE_PIP_VERSION_CHECK='1'
$env:FORCE_COLOR='0'
$env:CI='true'
python -m venv .venv
# Fail on nonzero exit after EACH native command, as the workflow does.
.venv/Scripts/python.exe -m pip install --index-url https://pypi.org/simple --only-binary=:all: --require-hashes -r ci/requirements-windows.lock
npm.cmd ci --ignore-scripts --no-audit --no-fund --prefix recall-ui
.venv/Scripts/python.exe ci/prepare.py
.venv/Scripts/python.exe ci/run_gates.py
```

`prepare.py` downloads the exact browser artifact, verifies SHA256, safely extracts it, and independently fetches/checks out the exact GS1 SHA. An existing cached ZIP may be reused only after its digest matches; an extracted executable is regenerated from it. Existing wrong/corrupt prerequisites are not silently replaced to hide failure. No mutable GS1 HEAD/tag is consulted at runtime.

Runner command mapping (all outputs in `.tmp-ci-results/`):

| Gate | Underlying command/check |
| --- | --- |
| K, before/after | Full frozen non-doc inventory plus `application.provenance.verify(ROOT)`; reject unapproved tracked paths and missing/changed reviewed files |
| Infrastructure | `python -m unittest discover -s ci -p test_*.py -v` (4 tests) |
| A | In recall-engine: `python -m unittest discover -s tests -t . -v` (127) |
| B | `python experiments/foundation/interop.py --gs1-checkout <pinned> --output <results>/foundation.json` (all21 true) |
| C | In integration: `python -m unittest discover -s integration_tests -t . -v` (44) |
| D | `python -m unittest application.test_application -v` (7), `application.test_remediation` (16), `application.test_hardening` (13) |
| E/J | `python ci/standards.py <pinned-gs1>`: existing synthetic safety, existing GS1 conformance, seeded live-document validation |
| F | `python -m unittest discover -s recall-ui/tests -p test_*.py -v` (7); `python recall-ui/tools/export_snapshot.py --check` |
| G | In recall-ui: `npm run typecheck`, `npm run build` |
| H | In recall-ui: `npm test` (33) |
| I | Launched version check, then in recall-ui: `npm run test:e2e -- --config <absolute-ci-config>` (29) |

The runner sets `PRAMAAN_CI_CHROME` itself only after prerequisite checks. Its final summary records commit, unique invocation, versions, every completed gate and actual exit status. There are no hand-authored PASS substitutions. Public-file absence or empty test discovery fails.

## Isolation, setup, teardown and provenance

The browser wrapper retains the reviewed two-worker limit and `reuseExistingServer:false`. Tests provision synthetic temporary SQLite databases and test-owned anchor files using the frozen `recall-ui/tests/browser_server.py`; no real owner checkpoint, real data, authenticated operator or delivery is invented. Readiness/startup remains Playwright-controlled. Standalone shutdown/scope/external-writer servers retain existing test finally-cleanup.

The runner checks relevant ports before and after browser execution; a leftover listener prevents PASS. It does not kill arbitrary local services. Failure/cancellation relies on Playwright teardown and, on hosted cancellation, disposal of the ephemeral runner. Forced host termination is not a tested graceful application shutdown protocol. Trace/log artifacts contain synthetic examples only.

Local validation uses a fresh shallow clone of committed infrastructure with no shared Git objects, a new venv and a new npm installation. The already downloaded browser ZIP is copied into that new checkout as a cache input and rehashed/re-extracted; dependencies are not copied from the old venv/node_modules. GS1 is independently fetched again. This is local fresh-checkout reproduction, not a GitHub-hosted run or a Windows2025-image test.

Some frozen test/report helpers regenerate historical documentation screenshots/JSON in the disposable checkout. The CI branch does not commit those rewrites. All non-documentation frozen bytes are checked before and after. New proof documentation contains the final runner summary; detailed hosted logs will be Actions artifacts.

## Local verification results and Actions status

Preflight tooling checks executed: hash-locked dependencies installed,4 infrastructure tests passed, the CI wrapper discovered all29 existing browser tests and launched exact Chrome155.0.8059.84. No product safety source change was required.

**Complete fresh-checkout run: PASSED, exit0**, at infrastructure commit25cbb3a. Final delivery is its documentation/evidence descendant with only a wording correction from “authenticated” to “pinned” digest in the preparation-script comment; no behavior change. [Machine-readable local proof](PHASE31_CI_LOCAL_PROOF.json) records every command, exit, toolchain, source inventory and conformance/synthetic result.

| Required coverage | Actual local result |
| --- | --- |
| Infrastructure fail-closed tests | 4 passed |
| A: pinned engine | 127 passed |
| B: foundation | 21/21 checks true |
| C: integration | 44 passed |
| D: application / A31 / hardening | 7 / 16 / 13 passed |
| E: retained synthetic suite | 12/12 agreement; 0 false releases in6 unsafe, 3 holds among6 safe |
| E: expanded synthetic suite | 25/25 agreement; 0 false releases in14 unsafe, 3 holds among11 safe |
| F: exporter / snapshot | 7 passed / exact snapshot check passed |
| G: TypeScript / production build | both passed, dependency install scripts disabled |
| H: Vitest | 33 passed |
| I: pinned-browser Playwright | 29 passed, including live safety, responsive and accessibility cases |
| J: GS1 | 58 live generated documents schema-valid; 19 retained events/2 documents schema + JSON-LD roundtrip valid |
| K: provenance | original126-file verifier and full196-file frozen inventory passed before/after |
| Server cleanup | ports4173/4182/4183/4184 free before and after |

The fresh checkout was shallow and used no shared Git objects; its Python and npm environments were newly installed. The Google ZIP cache was independently reverified/re-extracted, not treated as proof solely because it existed. GS1 was fetched independently at its exact SHA. Only disposable generated documentation artifacts changed during the run; no product sources changed. There were no failing required verification gates in this complete run. These observations do not establish Actions success or factory safety rates.

**GitHub Actions at report preparation:** no hosted run of this new workflow had occurred before the first push. Actions is enabled and allows all Actions; default token permissions are read and automated PR approval is disabled. The authorized branch push will trigger the workflow. The delivery message reports the observed scheduling state, if available. Require an actual successful run at the exact final SHA before treating either check as available/enforceable. See [branch-specific Actions runs](https://github.com/mohammedsuhailrafek28/PRAMAAN-Manufacturing/actions?query=branch%3Ainfra%2Fphase31-ci-gates).

No claim that YAML validation executes a hosted workflow, that local Windows equals windows-2025, or that the dependent Linux summary job was executed locally. That summary is a simple status predicate and still requires an actual hosted run.

## Known infrastructure risks and owner prerequisites

- Enable/retain Actions, GitHub-hosted Windows2025/Ubuntu24.04 runner availability and artifact storage. Existing settings already enable Actions/all actions. If later restricted, allow the four exact official action references; no new privileged secret is required.
- Python/Node release availability, bundled npm11.13.0, public PyPI/npm, Google ZIP and exact GS1 commit access are mandatory. Unexpected versions or missing artifacts fail setup. No downgrade or mutable-browser fallback is provided.
- Registry/package scripts are disabled during npm installation; all required native binaries must exist in integrity-locked optional packages. The fresh test run must prove build/test functionality without install scripts.
- Browser timing, local CPU contention, fixed-port occupation and OS/browser differences can cause genuine infrastructure failures. No retries that turn a failed gate into unreported green, no screenshot-only pass and no skipped hardening tests.
- The frozen inventory intentionally rejects later product changes. Updating the reviewed baseline/pins requires a separate authorized safety/CI review, not editing the manifest just to make a product diff pass.
- Required contexts are not available merely because names appear in YAML. Wait for successful real runs; stale/old-head evidence is insufficient.
- Establish an independent authorized GitHub reviewer. The collaborator API currently lists only the owner; Claude's written audit is required evidence but is not a distinct GitHub approval identity.

## Owner-side protection configuration — proposal only

Inspected settings: main protected=false; rulesets empty; no existing workflows before this branch; auto-merge disabled, automatic branch deletion disabled. The authenticated account has admin access, so these are confirmed observations, not permission-denied assumptions. No settings were modified.

After explicit owner approval:

1. Invite/authorize a genuinely independent reviewer. The PR author cannot provide their own independent approval; do not create a fake identity or use a routine bypass to satisfy this requirement.
2. Wait for a successful hosted run of this workflow on the final reviewed candidate. Confirm both exact context names and GitHub Actions as the expected source. GitHub requires recent successful contexts before they can be selected; do not configure fictional required checks. [Required checks guidance](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks).
3. In repository Settings → Rules → Rulesets → New branch ruleset, target main/default branch, set enforcement Active, and leave the bypass list empty. Alternatively use a classic branch protection rule for exact main with administrator enforcement enabled; do not configure conflicting rule sets blindly.
4. Require PR before merge, at least one independent approving review, dismiss stale approvals, require approval of the latest reviewable push, and require resolved review conversations.
5. Require **Phase 3.1 verification (Windows)** and **Phase 3.1 required gates**, selecting their actual GitHub Actions source when available. Require the branch to be up to date with main so final merge-result changes are tested.
6. Block force pushes and branch deletion. Apply enforcement to administrators/no routine bypass. Keep auto-merge and automatic source-branch deletion off. Do not impose linear-history rules incompatible with preserving imported merge histories, or retrospective signature requirements without assessing existing commits.
7. Add reviewed CODEOWNERS for `.github/`, `ci/`, safety/audit/ledger/evaluator and provenance paths after real owners exist. This assignment does not create that governance file or modify settings. Verify a test PR actually cannot merge without the required independent approval/checks, only when PR creation is separately authorized.

An administrator able to edit rules can still change them; branch protection is governance enforcement, not protection from a fully compromised repository administrator. [GitHub protected-branch behavior](https://docs.github.com/en/enterprise-cloud%40latest/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

## Integration ancestry and non-mutating plan

Main and hardening share merge base `4a9e8f2c11e5e12bfd6926bfb9f9a0ee0dd3fa57`. Main is its existing PR#1 merge, with the same original application tree. Hardening adds the two A31 commits (`3cf6bc9`, `ad76098`) and three hardening commits (`903f37b`, `dc273fe`, `f928210`). CI then adds its own infrastructure/documentation commits. Those five related remediation commits would be included in a future CI→main PR; **that would not be an infrastructure-only PR**.

Neither `phase3/safety-remediation@5ac0a16` nor `research/process-deviation-tracing@ff1a025` is an ancestor of this branch. No new process-deviation/evidence-guided research is included. Original foundation experiments already present in the approved common baseline remain unchanged, as required for their conformance checks. Source references and attribution are preserved, not copied into a second engine.

Future owner-approved sequence, not executed:

1. Receive Claude's exact-f928210 verdict, resolve any conditions, independently review these CI pins/scripts and obtain owner approval for a candidate.
2. Fetch/reverify main, hardening and final CI refs. If any expected source changed, review the new diff and evidence; do not assume this report transfers to another SHA.
3. Only after separate authorization, create `integration/phase3-reviewed` from the approved CI SHA (which already includes exact f928210). Do not modify the audited hardening branch or merge the competing remediation/research ancestry.
4. Main6e772e8 is not an ancestor of this feature line. Strict up-to-date protection may require an explicitly approved merge of main into the NEW candidate. Review the actual tree/conflicts and rerun A–K on that final result. No merge/rebase/cherry-pick is performed in this assignment.
5. With separate PR approval, create a draft candidate→main PR. Include exact ancestry, Claude's verdict, CI source review, final-hosted-run links and migration/custody requirements. Mark ready only after checks, resolved conversations and independent GitHub review apply to the latest SHA.
6. Owner explicitly authorizes any eventual manual GitHub merge commit. Preserve original SHAs/attribution; no squash/rebase/history rewrite, deployment or source-branch deletion is proposed here.

Read-only inspection commands:

```powershell
git fetch origin
git ls-remote --heads origin main integration/phase31-a31-hardening infra/phase31-ci-gates
git merge-base origin/main HEAD
git log --oneline origin/main..HEAD
git diff --name-status origin/main HEAD
git diff --name-only f9282101159b6b6806974848d7c351999098d792 HEAD
git merge-base --is-ancestor origin/phase3/safety-remediation HEAD
git merge-base --is-ancestor origin/research/process-deviation-tracing HEAD
```

For the last two commands exit1 is the expected finding that unrelated ancestry is absent, not a passing test being fabricated. There is no command here that merges/rebases/cherry-picks.

## Rollback and C1 custody

CI uses synthetic test-owned anchor files solely to exercise the enforcement contract. **CI passing does not establish operational checkpoint custody.** A file outside SQLite is not inherently trusted. C1 proves continuation from an independently retained checkpoint, not that the checkpoint is the newest one or that manufacturing evidence is physically true. An old checkpoint cannot detect rollback of later uncheckpointed captures/holds/obligations, and replacing both archive and reference is outside its trust model.

Before real operational use, establish owner custody, monotonic checkpoint advancement, independent retention and recovery procedures. There is no authenticated resolution/delivery system in this branch. Production decisions need separately validated real evidence and identity controls.

Future code rollback should be a separately approved forward revert, not forced main reset. Database rollback is not equivalent: restoring old data can erase late holds/obligations. Reconcile intervening evidence and communications, verify externally retained checkpoints and keep clearance unavailable until authorized recovery. CI cannot bless an unsafe DB restore merely because source tests pass.

## Go/no-go and review checklist

- [ ] Claude independently approves exact f928210 and all applicable conditions.
- [ ] Independent reviewer approves CI scripts, source inventory, action SHAs and artifact pins.
- [x] Fresh local A–K reproduction passes with no product changes or omitted gates.
- [ ] Actual GitHub-hosted A–K and required summary pass at the final candidate SHA/base.
- [ ] Owner configures/verifies real main protection and independent review, without bypass.
- [ ] Ancestry/diff contains only approved remediation + CI; no competing lifecycle or new research.
- [ ] Migration/replay and C1 custody/advancement/recovery boundaries are explicitly accepted.
- [ ] Final merge authorization is separately obtained; no deployment follows automatically.

Until all are satisfied: **HOLD for integration approval**. Local CI success alone is a tooling result, not a safety or merge-readiness verdict. After the authorized infrastructure-branch push, stop for approval.
