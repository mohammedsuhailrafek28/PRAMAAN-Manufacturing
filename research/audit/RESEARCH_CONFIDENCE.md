# Updated research confidence for candidates A and B (no winner selected)

Evidence base: self-authored synthetic spikes plus the unknown-lot audit. Confidence below is about whether further research is justified, not about readiness. Neither candidate is selected, frozen or recommended for build.

| | A Counterfactual Recall | B Contradiction Intelligence |
|---|---|---|
| Earlier stance | REVISE | GO (conditional) |
| What the audit changes | The evaluator clears motors on exact lot-string mismatch, so the counterfactual search's "what would clear this" can propose or accept evidence built on an unrecognised lot string. The oracle equality (18/18) holds relative to the evaluator, and the evaluator itself can be wrong on identity. | B's diagnostic for unknown identity (`diagnosticUnknownIdentityWouldBeReadAsUnaffected`) now has a real production-path counterpart: contested identity can silently become an exclusion. B's value proposition (flag exclusions resting on contested records) is more relevant, but its DEFINITE labels need master data that does not exist. |
| Confidence that the idea works as specified | medium on search correctness (exhaustive oracle); low on usefulness (the catalog is unvalidated and obtainability is unknown) | medium on detection logic against its own rules; low on classification under wrong or missing master data (probes P1 to P4) |
| Confidence in evidence quality | low (single author, hand-written catalog and scenarios) | low (single author, same rules for fleets, truth and detector) |
| Main open risk | physically unobtainable or incomplete catalog yields false promises or false "no path" | false DEFINITE under serial reuse, lot relabelling, incomplete removal records, clock error; cross-motor claims are an unvalidated data source |
| Dependency on the lot-identity decision | high (clearance rests on the evaluator's exclusion) | high (impact reasoning rests on the evaluator's identity reading) |
| Stance after this review | HOLD pending independent benchmark and owner decision on identity | CONTINUE research only under the approved read-only advisory boundary; refuse DEFINITE without master data; pending independent benchmark |

Both stances are research-process positions. The owner decides; nothing is selected. Prior-art notes in each REPORT.md stand unchanged (novelty-risk A medium-high, B medium; no invention or superiority claim is supported).

What would change these assessments: independent authors (benchmark spec), a decision on the identity model (audit), real or externally grounded examples, and a user study of how advisory text is read.
