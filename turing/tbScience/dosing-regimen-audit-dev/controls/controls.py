"""Wrong-method controls for the tolerance study (dev tool). Each control is the oracle with one
deliberate scientific or numerical shortcut.

usage: controls.py <control> --regimen <in.json> --output <out.json>
"""
import argparse
import copy
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ORACLE = HERE.parents[2] / "tasks/life-sciences/pharmacology/dosing-regimen-audit/solution/regimen.py"
spec = importlib.util.spec_from_file_location("rg", ORACLE)
rg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rg)
LEGACY = HERE.parents[2] / "tasks/life-sciences/pharmacology/dosing-regimen-audit/environment/data/legacy/regimencalc.py"


def transform(d, control):
    d = copy.deepcopy(d)
    if control == "bolus_infusion":
        for lst in (d["loading_doses"], d["maintenance"]["doses"]):
            for dose in lst:
                if dose["route"] == "iv_infusion":
                    dose["route"], dose["duration"] = "iv_bolus", None
    if control == "no_lag":
        for f in d["formulations"]:
            f["tlag"], f["n_transit"] = 0.0, 0
    if control == "linear_mm":
        if d["model"]["Vmax"] > 0:
            d["model"]["CL"] += d["model"]["Vmax"] / d["model"]["Km"]
            d["model"]["Vmax"] = 0.0
    return d


def grid_quantities(rep, aux, d, h):
    model, traj, ptr = aux["model"], aux["traj"], aux["ptr"]
    ts = np.arange(0.0, d["horizon"] + h / 2, h)
    ts[-1] = min(ts[-1], d["horizon"])
    Cs = np.array([traj.C(float(t)) for t in ts])
    k = int(np.argmax(Cs))
    rep["cmax"], rep["t_cmax"] = float(Cs[k]), float(ts[k])
    P = ptr.t1
    ps = np.arange(0.0, P, h)
    Cp = np.array([ptr.C(float(t)) for t in ps])
    low, high = d["window"]["low"], d["window"]["high"]
    rep["steady_state"]["cmax"], rep["steady_state"]["cmin"] = float(Cp.max()), float(min(Cp.min(), rep["steady_state"]["trough"]))
    rep["steady_state"]["time_in_window"] = float(np.sum((Cp >= low) & (Cp <= high)) * h)
    return rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("control")
    ap.add_argument("--regimen", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    d = json.load(open(a.regimen))
    c = a.control
    if c == "legacy":
        import subprocess
        subprocess.run([sys.executable, str(LEGACY), "--regimen", a.regimen, "--output", a.output], check=True)
        return
    if c == "loose_rtol":
        rg.RTOL = 1e-6
    if c == "ss_iterate20":
        def periodic_state(model, dd):
            period = float(dd["maintenance"]["period"])
            folded, rate0 = rg.periodic_events(dd)
            x = np.zeros(model.n + 1)
            for _ in range(20):
                x = rg.Trajectory(model, x, 0.0, period, folded, rate0).x_end.copy()
                x[model.n] = 0.0
            return x, rg.Trajectory(model, x, 0.0, period, folded, rate0)
        rg.periodic_state = periodic_state
    rep, aux = rg.solve(transform(d, c))
    rep["regimen_id"] = d["regimen_id"]
    if c in ("grid_01", "grid_001"):
        rep = grid_quantities(rep, aux, d, 0.1 if c == "grid_01" else 0.01)
    if c == "nc_formula":
        lam = np.linalg.eigvals(aux["model"].J0)
        k_term = float(min(-lam.real))
        rep["steady_state"]["n_cycles_to_steady"] = max(1, int(math.ceil(math.log(100.0) / (k_term * d["maintenance"]["period"]))))
    if c == "nc_single":
        # first cycle whose trough is within 1 % (not "every later cycle")
        tr = rep["steady_state"]["trough"]
        n = next((m for m, v in enumerate(aux["troughs"], start=1) if abs(v - tr) <= 0.01 * tr), 60)
        rep["steady_state"]["n_cycles_to_steady"] = int(n)
    json.dump(rep, open(a.output, "w"), indent=1)


if __name__ == "__main__":
    main()
