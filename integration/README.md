# EPCIS → ledger → actual v3 recall integration

Local library and reproducible CLI validation only. No API, UI, Java service or
full EPCIS repository. Engine source remains byte-for-byte at `1620ed3`.

From this directory, using Python 3.12:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock
.venv/Scripts/python.exe -m unittest discover -s integration_tests -t . -v
```

For the complete validation, including the unchanged foundation checks, install
the separate **research-only** dependencies and use an external pinned GS1
checkout (not bundled with this code):

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-validation.txt
git clone https://github.com/gs1/EPCIS.git <external-gs1-directory>
git -C <external-gs1-directory> checkout 6f71468231838e424bb5dfa836e006e8dc69615c
.venv/Scripts/python.exe run_validation.py --gs1-checkout <external-gs1-directory>
```

Outputs are under `reports/`: test transcripts, original foundation results,
external schema/JSON-LD conformance, durable end-to-end demo, independent safety
matrix and benchmark methodology/results. Temporary SQLite databases are removed
after reports are generated. Re-running replaces generated reports.

Runtime dependencies are `jsonschema` (MIT), `rfc8785` (Apache-2.0) and their pinned
runtime closure. There are no OpenEPCIS Maven artifacts or unavailable CE
dependencies. PyLD and its LGPL-declaring frozendict dependency are validation
tools only; no upstream library source or GS1 schema/context is redistributed.

## Calling the integration

1. `Ledger(path)` opens a file-backed SQLite ledger, or `:memory:` for a test.
2. `register_motor(serial, sources=..., sessions=..., coverage=...)` provisions
   trusted configuration once. It requires motor-scoped producer streams,
   explicit source/actor/event permissions, authenticated session declarations,
   conservative v3 configuration and both DE/NDE position bindings. These are
   caller-supplied control-plane facts; this library does not authenticate a user,
   source credential, clock or physical label.
3. `capture(serial, original_bytes, producer_source=..., expected_sha256=...)`
   validates the wire profile, source/actor capability, session, sequence and
   references. The producer source must come from an already-authorized caller,
   not from an untrusted request header. `expected_sha256` checks content, not
   identity. Identical events are idempotent; corrected facts require a new ID
   and `supersedesEventId`.
4. `watermark(serial)` returns receipt positions. The caller explicitly selects
   the decision horizon; receipt positions alone do not attest factory coverage.
5. `genealogy(serial, full_watermark)` returns historical parent/child association
   claims, slot, lot/serial and references. It does not independently infer safe
   current state. Superseded claims remain visible as evidence.
6. `decide(serial, trusted_policy, [full_watermark], communicated=())` verifies
   complete source prefixes and evidence integrity, calls the real
   `evaluate_series(..., Config.v3())`, and persists immutable decision runs.
   It extends earlier recorded horizons automatically, preserving supersession
   across separate calls/restarts. Findings and reason codes come from the engine.
7. `replay(serial, trusted_policy, issued_bundle)` verifies persisted bundle,
   evidence/configuration/policy digests and calls the engine's actual replay.
   The integration only issues v3 records; engine-native v1/v2 replay remains
   supported and tested in the unchanged engine.

Use `bundle['manifest']['watermark']` at this boundary. It retains explicit zeros
for all registered sources; the engine's decision watermark omits zero entries.
Do not use a component-only history or engine-shortened watermark as a complete
motor evidence snapshot.

## Supported wire profile

`pramaan-bearing-epcis/1` supports EPCISDocument 2.0 with AssociationEvent ADD/DELETE
for installs/removals and ObjectEvent OBSERVE for supported native evidence types.
Each event contains a namespaced JSON-LD `trace` JSON literal. Event ID and
event time map to native `eventId` and `occurredAt`; all remaining native fields
are explicit in trace, including the payload and capture-session ID.

Only whole-second UTC timestamps and `+00:00` eventTimeZoneOffset are supported.
No timestamp rounding, source renumbering, lot/serial inference or UNKNOWN→EMPTY
conversion occurs. Parent/child URIs must agree with the explicit trace identity;
this slice uses its documented private URI namespace, not arbitrary GS1 identity
aliases. Unknown event types and incompatible wire forms are rejected.

Original document bytes, upstream `recordTime`, producer `recordedAt`, local
receipt time, original SHA-256, canonical event/configuration hashes and a chained
ledger hash are kept separately. Corrections never mutate earlier rows. SQLite
triggers disallow updates/deletes; replay verifies hashes against original bytes.
Hashes are not signatures or external anchoring against a database administrator.

Structurally invalid evidence persists a motor-level rejection block and produces
no decision. There is deliberately no automatic unblock path. Coherent claims of
conflicting physical operations are retained and held by the engine; dropping a
double-install or an affected observation would conceal risk. New evidence may
resolve engine ambiguity, but does not clear an ingress rejection block.

Read [the delivery report](../docs/PHASE2_INTEGRATION_REPORT.md) for measurements,
scope, limits and acceptance recommendation.
