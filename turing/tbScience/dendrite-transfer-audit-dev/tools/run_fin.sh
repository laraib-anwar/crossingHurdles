#!/bin/bash
# oracle, Reference A and referee on every neuron in gen/neurons lacking outputs
cd "$(dirname "$0")/.."
PY=~/.venvs/tbs/bin/python; SOL=../../tasks/life-sciences/neuroscience/dendrite-transfer-audit/solution/cabletree.py
for f in gen/neurons/*.json; do r=$(basename $f .json)
  [ -f fin/oracle/$r.json ] || OPENBLAS_NUM_THREADS=1 $PY -I $SOL --neuron $f --output fin/oracle/$r.json 2>/dev/null || echo "ORACLE FAILED $r"
  [ -f fin/refA/$r.json ] || OPENBLAS_NUM_THREADS=1 $PY -I refA/reference.py --neuron $f --output fin/refA/$r.json >/dev/null 2>&1 || echo "REFA FAILED $r"
  [ -f fin/refB/$r.json ] || { OPENBLAS_NUM_THREADS=1 $PY refB/referee.py --neuron $f --report fin/oracle/$r.json --out fin/refB/$r.json --quiet > fin/refB/$r.log 2>&1; echo "$r referee exit $?"; }
done
echo RUNFIN_DONE
