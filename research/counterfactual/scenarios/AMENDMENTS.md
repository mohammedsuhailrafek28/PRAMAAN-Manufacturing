# Scenario amendments (Experiment A)

Scenarios were first committed at `6ba87ce` (before any candidate ran). Any later change to a scenario file is listed here with the
reason, and the manifest is regenerated. No amendment was made after seeing a candidate's results.

## AM-1 (before any candidate result existed): A04 access evidence

Original A04 modelled the missing station access record as a *lost record* of source QA-02 (sequence 1 counted in the watermark).
While writing the operation catalog I noticed that this makes any later QA-02 evidence (a hypothetical verification) expose that
unrecovered sequence gap, so the scenario no longer tested "two equally small independent clearances". The author's intent for A04
was unchanged. A04 now models the access evidence as a record that was never captured but can be retrieved from the station fixture
archive (`ARCHIVE_ACCESS`: occurredAt inside the work-order window, recordedAt now). The old lost-record variant remains a useful
interaction and is noted as an observation in the report (an evaluator behaviour, not a defect of the experiment):
`integrity.check` only checks sequence completeness for sources with at least one visible event, so a source whose records are
*all* missing produces no SOURCE_SEQUENCE_GAP.

Also under AM-1: the facts key `accessEvidenceRecoverable` was renamed `accessEvidenceArchive` in every scenario file (default false).
Only A04 sets it true; no other scenario changed meaning.
