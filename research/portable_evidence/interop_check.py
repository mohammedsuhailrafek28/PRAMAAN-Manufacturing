"""Cross-implementation check. Reference verifier (application.evidence_verify, `cryptography`) vs Node `crypto` (OpenSSL) vs PyNaCl (libsodium) on one corpus.
Run with the F5 venv from the repo root: python -B research/portable_evidence/interop_check.py OUT.json [PYTHON_WITH_PYNACL]. Needs `node` on PATH."""
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
    rows, disagreements = [], []
    for c, n, p in zip(cases, node, nacl):
        ref = c["reference"]
        agree = (ref["claims"] == n["claims"] == p["claims"]) if ref["accepted"] else True
        row = dict(case=c["name"], reference=ref["accepted"], node=n["accepted"], pynacl=p["accepted"], claimsAgree=agree)
        rows.append(row)
        if not (ref["accepted"] == n["accepted"] == p["accepted"]) or not agree:
            disagreements.append(row)
    result = dict(cases=len(rows), allAgree=not disagreements, disagreements=disagreements, rows=rows, accepted=sum(r["reference"] for r in rows),
                  note="Verdicts and accepted claims compared; failure codes differ by implementation by design. Ed25519 primitives: cryptography (reference), OpenSSL via Node crypto, libsodium via PyNaCl.")
    Path(out).write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=1))
    return 0 if result["allAgree"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], *sys.argv[2:3]))
