"""Synthetic test custody/bootstrap only; not an operator authorization flow."""
import json
from pathlib import Path
import sys
import argparse
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from application.service import Manufacturing
from application.anchors import export_anchor
from application.server import make_server
parser=argparse.ArgumentParser(); parser.add_argument('database',type=Path); parser.add_argument('--empty',action='store_true'); parser.add_argument('--port',type=int,default=4173)
args=parser.parse_args(); database=args.database
app=Manufacturing(database)
if not args.empty: app.seed_demo()
anchor=database.with_suffix('.test-owner-anchor.json')
anchor.write_text(json.dumps(export_anchor(app)))
app.close()
server=make_server(database, args.port, trusted_anchor=anchor)
try: server.serve_forever()
finally: server.server_close()
