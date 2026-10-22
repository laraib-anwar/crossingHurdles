#!/usr/bin/env python
"""tangentdiag.py - binary phase diagram from Gibbs energy models by pairwise common tangents.

Reads a system file (solution phases with Redlich-Kister excess terms, stoichiometric compounds,
a temperature window and requested isotherms) and writes the equilibrium diagram: the isothermal
sections (single-phase regions and tie-lines), the invariant reactions, the congruent points and
the critical points of miscibility gaps.

Method
------
At a temperature the two-phase equilibria are the common tangents of pairs of Gibbs energy
curves. For every pair of solution phases the tangents are the joining segments of the lower
convex hull of the two curves, polished by Newton iteration on the equal chemical potential
conditions. Compounds are stable when they lie below the straight line joining the two reference
end members, and are then connected on each side to the solution phase whose tangent through the
compound is lowest. Miscibility gaps of a phase are bounded by its spinodal (the roots of the
second derivative of G). Every tie-line is checked against the other solution phases at its
midpoint, and overlapping tie-lines are resolved by keeping the one with the lower Gibbs energy
at its midpoint.

Invariant reactions are located where the set of tie-lines changes with temperature (5 K scan,
refined by bisection) and classified from the phases present: eutectic when the liquid takes
part, eutectoid otherwise. Congruent points are the temperatures at which the two tie-lines of a
lens disappear. Critical points of miscibility gaps follow from the regular-solution result
T_c = L0(T_c) / (2 R) at x = 1/2.

usage: tangentdiag.py --system <system.json> --output <report.json>
"""
import argparse
import json
import math

import numpy as np
from scipy.optimize import brentq, fsolve

R = 8.314462618
XS = np.linspace(1e-6, 1 - 1e-6, 801)


class Phase:
    def __init__(self, d):
        self.name = d["name"]
        em = d["end_members"]
        self.hA, self.sA, self.hB, self.sB = em["A"]["h"], em["A"]["s"], em["B"]["h"], em["B"]["s"]
        self.L = [(c["a"], c["b"]) for c in d["redlich_kister"]]

    def ga(self, T):
        return self.hA - self.sA * T

    def gb(self, T):
        return self.hB - self.sB * T

    def g(self, x, T):
        x = np.asarray(x, float)
        ex = sum((a + b * T) * (1 - 2 * x) ** k for k, (a, b) in enumerate(self.L))
        return (1 - x) * self.ga(T) + x * self.gb(T) + R * T * (x * np.log(x) + (1 - x) * np.log(1 - x)) + x * (1 - x) * ex

    def dg(self, x, T):
        x = np.asarray(x, float)
        ex = sum((a + b * T) * (1 - 2 * x) ** k for k, (a, b) in enumerate(self.L))
        dex = sum(-2 * k * (a + b * T) * (1 - 2 * x) ** (k - 1) for k, (a, b) in enumerate(self.L) if k > 0)
        return self.gb(T) - self.ga(T) + R * T * np.log(x / (1 - x)) + (1 - 2 * x) * ex + x * (1 - x) * dex

    def d2g(self, x, T):
        h = 1e-5
        return (self.dg(x + h, T) - self.dg(x - h, T)) / (2 * h)

    def mu(self, x, T):
        g, d = self.g(x, T), self.dg(x, T)
        return g - x * d, g + (1 - x) * d


class Compound:
    def __init__(self, d):
        self.name, self.x, self.h, self.s = d["name"], float(d["x_b"]), d["h"], d["s"]

    def g(self, T):
        return self.h - self.s * T


def lower_chain(pts):
    """Lower convex hull (monotone chain) of points sorted by x: list of indices."""
    hull = []
    for i, (x, y) in enumerate(pts):
        while len(hull) >= 2:
            (x1, y1), (x2, y2) = pts[hull[-2]], pts[hull[-1]]
            if (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1) <= 0:
                hull.pop()
            else:
                break
        hull.append(i)
    return hull


def pair_tangents(p, q, T):
    """Common tangents of two solution phases: segments of the two-curve lower hull joining the
    curves, polished by Newton on the equal chemical potential conditions."""
    gp, gq = p.g(XS, T), q.g(XS, T)
    pts = sorted([(x, y, 0) for x, y in zip(XS, gp)] + [(x, y, 1) for x, y in zip(XS, gq)])
    idx = lower_chain([(x, y) for x, y, _ in pts])
    out = []
    for i, j in zip(idx, idx[1:]):
        a, b = pts[i], pts[j]
        if a[2] == b[2]:
            continue
        left, right = (p, q) if a[2] == 0 else (q, p)

        def eqs(z):
            x1, x2 = z
            if not (0 < x1 < 1 and 0 < x2 < 1):
                return [1e9, 1e9]
            a1, b1 = left.mu(x1, T)
            a2, b2 = right.mu(x2, T)
            return [a1 - a2, b1 - b2]
        z, info, ok, _ = fsolve(eqs, (a[0], b[0]), full_output=True, maxfev=200)
        if ok == 1 and 1e-5 < z[0] < z[1] < 1 - 1e-5 and z[1] - z[0] > 1e-3:
            out.append((left.name, float(z[0]), right.name, float(z[1])))
    return out


def spinodal_gap(p, T):
    """Miscibility gap of p bounded by the spinodal (d2G/dx2 = 0)."""
    d2 = p.d2g(XS, T)
    roots = []
    for i in range(len(XS) - 1):
        if d2[i] * d2[i + 1] < 0:
            roots.append(brentq(lambda x: p.d2g(x, T), XS[i], XS[i + 1]))
    if len(roots) >= 2:
        return roots[0], roots[-1]
    return None


def tangent_to_compound(p, c, T, side):
    """Tangent from solution phase p to compound c, on the left (side < 0) or right of c."""
    def f(x):
        return p.g(x, T) + p.dg(x, T) * (c.x - x) - c.g(T)
    grid = XS[XS < c.x] if side < 0 else XS[XS > c.x]
    vals = f(grid)
    for i in range(len(grid) - 1):
        if vals[i] * vals[i + 1] < 0:
            return brentq(f, grid[i], grid[i + 1])
    return None


def isotherm(phases, comps, T, ref_lo, ref_hi):
    """Tie-lines at T: pairwise tangents, spinodal gaps and compound tangents, overlaps resolved."""
    cands = []
    for i, p in enumerate(phases):
        for q in phases[i + 1:]:
            cands += pair_tangents(p, q, T)
        gap = spinodal_gap(p, T)
        if gap is not None:
            cands.append((p.name, gap[0], p.name, gap[1]))
    mix_line = lambda x: ref_lo.ga(T) * (1 - x) + ref_hi.gb(T) * x
    for c in comps:
        if c.g(T) < mix_line(c.x):
            best_l, best_r = None, None
            for p in phases:
                xl, xr = tangent_to_compound(p, c, T, -1), tangent_to_compound(p, c, T, +1)
                if xl is not None:
                    icpt = p.g(xl, T) - xl * p.dg(xl, T)          # value of the tangent at x = 0
                    if best_l is None or icpt < best_l[0]:
                        best_l = (icpt, p.name, xl)
                if xr is not None:
                    icpt = p.g(xr, T) + (1 - xr) * p.dg(xr, T)    # value of the tangent at x = 1
                    if best_r is None or icpt < best_r[0]:
                        best_r = (icpt, p.name, xr)
            if best_l is not None:
                cands.append((best_l[1], best_l[2], c.name, c.x))
            if best_r is not None:
                cands.append((c.name, c.x, best_r[1], best_r[2]))
    by_name = {p.name: p for p in phases}

    def midpoint_g(t):
        lp, xl, rp, xr = t
        gl = by_name[lp].g(xl, T) if lp in by_name else next(c.g(T) for c in comps if c.name == lp)
        gr = by_name[rp].g(xr, T) if rp in by_name else next(c.g(T) for c in comps if c.name == rp)
        return 0.5 * (gl + gr)
    def line_value(t, x):
        lp, xl, rp, xr = t
        gl = by_name[lp].g(xl, T) if lp in by_name else next(c.g(T) for c in comps if c.name == lp)
        gr = by_name[rp].g(xr, T) if rp in by_name else next(c.g(T) for c in comps if c.name == rp)
        return gl + (gr - gl) * (x - xl) / (xr - xl)

    # sanity check of every candidate against the other solution phases at the tie-line midpoint
    cands = [t for t in cands if line_value(t, 0.5 * (t[1] + t[3]))
             <= min(p.g(0.5 * (t[1] + t[3]), T) for p in phases) + 1e-6]
    cands.sort(key=midpoint_g)
    kept = []
    for t in cands:
        if all(t[3] <= k[1] or t[1] >= k[3] for k in kept):
            kept.append(t)
    kept.sort(key=lambda t: t[1])
    return kept


def end_phase(phases, T, side):
    return min(phases, key=lambda p: p.ga(T) if side == "A" else p.gb(T))


def regions_from_ties(ties, phases, T):
    regs = []
    left = end_phase(phases, T, "A").name
    x = 0.0
    for t in ties:
        if t[0] != left:
            left = t[0]
        if t[0] in {p.name for p in phases} and t[1] > x:
            regs.append(dict(phase=t[0], x_lo=x, x_hi=t[1]))
        x = t[3]
        left = t[2]
    right = end_phase(phases, T, "B").name
    if ties and ties[-1][2] in {p.name for p in phases}:
        right = ties[-1][2]
    regs.append(dict(phase=right, x_lo=x, x_hi=1.0))
    return regs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    with open(a.system, encoding="utf-8") as fh:
        d = json.load(fh)
    phases = [Phase(p) for p in d["solution_phases"]]
    comps = [Compound(c) for c in d["compounds"]]
    T_lo, T_hi = d["window_K"]
    liquid = next(p for p in phases if p.name == "liquid")
    solids = [p for p in phases if p is not liquid] or phases
    ref_lo = min(solids, key=lambda p: p.ga(0.5 * (T_lo + T_hi)))
    ref_hi = min(solids, key=lambda p: p.gb(0.5 * (T_lo + T_hi)))

    isos = []
    for T in d["isotherms_K"]:
        ties = isotherm(phases, comps, T, ref_lo, ref_hi)
        isos.append(dict(temperature_K=T, single_phase_regions=regions_from_ties(ties, phases, T),
                         tie_lines=[dict(left_phase=t[0], x_left=t[1], right_phase=t[2], x_right=t[3]) for t in ties]))

    # invariant reactions and congruent points: changes of the tie-line set with temperature
    by_name = {p.name: p for p in phases}

    def pairs(T):
        return tuple(sorted((t[0], t[2]) for t in isotherm(phases, comps, T, ref_lo, ref_hi)))
    invariants, congruent = [], []
    Ts = np.arange(T_lo, T_hi + 1e-9, 5.0)
    prev = pairs(Ts[0])
    for T0, T1 in zip(Ts, Ts[1:]):
        cur = pairs(T1)
        if cur != prev:
            lo, hi = T0, T1
            for _ in range(14):
                mid = 0.5 * (lo + hi)
                if pairs(mid) == prev:
                    lo = mid
                else:
                    hi = mid
            Tc = 0.5 * (lo + hi)
            lost, gained = set(prev) - set(cur), set(cur) - set(prev)
            involved = {n for pr in lost | gained for n in pr}
            pure_change = (end_phase(phases, lo, "A") is not end_phase(phases, hi, "A")
                           or end_phase(phases, lo, "B") is not end_phase(phases, hi, "B"))
            ties_lo = isotherm(phases, comps, lo, ref_lo, ref_hi)
            ties_hi = isotherm(phases, comps, hi, ref_lo, ref_hi)
            if pure_change:
                pass                                   # melting or transformation of a pure component
            elif len(lost | gained) == 2 and len(involved) == 2:
                # a two-phase lens appears or disappears: congruent point
                changed = [t for t in ties_lo + ties_hi if (t[0], t[2]) in lost | gained]
                xc = float(np.mean([v for t in changed for v in (t[1], t[3])]))
                p_, q_ = sorted(involved)

                def g_at(n):
                    if n in by_name:
                        return float(by_name[n].g(xc, hi))
                    return next(c.g(hi) for c in comps if c.name == n)
                above, below = sorted(involved, key=g_at)
                congruent.append(dict(temperature_K=Tc, x=xc, phase_above=above, phase_below=below,
                                      two_phase_side="below"))
            elif len(involved) >= 3:
                states = {}
                for t in ties_lo + ties_hi:
                    if t[0] in involved:
                        states.setdefault(t[0], t[1])
                    if t[2] in involved:
                        states.setdefault(t[2], t[3])
                phs = sorted(states.items(), key=lambda kv: kv[1])[:3]
                if len(phs) == 3:
                    name = "eutectic" if "liquid" in involved else "eutectoid"
                    invariants.append(dict(temperature_K=Tc, **{"class": "eutectic"}, name=name,
                                           phases=[dict(phase=n, x=x) for n, x in phs]))
            prev = cur

    critical = []
    for p in phases:
        a0, b0 = p.L[0]
        if 2 * R - b0 != 0:
            Tc = a0 / (2 * R - b0)
            if T_lo < Tc < T_hi:
                critical.append(dict(temperature_K=Tc, x=0.5, phase=p.name, gap_side="below"))
    critical.sort(key=lambda c: c["temperature_K"])

    rep = dict(system_id=d["system_id"], isotherms=isos, invariants=invariants, congruent_points=congruent,
               critical_points=critical)
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
