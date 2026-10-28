#!/bin/sh
# Run the Reference B referee on every frame in FRAMEDIR against REPDIR/<frame_id>.json.
# usage: sh refB/run_set.sh FRAMEDIR REPDIR OUTDIR [PAR]
# writes OUTDIR/<id>.json (verdict) and OUTDIR/<id>.log (summary line + verbose trace),
# OUTDIR/summary.txt, and prints the pass list. Exit 0 iff every frame passes.
set -u
if [ $# -lt 3 ]; then
  echo "usage: sh $0 FRAMEDIR REPDIR OUTDIR [PAR]" >&2
  exit 2
fi
FRAMEDIR=$1
REPDIR=$2
OUTDIR=$3
PAR=${4:-1}
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${PYTHON:-/Users/adnananwar/.venvs/tbs/bin/python}
[ -x "$PY" ] || PY=python3
mkdir -p "$OUTDIR"
export PY HERE REPDIR OUTDIR
ls "$FRAMEDIR"/*.json | xargs -n 1 -P "$PAR" sh -c '
  f=$1; id=$(basename "$f" .json)
  "$PY" "$HERE/referee.py" --frame "$f" --report "$REPDIR/$id.json" --out "$OUTDIR/$id.json" --verbose > "$OUTDIR/$id.log" 2>&1
  echo "exit=$?" >> "$OUTDIR/$id.log"
' sh
: > "$OUTDIR/summary.txt"
npass=0; nall=0; fails=""
for f in "$FRAMEDIR"/*.json; do
  id=$(basename "$f" .json)
  line=$(grep "^$id pass=" "$OUTDIR/$id.log" | tail -1)
  [ -n "$line" ] || line="$id pass=False (no summary line; see $OUTDIR/$id.log)"
  echo "$line" >> "$OUTDIR/summary.txt"
  nall=$((nall + 1))
  case "$line" in
    *"pass=True"*) npass=$((npass + 1));;
    *) fails="$fails $id";;
  esac
done
cat "$OUTDIR/summary.txt"
echo "PASS $npass/$nall"
[ -z "$fails" ] || echo "NOT PASSED:$fails"
[ -z "$fails" ]
