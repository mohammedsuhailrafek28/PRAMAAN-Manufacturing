# Manufacturing PRAMAAN

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
.venv/Scripts/python.exe app.py --seed-demo
```

On macOS/Linux substitute `.venv/bin/python` for `.venv/Scripts/python.exe`. Open **http://127.0.0.1:4173**. One Python process serves the built UI and API from the same loopback origin. SQLite persists at `.local/manufacturing.sqlite`; stop with Ctrl+C. Seeding is idempotent for the completed demo database. To start a fresh manufacturing workflow, use a distinct database path without `--seed-demo`:

```powershell
.venv/Scripts/python.exe app.py --database .local/fresh.sqlite --port 4174
```

Use the capture workspace to create a unit, capture DE/NDE assembly, record shipment evidence, announce a defective lot, replace the DE bearing, and inject late contradictory evidence. Decisions always come from v3. A unit with unknown baseline stays held after recall announcement. The local demo provisions synthetic source/actor/session claims; it never generates independent trusted verification. One immutable recall scope is supported per database.

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

Safety remediation after the independent audit (explicit recall scope, durable notification obligations, decision-history integrity, freshness, accessibility): [Phase 3 remediation](docs/PHASE3_REMEDIATION.md).

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

The complete GS1 pin and hash evidence are in the foundation evaluation. The GS1 checkout stays external and is not distributed here. `application.verify` writes fresh results to `docs/phase3-validation` (override with `--output-dir`); source identity of `recall-engine` and `experiments/foundation` is checked by pinned git tree id, so the command works from a plain clone; original Phase 2 reports are preserved. It runs engine, foundation, integration, application, exporter, UI, browser and production-build gates, and validates newly captured documents against the external schema. The benchmark reports are synthetic local measurements, not production safety or performance claims.
