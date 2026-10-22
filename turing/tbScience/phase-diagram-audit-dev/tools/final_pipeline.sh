#!/bin/bash
# Rerun oracle, Reference A and controls on every generated system; compare; install expected values and cases.
set -u
cd "$(dirname "$0")/.."
PY=~/.venvs/tbs/bin/python
T=../../tasks/physical-sciences/materials-science/phase-diagram-audit
SOL=$T/solution/phasediagram.py
mkdir -p fin/oracle fin/refA fin/legacy
for f in gen/systems/*.json; do r=$(basename $f .json)
  OPENBLAS_NUM_THREADS=1 $PY -I $SOL --system $f --output fin/oracle/$r.json 2>/dev/null || echo "ORACLE FAILED $r"
  OPENBLAS_NUM_THREADS=1 $PY -I refA/reference.py --system $f --output fin/refA/$r.json 2>/dev/null || echo "REFA FAILED $r"
  OPENBLAS_NUM_THREADS=1 $PY -I $T/environment/data/legacy/tangentdiag.py --system $f --output fin/legacy/$r.json 2>/dev/null || echo "LEGACY FAILED $r"
done
$PY tools/agree.py fin/oracle fin/refA
$PY - <<'PYEOF'
import json, shutil
from pathlib import Path
T = Path("../../tasks/physical-sciences/materials-science/phase-diagram-audit")
for d in (T / "environment/data/systems", T / "tests/cases"):
    d.mkdir(parents=True, exist_ok=True)
    for p in d.glob("*.json"): p.unlink()
exp = {}
for p in sorted(Path("gen/systems").glob("*.json")):
    shutil.copy(p, T / "tests/cases" / p.name)
    if p.stem.startswith("model_"): shutil.copy(p, T / "environment/data/systems" / p.name)
    exp[p.stem] = json.loads(Path(f"fin/refA/{p.name}").read_text())
(T / "tests/expected.json").write_text(json.dumps(exp, indent=1) + "\n")
shutil.copy(T / "environment/data/legacy/tangentdiag.py", T / "tests/legacy/tangentdiag.py")
shutil.copy("refA/reference.py", T / "tests/reference/reference.py")
print("installed", len(exp), "cases and expected values")
PYEOF
