"""Authoring check: the pinned evaluator's as-recorded finding for every motor of every fleet (no detector involved)."""
import fleet
import sandbox

for f in fleet.make_all():
    row = []
    for m in fleet.motors(f):
        c = fleet.motor_case(f, m)
        d = sandbox.replay(c, f["policy"])
        row.append(f"{m}:{d['evidenceFinding'][:4]}{d['reasonCodes'][:2]}")
    print(f["id"], " | ".join(row))
