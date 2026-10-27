# PS10 manufacturing lifecycle completeness

Branch `feature/ps10-lifecycle`, from `manufacturing-demo-v1.2` (`6709b0c6f521006cf6332caeecec6b08dbd44e84`). Synthetic data only. The recall evaluator
(`recall-engine/`), the shipment gate (`Manufacturing.ship`), F5/F6 and A7 are **not modified**.

## 1. Audit of what existed

| Area | Finding at v1.2 |
|---|---|
| Event schema (`integration/pramaan_integration/profile.py`) | 13 event types. Bearing-centred: `MATERIAL_ALLOCATED`, `BEARING_MANUFACTURED`, `WORK_ORDER_*`, `COMPONENT_INSTALLED/REMOVED`, slot observations, capture exceptions, `MOTOR_SHIPPED`. |
| Machining | **Absent.** Nothing records an operation on a shaft, housing, end shield or rotor core, the machine used, or the routing step. |
| Inspection | `INSPECTION_RECORDED` exists, but only as the damage-inspection input of the P2 historical-exposure policy (protocol id matched to the policy). It has no subject reference and is not a manufacturing quality record. Left untouched. |
| Passport timeline (`recall-ui/src/passport/projection.ts`) | Renders every event; an unknown type is shown as category "Other / Recorded event" without error. No UI change was made. |
| Read APIs | `/api/snapshot` and `/api/motors/<m>/genealogy` already carry every event of a unit (`units[].events`, with capture hash and event-chain hash). There was no chronology or traceability view. |

The recall evaluator ignores event types it has no handler for (`recall-engine/pramaan_recall/ledger.py`, `h.get(eventType)`), and reads `payload.slot` from every
event to build its slot universe. The new payloads therefore **forbid a `slot` key**, so a lifecycle event can never alter the evaluator's view of the motor.

## 2. What was added

**Two event types** (same ledger, hash chain, capture documents and checkpoint coverage as every other event):

- `MACHINING_RECORDED` — an operation was performed on a motor component. Payload: `componentType` (SHAFT, HOUSING, END_SHIELD, ROTOR_CORE), `componentId`, `operation`
  (TURNING, MILLING, DRILLING, GRINDING, BORING, KEYWAY_CUTTING), `machineId`, `routingStepId`, `drawingRef`, optional `previousOperationEventId`. No measured value, no result.
- `QUALITY_INSPECTION_RECORDED` — a claim about earlier machining operations. Payload: `inspectionType`, `subjectEventIds` (1–20 distinct machining events of the same motor),
  `protocolId`, `result` (PASS / FAIL / INCONCLUSIVE, **always supplied by the caller, never defaulted or inferred**), `inspectorQualifiedFor`, optional `instrumentId`, `measurementRecordRef`.

Every new event has: a URN `eventId`; a motor-scoped `sourceId` (`MACHINING:<motor>`, `QC:<motor>`) with a gap-free `sourceSeq` and a provisioned capture session; `occurredAt`, `recordedAt`
and `timeSource`; `evidenceRefs`; event references (`previousOperationEventId`, `subjectEventIds`) that the ledger checks exist, are the right type, belong to the same motor and do not
follow the referencing event on either clock; and the standard capture-document hash and event hash chain.

Rejected by the profile: any `slot`, `verified`, `independentlyVerified`, `independent`, `approved`, `clearance`, `releaseEligible`, `recallStatus`, `disposition` field; any
`trusted`/`authorized` self-assertion (existing rule); a work-order id; unknown component, operation, inspection type or result; extra fields.

**Service** (`application/service.py`): `create_unit(..., lifecycle=True)` provisions the two extra sources; `machine(...)` and `inspect_quality(...)` validate the request completely
**before** capture. This matters: a ledger-level rejection permanently blocks a motor, so a mistaken request must never reach it. Units created without `lifecycle=True` are byte-for-byte as before
(same sources, same configuration digest); asking them for lifecycle capture is refused without a rejection row.

**Read model** (`application/lifecycle.py`, pure): `chronology` (all events ordered, with references and ledger coordinates), `violations` (references that are missing or occur later),
`backward` (shipment ← assembly ← bearings ← manufacture ← material, and machined components with operations and inspections), `forward` (key → motors → matching events → inspections → shipments;
keys: `bearingLot`, `rawMaterialLot`, `machineId`, `componentId`).

**HTTP** (`application/server.py`): read-only `GET /api/motors/<m>/lifecycle` and `GET /api/trace/<key>/<value>` (history only: no decision, eligibility or clearance travels with them;
the checkpoint state is included). Commands `POST /api/units/<m>/machine` and `/inspect`, and an optional boolean `lifecycle` on `POST /api/units`, follow the existing command rules
(local session token, trusted checkpoint present, full snapshot in the response). Existing read contracts are unchanged: lifecycle events already appear in `units[].events`.

## 3. Recorded versus independently verified

| Statement | Status |
|---|---|
| A machining operation was performed on component X on machine M | **Recorded claim** by the machining source. Nothing verifies that it happened. |
| An inspection of those operations took place and its result | **Recorded claim** by the QC source; `result` is whatever the caller supplied. |
| The inspector was qualified | **Claimed** (`inspectorQualifiedFor`); not checked against any authority. |
| The inspection was by a different actor and source than the machining | **Computed** from the record: `RECORDED_CLAIM_DIFFERENT_ACTOR_AND_SOURCE`, else `RECORDED_CLAIM_SAME_ACTOR_OR_SOURCE`. Even the stronger label is a statement about the record, not about the part. |
| Time | `SYNTHETIC_SIMULATED`; `trustedTime` is always false. |
| The part is correct, the motor is safe, the motor is release eligible, the recall evaluator trusts the inspection | **Not established.** Every inspection carries `independentlyVerified: false` and the list `notEstablished`. The QC source is not a recall `trustedVerifierSource`; nothing here can create, change or clear a decision. |

## 4. Safety properties kept (and how they are tested)

All in `application/test_lifecycle.py` (19 tests): the evaluator's raw output for a motor is identical before and after lifecycle evidence (including a recorded PASS) is added;
supported rework still yields the same outcome and no clearance without a current checkpoint; tampering with a recorded inspection result is detected as a hash-chain failure;
an old checkpoint no longer covers a ledger that gained a lifecycle event (`ANCHORED_PREFIX_ONLY`), a fresh one does; 17 malformed requests are refused with no rejection row;
profile-level forbidden fields; ledger-level rejection of unknown references, cross-motor references and a source writing outside its capability; chronology order across the whole lifecycle
(machining → inspection → material → assembly → shipment → rework); forward/backward agreement; HTTP read-only routes and 400 on bad commands with no write.

## 5. Capture-to-visible-history latency

See `docs/ps10/lifecycle-latency.json` (reproduce with `python -B -m application.measure_lifecycle --fleet 5 --fleet 50 --events 30`).

Measured on the development machine (Windows 11, Python 3.12.10, SQLite WAL), loopback, single process, 12 events per case, while an unrelated benchmark ran on other cores; treat as indicative, not a benchmark.
Visibility is checked by locating the new event id in the derived lifecycle view, never assumed from a status code.

| Case | Fleet | p50 | p95 | Notes |
|---|---|---|---|---|
| Capture call only (validate + ledger write) | 5 / 50 motors | 69 ms / 71 ms | 100 ms / 87 ms | independent of fleet size |
| Capture → visible in a freshly derived lifecycle view (in process) | 5 motors | 277 ms | 368 ms | includes one full verified snapshot |
| same | 50 motors | 2,138 ms | 2,170 ms | the snapshot dominates (~43 ms per motor) |
| `POST …/machine` → `GET …/lifecycle` shows it (anchored HTTP server) | 5 motors | 1,118 ms | 1,565 ms | POST 849 ms (p50) + GET 273 ms |
| same | 50 motors | **no successful request** | | all 12 POSTs returned `503 VERIFYING` |

**Finding.** The server gives each request a 1.25 s verification deadline that covers the whole snapshot, not only checkpoint verification. At 50 motors on this machine the snapshot alone exceeds it, so
every command returns `503 VERIFYING`. The 12 events were nevertheless **committed** (`eventsActuallyInLedger: 12`): the write happens before the snapshot that is built for the response. This is existing
behaviour of every command route (`replace`, `observe`, …), not something introduced here, but lifecycle capture inherits it: a 503 does not mean the event was refused. The in-process path, which has no deadline, shows the true
capture-to-visible cost (about 0.3 s at 5 motors, 2.1 s at 50). Capture itself costs under 0.1 s.

## 6. Limitations

- **Existing databases cannot gain lifecycle capture.** A motor's source registry is immutable once registered; only units created with `lifecycle=True` have machining/QC sources. There is no migration.
- Inspection is a claim. Nothing in this branch verifies a machined part, and the demo seeding does not create any inspection result (tests supply explicit, synthetic results).
- Machining carries no measurements and no tooling or program identity; QC carries a pointer (`measurementRecordRef`), not data.
- The passport and impact UI show these events generically ("Other · Recorded event"); no frontend change was made, so there is no dedicated lifecycle view.
- Component identity (`componentId`) is not linked to the bearing slots or to a physical serial of the motor; the link to a motor is the motor serial.
- Capture requires a trusted checkpoint for HTTP commands, and the response carries a full snapshot (cost grows with fleet size; see the performance audit).

## 7. Integration risks (for the owner)

1. **`integration/` is modified** (`profile.py`: two types and their validation; `ledger.py`: additive reference checks in `capture` and in the watermark-hides-evidence check). The pinned-provenance gate (K) and
   `test_remediation.test_pinned_provenance_no_git_dependency` assert that tree is unmodified from baseline `4a9e8f2`. I updated exactly those two pins in `application/source-provenance.json`
   (ledger.py `42192c1b…→24916ebb…`, profile.py `a2574411…→e6950b18…`); the engine and foundation pins are untouched. This is a deliberate, reviewable change to a safety pin and needs owner approval.
2. **Any new ledger evidence ends current clearance** for the whole ledger until a new checkpoint is proposed and accepted (existing semantics; tested). Lifecycle capture after the checkpoint therefore moves the ledger to `ANCHORED_PREFIX_ONLY`.
3. Each new lifecycle event adds an `EVALUATION` entry (same version, `unchanged: true`) to that motor's journal at the next snapshot, because the manifest changes. Journal growth is linear in events.
4. Merge surface with the parallel performance branch: `integration/pramaan_integration/ledger.py` (capture and snapshot reference loops), `application/service.py` (`create_unit`, `event`), `application/server.py` (route chain). Re-run `test_lifecycle` and the pin update after any merge that touches them.
5. `ci/frozen-source.json` and the CI inventory must be regenerated by the owner's freeze procedure for the final source commit.
