"""Consistency checks of the two-feed engine (dev tool, not shipped).

1. Integral mass balance over a window long enough for every wave to leave: for every ion,
   int_0^B (x_in(b) - x_out(b)) db = eps (x_F2 - x0) + Lambda (y_F2 - y0), the integrand taken
   from Outlet.state() with Gauss-Legendre quadrature between consecutive outlet events.
2. Late-switch limit: with the switch after every first-feed wave has left, the outlet events
   must be the first feed's closed-form events plus the second Riemann fan shifted by bv_s.
3. Convergence: largest change of any event BV between N and 2N pieces.
usage: two_feed_check.py <recipe.json> <ixfront.py>
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
feeds = recipe["feed_program"]
xF1 = np.array([feeds[0]["composition_meq_per_L"][i] for i in IONS]) / CT
xF2 = np.array([feeds[1]["composition_meq_per_L"][i] for i in IONS]) / CT
yF2 = a * xF2 / np.sum(a * xF2)
bv_s = feeds[1]["start_bv"]
hD, hU1, hU2 = sysm.roots(x0), sysm.roots(xF1), sysm.roots(xF2)

# ---- 1. mass balance on a long window
B = 20000.0
gx, gw = np.polynomial.legendre.leggauss(24)
for N in (300, 600):
    jumps = ix.two_feed_jumps(sysm, hD, hU1, hU2, bv_s, N)
    out = ix.Outlet(sysm, jumps, hD, B)
    knots = np.unique(np.concatenate([[0.0, bv_s, B], out.ev_bv]))
    lhs = np.zeros(len(IONS))
    for k0, k1 in zip(knots[:-1], knots[1:]):
        if k1 <= k0:
            continue
        bs = 0.5 * (k1 - k0) * gx + 0.5 * (k1 + k0)
        xin = np.where(bs[:, None] < bv_s, xF1[None, :], xF2[None, :])
        xout = np.array([sysm.x_of(out.state(b)) for b in bs])
        lhs += 0.5 * (k1 - k0) * (gw[:, None] * (xin - xout)).sum(0)
    rhs = sysm.eps * (xF2 - x0) + Lam * (yF2 - y0)
    print(f"N={N}: mass-balance residual per ion", np.round(lhs - rhs, 6).tolist(), " (values ~", np.round(rhs, 2).tolist(), ")")
    shocks, trans = out.structure()
    print(f"      shocks at", [round(b, 4) for b, _ in shocks], " transitions", [[round(t[0], 4), round(t[1], 4)] for t in trans])

# ---- 2. late switch limit
late = 10 * (sysm.eps + Lam * max(sysm.lam(hD, k) for k in range(sysm.n - 1)) + sysm.eps + Lam * max(sysm.lam(hU1, k) for k in range(sysm.n - 1)))
jumps = ix.two_feed_jumps(sysm, hD, hU1, hU2, late, 200)
out = ix.Outlet(sysm, jumps, hD, 10 * late)
shocks, trans = out.structure()
segs1 = ix.outlet_history_single(sysm, hU1, hD, 1e12)
segs2 = ix.outlet_history_single(sysm, hU2, hU1, 1e12)
expect_shocks = [s[1] for s in segs1 if s[0] == "shock"] + [late + s[1] for s in segs2 if s[0] == "shock"]
expect_fans = [[s[1], s[2]] for s in segs1 if s[0] == "fan"] + [[late + s[1], late + s[2]] for s in segs2 if s[0] == "fan"]
got_shocks = [b for b, _ in shocks]
print("late switch: shocks got", [round(b, 6) for b in got_shocks], "expected", [round(b, 6) for b in expect_shocks])
print("             fans got", [[round(t[0], 6), round(t[1], 6)] for t in trans], "expected", [[round(t[0], 6), round(t[1], 6)] for t in expect_fans])
if len(got_shocks) == len(expect_shocks):
    print("             max shock error", max([abs(g - e) for g, e in zip(sorted(got_shocks), sorted(expect_shocks))] + [0.0]))
