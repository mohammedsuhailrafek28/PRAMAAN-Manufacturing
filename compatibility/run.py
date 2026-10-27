"""Isolated contracts and headless component tests; never starts a unified frontend preview."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import sqlite3
import tempfile
import threading

from application.anchors import TrustedAnchor, export_anchor, publish_candidate
from application.server import make_server
from application.service import Manufacturing
from application import lifecycle as lifecycle_view
from review2.demo import prepare, stale, verify

ROOT = Path(__file__).resolve().parents[1]


def snapshot(database, reference=None, previous=None):
    app = Manufacturing(database)
    try:
        return app.snapshot(trusted_anchor=TrustedAnchor(reference, previous) if reference else None)
    finally:
        app.close()


def resources(database, snap):
    """Per-motor bodies exactly as application/server.py builds them (same functions and query), for deterministic consistency tests."""
    app = Manufacturing(database)
    try:
        out = dict(decisions={}, lifecycle={}, provenance={})
        for unit in snap['units']:
            m = unit['unitId']
            out['lifecycle'][m] = dict(lifecycle_view.view(unit['events']), checkpoint=snap['checkpoint'], motorSerial=m)
            rows = app.db.execute("SELECT c.hash,c.raw,c.received,e.id,e.source,e.seq,e.hash AS event_chain_hash,e.epcis FROM captures c JOIN events e ON e.capture=c.hash WHERE e.motor=? ORDER BY e.ordinal", (m,)).fetchall()
            out['provenance'][m] = [{k: r[k] for k in r.keys() if not isinstance(r[k], bytes)} for r in rows]
            if snap['checkpoint']['state'] == 'ANCHORED_CURRENT':
                out['decisions'][m] = dict(snap['decisions'][m], checkpoint=snap['checkpoint'], eligibility=snap['eligibility'][m])
        return out
    finally:
        app.close()


def main():
    with tempfile.TemporaryDirectory(prefix="pramaan-unified-contract-") as temp:
        d = Path(temp)
        a, b = d / "manufacturing", d / "stale-manufacturing"
        result = prepare(a)
        assert result['eventCount'] == 47 and result['repeated']['ledgerEventsPlanned'] == 0
        current = snapshot(a / 'ledger.sqlite', a / 'demo-reference.json')
        unanchored = snapshot(a / 'ledger.sqlite')
        # An owned snapshot fork preserves the same archive/reference for the real
        # current -> prefix-only transition. No live database or other dataset is copied.
        shutil.copytree(a, b, ignore=shutil.ignore_patterns('ledger.sqlite', 'ledger.sqlite-*'))
        source = sqlite3.connect((a / 'ledger.sqlite').as_uri() + '?mode=ro', uri=True)
        target = sqlite3.connect(b / 'ledger.sqlite')
        try: source.backup(target)
        finally: source.close();target.close()
        stale(b)
        prefix = snapshot(b / 'ledger.sqlite', b / 'demo-reference.json')
        # Explicit test-only custody simulation for a legitimate successor. Never hot-swap a live server.
        app = Manufacturing(b / 'ledger.sqlite')
        successor_ref = b / 'successor-reference.json'
        try:
            previous = json.loads((b / 'demo-reference.json').read_text(encoding='utf-8'))
            publish_candidate(successor_ref, export_anchor(app, previous=previous))
        finally:
            app.close()
        successor = snapshot(b / 'ledger.sqlite', successor_ref, b / 'demo-reference.json')
        assert successor['checkpoint']['state'] == 'ANCHORED_CURRENT'
        five_db, five_reference = d / 'five.sqlite', d / 'five-reference.json'
        app = Manufacturing(five_db)
        try:
            app.seed_demo()
            assert app.db.execute('SELECT count(*) FROM events').fetchone()[0] == 58
            app.snapshot();publish_candidate(five_reference, export_anchor(app))
        finally:
            app.close()
        five = snapshot(five_db, five_reference)
        for name, body in [('manufacturing-current', current), ('manufacturing-stale', prefix),
                           ('manufacturing-unanchored', unanchored), ('manufacturing-successor', successor), ('five-current', five)]:
            (d / (name + '.json')).write_text(json.dumps(body), encoding='utf-8')
        for name, body, database in [('manufacturing-current', current, a), ('manufacturing-stale', prefix, b), ('manufacturing-successor', successor, b)]:
            (d / ('resources-' + name + '.json')).write_text(json.dumps(resources(database / 'ledger.sqlite', body), default=str), encoding='utf-8')
        ui = ROOT / 'stitch-nextjs'
        subprocess.run(['node', str(ui / 'node_modules/typescript/bin/tsc'), '-p', 'tsconfig.compat.json'], cwd=ui, check=True)
        srv = make_server(a / 'ledger.sqlite', 0, trusted_anchor=a / 'demo-reference.json')
        thread = threading.Thread(target=srv.serve_forever, daemon=True);thread.start()
        try:
            assert srv.server_port not in (3002, 3003, 3004, 3005, 3006, 4400, 4411)
            url = f'http://127.0.0.1:{srv.server_port}'
            verify(url)
            artifacts = ROOT / '.local/unified-validation'
            artifacts.mkdir(parents=True, exist_ok=True)
            env = dict(os.environ, PRAMAAN_COMPAT_FIXTURES=str(d), PRAMAAN_API_URL=url,
                       PRAMAAN_TEST_ARTIFACTS=str(artifacts), NODE_PATH=str(ui / 'node_modules'))
            names = ('compat.test.js', 'graph.test.js', 'unified.test.js', 'consistency.test.js')
            subprocess.run(['node', '--require', str(ROOT / 'compatibility/register.cjs'), '--test', '--test-concurrency=1', *(str(ROOT / '.local/frontend-compat-compiled/tests' / n) for n in names)],
                           cwd=ROOT, env=env, check=True)
            # Real React/provider/report code in jsdom: no Next/Vite server, no public preview port.
            subprocess.run(['npm.cmd', 'exec', '--', 'vitest', 'run', '--config', 'vitest.unified.config.ts'],
                           cwd=ROOT / 'recall-ui', env=env, check=True)
            print(json.dumps(dict(backend='OWNED_EPHEMERAL_TEST_ONLY', frontendPreviewStarted=False,
                                  manufacturingEvents=47, fiveMotorEvents=58, datasetsCombined=False,
                                  repeatImportNewEvents=0, result='PASS')))
        finally:
            srv.shutdown();srv.server_close();thread.join(5)


if __name__ == '__main__':
    main()
