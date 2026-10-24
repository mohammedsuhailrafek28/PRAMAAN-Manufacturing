"""Seal or verify a directory of case files by sha256.
  python -B seal_manifest.py seal   CASES_DIR MANIFEST.sha256    (refuses to overwrite an existing manifest)
  python -B seal_manifest.py verify CASES_DIR MANIFEST.sha256    (exit 1 if any case was added, removed or changed since sealing)
The manifest must be committed before the candidate is chosen and before the run. Hashing only: this does not authenticate who wrote a case.
"""
import hashlib
import sys
from pathlib import Path


def digests(d):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(d).glob("*.json"))}


def main(mode, cases, manifest):
    manifest = Path(manifest)
    if mode == "seal":
        if manifest.exists():
            raise SystemExit("REFUSED: manifest already exists; a sealed set is never re-sealed in place")
        d = digests(cases)
        if not d:
            raise SystemExit("REFUSED: no case files")
        manifest.write_text("".join(f"{h}  {n}\n" for n, h in d.items()), encoding="utf-8")
        print(f"sealed {len(d)} case(s)")
    elif mode == "verify":
        want = dict(reversed(line.split("  ", 1)) for line in manifest.read_text(encoding="utf-8").splitlines() if line)
        have = digests(cases)
        bad = sorted(n for n in set(want) | set(have) if want.get(n) != have.get(n))
        if bad:
            print("MISMATCH:", bad); raise SystemExit(1)
        print(f"verified {len(have)} case(s)")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(*sys.argv[1:4])
