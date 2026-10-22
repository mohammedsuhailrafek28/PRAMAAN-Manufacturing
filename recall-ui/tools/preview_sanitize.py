"""Remove customer, destination and operator identifiers from the publicly served preview JSON.

Owner decision O2: the files in public/data are served to anyone who can reach the origin, so they
must not carry customer names, destinations or operator/employee/system-actor identifiers. UI-only
redaction is not an access-control claim and this is not one either: it only shrinks what a static
preview publishes. The live API is a separate backend decision (see docs/FRONTEND_PHASE_A.md).

  * customer / destination values  -> "[not included in preview]" (every occurrence, any key)
  * operator / employee / system actor ids (OP-*, QA-*, EMP-*, SYS-*, SUPPLIER-*, DISPATCH-*, MES-*)
        -> "ACTOR-NN", one stable pseudonym per distinct id per file, so "same actor" / "different
           actors" comparisons in the data keep their meaning without exposing who the actor is
  * shipmentId is kept: it is a synthetic pseudonymous id the shipment/exposure views genuinely need.

Usage:  python tools/preview_sanitize.py [--check] [files...]   (default: all public/data/*.json)
"""
import json
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "public" / "data"
PLACEHOLDER = "[not included in preview]"
ACTOR = re.compile(r"\b(?:OP|QA|EMP|SYS|SUPPLIER|DISPATCH|MES)-[A-Z0-9][A-Z0-9-]*")
SENSITIVE_KEYS = {"customer", "destination"}


def _walk(o, fn):
    if isinstance(o, dict):
        return {fn(k): _walk(v, fn) for k, v in o.items()}
    if isinstance(o, list):
        return [_walk(v, fn) for v in o]
    return fn(o) if isinstance(o, str) else o


def sanitize(doc):
    """Pure and idempotent. Returns a new document."""
    sensitive = set()

    def collect(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in SENSITIVE_KEYS and isinstance(v, str) and v != PLACEHOLDER:
                    sensitive.add(v)
                collect(v)
        elif isinstance(o, list):
            for v in o:
                collect(v)
        elif isinstance(o, str):
            sensitive_actor.update(ACTOR.findall(o))

    sensitive_actor = set()
    collect(doc)
    sensitive_actor = {a for a in sensitive_actor if not a.startswith("ACTOR-")}
    mapping = {a: f"ACTOR-{i:02d}" for i, a in enumerate(sorted(sensitive_actor), start=1)}

    def clean(s):
        for v in sorted(sensitive, key=len, reverse=True):
            s = s.replace(v, PLACEHOLDER)
        return ACTOR.sub(lambda m: mapping.get(m.group(0), m.group(0)), s)

    def fix(o):
        if isinstance(o, dict):
            return {clean(k): (PLACEHOLDER if k in SENSITIVE_KEYS and isinstance(v, str) else fix(v)) for k, v in o.items()}
        if isinstance(o, list):
            return [fix(v) for v in o]
        return clean(o) if isinstance(o, str) else o

    return fix(doc)


def dumps(doc, pretty):
    if pretty:
        return json.dumps(doc, indent=1, sort_keys=True, default=str) + "\n"
    return json.dumps(doc, sort_keys=True, separators=(",", ":"))


def main(argv):
    check = "--check" in argv
    files = [Path(a) for a in argv if not a.startswith("--")] or sorted(DATA.glob("*.json"))
    stale = []
    for f in files:
        raw = f.read_bytes().decode("utf-8")
        pretty = raw[1:2] == "\n"
        out = dumps(sanitize(json.loads(raw)), pretty)
        if out != raw:
            stale.append(f.name)
            if not check:
                f.write_bytes(out.encode("utf-8"))
    if check and stale:
        print("preview JSON still carries sensitive identifiers:", ", ".join(stale)); return 1
    print(("clean: " if check else "sanitized: ") + (", ".join(stale) or "nothing to change"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
