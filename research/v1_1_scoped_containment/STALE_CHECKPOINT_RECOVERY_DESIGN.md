# Restricted stale-checkpoint recovery workflow (prototype)

Research branch `research/v1-1-scoped-containment-recovery`. Loopback, synthetic, no real notifications. Not a release; not independent custody.

## 1. The gap that was reported
Every ordinary capture moves the ledger past the active checkpoint, so the state becomes `ANCHORED_PREFIX_ONLY` and the console (correctly) withholds every decision, hold and clearance and hides the capture workspace. Recovery was only possible through the API or the command line. The owner asked for a restricted operator recovery workflow for that state.

## 2. Design
A **separate, whitelisted route family** under `/api/recovery`. It is separate so that the ordinary routes keep their behaviour and so that the whole permitted surface can be enumerated and tested.

| Route | Method | Allowed | Effect |
|---|---|---|---|
| `/api/recovery` | GET | stale state only | operator status: held motors with finding reasons and quarantine steps, allowed and prohibited action names, whether a custody directory is configured |
| `/api/recovery/observe` | POST | stale state only | evidence capture: `Manufacturing.observe` (unverified sighting) |
| `/api/recovery/replace` | POST | stale state only | reconciliation: `Manufacturing.replace` (controlled replacement with a registered lot) |
| `/api/recovery/propose` | POST | stale state only | proposal of a successor checkpoint via `checkpoint_ops.propose` into `--custody-dir`; nothing is accepted or activated |
| anything else under `/api/recovery/` | any | never | `404`; nothing is written |

Properties enforced and tested (`application/test_stale_recovery.py`, `recall-ui` unit and browser tests):
1. **Not applicable unless stale**: `409 RECOVERY_NOT_APPLICABLE` when the checkpoint is current, and `409 RECOVERY_REQUIRES_ANCHOR` with no anchor (an unanchored server stays "start with an owner-custodied checkpoint").
2. **No shipment, release, announcement, unit creation, assembly, acceptance or activation route exists**; all such names return `404` and leave the event count unchanged.
3. **No decision or eligibility in any response**: the response omits `operationalAction`, `evidenceFinding`, `currentReleaseEligible`, `eligibility`, `decisions` at any depth (checked recursively). The UI receives only held-motor reasons.
4. **Same request hygiene as every mutation**: loopback Host check, same-origin, local session token (`403` without it). This is hygiene, not authentication: any local process can call the API.
5. **Proposal activates nothing**: the running server remains `ANCHORED_PREFIX_ONLY` with every motor ineligible; the candidate is a file under `custody/candidates`, `custody/accepted` does not exist. Acceptance stays an offline operator action (`checkpoint_ops accept`, typed digest, acknowledgements) followed by a restart with `--trusted-anchor`; no HTTP route promotes a checkpoint.
6. **Recovery cannot bypass the guards**: captured sightings still hold the motor; after the operator accepts a reviewed checkpoint a contained motor stays held; a superseded sighting returns eligibility only through a newly accepted checkpoint.
7. Re-proposing with no ledger change is idempotent (an identical candidate file is reused; before, it crashed with `FileExistsError`; a differing file with the same name is still an error).

UI: when the console is in the `PREFIX_ONLY` historical state and the data source supports recovery, a "Recovery workspace" section appears under the existing "Checkpoint required / do not ship or release" warning. It lists held motors, offers the sighting and replacement forms and the proposal button, and shows the proposal's contained/refused motors. It contains no button whose label mentions shipping, announcing, accepting, activating or releasing (asserted in a unit test and a browser test).

## 3. Open gap (reported, decision requested)
The **ordinary** `POST /api/units/<motor>/ship` route records a shipment fact whether or not the checkpoint is current. It grants no eligibility (eligibility is false for every motor while stale; asserted by `test_known_gap_the_ordinary_ship_route_is_not_gated_by_checkpoint_state`), and the stale console tells the operator not to ship, but the API does not refuse it. Existing browser specs and application tests call `ship` while stale, so gating it is an owner-approved behaviour change with test updates, not something to do silently. The recovery surface itself has no shipment route.

## 4. Not claimed
- It is not authentication or role-based authorization. Roles in the ledger (`HANDHELD`, `REWORK`, ...) are synthetic source identities, not authenticated people. A real deployment needs the authority model in `TRUSTED_AUTHORITY_MODEL.md`.
- It does not make the checkpoint independent of this host.
- Proposal writes a file and archives evaluator publications into the local database (as `propose` always did); it is not read-only.
