"""Pre-stage the live demo (run once BEFORE going on stage; synthetic, loopback, disposable).

    python -B docs/v1_1_release_candidate/demo_prestage.py demo/ledger.sqlite demo/custody/root.json

Seeds the five demo motors, then adds MTR-DEMO-1 (clean lots, unshipped) and MTR-DEMO-2 (recalled DE lot BR-204, unshipped), and writes a root checkpoint that covers
everything, so the console starts ANCHORED_CURRENT with DEMO-1 release eligible and DEMO-2 on recall hold. Same-host custody, operator asserted, NOT independent.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from application.anchors import export_anchor, publish_candidate  # noqa: E402
from application.service import Manufacturing  # noqa: E402

db, anchor = Path(sys.argv[1]), Path(sys.argv[2])
if db.exists() or anchor.exists():
    raise SystemExit("refusing to overwrite an existing demo ledger or checkpoint; delete the demo/ directory first")
anchor.parent.mkdir(parents=True, exist_ok=True)
app = Manufacturing(db)
app.seed_demo()
for serial, de in (("MTR-DEMO-1", "BR-310"), ("MTR-DEMO-2", "BR-204")):
    app.create_unit(serial); app.assemble(serial, de, "BR-312")
app.snapshot()
publish_candidate(anchor, export_anchor(app))
app.close()
print("staged:", db, anchor)
