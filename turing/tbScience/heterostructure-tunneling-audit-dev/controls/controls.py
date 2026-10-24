"""Wrong-method controls (dev tool, not shipped), each the exact oracle with one shortcut:

  one_mass    the left-lead mass in every layer and the right lead (no BenDaniel-Duke contrast)
  no_velocity T = |t|^2 without the lead velocity ratio
  staircase   sloped layers replaced by 20 flat steps each
  coarse_scan maxima read off a 1 meV grid of the exact T, no refinement
  box_fd      bound states from second-order finite differences, 0.05 nm grid, hard walls 10 nm into the leads, exact masses
  legacy      the shipped legacy script

usage: controls.py <control> --structure S --output O
"""
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.linalg import eigh_tridiagonal

HERE = Path(__file__).resolve().parent
TASK = HERE.parents[2] / "tasks/physical-sciences/physics/heterostructure-tunneling-audit"
spec = importlib.util.spec_from_file_location("ht", TASK / "solution/hetero.py")
ht = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ht)


def one_mass(m):
    m2 = json.loads(json.dumps(m))
    mL = m2["left_lead"]["mass"]
    for ly in m2["layers"]:
        ly["mass"] = mL
    m2["right_lead"]["mass"] = mL
    return ht.solve(m2)


def no_velocity(m):
    st = ht.Structure(m)
    rep = st.report()
    kfac = lambda E: (math.sqrt(st.mR * (E - st.VR)) / st.mR) / (math.sqrt(st.mL * (E - st.VL)) / st.mL)
    for t in rep["transmission"]:
        t["T"] = t["T"] / kfac(t["E_eV"])
    for x in rep["maxima"]:
        x["T"] = x["T"] / kfac(x["E_eV"])
    return rep


def staircase(m):
    m2 = json.loads(json.dumps(m))
    out = []
    for ly in m2["layers"]:
        if ly["vl_eV"] == ly["vr_eV"]:
            out.append(ly)
        else:
            for i in range(20):
                v = ly["vl_eV"] + (ly["vr_eV"] - ly["vl_eV"]) * (i + 0.5) / 20
                out.append(dict(thickness_nm=ly["thickness_nm"] / 20, mass=ly["mass"], vl_eV=v, vr_eV=v))
    m2["layers"] = out
    return ht.solve(m2)


def coarse_scan(m):
    st = ht.Structure(m)
    rep = st.report()
    lo, hi = m["window_eV"]
    grid = np.arange(lo, hi + 1e-12, 1e-3)
    T = st.T(grid)
    rep["maxima"] = [dict(E_eV=float(grid[k]), T=float(T[k])) for k in range(1, len(grid) - 1) if T[k] > T[k - 1] and T[k] >= T[k + 1]]
    return rep


def box_fd(m):
    rep = ht.solve(m)
    st = ht.Structure(m)
    h = 0.05
    X = sum(ly.d for ly in st.layers)
    xs = np.arange(-10.0, X + 10.0 + 1e-12, h)
    edges = np.cumsum([0.0] + [ly.d for ly in st.layers])

    def region(x):
        if x < 0:
            return st.mL, st.VL
        if x >= X:
            return st.mR, st.VR
        j = min(int(np.searchsorted(edges, x, side="right")) - 1, len(st.layers) - 1)
        ly = st.layers[j]
        return ly.m, ly.vl + (ly.vr - ly.vl) * (x - edges[j]) / ly.d
    MV = [region(x) for x in xs]
    mid_m = [region(0.5 * (a + b))[0] for a, b in zip(xs[:-1], xs[1:])]
    inner = range(1, len(xs) - 1)
    diag = np.array([MV[i][1] + ht.C / h ** 2 * (1 / mid_m[i - 1] + 1 / mid_m[i]) for i in inner])
    off = np.array([-ht.C / (h ** 2 * mid_m[i]) for i in range(1, len(xs) - 2)])
    w = eigh_tridiagonal(diag, off, eigvals_only=True)
    E_th = min(st.VL, st.VR)
    rep["bound_states"] = [dict(E_eV=float(e)) for e in w if e < E_th]
    return rep


def legacy(m):
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mp, op = Path(td) / "m.json", Path(td) / "o.json"
        mp.write_text(json.dumps(m))
        subprocess.run([sys.executable, str(TASK / "environment/data/legacy/qwell.py"), "--structure", str(mp), "--output", str(op)], check=True)
        return json.loads(op.read_text())


CONTROLS = dict(one_mass=one_mass, no_velocity=no_velocity, staircase=staircase, coarse_scan=coarse_scan, box_fd=box_fd, legacy=legacy)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("control", choices=sorted(CONTROLS))
    ap.add_argument("--structure", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    m = json.loads(Path(a.structure).read_text())
    Path(a.output).write_text(json.dumps(CONTROLS[a.control](m), indent=1) + "\n")
