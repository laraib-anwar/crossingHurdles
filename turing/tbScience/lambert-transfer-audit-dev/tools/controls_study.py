"""Run every control on every generated system and grade it with the verifier's comparison
(dev tool). Prints failures per control and the smallest error of each control that fails, which
is what the tolerance table rests on.

usage: controls_study.py <systems_dir> <expected_dir> <out_dir>
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = HERE.parents[2] / "tasks/physical-sciences/astronomy/lambert-transfer-audit"
spec = importlib.util.spec_from_file_location("tv", TASK / "tests/test_outputs.py")
tv = importlib.util.module_from_spec(spec)
sys.modules["pytest"] = importlib.import_module("pytest")
spec.loader.exec_module(tv)

systems, expected, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
CONTROLS = ["shortway", "zero_rev", "one_branch", "fixedpoint", "tmin_hohmann", "legacy"]
summary = {}
for c in CONTROLS:
    (out / c).mkdir(parents=True, exist_ok=True)
    fails, total, reasons = 0, 0, {}
    for sp in sorted(systems.glob("*.json")):
        rep_path = out / c / sp.name
        if not rep_path.exists():
            r = subprocess.run([sys.executable, str(HERE.parent / "controls/controls.py"), c, "--system", str(sp), "--output", str(rep_path)],
                               capture_output=True, text=True, env=dict(os.environ, OPENBLAS_NUM_THREADS="1"))
            if r.returncode != 0:
                reasons.setdefault("crash", 0)
                reasons["crash"] += 1
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
            key = errs[0].split(":")[1].strip().split(" ")[0] if ":" in errs[0] else errs[0][:30]
            reasons[key] = reasons.get(key, 0) + 1
    summary[c] = dict(fails=fails, total=total, reasons=reasons)
    print(f"{c:10s} fails {fails}/{total} {reasons}")
json.dump(summary, open(out / "summary.json", "w"), indent=1)
