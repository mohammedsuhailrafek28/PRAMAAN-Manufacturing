# Known issue: lot-identity clearance defect (P0), affects the demo builds

**Affected:** `manufacturing-demo-v1.0` (`c25466c`, reproduced end to end) and the runbook demo SHA `73f3bdbd` (decision level reproduced with an unanchored snapshot; the anchored/checkpoint path was not retested there). No validated fix exists yet; a corrected baseline has not been approved or tagged.

**What happens:** the evaluator treats any lot string that is not exactly the recalled lot as evidence that a bearing is unaffected. Unknown, sentinel (`UNKNOWN`, `N/A`), mistyped or look-alike lots (`BR-2O4`, `br-204`, trailing space, hidden characters) and any unregistered string can therefore yield `EXCLUDED_WITH_EVIDENCE` / `RELEASE_ELIGIBLE`; after the checkpoint is accepted on v1.0, `currentReleaseEligible` is `true`.

**Presenter rules until a validated fix exists**
1. Do not describe `RELEASE_ELIGIBLE`, "excluded with evidence" or the eligibility flag as robust to wrong or mistyped lot identities, or as proof a bearing is not from the recalled lot.
2. Say lot identity here is operator-entered text on synthetic data; there is no lot master and no supplier authentication.
3. Do not enter unknown or look-alike lots as a success case; if asked, present it as this known defect.
4. Do not describe checkpoint acceptance as a check of lot identity or of independent custody (the review shows only row counts).
5. Do not claim production readiness, independent safety certification, or hosted-CI results for any corrected build.

Evidence: branches `research/audit-unknown-lot-safety` and `research/p0-lot-identity-remediation` (reports `UNKNOWN_LOT_AUDIT.md`, `P0_LOT_IDENTITY_REMEDIATION.md`). Synthetic data only.
