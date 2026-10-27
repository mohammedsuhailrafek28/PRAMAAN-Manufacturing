# Independent benchmark: handoff for an independent case author and a separate ground-truth reviewer

Status: **preparation only. Nothing here has been run against any candidate and no sealed case exists yet.** The candidate author (Claude) wrote all tests in this branch; they are regression and adversarial tests, **not independent evidence**. If no independent author is available, that must be disclosed in any report and the results used only to find failure modes.

## Roles
- **Case author** (for example Codex, or a human): has not read `application/lot_identity.py`, `application/test_lot_identity_ab.py` or the earlier prototype tests. Receives only the package below.
- **Ground-truth reviewer** (a different party): reads each case's physical scenario and the author's expected outcome and records agree, disagree or contested, without seeing candidate output.
- **Candidate runner** (Claude, once approved): freezes the candidate commit, runs the sealed cases once, publishes results unchanged.

## Package given to the case author
1. `docs` of the data model: event types and payload fields (`application/service.py` capture sequence is described, not shared as test code), the evaluator semantics summary, and the recall-policy fields.
2. The lot-identity contract (`P0_LOT_IDENTITY_REMEDIATION.md` section 2 and `AB_CANDIDATE_REPORT.md` section "Identity contract").
3. `case.schema.json` (this directory) and the instructions below.
4. Explicit statement of what is **not** claimed: registry membership does not prove physical identity; the registry is locally authored synthetic data.

## What to write (each case is one JSON file validating against `case.schema.json`)
- A short physical story (what actually happened on the line), the registry document in force, the recall policy, one or more motors with their installed lots per slot and capture route (`service`, or `bypass` for records that did not pass the validating commands), and any registry change after capture.
- The author's **expected outcome per motor**: `mustHold` (true/false) and the reason class expected when held. Uncertain cases are marked `contested: true`, never forced.
- The author's citation or reasoning for the expectation. Prefer cases grounded in public recall notices or quality write-ups (cite them); mark invented parts as invented.

## Required adversarial families (the owner's list)
Unknown, N/A, empty, whitespace lots; case, punctuation and Unicode near-misses; wholly different unregistered strings; valid registered unaffected lots **including lots numerically adjacent to the recalled lot**; valid recalled lots; conflicting aliases and supplier scopes; initial assembly, replacement and observation; DE and NDE; scoped and unspecified recalls; interrupted operations; checkpoint renewal after ambiguity; attempts to inject false eligibility through the API or static previews; registry changes (withdrawal, expiry, late effectiveness, retroactive registration); the recall naming an unregistered lot; legacy records captured before the registry existed.

## Sealing
1. Author delivers cases; 30 percent are designated development cases (visible to the candidate author), 70 percent sealed.
2. A manifest of sha256 hashes of every sealed file is committed to this repository before any candidate run; the candidate commit hash is frozen first.
3. Ground-truth review is recorded per case (agree, disagree, contested) before the run. Contested cases are scored separately.
4. One confirmatory run; results committed unchanged, failures reported as failures. Any candidate change afterwards is a new version needing a fresh sealed split.
5. Do not tune the candidate against sealed cases. Do not reuse the candidate author's fixtures as independent evidence.

## Proposed acceptance questions (owner to confirm)
- Zero cases where a motor with an unestablished identity ends current-eligible.
- Zero unintended holds on cases the reviewer agrees are legitimate registered lots (report the count, do not hide contested ones).
- Every refusal and every hold carries a reason class that the reviewer agrees is correct.
