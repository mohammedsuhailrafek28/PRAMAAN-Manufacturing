"""Test-only bootstrap for an OWNED per-test stack: seed a synthetic ledger and write its root checkpoint.
Not an operator flow; the checkpoint is local test custody, not independent custody."""
import json
from pathlib import Path
import sys
import argparse
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from application.service import Manufacturing
from application.anchors import export_anchor
parser = argparse.ArgumentParser(); parser.add_argument('database', type=Path); parser.add_argument('anchor', type=Path); parser.add_argument('--empty', action='store_true')
args = parser.parse_args()
app = Manufacturing(args.database)
if not args.empty: app.seed_demo()
args.anchor.parent.mkdir(parents=True, exist_ok=True)
args.anchor.write_text(json.dumps(export_anchor(app)))
app.close()
