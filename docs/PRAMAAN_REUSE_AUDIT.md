# PRAMAAN Reuse Audit for HORIZONXT PS10

Date: 2026-10-20  
PRAMAAN main baseline: `2bb2bb11344102c80620fde44a29a9bff359bf81`  
Unmerged references reviewed: Firewall PR #4 at `66dd510b31735cb8da0e3df21a6ba38c5cdd1276`; OCR PR #5 at `f02294a8aa1da6b258eb1690b548cefaa01c0b5a`.  
Original repository: [mohammedsuhailrafek28/PRAMAAN](https://github.com/mohammedsuhailrafek28/PRAMAAN)

This is an architecture and reuse audit only. No PRAMAAN source, database, upload, secret, generated artifact, or environment file was copied into this repository. PRAMAAN remains an independent product. PR #4 and PR #5 remain unmerged and are not dependencies of this project.

## Executive Decision

**Recommendation: REUSE THE ENGINEERING PATTERNS, REBUILD THE PS10 DOMAIN CORE.**

The smallest credible PS10 foundation is a new, append-only manufacturing event and genealogy service with an EPCIS-compatible boundary, backed by deterministic validation and graph queries. Reuse PRAMAAN's authentication, request validation, structured logging, safe file-ingestion patterns, hash/revision ideas, audit conventions, snapshot discipline, test harness style, and selected frontend primitives by extraction or adaptation. Do not copy the MSME `Business`, `Document`, `Passport`, `ConsentRequest`, or Trust Profile models into the manufacturing core.

PRAMAAN is currently a TypeScript/Express backend with Prisma and SQLite for local demos, plus a Vite/React frontend. Its product semantics are MSME claims, evidence, consent, and readiness. PS10 requires durable identities for material lots, components, products, sites, transformations, shipments, and event provenance. That is a different bounded context.

## Baseline Architecture Inventory

### Backend and security

- Runtime: Node.js, Express 5, TypeScript; entry points are `src/server.ts` and `src/app.ts`.
- Configuration and safety: `src/config/env.ts`, `src/config/jwtSecretPolicy.ts`, `src/config/prisma.ts`.
- Authentication: JWT and bcrypt in `src/modules/auth/auth.service.ts`, `auth.routes.ts`, and `src/middleware/auth.ts`.
- Authorization: role middleware in `src/middleware/roles.ts`; business ownership checks are implemented in module services.
- Validation and errors: `src/middleware/validate.ts`, `src/utils/apiError.ts`, `src/middleware/errorHandler.ts`.
- Operational controls: `src/config/logger.ts`, `src/middleware/requestId.ts`, Helmet, CORS, API rate limiting, and Swagger setup in `src/docs/openapi.ts`.
- Deployment: `Dockerfile`, `docker-compose.yml`, SQLite initialization in `prisma/init-sqlite.ts`.

### Evidence, snapshots, access and workflow

- MSME profile and document ingestion: `src/modules/business/business.service.ts`, `business.routes.ts`, `business.controller.ts`.
- Deterministic checks: `src/modules/trustEngine/`, including `trust-engine.service.ts`, `cross-check-engine.ts`, `contradiction-detector.ts`, and rule modules.
- Evidence lifecycle and revision semantics: `src/modules/evidence/evidence-lifecycle.service.ts` and `src/modules/evidence/pinned-evidence.ts`.
- Immutable Trust Profile/Passport snapshots: `src/modules/passport/passport.service.ts` and `src/modules/passport/passport-snapshot.ts`.
- Consent and selected disclosure: `src/modules/consent/` and `src/modules/trustView/`.
- Guest access grants: `src/modules/accessGrant/`; tokens are hashed and grants are pinned to a Passport.
- Audit and notifications: `src/modules/audit/` and `src/modules/notifications/`.
- Institution onboarding assignments: `src/modules/onboarding/`; useful workflow precedent, but it is not a production-event ledger.
- Readiness and reports: `src/modules/readinessEngine/` and `src/modules/reportComposer/`.

### Database shape

`prisma/schema.prisma` contains `User`, `Business`, `Document`, `Passport`, `ConsentRequest`, `AccessGrant`, `AuditLog`, `Notification`, `ReadinessEvaluation`, `GeneratedReport`, onboarding assignments, evidence requests, and requester assurance records. The migration chain is ordered through migration 11 on current main. The schema is suitable for the PRAMAAN bounded context; it is not a genealogy graph or event store.

### Frontend and quality tooling

- App shell and routing: `frontend/src/App.tsx`, `frontend/src/routes/ProtectedRoute.tsx`, `frontend/src/components/layout/`.
- Reusable UI: `frontend/src/components/ui/` and `frontend/src/components/shared/`.
- API/session handling: `frontend/src/services/api.ts`, `frontend/src/services/session.ts`, `frontend/src/store/`.
- Evidence and trust presentation: `frontend/src/lib/disclosure.ts`, `trustProfileView.ts`, `evidenceSlots.ts`, and `frontend/src/pages/msme/`.
- Quality: backend scripts under `scripts/`; frontend `check` runs contract check, TypeScript, ESLint, tests, and Vite production build.

## Reuse Matrix

| Component | Current purpose / source | PS10 applicability | Approach | Coupling and risk | Effort / tests |
|---|---|---|---|---|---|
| Express/TypeScript application shell | `src/app.ts`, `src/server.ts` | Good HTTP boundary and local demo base | EXTRACT | Keep manufacturing modules separate from MSME routes | 1-2 days; route/auth/integration tests |
| JWT auth and bcrypt | `src/modules/auth/`, `src/middleware/auth.ts` | Useful for operator and organization accounts | ADAPT | Roles and claims must become plant/org scoped; JWT is not event provenance | 2-4 days; tenant, expiry, revocation tests |
| Zod validation and API errors | `src/middleware/validate.ts`, `src/utils/apiError.ts` | Directly useful for event envelopes and query filters | COPY/EXTRACT | Validate identifiers, timestamps, quantities, units and vocabulary at runtime | 1 day; malformed payload tests |
| Prisma migration discipline | `prisma/schema.prisma`, `prisma/migrations/` | Useful for account/configuration metadata | ADAPT | SQLite is not sufficient for high-write event capture or graph queries | 2-5 days; migration and rollback tests |
| Document upload pipeline | `src/modules/business/business.service.ts`, Multer setup | Useful for certificates, photos, manifests and lab records | ADAPT | MIME/path/file limits and malware scanning remain needed; no automatic trust from upload | 2-4 days; upload isolation/cleanup tests |
| Evidence hash/revision pattern | `Document` revisions and `pinned-evidence.ts` | Strong pattern for artifact integrity and supersession | EXTRACT | A hash alone is not a signed production event or source attestation | 2-3 days; chain, replay, replacement tests |
| Passport snapshot pattern | `src/modules/passport/` | Useful for immutable product/lot views and reports | ADAPT | Snapshot must pin event IDs and source sequence, not live document rows | 3-5 days; historical byte-stability tests |
| Consent/access grants | `src/modules/consent/`, `accessGrant/` | Potentially useful for partner-scoped DPP sharing | ADAPT | Consent is not the same as supply-chain custody or event authorization | 3-5 days; scope, expiry, revocation, tenant tests |
| Audit service | `src/modules/audit/audit.service.ts` | Useful for operational actions and security events | ADAPT | Manufacturing events need an append-only domain ledger, not only an audit log | 2-4 days; atomicity and non-repudiation tests |
| Notifications | `src/modules/notifications/` | Useful for recall/task alerts | ADAPT | Delivery is not proof that a production event occurred | 1-2 days; idempotency/deduplication tests |
| Deterministic trust/readiness checks | `src/modules/trustEngine/`, `readinessEngine/` | Some validation concepts transfer | ADAPT | Do not reuse MSME score semantics for product safety or quality conclusions | 3-6 days; rule and provenance tests |
| Report Composer | `src/modules/reportComposer/` | Useful for evidence-linked recall explanations | ADAPT | Reports must state event snapshot and query time; no fresh live recomputation | 3-5 days; snapshot/rendering tests |
| Onboarding/evidence request workflow | `src/modules/onboarding/`, evidence requests | Useful for supplier data requests | ADAPT | Requirement packs do not establish genealogy or custody | 3-6 days; lifecycle/concurrency/privacy tests |
| Structured request logging | `src/config/logger.ts`, `requestId.ts` | Direct reuse | COPY | Redact identifiers, credentials and sensitive production payloads | 0.5-1 day; log-redaction tests |
| Security middleware and rate limits | `src/app.ts`, rate-limit modules | Direct baseline | COPY/ADAPT | Per-process limits are insufficient for multi-instance production | 1-3 days; proxy/IP and abuse tests |
| React/Vite design system | `frontend/src/components/ui/`, shared components | Useful for a demo console | EXTRACT/ADAPT | Replace business-trust copy and disclosure assumptions | 2-5 days; a11y/responsive tests |
| Playwright/browser workflow style | existing browser scripts and frontend tests | Useful for demo gates | COPY | Add graph, event capture, recall, and mobile flows | 1-3 days; journey tests |

## Open-Source and Standards Research

### EPCIS/CBV

Use [GS1 EPCIS 2.0.1](https://ref.gs1.org/standards/epcis/2.0.1/) and [CBV](https://ref.gs1.org/standards/cbv/) as the interoperability target. EPCIS defines a framework and interfaces for capturing and sharing visibility event data; it is a better external contract than inventing a proprietary event JSON model. The [GS1 EPCIS repository](https://github.com/gs1/EPCIS) provides normative artifacts and OpenAPI material.

Recommended event mapping:

- ObjectEvent for creation, commissioning, transformation input/output state changes where appropriate.
- AggregationEvent for component-to-assembly relationships.
- TransformationEvent for consume/produce and material conversion.
- AssociationEvent where the chosen EPCIS profile requires an association relationship.
- Business location, source/destination, disposition, quantities, units, event time, record time, and business transaction references must be modeled deliberately, with vocabulary validation.

### OpenEPCIS

[OpenEPCIS Community Edition](https://github.com/openepcis/epcis-repository-ce) is an Apache-2.0, container-friendly EPCIS 2.0 repository. [OpenEPCIS models](https://github.com/openepcis/openepcis-models) provide Apache-2.0 Java models. These are strong candidates for a conformance/reference environment or a separate event-store service, not a drop-in dependency inside the current Express/Prisma SQLite application. Evaluate Java/runtime and operational cost before adoption.

### Tractus-X / DPP

[Eclipse Tractus-X Digital Product Pass](https://github.com/eclipse-tractusx/digital-product-pass) is a reference implementation for visualizing standardized product/battery/transmission passports. The wider Tractus-X project is Apache-2.0 governed, while individual repositories and content may carry additional notices; perform a repository-specific license and NOTICE review before copying code. Reuse its conceptual DPP interoperability patterns and schema references first. Do not copy its full platform into PS10.

### Workflow engines

For the first slice, build a small explicit state-transition module in TypeScript, backed by durable event records. A full BPM platform is premature. [XState](https://github.com/statelyai/xstate) is MIT and useful if the workflow grows into human review and retryable statecharts, but it should not own the manufacturing event ledger. [Conductor OSS](https://github.com/conductor-oss/conductor) is Apache-2.0 and durable, but is too large for the first PS10 vertical slice. Reassess after the event model and query boundaries are proven.

### License and attribution position

PRAMAAN's current repository does not contain a root `LICENSE` or `NOTICE` file in the reviewed main tree. Do not copy PRAMAAN source until its licensing and attribution position is explicitly settled. The new repository contains no copied PRAMAAN code. For external reuse, retain upstream LICENSE/NOTICE files, record exact versions/commits, and run an SBOM/license scan before distribution. Direct PRAMAAN dependencies are predominantly MIT or Apache-2.0, but this must be verified from lockfiles and package metadata at implementation time.

## PS10 Gap Analysis

| PS10 capability | Existing PRAMAAN support | Decision |
|---|---|---|
| Material batch/lot identity | No batch, lot, serial, SKU, GTIN, or material identity model | BUILD FRESH |
| Component and assembly genealogy | No graph edges or parent/child production relationships | BUILD FRESH |
| Manufacturing event capture | Audit logs record application actions, not EPCIS production events | BUILD FRESH; EPCIS boundary |
| Split, merge, consume, rework | No quantity ledger or transformation semantics | BUILD FRESH |
| Finished product traceability | Passport is an MSME evidence snapshot, not a product passport | BUILD FRESH; reuse snapshot discipline |
| Shipment and custody traceability | No shipment, carrier, source/destination, or custody model | BUILD FRESH |
| Forward/backward graph traversal | No graph query layer | BUILD FRESH |
| Defect impact analysis | Contradiction detection is unrelated to lot impact propagation | BUILD FRESH |
| Tamper-evident production events | Hash/revision ideas exist; no signed event chain or external anchoring | ADAPT pattern, BUILD protocol |
| Evidence-linked recall explanations | Reports can preserve evidence snapshots, but not event-to-lot impact paths | ADAPT report renderer after graph core |
| Recall accuracy benchmarking | No manufacturing benchmark or query dataset | BUILD FRESH |
| Query-speed benchmarking | Reliability script measures API samples only | ADAPT harness, BUILD PS10 dataset/queries |
| Partner-scoped sharing | Consent and guest grants are reusable patterns | ADAPT after event authorization model |

## Smallest Safe PS10 Foundation

Build this vertical slice first, without committing to a final product name:

1. Organization, site, actor, product, material lot, component serial/lot, and finished-unit identifiers.
2. An append-only canonical event envelope with `eventId`, `eventTime`, `recordTime`, `eventType`, `subjectIds`, `source`, `destination`, `quantity`, `unit`, `location`, `businessStep`, `disposition`, and `evidenceRefs`.
3. A deterministic state-transition validator for create, receive, transform, consume, produce, split, merge, rework, and ship. Reject impossible transitions and negative quantities.
4. An EPCIS 2.0-compatible capture/query adapter. Store the canonical event and preserve the original event payload/hash for traceability.
5. A bounded forward/backward traversal query for one lot or unit, with depth and result limits.
6. A synthetic demo dataset: raw material receipt -> split -> component production -> assembly -> rework -> shipment, plus one defect and recall impact query.
7. A read-only product-passport view generated from a pinned event set. Sharing and consent can be adapted later, but must not bypass event authorization.

This slice proves the PS10 value proposition: “where did this product come from, what did it become, and which shipped units are affected?” It does not attempt supplier onboarding packs, OCR, external verification, blockchain, or a generalized workflow platform.

## Architectural Coupling Risks

1. **Business-centric schema coupling:** Reusing `Business` and `Document` directly would make material lots look like MSME evidence and make future migrations difficult. Use a separate bounded context and explicit adapters.
2. **Consent versus custody:** PRAMAAN consent answers who may see selected claims. It does not establish who handled a material or whether an event is true.
3. **Snapshot versus event history:** A Passport snapshot is a read artifact. It must never become the source of truth for production genealogy.
4. **SQLite write serialization:** The local demo's SQLite-first model is useful for prototyping but not a credible high-volume event store. Measure write contention and plan a production event-store boundary.
5. **Trust semantics:** PRAMAAN's deterministic checks intentionally avoid external verification and safety conclusions. Do not present them as product quality, regulatory compliance, or recall safety evidence.
6. **Privacy and tenant scope:** Supplier, customer, batch and shipment relationships may be commercially sensitive. Reusing guest-link semantics without a PS10 disclosure policy risks leaking partner topology.
7. **Unmerged branches:** Firewall PR #4 and OCR PR #5 are not part of main. OCR has additional licensing, isolation, queue/cache, and operational caveats. Do not make PS10 depend on either before separate acceptance.
8. **License ambiguity:** The absence of a root PRAMAAN license/NOTICE requires a legal/ownership decision before source extraction.

## Immediate Reuse versus Fresh Build

### Reuse immediately

- TypeScript/Express module conventions, Zod validation, error shape, request IDs, structured logging, Helmet/CORS/rate-limit baseline.
- Prisma migration/test conventions for control-plane data.
- Hashing, revision, immutable snapshot, transactional audit, and failure-injection test patterns.
- React/Vite shell and accessibility-oriented shared UI primitives for a demo console, after replacing domain copy and routes.

### Adapt

- Authentication into organization/site/operator scopes.
- Document/evidence artifacts into event evidence attachments.
- Consent/access grants into partner-scoped DPP views, with a new policy vocabulary.
- Report Composer into evidence-linked recall explanations.
- Readiness/check modules into deterministic event validity and data-quality checks only.

### Build fresh

- Manufacturing identity model and event ledger.
- EPCIS capture/query boundary and vocabulary validation.
- Quantity conservation and transformation semantics.
- Genealogy graph, traversal, impact analysis, and query indexes.
- Tamper-evidence protocol for production events.
- Recall benchmark dataset and accuracy/latency harness.

### Exclude from the first PS10 foundation

- OCR/document intelligence as a prerequisite.
- Blockchain or tokenization.
- Credit, lending, reputation, or trust scoring.
- External government/bank verification claims.
- Arbitrary pack builders or a general BPM platform.

## Acceptance Gates for the First Implementation

- Fresh database can apply all migrations without production data.
- Event IDs are unique and idempotent under retries.
- Invalid transitions and quantity mismatches are rejected atomically.
- Concurrent capture cannot create duplicate current states or negative balances.
- Historical event payloads and evidence references are immutable.
- Tenant and partner authorization is enforced on capture and query.
- Forward/backward traversal returns bounded, deterministic results.
- Defect impact results are reproducible against a seeded synthetic graph.
- Recall explanations identify source events and limitations without claiming regulatory certification.
- Benchmark reports include dataset seed, event count, query shape, p50/p95/p99 latency, result counts, and failure counts.
- Browser demo covers capture, genealogy, defect marking, impact query, and a read-only passport view at desktop and mobile widths.

## Conclusion

PRAMAAN is a useful engineering reference and possible control-plane component, not a manufacturing product core. Start PS10 with a separate event/genealogy bounded context and an EPCIS-compatible adapter. Reuse proven security, validation, snapshot, audit, and testing patterns only through explicit interfaces. The safest next step is a synthetic event-ledger vertical slice with no integration into PRAMAAN's production repository.

