#!/bin/sh
# Referee every report in REPORT_DIR against SYSTEM_DIR/<same name>; verdicts to OUT_DIR/<id>.json/.log
# usage: sh run_set.sh SYSTEM_DIR REPORT_DIR OUT_DIR [PARALLEL]
SYS=$1; REP=$2; OUT=$3; PAR=${4:-1}
PY=${PYTHON:-/Users/adnananwar/.venvs/tbs/bin/python}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$OUT"
ls "$REP" | grep '\.json$' | sed 's/\.json$//' | xargs -P "$PAR" -n 1 sh -c \
  '"$0" "$1/referee.py" --system "$2/$5.json" --report "$3/$5.json" --out "$4/$5.json" > "$4/$5.log" 2>&1' \
  "$PY" "$HERE" "$SYS" "$REP" "$OUT"
cat "$OUT"/*.log | cut -c1-160
