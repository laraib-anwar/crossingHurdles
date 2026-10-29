"""Run every control on every generated regimen and grade it with the verifier's comparison
(dev tool). Prints failures per control and the reasons, which is what the tolerance table rests on.

usage: controls_study.py <regimens_dir> <expected_dir> <out_dir>
"""
import importlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = HERE.parents[2] / "tasks/life-sciences/pharmacology/dosing-regimen-audit"
spec = importlib.util.spec_from_file_location("tv", TASK / "tests/test_outputs.py")
tv = importlib.util.module_from_spec(spec)
sys.modules["pytest"] = importlib.import_module("pytest")
spec.loader.exec_module(tv)

regimens, expected, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
CONTROLS = sys.argv[4].split(",") if len(sys.argv) > 4 else ["loose_rtol", "grid_001", "grid_01", "bolus_infusion", "no_lag", "linear_mm", "ss_iterate20", "nc_formula", "nc_single", "legacy"]
summary = {}
for c in CONTROLS:
    (out / c).mkdir(parents=True, exist_ok=True)
    fails, total, reasons, worst = 0, 0, {}, {}
    for sp in sorted(regimens.glob("*.json")):
        rep_path = out / c / sp.name
        if not rep_path.exists():
            r = subprocess.run([sys.executable, str(HERE.parent / "controls/controls.py"), c, "--regimen", str(sp), "--output", str(rep_path)],
                               capture_output=True, text=True, env=dict(os.environ, OPENBLAS_NUM_THREADS="1"))
            if r.returncode != 0:
                reasons["crash"] = reasons.get("crash", 0) + 1
                fails += 1
                total += 1
                continue
        total += 1
        m = json.loads(sp.read_text())
        rep = json.loads(rep_path.read_text())
        exp = json.loads((expected / sp.name).read_text())
        try:
            tv.validate_report(rep, m, sp.stem)
            errs = tv.compare(rep, exp, sp.stem)
        except AssertionError as e:
            errs = [f"contract: {e}"]
        if errs:
            fails += 1
            for e in errs:
                key = e.split(": ", 1)[1].split(" ")[0]
                reasons[key] = reasons.get(key, 0) + 1
    summary[c] = dict(fails=fails, total=total, reasons=reasons)
    print(f"{c:14s} fails {fails}/{total} {reasons}", flush=True)
json.dump(summary, open(out / "summary.json", "w"), indent=1)
