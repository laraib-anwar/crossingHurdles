"""Wrong-method controls (dev tool, not shipped), each the exact oracle with one shortcut:

  shortway    transfer angle always below 180 degrees (retrograde plane when the prograde arc is the long way)
  zero_rev    multi-revolution families ignored (only the N = 0 solution)
  one_branch  only the low branch of each multi-revolution family
  fixedpoint  Kepler's equation by 50 fixed-point sweeps E = M + e sin E (ellipses)
  tmin_hohmann  T_min(N) = (N + 1/2) Hohmann periods between the two radii
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

HERE = Path(__file__).resolve().parent
TASK = HERE.parents[2] / "tasks/physical-sciences/astronomy/lambert-transfer-audit"
spec = importlib.util.spec_from_file_location("lb", TASK / "solution/lambert.py")
lb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lb)


def shortway(m):
    """The short way regardless of direction: when the prograde arc is the long way, solve in a
    frame rotated (properly) so that the short-way angular momentum points along +z, and rotate
    the velocities back; the result is the retrograde short-way arc."""
    orig = lb.lambert

    def rot_to_z(h):
        h = h / np.linalg.norm(h)
        z = np.array([0.0, 0.0, 1.0])
        v = np.cross(h, z)
        c = float(np.dot(h, z))
        if np.linalg.norm(v) < 1e-15:
            return np.eye(3) if c > 0 else np.diag([1.0, -1.0, -1.0])
        vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        return np.eye(3) + vx + vx @ vx * (1.0 / (1.0 + c))

    def lam_short(r1, r2, tof, mu, n_max):
        r1 = np.asarray(r1, float); r2 = np.asarray(r2, float)
        h = np.cross(r1, r2)
        if h[2] < 0:
            R = rot_to_z(h)
            theta, tmins, sols = orig(R @ r1, R @ r2, tof, mu, n_max)
            for s in sols:
                s["v1"], s["v2"] = R.T @ s["v1"], R.T @ s["v2"]
            return theta, tmins, sols
        return orig(r1, r2, tof, mu, n_max)
    lb.lambert = lam_short
    try:
        return lb.solve(m)
    finally:
        lb.lambert = orig


def zero_rev(m):
    rep = lb.solve(m)
    for t in rep["transfers"]:
        t["solutions"] = [s for s in t["solutions"] if s["N"] == 0]
        t["best"] = 0
    return rep


def one_branch(m):
    rep = lb.solve(m)
    for t in rep["transfers"]:
        t["solutions"] = [s for s in t["solutions"] if s["branch"] != "high"]
        t["best"] = min(range(len(t["solutions"])), key=lambda k: t["solutions"][k]["dv_km_s"])
    return rep


def fixedpoint(m):
    orig = lb.kepler_E

    def fp(M, e):
        M = math.fmod(M, 2 * math.pi)
        E = M
        for _ in range(50):
            E = M + e * math.sin(E)
        return E
    lb.kepler_E = fp
    try:
        return lb.solve(m)
    finally:
        lb.kepler_E = orig


def tmin_hohmann(m):
    rep = lb.solve(m)
    mu = m["mu_km3_s2"]
    bodies = {o["name"]: lb.Body(o, mu) for o in m["objects"]}
    for q, t in zip(m["transfer_queries"], rep["transfers"]):
        rA, _ = bodies[q["from"]].state(q["t1_days"]); rB, _ = bodies[q["to"]].state(q["t2_days"])
        a_h = 0.5 * (np.linalg.norm(rA) + np.linalg.norm(rB))
        P = 2 * math.pi * math.sqrt(a_h ** 3 / mu) / 86400
        t["t_min_days"] = [(N + 0.5) * P for N in range(1, q["n_max"] + 1)]
    return rep


def legacy(m):
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mp, op = Path(td) / "m.json", Path(td) / "o.json"
        mp.write_text(json.dumps(m))
        subprocess.run([sys.executable, str(TASK / "environment/data/legacy/porkchop.py"), "--system", str(mp), "--output", str(op)], check=True)
        return json.loads(op.read_text())


CONTROLS = dict(shortway=shortway, zero_rev=zero_rev, one_branch=one_branch, fixedpoint=fixedpoint, tmin_hohmann=tmin_hohmann, legacy=legacy)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("control", choices=sorted(CONTROLS))
    ap.add_argument("--system", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    m = json.loads(Path(a.system).read_text())
    Path(a.output).write_text(json.dumps(CONTROLS[a.control](m), indent=1) + "\n")
