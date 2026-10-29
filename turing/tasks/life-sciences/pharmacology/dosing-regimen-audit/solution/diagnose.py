"""Find executable witnesses of the legacy script's defects at run time.

Runs the legacy script and the corrected program on the shipped regimens, compares the diagnosis
quantities of the spec, and writes diagnosis.json with one entry per defect. Nothing is stored.

usage: diagnose.py --program <regimen.py> --legacy <regimencalc.py> --regimens <dir> --output <diagnosis.json>
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DESCRIPTIONS = {
    "concentration": "Infusions are placed as boluses at their start, absorption lag and transit compartments are "
                     "dropped and saturable elimination is replaced by the first-order rate CL + Vmax/Km, so the "
                     "concentration-time course is wrong whenever a regimen has any of these features.",
    "auc": "The AUC is a linear trapezoid on a 0.1 h grid of a curve with exponential segments and dose "
           "discontinuities, and the curve itself is the simplified superposition model.",
    "cmax": "The peak is the largest value on a 0.1 h grid of the simplified model: it misses the true maximum "
            "between grid points and the shape change from infusions, lag and saturable elimination.",
    "t_cmax": "The time of the peak is a grid point of a 0.1 h grid, not the time at which dC/dt vanishes or the "
              "infusion ends.",
    "ss_cmax": "Steady state is approximated by the 20th maintenance cycle of the simplified linear model instead of "
               "the periodic solution of the full model.",
    "ss_cmin": "The steady-state minimum is read off a 0.1 h grid of the 20th cycle of the simplified model.",
    "ss_trough": "The steady-state trough is the end of the 20th cycle of the simplified linear model; with slow "
                 "accumulation or saturable elimination it has not converged to the periodic solution.",
    "time_in_window": "Time in the window is a count of 0.1 h grid points inside the window on the simplified curve, "
                      "not the measure of the exact crossing intervals.",
    "n_cycles_to_steady": "The number of cycles to steady state is ln(100)/(k_term period) from the terminal rate "
                          "constant of the linearised model, which ignores loading doses, the actual trough sequence "
                          "and saturable elimination.",
}
ORDER = ["n_cycles_to_steady", "concentration", "ss_trough", "cmax", "time_in_window", "auc", "t_cmax", "ss_cmax", "ss_cmin"]


def run(program, path, out_path):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    subprocess.run([sys.executable, str(program), "--regimen", str(path), "--output", str(out_path)],
                   check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    with open(out_path, encoding="utf-8") as fh:
        return json.load(fh)


def value(rep, q, k):
    if q == "concentration":
        return rep["concentrations"][k]
    if q in ("auc", "cmax", "t_cmax"):
        return rep[q]
    if q.startswith("ss_"):
        return rep["steady_state"][q[3:]]
    return rep["steady_state"][q]


def differs(q, a, b, S):
    if q == "n_cycles_to_steady":
        return a != b
    if q in ("t_cmax", "time_in_window"):
        return abs(a - b) > 1e-3
    if q == "auc":
        return abs(a - b) > 1e-5 * abs(b)
    return abs(a - b) > 1e-5 * S


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--regimens", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    results = []
    with tempfile.TemporaryDirectory() as td:
        for rp in sorted(Path(a.regimens).glob("*.json")):
            reg = json.loads(rp.read_text(encoding="utf-8"))
            try:
                leg = run(a.legacy, rp, Path(td) / "l.json")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
                continue
            results.append((reg, leg, run(a.program, rp, Path(td) / "c.json")))
    defects = []
    for q in ORDER:
        for reg, leg, cor in results:
            S = cor["cmax"]
            found = None
            if q == "concentration":
                for k in range(len(reg["query_times"])):
                    if differs(q, leg["concentrations"][k], cor["concentrations"][k], S):
                        found = (k, leg["concentrations"][k], cor["concentrations"][k])
                        break
            else:
                lv, cv = value(leg, q, None), value(cor, q, None)
                if differs(q, lv, cv, S):
                    found = (None, lv, cv)
            if found:
                k, lv, cv = found
                defects.append(dict(description=DESCRIPTIONS[q], regimen=reg, quantity=q, index=k,
                                    legacy_value=lv, correct_value=cv))
                break
        if len(defects) >= 8:
            break
    assert len(defects) >= 3, "too few witnesses found"
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump({"defects": defects}, fh, indent=1)
        fh.write("\n")
    print("diagnosis:", ", ".join(f"{d['quantity']}@{d['regimen']['regimen_id']}" for d in defects))


if __name__ == "__main__":
    main()
