"""Build the two separate hand-off packages for the independent benchmark. Copies NO implementation, test or candidate-output file.
usage (repository root):  python -B research/v1_1_scoped_containment/benchmark/make_packages.py OUT_DIR
OUT_DIR must not exist. Creates OUT_DIR/author and OUT_DIR/reviewer, each with a sha256 MANIFEST. Nothing is run against any candidate.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
AUTHOR_README = """Independent case author package (preparation only; no sealed case exists, nothing has been run).
1. Read HANDOFF_FOR_CASE_AUTHOR.md. Do not read other files of the repository, and do not ask for or read any output of the software.
2. Write one JSON file per case validating against case.schema.v1_2.json.
3. Give your expectation per motor from the physical story alone; mark uncertain expectations contested=true with a rationale.
4. Deliver the case files only. A different party will review each case before anything is run.
"""
REVIEWER_README = """Ground-truth reviewer package (preparation only).
You are a different party from the case author and from the engineer of the software. For every case, read the story, the registry and the steps, and decide
from the physical story alone whether the author's expectation for each motor is right. Record AGREE, DISAGREE or CONTESTED in reviewer_worksheet.csv with a
short reason. You must not see the software, its tests or any output of it, and you must record your verdicts BEFORE the software is run on the sealed set.
Do not edit a case. If you disagree, your verdict is what is recorded; the case file stays as delivered.
Registry membership does not prove the physical identity of a bearing; the registry in a case is locally authored synthetic data.
"""
WORKSHEET = "caseId,motor,authorExpectedMustHold,authorExpectedRenewalAccepted,reviewer,verdict(AGREE|DISAGREE|CONTESTED),reviewerNote\n"


def write(out, files):
    manifest = {}
    for name, data in files.items():
        (out / name).write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
        manifest[name] = hashlib.sha256((out / name).read_bytes()).hexdigest()
    (out / "MANIFEST.sha256").write_text("".join(f"{h}  {n}\n" for n, h in sorted(manifest.items())), encoding="utf-8")
    return manifest


def main(out):
    out = Path(out)
    out.mkdir(parents=True)
    (out / "author").mkdir(); (out / "reviewer").mkdir()
    schema = (HERE / "case.schema.v1_2.json").read_bytes()
    json.loads(schema)                                              # must at least parse
    example_registry = (ROOT / "application" / "lot_registry.synthetic.json").read_bytes()
    a = write(out / "author", {"HANDOFF_FOR_CASE_AUTHOR.md": (HERE / "HANDOFF_FOR_CASE_AUTHOR.md").read_bytes(), "case.schema.v1_2.json": schema,
                               "example_registry_document_shape.json": example_registry, "README_FOR_AUTHOR.txt": AUTHOR_README})
    r = write(out / "reviewer", {"README_FOR_REVIEWER.txt": REVIEWER_README, "case.schema.v1_2.json": schema, "reviewer_worksheet.csv": WORKSHEET,
                                "HANDOFF_FOR_CASE_AUTHOR.md": (HERE / "HANDOFF_FOR_CASE_AUTHOR.md").read_bytes()})
    print(json.dumps(dict(author=a, reviewer=r), indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
