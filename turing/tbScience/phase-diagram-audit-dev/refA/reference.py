#!/usr/bin/env python3
"""Reference A: independent answer key for the binary phase diagram task (PHASE_SPEC.md).

Route (deliberately different from a grid hull + fixed-step temperature scan):
  * isotherm: every common tangent is found exactly as a root of the intercept-difference
    function on slope sub-intervals where it is monotone (split points are the exact roots
    of the polynomial G_P' - G_Q'); candidates are kept when the line is a supporting line
    of every phase (checked through the roots of G_R' = m on the convex branches of R, no grid);
  * temperature: congruent, critical, compound-congruent and pure-end events are exact roots
    of polynomials/linear equations in (x, T); three-phase events are located by continuing
    the stable tie-lines in T (Newton predictor-corrector) and bracketing smooth indicator
    functions (phase or compound touching a tie-line, single-phase region length, slope
    difference at a compound vertex) with brentq, then polishing the full event system.
Only numpy and scipy are used.
"""
import argparse
import json
import math
import sys

import numpy as np
from numpy.polynomial import polynomial as P
from scipy.optimize import brentq

R_GAS = 8.314462618
UCAP = 40.0          # |logit x| cap: x in [4e-18, 1 - 4e-18]
STAB_TOL = 1e-6      # J/mol tolerance for "line lies below every phase"
XTIE_MIN = 1e-9      # minimal tie-line length treated as a real tie-line

# polynomial building blocks in x (coefficients low -> high)
PX = np.array([0.0, 1.0])
PS = np.array([1.0, -2.0])          # s = 1 - 2x = y - x
PQ = np.array([0.0, 1.0, -1.0])     # q = x(1 - x)


def sig(u):
    if isinstance(u, (float, int)):
        return 1.0 / (1.0 + math.exp(-u))
    u = np.asarray(u, dtype=float)
    return 1.0 / (1.0 + np.exp(-u))


def xy_from_u(u):
    if isinstance(u, (float, int)):
        return 1.0 / (1.0 + math.exp(-u)), 1.0 / (1.0 + math.exp(u))
    u = np.asarray(u, dtype=float)
    x = 1.0 / (1.0 + np.exp(-u))
    y = 1.0 / (1.0 + np.exp(u))
    return x, y


def logit(x):
    x = float(x)
    return math.log(x) - math.log1p(-x)


def real_roots_in_unit(coef, lo=0.0, hi=1.0, imag_tol=1e-7, grid=4001):
    """Real roots of a polynomial (low->high coefficients) strictly inside (lo, hi)."""
    c = np.array(coef, dtype=float)
    while c.size > 1 and abs(c[-1]) <= 1e-300 * max(1.0, np.max(np.abs(c))):
        c = c[:-1]
    if c.size <= 1:
        return []
    scale = np.max(np.abs(c))
    c = c / scale
    try:
        rts = P.polyroots(c)
    except Exception:
        return []
    out = []
    for r in rts:
        if abs(r.imag) <= imag_tol * max(1.0, abs(r.real)):
            xr = float(r.real)
            if lo < xr < hi:
                out.append(xr)
    # safety net: sign changes on a fine grid (catches roots that the eigen solver blurred)
    if grid < 3:
        out.sort()
        return out
    xs = np.linspace(lo, hi, grid)[1:-1]
    v = P.polyval(xs, c)
    sgn = np.sign(v)
    idx = np.nonzero(sgn[:-1] * sgn[1:] < 0)[0]
    for i in idx:
        a, b = xs[i], xs[i + 1]
        if any(a - 1e-12 <= r <= b + 1e-12 for r in out):
            continue
        try:
            out.append(float(brentq(lambda t: P.polyval(t, c), a, b, xtol=1e-15, rtol=1e-15, maxiter=200)))
        except Exception:
            pass
    out.sort()
    ded = []
    for r in out:
        if not ded or r - ded[-1] > 1e-11:
            ded.append(r)
    return ded


class Solution:
    """Solution phase: G = y GA + x GB + RT (x ln x + y ln y) + x y sum_k L_k (y - x)^k."""

    def __init__(self, d):
        self.name = d["name"]
        em = d["end_members"]
        self.hA, self.sA = float(em["A"]["h"]), float(em["A"]["s"])
        self.hB, self.sB = float(em["B"]["h"]), float(em["B"]["s"])
        rk = d["redlich_kister"]
        self.a = np.array([float(rk[k]["a"]) for k in range(3)])
        self.b = np.array([float(rk[k]["b"]) for k in range(3)])
        self.is_liquid = (self.name == "liquid")
        self.kind = "sol"
        # polynomial excess parts in x: Ea (J/mol) and Eb (J/mol/K); E(T) = Ea + T Eb
        self.Ea = self._excess_poly(self.a)
        self.Eb = self._excess_poly(self.b)
        # cached pieces: spinodal polynomial q E'' + RT = qa + T qb, slope polynomial sa + T sb
        self.qa = P.polymul(PQ, P.polyder(self.Ea, 2))
        self.qb = P.polyadd(P.polymul(PQ, P.polyder(self.Eb, 2)), np.array([R_GAS]))
        self.sa = P.polyadd(np.array([self.hB - self.hA]), P.polyder(self.Ea))
        self.sb = P.polyadd(np.array([-(self.sB - self.sA)]), P.polyder(self.Eb))
        self.af = tuple(float(v) for v in self.a)
        self.bf = tuple(float(v) for v in self.b)

    @staticmethod
    def _excess_poly(coef):
        acc = np.array([coef[0]])
        acc = P.polyadd(acc, P.polymul(np.array([coef[1]]), PS))
        acc = P.polyadd(acc, P.polymul(np.array([coef[2]]), P.polymul(PS, PS)))
        return P.polymul(PQ, acc)

    def GA(self, T):
        return self.hA - self.sA * T

    def GB(self, T):
        return self.hB - self.sB * T

    def Lk(self, T):
        return self.a + self.b * T

    def evalu(self, u, T):
        """G, G1, G2, G3 (value and first three x-derivatives) at logit composition u."""
        if isinstance(u, (float, int)):
            if u > 300.0:
                u = 300.0
            elif u < -300.0:
                u = -300.0
            x = 1.0 / (1.0 + math.exp(-u))
            y = 1.0 / (1.0 + math.exp(u))
            s = y - x
            p = x * y
            af, bf = self.af, self.bf
            L0 = af[0] + bf[0] * T
            L1 = af[1] + bf[1] * T
            L2 = af[2] + bf[2] * T
            S = L0 + L1 * s + L2 * s * s
            S1 = L1 + 2.0 * L2 * s
            S2 = 2.0 * L2
            GA = self.hA - self.sA * T
            GB = self.hB - self.sB * T
            lnx = -math.log1p(math.exp(-u))
            lny = -math.log1p(math.exp(u))
            RT = R_GAS * T
            G = y * GA + x * GB + RT * (x * lnx + y * lny) + p * S
            G1 = (GB - GA) + RT * u + s * S - 2.0 * p * S1
            G2 = RT / p + (-2.0 * S - 4.0 * s * S1 + 4.0 * p * S2)
            G3 = RT * (1.0 / (y * y) - 1.0 / (x * x)) + 12.0 * S1 + 12.0 * s * S2
            return G, G1, G2, G3
        u = np.clip(np.asarray(u, dtype=float), -300.0, 300.0)
        x = 1.0 / (1.0 + np.exp(-u))
        y = 1.0 / (1.0 + np.exp(u))
        s = y - x
        p = x * y
        L0, L1, L2 = self.Lk(T)
        S = L0 + L1 * s + L2 * s * s
        S1 = L1 + 2.0 * L2 * s
        S2 = 2.0 * L2
        GA = self.GA(T)
        GB = self.GB(T)
        lnx = -np.log1p(np.exp(-u))
        lny = -np.log1p(np.exp(u))
        RT = R_GAS * T
        G = y * GA + x * GB + RT * (x * lnx + y * lny) + p * S
        G1 = (GB - GA) + RT * u + s * S - 2.0 * p * S1
        G2 = RT / p + (-2.0 * S - 4.0 * s * S1 + 4.0 * p * S2)
        G3 = RT * (1.0 / (y * y) - 1.0 / (x * x)) + 12.0 * S1 + 12.0 * s * S2
        return G, G1, G2, G3

    def dT(self, u, T):
        """Partial derivatives in T of G, G1, G2, G3 (all linear in T); scalar u."""
        u = min(300.0, max(-300.0, float(u)))
        x = 1.0 / (1.0 + math.exp(-u))
        y = 1.0 / (1.0 + math.exp(u))
        s = y - x
        p = x * y
        b0, b1, b2 = self.bf
        Sb = b0 + b1 * s + b2 * s * s
        Sb1 = b1 + 2.0 * b2 * s
        Sb2 = 2.0 * b2
        lnx = -math.log1p(math.exp(-u))
        lny = -math.log1p(math.exp(u))
        gT = -(y * self.sA + x * self.sB) + R_GAS * (x * lnx + y * lny) + p * Sb
        g1T = -(self.sB - self.sA) + R_GAS * u + s * Sb - 2.0 * p * Sb1
        g2T = R_GAS / p + (-2.0 * Sb - 4.0 * s * Sb1 + 4.0 * p * Sb2)
        g3T = R_GAS * (1.0 / (y * y) - 1.0 / (x * x)) + 12.0 * Sb1 + 12.0 * s * Sb2
        return gT, g1T, g2T, g3T

    def G_of_x(self, x, T):
        if x <= 0.0:
            return self.GA(T)
        if x >= 1.0:
            return self.GB(T)
        return float(self.evalu(logit(x), T)[0])

    # ---- polynomial pieces ----
    def lin_poly(self, T):
        return np.array([self.GA(T), self.GB(T) - self.GA(T)])

    def E_poly(self, T):
        return P.polyadd(self.Ea, T * self.Eb)

    def slope_poly(self, T):
        """Polynomial part of G' (G' = this + RT ln(x/y))."""
        return P.polyadd(self.sa, T * self.sb)

    def spinodal(self, T):
        """Roots of G'' = 0 in (0,1): q E'' + RT = 0 (degree 5), polished by Newton."""
        q = P.polyadd(self.qa, T * self.qb)
        roots = real_roots_in_unit(q, 1e-9, 1.0 - 1e-9, grid=0)
        out = []
        for x0 in roots:
            u = logit(x0)
            for _ in range(60):
                _, _, g2, g3 = self.evalu(u, T)
                xx, yy = xy_from_u(u)
                d = g3 * xx * yy
                if d == 0.0:
                    break
                du = -g2 / d
                u += du
                if abs(du) < 1e-15:
                    break
            out.append(float(sig(u)))
        out.sort()
        # G'' > 0 near both ends, so roots come in an even number; keep only sign-changing ones
        ded = []
        for r in out:
            if not ded or r - ded[-1] > 1e-12:
                ded.append(r)
        return ded

    def branches(self, T):
        """Convex branches of the curve as (ulo, uhi, mlo, mhi) in logit; built from the sign
        of G'' between consecutive spinodal roots (robust to double roots) and merged."""
        sp = self.spinodal(T)
        pts = [0.0] + sp + [1.0]
        keep = []
        for i in range(len(pts) - 1):
            lo, hi = pts[i], pts[i + 1]
            if hi - lo <= 1e-13:
                continue
            xm = 0.5 * (lo + hi)
            g2 = float(self.evalu(logit(xm), T)[2])
            if g2 > 0.0:
                if keep and abs(keep[-1][1] - lo) <= 1e-13:
                    keep[-1] = (keep[-1][0], hi)
                else:
                    keep.append((lo, hi))
        br = []
        for lo, hi in keep:
            ulo = -UCAP if lo <= 0.0 else max(-UCAP, logit(lo))
            uhi = UCAP if hi >= 1.0 else min(UCAP, logit(hi))
            if uhi <= ulo:
                continue
            mlo = float(self.evalu(ulo, T)[1])
            mhi = float(self.evalu(uhi, T)[1])
            br.append((ulo, uhi, mlo, mhi))
        return br

    def inv_slope(self, m, br, T):
        """Solve G'(u) = m on convex branch br = (ulo, uhi, mlo, mhi); None if m is outside."""
        ulo, uhi, mlo, mhi = br
        if m < mlo or m > mhi:
            return None
        if m == mlo:
            return ulo
        if m == mhi:
            return uhi
        a, b = ulo, uhi
        u = 0.5 * (a + b)
        for _ in range(200):
            _, g1, g2, _ = self.evalu(u, T)
            f = float(g1) - m
            if f == 0.0:
                return u
            if f < 0.0:
                a = u
            else:
                b = u
            x, y = xy_from_u(u)
            d = float(g2) * x * y
            un = u - f / d if d > 0.0 else None
            if un is None or not (a < un < b):
                un = 0.5 * (a + b)
            if abs(un - u) <= 1e-15 * max(1.0, abs(u)) or b - a <= 1e-15 * max(1.0, abs(u)):
                return un
            u = un
        return u

    def branch_index(self, x, T, brs=None):
        if brs is None:
            brs = self.branches(T)
        u = logit(min(max(x, 1e-300), 1.0 - 1e-16))
        for i, (ulo, uhi, _, _) in enumerate(brs):
            if ulo - 1e-9 <= u <= uhi + 1e-9:
                return i
        return None


class Compound:
    def __init__(self, d):
        self.name = d["name"]
        self.x = float(d["x_b"])
        self.h = float(d["h"])
        self.s = float(d["s"])
        self.kind = "cmp"
        self.is_liquid = False

    def G(self, T):
        return self.h - self.s * T


class System:
    def __init__(self, d):
        self.system_id = d["system_id"]
        self.phases = [Solution(p) for p in d["solution_phases"]]
        self.compounds = [Compound(c) for c in d["compounds"]]
        self.T_lo, self.T_hi = float(d["window_K"][0]), float(d["window_K"][1])
        self.isotherms = [float(t) for t in d["isotherms_K"]]
        self.isotherms_raw = list(d["isotherms_K"])
        self.by_name = {p.name: p for p in self.phases}
        self.by_name.update({c.name: c for c in self.compounds})
        self.raw = d


# =====================================================================================
# Isotherm: exact common tangents and lower hull
# =====================================================================================
class End:
    """One end of a tie-line: a solution state (phase, u) or a compound."""
    __slots__ = ("ph", "u", "x")

    def __init__(self, ph, u=None):
        self.ph = ph
        if ph.kind == "cmp":
            self.u = None
            self.x = ph.x
        else:
            self.u = float(u)
            self.x = float(sig(self.u))

    def is_cmp(self):
        return self.ph.kind == "cmp"


class Tie:
    __slots__ = ("l", "r", "m", "c")

    def __init__(self, l, r, m, c):
        self.l, self.r, self.m, self.c = l, r, m, c

    def line(self, x):
        return self.m * x + self.c

    def names(self):
        return (self.l.ph.name, self.r.ph.name)


def line_through(ph1, u1, ph2, u2, T):
    """Slope/intercept through two solution states (chemical-potential form)."""
    G1, g1, _, _ = ph1.evalu(u1, T)
    G2, g2, _, _ = ph2.evalu(u2, T)
    x1, x2 = float(sig(u1)), float(sig(u2))
    m = 0.5 * (float(g1) + float(g2))
    c = 0.5 * ((float(G1) - m * x1) + (float(G2) - m * x2))
    return m, c


def polish_sol_sol(ph1, u1, ph2, u2, T, iters=60):
    """Newton on {G1'(u1) = G2'(u2), G1 - G2 - G1' (x1 - x2) = 0} in (u1, u2)."""
    best = None
    for _ in range(iters):
        G1, g1, h1, _ = ph1.evalu(u1, T)
        G2, g2, h2, _ = ph2.evalu(u2, T)
        x1, y1 = xy_from_u(u1)
        x2, y2 = xy_from_u(u2)
        f1 = float(g1 - g2)
        f2 = float(G1 - G2 - g1 * (x1 - x2))
        res = abs(f1) + abs(f2)
        if best is None or res < best[0]:
            best = (res, u1, u2)
        J = np.array([[float(h1 * x1 * y1), float(-h2 * x2 * y2)],
                      [float(-h1 * (x1 - x2) * x1 * y1), float((g1 - g2) * x2 * y2)]])
        try:
            d = np.linalg.solve(J, -np.array([f1, f2]))
        except np.linalg.LinAlgError:
            break
        if not np.all(np.isfinite(d)):
            break
        step = max(abs(d[0]), abs(d[1]))
        if step > 2.0:
            d *= 2.0 / step
        u1 = float(u1 + d[0])
        u2 = float(u2 + d[1])
        if step < 1e-14:
            G1, g1, _, _ = ph1.evalu(u1, T)
            G2, g2, _, _ = ph2.evalu(u2, T)
            x1, _ = xy_from_u(u1)
            x2, _ = xy_from_u(u2)
            res = abs(float(g1 - g2)) + abs(float(G1 - G2 - g1 * (x1 - x2)))
            if res < best[0]:
                best = (res, u1, u2)
            break
    return best[1], best[2], best[0]


def polish_sol_cmp(ph, u, cmp_, T, iters=60):
    """Newton on G(u) - G'(u)(x - x_theta) - G_theta = 0 in u."""
    Gt = cmp_.G(T)
    for _ in range(iters):
        G, g1, g2, _ = ph.evalu(u, T)
        x, y = xy_from_u(u)
        f = float(G - g1 * (x - cmp_.x) - Gt)
        d = float(-g2 * (x - cmp_.x) * x * y)
        if d == 0.0:
            break
        du = -f / d
        if abs(du) > 2.0:
            du = math.copysign(2.0, du)
        u += du
        if abs(du) < 1e-15:
            break
    G, g1, _, _ = ph.evalu(u, T)
    x, _ = xy_from_u(u)
    return u, abs(float(G - g1 * (x - cmp_.x) - Gt))


def tangents_sol_sol(ph1, br1, ph2, br2, T):
    """All common tangents between convex branch br1 of ph1 and br2 of ph2 (exact)."""
    mlo = max(br1[2], br2[2])
    mhi = min(br1[3], br2[3])
    if mhi <= mlo:
        return []
    splits = []
    if ph1 is not ph2:
        dpoly = P.polysub(ph1.slope_poly(T), ph2.slope_poly(T))   # G1' - G2' (ln terms cancel)
        for xr in real_roots_in_unit(dpoly, 1e-12, 1.0 - 1e-12, grid=0):
            ms = float(ph1.evalu(logit(xr), T)[1])
            if mlo < ms < mhi:
                splits.append(ms)
    grid = sorted(set([mlo, mhi] + splits))

    def f(m):
        u1 = ph1.inv_slope(m, br1, T)
        u2 = ph2.inv_slope(m, br2, T)
        G1 = float(ph1.evalu(u1, T)[0])
        G2 = float(ph2.evalu(u2, T)[0])
        return (G1 - m * float(sig(u1))) - (G2 - m * float(sig(u2)))

    out = []
    vals = [f(m) for m in grid]
    for i in range(len(grid) - 1):
        fa, fb = vals[i], vals[i + 1]
        if fa == 0.0 and i == 0:
            m0 = grid[i]
        elif fa * fb < 0.0:
            try:
                m0 = brentq(f, grid[i], grid[i + 1], xtol=1e-13, rtol=1e-15, maxiter=300)
            except Exception:
                continue
        else:
            continue
        u1 = ph1.inv_slope(m0, br1, T)
        u2 = ph2.inv_slope(m0, br2, T)
        u1, u2, res = polish_sol_sol(ph1, u1, ph2, u2, T)
        x1, x2 = float(sig(u1)), float(sig(u2))
        if abs(x1 - x2) < XTIE_MIN:
            continue
        m, c = line_through(ph1, u1, ph2, u2, T)
        if x1 < x2:
            out.append(Tie(End(ph1, u1), End(ph2, u2), m, c))
        else:
            out.append(Tie(End(ph2, u2), End(ph1, u1), m, c))
    return out


def tangents_sol_cmp(ph, br, cmp_, T):
    """Tangent lines from the compound point to the convex branch br (exact)."""
    ulo, uhi, _, _ = br
    ut = logit(cmp_.x)
    Gt = cmp_.G(T)

    def g(u):
        G, g1, _, _ = ph.evalu(u, T)
        return float(G - g1 * (float(sig(u)) - cmp_.x) - Gt)

    ivs = []
    if ulo < ut - 1e-12:
        ivs.append((ulo, min(uhi, ut - 1e-12)))
    if uhi > ut + 1e-12:
        ivs.append((max(ulo, ut + 1e-12), uhi))
    out = []
    for a, b in ivs:
        if b <= a:
            continue
        ga, gb = g(a), g(b)
        if ga * gb > 0.0:
            continue
        try:
            u0 = brentq(g, a, b, xtol=1e-14, rtol=1e-15, maxiter=300)
        except Exception:
            continue
        u0, res = polish_sol_cmp(ph, u0, cmp_, T)
        x0 = float(sig(u0))
        if abs(x0 - cmp_.x) < XTIE_MIN:
            continue
        G, g1, _, _ = ph.evalu(u0, T)
        m = float(g1)
        c = 0.5 * ((float(G) - m * x0) + (Gt - m * cmp_.x))
        if x0 < cmp_.x:
            out.append(Tie(End(ph, u0), End(cmp_), m, c))
        else:
            out.append(Tie(End(cmp_), End(ph, u0), m, c))
    return out


def min_above_line(ph, brs, m, c, T, skip_branch=None):
    """min over x of G_ph(x) - (m x + c): evaluated at the roots of G' = m on convex
    branches (local minima) and at the pure ends. Returns (value, x_at_min)."""
    best = (ph.GA(T) - c, 0.0)
    v = ph.GB(T) - m - c
    if v < best[0]:
        best = (v, 1.0)
    for i, br in enumerate(brs):
        if skip_branch is not None and i == skip_branch:
            continue
        u = ph.inv_slope(m, br, T)
        if u is None:
            continue
        x = float(sig(u))
        v = float(ph.evalu(u, T)[0]) - m * x - c
        if v < best[0]:
            best = (v, x)
    return best


class Hull:
    """Lower hull at one temperature: stable tie-lines (sorted) and single-phase regions."""

    def __init__(self, sysm, T, ties, branches):
        self.sys = sysm
        self.T = T
        self.ties = ties
        self.branches = branches
        self.regions = []     # (phase, x_lo, x_hi)
        self.ok = True
        self.msgs = []
        self._assemble()

    def _end_phase(self, side):
        T = self.T
        if side == 0:
            vals = [(p.GA(T), p.name) for p in self.sys.phases]
        else:
            vals = [(p.GB(T), p.name) for p in self.sys.phases]
        vals.sort()
        return self.sys.by_name[vals[0][1]]

    def _assemble(self):
        ties = sorted(self.ties, key=lambda t: (t.l.x, t.r.x))
        self.ties = ties
        regs = []
        pA = self._end_phase(0)
        pB = self._end_phase(1)
        if not ties:
            if pA is not pB and abs(pA.GA(self.T) - pB.GA(self.T)) > 1e-6 and abs(pA.GB(self.T) - pB.GB(self.T)) > 1e-6:
                self.ok = False
                self.msgs.append("no tie-line but different end phases")
            regs.append((pA, 0.0, 1.0))
            self.regions = regs
            return
        first = ties[0]
        if first.l.is_cmp():
            self.ok = False
            self.msgs.append("first tie-line starts at a compound")
        if first.l.ph is not pA and abs(first.l.ph.GA(self.T) - pA.GA(self.T)) > 1e-6:
            self.ok = False
            self.msgs.append("left end phase mismatch %s vs %s" % (first.l.ph.name, pA.name))
        regs.append((first.l.ph, 0.0, first.l.x))
        for i in range(len(ties) - 1):
            a, b = ties[i], ties[i + 1]
            if a.r.is_cmp() and b.l.is_cmp() and a.r.ph is b.l.ph:
                continue          # shared compound vertex
            if a.r.ph is not b.l.ph or a.r.is_cmp() or b.l.is_cmp():
                self.ok = False
                self.msgs.append("inconsistent neighbours %s-%s | %s-%s" %
                                 (a.l.ph.name, a.r.ph.name, b.l.ph.name, b.r.ph.name))
                continue
            if b.l.x < a.r.x - 1e-9:
                self.ok = False
                self.msgs.append("overlapping tie-lines at x=%.6g" % a.r.x)
            regs.append((a.r.ph, a.r.x, b.l.x))
        last = ties[-1]
        if last.r.is_cmp() or (last.r.ph is not pB and abs(last.r.ph.GB(self.T) - pB.GB(self.T)) > 1e-6):
            self.ok = False
            self.msgs.append("right end phase mismatch")
        regs.append((last.r.ph, last.r.x, 1.0))
        self.regions = regs

    def value(self, x):
        """Hull value at x: min over curves, compound points and stable segments."""
        T = self.T
        best = math.inf
        for p in self.sys.phases:
            best = min(best, p.G_of_x(x, T))
        for cm in self.sys.compounds:
            if cm.x == x:
                best = min(best, cm.G(T))
        for t in self.ties:
            if t.l.x - 1e-15 <= x <= t.r.x + 1e-15:
                best = min(best, t.line(x))
        return best

    def piece_at(self, x):
        """('tie', Tie) or ('reg', (phase, lo, hi)) or ('cmp', compound) containing x."""
        for t in self.ties:
            if t.l.is_cmp() and abs(x - t.l.x) < 1e-13:
                return ("cmp", t.l.ph)
            if t.r.is_cmp() and abs(x - t.r.x) < 1e-13:
                return ("cmp", t.r.ph)
        for t in self.ties:
            if t.l.x < x < t.r.x:
                return ("tie", t)
        for rg in self.regions:
            if rg[1] <= x <= rg[2]:
                return ("reg", rg)
        return (None, None)

    def topology(self):
        """Hashable description of the piece sequence (names only)."""
        out = []
        for rg in self.regions:
            out.append(("R", rg[0].name))
        for t in self.ties:
            out.append(("T", t.l.ph.name, t.r.ph.name))
        return tuple(sorted(out))


def hull_at(sysm, T):
    """Exact lower hull at temperature T."""
    brs = {p.name: p.branches(T) for p in sysm.phases}
    cands = []
    plist = sysm.phases
    for i, p1 in enumerate(plist):
        for j in range(i, len(plist)):
            p2 = plist[j]
            b1s, b2s = brs[p1.name], brs[p2.name]
            for ia, br1 in enumerate(b1s):
                for ib, br2 in enumerate(b2s):
                    if p1 is p2 and ib <= ia:
                        continue
                    cands.extend(tangents_sol_sol(p1, br1, p2, br2, T))
    for p in plist:
        for br in brs[p.name]:
            for cm in sysm.compounds:
                cands.extend(tangents_sol_cmp(p, br, cm, T))
    cms = sorted(sysm.compounds, key=lambda c: c.x)
    for i in range(len(cms)):
        for j in range(i + 1, len(cms)):
            c1, c2 = cms[i], cms[j]
            m = (c2.G(T) - c1.G(T)) / (c2.x - c1.x)
            c = c1.G(T) - m * c1.x
            cands.append(Tie(End(c1), End(c2), m, c))
    stable = []
    for t in cands:
        ok = True
        for p in plist:
            v, _ = min_above_line(p, brs[p.name], t.m, t.c, T)
            if v < -STAB_TOL:
                ok = False
                break
        if ok:
            for cm in sysm.compounds:
                if cm.G(T) - t.line(cm.x) < -STAB_TOL:
                    ok = False
                    break
        if ok:
            stable.append(t)
    return Hull(sysm, T, stable, brs)


# =====================================================================================
# Exact (polynomial / linear) event candidates in (x, T)
# =====================================================================================
def newton_2d(fun, z0, iters=80):
    """Generic damped Newton for fun(z) -> (F, J) with 2 unknowns; returns (z, residual)."""
    z = np.array(z0, dtype=float)
    best = None
    for _ in range(iters):
        F, J = fun(z)
        res = float(np.max(np.abs(F)))
        if best is None or res < best[0]:
            best = (res, z.copy())
        try:
            d = np.linalg.solve(J, -F)
        except np.linalg.LinAlgError:
            break
        if not np.all(np.isfinite(d)):
            break
        if abs(d[0]) > 1.0:
            d *= 1.0 / abs(d[0])
        if abs(d[1]) > 50.0:
            d *= 50.0 / abs(d[1])
        z = z + d
        if abs(d[0]) < 1e-15 and abs(d[1]) < 1e-12 * max(1.0, abs(z[1])):
            F, J = fun(z)
            res = float(np.max(np.abs(F)))
            if res < best[0]:
                best = (res, z.copy())
            break
    return best[1], best[0]


def critical_candidates(sysm):
    """(x, T, phase) with G'' = G''' = 0: exact polynomial reduction, Newton polish."""
    out = []
    for p in sysm.phases:
        A2 = P.polyder(p.Ea, 2)
        B2 = P.polyder(p.Eb, 2)
        A3 = P.polyder(p.Ea, 3)
        B3 = P.polyder(p.Eb, 3)
        q2 = P.polymul(PQ, PQ)
        lhs = P.polymul(A2, P.polyadd(P.polymul(np.array([-R_GAS]), PS), P.polymul(q2, B3)))
        rhs = P.polymul(P.polymul(A3, PQ), P.polyadd(np.array([R_GAS]), P.polymul(PQ, B2)))
        W = P.polysub(lhs, rhs)
        for xr in real_roots_in_unit(W, 1e-6, 1.0 - 1e-6):
            q = xr * (1.0 - xr)
            den = R_GAS + q * P.polyval(xr, B2)
            if abs(den) < 1e-12:
                continue
            T0 = -P.polyval(xr, A2) * q / den
            if not (sysm.T_lo - 5.0 < T0 < sysm.T_hi + 5.0):
                continue

            def fun(z, p=p):
                u, T = float(z[0]), float(z[1])
                _, _, g2, g3 = p.evalu(u, T)
                _, _, g2T, g3T = p.dT(u, T)
                x, y = xy_from_u(u)
                L2 = p.Lk(T)[2]
                g4 = R_GAS * T * (2.0 / x ** 3 + 2.0 / y ** 3) - 96.0 * L2
                J = np.array([[float(g3 * x * y), float(g2T)],
                              [float(g4 * x * y), float(g3T)]])
                return np.array([float(g2), float(g3)]), J

            z, res = newton_2d(fun, [logit(xr), T0])
            u, T = z
            scale = R_GAS * T
            if res > 1e-6 * scale:
                continue
            if sysm.T_lo < T < sysm.T_hi:
                out.append({"kind": "critical", "T": float(T), "x": float(sig(u)), "phase": p})
    return out


def congruent_candidates(sysm):
    """Tangency of two solution curves: dG = U + T V polynomial, U V' - U' V = 0."""
    out = []
    ph = sysm.phases
    for i in range(len(ph)):
        for j in range(i + 1, len(ph)):
            p1, p2 = ph[i], ph[j]
            U = P.polyadd(np.array([p1.hA - p2.hA, (p1.hB - p2.hB) - (p1.hA - p2.hA)]), P.polysub(p1.Ea, p2.Ea))
            V = P.polyadd(np.array([-(p1.sA - p2.sA), -((p1.sB - p2.sB) - (p1.sA - p2.sA))]), P.polysub(p1.Eb, p2.Eb))
            W = P.polysub(P.polymul(U, P.polyder(V)), P.polymul(P.polyder(U), V))
            for xr in real_roots_in_unit(W, 1e-6, 1.0 - 1e-6):
                v = P.polyval(xr, V)
                if abs(v) < 1e-14:
                    continue
                T0 = -P.polyval(xr, U) / v
                if not (sysm.T_lo - 5.0 < T0 < sysm.T_hi + 5.0):
                    continue

                def fun(z, p1=p1, p2=p2):
                    u, T = float(z[0]), float(z[1])
                    G1, g1, h1, _ = p1.evalu(u, T)
                    G2, g2, h2, _ = p2.evalu(u, T)
                    G1T, g1T, _, _ = p1.dT(u, T)
                    G2T, g2T, _, _ = p2.dT(u, T)
                    x, y = xy_from_u(u)
                    F = np.array([float(G1 - G2), float(g1 - g2)])
                    J = np.array([[float((g1 - g2) * x * y), float(G1T - G2T)],
                                  [float((h1 - h2) * x * y), float(g1T - g2T)]])
                    return F, J

                z, res = newton_2d(fun, [logit(xr), T0])
                u, T = z
                if res > 1e-7 * max(1.0, abs(T)):
                    continue
                if sysm.T_lo < T < sysm.T_hi:
                    out.append({"kind": "congruent", "T": float(T), "x": float(sig(u)), "P": p1, "Q": p2})
    return out


def compound_congruent_candidates(sysm):
    out = []
    for p in sysm.phases:
        for cm in sysm.compounds:
            u = logit(cm.x)
            G0 = float(p.evalu(u, 0.0)[0])
            G1 = float(p.evalu(u, 1.0)[0]) - G0     # dG/dT (G linear in T)
            den = G1 + cm.s
            if abs(den) < 1e-14:
                continue
            T = (cm.h - G0) / den
            if sysm.T_lo < T < sysm.T_hi:
                out.append({"kind": "cmp_congruent", "T": float(T), "x": cm.x, "P": p, "cmp": cm})
    return out


def pure_end_candidates(sysm):
    out = []
    ph = sysm.phases
    for i in range(len(ph)):
        for j in range(i + 1, len(ph)):
            p1, p2 = ph[i], ph[j]
            for side, (h1, s1, h2, s2) in enumerate([(p1.hA, p1.sA, p2.hA, p2.sA), (p1.hB, p1.sB, p2.hB, p2.sB)]):
                if s1 == s2:
                    continue
                T = (h1 - h2) / (s1 - s2)
                if sysm.T_lo < T < sysm.T_hi:
                    out.append({"kind": "pure_end", "T": float(T), "side": side, "P": p1, "Q": p2})
    return out


# =====================================================================================
# Continuation of tie-lines in T and smooth indicators
# =====================================================================================
def continue_ties(ties, T0, T1, depth=0):
    """Continue each tie-line (same end phases) from T0 to T1 by Newton; sub-steps on trouble."""
    out = []
    for t in ties:
        if t.l.is_cmp() and t.r.is_cmp():
            c1, c2 = t.l.ph, t.r.ph
            m = (c2.G(T1) - c1.G(T1)) / (c2.x - c1.x)
            out.append(Tie(End(c1), End(c2), m, c1.G(T1) - m * c1.x))
            continue
        if t.l.is_cmp() or t.r.is_cmp():
            if t.l.is_cmp():
                cm, se = t.l.ph, t.r
            else:
                cm, se = t.r.ph, t.l
            u, res = polish_sol_cmp(se.ph, se.u, cm, T1)
            x = float(sig(u))
            good = res < 1e-6 * max(1.0, R_GAS * T1) and ((x > cm.x) == (se.x > cm.x))
            if not good:
                break
            G, g1, _, _ = se.ph.evalu(u, T1)
            m = float(g1)
            c = 0.5 * ((float(G) - m * x) + (cm.G(T1) - m * cm.x))
            if t.l.is_cmp():
                out.append(Tie(End(cm), End(se.ph, u), m, c))
            else:
                out.append(Tie(End(se.ph, u), End(cm), m, c))
            continue
        u1, u2, res = polish_sol_sol(t.l.ph, t.l.u, t.r.ph, t.r.u, T1)
        if res > 1e-6 * max(1.0, R_GAS * T1) or not (sig(u1) < sig(u2)):
            break
        m, c = line_through(t.l.ph, u1, t.r.ph, u2, T1)
        out.append(Tie(End(t.l.ph, u1), End(t.r.ph, u2), m, c))
    else:
        return out
    if depth >= 14:
        return None
    Tm = 0.5 * (T0 + T1)
    mid = continue_ties(ties, T0, Tm, depth + 1)
    if mid is None:
        return None
    return continue_ties(mid, Tm, T1, depth + 1)


class Pseudo:
    """Hull-like structure built from continued tie-lines at temperature T (fixed topology)."""

    def __init__(self, sysm, T, ties, left_phase, right_phase):
        self.sys = sysm
        self.T = T
        self.ties = ties
        self.brs = {p.name: p.branches(T) for p in sysm.phases}
        self.regions = []
        if not ties:
            self.regions.append((left_phase, 0.0, 1.0))
        else:
            self.regions.append((ties[0].l.ph, 0.0, ties[0].l.x))
            for i in range(len(ties) - 1):
                a, b = ties[i], ties[i + 1]
                if a.r.is_cmp() and b.l.is_cmp():
                    continue
                self.regions.append((a.r.ph, a.r.x, b.l.x))
            self.regions.append((ties[-1].r.ph, ties[-1].r.x, 1.0))

    def value(self, x):
        for t in self.ties:
            if t.l.x <= x <= t.r.x:
                return t.line(x)
        for rg in self.regions:
            if rg[1] <= x <= rg[2]:
                return rg[0].G_of_x(x, self.T)
        # outside every piece (regions crossed): take the lowest of the neighbouring curves
        return min(p.G_of_x(x, self.T) for p in self.sys.phases)


def touch_indicator(ps, t, R):
    """min over x in [x_left, x_right] of G_R(x) - line(x), excluding R's own end state(s)."""
    T = ps.T
    brs = ps.brs[R.name]
    skip = set()
    if not t.l.is_cmp() and t.l.ph is R:
        bi = R.branch_index(t.l.x, T, brs)
        if bi is not None:
            skip.add(bi)
    if not t.r.is_cmp() and t.r.ph is R:
        bi = R.branch_index(t.r.x, T, brs)
        if bi is not None:
            skip.add(bi)
    best = 1e300
    xb = None
    if t.l.is_cmp() or t.l.ph is not R:
        v = R.G_of_x(t.l.x, T) - t.line(t.l.x)
        if v < best:
            best, xb = v, t.l.x
    if t.r.is_cmp() or t.r.ph is not R:
        v = R.G_of_x(t.r.x, T) - t.line(t.r.x)
        if v < best:
            best, xb = v, t.r.x
    for i, br in enumerate(brs):
        if i in skip:
            continue
        u = R.inv_slope(t.m, br, T)
        if u is None:
            continue
        x = float(sig(u))
        if not (t.l.x + 1e-12 < x < t.r.x - 1e-12):
            continue
        v = float(R.evalu(u, T)[0]) - t.line(x)
        if v < best:
            best, xb = v, x
    return best, xb


def indicators(ps):
    """List of (key, value, payload) smooth indicators; an event is a zero crossing from +."""
    out = []
    sysm = ps.sys
    for i, t in enumerate(ps.ties):
        for R in sysm.phases:
            v, xb = touch_indicator(ps, t, R)
            out.append((("touch", i, R.name), v, xb))
    for cm in sysm.compounds:
        on_hull = any((t.l.is_cmp() and t.l.ph is cm) or (t.r.is_cmp() and t.r.ph is cm) for t in ps.ties)
        if on_hull:
            out.append((("cmp", cm.name), 1e300, None))
        else:
            out.append((("cmp", cm.name), cm.G(ps.T) - ps.value(cm.x), cm.x))
    for i in range(len(ps.ties) - 1):
        a, b = ps.ties[i], ps.ties[i + 1]
        if a.r.is_cmp() and b.l.is_cmp():
            out.append((("vertex", i), b.m - a.m, None))
        else:
            out.append((("region", i), b.l.x - a.r.x, None))
    return out


# =====================================================================================
# Three-phase polishing: one line through three states at one temperature
# =====================================================================================
def polish_invariant(states, T0, iters=80):
    """states: list of (phase, x0) with x increasing. Unknowns: T, m, c and u for each
    solution state. Equations: G_P'(u) = m, G_P(u) = m x + c; G_theta(T) = m x_theta + c.
    Returns (T, [x1, x2, x3], residual)."""
    sol_idx = [i for i, (p, _) in enumerate(states) if p.kind == "sol"]
    n = 3 + len(sol_idx)
    z = np.zeros(n)
    z[0] = T0
    # initial m, c from the two outermost states
    x0, x2 = states[0][1], states[2][1]
    G0 = states[0][0].G_of_x(x0, T0) if states[0][0].kind == "sol" else states[0][0].G(T0)
    G2 = states[2][0].G_of_x(x2, T0) if states[2][0].kind == "sol" else states[2][0].G(T0)
    z[1] = (G2 - G0) / (x2 - x0)
    z[2] = G0 - z[1] * x0
    for k, i in enumerate(sol_idx):
        z[3 + k] = logit(states[i][1])
    best = None
    for _ in range(iters):
        T, m, c = float(z[0]), float(z[1]), float(z[2])
        F = []
        J = []
        k = 0
        for i, (p, _) in enumerate(states):
            if p.kind == "sol":
                u = float(z[3 + k])
                G, g1, g2, _ = p.evalu(u, T)
                GT, g1T, _, _ = p.dT(u, T)
                x, y = xy_from_u(u)
                F.append(float(g1) - m)
                row = np.zeros(n)
                row[0] = float(g1T)
                row[1] = -1.0
                row[3 + k] = float(g2 * x * y)
                J.append(row)
                F.append(float(G) - m * float(x) - c)
                row = np.zeros(n)
                row[0] = float(GT)
                row[1] = -float(x)
                row[2] = -1.0
                row[3 + k] = float((g1 - m) * x * y)
                J.append(row)
                k += 1
            else:
                F.append(p.G(T) - m * p.x - c)
                row = np.zeros(n)
                row[0] = -p.s
                row[1] = -p.x
                row[2] = -1.0
                J.append(row)
        F = np.array(F)
        J = np.array(J)
        res = float(np.max(np.abs(F)))
        if best is None or res < best[0]:
            best = (res, z.copy())
        try:
            d = np.linalg.solve(J, -F)
        except np.linalg.LinAlgError:
            break
        if not np.all(np.isfinite(d)):
            break
        if abs(d[0]) > 2.0:
            d *= 2.0 / abs(d[0])
        for k in range(len(sol_idx)):
            if abs(d[3 + k]) > 0.5:
                d *= 0.5 / abs(d[3 + k])
        z = z + d
        if abs(d[0]) < 1e-11 * max(1.0, abs(z[0])) and all(abs(d[3 + k]) < 1e-14 for k in range(len(sol_idx))):
            # one more residual evaluation at the final point
            T, m, c = float(z[0]), float(z[1]), float(z[2])
            Fr = []
            k = 0
            for p, _ in states:
                if p.kind == "sol":
                    u = float(z[3 + k])
                    G, g1, _, _ = p.evalu(u, T)
                    x, _ = xy_from_u(u)
                    Fr += [float(g1) - m, float(G) - m * float(x) - c]
                    k += 1
                else:
                    Fr.append(p.G(T) - m * p.x - c)
            res = float(np.max(np.abs(Fr)))
            if res < best[0]:
                best = (res, z.copy())
            break
    res, z = best
    xs = []
    k = 0
    for p, _ in states:
        if p.kind == "sol":
            xs.append(float(sig(z[3 + k])))
            k += 1
        else:
            xs.append(p.x)
    return float(z[0]), xs, res


def invariant_name(cls, phases):
    """phases: [P1, P2, P3] objects in increasing x."""
    mid = phases[1]
    outer = [phases[0], phases[2]]
    n_liq_outer = sum(1 for p in outer if p.is_liquid)
    if cls == "eutectic":
        if mid.is_liquid:
            return "eutectic" if n_liq_outer == 0 else "monotectic"
        return "eutectoid" if n_liq_outer == 0 else "metatectic"
    if mid.is_liquid:
        return "inverse_monotectic"
    if n_liq_outer == 1:
        return "peritectic"
    if n_liq_outer == 2:
        return "syntectic"
    return "peritectoid"


# =====================================================================================
# Temperature sweep
# =====================================================================================
class Sweep:
    STEP = 0.25        # K; events of the topology are >= 0.5 K apart
    RESTART = 0.1      # K after an accepted event
    DELTA = 0.1        # K for side checks
    CHECK_EVERY = 20   # steps between from-scratch cross-checks

    def __init__(self, sysm):
        self.sys = sysm
        self.warnings = []
        self.invariants = []
        self.congruent = []
        self.critical = []
        self.sched = (critical_candidates(sysm) + congruent_candidates(sysm)
                      + compound_congruent_candidates(sysm) + pure_end_candidates(sysm))
        self.sched.sort(key=lambda c: c["T"])
        self.used = set()
        self.n_hulls = 0

    def warn(self, msg):
        self.warnings.append(msg)
        print("WARNING: " + msg, file=sys.stderr)

    def hull(self, T, quiet=False):
        self.n_hulls += 1
        H = hull_at(self.sys, T)
        if not H.ok and not quiet:
            self.warn("hull at T=%.9f inconsistent: %s" % (T, "; ".join(H.msgs)))
        return H

    # ---- stability tests of exact candidates ----
    def cand_is_real(self, c):
        """Exact candidate is a real event iff its touching point lies on the hull at T."""
        T = c["T"]
        if c["kind"] == "pure_end":
            # real when one of the two phases is the stable end phase just below T
            Hb = self.hull(T - 1e-3)
            end = Hb._end_phase(c["side"])
            return end is c["P"] or end is c["Q"]
        H = self.hull(T, quiet=True)      # degenerate temperature: assembly warnings are expected
        v = H.value(c["x"])
        if c["kind"] == "critical":
            return v >= c["phase"].G_of_x(c["x"], T) - 1e-6
        if c["kind"] == "congruent":
            return v >= c["P"].G_of_x(c["x"], T) - 1e-6
        if c["kind"] == "cmp_congruent":
            return v >= c["cmp"].G(T) - 1e-6
        return False

    def report_candidate(self, c):
        T, x = c["T"], c["x"]
        d = self.DELTA
        Hb = self.hull(T - d)
        Ha = self.hull(T + d)
        if c["kind"] == "critical":
            P = c["phase"]
            kb, pb = Hb.piece_at(x)
            ka, pa = Ha.piece_at(x)
            gap_below = kb == "tie" and pb.l.ph is P and pb.r.ph is P
            gap_above = ka == "tie" and pa.l.ph is P and pa.r.ph is P
            if gap_below == gap_above:
                self.warn("critical point at T=%.6f: ambiguous gap side (%s/%s)" % (T, gap_below, gap_above))
            side = "below" if gap_below and not gap_above else "above"
            self.critical.append({"temperature_K": T, "x": x, "phase": P.name, "gap_side": side})
            return
        if c["kind"] == "congruent":
            P, Q = c["P"], c["Q"]
            names = {P.name, Q.name}

            def lens_dist(H):
                best = math.inf
                for t in H.ties:
                    if {t.l.ph.name, t.r.ph.name} == names and t.l.ph is not t.r.ph:
                        best = min(best, abs(t.l.x - x), abs(t.r.x - x))
                return best

            db, da = lens_dist(Hb), lens_dist(Ha)
            if (db < 0.2) == (da < 0.2):
                self.warn("congruent point at T=%.6f: ambiguous lens side (%.3g/%.3g)" % (T, db, da))
            side = "below" if db < da else "above"

            def phase_at(H):
                k, pc = H.piece_at(x)
                if k == "reg":
                    return pc[0].name
                if k == "tie":
                    return pc.l.ph.name if abs(pc.l.x - x) <= abs(pc.r.x - x) else pc.r.ph.name
                if k == "cmp":
                    return pc.name
                return None

            pa, pb = phase_at(Ha), phase_at(Hb)
            if pa not in names or pb not in names or pa == pb:
                self.warn("congruent point at T=%.6f: phases above/below %s/%s" % (T, pa, pb))
            self.congruent.append({"temperature_K": T, "x": x, "phase_above": pa, "phase_below": pb,
                                   "two_phase_side": side})
            return
        if c["kind"] == "cmp_congruent":
            P, cm = c["P"], c["cmp"]

            def phase_at(H):
                k, pc = H.piece_at(x)
                if k == "cmp":
                    return pc.name
                if k == "reg":
                    return pc[0].name
                if k == "tie":
                    return pc.l.ph.name if abs(pc.l.x - x) <= abs(pc.r.x - x) else pc.r.ph.name
                return None

            pa, pb = phase_at(Ha), phase_at(Hb)
            if {pa, pb} != {P.name, cm.name}:
                self.warn("compound congruent point at T=%.6f: phases above/below %s/%s" % (T, pa, pb))
            side = "below" if pb == cm.name else "above"
            self.congruent.append({"temperature_K": T, "x": x, "phase_above": pa, "phase_below": pb,
                                   "two_phase_side": side})

    # ---- invariant from an indicator root ----
    def accept_invariant(self, key, T_root, ps_root, payload):
        ties = ps_root.ties
        kind = key[0]
        if kind == "touch":
            i, Rname = key[1], key[2]
            t = ties[i]
            R = self.sys.by_name[Rname]
            states = [(t.l.ph, t.l.x), (R, payload), (t.r.ph, t.r.x)]
            cls = "eutectic"
        elif kind == "cmp":
            cm = self.sys.by_name[key[1]]
            t = None
            for tt in ties:
                if tt.l.x < cm.x < tt.r.x:
                    t = tt
            if t is None:
                # compound touched inside a single-phase region: exact candidate handles it
                return None
            states = [(t.l.ph, t.l.x), (cm, cm.x), (t.r.ph, t.r.x)]
            cls = "eutectic"
        elif kind == "region":
            i = key[1]
            a, b = ties[i], ties[i + 1]
            states = [(a.l.ph, a.l.x), (a.r.ph, 0.5 * (a.r.x + b.l.x)), (b.r.ph, b.r.x)]
            cls = "peritectic"
        elif kind == "vertex":
            i = key[1]
            a, b = ties[i], ties[i + 1]
            states = [(a.l.ph, a.l.x), (a.r.ph, a.r.x), (b.r.ph, b.r.x)]
            cls = "peritectic"
        else:
            return None
        T, xs, res = polish_invariant(states, T_root)
        if not (abs(T - T_root) < 1e-3 * max(1.0, T_root)) or res > 1e-5:
            self.warn("invariant polish at T=%.6f moved to %.6f (res %.3g); keeping bracket value" % (T_root, T, res))
            T = T_root
            xs = [s[1] for s in states]
        order = sorted(range(3), key=lambda k: xs[k])
        phases = [states[k][0] for k in order]
        xs = [xs[k] for k in order]
        if min(xs[1] - xs[0], xs[2] - xs[1]) < 1e-6:
            self.warn("invariant at T=%.6f has nearly coincident compositions" % T)
        # consistency check of the class against from-scratch hulls on both sides
        mid = phases[1]
        xm = xs[1]
        d = 0.02

        def mid_interior_of_outer_tie(H):
            k, pc = H.piece_at(xm)
            return k == "tie" and pc.l.ph is phases[0] and pc.r.ph is phases[2]

        below = mid_interior_of_outer_tie(self.hull(T - d))
        above = mid_interior_of_outer_tie(self.hull(T + d))
        cls_check = None
        if below and not above:
            cls_check = "eutectic"
        elif above and not below:
            cls_check = "peritectic"
        if cls_check != cls:
            self.warn("invariant at T=%.6f: class %s from sweep, hull check says %s" % (T, cls, cls_check))
        self.invariants.append({"temperature_K": float(T), "class": cls, "name": invariant_name(cls, phases),
                                "phases": [{"phase": phases[k].name, "x": float(xs[k])} for k in range(3)]})
        return T

    # ---- main loop ----
    def run(self):
        sysm = self.sys
        T = sysm.T_lo
        H = self.hull(T)
        ties = H.ties
        lp, rp = H.regions[0][0], H.regions[-1][0]
        ps = Pseudo(sysm, T, ties, lp, rp)
        ind = indicators(ps)
        steps = 0
        last_check_T = T
        guard = 0
        while T < sysm.T_hi - 1e-9:
            guard += 1
            if guard > 200000:
                self.warn("sweep guard tripped")
                break
            h = min(self.STEP, sysm.T_hi - T)
            Tn = T + h
            # exact candidates inside the step, earliest first
            event_T = None
            for ci, c in enumerate(self.sched):
                if ci in self.used or not (T < c["T"] <= Tn):
                    continue
                self.used.add(ci)
                if self.cand_is_real(c):
                    if c["kind"] != "pure_end":
                        self.report_candidate(c)
                    event_T = c["T"]
                    break
            if event_T is None:
                cont = continue_ties(ties, T, Tn)
                if cont is None:
                    self.warn("continuation failed on [%.6f, %.6f]; restarting from scratch" % (T, Tn))
                    Tn2 = T + 0.5 * h
                    H = self.hull(Tn2)
                    ties = H.ties
                    lp, rp = H.regions[0][0], H.regions[-1][0]
                    ps = Pseudo(sysm, Tn2, ties, lp, rp)
                    ind = indicators(ps)
                    T = Tn2
                    continue
                psn = Pseudo(sysm, Tn, cont, lp, rp)
                indn = indicators(psn)
                crossings = []
                for k, (key, v0, _) in enumerate(ind):
                    v1 = indn[k][1]
                    if v0 > 0.0 and v1 <= 0.0:
                        crossings.append(k)
                    elif v0 <= 0.0:
                        self.warn("indicator %s non-positive at base T=%.6f (%.3g)" % (str(key), T, v0))
                roots = []
                for k in crossings:
                    key = ind[k][0]
                    cache = {}

                    def fk(Tq, k=k, cache=cache):
                        if Tq == T:
                            return ind[k][1]
                        if Tq == Tn:
                            return indn[k][1]
                        ct = continue_ties(ties, T, Tq)
                        if ct is None:
                            return math.nan
                        pq = Pseudo(sysm, Tq, ct, lp, rp)
                        val = indicators(pq)[k]
                        cache[Tq] = (pq, val[2])
                        return val[1]

                    try:
                        Tr = brentq(fk, T, Tn, xtol=1e-12, rtol=1e-15, maxiter=200)
                    except Exception as e:
                        self.warn("brentq failed for %s on [%.6f, %.6f]: %s" % (str(key), T, Tn, e))
                        continue
                    ct = continue_ties(ties, T, Tr)
                    pq = Pseudo(sysm, Tr, ct, lp, rp)
                    payload = indicators(pq)[k][2]
                    roots.append((Tr, key, pq, payload))
                if roots:
                    roots.sort(key=lambda r: r[0])
                    Tr, key, pq, payload = roots[0]
                    if len(roots) > 1 and roots[1][0] - Tr < 1e-6:
                        self.warn("two indicators vanish together at T=%.6f: %s, %s" % (Tr, roots[0][1], roots[1][1]))
                    Te = self.accept_invariant(key, Tr, pq, payload)
                    event_T = Tr if Te is None else Te
            if event_T is not None:
                Tn = event_T + self.RESTART
                if Tn >= sysm.T_hi - 1e-9:
                    break
                H = self.hull(Tn)
                ties = H.ties
                lp, rp = H.regions[0][0], H.regions[-1][0]
                ps = Pseudo(sysm, Tn, ties, lp, rp)
                ind = indicators(ps)
                T = Tn
                last_check_T = T
                steps = 0
                continue
            # no event in the step: advance the continued state
            ties = cont
            ps = psn
            ind = indn
            T = Tn
            steps += 1
            if steps % self.CHECK_EVERY == 0:
                Hc = self.hull(T)
                if Hc.topology() != Pseudo_topology(ps):
                    self.warn("cross-check mismatch at T=%.6f: an event was missed in (%.6f, %.6f]" % (T, last_check_T, T))
                    ties = Hc.ties
                    lp, rp = Hc.regions[0][0], Hc.regions[-1][0]
                    ps = Pseudo(sysm, T, ties, lp, rp)
                    ind = indicators(ps)
                last_check_T = T
        self.invariants.sort(key=lambda e: e["temperature_K"])
        self.congruent.sort(key=lambda e: e["temperature_K"])
        self.critical.sort(key=lambda e: e["temperature_K"])


def Pseudo_topology(ps):
    out = []
    for rg in ps.regions:
        out.append(("R", rg[0].name))
    for t in ps.ties:
        out.append(("T", t.l.ph.name, t.r.ph.name))
    return tuple(sorted(out))


# =====================================================================================
# Report
# =====================================================================================
def finite(v):
    v = float(v)
    if not math.isfinite(v):
        raise ValueError("non-finite number in report")
    return v


def isotherm_report(sysm, T_raw, T):
    H = hull_at(sysm, T)
    regs = []
    for i, (p, lo, hi) in enumerate(H.regions):
        regs.append({"phase": p.name,
                     "x_lo": 0.0 if i == 0 else finite(lo),
                     "x_hi": 1.0 if i == len(H.regions) - 1 else finite(hi)})
    ties = []
    for t in H.ties:
        ties.append({"left_phase": t.l.ph.name,
                     "x_left": t.l.ph.x if t.l.is_cmp() else finite(t.l.x),
                     "right_phase": t.r.ph.name,
                     "x_right": t.r.ph.x if t.r.is_cmp() else finite(t.r.x)})
    return {"temperature_K": T_raw, "single_phase_regions": regs, "tie_lines": ties}, H


def build_report(d):
    sysm = System(d)
    isos = []
    for T_raw, T in zip(sysm.isotherms_raw, sysm.isotherms):
        rep, H = isotherm_report(sysm, T_raw, T)
        if not H.ok:
            print("WARNING: isotherm %s hull inconsistent: %s" % (T_raw, "; ".join(H.msgs)), file=sys.stderr)
        isos.append(rep)
    sw = Sweep(sysm)
    sw.run()
    for e in sw.invariants:
        e["temperature_K"] = finite(e["temperature_K"])
        for s in e["phases"]:
            s["x"] = finite(s["x"])
    for e in sw.congruent + sw.critical:
        e["temperature_K"] = finite(e["temperature_K"])
        e["x"] = finite(e["x"])
    # compound compositions exactly as given
    for e in sw.congruent:
        for cm in d["compounds"]:
            if e["phase_above"] == cm["name"] or e["phase_below"] == cm["name"]:
                e["x"] = cm["x_b"]
    for e in sw.invariants:
        for s in e["phases"]:
            for cm in d["compounds"]:
                if s["phase"] == cm["name"]:
                    s["x"] = cm["x_b"]
    report = {"system_id": d["system_id"],
              "isotherms": isos,
              "invariants": sw.invariants,
              "congruent_points": sw.congruent,
              "critical_points": sw.critical}
    return report, sw


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    with open(args.system, "r", encoding="utf-8") as f:
        d = json.load(f)
    report, sw = build_report(d)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, allow_nan=False)
        f.write("\n")
    print("hull evaluations: %d, warnings: %d" % (sw.n_hulls, len(sw.warnings)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
