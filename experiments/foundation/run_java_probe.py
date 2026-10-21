"""Use an external Maven install/cache; retain only text evidence in this branch."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from interop import sample, to_epcis, document


def invoke(command, timeout):
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        return dict(exitCode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)
    except subprocess.TimeoutExpired as exc:
        def decoded(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else value
        return dict(exitCode=None, timeoutSeconds=timeout, stdout=decoded(exc.stdout), stderr=decoded(exc.stderr))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--maven", required=True)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--baseline", action="store_true", help="Use only declared OpenEPCIS dependencies")
    parser.add_argument("--java", default="java", help="Actual JDK executable, avoiding launcher shims")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    command = [args.maven, "-f", str(root / "java-probe/pom.xml"),
               "-Dmaven.repo.local=" + str(args.cache.resolve()),
               "org.apache.maven.plugins:maven-dependency-plugin:3.8.1:build-classpath",
               "-Dmdep.outputFile=classpath.txt", "-B", "-q"]
    if not args.baseline:
        command.append("-Pcommons-io-workaround")
    output = {"dependencyCommand": command}
    output["resolution"] = invoke(command, 180)
    if output["resolution"]["exitCode"] == 0:
        cp = (root / "java-probe/classpath.txt").read_text().strip()
        output["runtimeArtifacts"] = []
        for entry in cp.split(os.pathsep):
            jar = Path(entry)
            parts = jar.relative_to(args.cache.resolve()).parts
            output["runtimeArtifacts"].append({"groupId": ".".join(parts[:-3]),
                "artifactId": parts[-3], "version": parts[-2], "sha256": hashlib.sha256(jar.read_bytes()).hexdigest()})
        with tempfile.TemporaryDirectory(prefix="pramaan-foundation-java-") as temp:
            base = document([to_epcis(e) for e in sample()])
            variants = {"base": base}
            for name, key, value in (("slot", "slot", "NDE"), ("sequence", "sourceSeq", 99),
                                     ("source_recorded_at", "recordedAt", "2026-10-21T08:01:09Z")):
                variant = copy.deepcopy(base)
                target = variant["epcisBody"]["eventList"][1]["trace"]
                (target["payload"] if key == "slot" else target)[key] = value
                variants[name] = variant
            variant = copy.deepcopy(base)
            variant["epcisBody"]["eventList"][1]["recordTime"] = "2026-10-21T10:00:00Z"
            variants["repository_record_time"] = variant
            paths = []
            for name, doc in variants.items():
                path = Path(temp) / (name + ".json")
                path.write_text(json.dumps(doc), encoding="utf-8")
                paths.append(str(path))
            output["hashProbe"] = invoke([args.java, "--class-path", cp, str(root / "java-probe/Probe.java"), *paths], 45)
            if output["hashProbe"]["exitCode"] == 0:
                hashes = {}
                for line in output["hashProbe"]["stdout"].splitlines():
                    if line.startswith("DOC="):
                        name = line[4:]; hashes[name] = []
                    elif line.startswith("HASH="):
                        hashes[name].append(line[5:])
                output["hashProperties"] = {name + "_changes_install_hash": values[1] != hashes["base.json"][1]
                                            for name, values in hashes.items() if name != "base.json"}
    name = "java-baseline-results.json" if args.baseline else "java-results.json"
    (root / name).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"resultFile": name, "resolutionExitCode": output["resolution"]["exitCode"],
                      "hashExitCode": output.get("hashProbe", {}).get("exitCode"),
                      "runtimeArtifactCount": len(output.get("runtimeArtifacts", [])),
                      "hashProperties": output.get("hashProperties")}, indent=2))
