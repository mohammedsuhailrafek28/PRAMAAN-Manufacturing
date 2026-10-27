# Manufacturing PRAMAAN: open-source foundation feasibility

Review date: **21 October 2026**. Status: evaluation only; architecture remains open.

## 1. Decision and scope

**REVISE the single-upstream-base premise. Recommend option D as the primary foundation for the 36-hour prototype: a lightweight EPCIS-compatible event store and explicit manufacturing profile, using reusable standards/validation libraries.** OpenEPCIS is the strongest reusable EPCIS toolkit and the preferred candidate for a later repository boundary. Industry Core Hub is the strongest future passport/dataspace exchange boundary. Trace-X is not the preferred base for this project.

No inspected upstream provides the combination of temporal slot genealogy, capture completeness, provenance and deterministic recall assurance out of the box. Combining the three complete platforms would increase infrastructure without resolving those semantics. Option D entails custom domain work; it is not a claim that a ready-made unified open-source product was found.

**GO for the isolated feasibility path demonstrated here; REVISE before production or full integration.** Do not adopt a complete platform, freeze architecture, or infer regulatory compliance from this study. No integration is started by this recommendation.

The canonical local repository is `<WORKSPACE>/ps10`. Its configured remote happens to be `https://github.com/mohammedsuhailrafek28/HORIZONXT-PS10`; that was observed locally, not assumed from the earlier URL. Research worktree: sibling `foundation-study`, branch `research/open-source-foundation`, created from main `1e7450f657d52fa4030c489433b0e520312cb867`. Claude's `feature/slot-attribution-safety` was at `02c631a405a62fbfb9bbbc153677526d836067dd` when the study started. Completion was explicitly confirmed by the user before study work began. During the study another worker advanced that branch to `1620ed3a8c78d7ea41063107666d9482fd93dff9` (v3 observation-hold profile); that change was not inspected for this evaluation or used by any probe. This research did not write to that branch. Main remained at the stated baseline.

This branch contains research and disposable probes only. It has no engine, original fixtures, oracle, production routes, UI, migrations or upstream source trees. The MSME repository was not opened or modified. Public upstream checkouts and tooling live outside both worktrees in `foundation-upstream`; none are merged or vendored.

## 2. Evidence and repository activity

These are inspected default-branch commits, not an assertion that every component belongs to one compatible release train. Exact file URLs, SHA-256 digests, GitHub API activity and latest-release responses are in [upstream-evidence.json](../experiments/foundation/upstream-evidence.json). Missing GitHub release responses mean HTTP 404, not absence of Maven/npm releases. GitHub `pushed_at` may reflect another branch; it is not the reviewed main commit date.

| Repository | Reviewed revision | Reviewed commit date | Release/activity finding | License finding |
|---|---|---|---|---|
| [OpenEPCIS CE](https://github.com/openepcis/epcis-repository-ce) | `e81a857771c4` | 2026-01-10 | Main is older than the 2026-10-21 repository push; no latest GitHub release returned | Root Apache-2.0, but conflicting restrictive header in CE distribution POM; Research Edition explicitly separately licensed |
| [OpenEPCIS models](https://github.com/openepcis/openepcis-models) | `88e82414d169` | 2026-10-08 | Models actively updated; Maven 0.9.3 available | Root, sampled Java classes and POMs Apache-2.0 |
| [OpenEPCIS event hash](https://github.com/openepcis/openepcis-event-hash-generator) | `bcfcb169e03b` | 2026-09-07 | GitHub `v0.9.3`, published 2026-06-11; Maven 0.9.3 | Root, core Java and POM Apache-2.0; transitive review still required |
| [OpenEPCIS Event Sentry](https://github.com/openepcis/openepcis-event-sentry) | `fe0a043c35fc` | 2026-09-09 | JS package declares 1.0.0; no latest GitHub release returned | Root/package Apache-2.0 conflicts with restrictive source headers |
| [OpenEPCIS BOM](https://github.com/openepcis/openepcis-bom) | `1e1e26deedec` | 2026-09-02 | Main is `999-SNAPSHOT`; published 0.9.3 is a different baseline | Apache-2.0 |
| [Trace-X / traceability-foss](https://github.com/eclipse-tractusx/traceability-foss) | `4cbf377f90eb` | 2025-06-10 | Latest release API returns 15.0.1, 2025-05-30; last repository push 2026-02-09; not archived | Apache-2.0 code; CC-BY-4.0 non-code; NOTICE and dependency inventories |
| [Industry Core Hub](https://github.com/eclipse-tractusx/industry-core-hub) | `ade4edfc19de` | 2026-10-20 | Active main; latest release API returns v0.5.0, 2026-03-17 | Apache-2.0 code; CC-BY-4.0 non-code; NOTICE |
| [Tractus-X SDK](https://github.com/eclipse-tractusx/tractusx-sdk) | `54653fea92c7` | 2026-10-16 | v0.8.3 release, 2026-09-25; Hub pins 0.8.2 | Apache-2.0 code; CC-BY-4.0 non-code |
| [GS1 EPCIS artifacts](https://github.com/gs1/EPCIS) | `6f7146823183` | 2026-09-04 | Schema, JSON-LD context, XSD and query/interface artifacts | `LICENSE` contains GS1 IP-policy disclaimer, not an MIT/Apache software grant |

License conclusions are adoption findings, not blanket legal clearance. Apache redistribution normally requires the license, applicable notices and identification of modified files; it does not grant trademark rights. CC-BY content needs attribution and indication of changes. Preserve file-specific rights and third-party notices, not just a top-level label. Verify the exact distribution and full dependency closure before shipping.

### Specific license blockers

* CE [distribution POM](https://github.com/openepcis/epcis-repository-ce/blob/e81a857771c4c4a2d12e62b60a2dbc094551aa6e/distributions/community-edition/pom.xml) carries a restrictive header despite the root Apache license. This is a conflict to resolve with the maintainer, not proof that all CE code is proprietary. The README separately states that Research Edition components require a commercial agreement. Exclude Research Edition from the proposed adoption set.
* Event Sentry [validator source](https://github.com/openepcis/openepcis-event-sentry/blob/fe0a043c35fca81284a813fd793de2657165b380/src/validation/validator.js) and `src/index.js` contain restrictive headers despite Apache declarations. Do not extract these files before clarification.
* GS1 normative artifacts are publicly inspectable, but this checkout's license file does not establish a conventional permissive redistribution license. The experiment reads the schema/context from an external checkout and commits only digests. Resolve redistribution terms before bundling them in a distributed product.
* Hub's `NOTICE.md` still names `sig-security` as its source repository and says third-party content is “None”, although its requirements contain many third-party packages. Retain the actual notice, but do not use it as a complete SBOM or dependency clearance.
* Probe packages are not all under one license: `jsonschema` is MIT; `rfc8785` 0.1.4 ships Apache-2.0 in its wheel LICENSE despite missing license metadata; PyLD 2.0.4 declares BSD-3-Clause, but its resolved `frozendict` 2.4.7 dependency declares LGPL v3. PyLD is a research conformance tool here, not a selected production dependency. Distribution of that closure requires its own obligations review.

## 3. What already solves PS10 needs

| PS10 need | Useful existing capability | What it does not establish |
|---|---|---|
| Shared manufacturing event vocabulary | EPCIS AssociationEvent, ObjectEvent, TransformationEvent; CBV business steps | Slot labels, installation references, source sequences and safety policy are not mandatory base EPCIS fields |
| Capture, historical search, subscriptions | OpenEPCIS API interfaces and CE capture/query pipeline | Safe slot attribution or completeness of source evidence |
| Serialized and batch identities | OpenEPCIS models; Hub catalog/serialized/batch management; Trace-X SerialPart/Batch | Equivalence of local serials, GS1 identifiers and Catena-X UUIDs without an identity map |
| Parent/child manufacturing genealogy | EPCIS association history; Trace-X as-built/as-planned tree and IRS integration | Trustworthy temporal removal or “no historical exposure” from a current BoM snapshot |
| Digital passport sharing | Hub EcoPass DTOs, passport manager, twin/submodel registration and sharing services | An immutable, event-pinned PRAMAAN safety finding or full product-specific passport compliance |
| Partner interoperability | Hub/SDK EDC negotiation, DTR, discovery and submodel access | Local factory event completeness or proof an operator physically used the stated slot |
| Quality incident collaboration | Trace-X quality alerts/investigations | The existing deterministic recall engine's finding/action/review semantics |
| Duplicate/content fingerprint | OpenEPCIS CBV event hashing; RFC8785 for a separately specified local JSON envelope | Source authenticity, digital signatures or external tamper anchoring |

[EPCIS 2.0.1](https://ref.gs1.org/standards/epcis/2.0.1/) is the target standard reference. The probe uses the exact pinned repository schema/context, not a claim that a mutable main artifact is byte-identical to the ratified publication. Both digests are recorded. Do not silently move this target to public-review 2.1 artifacts.

## 4. Genuinely reusable modules and coupling

### OpenEPCIS

1. **`io.openepcis:openepcis-model-core:0.9.3` and `openepcis-model-epcis:0.9.3`:** actual Maven libraries; `epcis/.../AssociationEvent.java` models parent, children, actions, time and user extensions with Jackson/JAXB bindings. Core is smaller; EPCIS models pull format/identifier concerns and related libraries. They are Java modules, not Python imports. Keep behind a process/library boundary if PRAMAAN remains Python.
2. **`io.openepcis:openepcis-event-hash-generator:0.9.3`:** actual standalone core artifact, entry point `io.openepcis.eventhash.EventHashGenerator`, with `fromJson`/`fromXml`. Current source has CBV-version behavior and tests for field exclusion, parity and invariants. Core depends on the reactive publisher, Digital Link converter, constants, Jackson, Mutiny, Commons and SLF4J; a provided Quarkus dependency is also declared. It is not a dependency-free hash function.
3. **`openepcis-digital-link-converter-core:0.9.3` and `openepcis-reactive-event-publisher:0.9.3`:** published dependencies confirmed on Maven Central. Useful for identifier conversion and stream processing. The converter child POM has no direct license entry; inspect its parent/source/license closure rather than interpreting an absent element as permission or prohibition.
4. **`modules/openepcis-rest-api-common` and `modules/openepcis-client`:** reusable API/client contracts, not an embedded repository. `EventsApi.java` exposes EPCIS query filters and pagination. These interfaces do not implement storage, indexing or graph replay.
5. **`modules/quarkus-capture-topology-ce` and `quarkus-rest-application-ce`:** application/infrastructure assembly, not attractive small-library extractions. They reference `openepcis-capture-service`, `openepcis-capture-kafka-streams`, `openepcis-repository-opensearch`, `openepcis-query` and `openepcis-repository-api`. Those coordinates returned 404 from Maven Central metadata and their implementations are not in this CE checkout. The BOM also declares a company-hosted Maven registry. Availability and rights outside Central remain unresolved; this is not proof they cannot be obtained elsewhere.
6. **Event Sentry:** inspectable profile validation SDK, but not selected. Besides the header conflict, `validator.js` imports lodash while `package.json` places it in devDependencies; direct source reuse under production-only installation needs correction or bundling verification. Its AJV setup uses `strict:false`; application profile and format checks still need explicit tests.

The **published** 0.9.3 core/model/hash jars inspected here use class major 65 (Java 21). The **reviewed main BOM** specifies Java 25 and `999-SNAPSHOT`. These must not be conflated. The local Java runtime is 21.0.12.1. Central metadata, POM dependencies, jar digests and class-version findings are in [artifact-evidence.json](../experiments/foundation/artifact-evidence.json).

### Trace-X

The reusable seams are `tx-models` API DTOs, `tx-backend/.../assets/application/asbuilt/rest/AssetAsBuiltController.java`, `assets/domain/asbuilt/service/AssetAsBuiltServiceImpl.java`, and `assets/infrastructure/base/irs/model/response/mapping/relationship/RelationshipMapper.java`. Use the public interfaces and semantic models as references before attempting extraction.

`AbstractAssetBaseService.syncAssetsUsingIRSOrderAPI` delegates upward/downward resolution to `OrderRepository`/IRS; the as-built service requires asset, view, order and trigger-configuration repositories. The relationship mapper imports `org.eclipse.tractusx.irs.component.Relationship`. These are coupled application services, not a standalone graph library. Even `tx-models` brings Spring validation/web and other dependencies.

Reviewed stack: Java 17 source target, Spring Boot 3.4.1 property, Angular 16.2.x frontend, PostgreSQL, OAuth/Keycloak and IRS/EDC/DTR/discovery/submodel infrastructure. Its compatibility matrix names IRS 7.0.1 and connector 0.10.0 for the reviewed release family; Maven also pins IRS client 3.0.2. Do not infer compatibility with current Hub/SDK from common Tractus-X branding. Old main/release dates and older dependency generations increase maintenance risk; no full vulnerability clearance was performed.

### Industry Core Hub and SDK

Real Hub code includes `ichub-backend/services/provider/{part_management_service,twin_management_service,submodel_dispatcher_service}.py`, `models/services/provider/`, and `managers/addons_service/ecopass_kit/v1/passports.py`. `PassportsManager` queries `TwinAspect`/twin/part relations and retrieves submodel data; it is not a manufacturing-event journal. Twin management imports configured connector/DTR managers and a repository factory. Copying it alone does not remove those dependencies.

Hub uses FastAPI, Pydantic, SQLModel/SQLAlchemy, PostgreSQL, Keycloak and Tractus-X SDK; frontend is React 18/MUI/Vite. Its setup.py declares no install dependencies, so requirements.txt is essential. Reviewed requirements pin SDK 0.8.2 and include unconditionally pinned `uvloop` (a native Windows install issue); the separately reviewed SDK 0.8.3 uses platform markers and `winloop`. The 0.8.3 package requires Python >=3.12 and includes substantial web/auth/database dependencies. This is a useful future interoperability dependency, not a tiny pure domain package.

The cleaner reusable SDK seams are `industry/services/aas_service.py`, `industry/adapters/submodel_adapter.py` and its file/HTTP adapters, and `dataspace/services/connector/{jupiter,saturn}/` provider/consumer services. Pin the connector protocol family before adopting them. Hub's README lists EcoPass as available and Traceability KIT as planned: its current passport capability must not be mistaken for a completed slot genealogy implementation.

## 5. Minimal interoperability experiment

Executable source: [interop.py](../experiments/foundation/interop.py). Machine-readable evidence: [results.json](../experiments/foundation/results.json). **21 checks pass**, using six independently authored synthetic events: BUILD open, bearing install, BUILD close, REWORK open, bearing removal, REWORK close.

The flow is: native documented envelope → EPCIS document → schema validation → transactional in-memory SQLite capture → component-to-motor association query → retrieval of full motor evidence stream → native input adapter. No production engine is imported, executed, copied or rewritten. The old Phase 1 README/event-envelope examples at `72be2c9` were read solely to identify the documented contract permitted by the task; neither that branch nor Claude's safety changes are runtime dependencies. Original fixture datasets and oracle values are not used.

| Concern | Tested representation/result |
|---|---|
| Install/remove | AssociationEvent `ADD`/`DELETE`, motor URI as parent, serialized bearing URI as child; assembling/disassembling business steps |
| Work-order evidence | ObjectEvent with private trace metadata; no invented standardized work-order semantics |
| Native envelope | `eventID` → `eventId`, `eventTime` → `occurredAt`; source ID/sequence, actor, evidence refs, work order, schema version, time source, supersession and payload survive exact equality round-trip |
| Slot identity | Required `DE`/`NDE` inside a namespaced JSON-LD `@json` trace extension; missing slot rejected |
| Removal attribution | Explicit `endsInstallEventId` and observed part/lot/serial retained; no installation reference rejected |
| Two timestamps | Original producer `recordedAt` survives separately from repository `recordTime`; replacing it would corrupt replay semantics |
| JSON-LD | Expansion/compaction with PyLD preserves trace values; loader allows only pinned offline GS1 context |
| Genealogy | Component query returns both ADD and DELETE with the same motor parent; historical relationship retained after removal |
| Retry/conflict | Identical capture is idempotent; changed content under the same event ID and duplicate source sequence rejected |
| Integrity | Exact-byte SHA-256 and context-bound RFC8785 SHA-256 metadata retained; key order invariant, slot mutation changes digest, stored-byte mutation detected |
| Missing profile | A bare association event passes base EPCIS schema but is rejected by the adapter: it cannot invent slot/source sequence/coverage |
| Input consistency | Conflicting core/extension action and invalid EPCIS timestamp rejected; rejected captures preserve original history |

The capture session in the generated input is an explicit synthetic declaration, not coverage inferred from an EPCIS query. A component-only query is **not** sufficient engine evidence: it omits work orders, other slots, outages, operation and verification events. `engineInput` is built from the full retrieved stream. A real adapter must obtain all relevant motor events plus authoritative source watermarks and capture-coverage records before evaluating anything.

The extension is intentionally verbose to demonstrate losslessness. It is a research profile, not an approved production schema or an upstream-supported profile. A JCS digest is not a GS1 CBV hash, RDF canonicalization, signature or proof of a physical operation. The engine has no demonstrated native integrity-metadata input; hashes remain a separate evidence manifest and must not be silently treated as an engine trust signal.

### Evidence levels for A–D

* **A: CE separate service:** upstream Compose parses successfully (`docker compose ... config --quiet`, exit 0). No service started, no capture endpoint called, no container deployed. Runtime extension retention, capture-job completion, association query filters and paging remain unverified. License conflict and non-Central dependency availability prevent recommending it as the hackathon critical path.
* **B: selected libraries:** Maven resolution succeeded, but the unmodified declared dependency set failed in `fromJson` with `NoClassDefFoundError: org/apache/commons/io/input/ReaderInputStream`; see [baseline result](../experiments/foundation/java-baseline-results.json). Adding explicit `commons-io:commons-io:2.22.0` in the probe profile allowed OpenEPCIS hash generator 0.9.3 to hash all six events. Five document variants showed that changing private slot, source sequence or producer recorded-at metadata changes the install hash; changing repository `recordTime` does not. See [java-results.json](../experiments/foundation/java-results.json). This demonstrates selective library use without Kafka/OpenSearch, with a packaging workaround. XML parity and full model serializer round-trip were not tested. No engine is involved.
* **C: Trace-X/Hub interfaces:** source, DTOs, repository coupling and deployment contracts inspected. Neither platform nor its network dependencies was started. No claim of an end-to-end cross-company exchange or safe recall outcome.
* **D: local store/adapters:** executable synthetic install/remove/query/native-envelope round-trip and integrity checks pass. This is an in-memory feasibility result, not a durability, performance, fleet-scale or full-recall evaluation.

## 6. Setup, maintenance and security

CE's supplied configuration requires REST application, Kafka, OpenSearch and topic setup; Dashboards is also included. Its README suggests 8 GiB/8 CPU for a Podman VM. That is a documented setup suggestion, not measured usage. Supplied Compose pins OpenSearch 2.19.2 and `bitnamilegacy/kafka:3.8`, uses plaintext Kafka and disabled OpenSearch security, and references a mutable `stable` application image. These are local-development defaults requiring replacement before any production exposure. No image scan or runtime SBOM was completed.

Trace-X's documented full environment adds Kubernetes/Helm/umbrella provisioning and external identity/connector/registry/discovery/IRS components. A mocked developer profile is not evidence of real partner interoperability. Hub reduces orchestration work but still needs enablement services, configuration, credentials and compatible semantic model versions. Its PostgreSQL-only local Compose recipe does not create the full dataspace.

The Python probe installed in an external venv. A resolved package list is in [requirements.lock](../experiments/foundation/requirements.lock), with licenses/dependencies in [package-evidence.json](../experiments/foundation/package-evidence.json). `pip-audit` 2.10.1 reported **no known vulnerabilities for the 10 enumerated pinned packages** on the review date; see [dependency-audit.json](../experiments/foundation/dependency-audit.json). The scan used `--no-deps --disable-pip` against that enumerated closure. It is not a comprehensive audit of the machine, Maven closure, Hub, Trace-X, images or future releases. The lock is version-pinned, not a hash-verified production lock/SBOM. The resolved Java closure includes legacy `avalon-framework-impl:4.2.0`, `commons-cli:1.0`, `commons-logging:1.0` and `commons-lang:1.0`; successful execution does not clear those transitives for product use. Jar coordinates/digests are recorded with the Java result; vulnerability and license-closure review remains open.

Time estimates below are engineering estimates, not measured full-stack setup times. Only probe and configuration checks were executed. Allow roughly 2–6 hours for a narrow D slice, 4–12 hours for a cleared Java library boundary, 8–24+ hours for an unfamiliar CE service, and 1–3+ days for a working dataspace stack. Identity/provider access and licensing can exceed those estimates regardless of coding speed.

## 7. Comparison matrix

| Criterion | A: OpenEPCIS CE service | B: selected OpenEPCIS libraries | C: Trace-X interfaces/modules | D: local EPCIS-compatible store | Hub as unified base |
|---|---|---|---|---|---|
| End-to-end evidence here | Compose only; runtime not proven | Six-event hashing works with explicit Commons IO dependency; mutation coverage tested | Static inspection only | Install/remove/query/native translation proven | Static inspection only |
| Setup / operations | Kafka + OpenSearch + REST; topic/index/readiness management | Java boundary and dependency closure; no Kafka needed for model/hash use | Spring/PostgreSQL plus IRS/EDC/DTR/IAM ecosystem | Smallest experimental footprint; production persistence remains work | Python/PostgreSQL plus EDC/DTR/discovery/IAM |
| Engine compatibility | Adapter/profile and complete evidence export required | Models/hash assist boundary; do not replace engine | Snapshot/relationship data lacks native source stream semantics | Direct explicit mapping to existing envelope | Passport/twin views require event-stream adapter |
| Manufacturing completeness | Strong generic event types; custom slots/coverage | Serialization/conversion/hash only | Strong parts/supplier relationships and quality messaging | Only tested bearing slice; quantities/transforms unfinished | Strong twins/submodels/passports; temporal slot journal missing |
| License obligations | Apache declarations plus unresolved file conflict; exclude Research Edition | Artifact-specific Apache/parent/transitive review | Apache code, CC-BY content, NOTICE/dependencies | Small dependency surface; GS1 artifact rights and probe LGPL closure need care | Apache/CC-BY and substantial transitive closure |
| Maintenance/security | Main/dependency drift, external registry, mutable images, dev security defaults | Released 0.9.3 vs Java-25 main must be pinned | Older main/dependency baseline, multi-service compatibility | Custom store burden; smallest auditable core | Active project; requirements/protocol/version coupling |
| 36-hour feasibility | Risky critical path | Conditional for a narrow cleared library | Poor for full platform; interface research useful | Best fit for one controlled slice | Poor for full dataspace; future adapter viable |
| Long-term extensibility | Strong standardized capture/query backend candidate | Strong reusable boundary toolkit | Useful partner traceability/quality integration | Good boundary flexibility; most domain implementation remains ours | Strong future passport/data-exchange orchestrator |
| Decision | REVISE; later service pilot | GO for selective evaluation, not full embedding | NO-GO as primary base | Recommended primary prototype foundation | REVISE into optional exchange boundary |

## 8. What remains custom

Keep the existing deterministic recall engine, slot-attribution rules, finding/action/review separation, policy interpretation and tests under their current ownership. This study does not judge or modify Claude's reported 99-test/35-oracle result.

PRAMAAN must own its manufacturing profile and identifier map; trusted source enrollment; source sequence/watermark and coverage semantics; observed-versus-claimed slot attribution; verification independence; work-order reconciliation; correction/supersession policy; and evidence-pinned explanations. It also needs quantity conservation, transformation/split/merge semantics, bounded genealogy traversal, retention, authorization, provenance authentication and passport snapshot policy. Upstream storage or DPP display does not eliminate that work.

## 9. Proposed integration boundaries, subject to approval

1. **Capture boundary:** accept EPCIS plus a versioned PRAMAAN trace profile; preserve original bytes, context/schema digests and authenticated source claims. Reject incomplete/contradictory inputs or quarantine them with an explicit unresolved state. Do not fill missing slots from a BoM guess.
2. **Event repository boundary:** use D for the first approved slice; keep interfaces compatible with a later CE capture/query adapter. Exactly one authoritative event history. Any search index is rebuildable; no independent safety truth in a second platform.
3. **Assurance boundary:** obtain a complete, pinned motor evidence set, coverage policy and source watermarks; map to the existing engine envelope. Integrity/provenance verification occurs before engine input. No external graph, hash tool or LLM makes recall findings.
4. **Passport boundary:** derive a read-only versioned passport from that evidence snapshot. A future Hub/SDK adapter can publish a twin/submodel or passport reference with policy-controlled sharing. It cannot override recall findings or mutate original history.
5. **Partner genealogy boundary:** optional Trace-X/IRS interfaces may supply explicitly attributed external relationships. Treat absent or truncated partner data as unknown; never use it to prove a component was removed.

## 10. Exact blockers and unresolved questions

| Blocker / question | Required next evidence before adoption |
|---|---|
| Conflicting CE/Sentry headers | Maintainer clarification identifying exact permitted files/artifacts; retain responses with versioned license manifest |
| CE core implementation/distribution availability | Resolve non-Central dependencies and provenance/rights; pin reproducible distribution/image digest and SBOM |
| CE JSON-LD extension retention | Disposable service pilot capturing these exact events; retrieve full pages, verify byte/semantic metadata, timestamps and digest behavior |
| Native JSON literal in GS1 CBV hash | Slot/source sequence/producer recorded-at mutations tested in 0.9.3; still need XML parity, timestamp/identifier normalization and approved extension-profile conformance. Keep CBV hash separate from full-envelope integrity |
| Released hash library packaging/transitives | Explicit Commons IO workaround is required for tested `fromJson` path; obtain upstream packaging fix or pin/review full patched closure and legacy transitives |
| GS1 schema/context redistribution | Establish explicit artifact redistribution terms; keep external use until resolved |
| Trace-X/Hub compatibility | Select a compatible connector/IRS/DTR/semantic model release set and prove authenticated provider/consumer exchange |
| Completeness and source trust | Define authoritative signed/authenticated producer sequence, coverage sessions and bounded query/export watermark; a repository query alone cannot prove completeness |
| Safety-engine promotion | Independently review/merge safety work through its own process before product integration; this branch has no runtime dependency on it |
| Additional manufacturing scope | Validate NDE/DE ambiguity, same-lot multi-slot identity, corrections, late/out-of-order events, quantity/split/merge, concurrent capture and bounded fleet traversal |
| Production integrity/operations | Key management, signature verification, external audit anchoring, tenant policy, backup/replay recovery and load tests are unproven |
| Passport requirements | Confirm exact PS10 judging fields and any chosen legal passport regime; EcoPass presence does not establish compliance |

**Final recommendation:** approve only a subsequent bounded D integration proposal if desired, using OpenEPCIS as the preferred standards toolkit and later repository candidate. There is insufficient evidence to select CE, Trace-X or Hub as a single production foundation today. Stop at this evaluation; no merge, deployment or full integration is authorized by this document.
