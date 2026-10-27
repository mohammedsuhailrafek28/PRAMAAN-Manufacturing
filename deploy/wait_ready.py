"""Wait for the backend and require the exact reference identity. Read-only: one or more GETs of /api/snapshot. Usage: wait_ready.py URL IDENTITY.json TIMEOUT_SECONDS"""
import json
import sys
import time
import urllib.request


def snapshot(base):
    with urllib.request.urlopen(base.rstrip("/") + "/api/snapshot", timeout=10) as r:
        return json.load(r)


def check(snap, want):
    f, c = snap["freshness"], snap["checkpoint"]
    got = dict(archiveId=f["archiveId"], sequence=f["sequence"], headHash=f["headHash"], events=sum(u["eventCount"] for u in snap["units"]),
               motors=len(snap["units"]), checkpointState=c["state"], anchoredSequence=c["anchoredSequence"])
    bad = {k: (got[k], want[k]) for k in got if got[k] != want[k]}
    return got, bad


def main():
    base, ident, timeout = sys.argv[1], sys.argv[2], float(sys.argv[3])
    want = json.load(open(ident, encoding="utf-8"))
    end = time.time() + timeout
    last = "not started"
    while time.time() < end:
        try:
            got, bad = check(snapshot(base), want)
            if bad:
                print("[wait_ready] IDENTITY MISMATCH:", json.dumps(bad), file=sys.stderr)
                return 1
            print(f"[wait_ready] ok archive {got['archiveId']} sequence {got['sequence']} events {got['events']} motors {got['motors']} checkpoint {got['checkpointState']}", flush=True)
            return 0
        except Exception as e:  # backend still starting
            last = type(e).__name__
            time.sleep(1)
    print("[wait_ready] backend not ready:", last, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
