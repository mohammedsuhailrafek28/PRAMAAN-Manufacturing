"""Print the pinned evaluator's baseline for each scenario (authoring check only)."""
import sandbox
import scenarios

for s in scenarios.make_all():
    d = sandbox.replay(s["case"], s["policy"], watermark=s["watermark"])
    m = sandbox.summary(d)
    print(s["id"], m["finding"], m["reasons"], m["flags"], m["gaps"], "|", s["intent"][:60])
