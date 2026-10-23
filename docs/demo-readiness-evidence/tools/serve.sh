#!/bin/bash
# review tooling: serve.sh <checkoutDir> <db> <port> [anchor]   (kills the port first; prints startup ms)
D=$1; DB=$2; PORT=$3; ANCHOR=$4
for p in $(netstat -ano | grep ":$PORT " | grep LISTENING | awk '{print $5}' | sort -u); do taskkill //F //PID $p >/dev/null 2>&1; done
PY=$D/.venv/Scripts/python.exe
cd $D
ARGS="--database $DB --port $PORT"; [ -n "$ANCHOR" ] && ARGS="$ARGS --trusted-anchor $ANCHOR"
t0=$(date +%s%N)
($PY app.py $ARGS > $D/../srv_$PORT.log 2>&1 &)
for i in $(seq 1 100); do curl -s -o /dev/null http://127.0.0.1:$PORT/api/session && break; sleep 0.2; done
echo "server up on $PORT in $(( ($(date +%s%N)-t0)/1000000 ))ms :: $ARGS"
