# Controlled release candidate: pre-change review

Date: 2026-10-23. Status: REVISE; no safety closure or merge authorization.

## Provenance and scope

Start: frontend-branded-views 7482fc1fab759bfd7c3a3eedd7946eae62895a18. Verified ancestors: audited base f9282101159b6b6806974848d7c351999098d792; DPP caf651f60ef9a6444239401cee4609ad9eaf188f; Investigation 899456252c74f76cd30527baaa7dc778686ff62d; Impact 68cdef8a507378bc291493c3bb0ce5ee6d22d45b; three-features 73f3bdbd78ee8bdf4b323457ba2f036f16fb82d9; Phase A cf97c1d4998f45c5060bd8d33a7b00a8fa545ed9. Do not remerge these branches.

Prepare a separate merge of exact H1/H2 f9dcf56ae52b095a3af05b8fc45a2568cd5642fe. It remains REVISE under independent audit e63bf90919b1765ef9d7d00f60a69c713323c82c. Backend D2?D10 remediation is excluded. Hosted-green CI 04d974fd6307fca1f129be6b5683f4468b5fcad7 and reliability 6d177e8113b73212d7d39faf3208868c119d50f4 are references, not merged or certification of this tree.

## Original evidence before changes

Detached exact 748: TypeScript and production four-entry build pass. Original Vitest: 297 total, 287 pass, 10 fail (not 286 reported elsewhere). Original Playwright: 125 total, 102 pass, 23 fail, zero skipped/flaky; 332.586 seconds. JSON artifacts preserve every result, assertion and failure. Original tests are unchanged. Independent new challenges: 10 total, 5 pass, 5 fail. Original screenshots regenerated during tests are not source changes and are not imported.

## Confirmed defects before repair

| ID | Severity / scope | Reproduction / observed behavior | Proposed bounded repair |
|---|---|---|---|
| F1 | Medium, malformed live read model | Duplicate a unit, add unknown eligibility key: cardinalities match and gate is CURRENT | Unique unit/policy identities and exact decision/eligibility scope |
| F2 | Medium, contradictory live read model | Empty policy list conceals AFFECTED + RELEASE decision; gate is CURRENT | Validate decision scope before existing finding/action validator |
| F3 | Medium, incomplete obligation model | Required notification omits unitId; gate ignores it for release | Require structured known-motor notification identities and required fields |
| F4 | Medium, URL privacy | QR page URL with user:password leaks userinfo despite stripping query | Clear username and password |
| F5 | Medium, genealogy correctness | Shipment ID changed while cited MOTOR_SHIPPED event unchanged; graph draws fabricated ID | Require shipment ID and occurrence time to match actual cited event, else withhold edge and show issue |

These are frontend contract/privacy defects, not evidence of bypassing backend cryptographic verification. Threat assumptions: malformed or contradictory response supplied to browser. New tests are independent and preserve assertions. Additional original UI failures remain failures, not waived.

Main application still uses raw decision presentation and the older gate. H1 imports a global withholding panel; it does not supply the approved shared per-motor branded interface. This is an unresolved integration gap, not safe completion.

## Semantic proposal for protected frontend interface (before any edit)

App.tsx, freshness.ts and RecallDataSource.ts will not be edited in this bounded tranche. Future reviewed changes must use the shared typed gate for HTTP and command responses, keep four-second timeout, preserve abort/generation ordering and high-water tracking, permit per-motor clearance only through clearanceOf/CurrentClearance, and label fixture mode as synthetic without operational authority. CURRENT findings/holds must remain visible even when that motor has no clearance; another motor must not suppress them. WITHHELD clears motor records. Preview never supplies trust. No local anchor trust or server semantics changes.

There is a specification conflict: approved HistoricalView strips all decisions, while the new mission asks to preserve findings/holds when clearance unavailable. Asked owner whether PREFIX_ONLY remains facts-only or gets explicitly historical hold records. No answer at recording time. Do not silently extend that interface; leave main gate unification blocked rather than inventing semantics.

### R1?R20 semantic impact review

| Cases | Required invariant / effect of bounded fixes and proposed future interface |
|---|---|
| R1?R2 | ANCHOR_INVALID/rollback remains withheld; no regression reset |
| R3 | Restart prefix is historical, never current clearance |
| R4 | Exact trusted-checkpoint restart rollback residual remains explicitly undetectable |
| R5 | Legitimate extension requires checkpoint; holds preservation conflict must be resolved explicitly |
| R6?R8 | Backend replay authoritative; malformed frontend scope now rejected, no locally fabricated decisions |
| R9 | Forged resolutions remain forbidden; historical archives not migrated |
| R10 | Unevaluated ledger extension never earns eligibility |
| R11 | v1 cannot earn CURRENT; frontend does not manufacture anchor states |
| R12?R13 | No export, file or transaction semantics changes |
| R14 | Candidate is not trust; no promotion route |
| R15 | No chaining semantics change; known third-generation defect remains blocked |
| R16 | No legacy decision promoted to clearance |
| R17 | Typed gate hides raw backend exceptions; no new backend error contract |
| R18 | 503 remains unavailable, not throughput; four-second timeout unchanged |
| R19 | Policy extension requires new checkpoint; no browser policy inference |
| R20 | Preserve all original tests and pinned sources; failures reported explicitly |

This is a change review, not evidence that R1?R20 pass. No own H1 implementation is independently certified here. No engine, ledger, source fixture or CI inventory edits. No backend D2?D10 fixes authorized into this candidate.

## Owner clarification and main interface review (before edits)

Owner explicitly answered: "Retain facts-only PREFIX; preserve CURRENT findings/holds". This supersedes the pending-question status above. Main will use the same evaluateDetailed gate as the standalone pages. SEGREGATED gets only HistoricalView facts and an explicit warning, with no decision, notification-task or clearance rendering. WITHHELD and hidden/expired states drop all motor records. CURRENT permits the existing console's findings, evidence and history, with current action claims supplied through a branded GatedSnapshot resolver keyed by current decision ID. Historical versions and comparison output get explicit recorded-output labels, never current clearance. Fleet current clearance counts use that resolver rather than raw release actions. Fixture mode remains explicitly synthetic and cannot mint current clearance. Backend command responses pass the same gate, including PREFIX after writes; controls remain disabled until a new covering independently activated checkpoint makes the view CURRENT.

The protected files will change only as described: RecallDataSource routes successful snapshot bodies through the shared gate, preserves latest-request rejection, timeout/abort, and emits neutral typed gate errors for failed HTTP; freshness becomes a strict CURRENT-only compatibility bridge; App owns visibility/lease and typed state, removes old global/per-fleet withholding and historical-error fallback, and renders facts-only for SEGREGATED. No new trust states or activation workflow. R1?R20 table above applies; R5 holds remain visible only in CURRENT per explicit owner clarification, while PREFIX is facts-only. Existing H1 browser assertion expecting a PREFIX hold list becomes a documented contract conflict, preserved as a failure, not edited away.

## Browser harness finding before isolated rerun

Full integrated default browser invocation aborted with zero tests: port 4173 is occupied by Claude's active audit process (confirmed command line, left untouched). The exact source suite also introduces a 4185 reuse between H1 checkpoint.spec.ts and Passport's external-writer test. Default two-worker execution can overlap them. Preserve both tests unchanged. Add a separate RC configuration: own server 4340, one worker, no reuse, four-second product freshness unchanged. A legacy QR assertion hardcoding 4173 will be reported as a port-specific contract assumption, not edited or accepted as PASS. Do not kill another agent's server. This is test harness isolation, not a product fix.
