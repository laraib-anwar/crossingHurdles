"""Wrong-method controls (dev tool, not shipped), each the exact oracle with one shortcut:

  grid        tie-line and region compositions read off the hull of the 5e-4 composition grid
              without Newton polish (events exact)
  scan        event temperatures located only to the 0.1 K scan point below the event (the
              topology-scan habit without refinement); compositions exact
  rule        invariant class from the "liquid takes part -> eutectic type" rule instead of the
              stability of the middle phase; names follow
  spinodal    miscibility gaps bounded by the spinodal (d2G/dx2 = 0) instead of the binodal
  legacy      the shipped legacy script

usage: controls.py <control> --system S --output O
"""
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

HERE = Path(__file__).resolve().parent
TASK = HERE.parents[2] / "tasks/physical-sciences/materials-science/phase-diagram-audit"
spec = importlib.util.spec_from_file_location("pd", TASK / "solution/phasediagram.py")
pd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pd)


def grid(m):
    """Every solution-phase composition rounded to the nearest point of the oracle's 5e-4 grid
    (geometric near the ends): the precision of a grid hull without Newton polish."""
    rep = pd.solve(m)
    comp_x = {c["name"] for c in m["compounds"]}

    def snap(x):
        return float(pd.XG[int(np.argmin(np.abs(pd.XG - x)))])
    for iso in rep["isotherms"]:
        for g in iso["single_phase_regions"]:
            if g["x_lo"] > 0: g["x_lo"] = snap(g["x_lo"])
            if g["x_hi"] < 1: g["x_hi"] = snap(g["x_hi"])
        for t in iso["tie_lines"]:
            if t["left_phase"] not in comp_x: t["x_left"] = snap(t["x_left"])
            if t["right_phase"] not in comp_x: t["x_right"] = snap(t["x_right"])
    for e in rep["invariants"]:
        for q in e["phases"]:
            if q["phase"] not in comp_x: q["x"] = snap(q["x"])
    for key in ("congruent_points", "critical_points"):
        for e in rep[key]:
            if key == "critical_points" or (e["phase_above"] not in comp_x and e["phase_below"] not in comp_x):
                e["x"] = snap(e["x"])
    return rep


def scan(m):
    rep = pd.solve(m)
    T_lo = m["window_K"][0]
    for key in ("invariants", "congruent_points", "critical_points"):
        for e in rep[key]:
            e["temperature_K"] = T_lo + math.floor((e["temperature_K"] - T_lo) / 0.1) * 0.1
    return rep


def rule(m):
    rep = pd.solve(m)
    for e in rep["invariants"]:
        liq = [p["phase"] == "liquid" for p in e["phases"]]
        e["class"] = "eutectic"
        if liq[1]:
            e["name"] = "eutectic" if not (liq[0] or liq[2]) else "monotectic"
        else:
            e["name"] = "eutectoid" if not (liq[0] or liq[2]) else "metatectic"
    return rep


def spinodal(m):
    S = pd.System(m)
    rep = S.report()
    for iso in rep["isotherms"]:
        T = iso["temperature_K"]
        for t in iso["tie_lines"]:
            if t["left_phase"] == t["right_phase"]:
                ph = next(s for s in S.sols if s.name == t["left_phase"])
                xs = np.linspace(t["x_left"], t["x_right"], 2001)
                g2 = ph.Gxx(xs, T)
                k = np.flatnonzero(g2 < 0)
                if len(k):
                    a = brentq(lambda x: float(ph.Gxx(x, T)), xs[k[0] - 1], xs[k[0]])
                    b = brentq(lambda x: float(ph.Gxx(x, T)), xs[k[-1]], xs[k[-1] + 1])
                    t["x_left"], t["x_right"] = a, b
        regs = iso["single_phase_regions"]
        for k, g in enumerate(regs):
            for t in iso["tie_lines"]:
                if t["right_phase"] == g["phase"] and abs(t["x_right"] - g["x_lo"]) < 0.2 and k > 0:
                    g["x_lo"] = t["x_right"]
                if t["left_phase"] == g["phase"] and abs(t["x_left"] - g["x_hi"]) < 0.2 and k < len(regs) - 1:
                    g["x_hi"] = t["x_left"]
    return rep


def legacy(m):
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mp, op = Path(td) / "m.json", Path(td) / "o.json"
        mp.write_text(json.dumps(m))
        subprocess.run([sys.executable, str(TASK / "environment/data/legacy/tangentdiag.py"), "--system", str(mp), "--output", str(op)], check=True)
        return json.loads(op.read_text())


CONTROLS = dict(grid=grid, scan=scan, rule=rule, spinodal=spinodal, legacy=legacy)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("control", choices=sorted(CONTROLS))
    ap.add_argument("--system", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    m = json.loads(Path(a.system).read_text())
    Path(a.output).write_text(json.dumps(CONTROLS[a.control](m), indent=1) + "\n")
