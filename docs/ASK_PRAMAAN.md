# Ask PRAMAAN — local rule-based investigation assistant

A floating "?" button on every dashboard page opens a chat window. Answers come from a **fixed, deterministic rule engine**: no language model, no Gemini or other provider, no API key, no external request. It cannot release, hold, clear, approve or alter anything; the deterministic evaluator alone decides recall and release.

## Configuration
None beyond the existing `PRAMAAN_API_URL`. No key or provider variable is read.

## Flow
validate request (≤500 chars, ≤4 earlier questions) → GET verified snapshot → unknown motor/lot id → deterministic not-found → keyword intent router → answer template filled from the snapshot (motor questions also GET `/api/motors/:id/decisions` and require `assessDecisions` = CURRENT) → snapshot re-read; if the epoch changed the answer is withheld. Not anchored-current (prefix-only, unanchored, stale, decision-less) → no current decision is stated; answers are labelled NOT VERIFIED CURRENT. The browser marks any answer whose epoch differs from the dashboard's as HISTORICAL.

## Supported questions
Project overview · affected/held motors · why a motor is held · defective bearing lot · genealogy/traceability · evidence behind a decision · what is missing · corrective work / Resolution Trail · decision history · daily report summary · ML Quality Inspection (advisory steel-plate demo, separate from recall). A follow-up may reuse the last question that named exactly one motor; several or none → "Which motor do you mean?". Action requests (release, approve, clear…) are refused. Anything else lists what can be asked.

## Limits
Keyword matching: unusual phrasings fall to "can't answer that". Recorded data are claims, not independent custody; no production-readiness claim. Chat state lives in the browser tab only.
