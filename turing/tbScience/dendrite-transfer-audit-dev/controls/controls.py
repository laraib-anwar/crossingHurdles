"""Wrong-method controls (dev tool, not shipped), each the exact oracle with one shortcut:

  sealed      every terminal treated as sealed (killed and shunted ends ignored)
  infinite    attenuation and transfer by the infinite-cable law exp(-X/lambda) along the path
  somatic     time constants read off the somatic admittance F(s) on a 1e-3-relative scan
              without the exact characteristic function (nearly hidden modes missed), and
              coefficients from a finite difference of F
  lumped      transfer impedance of the lumped RC circuit (DC transfer times 1/(1 + j w tau_m))
  fd          second-order compartmental model, 4 um compartments, no extrapolation
  legacy      the shipped legacy script

usage: controls.py <control> --neuron N --output O
"""
import cmath
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TASK = HERE.parents[2] / "tasks/life-sciences/neuroscience/dendrite-transfer-audit"
spec = importlib.util.spec_from_file_location("ct", TASK / "solution/cabletree.py")
ct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ct)
gspec = importlib.util.spec_from_file_location("gn", HERE.parent / "tools/gen_neurons.py")


def sealed(m):
    m2 = json.loads(json.dumps(m))
    for s in m2["segments"]:
        if s["end"]:
            s["end"] = {"type": "sealed", "g_nS": None}
    rep = ct.solve(m2)
    rep["neuron_id"] = m["neuron_id"]
    return rep


def infinite(m):
    T = ct.Tree(m)
    rep = T.report()
    segs = T.segs

    def X(loc):
        if loc["segment"] == 0:
            return 0.0
        s = segs[loc["segment"]]
        x = s.a * loc["fraction"]
        while s.parent:
            s = segs[s.parent]
            x += s.a
        return x
    for e in rep["attenuation"]:
        e["factor"] = math.exp(-abs(X(e["source"]) - X(e["target"])))
    return rep


def lumped(m):
    T = ct.Tree(m)
    rep = T.report()
    tau_m = np.mean([s.tau for s in T.segs.values()])
    for q in rep["impedance"]:
        V, (Vt,) = T.respond(0.0, q["source"], [q["target"]])
        Z = Vt.real / (1 + 1j * 2 * math.pi * q["frequency_Hz"] * tau_m)
        q["magnitude_MOhm"], q["phase_deg"] = abs(Z) * 1e3, math.degrees(cmath.phase(Z))
    return rep


def somatic(m):
    """Roots of the somatic admittance F(s) = 1/Z_soma on a geometric scan of ratio 1 + 1e-3 (sign
    changes bracket roots and poles alike; a root and a pole closer than the step are missed)."""
    T = ct.Tree(m)
    rep = T.report()
    tau_min = m["tau_min_ms"] * 1e-3

    def F(s):
        gam = T.gammas(s)
        Yd = T.downward(s, gam)
        return (T.Gs + s * T.Cs + sum(Yd[c.id] for c in T.soma_children)).real
    tau_max = max([s.tau for s in T.segs.values()] + [T.Cs / T.Gs])
    grid = -1.0 / tau_min / (1 + 1e-3) ** np.arange(int(math.log(tau_max / tau_min) / math.log(1 + 1e-3)) + 2)
    vals = np.array([F(s) for s in grid])
    roots = []
    for k in range(len(grid) - 1):
        if vals[k] * vals[k + 1] < 0 and abs(vals[k + 1]) < 10 * abs(vals[k]) + 1e-12 and abs(vals[k]) < 10 * abs(vals[k + 1]) + 1e-12:
            from scipy.optimize import brentq
            roots.append(brentq(F, grid[k], grid[k + 1], xtol=1e-300, rtol=1e-15))
    modes = []
    for s in sorted(roots):
        tau = -1 / s
        if tau < tau_min:
            continue
        h = 1e-6 * abs(s)
        dF = (F(s + h) - F(s - h)) / (2 * h)
        modes.append(dict(tau_ms=tau * 1e3, coefficient_MOhm=tau / dF * 1e3))
    rep["modes"] = sorted(modes, key=lambda e: -e["tau_ms"])
    return rep


def fd(m):
    """Compartmental model at 4 um (DC, AC and modes), no extrapolation."""
    gn = importlib.util.module_from_spec(gspec)
    sys.argv = ["gn", str(TASK / "solution/cabletree.py"), "/tmp/gn_unused"]
    gspec.loader.exec_module(gn)
    rep = ct.solve(m)
    taus = [t for t in gn.fd_taus(m) if t >= m["tau_min_ms"]]
    for e, t in zip(rep["modes"], taus):
        e["tau_ms"] = float(t)
    return rep


def legacy(m):
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mp, op = Path(td) / "m.json", Path(td) / "o.json"
        mp.write_text(json.dumps(m))
        subprocess.run([sys.executable, str(TASK / "environment/data/legacy/cableprop.py"), "--neuron", str(mp), "--output", str(op)], check=True)
        return json.loads(op.read_text())


CONTROLS = dict(sealed=sealed, infinite=infinite, lumped=lumped, somatic=somatic, fd=fd, legacy=legacy)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("control", choices=sorted(CONTROLS))
    ap.add_argument("--neuron", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    m = json.loads(Path(a.neuron).read_text())
    Path(a.output).write_text(json.dumps(CONTROLS[a.control](m), indent=1) + "\n")
