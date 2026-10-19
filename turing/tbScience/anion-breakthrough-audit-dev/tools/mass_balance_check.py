"""Integral mass-balance check of an effluent report (dev tool, not shipped).

For a single feed and a window long enough for every wave to leave the bed, the exact solution
satisfies, for every ion i,
    int_0^BV (x_F,i - x_out,i(b)) db  =  eps (x_F,i - x0_i) + Lambda (y_F,i - y0_i),
with the bed uniformly at the feed state at the end. The left side is integrated from the report
(plateaus exactly, transitions by Gauss-Legendre quadrature of the oracle's state function), so
the residual tests shock positions, fan edges and fan shapes together.
usage: mass_balance_check.py <recipe.json> <ixfront.py path>
"""
import importlib.util
import json
import sys

import numpy as np

recipe = json.load(open(sys.argv[1]))
spec = importlib.util.spec_from_file_location("ixfront", sys.argv[2])
ix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ix)

IONS = ix.IONS
a = np.array([recipe["alpha"][i] for i in IONS])
CT = recipe["C_T_meq_per_L"]
Lam = 1000.0 * recipe["Q_eq_per_L_bed"] / CT
sysm = ix.System(a, recipe["eps"], Lam)
y0 = np.array([recipe["initial_resin_fraction"][i] for i in IONS])
x0 = (y0 / a) / np.sum(y0 / a)
xF = np.array([recipe["feed_program"][0]["composition_meq_per_L"][i] for i in IONS]) / CT
yF = a * xF / np.sum(a * xF)
hD, hU = sysm.roots(x0), sysm.roots(xF)
BV_END = 1e9                              # long enough for every wave to leave
segs = ix.outlet_history_single(sysm, hU, hD, BV_END)
gl_x, gl_w = np.polynomial.legendre.leggauss(64)
lhs = np.zeros(len(IONS))
for seg in segs:
    if seg[0] == "plateau":
        lhs += (seg[2] - seg[1]) * (xF - sysm.x_of(seg[3]))
    elif seg[0] == "fan":
        b0, b1 = seg[1], seg[2]
        bs = 0.5 * (b1 - b0) * gl_x + 0.5 * (b1 + b0)
        vals = np.array([xF - sysm.x_of(ix.fan_state(sysm, seg, b)) for b in bs])
        lhs += 0.5 * (b1 - b0) * (gl_w[:, None] * vals).sum(0)
rhs = sysm.eps * (xF - x0) + Lam * (yF - y0)
print("recipe", recipe["recipe_id"])
for i, ion in enumerate(IONS):
    print(f"  {ion:12s} lhs {lhs[i]: .10f}  rhs {rhs[i]: .10f}  residual {lhs[i]-rhs[i]: .2e}")
print("  waves:", [(s[0], round(s[1], 4)) for s in segs if s[0] != "plateau"])
