#!/bin/sh
# Produce out/<name>.json for every regimen with Reference A, and record the SHA-256 of each
# input used in inputs.sha256.
# Usage: sh run_all.sh [regimen_dir]   (default ../gen/regimens)
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
RDIR="${1:-$HERE/../gen/regimens}"
. "$HOME/.venvs/tbs/bin/activate"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONHASHSEED=0
mkdir -p "$HERE/out"
: > "$HERE/inputs.sha256"
for f in "$RDIR"/*.json; do
  name="$(basename "$f" .json)"
  (cd "$RDIR" && shasum -a 256 "$name.json") >> "$HERE/inputs.sha256"
  t0=$(python -c 'import time; print(time.time())')
  python "$HERE/reference.py" --regimen "$f" --output "$HERE/out/$name.json"
  t1=$(python -c 'import time; print(time.time())')
  python -c "print('%-10s %6.2f s' % ('$name', $t1 - $t0))"
done
