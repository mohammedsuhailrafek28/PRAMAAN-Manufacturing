#!/bin/sh
# One-container start: verify the reference bundle, copy it to a writable directory, start the manufacturing backend on loopback,
# check the archive identity, then start the public Next.js server. Any failure exits non-zero (fail closed); nothing is reset or re-seeded.
set -eu

BUNDLE="${PRAMAAN_BUNDLE_DIR:-/app/deploy/ledger-bundle}"
DATA="${PRAMAAN_DATA_DIR:-/home/app/data}"
API_PORT=4420
WEB_PORT="${PORT:-3000}"

echo "[start] verifying reference bundle checksums"
(cd "$BUNDLE" && sha256sum -c SHA256SUMS)

echo "[start] copying bundle to writable directory"
rm -rf "$DATA"
mkdir -p "$DATA"
for f in ledger.sqlite demo-reference.json demo-reference.json.registry-binding.json; do cp "$BUNDLE/$f" "$DATA/$f"; done

echo "[start] starting backend on 127.0.0.1:$API_PORT"
python -B /app/app.py --database "$DATA/ledger.sqlite" --trusted-anchor "$DATA/demo-reference.json" --port "$API_PORT" &
API_PID=$!

python -B /app/deploy/wait_ready.py "http://127.0.0.1:$API_PORT" "$BUNDLE/IDENTITY.json" 90 || { echo "[start] backend identity check failed"; kill "$API_PID" 2>/dev/null || true; exit 1; }

echo "[start] starting Next.js on 0.0.0.0:$WEB_PORT"
cd /app/stitch-nextjs
PRAMAAN_API_URL="http://127.0.0.1:$API_PORT" node node_modules/next/dist/bin/next start -H 0.0.0.0 -p "$WEB_PORT" &
WEB_PID=$!

stop() { kill "$WEB_PID" "$API_PID" 2>/dev/null || true; wait 2>/dev/null || true; exit 0; }
trap stop TERM INT

# Either process ending ends the container so the platform restarts both from the verified bundle.
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do sleep 2; done
echo "[start] a process exited; stopping"
kill "$WEB_PID" "$API_PID" 2>/dev/null || true
exit 1
