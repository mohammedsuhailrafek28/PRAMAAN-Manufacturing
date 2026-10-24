# Independent benchmark preparation and authorship plan (sealed; not run)

Scope: Counterfactual Recall Intelligence (A) and Evidence Contradiction Intelligence (B). Innovation selection is paused. **No candidate has been run against the benchmark described in the specification, and none will be until the owner approves.** Existing authored datasets and their ground truth are not altered.

## Sealed specification
- File: `research/audit/INDEPENDENT_BENCHMARK_SPEC.md` on branch `research/audit-unknown-lot-safety`, commit `ecc93e4`, sha256 `d20a96c5871c6c16b72ba8b84deabb2a773402f8c85da8b0d755e1724000f919`. Any change after owner approval must be an amendment entry, not an edit.
- Owner-approved addition (cross-motor reading): contradiction intelligence may read copies of evidence across motors; read-only, advisory only; no effect on evaluator results, clearance eligibility, trust semantics or checkpoint state.
- New adversarial family required by this review (add as F13 by amendment on approval): lot-identity dependence, meaning "unaffected" results that rest on an unregistered, look-alike, sentinel or conflicting lot identity, evaluated against the corrected baseline only (never against v1.0).

## Authorship plan (needs owner action)
1. Name at least one author and one case reviewer who have not read candidate code; preferably two authors working separately. If none is available, results are reported as "no independent evidence" and used only to find failure modes.
2. Authors get: data model, published evaluator semantics, the specification. They do not get candidate code, earlier datasets, or these prototypes.
3. Sources: externally grounded examples (public recall notices, quality/CAPA write-ups, EPCIS event semantics) with per-case citation; invented parts marked as invented.
4. Split: 30% development cases visible to candidate authors; 70% sealed. Hashes of the sealed files committed before any candidate run; candidate code frozen by commit hash first.
5. Expected outcomes and rationale committed before running; contested cases kept as contested.
6. Candidates are evaluated only on the corrected baseline selected by the owner (lot identity model decided first), so unaffected results are not inherited from the vulnerable behaviour.

## Not done, by instruction
No candidate run, no scoring, no case authored by me for the sealed split, no tuning against any authored set.
