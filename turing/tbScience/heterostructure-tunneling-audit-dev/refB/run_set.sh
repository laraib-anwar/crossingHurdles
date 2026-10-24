#!/bin/sh
# Run the Ref B referee on every structure in SYSDIR against REPDIR/<structure_id>.json.
#   sh refB/run_set.sh SYSDIR REPDIR OUTDIR [PAR] [extra referee args...]
# Writes OUTDIR/<id>.json (verdict) and OUTDIR/<id>.log (summary line + stderr),
# then prints the pass list and OUTDIR/summary.txt.
set -u
if [ $# -lt 3 ]; then
  echo "usage: sh run_set.sh SYSDIR REPDIR OUTDIR [PAR] [referee args...]" >&2
  exit 2
fi
SYSDIR=$1; REPDIR=$2; OUTDIR=$3; PAR=${4:-2}
shift 3; [ $# -gt 0 ] && shift
EXTRA="$*"
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${PYTHON:-/Users/adnananwar/.venvs/tbs/bin/python}
mkdir -p "$OUTDIR"
export HERE PY REPDIR OUTDIR EXTRA
ls "$SYSDIR"/*.json | xargs -n 1 -P "$PAR" sh -c '
  f="$1"
  id=$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))[\"structure_id\"])" "$f")
  "$PY" "$HERE/referee.py" --structure "$f" --report "$REPDIR/$id.json" --out "$OUTDIR/$id.json" $EXTRA > "$OUTDIR/$id.log" 2>&1
  echo "exit=$?" >> "$OUTDIR/$id.log"
' sh
: > "$OUTDIR/summary.txt"
for f in "$OUTDIR"/*.log; do head -n 1 "$f" >> "$OUTDIR/summary.txt"; done
cat "$OUTDIR/summary.txt"
np=$(grep -c "pass=True" "$OUTDIR/summary.txt")
nt=$(ls "$SYSDIR"/*.json | wc -l | tr -d " ")
echo "PASS $np / $nt"
grep -v "pass=True" "$OUTDIR/summary.txt" | sed "s/^/NOT PASSING: /"
exit 0
