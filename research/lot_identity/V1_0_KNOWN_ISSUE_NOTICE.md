# Known issue notice for `manufacturing-demo-v1.0` (proposed demo-guidance text)

**Status: v1.0 (`c25466c`) is AFFECTED by a reproduced lot-identity clearance defect (P0).** A corrected baseline has not been validated. The tag is kept unchanged as the known-vulnerable historical baseline.

What is affected: the demonstration treats any lot string that is not exactly the recalled lot as evidence that a bearing is unaffected. An unknown, sentinel (`UNKNOWN`, `N/A`), mistyped or look-alike lot (`BR-2O4`, `br-204`, trailing space, hidden characters) or any unregistered string can therefore produce `RELEASE_ELIGIBLE`, and, after the checkpoint is accepted, `currentReleaseEligible: true`.

Presenter rules until a validated fix exists:
1. Do not describe `RELEASE_ELIGIBLE`, "excluded with evidence" or the eligibility flag as robust to wrong or mistyped lot identities, or as proof that a bearing is not from a recalled lot.
2. Say that lot identity in this demo is operator-entered text on synthetic data; there is no lot master and no supplier authentication.
3. Do not demonstrate entering unknown or look-alike lots as a success case; if asked, show it as the known defect.
4. The checkpoint review shows only row counts; do not describe checkpoint acceptance as a check of lot identity or of independent custody.
5. Do not claim production readiness, independent safety certification, or hosted-CI results for any corrected build.

Evidence: `research/audit-unknown-lot-safety` (`UNKNOWN_LOT_AUDIT.md`) and `research/p0-lot-identity-remediation` (`P0_LOT_IDENTITY_REMEDIATION.md`).
