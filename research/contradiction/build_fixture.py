"""Build a DISPOSABLE synthetic ledger + checkpoint file for the safety check. Not imported by the experiment.

usage (cwd = repository root): python -B research/contradiction/build_fixture.py <empty-dir>
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.getcwd())
from application.anchors import export_anchor, publish_candidate  # noqa: E402
from application.service import Manufacturing  # noqa: E402

d = sys.argv[1]
os.makedirs(d, exist_ok=True)
app = Manufacturing(os.path.join(d, "ledger.sqlite"))
app.create_unit("MTR-SAFETY-001")
app.assemble("MTR-SAFETY-001", "BR-310", "BR-312")
app.ship("MTR-SAFETY-001")
app.announce("BR-204", ["DE"])
app.snapshot()
publish_candidate(os.path.join(d, "checkpoint-001.json"), export_anchor(app))
app.close()
print("fixture ready:", sorted(os.listdir(d)))
