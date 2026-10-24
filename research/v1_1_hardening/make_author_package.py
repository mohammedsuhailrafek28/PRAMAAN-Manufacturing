"""Build the package for the independent case author. Copies NO implementation or test code; writes a sha256 manifest of what it wrote.
usage (repository root):  python -B research/v1_1_hardening/make_author_package.py OUT_DIR
OUT_DIR must not exist. Nothing is run against any candidate.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
FILES = [(HERE / "case.schema.v1_1.json", "case.schema.v1_1.json"), (ROOT / "research/lot_identity_ab/case.schema.json", "case.schema.v1_0.json"),
         (HERE / "INDEPENDENT_BENCHMARK_HANDOFF_V1_1.md", "HANDOFF.md"), (ROOT / "application/lot_registry.synthetic.json", "example_registry_document_shape.json")]
README = """Independent case author package (preparation only; no sealed case exists, nothing has been run).

1. Read HANDOFF.md ("Behaviour contract the author may rely on" and the families list). Do not read other files of the repository.
2. Write one JSON file per case validating against case.schema.v1_1.json. Prefer externally cited scenarios; mark invented parts INVENTED.
3. Give the expected outcome per motor from the physical story alone. Mark uncertain expectations contested=true.
4. Deliver cases only. Do not request or read candidate outputs. A separate reviewer will judge each case before any run.
Registry membership does not prove a bearing's physical identity, and the example registry is locally authored synthetic data.
"""
WORKSHEET = "caseId,motor,authorExpectedMustHold,reviewer,verdict(AGREE|DISAGREE|CONTESTED),reviewerNote\n"


def main(out):
    out = Path(out)
    out.mkdir(parents=True)
    written = []
    for src, name in FILES:
        (out / name).write_bytes(src.read_bytes()); written.append(name)
    (out / "README_FOR_AUTHOR.txt").write_text(README, encoding="utf-8"); written.append("README_FOR_AUTHOR.txt")
    (out / "reviewer_worksheet.csv").write_text(WORKSHEET, encoding="utf-8"); written.append("reviewer_worksheet.csv")
    manifest = {n: hashlib.sha256((out / n).read_bytes()).hexdigest() for n in sorted(written)}
    (out / "MANIFEST.sha256").write_text("".join(f"{h}  {n}\n" for n, h in manifest.items()), encoding="utf-8")
    json.loads((out / "case.schema.v1_1.json").read_text(encoding="utf-8"))      # the schema must at least parse
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
