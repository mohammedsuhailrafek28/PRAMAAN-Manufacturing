# PS10 data integration layer

Branch `feature/ps10-data-integration`, from `manufacturing-demo-v1.2` (`6709b0c6f521006cf6332caeecec6b08dbd44e84`). Synthetic data only. The recall evaluator
(`recall-engine/`), `integration/`, the ledger rules, checkpoint rules and freshness, the shipment gate (`Manufacturing.ship`), the identity guard, release eligibility,
F5/F6, A7 and the frontend are **not modified**. No lifecycle-branch or performance-branch change is included.

## 1. What it does

A configurable layer between manufacturing systems and the existing EPCIS-compatible capture path. It reads CSV and JSON exports from ERP, MES, SCADA, quality-inspection
and logistics systems; maps their fields to one canonical event schema; validates identities, timestamps, required fields and relationships between records; detects
missing, duplicate and contradictory records; keeps the original records, provenance and every transformation; shows a preview of what is accepted, rejected and
unresolved; and, only on an explicit `import`, writes the accepted evidence through `Manufacturing`'s existing capture path. Importing twice does not write an event twice.

It is a **data-quality and provenance layer, not a verification layer.** Everything it imports is a claim made by a source system. See section 9.

Libraries (as requested): **Pandas** (tabular handling, duplicate grouping, report tables and CSV output), **Pydantic v2** (canonical event and per-kind attribute models,
mapping configuration, report models), **Frictionless** (Table Schema validation of the mapped table: required, pattern, closed vocabulary, with row/field error positions).
Versions at validation: pandas 3.1.0, pydantic 2.14.1, frictionless 5.21.0, Python 3.12.10.

## 2. Pipeline

```
export file (bytes, sha256)                                         application/dataintegration/
  -> read_rows        CSV (stdlib csv, exact cells) or JSON (duplicate keys / NaN refused, nested paths flattened)   ingest.py
  -> map + transform  column mapping, named transformations, value maps, timestamps -> UTC; every changed value is a Step   mapping.py
  -> validate         Frictionless schema over the mapped table (required / pattern / enum)                          ingest.py
  -> adapter          source-specific meaning -> CanonicalEvent (Pydantic per-kind attributes)                        adapters.py, canonical.py
  -> duplicates       same (system, record id) across the supplied files (pandas groupby)                             ingest.py
  -> plan             repeat-import check, identity, relationships, work-order grouping, dry-run of the ledger profile planner.py
  -> PREVIEW          report only; nothing written anywhere                                                          report.py
  -> IMPORT           staging store first, then ledger capture of exactly the planned events, then dispositions       importer.py, capture.py, staging.py
```

`run(..., commit=False)` and `run(..., commit=True)` call the same `plan()`; import executes the plan the preview printed (tested: same planned event ids, same dispositions).

## 3. Canonical event schema (`canonical.py`)

`CanonicalEvent`: `canonicalId` (system + source record id + kind), `contentSha256` (what the source said), `sourceSystem`, `sourceRecordId`, `kind`, `motorSerial`, `occurredAt`
(whole-second UTC), `attributes` (validated by a per-kind Pydantic model), `claim = RECORDED_CLAIM_FROM_SOURCE_SYSTEM`, `independentlyVerified` (the type only admits `False`).
Keys such as `verified`, `trusted`, `clearance`, `releaseEligible`, `currentReleaseEligible`, `recallStatus` are rejected by name.

| Source | Canonical kind | Ledger result |
|---|---|---|
| ERP lot issue | `BEARING_LOT_ISSUED` | `MATERIAL_ALLOCATED` + `BEARING_MANUFACTURED` (role `MATERIAL`) |
| MES open / install / remove / close | `WORK_ORDER_OPENED`, `COMPONENT_INSTALLED`, `COMPONENT_REMOVED`, `WORK_ORDER_CLOSED` | same event types (roles `MES`, `ASSY`, `REWORK`) |
| Logistics dispatch | `SHIPMENT_DISPATCHED` | `MOTOR_SHIPPED` (role `SHIP`), historical record, **disabled by default** (explicit opt-in) |
| SCADA tag sample | `PROCESS_SIGNAL` | **staged only** |
| Quality inspection | `QUALITY_INSPECTION` | **staged only** |

Why SCADA and quality are staged only: the baseline ledger has no process-signal type, and its only inspection type, `INSPECTION_RECORDED`, is read by the recall policy and
work-order logic and is written by the `QA` role, which is the configured *trusted verifier* source. Writing imported inspection claims there would turn a claim into evidence the
evaluator treats specially. They are validated, related to the motor and work order, preserved, and reported, but never become ledger events or influence a decision.
(The lifecycle branch adds a dedicated, non-influencing type; whether to use it is an integration decision for the owner.)

## 4. Mappings and adapters

Five bundled mappings in `application/dataintegration/mappings/` (`erp.lot_issue`, `mes.assembly`, `scada.station_signal`, `quality.inspection`, `logistics.dispatch`, each `*.v1.json`).
A mapping (`MappingConfig`) declares: `sourceSystem`, `adapter`, `format`, `delimiter`/`encoding`/`recordsPath`, `fields` (canonical field -> source column, or dotted JSON path, or a
list of columns joined with `/`; `required`, `transforms`, `valueMap`, `pattern`, `allowed`), `timestamps` (field, **mandatory IANA time zone** for offset-less values, formats), `valueMaps`,
adapter `options` (SCADA tag ranges) and `capture` defaults. Unknown keys, transforms, adapters or zones are refused at load. The mapping's sha256 is stored with every file and run.

Transformations: `strip`, `upper`, `lower`, `collapse_space`, `motor_serial` (`mtr 27009` -> `MTR-27009`), `decimal_comma`, `null_if_blank`. **No transformation is applied to a bearing lot**:
the existing registry accepts an exact string or a declared alias only, and so does this layer (`NSB-204` resolves to `BR-204`; `br-310 ` does not resolve and is reported with look-alike hints).

Example: the sample exports differ on purpose. ERP: semicolon CSV, day-first local time (IST), `BELNR`+`POSNR` as record id. MES: comma CSV, ISO-8601. Quality: tab-separated, local time.
SCADA and logistics: JSON with nested objects. Changing a column name in a source system means editing one mapping file (tested: a renamed-column mapping yields identical canonical content hashes).

New source: add a mapping JSON and, if its meaning differs, an adapter function registered in `adapters.ADAPTERS`.

## 5. Validation and detection

Issue codes (`ERROR` decides the outcome; `WARNING` never blocks):

| Group | Codes | Outcome |
|---|---|---|
| File | `FILE_UNREADABLE` (encoding, empty, invalid JSON, duplicate JSON key, NaN, duplicate header, records path missing), `MISSING_COLUMN` | whole file REJECTED, nothing read |
| Row / field | `MALFORMED_ROW`, `MISSING_REQUIRED`, `BAD_FORMAT`, `BAD_VALUE`, `BAD_TIMESTAMP`, `BAD_IDENTITY`, `BAD_SIGNAL_QUALITY` | REJECTED |
| Duplicate | `EXACT_DUPLICATE_IN_BATCH` | later copy REJECTED, first kept |
| Contradiction | `CONTRADICTORY_DUPLICATE` (same record id, different content: no copy used), `CONTRADICTORY_LOT` (ERP issued X, MES installed Y at the same position), `CONTRADICTORY_SERIAL`, `CONTRADICTORY_IDENTITY`, `CONTRADICTS_REGISTRY` (ERP raw lot / supplier differ from the registry), `CONTRADICTS_PRIOR_IMPORT` (record id already imported with other content: the append-only ledger keeps the earlier record), `REMOVAL_MISMATCH`, `SECOND_SHIPMENT`, `WORK_ORDER_ID_REUSED`, `PARTIAL_PRIOR_IMPORT` | UNRESOLVED |
| Missing | `MISSING_UPSTREAM` (install without an ERP lot issue), `MISSING_WORK_ORDER`, `MISSING_ASSEMBLY` (dispatch without a completed build order), `MISSING_IDENTITY`, `OBLIGATIONS_NOT_MET` (close COMPLETED with positions not done), `UNKNOWN_MOTOR`, `UNKNOWN_WORK_ORDER`, `REMOVAL_REQUIRED` | UNRESOLVED |
| Order / window | `TIME_ORDER`, `OUTSIDE_WORK_ORDER_WINDOW` | UNRESOLVED |
| Identity | `UNRESOLVED_LOT` (registry status in the message) | UNRESOLVED |
| Held | `WORK_ORDER_GROUP_HELD` | UNRESOLVED |
| Warnings | `NO_MATCHING_INSTALL`, `INSPECTION_FAILED_BEFORE_SHIPMENT`, `INSPECTED_COMPONENT_NOT_RECORDED`, `CLOSED_CANCELLED_WITH_OPEN_OBLIGATIONS` | ACCEPTED with warning |

**Work orders are all-or-nothing.** If one record of an order cannot be accepted, the whole order is held and nothing of it is written, so a data defect cannot leave a half-built,
"interrupted" order in the ledger. An in-progress order whose records are all acceptable is captured as it stands.

Outcomes per record: `ACCEPTED` (disposition `CAPTURE`, `STAGE_ONLY` or `ALREADY_IMPORTED`), `REJECTED`, `UNRESOLVED`. Every row has exactly one.

## 6. Provenance, transformation history, repeatability

`staging.py` (separate SQLite file, append-only by trigger): `source_files` (the original bytes + sha256 + mapping id and sha), `source_records` (each row verbatim), `transformations`
(field, step, before, after, in order), `canonical_events`, `runs`/`run_results` (tool versions, ledger head before/after, report digest), `dispositions` (every decision of every run).

Each ledger event the layer writes carries `evidenceRefs = ["pramaan-import:v1:<canonicalId>:<content16>"]` inside the hashed, chained capture document. A later run recognises
what was already written from the **ledger itself**: same id and content = `ALREADY_IMPORTED` (also after the staging file is lost; tested), same id and other content =
`CONTRADICTS_PRIOR_IMPORT`, a record with only some of its events present = `PARTIAL_PRIOR_IMPORT`. Staged-only records use the staging history for the same check.

`capture.native_event` rebuilds `Manufacturing.event` exactly except for that reference; a test asserts byte-identical events and hashes when the same evidence reference is given.
Before any write, the planner dry-runs the ledger profile (`validate_native`) and the source-role capability list, because a ledger rejection permanently blocks a motor.
`execute()` checks the ledger's sequence for every planned event first and stops with `CaptureMismatch` (before writing) if the ledger moved after the plan was made.

## 7. Time

`occurredAt` is the source's claimed time, converted to UTC (offset-less values use the mapping's declared zone; fractional seconds are truncated and that is a recorded step). Producer
`recordedAt` and `timeSource = SYNTHETIC_SIMULATED` are the existing application clock's, exactly as for every other captured event. A source time later than that clock is refused (`UNRESOLVED_TIME_OUT_OF_WINDOW`); an import never moves the shared clock to a source time (see `PS10_INTEGRATION_HARDENING.md`). Nothing in the ledger says a source clock was accurate.

## 8. Reproduction

All commands from the repository root with a Python 3.12 environment that has the three libraries (hash-pinned in `ci/requirements-data-integration.lock`):

```
python -m venv .venv
.venv/Scripts/python -m pip install --require-hashes -r ci/requirements-windows.lock -r ci/requirements-hackathon-crypto.lock -r ci/requirements-data-integration.lock

python -B -m application.dataintegration.samples.generate            # re-create the synthetic exports (committed copies must match; tested)
python -B -m application.dataintegration demo --workdir out/di-demo   # end-to-end, writes reports under out/di-demo/run1/reports
python -B -m application.dataintegration preview --source ERP=application/dataintegration/samples/batch1/erp_lot_issue.csv --source MES=application/dataintegration/samples/batch1/mes_assembly.csv --create-units
python -B -m application.dataintegration import  --source ... --ledger out/l.sqlite --staging out/s.sqlite --create-units --historical-shipments --out out/reports
python -B -m unittest application.test_data_integration -v            # 55 tests, about 12 s
```

Demo (synthetic batch 1 = 73 records from five systems, batch 2 = 7 new records, re-sent files):

| Step | Accepted | Rejected | Unresolved | Ledger events written |
|---|---|---|---|---|
| 1 preview batch 1 (no ledger) | 37 (32 capture, 5 staged only) | 8 | 28 | 0 (45 planned, 9 units) |
| 2 import batch 1 | 37 | 8 | 28 | 45 |
| 3 import batch 1 again | 38 (all already imported, incl. the two duplicate copies) | 7 (field-level) | 28 | **0** |
| 4 import batch 2 + re-sent batch 1 | 48 (10 new capture) | 7 | 25 | 12 |

Defects planted in batch 1 and where they land: impossible calendar date, missing motor, unmapped event code, ragged CSV row, implausible and BAD-quality SCADA samples (REJECTED);
exact duplicate ERP and MES rows (REJECTED); conflicting ERP duplicate and a shipment id used for two motors (UNRESOLVED); ERP vs MES lot mismatch (MTR-27003); unregistered lot and a
look-alike spelling (MTR-27004, MTR-27013); install with no ERP issue (MTR-27005, resolved by batch 2); shipment before the order closed (MTR-27007); SCADA sample outside its order window
or tied to no motor; inspection of an unknown motor; a shipped motor with an earlier recorded FAIL (MTR-27008: accepted with a warning). Batch 2 completes MTR-27005, records a rework of
MTR-27001 (removal of the DE bearing it ends, replacement installed) and flags a re-sent record whose content changed. After the demo the ledger has 57 events and 0 rejections.

Read-only recall evaluation of the imported evidence (existing `announce` + `snapshot`, lot BR-204 at the drive end, no checkpoint): MTR-27002 (alias NSB-204) and MTR-27008 `AFFECTED / RECALL_HOLD`;
MTR-27001 `REPLACED_WITH_UNAFFECTED_LOT`; the motors with held or incomplete records `UNRESOLVED / RECALL_HOLD`; **no motor is release eligible** (`currentReleaseEligible=false` for all 9).

## 9. What is and is not established

| Statement | Status |
|---|---|
| A source system exported this record, with these bytes | Established (sha256 of the file, stored original, row verbatim) |
| The record was transformed as listed | Established (ordered steps with before/after) |
| The ledger contains an event derived from this record | Established (event id and `evidenceRefs` reference; hash chain verified by the ledger) |
| The physical event happened, the part/lot/serial is the one named, the operator/station/time are real | **Not established** (recorded claim) |
| The source system is authenticated or its clock correct | **Not established** |
| A bearing is correct, an inspection took place, a motor is safe or release eligible | **Not established**; the layer cannot set any of these |

Safety properties, each tested in `application/test_data_integration.py`: preview writes nothing; import = preview; no event written twice (also without the staging store); events
byte-identical to the service's; ledger validation and hash chain intact (0 rejections, `snapshot()` verifies); the layer never uses the `QA`/`HANDHELD` roles, never writes
`INSPECTION_RECORDED`/`SLOT_STATE_VERIFIED`, never calls `ship`, a checkpoint or the evaluator (source scan); no imported motor is release eligible; importing after a checkpoint moves
the ledger to `ANCHORED_PREFIX_ONLY` (existing semantics: new ledger evidence ends current clearance until a new checkpoint is accepted); shipment import needs explicit opt-in and does not
touch the ship tickets; unit creation needs explicit opt-in; the staging store refuses UPDATE and DELETE.

## 10. Limitations

- **Shipment import records history; it does not run the shipment gate.** A logistics record for a motor that is not currently eligible is still recorded as what the logistics system
  says happened (the recall evaluation then reflects it). Do not point it at a system that *requests* shipments.
- SCADA and quality records are staged, not evidence the evaluator sees (section 3).
- Positions are the application's `DE`/`NDE` bearings; component types other than bearings are not modelled. One build order per motor; later changes are rework orders. A rework needs
  the removed bearing to match the recorded occupant. Superseding or correcting an imported record is not supported: the ledger is append-only and a changed record is reported as a contradiction for review.
- `createMissingUnits` registers a motor with the application's fixed source configuration; a motor created this way and left with only ERP issues stays `UNRESOLVED / RECALL_HOLD` until its assembly is imported.
- Prior-run unresolved records are re-evaluated only when their file is supplied again (as in step 4); the layer does not queue them.
- The lot registry is the application's locally authored synthetic registry; a lot that resolves is declared in that file, not authenticated.
- Time zones: offset-less timestamps in a DST fold are not disambiguated beyond `zoneinfo`'s default.
- Performance was exercised at demo scale only (73 records import in about 1 s). Each captured event reads the motor's verified history, so cost grows with ledger size (see the core-performance audit); no scale claim is made.
- Source adapters cover the sample shapes; a real export will need its own mapping and probably adapter checks. Nothing here has seen real plant data.

## 11. Integration notes for the owner

- New files only under `application/dataintegration/`, `application/test_data_integration.py`, `ci/requirements-data-integration.lock`, docs. Modified existing files: `ci/run_gates.py` (one expected count), `.github/workflows/phase31-release-gates.yml` (install line + evidence path include the new lock).
- **No source-provenance pin changes**: `recall-engine/`, `experiments/foundation/`, `integration/`, `application/service.py` and `application/server.py` are byte-identical to the baseline (`git diff 6709b0c` is empty for them; gate K verified).
- New third-party dependencies (36 hash-pinned wheels) are the main review item: `ci/requirements-data-integration.lock`.
- `ci/frozen-source.json` and the CI inventory must be regenerated for the final source commit (see `docs/CI_INVENTORY_CHANGE_PS10_DATA_INTEGRATION.md`).
- Merge surface with the lifecycle and performance branches is limited to `ci/run_gates.py` (EXPECTED counts) and `ci/frozen-source.json`; the layer reads `Manufacturing` through its public methods.
