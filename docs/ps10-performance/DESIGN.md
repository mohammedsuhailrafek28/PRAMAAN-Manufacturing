# PS10 isolated impact-query design

Base: manufacturing-demo-v1.2 = 6709b0c6f521006cf6332caeecec6b08dbd44e84. Branch feature/ps10-performance. No lifecycle changes imported.

Add only performance/impact_query.py, focused tests, benchmark and evidence/docs. Do not edit frontend, ledger, evaluator, service, checkpoint, shipment gate, F5/F6 or A7. No HTTP integration or new permission/trust surface. No source/frozen manifest rewrite.

Existing Ledger.watermark and Ledger.snapshot each call _verified_rows (hash original documents, decode/schema validate, compare derived records, verify per-motor hash chain). Full service snapshot also issues/replays full fleet decisions and constructs comparison/read models. Do not use bare SQL lot filtering: a deleted index field, unknown observation or unknown lot could silently remove exposure.

Build the in-memory inverted candidate index only after unchanged ledger verification of EVERY motor succeeds. Full SQLite snapshot-image plus registry content digest is recomputed for EVERY query in a single SQLite read transaction (force a read, then Connection.serialize and SHA-256; includes WAL-visible pages, not a bare database-file hash); matching bytes reuse the already verified facts, not a head/count/mtime proof. Any changed evidence invalidates the reader until explicit rebuild. SQL read transaction linearizes results before a concurrent writer; no claimed later state. Registry content is included. Unknown query lot returns every motor, never an empty negative. Sighting/coverage/identity/interruption/slot uncertainty is over-included across queries. Historical install/remove/correction evidence is not pruned. Recorded shipments carry original ledger evidence, never an authorization.

No decisions or current clearance are returned. This is evidence-backed potential-impact retrieval, not recall evaluation and not an independently authenticated ledger. Existing checkpoint/clearance/shipment safeguards remain the only authorization path. H2/A7/F5/F6 operations are unchanged. No disk index may be trusted on restart. Query cost remains linear in all input bytes; report that floor honestly at100/1000/10000, including cold rebuild and output/serialization separately.


## Bounded follow-up after first scale measurement

The full-object path at10000 measured1.253s p95 including JSON, so it did NOT meet sub-second. Preserve that result. Add a ready-to-send immutable JSON method, bounded to eight payloads, still recomputing the entire database-image digest and registry digest on every call. First novel-lot projection/encoding is measured separately; do not conflate warm serialization reuse with cold first request. No raw object cache is returned to callers. Any write invalidates it.

Retain an in-process monotonic inventory/configuration/event-hash set across rebuilds. Rebuild cannot erase previously observed motors, rewrite their provisioning, or remove earlier event hashes. This does not substitute for an independently protected checkpoint and cannot detect a consistent pre-start rollback. No operational trust is acquired. No disk cache on restart. Added focused tests prove invalidation on same-count raw tampering, concurrent commits, missing motors, changed config, unknown/sighted lots, immutable byte responses and read-only/no-clearance behavior.
