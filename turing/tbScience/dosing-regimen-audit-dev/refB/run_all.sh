#!/usr/bin/env bash
# Run Reference B on all regimens: out/<name>.json (report) and out/<name>.check.json
# (half-step error estimates, Newton residuals, guarantee checks).
# Usage: ./run_all.sh [jobs]      (default 3 parallel jobs)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
if [ "${1:-}" = "--one" ]; then
  f="$2"; n="$(basename "$f" .json)"
  s=$(date +%s)
  python "$here/referee.py" --regimen "$f" --output "$here/out/$n.json" --check "$here/out/$n.check.json"
  echo "$n $(( $(date +%s) - s ))s"
  exit 0
fi
regdir="$here/../gen/regimens"
jobs="${1:-3}"
source "$HOME/.venvs/tbs/bin/activate"
mkdir -p "$here/out"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
ls "$regdir"/*.json | xargs -P "$jobs" -n 1 "$here/run_all.sh" --one
