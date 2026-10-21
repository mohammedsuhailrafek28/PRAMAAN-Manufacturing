# Disposable foundation probes

These are research scripts, not production adapters. They do not access the MSME
repository or import any version of the production recall engine. All events are
independently authored synthetic records; no fixture/oracle datasets are used.

## Reproduce the local interoperability probe

Use Python 3.12 in an isolated virtual environment outside the production tree:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock
git clone https://github.com/gs1/EPCIS.git <external-gs1-checkout>
git -C <external-gs1-checkout> checkout 6f71468231838e424bb5dfa836e006e8dc69615c
.venv/Scripts/python.exe interop.py --gs1-checkout <external-gs1-checkout>
```

Run from this directory or supply paths relative to the repository root.
`results.json` contains 21 passing checks, retrieved association events, the
translated six-event native envelope, and separate integrity metadata. The
schema/context are read externally and are not redistributed in this branch.
The loader performs no remote JSON-LD fetches. Example identifiers are reserved
`example.org` URIs, not registered GS1 or Catena-X identities.

Schema success is not manufacturing correctness, source authentication, capture
completeness, or recall safety. The SQLite database is in memory and closes with
the process. There are no endpoints, background services or migrations.

## Reproduce selective OpenEPCIS library evaluation

Install Java 21 and Maven 3.9.x outside the production worktree. Maven dependencies
are downloaded to an explicitly isolated cache. From this directory:

```powershell
.venv/Scripts/python.exe run_java_probe.py --maven <mvn.cmd> --cache <external-cache> --baseline
.venv/Scripts/python.exe run_java_probe.py --maven <mvn.cmd> --cache <external-cache>
```

The baseline uses two OpenEPCIS 0.9.3 dependencies and their declared transitives.
The second run enables the explicit `commons-io-workaround` Maven profile.
Use `--java <actual-JDK-java.exe>` if PATH resolves a Windows launcher shim.
`java-baseline-results.json` and `java-results.json` preserve the separate results.
The runner generates input in an OS temporary directory and deletes it afterward.
No Java dependency jars, upstream code, or generated classpath are committed.
The baseline fails because Commons IO is absent. With the explicit dependency,
all six events hash successfully. Slot, producer sequence and producer recorded-at
mutations change the hash; repository recordTime is excluded. These results do
not establish XML parity or clear the Java transitive closure for production.

## Evidence refresh

`inspect_upstream.py --checkouts <external-directory>` expects public checkouts
whose directory names match the nine repositories in the script. Check out the
recorded revisions before reproducing. It records exact file digests and GitHub
metadata. File digests describe local checkout bytes (this study used Windows);
Git line-ending conversion can change those digests on another platform. Match
the schema/context digests before comparing a reproduced probe result. A run
against new heads is a new study, not a reproduction.

`probe_artifacts.py` reads Maven Central metadata/POMs, inspects three released
jars in memory and validates the external CE Compose configuration. Its default
external directory is the sibling `foundation-upstream` used in this study.
It never starts containers. These evidence scripts require network access;
`interop.py` does not once dependencies and the checkout are available.

The Python scan command was:

```powershell
python -m pip_audit --no-deps --disable-pip -r requirements.lock --timeout 15 --format json --output dependency-audit.json
```

Install `pip-audit==2.10.1` in an isolated tooling environment first. This audits
the explicitly enumerated probe closure, not Maven dependencies or full upstream
applications. Version pins are not artifact hashes. In particular, PyLD's
resolved frozendict dependency declares LGPL v3; it is not approved for product
distribution by inclusion in this research requirements file.
