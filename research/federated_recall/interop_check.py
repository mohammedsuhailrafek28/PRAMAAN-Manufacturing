"""Cross-implementation check for F6 envelopes: reference (`cryptography`) vs Node `crypto` (OpenSSL) vs PyNaCl (libsodium) on one corpus.
Run with the F6 venv from the repo root: python -B research/federated_recall/interop_check.py OUT.json [PYTHON_WITH_PYNACL]. Needs `node` on PATH.
Scope: signature, pinned sender/role/kid, type, closed field sets, ALERT validity window. Chains, lot mapping, adoption and ledger behaviour are NOT re-implemented independently."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main(out, nacl_python=sys.executable):
    with tempfile.TemporaryDirectory() as d:
        corpus = Path(d) / "corpus.json"
        subprocess.run([sys.executable, "-B", str(HERE / "make_corpus.py"), str(corpus)], cwd=ROOT, check=True)
        node = json.loads(subprocess.run(["node", str(HERE / "verify_node.mjs"), str(corpus)], check=True, capture_output=True, text=True).stdout)
        nacl = json.loads(subprocess.run([nacl_python, "-I", str(HERE / "verify_pynacl.py"), str(corpus)], check=True, capture_output=True, text=True).stdout)
        cases = json.loads(corpus.read_text())["cases"]
    rows = [dict(case=c["name"], reference=c["reference"], node=n["accepted"], pynacl=p["accepted"]) for c, n, p in zip(cases, node, nacl)]
    disagreements = [r for r in rows if not (r["reference"] == r["node"] == r["pynacl"])]
    result = dict(cases=len(rows), accepted=sum(r["reference"] for r in rows), allAgree=not disagreements, disagreements=disagreements, rows=rows,
                  note="Ed25519 primitives: cryptography (reference), OpenSSL via Node crypto, libsodium via PyNaCl; canonical JSON implemented separately in each.")
    Path(out).write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=1))
    return 0 if result["allAgree"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], *sys.argv[2:3]))
