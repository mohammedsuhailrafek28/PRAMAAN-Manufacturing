"""Write/verify the SHA-256 manifest of the frozen fleet files."""
import hashlib
import json
import os
import sys

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fleets")


def compute():
    return {n: hashlib.sha256(open(os.path.join(D, n), "rb").read()).hexdigest()
            for n in sorted(os.listdir(D)) if n.startswith("B") and n.endswith(".json")}


if __name__ == "__main__":
    path = os.path.join(D, "MANIFEST.json")
    if "--verify" in sys.argv:
        ok = json.load(open(path)) == compute()
        print("fleets match manifest:", ok)
        sys.exit(0 if ok else 1)
    json.dump(compute(), open(path, "w", newline="\n"), indent=1, sort_keys=True)
    print(len(compute()), "fleets hashed")
