# Manufacturing PRAMAAN

**Phase 3.1 safety remediation:** see [root causes, before/after evidence and regression gates](docs/PHASE31_SAFETY_REMEDIATION.md). Start a **new** local demo database with `app.py --seed-demo --database .local/phase31.sqlite`; preserve old Phase 3 databases for historical replay. Their hardcoded scope is not silently reinterpreted as verified current clearance. The v3 evaluator and original engine/foundation/integration source trees remain unchanged.

One local application: EPCIS-compatible capture → append-only SQLite evidence → motor/component genealogy → actual recall assurance engine v3 → Recall Investigation UI.

Official destination: [mohammedsuhailrafek28/PRAMAAN-Manufacturing](https://github.com/mohammedsuhailrafek28/PRAMAAN-Manufacturing). This is the manufacturing project, separate from MSME PRAMAAN. Phase 3 is a local synthetic demonstration ready for review, not a production deployment or shipment release system.

## Install and run

Requires Python 3.12+, Node 24+ and npm. From the repository root on Windows PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r integration/requirements.lock
Set-Location recall-ui
npm ci --ignore-scripts
npm run build
Set-Location ..
.venv/Scripts/python.exe app.py --seed-demo --database .local/phase31.sqlite
```

On macOS/Linux substitute `.venv/bin/python` for `.venv/Scripts/python.exe`. Open **http://127.0.0.1:4173**. One Python process serves the built UI and API from the same loopback origin. SQLite persists at `.local/manufacturing.sqlite`; stop with Ctrl+C. Seeding is idempotent for the completed demo database. To start a fresh manufacturing workflow, use a distinct database path without `--seed-demo`:

```powershell
.venv/Scripts/python.exe app.py --database .local/fresh.sqlite --port 4174
```

Use the capture workspace to create a unit, capture DE/NDE assembly, record shipment evidence, announce a defective lot, replace the DE bearing, and inject late contradictory evidence. Missing recall positions default to **both DE and NDE**; the UI also supports explicit DE-only/NDE-only restrictions. The seeded historical DE scenario declares DE explicitly. Exposure decisions come from unchanged v3; application publication history uses `APPLICATION_PUBLICATION_A31`. A unit with unknown baseline stays held. Synthetic clocks are labelled `SYNTHETIC_SIMULATED` and are not registered as trusted. One immutable recall scope remains supported per database.

Fixture demo mode is explicitly selected at **/?mode=fixtures**; it remains read-only and repeatable. A backend error never automatically selects fixtures.

## Structure

```text
app.py                     local application launcher
application/               manufacturing commands, HTTP API, tests, measurements
integration/               EPCIS profile, validated durable ledger, engine bridge
recall-engine/             unchanged pinned v1/v2/v3 evaluator, fixtures and oracles
recall-ui/                 React investigation UI and RecallDataSource adapters
experiments/foundation/    original isolated interoperability experiments
docs/                      source attribution, evaluation, reports and screenshots
```

See [Phase 3 delivery and walkthrough](docs/PHASE3_UNIFIED_APPLICATION.md), [source provenance](docs/PHASE3_SOURCE_PROVENANCE.md), [foundation evaluation](docs/OPEN_SOURCE_FOUNDATION_EVALUATION.md), [engine contract](recall-engine/README.md), and [ledger contract](integration/README.md).

## Reproduce verification

Chrome is used by browser tests. Install validation-only Python dependencies, obtain the external public GS1 artifacts at the documented pin, then run:

```powershell
.venv/Scripts/python.exe -m pip install -r integration/requirements-validation.txt
git clone https://github.com/gs1/EPCIS.git ../gs1-epcis
git -C ../gs1-epcis checkout 6f71468231838e424bb5dfa836e006e8dc69615c
.venv/Scripts/python.exe -m application.verify --gs1-checkout ../gs1-epcis
.venv/Scripts/python.exe -m application.measure
```

The GS1 checkout stays external and is not distributed here. Without arguments, `application.verify` uses `PRAMAAN_GS1_CHECKOUT` if set, otherwise `../gs1-epcis`. From an activated environment, `python -m application.verify` runs the same complete gate. It verifies pinned schema/context bytes and 126 engine/foundation/integration file hashes without requiring source Git commit objects. It writes results to `docs/phase31-validation/verification`, preserving earlier reports. Gates include the expanded synthetic safety suite and timeout/offline/mobile regressions as well as all original suites. Benchmark reports are synthetic local measurements, not production safety or performance claims.
# A31 C1–C3 hardening

Operational API decisions now require an explicitly owner-custodied external
anchor. An unanchored server exposes only a historical snapshot envelope; it
cannot authorize operational commands or current UI eligibility. Notification
resolution is disabled, including caller-supplied authorization callbacks.

For an existing, independently reviewed synthetic database:

```powershell
python -m application.anchors export --database .local/manufacturing.sqlite --anchor C:\owner-custody\checkpoint-001.json
python -m application.anchors verify --database .local/manufacturing.sqlite --anchor C:\owner-custody\checkpoint-001.json
python app.py --database .local/manufacturing.sqlite --trusted-anchor C:\owner-custody\checkpoint-001.json
```

Export creates a new file exclusively; it does not establish trust in that file.
Its custody and the latest checkpoint must be maintained independently. Verify
the previous checkpoint before accepting a successor. A valid extension is
accepted, so rollback of **uncheckpointed** later changes cannot be detected by
an older reference. Replacing both DB and reference is outside this mechanism's
trust model. A local writable path is not an authenticated anchor service.

The UI checks server timestamp/maximum age, local lease, request generation,
archive/journal continuity and evidence/decision regressions. This is bounded
freshness, not cryptographic protection against a proxy forging fresh metadata.
See `docs/PHASE31_A31_HARDENING_C1_C3.md` for verification and limitations.

