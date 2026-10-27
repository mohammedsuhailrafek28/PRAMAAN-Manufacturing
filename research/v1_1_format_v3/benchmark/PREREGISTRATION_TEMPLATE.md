# Pre-registration of the independent evaluation (template; to be completed and committed BEFORE any sealed case is run)

Status of this file: **template, unsigned, nothing registered.** No independent case author, ground-truth reviewer or sealed case exists yet. Nothing in this repository counts as independent validation.

## Separation of roles (all three must be different parties)
| Role | Who (to be filled) | May see | Must not see |
|---|---|---|---|
| Blinded case author | ______ | author package only (`make_author_package.py` output) | any implementation, any test, any `research/` file, any candidate output |
| Ground-truth reviewer | ______ | each case's story and the author's expected outcome | candidate output, implementation, other reviewers' verdicts until submitted |
| Candidate engineer (Claude) | ______ | development split (30 percent) only, and the harness | sealed cases, sealed expectations, reviewer verdicts on sealed cases |

## Frozen before the run
- Candidate commit SHA: ________ (frozen first; any later candidate change = new version, new split)
- Runner: `research/v1_1_format_v3/benchmark/run_cases.py` at SHA ________ (generic; contains no case knowledge)
- Case schema: `research/v1_1_hardening/case.schema.v1_1.json` sha256 ________
- Sealed manifest: output of `seal_manifest.py` committed at SHA ________ **before** the candidate is chosen and before the run
- Split rule: 30 percent development / 70 percent sealed, assigned by a party other than the candidate engineer, by case id hash

## Hypotheses and metrics (confirm or amend before sealing)
H1. Zero sealed cases in which a motor the reviewer agrees must be held ends current-release-eligible.
H2. Zero sealed cases in which a registry or checkpoint-format change raises eligibility under an older checkpoint.
H3. Unintended holds on reviewer-agreed legitimate cases reported as a count with the list; contested cases reported separately and never counted as passes or failures.
H4. Every hold carries a reason class the reviewer agrees with (reviewer grades reason classes blind to the candidate's own labels).
Primary result: H1 and H2 counts. Secondary: H3, H4. No other metric may be introduced after sealing.

## Procedure
1. Author delivers cases; reviewer records AGREE / DISAGREE / CONTESTED per case **before** the run.
2. `seal_manifest.py` hashes every sealed case file; manifest committed; candidate SHA frozen.
3. One confirmatory run of the runner on the sealed set; output written unchanged to the repository.
4. Failures are reported as failures. No re-run after a fix on the same split. Disagreements between author and reviewer are resolved only by recording the reviewer's verdict, not by editing a case.
5. Report states exactly who authored, who reviewed, what was frozen when, and that same-host custody is not independent verification.

## Disclosures required in any report
The candidate engineer wrote the runner and all samples; samples are harness self-checks, not evidence. If the author or reviewer is not independent of the candidate engineer, the report must say so and the result is exploratory only.

Signed (author / reviewer / engineer / owner): ______  Date: ______
