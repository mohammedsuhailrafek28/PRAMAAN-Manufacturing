"""Record revisions and dependency/license evidence without vendoring source."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor

REPOS = {
    "openepcis/epcis-repository-ce": ["LICENSE", "README.md", "parent/pom.xml", "distributions/community-edition/pom.xml", "docker/docker-compose.yml", "modules/openepcis-rest-api-common/pom.xml"],
    "openepcis/openepcis-models": ["LICENSE", "pom.xml", "core/pom.xml", "epcis/pom.xml"],
    "openepcis/openepcis-event-hash-generator": ["LICENSE", "pom.xml", "core/pom.xml", "core/src/main/java/io/openepcis/eventhash/EventHashGenerator.java"],
    "openepcis/openepcis-event-sentry": ["LICENSE", "package.json", "src/validation/validator.js", "src/index.js"],
    "openepcis/openepcis-bom": ["LICENSE", "pom.xml"],
    "eclipse-tractusx/traceability-foss": ["LICENSE", "LICENSE_non-code", "NOTICE.md", "pom.xml", "frontend/package.json", "COMPATIBILITY_MATRIX.md", "tx-models/pom.xml"],
    "eclipse-tractusx/industry-core-hub": ["LICENSE", "LICENSE_non-code", "NOTICE.md", "ichub-backend/requirements.txt", "ichub-backend/setup.py", "ichub-backend/services/provider/part_management_service.py"],
    "eclipse-tractusx/tractusx-sdk": ["LICENSE", "LICENSE_non-code", "NOTICE.md", "pyproject.toml"],
    "gs1/EPCIS": ["LICENSE", "Disclaimer", "EPCIS-JSON-Schema.json", "epcis-context.jsonld"],
}


def inspect(repo, root):
    checkout = root / repo.split("/")[1]
    rev = subprocess.check_output(["git", "log", "-1", "--format=%H%n%cI%n%s"], cwd=checkout, text=True).splitlines()
    result = {"repository": "https://github.com/" + repo, "commit": rev[0], "commitDate": rev[1], "subject": rev[2], "files": {}}
    for relative in REPOS[repo]:
        path = checkout / relative
        if not path.exists():
            result["files"][relative] = {"missing": True}
            continue
        content = path.read_bytes()
        result["files"][relative] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "url": f"https://github.com/{repo}/blob/{rev[0]}/{relative}",
            "restrictiveHeaderDetected": any(s in content.lower() for s in (b"unauthorized copying", b"unauthorised use", b"strictly prohibited")),
        }
    for endpoint, fields in (("", ("archived", "disabled", "pushed_at", "open_issues_count", "default_branch")), ("/releases/latest", ("tag_name", "published_at", "html_url"))):
        try:
            request = urllib.request.Request("https://api.github.com/repos/" + repo + endpoint, headers={"User-Agent": "Manufacturing-PRAMAAN-feasibility-study"})
            data = json.load(urllib.request.urlopen(request, timeout=25))
            result["metadata" if not endpoint else "latestRelease"] = {k: data.get(k) for k in fields}
        except Exception as exc:
            result["metadataError" if not endpoint else "releaseError"] = str(exc)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkouts", required=True, type=Path)
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=6) as pool:
        evidence = list(pool.map(lambda r: inspect(r, args.checkouts), REPOS))
    output = Path(__file__).with_name("upstream-evidence.json")
    output.write_text(json.dumps({"reviewDate": "2026-10-21", "repositories": evidence}, indent=2) + "\n", encoding="utf-8")
    for r in evidence:
        print(r["repository"], r["commit"][:12], r["commitDate"], r.get("latestRelease", r.get("releaseError")))
