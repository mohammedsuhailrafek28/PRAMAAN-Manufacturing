"""Create a disposable synthetic demo database (review tooling, not application source). Run from the demo checkout root:

    .venv\\Scripts\\python.exe <path>\\prepare_db.py seeded .local\\demo.sqlite   # five seeded synthetic motors, recall BR-204 (DE explicit)
    .venv\\Scripts\\python.exe <path>\\prepare_db.py empty  .local\\live.sqlite   # empty ledger for the live capture segment

It uses only the application's own service layer (`Manufacturing.seed_demo()` or an empty ledger) and refuses to overwrite an
existing file, so a database that already holds evidence is never altered by mistake. It exports no anchor: that is a separate,
explicit step (see the runbook).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
from application.service import Manufacturing  # noqa: E402

if len(sys.argv) != 3 or sys.argv[1] not in ("seeded", "empty"):
    sys.exit(__doc__)
db = Path(sys.argv[2])
if db.exists():
    sys.exit(f"REFUSED: {db} already exists. Choose a new path; this script never modifies an existing ledger.")
db.parent.mkdir(parents=True, exist_ok=True)
m = Manufacturing(db)
try:
    if sys.argv[1] == "seeded":
        m.seed_demo()
finally:
    m.close()
print(f"created {sys.argv[1]} synthetic database: {db.resolve()}")
