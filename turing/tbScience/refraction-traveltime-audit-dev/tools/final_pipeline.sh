#!/bin/bash
# Rerun oracle, Reference A and controls on every model; compare; gate; install expected values and cases.
set -u
cd "$(dirname "$0")/.."
PY=~/.venvs/tbs/bin/python; SOL=../../tasks/earth-sciences/geosciences/refraction-traveltime-audit/solution/raytimes.py
T=../../tasks/earth-sciences/geosciences/refraction-traveltime-audit
mkdir -p fin/oracle fin/refA
for f in gen/models/*.json; do r=$(basename $f .json)
  OPENBLAS_NUM_THREADS=1 $PY -I $SOL --model $f --output fin/oracle/$r.json 2>/dev/null || echo "ORACLE FAILED $r"
  OPENBLAS_NUM_THREADS=1 $PY -I refA/reference.py --model $f --output fin/refA/$r.json 2>/dev/null || echo "REFA FAILED $r"
  for c in precritical no_refl_first coarse legacy; do mkdir -p fin/controls/$c; OPENBLAS_NUM_THREADS=1 $PY controls/controls.py $c --model $f --output fin/controls/$c/$r.json 2>/dev/null || echo "control $c failed $r"; done
done
$PY tools/agree.py fin/oracle fin/refA
$PY - <<'PYEOF'
import json, shutil
from pathlib import Path
T = Path("../../tasks/earth-sciences/geosciences/refraction-traveltime-audit")
for d in (T / "environment/data/models", T / "tests/cases"):
    for p in d.glob("*.json"): p.unlink()
exp = {}
for p in sorted(Path("gen/models").glob("*.json")):
    shutil.copy(p, T / "tests/cases" / p.name)
    if p.stem.startswith("model_"): shutil.copy(p, T / "environment/data/models" / p.name)
    exp[p.stem] = json.loads(Path(f"fin/refA/{p.name}").read_text())
(T / "tests/expected.json").write_text(json.dumps(exp, indent=1) + "\n")
print("installed", len(exp), "cases and expected values")
PYEOF
