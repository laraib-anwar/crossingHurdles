#!/usr/bin/env python
"""Equilibrium phase diagram of a binary system from Gibbs energy models (PHASE_SPEC.md).

The equilibrium at a temperature is the lower convex hull of the solution-phase curves and the
compound points. Anchor temperatures (window start, isotherms, just after every event) get a
certified hull: a point-cloud hull refined by Newton on the exact common-tangent equations and
checked against every phase. Between anchors the tie-lines are continued in temperature by
Newton, and every way the topology can change is watched by a continuous indicator that is
positive while the structure is valid: a third phase reaching a tie-line, a phase or a compound
touching a single-phase region from above, a region or a compound vertex collapsing, a lens or a
miscibility gap closing, a pure end member changing. The first indicator to cross zero brackets
the event, which is then solved exactly from its own equations and classified by its mechanism.

usage: phasediagram.py --system <system.json> --output <report.json>
"""
import argparse
import json
import math

import numpy as np
from numpy.polynomial import polynomial as P
from scipy.optimize import brentq
from scipy.spatial import ConvexHull

R = 8.314462618
XG = np.unique(np.concatenate([np.logspace(-7, -2, 61), np.linspace(0.01, 0.99, 1961), 1 - np.logspace(-2, -7, 61)]))
STEP = 0.25        # temperature scan step (K); events are at least 0.5 K apart in the domain
EPS = 0.02         # distance past an event at which the hull is rebuilt (K)
EDGE = 1e-4        # exclusion around a phase's own tangent point when testing a tie-line
VIOL = 1e-7        # J/mol below the hull that counts as a violation


def logit(x):
    return math.log(x / (1.0 - x))


def expit(u):
    if u >= 0:
        e = math.exp(-u)
        return 1.0 / (1.0 + e)
    e = math.exp(u)
    return e / (1.0 + e)


def xlogx(x):
    x = np.asarray(x, float)
    out = np.zeros_like(x)
    m = x > 0
    out[m] = x[m] * np.log(x[m])
    return out


class Sol:
    """A substitutional solution phase with Redlich-Kister excess and linear-in-T coefficients."""

    def __init__(self, i, d):
        self.i, self.name, self.kind = i, d["name"], "S"
        em = d["end_members"]
        self.hA, self.sA, self.hB, self.sB = float(em["A"]["h"]), float(em["A"]["s"]), float(em["B"]["h"]), float(em["B"]["s"])
        pa, pb = np.zeros(5), np.zeros(5)
        for k, c in enumerate(d["redlich_kister"]):
            pk = P.polymul([0.0, 1.0, -1.0], P.polypow([1.0, -2.0], k))
            pa[: len(pk)] += float(c["a"]) * pk
            pb[: len(pk)] += float(c["b"]) * pk
        self.pa = [pa] + [P.polyder(pa, n) for n in (1, 2, 3, 4)]
        self.pb = [pb] + [P.polyder(pb, n) for n in (1, 2, 3, 4)]

    def GA(self, T):
        return self.hA - self.sA * T

    def GB(self, T):
        return self.hB - self.sB * T

    def ex(self, n, x, T):
        return P.polyval(x, self.pa[n]) + T * P.polyval(x, self.pb[n])

    @staticmethod
    def _xm(x, xm):
        x = np.asarray(x, float)
        return x, (1 - x if xm is None else np.asarray(xm, float))

    def G(self, x, T, xm=None):
        x, xm = self._xm(x, xm)
        return self.GA(T) * xm + self.GB(T) * x + R * T * (xlogx(x) + xlogx(xm)) + self.ex(0, x, T)

    def Gx(self, x, T, xm=None):
        x, xm = self._xm(x, xm)
        return (self.hB - self.hA) - (self.sB - self.sA) * T + R * T * np.log(x / xm) + self.ex(1, x, T)

    def Gxx(self, x, T, xm=None):
        x, xm = self._xm(x, xm)
        return R * T / (x * xm) + self.ex(2, x, T)

    def Gxxx(self, x, T, xm=None):
        x, xm = self._xm(x, xm)
        q = x * xm
        return R * T * (x - xm) / (q * q) + self.ex(3, x, T)

    def Gxxxx(self, x, T, xm=None):
        x, xm = self._xm(x, xm)
        q = x * xm
        return R * T * (2 / (q * q) + 2 * (xm - x) ** 2 / (q * q * q)) + self.ex(4, x, T)

    def GT(self, x, T, xm=None):
        x, xm = self._xm(x, xm)
        return -self.sA * xm - self.sB * x + R * (xlogx(x) + xlogx(xm)) + P.polyval(x, self.pb[0])

    def GxT(self, x, T, xm=None):
        x, xm = self._xm(x, xm)
        return -(self.sB - self.sA) + R * np.log(x / xm) + P.polyval(x, self.pb[1])

    def GxxT(self, x, T, xm=None):
        x, xm = self._xm(x, xm)
        return R / (x * xm) + P.polyval(x, self.pb[2])

    def GxxxT(self, x, T, xm=None):
        x, xm = self._xm(x, xm)
        q = x * xm
        return R * (x - xm) / (q * q) + P.polyval(x, self.pb[3])


class Comp:
    """A stoichiometric compound: one point at x_theta."""

    def __init__(self, i, d):
        self.i, self.name, self.kind = i, d["name"], "C"
        self.x, self.h, self.s = float(d["x_b"]), float(d["h"]), float(d["s"])

    def G(self, T):
        return self.h - self.s * T


class State:
    """A phase at a composition: a point of the (x, G) plane that may be a hull vertex."""
    __slots__ = ("ph", "x")

    def __init__(self, ph, x):
        self.ph, self.x = ph, float(x)

    def label(self):
        return (self.ph.kind, self.ph.i)

    def G(self, T):
        return float(self.ph.G(self.x, T)) if self.ph.kind == "S" else self.ph.G(T)


class Tie:
    """A tie-line: two states on one supporting line y = m x + c."""
    __slots__ = ("l", "r", "m", "c")

    def __init__(self, l, r, m, c):
        self.l, self.r, self.m, self.c = l, r, m, c

    def sig(self):
        return (self.l.label(), self.r.label())


class NewtonFailure(Exception):
    pass


def converged(small, prev, it, scale):
    """Newton stop rule: a tiny scaled step, or a step that no longer shrinks at rounding level."""
    if scale != 1.0 or it < 1:
        return False
    return small < 1e-13 or (small < 1e-9 and prev is not None and small > 0.5 * prev)


class System:
    def __init__(self, d):
        self.id = d["system_id"]
        self.sols = [Sol(i, s) for i, s in enumerate(d["solution_phases"])]
        self.comps = [Comp(j, c) for j, c in enumerate(d["compounds"])]
        self.liquid = next(s for s in self.sols if s.name == "liquid")
        self.T_lo, self.T_hi = (float(v) for v in d["window_K"])
        self.isotherms = [float(v) for v in d["isotherms_K"]]

    # ------------------------------------------------------------ exact equations
    def line_newton(self, states, T, solve_T, max_iter=80):
        """Newton on the supporting-line equations: for every solution state G = m x + c and
        dG/dx = m, for every compound G_theta = m x_theta + c; unknowns m, c, logit(x) of the
        solution states and, if solve_T, T. Returns (states, T, m, c) or raises."""
        sol_idx = [k for k, s in enumerate(states) if s.ph.kind == "S"]
        xs = [s.x for s in states]
        xms = [1.0 - s.x for s in states]
        us = [logit(xs[k]) for k in sol_idx]
        for j, k in enumerate(sol_idx):
            xms[k] = expit(-us[j])
        # initial m, c from a least-squares fit through the states
        A = np.array([[s.x, 1.0] for s in states])
        y = np.array([s.G(T) for s in states])
        m, c = np.linalg.lstsq(A, y, rcond=None)[0]
        n = 2 + len(sol_idx) + (1 if solve_T else 0)
        prev = None
        for it in range(max_iter):
            F, J = np.zeros(n), np.zeros((n, n))
            row = 0
            for k, s in enumerate(states):
                x = xs[k]
                if s.ph.kind == "S":
                    p, j, xm = s.ph, sol_idx.index(k), xms[k]
                    dxdu = x * xm
                    g, gx, gxx = float(p.G(x, T, xm)), float(p.Gx(x, T, xm)), float(p.Gxx(x, T, xm))
                    F[row] = g - m * x - c
                    J[row, 0], J[row, 1], J[row, 2 + j] = -x, -1.0, (gx - m) * dxdu
                    if solve_T:
                        J[row, n - 1] = float(p.GT(x, T, xm))
                    row += 1
                    F[row] = gx - m
                    J[row, 0], J[row, 2 + j] = -1.0, gxx * dxdu
                    if solve_T:
                        J[row, n - 1] = float(p.GxT(x, T, xm))
                    row += 1
                else:
                    F[row] = s.ph.G(T) - m * x - c
                    J[row, 0], J[row, 1] = -x, -1.0
                    if solve_T:
                        J[row, n - 1] = -s.ph.s
                    row += 1
            try:
                dz = np.linalg.solve(J, -F)
            except np.linalg.LinAlgError:
                raise NewtonFailure("singular Jacobian")
            if not np.all(np.isfinite(dz)):
                raise NewtonFailure("non-finite step")
            scale = 1.0
            for j in range(len(sol_idx)):
                scale = min(scale, 1.0 / max(abs(dz[2 + j]), 1e-300))
            if solve_T:
                scale = min(scale, 20.0 / max(abs(dz[n - 1]), 1e-300))
            dz *= scale
            m += dz[0]
            c += dz[1]
            for j, k in enumerate(sol_idx):
                us[j] += dz[2 + j]
                xs[k], xms[k] = expit(us[j]), expit(-us[j])
                if not (0.0 < xs[k] < 1.0 and 0.0 < xms[k] < 1.0):
                    raise NewtonFailure("composition reached a pure end")
            if solve_T:
                T += dz[n - 1]
                if not (1.0 < T < 1e5):
                    raise NewtonFailure("temperature left the physical range")
            # a composition step counts by its logit or by 100 x its absolute size, whichever is
            # smaller: dilute ends are resolved absolutely, not relatively
            small = max([min(abs(dz[2 + j]), 100.0 * abs(dz[2 + j]) * xs[k] * xms[k]) for j, k in enumerate(sol_idx)]
                        + [abs(dz[n - 1]) / T if solve_T else 0.0]
                        + [abs(dz[0]) / (abs(m) + 1e3), abs(dz[1]) / (abs(c) + 1e3)])
            if converged(small, prev, it, scale):
                break
            prev = small
        else:
            raise NewtonFailure("no convergence")
        out = [State(s.ph, xs[k]) for k, s in enumerate(states)]
        for s in out:
            if s.ph.kind == "S" and not (0.0 < s.x < 1.0):
                raise NewtonFailure("composition left (0, 1)")
        return out, T, float(m), float(c)

    def tie(self, l, r, T):
        """Polish a tie-line between two states at fixed T."""
        if l.ph.kind == "C" and r.ph.kind == "C":
            m = (r.G(T) - l.G(T)) / (r.x - l.x)
            return Tie(l, r, m, l.G(T) - m * l.x)
        states, _, m, c = self.line_newton([l, r], T, False)
        if not states[0].x < states[1].x:
            raise NewtonFailure("tie-line ends crossed")
        return Tie(states[0], states[1], m, c)

    def tangency(self, p, q, x, T, max_iter=80):
        """Congruent point of two solution phases: G_p = G_q and dG_p/dx = dG_q/dx; unknowns logit(x), T."""
        u, prev = logit(x), None
        for it in range(max_iter):
            x, xm = expit(u), expit(-u)
            dxdu = x * xm
            F = np.array([float(p.G(x, T, xm) - q.G(x, T, xm)), float(p.Gx(x, T, xm) - q.Gx(x, T, xm))])
            J = np.array([[float(p.Gx(x, T, xm) - q.Gx(x, T, xm)) * dxdu, float(p.GT(x, T, xm) - q.GT(x, T, xm))],
                          [float(p.Gxx(x, T, xm) - q.Gxx(x, T, xm)) * dxdu, float(p.GxT(x, T, xm) - q.GxT(x, T, xm))]])
            try:
                dz = np.linalg.solve(J, -F)
            except np.linalg.LinAlgError:
                raise NewtonFailure("singular Jacobian")
            scale = min(1.0, 1.0 / max(abs(dz[0]), 1e-300), 20.0 / max(abs(dz[1]), 1e-300))
            dz *= scale
            u += dz[0]
            T += dz[1]
            if not (1.0 < T < 1e5):
                raise NewtonFailure("temperature left the physical range")
            small = max(min(abs(dz[0]), 100.0 * abs(dz[0]) * x * xm), abs(dz[1]) / T)
            if converged(small, prev, it, scale):
                return expit(u), T
            prev = small
        raise NewtonFailure("no convergence")

    def compound_touch(self, p, th, T, max_iter=80):
        """T at which solution phase p passes through compound th: G_p(x_theta, T) = G_theta(T)."""
        prev = None
        for it in range(max_iter):
            F = float(p.G(th.x, T)) - th.G(T)
            dF = float(p.GT(th.x, T)) + th.s
            if dF == 0.0:
                raise NewtonFailure("flat")
            dT = -F / dF
            dT = max(-20.0, min(20.0, dT))
            T += dT
            if not (1.0 < T < 1e5):
                raise NewtonFailure("temperature left the physical range")
            small = abs(dT) / T
            if converged(small, prev, it, 1.0):
                return T
            prev = small
        raise NewtonFailure("no convergence")

    def critical(self, p, x, T, max_iter=80):
        """Consolute point of p: d2G/dx2 = 0 and d3G/dx3 = 0; unknowns logit(x), T."""
        u, prev = logit(x), None
        for it in range(max_iter):
            x, xm = expit(u), expit(-u)
            dxdu = x * xm
            F = np.array([float(p.Gxx(x, T, xm)), float(p.Gxxx(x, T, xm))])
            J = np.array([[float(p.Gxxx(x, T, xm)) * dxdu, float(p.GxxT(x, T, xm))],
                          [float(p.Gxxxx(x, T, xm)) * dxdu, float(p.GxxxT(x, T, xm))]])
            try:
                dz = np.linalg.solve(J, -F)
            except np.linalg.LinAlgError:
                raise NewtonFailure("singular Jacobian")
            scale = min(1.0, 1.0 / max(abs(dz[0]), 1e-300), 20.0 / max(abs(dz[1]), 1e-300))
            dz *= scale
            u += dz[0]
            T += dz[1]
            if not (1.0 < T < 1e5):
                raise NewtonFailure("temperature left the physical range")
            small = max(min(abs(dz[0]), 100.0 * abs(dz[0]) * x * xm), abs(dz[1]) / T)
            if converged(small, prev, it, scale):
                return expit(u), T
            prev = small
        raise NewtonFailure("no convergence")

    # ------------------------------------------------------------ hull at fixed T
    def cloud(self, T, extra):
        X = [XG] * len(self.sols) + [np.array([c.x]) for c in self.comps]
        Y = [s.G(XG, T) for s in self.sols] + [np.array([c.G(T)]) for c in self.comps]
        phase = []
        for s in self.sols:
            phase += [s] * len(XG)
        phase += list(self.comps)
        for s, x in extra:
            X.append(np.array([x]))
            Y.append(np.array([float(s.G(x, T))]))
            phase.append(s)
        return np.concatenate(X), np.concatenate(Y), phase

    @staticmethod
    def lower_hull(X, Y):
        hv = ConvexHull(np.column_stack([X, Y])).vertices        # counterclockwise
        k0 = min(range(len(hv)), key=lambda k: (X[hv[k]], Y[hv[k]]))
        k1 = max(range(len(hv)), key=lambda k: (X[hv[k]], -Y[hv[k]]))
        idx = list(hv[k0:k1 + 1]) if k1 >= k0 else list(hv[k0:]) + list(hv[:k1 + 1])
        return idx

    def ties_from_vertices(self, verts, T):
        ties = []
        for a, b in zip(verts, verts[1:]):
            if a.ph.kind == "S" and b.ph.kind == "S" and a.ph is b.ph:
                xs = np.linspace(a.x, b.x, 18)[1:-1]
                if np.min(a.ph.Gxx(xs, T)) > 0:
                    continue                                   # same convex arc: a region
            ties.append(self.tie(a, b, T))
        return ties

    def regions(self, ties, T, sole=None):
        """Single-phase regions implied by the ties: (phase, x_lo, x_hi, k_prev, k_next)."""
        if not ties:
            return [(sole, 0.0, 1.0, None, None)]
        out = []
        if ties[0].l.ph.kind != "S":
            raise NewtonFailure("hull starts at a compound")
        out.append((ties[0].l.ph, 0.0, ties[0].l.x, None, 0))
        for k in range(len(ties) - 1):
            a, b = ties[k].r, ties[k + 1].l
            if a.ph is not b.ph:
                raise NewtonFailure("consecutive tie-lines do not share a phase")
            if a.ph.kind == "S":
                out.append((a.ph, a.x, b.x, k, k + 1))
        if ties[-1].r.ph.kind != "S":
            raise NewtonFailure("hull ends at a compound")
        out.append((ties[-1].r.ph, ties[-1].r.x, 1.0, len(ties) - 1, None))
        return out

    def consistent(self, ties, T):
        """Merge tie-line pairs whose shared phase has a non-positive region or a non-convex
        compound vertex (the shared state is not actually on the hull)."""
        changed = True
        while changed and ties:
            changed = False
            for k in range(len(ties) - 1):
                a, b = ties[k].r, ties[k + 1].l
                if a.ph is not b.ph:
                    raise NewtonFailure("consecutive tie-lines do not share a phase")
                bad = (a.ph.kind == "S" and not a.x < b.x) or (a.ph.kind == "C" and not ties[k].m < ties[k + 1].m)
                if bad:
                    merged = self.tie(ties[k].l, ties[k + 1].r, T)
                    ties = ties[:k] + [merged] + ties[k + 2:]
                    changed = True
                    break
        return ties

    def hull_values(self, ties, T, x, sole=None):
        """Equilibrium G on the array x for a certified structure."""
        x = np.asarray(x, float)
        out = np.empty_like(x)
        pieces = []
        for ph, lo, hi, _, _ in self.regions(ties, T, sole):
            pieces.append((lo, hi, ph, None))
        for t in ties:
            pieces.append((t.l.x, t.r.x, None, t))
        pieces.sort(key=lambda p: p[0])
        bounds = np.array([p[0] for p in pieces] + [1.0])
        k = np.clip(np.searchsorted(bounds, x, side="right") - 1, 0, len(pieces) - 1)
        for i, (lo, hi, ph, t) in enumerate(pieces):
            msk = k == i
            if not np.any(msk):
                continue
            out[msk] = ph.G(x[msk], T) if t is None else t.m * x[msk] + t.c
        return out

    def violations(self, ties, T, sole=None):
        """Phases that lie below the hull of a candidate structure: list of (phase, x)."""
        h = self.hull_values(ties, T, XG, sole)
        out = []
        for s in self.sols:
            d = s.G(XG, T) - h
            below = np.flatnonzero(d < -VIOL)
            if len(below):
                # one representative per run of consecutive grid points
                runs = np.split(below, np.flatnonzero(np.diff(below) > 1) + 1)
                for run in runs:
                    k = run[np.argmin(d[run])]
                    out.append((s, float(XG[k])))
        for c in self.comps:
            if c.G(T) - float(self.hull_values(ties, T, np.array([c.x]), sole)[0]) < -VIOL:
                out.append((c, c.x))
        # convexity of every single-phase region
        for ph, lo, hi, _, _ in self.regions(ties, T, sole):
            msk = (XG >= lo) & (XG <= hi)
            if np.any(msk):
                g2 = ph.Gxx(XG[msk], T)
                k = int(np.argmin(g2))
                if g2[k] < 0:
                    out.append((ph, float(XG[msk][k])))
        return out

    def certified(self, T):
        """Exact hull structure at T: polished tie-lines certified against every phase."""
        extra = []
        for it in range(12):
            X, Y, phase = self.cloud(T, extra)
            idx = self.lower_hull(X, Y)
            verts = [State(phase[i], X[i]) for i in idx]
            ties = self.consistent(self.ties_from_vertices(verts, T), T)
            sole = verts[0].ph if not ties else None
            viol = self.violations(ties, T, sole)
            if not viol:
                return ties, sole
            seen = {(s.i, round(x, 12)) for s, x in extra}
            for t in ties:
                for st in (t.l, t.r):
                    if st.ph.kind == "S" and (st.ph.i, round(st.x, 12)) not in seen:
                        extra.append((st.ph, st.x))
            for ph, x in viol:
                if ph.kind != "S":
                    continue
                for dx in (0.0, -1e-6, 1e-6, -1e-5, 1e-5, -1e-4, 1e-4, -5e-4, 5e-4):
                    xx = x + dx
                    if 1e-9 < xx < 1 - 1e-9 and (ph.i, round(xx, 12)) not in seen:
                        extra.append((ph, xx))
        raise NewtonFailure(f"hull at T={T} did not certify")

    # ------------------------------------------------------------ continuation and indicators
    def continue_ties(self, ties, T):
        return [self.tie(t.l, t.r, T) for t in ties]

    def indicators(self, ties, T, sole):
        """All indicators of the structure (ties at T): positive while the topology holds."""
        G = [s.G(XG, T) for s in self.sols]
        out = []
        regs = self.regions(ties, T, sole)
        for k, t in enumerate(ties):
            x1, x2 = t.l.x, t.r.x
            line = t.m * XG + t.c
            for s in self.sols:
                lo = x1 + EDGE if s is t.l.ph else x1
                hi = x2 - EDGE if s is t.r.ph else x2
                msk = (XG >= lo) & (XG <= hi)
                if np.any(msk):
                    d = G[s.i][msk] - line[msk]
                    j = int(np.argmin(d))
                    out.append((float(d[j]), ("clear", k, s, float(XG[msk][j]))))
            for c in self.comps:
                if x1 < c.x < x2:
                    out.append((c.G(T) - (t.m * c.x + t.c), ("clearC", k, c, c.x)))
            if t.l.ph is t.r.ph:                                       # miscibility gap
                msk = (XG >= x1) & (XG <= x2)
                g2 = t.l.ph.Gxx(XG[msk], T) if np.any(msk) else np.array([1.0])
                out.append((-float(np.min(g2)), ("gapclose", k)))
        for ph, lo, hi, kp, kn in regs:
            msk = (XG >= lo) & (XG <= hi)
            if np.any(msk):
                for s in self.sols:
                    if s is ph:
                        continue
                    d = G[s.i][msk] - G[ph.i][msk]
                    j = int(np.argmin(d))
                    out.append((float(d[j]), ("open", ph, s, float(XG[msk][j]), kp, kn)))
                g2 = ph.Gxx(XG[msk], T)
                out.append((float(np.min(g2)), ("gap", ph, float(XG[msk][int(np.argmin(g2))]), kp, kn)))
            for c in self.comps:
                if lo < c.x < hi:
                    out.append((c.G(T) - float(ph.G(c.x, T)), ("openC", ph, c, kp, kn)))
            if kp is not None and kn is not None:
                out.append((hi - lo, ("width", kp, kn, ph)))
                a, b = ties[kp], ties[kn]
                if a.l.ph is b.r.ph:                                   # lens of ph inside a.l.ph
                    msk2 = (XG >= a.l.x) & (XG <= b.r.x)
                    d = G[ph.i][msk2] - G[a.l.ph.i][msk2]
                    out.append((-float(np.min(d)), ("lens", kp, kn, a.l.ph, ph)))
        for k in range(len(ties) - 1):
            a, b = ties[k], ties[k + 1]
            if a.r.ph.kind == "C":
                out.append((b.m - a.m, ("vertex", k, k + 1, a.r.ph)))
                if a.l.ph is b.r.ph:
                    out.append((float(a.l.ph.G(a.r.ph.x, T)) - a.r.ph.G(T), ("lensC", k, k + 1, a.l.ph, a.r.ph)))
        left = regs[0][0]
        right = regs[-1][0]
        for s in self.sols:
            if s is not left:
                out.append((s.GA(T) - left.GA(T), ("pureA", s)))
            if s is not right:
                out.append((s.GB(T) - right.GB(T), ("pureB", s)))
        return out

    def closing_tags(self, ties, sole):
        """Closing indicators of the structure that can be evaluated without continuing the
        tie-lines: a lens, a compound lens or a miscibility gap closing on its old span."""
        tags = []
        for k, t in enumerate(ties):
            if t.l.ph is t.r.ph:
                tags.append(("gapclose", k))
        for k in range(len(ties) - 1):
            a, b = ties[k], ties[k + 1]
            if a.l.ph is b.r.ph and a.r.ph is b.l.ph:
                if a.r.ph.kind == "S":
                    tags.append(("lens", k, k + 1, a.l.ph, a.r.ph))
                else:
                    tags.append(("lensC", k, k + 1, a.l.ph, a.r.ph))
        return tags

    def closing_value(self, ties, T, tag):
        """Value of a closing indicator at T on the spans of the old structure `ties`."""
        if tag[0] == "gapclose":
            t = ties[tag[1]]
            msk = (XG >= t.l.x) & (XG <= t.r.x)
            xs = np.concatenate([[t.l.x], XG[msk], [t.r.x]])
            return -float(np.min(t.l.ph.Gxx(xs, T)))
        if tag[0] == "lens":
            _, kp, kn, outer, inner = tag
            lo, hi = ties[kp].l.x, ties[kn].r.x
            msk = (XG >= lo) & (XG <= hi)
            xs = np.concatenate([[lo], XG[msk], [hi]])
            return -float(np.min(inner.G(xs, T) - outer.G(xs, T)))
        _, kp, kn, outer, c = tag
        return float(outer.G(c.x, T)) - c.G(T)

    def closing_event(self, ties, Tr, tag):
        if tag[0] == "gapclose":
            t = ties[tag[1]]
            x, T = self.critical(t.l.ph, 0.5 * (t.l.x + t.r.x), Tr)
            return dict(kind="critical", T=T, x=x, phase=t.l.ph, side="below")
        if tag[0] == "lens":
            _, kp, kn, outer, inner = tag
            x, T = self.tangency(outer, inner, 0.5 * (ties[kp].r.x + ties[kn].l.x), Tr)
            return dict(kind="congruent", T=T, x=x, above=outer, below=inner, side="below")
        _, kp, kn, outer, c = tag
        T = self.compound_touch(outer, c, Tr)
        return dict(kind="congruent", T=T, x=c.x, above=outer, below=c, side="below")

    def closing_only(self, ties, sole, T0, T1):
        """Earliest closing event in (T0, T1] found from the tie-free indicators, or None."""
        roots = []
        for tag in self.closing_tags(ties, sole):
            v0, v1 = self.closing_value(ties, T0, tag), self.closing_value(ties, T1, tag)
            if v1 < 0 <= v0:
                roots.append((brentq(lambda T, tag=tag: self.closing_value(ties, T, tag), T0, T1,
                                     xtol=1e-9, rtol=1e-15, maxiter=200), tag))
        if not roots:
            return None
        roots.sort(key=lambda r: r[0])
        return self.closing_event(ties, roots[0][0], roots[0][1])

    @staticmethod
    def same_tag(a, b):
        if a[0] != b[0]:
            return False
        if a[0] in ("clear", "open"):
            return a[1:3] == b[1:3] if a[0] == "clear" else (a[1] is b[1] and a[2] is b[2])
        if a[0] in ("clearC",):
            return a[1] == b[1] and a[2] is b[2]
        if a[0] == "openC":
            return a[1] is b[1] and a[2] is b[2]
        if a[0] == "gap":
            return a[1] is b[1]
        if a[0] in ("pureA", "pureB"):
            return a[1] is b[1]
        return a[1] == b[1]

    def indicator_value(self, ties, sole, T, tag):
        cont = self.continue_ties(ties, T)
        for v, t in self.indicators(cont, T, sole):
            if self.same_tag(t, tag):
                return v, cont, t
        raise NewtonFailure("indicator vanished")

    # ------------------------------------------------------------ events
    def classify_name(self, states):
        mid, outer = states[1].ph, (states[0].ph, states[2].ph)
        n_liq = sum(1 for p in outer if p is self.liquid)
        mid_liq = mid is self.liquid
        return mid_liq, n_liq

    def invariant(self, states, T, cls):
        states, T, m, c = self.line_newton(states, T, True)
        states.sort(key=lambda s: s.x)
        mid_liq, n_liq = self.classify_name(states)
        if cls == "eutectic":
            name = ("eutectic" if n_liq == 0 else "monotectic") if mid_liq else ("eutectoid" if n_liq == 0 else "metatectic")
        else:
            name = "inverse_monotectic" if mid_liq else {1: "peritectic", 2: "syntectic", 0: "peritectoid"}[n_liq]
        for a, b in zip(states, states[1:]):
            if not b.x - a.x > 0:
                raise NewtonFailure("invariant compositions not ordered")
        return dict(kind="invariant", T=T, cls=cls, name=name, states=states)

    def pure_transition(self, ties, sole, T, tag):
        """Temperature at which solution phase tag[1] replaces the end phase of the structure."""
        regs = self.regions(ties, T, sole)
        q = tag[1]
        if tag[0] == "pureA":
            left = regs[0][0]
            return (q.hA - left.hA) / (q.sA - left.sA)
        right = regs[-1][0]
        return (q.hB - right.hB) / (q.sB - right.sB)

    def next_pure(self, ties, sole, T):
        """The nearest temperature above T at which a pure end member of the current end phases
        is overtaken by another solution phase (melting or allotropic transition), or None."""
        regs = self.regions(ties, T, sole)
        best = None
        for end, q_of in (("A", regs[0][0]), ("B", regs[-1][0])):
            for q in self.sols:
                if q is q_of:
                    continue
                if end == "A":
                    num, den = q.hA - q_of.hA, q.sA - q_of.sA
                else:
                    num, den = q.hB - q_of.hB, q.sB - q_of.sB
                if den == 0.0:
                    continue
                Tp = num / den
                if Tp > T + 1e-9 and (best is None or Tp < best):
                    best = Tp
        return best

    def solve_event(self, ties, sole, T0, T1, fired):
        """Locate and solve the earliest event in (T0, T1]."""
        roots = []
        for value, tag in fired:
            if tag[0] in ("pureA", "pureB"):
                Tp = self.pure_transition(ties, sole, T0, tag)
                if T0 - 1e-6 <= Tp <= T1 + 1e-6:
                    roots.append((Tp, tag))
                continue
            if tag[0] in ("lens", "lensC", "gapclose"):
                f = lambda T, tag=tag: self.closing_value(ties, T, tag)
            else:
                f = lambda T, tag=tag: self.indicator_value(ties, sole, T, tag)[0]
            try:
                Tr = brentq(f, T0, T1, xtol=1e-9, rtol=1e-15, maxiter=200)
            except (ValueError, NewtonFailure):
                continue
            roots.append((Tr, tag))
        if not roots:
            raise NewtonFailure("no indicator root")
        roots.sort(key=lambda r: r[0])
        Tr = roots[0][0]
        near = [tag for t, tag in roots if t - Tr < 1e-6]
        kinds = {tag[0] for tag in near}
        # a closing lens or compound lens takes precedence over the collapse of its region; a pure
        # end transition over the opening indicators that see it at the first grid point
        if "lens" in kinds or "lensC" in kinds:
            near = [tag for tag in near if tag[0] in ("lens", "lensC")]
        if "pureA" in kinds or "pureB" in kinds:
            near = [tag for tag in near if tag[0] in ("pureA", "pureB")]
        tag = near[0]
        kind = tag[0]
        if kind in ("pureA", "pureB"):
            return dict(kind="pure", T=self.pure_transition(ties, sole, T0, tag))
        if kind in ("lens", "lensC", "gapclose"):
            return self.closing_event(ties, Tr, tag)
        cont = self.continue_ties(ties, Tr - 1e-7) if ties else []
        if kind == "clear":
            _, k, s, xr = tag
            t = cont[k]
            return self.invariant([t.l, State(s, xr), t.r], Tr, "eutectic")
        if kind == "clearC":
            _, k, c, _ = tag
            t = cont[k]
            return self.invariant([t.l, State(c, c.x), t.r], Tr, "eutectic")
        if kind == "width":
            _, kp, kn, ph = tag
            a, b = cont[kp], cont[kn]
            return self.invariant([a.l, State(ph, 0.5 * (a.r.x + b.l.x)), b.r], Tr, "peritectic")
        if kind == "vertex":
            _, kp, kn, c = tag
            a, b = cont[kp], cont[kn]
            return self.invariant([a.l, State(c, c.x), b.r], Tr, "peritectic")
        if kind == "open":
            _, ph, s, xr, kp, kn = tag
            if xr <= XG[0] or xr >= XG[-1]:
                ptag = ("pureA", s) if xr <= XG[0] else ("pureB", s)
                return dict(kind="pure", T=self.pure_transition(ties, sole, T0, ptag))
            x, T = self.tangency(ph, s, xr, Tr)
            return dict(kind="congruent", T=T, x=x, above=s, below=ph, side="above")
        if kind == "openC":
            _, ph, c, kp, kn = tag
            T = self.compound_touch(ph, c, Tr)
            return dict(kind="congruent", T=T, x=c.x, above=c, below=ph, side="above")
        if kind == "gap":
            _, ph, xr, kp, kn = tag
            x, T = self.critical(ph, xr, Tr)
            return dict(kind="critical", T=T, x=x, phase=ph, side="above")
        raise NewtonFailure(f"unknown indicator {kind}")

    @staticmethod
    def signature(ties, sole):
        return tuple(t.sig() for t in ties) if ties else (("sole", sole.i),)

    # ------------------------------------------------------------ driver
    def advance(self, T_event, T_prev):
        """Temperature at which the structure is rebuilt after an event."""
        if not T_prev - 1e-6 <= T_event:
            raise NewtonFailure(f"event at {T_event} before the current temperature {T_prev}")
        T = T_event + EPS
        if T >= self.T_hi:
            raise NewtonFailure(f"event at {T_event} too close to the window end")
        if any(T_event - 1e-9 <= c <= T for c in self.isotherms):
            raise NewtonFailure(f"event at {T_event} within {EPS} K of an isotherm")
        return T

    def solve(self):
        anchors = {}
        ties, sole = self.certified(self.T_lo)
        T, h = self.T_lo, STEP
        events = []
        checkpoints = sorted(set(self.isotherms))
        while T < self.T_hi:
            nxt = [c for c in checkpoints if c > T]
            T1 = min(T + h, self.T_hi, nxt[0] if nxt else self.T_hi)
            # pure end-member transitions are known analytically; cross them without continuing
            # the tie-lines, which lose their dilute end there
            Tp = self.next_pure(ties, sole, T)
            if Tp is not None and Tp <= T1 + 1e-2:
                events.append(dict(kind="pure", T=Tp))
                T, h = self.advance(Tp, T), EPS
                ties, sole = self.certified(T)
                continue
            try:
                cont = self.continue_ties(ties, T1)
                fired = [(v, tag) for v, tag in self.indicators(cont, T1, sole) if v < 0]
            except NewtonFailure as error:
                # a tie-line of a lens, a compound lens or a miscibility gap degenerates as it
                # closes; the closing indicators need no tie-lines
                ev = self.closing_only(ties, sole, T, T1)
                if ev is None:
                    if h > 1e-3:
                        h *= 0.5
                        continue
                    raise NewtonFailure(f"continuation failed ({error}) without a closing event in ({T}, {T1}]")
                events.append(ev)
                T, h = self.advance(ev["T"], T), EPS
                ties, sole = self.certified(T)
                continue
            if fired:
                ev = self.solve_event(ties, sole, T, T1, fired)
                if not (T - 1e-6 <= ev["T"] <= T1 + 1e-3):
                    raise NewtonFailure(f"event at {ev['T']} outside bracket ({T}, {T1})")
                events.append(ev)
                T, h = self.advance(ev["T"], T), EPS
                ties, sole = self.certified(T)
                continue
            ties, T = cont, T1
            h = min(2 * h, STEP)
            if T in checkpoints:
                cert, csole = self.certified(T)
                if self.signature(cert, csole) != self.signature(ties, sole):
                    raise NewtonFailure(f"continued structure disagrees with the certified hull at T={T}")
                anchors[T] = (cert, csole)
        cert, csole = self.certified(self.T_hi)
        if self.signature(cert, csole) != self.signature(ties, sole):
            raise NewtonFailure("continued structure disagrees with the certified hull at T_hi")
        return anchors, events

    def margin(self, ties, sole, T):
        """Smallest height above the hull of any solution phase that is stable nowhere at T and
        of any compound that is not a hull vertex at T (guarantee 2 of the spec)."""
        h = self.hull_values(ties, T, XG, sole)
        stable = {ph for ph, _, _, _, _ in self.regions(ties, T, sole)} | {st.ph for t in ties for st in (t.l, t.r)}
        best = math.inf
        for s in self.sols:
            if s not in stable:
                best = min(best, float(np.min(s.G(XG, T) - h)))
        for c in self.comps:
            if c not in stable:
                best = min(best, c.G(T) - float(self.hull_values(ties, T, np.array([c.x]), sole)[0]))
        return best

    def report(self):
        anchors, events = self.solve()
        iso = []
        for T in self.isotherms:
            ties, sole = anchors[T] if T in anchors else self.certified(T)
            regs = [dict(phase=ph.name, x_lo=lo, x_hi=hi) for ph, lo, hi, _, _ in self.regions(ties, T, sole)]
            tl = [dict(left_phase=t.l.ph.name, x_left=t.l.x, right_phase=t.r.ph.name, x_right=t.r.x) for t in ties]
            iso.append(dict(temperature_K=T, single_phase_regions=regs, tie_lines=tl))
        inv = sorted((e for e in events if e["kind"] == "invariant"), key=lambda e: e["T"])
        con = sorted((e for e in events if e["kind"] == "congruent"), key=lambda e: e["T"])
        cri = sorted((e for e in events if e["kind"] == "critical"), key=lambda e: e["T"])
        return dict(
            system_id=self.id,
            isotherms=iso,
            invariants=[dict(temperature_K=e["T"], **{"class": e["cls"]}, name=e["name"],
                             phases=[dict(phase=s.ph.name, x=s.x) for s in e["states"]]) for e in inv],
            congruent_points=[dict(temperature_K=e["T"], x=e["x"], phase_above=e["above"].name,
                                   phase_below=e["below"].name, two_phase_side=e["side"]) for e in con],
            critical_points=[dict(temperature_K=e["T"], x=e["x"], phase=e["phase"].name, gap_side=e["side"]) for e in cri],
        )


def solve(d):
    return System(d).report()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    with open(a.system, encoding="utf-8") as fh:
        d = json.load(fh)
    rep = solve(d)
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
