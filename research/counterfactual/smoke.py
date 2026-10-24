import scenarios
import methods as M
import ops as O

scenarios.write_all()
for sc in scenarios.load_all():
    r = M.search(sc, K=3)
    out = []
    for t, v in r["found"].items():
        m, mins = M.minimal([frozenset(x) for x in v])
        out.append(f"{t[:4]}:min={m}:{[sorted(x) for x in mins][:3]}(+{len(v) - len(mins)})")
    inad = [o["id"] for o in O.catalog(sc, True) if O.violations(o, sc)]
    print(sc["id"], r["baseline"]["finding"][:4], "cat", r["catalogSize"], "evals", r["evals"], "complete", r["complete"], " ".join(out), "| inadm", inad)
