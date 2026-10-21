"""Read public artifact metadata and validate Compose without starting services."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

ARTIFACTS = ["openepcis-bom", "openepcis-model-core", "openepcis-model-epcis",
             "openepcis-event-hash-generator", "openepcis-digital-link-converter-core",
             "openepcis-reactive-event-publisher", "openepcis-capture-service",
             "openepcis-capture-kafka-streams", "openepcis-repository-opensearch",
             "openepcis-query", "openepcis-repository-api"]


def probe(artifact):
    base = f"https://repo.maven.apache.org/maven2/io/openepcis/{artifact}/"
    result = {"artifact": "io.openepcis:" + artifact, "metadataUrl": base + "maven-metadata.xml"}
    try:
        data = urllib.request.urlopen(result["metadataUrl"], timeout=20).read()
        root = ET.fromstring(data)
        version = root.findtext("versioning/release") or root.findtext("versioning/latest")
        result.update(release=version, versions=[e.text for e in root.findall("versioning/versions/version")], metadataSha256=hashlib.sha256(data).hexdigest())
        pom_url = f"{base}{version}/{artifact}-{version}.pom"
        pom = ET.fromstring(urllib.request.urlopen(pom_url, timeout=20).read())
        ns = {"m": "http://maven.apache.org/POM/4.0.0"}
        result["pomUrl"] = pom_url
        result["licenses"] = [n.text for n in pom.findall("m:licenses/m:license/m:name", ns)]
        result["dependencies"] = [{k: d.findtext("m:" + k, namespaces=ns) for k in ("groupId", "artifactId", "version", "scope")} for d in pom.findall("m:dependencies/m:dependency", ns)]
        if artifact in ("openepcis-model-core", "openepcis-model-epcis", "openepcis-event-hash-generator"):
            jar_url = f"{base}{version}/{artifact}-{version}.jar"
            jar_bytes = urllib.request.urlopen(jar_url, timeout=25).read()
            with zipfile.ZipFile(io.BytesIO(jar_bytes)) as jar:
                majors = sorted({int.from_bytes(jar.read(n)[6:8], "big") for n in jar.namelist() if n.endswith(".class") and not n.startswith("META-INF/")})
            result["jarInspection"] = {"url": jar_url, "sha256": hashlib.sha256(jar_bytes).hexdigest(), "classMajorVersions": majors, "javaVersions": [m - 44 for m in majors]}
    except Exception as exc:
        result["error"] = str(exc)
    return result


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=6) as pool:
        artifacts = list(pool.map(probe, ARTIFACTS))
    upstream = Path(__file__).resolve().parents[3] / "foundation-upstream" / "epcis-repository-ce" / "docker"
    command = ["docker", "compose", "-f", "docker-compose.rest-api-ce.yml", "config", "--quiet"]
    try:
        proc = subprocess.run(command, cwd=upstream, capture_output=True, text=True, timeout=30)
        compose = dict(command=command, exitCode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr, servicesStarted=False)
    except Exception as exc:
        compose = {"error": str(exc), "servicesStarted": False}
    output = {"reviewDate": "2026-10-21", "mavenCentral": artifacts, "compose": compose}
    Path(__file__).with_name("artifact-evidence.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifacts": [{"name": a["artifact"], "release": a.get("release"), "error": a.get("error")} for a in artifacts], "compose": compose}, indent=2))
