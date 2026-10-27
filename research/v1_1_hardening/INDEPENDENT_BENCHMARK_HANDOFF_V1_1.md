# Independent benchmark handoff, v1.1 (preparation only)

**No independent case exists. Nothing here has been run against any candidate. No claim of independent validation is made or implied.** Every test on this branch was written by the candidate author (Claude): regression and adversarial tests, not independent evidence. If no independent author is available this must be disclosed in any report, and results may only be used to find failure modes.

This extends `research/lot_identity_ab/INDEPENDENT_REVIEW_HANDOFF.md` (roles, sealing, acceptance questions are unchanged) with the v1.1 behaviours and a package builder that keeps the candidate's code and tests away from the case author.

## Roles
- **Case author** (Codex if available, or a human): receives only the author package (below). Must not read `application/lot_identity.py`, `application/registry_binding.py`, `application/test_lot_identity_ab.py`, `application/test_v11_hardening.py` or anything under `research/`.
- **Ground-truth reviewer** (a different party from the author): fills `reviewer_worksheet.csv` per case (agree, disagree, contested) from the story and expected outcome **without** seeing candidate output.
- **Candidate runner** (Claude, after approval): freezes the candidate SHA, runs sealed cases once, publishes results unchanged.

## Author package
`python -B research/v1_1_hardening/make_author_package.py OUT_DIR` writes: the contract text for v1.1 (below), `case.schema.v1_1.json`, the v1.0 `case.schema.json`, a blank `reviewer_worksheet.csv`, `README_FOR_AUTHOR.txt`, and `MANIFEST.sha256` of everything written. It copies **no** implementation or test code.

## Behaviour contract the author may rely on
1. Lot identity is registry membership (positive match to a canonical lot, optional aliases, supplier scope, effective dates). Capture refuses unregistered, malformed, sentinel, withdrawn, expired, not-yet-effective, ambiguous lots (assembly, replacement); recall announcement refuses them too. A motor with unestablished identity is never current-release-eligible.
2. A checkpoint is bound to the registry in force when it was exported. Any registry change (or missing/invalid binding) holds every motor until the change is reviewed and a new checkpoint is accepted with explicit acknowledgement. Acceptance acknowledgements are operator assertions, not authentication.
3. An unknown or unregistered DE **or NDE** lot holds the motor (quarantine, not clearance). The recovery path is controlled replacement of that slot with a registered lot, a closed work order, and a newly accepted checkpoint. Original evidence is preserved.
4. An operator sighting of a label is stored as an UNVERIFIED claim, raw. It never installs, registers or excludes. An unresolved sighting holds the motor until that slot is physically re-installed.
5. An interrupted operation is an operational-integrity hold (its own reason), distinct from lot identity; retries are refused.
6. Not claimed: registry membership proves physical identity; the registry or acknowledgements are independently authenticated; atomic multi-event capture; crash recovery; production readiness.

## Families the author must cover (v1.0 list plus v1.1)
Everything in the v1.0 list, and:
- **Registry custody:** registry edited after acceptance; rolled back; legacy unknown lot registered retroactively; alias redirected; supplier changed; effective dates altered; old checkpoint with new registry and the reverse; valid update followed by review and a new accepted checkpoint; missing/corrupted sidecar; update with and without acknowledgement.
- **NDE and DE recovery:** unknown NDE; unknown DE; both; replacement with registered, withdrawn and unregistered lots; replacement in the wrong slot; replacement interrupted midway; renewal before and after.
- **Unverified sightings:** misread labels (`BR-2O4`), sentinel text, the recalled lot name, empty text, sightings in either slot, sightings followed by re-installation, sightings under the historical basis.
- **Integrity:** crash after each event of assembly and replacement; retry; shipment after an interrupted build; checkpoint renewal with an interrupted unit.
- **Combined:** two simultaneous problems (for example an interrupted replacement on a motor whose NDE is unknown); registry change plus sighting.

## Sealing and scoring (unchanged)
30 percent development cases, 70 percent sealed; manifest of sha256 hashes committed **before** any run and before the candidate commit is chosen; ground-truth reviewer verdicts recorded first; one confirmatory run; contested cases scored separately; no tuning against sealed cases; a candidate change creates a new version and a new split.

Acceptance questions (owner to confirm): zero cases where a motor with unestablished identity ends current-eligible; zero unintended holds on cases the reviewer agrees are legitimate (count reported, contested not hidden); every hold and refusal carries a reason class the reviewer agrees with; for v1.1 additionally, zero cases where a registry change raises eligibility under an older checkpoint.

## Addendum (FORMAT_V3 branch `research/v1-1-format-v3-registry-binding`)
- Contract item 2 now reads: a checkpoint carries, **inside its checksummed body**, the digest of the registry accepted with it (FORMAT_V3). A checkpoint of an older format can still prove history but never grants current eligibility. A registry-only change with no new ledger events still needs a newly accepted checkpoint, with explicit registry acknowledgement.
- Practical constraints for authors: motor serials must match `MTR-[A-Z0-9-]{3,30}` (for example `MTR-91011`); a `bypass` assembly copies supplier fields from the case registry when the registry knows the lot, otherwise uses a default supplier; the runner creates the initial checkpoint after all listed motors exist and before the first step.
- Roles, pre-registration and sealing are specified in `research/v1_1_format_v3/benchmark/PREREGISTRATION_TEMPLATE.md`; the runner is `benchmark/run_cases.py`; hashing is `benchmark/seal_manifest.py`. The three samples under `benchmark/samples/` were written by the candidate engineer and exist only to check that the runner works. **They are not evidence and must not be scored or shown to the author.**
