#!/bin/bash
# review tooling: setup_pin.sh <dirName> <sha>   -> fresh clone + README setup steps, timed
N=$1; SHA=$2; cd "$(dirname "$0")"; ROOT=$PWD; rm -rf $N; : > timing_$N.txt
t(){ local n=$1; shift; local s=$(date +%s); "$@" > $ROOT/log_${N}_$n.txt 2>&1; echo "$n rc=$? $(( $(date +%s)-s ))s" >> $ROOT/timing_$N.txt; }
t clone git clone -q https://github.com/mohammedsuhailrafek28/PRAMAAN-Manufacturing.git $N
(cd $N && git checkout -q $SHA && echo "HEAD=$(git rev-parse HEAD)" >> $ROOT/timing_$N.txt)
cd $N
t venv python -m venv .venv
t pip .venv/Scripts/python.exe -m pip install -q -r integration/requirements.lock
cd recall-ui
t npmci npm ci --ignore-scripts
t build npm run build
echo done >> ../../timing_$N.txt
