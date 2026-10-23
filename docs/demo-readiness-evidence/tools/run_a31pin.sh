#!/bin/bash
# review tooling: run_a31pin.sh <dir> <tag>  (fresh db + empty anchor -> API walkthrough -> page screenshots of live standalone pages)
D=$PWD/$1; TAG=$2; ROOT=$PWD; PY=$D/.venv/Scripts/python.exe
rm -rf $D/.local/dr; mkdir -p $D/.local/dr
(cd $D && $PY -c "
from application.service import Manufacturing
Manufacturing('.local/dr/w.sqlite').close()" && rm -f $ROOT/anchors/${TAG}_empty.json && $PY -m application.anchors export --database .local/dr/w.sqlite --anchor $ROOT/anchors/${TAG}_empty.json) >/dev/null
./serve.sh $D $D/.local/dr/w.sqlite 4173 $ROOT/anchors/${TAG}_empty.json
$PY walkthrough.py http://127.0.0.1:4173 walk_${TAG}.json > walk_${TAG}.txt 2>&1; head -1 walk_${TAG}.txt
RT=$D/recall-ui
for r in "passport.html#/passport/MTR-27003/recall:passport_27003" "passport.html#/:passport_index" "investigation.html#/:investigation" "impact.html#/:impact_chooser" "impact.html#/lot/bearing/BR-901/graph:impact_graph" "impact.html#/lot/bearing/BR-901/list:impact_list" "index.html#/:console"; do
  node shot.mjs $RT "http://127.0.0.1:4173/${r%%:*}" shots/${TAG}_${r##*:} 3500
done
