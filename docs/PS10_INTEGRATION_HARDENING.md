# PS10 integration hardening (lifecycle + data integration, isolated candidate)

Branch `integration/ps10-hardening`, from `manufacturing-demo-v1.2` (`6709b0c6f521006cf6332caeecec6b08dbd44e84`) with `feature/ps10-lifecycle` (`5288610`) and `feature/ps10-data-integration` (`041a33f`) merged **for this candidate only**. Performance is not included. Synthetic data only; nothing here is production-ready, authenticated physical fact, or clearance.

## 1. Source times are checked before capture

Demonstrated failure: a source row dated 2099 made `capture_event` move the shared application clock to 2099; the ledger then refused the event (`Missing authorized capture session`, sessions end 2027-12-31T23:59:59Z) AFTER planning, and a ledger rejection blocks that motor permanently.

Now (`dataintegration/capture.py::time_problem`, one pure function used at four points):

| Where | Effect |
|---|---|
| planner, for every canonical record (all kinds, including staged-only quality / SCADA) | `UNRESOLVED_TIME_OUT_OF_WINDOW`; nothing is captured or staged as accepted |
| planner dry run per ledger event (`dry_run_problem`) | same, with the window of the motor's own provisioned session (or the `create_unit` default for a new unit) |
| `execute` pre-pass | every planned event is re-checked against the live clock before any unit is created or event written; `CaptureMismatch` otherwise |
| `capture_event` | `CaptureRefused` BEFORE `tick`, so the clock and ledger are untouched |

Refused: not exactly `YYYY-MM-DDTHH:MM:SSZ`; before the session start (2026-01-01); **after the application clock at all**; or whose projected `recordedAt` / repository time falls after the session end.

### 1a. Clock ratchet (final round)

The first round tolerated source times up to 24 h ahead of the clock and moved the clock to them (`tick(minimum=occurred)`), so repeated imports of records dated a day ahead could walk the synthetic clock forward without limit (up to the session end). Cause: capture used the source time as a clock input. Fix: `MAX_AHEAD_SECONDS = 0` and `capture_event` no longer calls `tick(minimum=...)`; the clock moves only by its own 30 s tick per event written, exactly like a native event (tested: clock delta = 30 s x events written across imports; repeats tick nothing; 25 rounds of ahead-dated rows leave clock, ledger, rejections and units unchanged; exact-clock accepted, +1 s refused). Timestamp, session-window and format checks are unchanged or stricter. Trade-off: source data newer than the application clock cannot be imported until the application clock has legitimately advanced. Residual: the clock still advances 30 s per written event, as for every native event.

## 2. ROLES versus ALL_ROLES

`capture.py` now reads `ALL_ROLES` (it previously raised `KeyError` / mis-reported for MACHINING and QC). `ROLES` is untouched and a test pins its exact content, so no existing permission broadens. Authorisation is checked against the motor's own provisioned source registry (`ledger._config`): a role the unit does not have (MACHINING / QC on a unit created without `lifecycle=True`), an event type outside that source's capability, or an actor mismatch is `CaptureRefused` before anything is written. The importer still never plans MACHINING, QC, QA or HANDHELD events (tested). Lifecycle reference keys (`subjectEventIds`, `previousOperationEventId`) are refused in other event types because the pinned ledger applies its lifecycle reference rule to any payload carrying them (see pin review, A3).

## 3. Quality and SCADA stay staged-only

No conversion into `QUALITY_INSPECTION_RECORDED`, `INSPECTION_RECORDED` or any lifecycle event was added; a test scans the package and the ledger for them.

## 4. Imported shipments are historical evidence

**Disabled by default** (final round): the bundled logistics mapping now sets `historicalShipments: false`, so logistics records are `UNRESOLVED_SHIPMENT_IMPORT_DISABLED` unless the caller opts in explicitly (`--historical-shipments`, `Options(historical_shipments=True)`, or a custom mapping with `capture.historicalShipments: true`). Only the synthetic demonstration (`demo.OPTIONS`) opts in. Additionally every imported `MOTOR_SHIPPED` now carries `pramaan-import-historical-shipment:v1` in its hashed `evidenceRefs`, the import report adds the warning `HISTORICAL_SHIPMENT_RECORD`, and the lifecycle trace marks the shipment `historicalImport: true`. Tested: `Manufacturing.ship` still refuses an already-shipped motor, refuses every other motor without a current trusted checkpoint and release eligibility, no ship ticket is ever created by an import, imported motors are never release-eligible, and the ledger holds exactly the imported shipment events. 

## 5. Pin review (`application/source-provenance.json`; not auto-approved)

Only two pins differ from the baseline. `profile.py` -> `e6950b18...` is exactly the lifecycle branch's. `ledger.py` -> `6674dfc0...` differs from the lifecycle branch's `24916ebb...` by the A3 fix only (the owner authorised this change in the final round; diff verified before the pin was recomputed: the helpers and their two call sites in `capture` and the snapshot loop).

**`integration/pramaan_integration/profile.py` (`e6950b18...`)**
- Change: two new event types in `TYPES`; vocabularies; payload validation for `MACHINING_RECORDED` and `QUALITY_INSPECTION_RECORDED`.
- Security: exact-key schema per type (unknown keys refused); keys `slot`, `verified`, `independentlyVerified`, `independent`, `approved`, `clearance`, `releaseEligible`, `recallStatus`, `disposition` refused; `workOrderId` must be null; result has no default and is an enum; reference lists bounded (1-20, distinct). Types are only usable by a source whose provisioned registry lists them. Existing types' validation is unchanged.
- Semantics: the new types are claims. They cannot express verification, clearance, a recall verdict or a slot, so the evaluator has nothing to act on. Side effect: `register_motor` now accepts these two types in any source capability (a control-plane decision, not reachable from imported data).

**`integration/pramaan_integration/ledger.py` (`24916ebb...`)**
- Change: helpers `previous_operation`, `lifecycle_refs`; in `capture`, every reference must exist, be a `MACHINING_RECORDED` event of this motor and not be later in either clock, and an operation sequence must stay on one component; the snapshot "Watermark hides referenced evidence" loop also covers these references.
- Security (positive): references to unseen / foreign / later evidence are refused; a watermark cannot hide a referenced event.
- Finding A3 (found in the first round, FIXED in the final round): the rule was keyed on payload KEYS, not event type, so a legacy event (for example `MATERIAL_ALLOCATED`) carrying `subjectEventIds` / `previousOperationEventId` that baseline accepted could be rejected, and a ledger already holding one could raise `LedgerBlocked` at snapshot time. Final `ledger.py` (`6674dfc0...`): `LIFECYCLE_TYPES = (MACHINING_RECORDED, QUALITY_INSPECTION_RECORDED)`; `previous_operation(event)` / `lifecycle_refs(event)` take the event and return nothing for any other type, so BOTH the capture-time check and the snapshot watermark check apply to lifecycle types only. Legacy validation is byte-for-byte the baseline's. Regression tests: legacy events with lifecycle-looking keys (including malformed values) are accepted and the snapshot reads them; unknown, foreign-motor, non-machining, other-motor and cross-component lifecycle references are still rejected; helper unit test. The import-edge guard (reserved keys refused outside lifecycle types) stays as defence in depth.
- Cost: lifecycle reference lookups reuse `known`, so no extra query; performance should re-test (`ImpactQuery` relies on the pinned ledger implementation).

## 6. Conflicts and resolutions

| Item | Resolution |
|---|---|
| `ci/run_gates.py` `EXPECTED` application dict (lifecycle vs data integration) | both entries kept: `test_lifecycle=19`, `test_data_integration=55`; plus `test_integration_hardening=28` |
| `ci/frozen-source.json` (textual auto-merge, content wrong) | regenerated once with `ci/freeze.py` against the final source commit; see the manifest commit |
| `application/service.py` / `server.py` | no conflict; lifecycle's changes only |

## 7. Tests

`python -B -m unittest application.test_integration_hardening` (36 tests): 2099 and 13 other malformed or out-of-window times (table); end-to-end 2099 import leaves clock, ledger, rejections and units unchanged and the motor usable; mixed good/bad batch; the window edge agrees with the real ledger; the default window equals what `create_unit` registers; `execute` pre-check; repeated bad imports inert; a corrected record replaces the refused one; staged kinds time-checked; role tables pinned; lifecycle unit permissions for the original roles identical; cross-role refusals leave nothing behind; lifecycle and imported units in one ledger; quality / SCADA staged only; historical shipments never authorise; duplicates and contradicting re-sends; interrupted imports (killed process and ordinary failure at six cut points, resumed twice, no duplicates, no rejections, chain verifies); checkpoint freshness (repeat and refused imports leave it current, new evidence and an interrupted import end it, a stale checkpoint opens no shipment).

Final-round additions (8 tests): A3 scope (3), shipment default-off and explicit custom opt-in (the default-off test replaced the first-round one), clock ratchet (4).
