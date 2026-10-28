"""Wrong-method controls (dev tool, not shipped), each the exact oracle with one shortcut:

  no_j0        Wittrick-Williams count without the member-local term J0 (sign count only)
  fe1_consistent  one cubic element per member with the consistent mass matrix (frequencies and harmonic)
  fe4_consistent  four cubic elements per member, consistent mass
  lumped_loads uniform member loads as half-loads at the ends, no fixed-end moments (statics)
  no_axial     axial deformation suppressed: EA scaled by 1e6 (frequencies, statics, harmonic)
  legacy       the shipped legacy script

usage: controls.py <control> --frame F --output O
"""
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.linalg import eigh

HERE = Path(__file__).resolve().parent
TASK = HERE.parents[2] / "tasks/engineering-sciences/civil-engineering/frame-vibration-audit"
spec = importlib.util.spec_from_file_location("fd", TASK / "solution/framedyn.py")
fd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fd)


def no_j0(m):
    F = fd.Frame(m)
    for mb in F.members:
        mb.j0 = lambda omega: 0
    return F.report()


def fe_model(m, nel):
    """Cubic Hermite frame elements, consistent mass; returns K, M on free dofs and dof maps."""
    nodes = {n["id"]: (n["x"], n["y"]) for n in m["nodes"]}
    coords = list(nodes.values())
    dofs = {}
    def new_node(xy):
        coords.append(xy)
        return len(coords)
    elems = []
    for mb in m["members"]:
        xi, yi = nodes[mb["i"]]; xj, yj = nodes[mb["j"]]
        chain = [mb["i"]]
        for k in range(1, nel):
            chain.append(new_node((xi + (xj - xi) * k / nel, yi + (yj - yi) * k / nel)))
        chain.append(mb["j"])
        for a, b in zip(chain, chain[1:]):
            elems.append((a, b, mb))
    N = len(coords)
    K = np.zeros((3 * N, 3 * N)); M = np.zeros((3 * N, 3 * N))
    for a, b, mb in elems:
        xa, ya = coords[a - 1]; xb, yb = coords[b - 1]
        L = math.hypot(xb - xa, yb - ya); cx, cy = (xb - xa) / L, (yb - ya) / L
        E, A, I, rho = mb["E"], mb["A"], mb["I"], mb["rho"]
        k = E * I / L ** 3
        Ke = np.array([[E * A / L, 0, 0, -E * A / L, 0, 0], [0, 12 * k, 6 * k * L, 0, -12 * k, 6 * k * L], [0, 6 * k * L, 4 * k * L * L, 0, -6 * k * L, 2 * k * L * L],
                       [-E * A / L, 0, 0, E * A / L, 0, 0], [0, -12 * k, -6 * k * L, 0, 12 * k, -6 * k * L], [0, 6 * k * L, 2 * k * L * L, 0, -6 * k * L, 4 * k * L * L]])
        mm = rho * A * L / 420
        Me = mm * np.array([[140, 0, 0, 70, 0, 0], [0, 156, 22 * L, 0, 54, -13 * L], [0, 22 * L, 4 * L * L, 0, 13 * L, -3 * L * L],
                            [70, 0, 0, 140, 0, 0], [0, 54, 13 * L, 0, 156, -22 * L], [0, -13 * L, -3 * L * L, 0, -22 * L, 4 * L * L]])
        T = np.zeros((6, 6))
        for o in (0, 3):
            T[o, o], T[o, o + 1], T[o + 1, o], T[o + 1, o + 1], T[o + 2, o + 2] = cx, cy, -cy, cx, 1.0
        idx = [3 * (a - 1), 3 * (a - 1) + 1, 3 * (a - 1) + 2, 3 * (b - 1), 3 * (b - 1) + 1, 3 * (b - 1) + 2]
        K[np.ix_(idx, idx)] += T.T @ Ke @ T; M[np.ix_(idx, idx)] += T.T @ Me @ T
    for n in m["nodes"]:
        for k in (0, 1):
            M[3 * (n["id"] - 1) + k, 3 * (n["id"] - 1) + k] += n["mass_kg"]
    fixed = {3 * (n["id"] - 1) + k for n in m["nodes"] for k, d in enumerate(("ux", "uy", "rz")) if n["support"][d]}
    free = [i for i in range(3 * N) if i not in fixed]
    return K[np.ix_(free, free)], M[np.ix_(free, free)], free, N


def fe_control(m, nel):
    rep = fd.solve(m)
    K, M, free, N = fe_model(m, nel)
    w2 = eigh(K, M, eigvals_only=True)
    freqs = np.sqrt(np.maximum(w2, 0)) / (2 * math.pi)
    rep["frequencies_Hz"] = [float(f) for f in freqs[: m["n_modes"]]]
    rep["count_below"] = int(np.sum(freqs <= m["f_max_Hz"]))
    for q, h in zip(m["harmonic_queries"], rep["harmonic"]):
        omega = 2 * math.pi * q["f_Hz"]
        Fv = np.zeros(3 * N); Fv[3 * (q["load_node"] - 1) + ("ux", "uy", "rz").index(q["load_dof"])] = q["amplitude"]
        u = np.zeros(3 * N); u[free] = np.linalg.solve(K - omega * omega * M, Fv[free])
        h["U"] = float(u[3 * (q["response_node"] - 1) + ("ux", "uy", "rz").index(q["response_dof"])])
    return rep


def fe1_consistent(m):
    return fe_control(m, 1)


def fe4_consistent(m):
    return fe_control(m, 4)


def lumped_loads(m):
    F = fd.Frame(m)
    for mb in F.members:
        orig_T = mb.T
        def fe(wx, wy, mb=mb):
            L = mb.L
            return np.array([wx * L / 2, wy * L / 2, 0.0, wx * L / 2, wy * L / 2, 0.0])
        mb.fixed_end_global = fe
    return F.report()


def no_axial(m):
    m2 = json.loads(json.dumps(m))
    for mb in m2["members"]:
        mb["A"] = mb["A"] * 1e6
    rep = fd.solve(m2)
    # keep the member mass as in the original frame: rescale rho
    m3 = json.loads(json.dumps(m))
    for mb in m3["members"]:
        mb["A"] = mb["A"] * 1e6
        mb["rho"] = mb["rho"] / 1e6
    return fd.solve(m3)


def legacy(m):
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mp, op = Path(td) / "m.json", Path(td) / "o.json"
        mp.write_text(json.dumps(m))
        subprocess.run([sys.executable, str(TASK / "environment/data/legacy/framefreq.py"), "--frame", str(mp), "--output", str(op)], check=True)
        return json.loads(op.read_text())


CONTROLS = dict(no_j0=no_j0, fe1_consistent=fe1_consistent, fe4_consistent=fe4_consistent, lumped_loads=lumped_loads, no_axial=no_axial, legacy=legacy)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("control", choices=sorted(CONTROLS))
    ap.add_argument("--frame", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    m = json.loads(Path(a.frame).read_text())
    Path(a.output).write_text(json.dumps(CONTROLS[a.control](m), indent=1) + "\n")
