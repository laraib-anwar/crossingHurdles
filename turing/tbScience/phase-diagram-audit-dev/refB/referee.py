#!/usr/bin/env python
"""Reference B: an independent high-precision referee for phase-diagram reports.

    python referee.py --system S.json --report R.json [--out verdict.json]
    python referee.py --solve --system S.json --output R.json

The referee certifies a report against PHASE_SPEC.md with its own machinery:
dense lower-convex-hull construction (Andrew monotone chain on a pointwise
envelope of all phases), Newton refinement of every equilibrium condition in
80-bit long double, global stability checks on a ~200k-point composition grid,
and an independent temperature scan with bisection and Newton polishing to find
every topology change of the diagram.  It shares no code with any solver that
produced the report.
"""
import argparse
import ctypes
import json
import math
import os
import subprocess
import sys
import time

import numpy as np

R_GAS = 8.314462618
LD = np.longdouble
HERE = os.path.dirname(os.path.abspath(__file__))

# thresholds of the verdict
TOL_TANGENT = 1e-6      # J/mol, common-tangent / tangency residuals
TOL_STAB = 1e-6         # J/mol, global stability violations
TOL_T_REL = 1e-7        # relative, refined temperature vs reported
TOL_X = 1e-9            # absolute, compositions
TOL_SEQ = 1e-12         # shared boundaries of consecutive pieces
MATCH_T = 0.25          # K, matching topology changes to events
DEPTH_TOL = 1e-7        # J/mol, same-phase hull edge counted as a gap only if deeper
DT_SIDE = 0.1           # K, offset for class / side determination


# ----------------------------------------------------------------------------
# model
# ----------------------------------------------------------------------------
def _xlogx(x):
    pos = x > 0
    safe = np.where(pos, x, 1)
    return np.where(pos, safe * np.log(safe), 0 * x)


class Sol:
    """Solution phase; G = A(x) + T B(x) with analytic x-derivatives to order 4."""

    def __init__(self, d):
        self.name = d["name"]
        em = d["end_members"]
        self.hA, self.sA = float(em["A"]["h"]), float(em["A"]["s"])
        self.hB, self.sB = float(em["B"]["h"]), float(em["B"]["s"])
        self.a = [float(c["a"]) for c in d["redlich_kister"]]
        self.b = [float(c["b"]) for c in d["redlich_kister"]]
        self.is_liquid = self.name == "liquid"
        self.kind = "sol"

    def AB(self, x, nmax=0):
        """Lists A[n], B[n] (n = 0..nmax) with d^nG/dx^n = A[n] + T B[n]."""
        x = np.asarray(x)
        y = 1 - x
        u = 1 - 2 * x
        p = x * y
        a0, a1, a2 = self.a
        b0, b1, b2 = self.b
        qa = a0 + a1 * u + a2 * u * u
        qb = b0 + b1 * u + b2 * u * u
        qa1 = -2 * (a1 + 2 * a2 * u)
        qb1 = -2 * (b1 + 2 * b2 * u)
        qa2 = 8 * a2
        qb2 = 8 * b2
        A = [y * self.hA + x * self.hB + p * qa]
        B = [-(y * self.sA + x * self.sB) + R_GAS * (_xlogx(x) + _xlogx(y)) + p * qb]
        if nmax >= 1:
            with np.errstate(divide="ignore", invalid="ignore"):
                lx = np.log(x)
                ly = np.log(y)
                A.append(self.hB - self.hA + u * qa + p * qa1)
                B.append(-(self.sB - self.sA) + R_GAS * (lx - ly) + u * qb + p * qb1)
                if nmax >= 2:
                    A.append(-2 * qa + 2 * u * qa1 + p * qa2)
                    B.append(R_GAS * (1 / x + 1 / y) - 2 * qb + 2 * u * qb1 + p * qb2)
                if nmax >= 3:
                    A.append(-6 * qa1 + 3 * u * qa2)
                    B.append(R_GAS * (-1 / x ** 2 + 1 / y ** 2) - 6 * qb1 + 3 * u * qb2)
                if nmax >= 4:
                    A.append(-96 * a2 + 0 * x)
                    B.append(R_GAS * (2 / x ** 3 + 2 / y ** 3) - 96 * b2)
        return A, B

    def G(self, x, T, nmax=0):
        A, B = self.AB(x, nmax)
        return [A[n] + T * B[n] for n in range(nmax + 1)]

    def GA(self, T):
        return self.hA - self.sA * T

    def GB(self, T):
        return self.hB - self.sB * T


class Cmp:
    def __init__(self, d):
        self.name = d["name"]
        self.x = float(d["x_b"])
        self.h = float(d["h"])
        self.s = float(d["s"])
        self.is_liquid = False
        self.kind = "cmp"

    def G(self, T):
        return self.h - self.s * T


class System:
    def __init__(self, d):
        self.raw = d
        self.id = d["system_id"]
        self.sols = [Sol(p) for p in d["solution_phases"]]
        self.cmps = [Cmp(c) for c in d["compounds"]]
        self.by_name = {p.name: p for p in self.sols}
        self.by_name.update({c.name: c for c in self.cmps})
        self.T_lo, self.T_hi = [float(v) for v in d["window_K"]]
        self.isotherms = [float(v) for v in d["isotherms_K"]]

    def phase(self, name):
        return self.by_name.get(name)

    def is_liquid(self, name):
        return name == "liquid"


# ----------------------------------------------------------------------------
# hull machinery
# ----------------------------------------------------------------------------
_LIB = None


def _load_lib():
    """Compile (once) and load the C monotone chain; None if unavailable."""
    global _LIB
    if _LIB is not None:
        return _LIB if _LIB else None
    src = os.path.join(HERE, "hull_chain.c")
    build = os.path.join(HERE, "_build")
    so = os.path.join(build, "hull_chain.so")
    try:
        if not os.path.exists(so) or os.path.getmtime(so) < os.path.getmtime(src):
            os.makedirs(build, exist_ok=True)
            subprocess.run(["cc", "-O2", "-shared", "-fPIC", "-o", so, src], check=True,
                           capture_output=True)
        lib = ctypes.CDLL(so)
        lib.lower_hull_d.restype = ctypes.c_long
        lib.lower_hull_d.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p]
        _LIB = lib
    except Exception:
        _LIB = False
    return _LIB if _LIB else None


def lower_hull(x, g):
    """Indices of the lower convex hull vertices of points sorted by x (float64 in)."""
    x = np.ascontiguousarray(x, dtype=np.float64)
    g = np.ascontiguousarray(g, dtype=np.float64)
    n = len(x)
    lib = _load_lib()
    if lib is not None:
        out = np.empty(n, dtype=np.int64)
        m = lib.lower_hull_d(x.ctypes.data, g.ctypes.data, n, out.ctypes.data)
        return out[:m]
    xl = [LD(v) for v in x]
    gl = [LD(v) for v in g]
    st = []
    for i in range(n):
        while len(st) >= 2:
            a, b = st[-2], st[-1]
            cr = (xl[b] - xl[a]) * (gl[i] - gl[a]) - (gl[b] - gl[a]) * (xl[i] - xl[a])
            if cr <= 0:
                st.pop()
            else:
                break
        st.append(i)
    return np.array(st, dtype=np.int64)


def make_x(n_uniform, per_decade):
    geo = np.logspace(-9, -3, 6 * per_decade + 1)
    x = np.concatenate([np.linspace(0.0, 1.0, n_uniform), geo, 1.0 - geo])
    return np.unique(x)


class Grid:
    """Composition grid with T-independent parts of every phase precomputed."""

    def __init__(self, sysm, n_uniform, per_decade, dtype=np.float64):
        self.sysm = sysm
        self.x = make_x(n_uniform, per_decade).astype(dtype)
        self.n = len(self.x)
        self.h = 1.0 / (n_uniform - 1)
        self.A = []
        self.B = []
        for p in sysm.sols:
            A, B = p.AB(self.x, 0)
            self.A.append(A[0])
            self.B.append(B[0])
        self.A = np.array(self.A)
        self.B = np.array(self.B)
        # second-derivative parts for the spinodal test (infinite at the pure ends)
        A2, B2 = [], []
        with np.errstate(divide="ignore", invalid="ignore"):
            for p in sysm.sols:
                A, B = p.AB(self.x, 2)
                A2.append(np.where(np.isfinite(A[2]), A[2], np.inf))
                B2.append(np.where(np.isfinite(B[2]), B[2], 0.0))
        self.A2 = np.array(A2)
        self.B2 = np.array(B2)
        xc = np.array([c.x for c in sysm.cmps], dtype=np.float64)
        allx = np.concatenate([self.x.astype(np.float64), xc])
        self.order = np.argsort(allx, kind="stable")
        self.px = allx[self.order]
        kind = np.concatenate([np.zeros(self.n, dtype=np.int64), np.ones(len(xc), dtype=np.int64)])
        self.pkind = kind[self.order]
        idx = np.concatenate([np.arange(self.n), np.arange(len(xc))])
        self.pidx = idx[self.order]

    def envelope(self, T):
        """Pointwise minimum over solution phases and its argmin, plus compound values."""
        G = self.A + T * self.B
        arg = np.argmin(G, axis=0)
        E = G[arg, np.arange(self.n)]
        Gc = np.array([c.G(T) for c in self.sysm.cmps], dtype=np.float64)
        return G, E, arg, Gc

    def all_G(self, T):
        return self.A + T * self.B

    def spinodal_min(self, T, pieces):
        """For each solution phase: minimum of the second derivative over the grid points of its
        stable support (its regions plus its own-phase gaps) as (min, x_at_min); None when the
        phase is not stable at T."""
        out = {}
        for k, p in enumerate(self.sysm.sols):
            mask = np.zeros(self.n, dtype=bool)
            for pc in pieces:
                if pc.kind == "R" and pc.phase == p.name:
                    mask |= (self.x >= pc.lo) & (self.x <= pc.hi)
                elif pc.kind == "T" and pc.pl == p.name and pc.pr == p.name:
                    mask |= (self.x >= pc.xl) & (self.x <= pc.xr)
            mask &= (self.x > 0) & (self.x < 1)
            if not mask.any():
                out[p.name] = None
                continue
            g2 = np.where(mask, self.A2[k] + T * self.B2[k], np.inf)
            j = int(np.argmin(g2))
            out[p.name] = (float(g2[j]), float(self.x[j]))
        return out


class Piece:
    __slots__ = ("kind", "phase", "lo", "hi", "pl", "xl", "pr", "xr", "refined")

    def __init__(self, kind, **kw):
        self.kind = kind
        for k in ("phase", "lo", "hi", "pl", "xl", "pr", "xr"):
            setattr(self, k, kw.get(k))
        self.refined = kw.get("refined", True)

    def label(self):
        if self.kind == "R":
            return "R:" + self.phase
        if self.kind == "T":
            return "T:%s|%s" % (self.pl, self.pr)
        return "V:" + self.phase

    def start(self):
        return self.lo if self.kind == "R" else (self.xl if self.kind == "T" else self.lo)

    def end(self):
        return self.hi if self.kind == "R" else (self.xr if self.kind == "T" else self.hi)

    def width(self):
        return self.end() - self.start()

    def __repr__(self):
        return "%s[%.6g,%.6g]" % (self.label(), self.start(), self.end())


def hull_pieces(sysm, T, grid, refine=True):
    """Hull at T as a list of Pieces (regions R, ties T, compound vertices V)."""
    G, E, arg, Gc = grid.envelope(T)
    pg = np.concatenate([E, Gc])[grid.order]
    v = lower_hull(grid.px, pg)
    vk = grid.pkind[v]
    vi = grid.pidx[v]
    vphase = np.where(vk == 0, arg[np.minimum(vi, grid.n - 1)], -1)
    i, j = v[:-1], v[1:]
    same = (vk[:-1] == 0) & (vk[1:] == 0) & (vphase[:-1] == vphase[1:])
    adj = same & (vi[1:] - vi[:-1] == 1)
    cand = np.nonzero(~adj)[0]
    names = [p.name for p in sysm.sols]
    cnames = [c.name for c in sysm.cmps]
    tie_edges = []
    for e in cand:
        if same[e]:
            ga, gb = vi[e], vi[e + 1]
            xa, xb = grid.x[ga], grid.x[gb]
            ya, yb = E[ga], E[gb]
            xs = grid.x[ga + 1:gb]
            line = ya + (yb - ya) * (xs - xa) / (xb - xa)
            depth = float(np.max(E[ga + 1:gb] - line)) if len(xs) else 0.0
            if depth < DEPTH_TOL:
                continue
        tie_edges.append(e)

    def state(k):
        if vk[k] == 0:
            return ("sol", names[vphase[k]], float(grid.x[vi[k]]))
        return ("cmp", cnames[vi[k]], float(grid.px[v[k]]))

    pieces = []
    flags = []
    first = state(0)
    if first[0] != "sol" or first[2] != 0.0:
        flags.append("hull does not start with a solution region at x=0")
    cur_phase = first[1] if first[0] == "sol" else None
    prev_right = 0.0
    for e in tie_edges:
        sl, sr = state(e), state(e + 1)
        xl, xr, ok = sl[2], sr[2], True
        if refine:
            xl, xr, ok = refine_tie(sysm, sl, sr, T)
        if sl[0] == "sol":
            if cur_phase is None:
                flags.append("tie starts on a solution phase after a compound vertex")
                cur_phase = sl[1]
            if xl < prev_right - 1e-15:
                flags.append("negative-width region %s at x=%.9g" % (cur_phase, xl))
            pieces.append(Piece("R", phase=cur_phase, lo=prev_right, hi=xl))
        else:
            pieces.append(Piece("V", phase=sl[1], lo=xl, hi=xl))
        pieces.append(Piece("T", pl=sl[1], xl=xl, pr=sr[1], xr=xr, refined=ok))
        if sr[0] == "sol":
            cur_phase = sr[1]
            prev_right = xr
        else:
            cur_phase = None
            prev_right = xr
    if cur_phase is not None:
        pieces.append(Piece("R", phase=cur_phase, lo=prev_right, hi=1.0))
    else:
        flags.append("hull ends on a compound vertex")
    # drop leading vertex duplicates: a V piece is only emitted before a tie whose left end is a
    # compound; it then sits between the two ties sharing that compound, as intended.
    pieces = [p for k, p in enumerate(pieces) if not (p.kind == "V" and (k == 0 or pieces[k - 1].kind != "T"))]
    return pieces, flags


def labels(pieces):
    return tuple(p.label() for p in pieces)


# ----------------------------------------------------------------------------
# Newton refinements (long double)
# ----------------------------------------------------------------------------
def _solve(J, F):
    """Gaussian elimination with partial pivoting in long double."""
    n = len(F)
    M = np.array(J, dtype=LD).reshape(n, n)
    b = np.array(F, dtype=LD).reshape(n)
    for c in range(n):
        piv = c + int(np.argmax(np.abs(M[c:, c])))
        if M[piv, c] == 0:
            return None
        if piv != c:
            M[[c, piv]] = M[[piv, c]]
            b[[c, piv]] = b[[piv, c]]
        for r in range(c + 1, n):
            f = M[r, c] / M[c, c]
            if f != 0:
                M[r, c:] -= f * M[c, c:]
                b[r] -= f * b[c]
    xsol = np.zeros(n, dtype=LD)
    for c in range(n - 1, -1, -1):
        xsol[c] = (b[c] - np.dot(M[c, c + 1:], xsol[c + 1:])) / M[c, c]
    return xsol


class _Conv:
    """Noise-floor-aware convergence test for Newton iterations in long double.

    Converged when the step is below tight tolerances (1e-15 in x, 1e-13 relative in T), or when
    two successive steps are already tiny (1e-12 in x, 1e-10 relative in T) but no longer shrink,
    which is the rounding floor of the residual (for example the third derivative near a critical
    point, where the x step is noise(G3)/G4)."""

    def __init__(self):
        self.prev = None

    def __call__(self, dx, dT, T):
        dx = abs(float(dx))
        dT = abs(float(dT)) / max(1.0, abs(float(T)))
        if dx < 1e-15 and dT < 1e-13:
            return True
        if self.prev is not None:
            pdx, pdT = self.prev
            if dx < 1e-12 and dT < 1e-10 and (dx >= 0.5 * pdx or dT >= 0.5 * pdT):
                return True
        self.prev = (dx, dT)
        return False


def _step_limit(d, lim):
    m = float(np.max(np.abs(d))) if np.size(d) else 0.0
    return d * (lim / m) if m > lim else d


def refine_tie(sysm, sl, sr, T, max_iter=80):
    """Newton on the common-tangent equations for one tie-line. Returns (xl, xr, converged)."""
    T = LD(T)
    P = sysm.phase(sl[1])
    Q = sysm.phase(sr[1])
    if sl[0] == "cmp" and sr[0] == "cmp":
        return sl[2], sr[2], True
    if sl[0] == "cmp" or sr[0] == "cmp":
        if sl[0] == "sol":
            S, xs, C = P, LD(sl[2]), Q
        else:
            S, xs, C = Q, LD(sr[2]), P
        xc, Gc = LD(C.x), LD(C.G(T))
        ok = False
        conv = _Conv()
        for _ in range(max_iter):
            g = S.G(xs, T, 2)
            F = g[0] + g[1] * (xc - xs) - Gc
            dF = g[2] * (xc - xs)
            if dF == 0:
                break
            d = _step_limit(np.array([-F / dF], dtype=LD), 0.02)[0]
            xs = xs + d
            if not (0 < xs < 1):
                return sl[2], sr[2], False
            if conv(d, 0.0, 1.0):
                ok = True
                break
        if sl[0] == "sol":
            return float(xs), float(xc), ok
        return float(xc), float(xs), ok
    xl, xr = LD(sl[2]), LD(sr[2])
    # a tie edge can start at the x=0 (or end at the x=1) grid vertex when the terminal region
    # is narrower than the grid; start Newton just inside instead
    xl = max(xl, LD(1e-9))
    xr = min(xr, LD(1) - LD(1e-9))
    ok = False
    conv = _Conv()
    for _ in range(max_iter):
        gl = P.G(xl, T, 2)
        gr = Q.G(xr, T, 2)
        F1 = (gl[0] - xl * gl[1]) - (gr[0] - xr * gr[1])
        F2 = (gl[0] + (1 - xl) * gl[1]) - (gr[0] + (1 - xr) * gr[1])
        J = [[-xl * gl[2], xr * gr[2]], [(1 - xl) * gl[2], -(1 - xr) * gr[2]]]
        d = _solve(J, [-F1, -F2])
        if d is None or not np.all(np.isfinite(d)):
            return sl[2], sr[2], False
        d = _step_limit(d, 0.02)
        xl, xr = xl + d[0], xr + d[1]
        if not (0 < xl < 1 and 0 < xr < 1) or xl >= xr:
            return sl[2], sr[2], False
        if conv(float(np.max(np.abs(d))), 0.0, 1.0):
            ok = True
            break
    return float(xl), float(xr), ok


def tie_residuals(sysm, pl, xl, pr, xr, T):
    """Common-tangent residuals in J/mol at the reported values (long double)."""
    T = LD(T)
    P, Q = sysm.phase(pl), sysm.phase(pr)
    if P.kind == "cmp" and Q.kind == "cmp":
        return {"type": "compound-compound"}
    if P.kind == "cmp" or Q.kind == "cmp":
        S, xs, C = (P, LD(xl), Q) if P.kind == "sol" else (Q, LD(xr), P)
        g = S.G(xs, T, 1)
        res = g[0] + g[1] * (LD(C.x) - xs) - LD(C.G(T))
        return {"type": "solution-compound", "tangent_through_compound": float(res), "max": abs(float(res))}
    gl, gr = P.G(LD(xl), T, 1), Q.G(LD(xr), T, 1)
    muA = (gl[0] - LD(xl) * gl[1]) - (gr[0] - LD(xr) * gr[1])
    muB = (gl[0] + (1 - LD(xl)) * gl[1]) - (gr[0] + (1 - LD(xr)) * gr[1])
    return {"type": "solution-solution", "mu_A": float(muA), "mu_B": float(muB),
            "max": max(abs(float(muA)), abs(float(muB)))}


def refine_invariant(sysm, states, T0, max_iter=80):
    """Newton on the full three-phase system: unknowns x (solution states), T, slope, intercept."""
    phs = [sysm.phase(n) for n, _ in states]
    xs = [LD(x) for _, x in states]
    T = LD(T0)
    sol_idx = [k for k, p in enumerate(phs) if p.kind == "sol"]
    g0 = [p.G(xs[k], T, 0)[0] if p.kind == "sol" else LD(p.G(T)) for k, p in enumerate(phs)]
    m = (g0[2] - g0[0]) / (xs[2] - xs[0])
    c = g0[0] - m * xs[0]
    conv = _Conv()
    for _ in range(max_iter):
        F, J = [], []
        nu = len(sol_idx) + 3
        col = {k: i for i, k in enumerate(sol_idx)}
        for k, p in enumerate(phs):
            row = [LD(0)] * nu
            if p.kind == "sol":
                A, B = p.AB(xs[k], 2)
                g = [A[n] + T * B[n] for n in range(3)]
                F.append(g[0] - m * xs[k] - c)
                row[col[k]] = g[1]
                row[-3] = B[0]
                row[-2] = -xs[k]
                row[-1] = LD(-1)
                J.append(row)
                row2 = [LD(0)] * nu
                F.append(g[1] - m)
                row2[col[k]] = g[2]
                row2[-3] = B[1]
                row2[-2] = LD(-1)
                J.append(row2)
            else:
                F.append(LD(p.G(T)) - m * xs[k] - c)
                row[-3] = LD(-p.s)
                row[-2] = -xs[k]
                row[-1] = LD(-1)
                J.append(row)
        d = _solve(J, [-f for f in F])
        if d is None or not np.all(np.isfinite(d)):
            return None
        dx = d[:len(sol_idx)]
        if len(dx):
            fac = min(1.0, 0.02 / max(1e-300, float(np.max(np.abs(dx)))))
        else:
            fac = 1.0
        fac = min(fac, 2.0 / max(1e-300, abs(float(d[-3]))))
        for i, k in enumerate(sol_idx):
            xs[k] = xs[k] + fac * d[i]
            if not (0 < xs[k] < 1):
                return None
        T = T + fac * d[-3]
        m = m + fac * d[-2]
        c = c + fac * d[-1]
        if T <= 0:
            return None
        if fac == 1.0 and conv(float(np.max(np.abs(dx))) if len(dx) else 0.0, d[-3], T):
            if not (xs[0] < xs[1] < xs[2]):
                return None
            return {"T": float(T), "x": [float(v) for v in xs], "m": float(m), "c": float(c)}
    return None


def refine_congruent(sysm, P, Q, x0, T0, max_iter=80):
    """Tangency of two solution curves (unknowns x, T) or compound touching a curve (T only)."""
    P, Q = sysm.phase(P), sysm.phase(Q)
    if P.kind == "cmp" and Q.kind == "cmp":
        return None
    if P.kind == "cmp" or Q.kind == "cmp":
        S, C = (P, Q) if P.kind == "sol" else (Q, P)
        A, B = S.AB(LD(C.x), 0)
        den = B[0] + LD(C.s)
        if den == 0:
            return None
        T = (LD(C.h) - A[0]) / den
        return {"T": float(T), "x": float(C.x)}
    x, T = LD(x0), LD(T0)
    conv = _Conv()
    for _ in range(max_iter):
        Ap, Bp = P.AB(x, 2)
        Aq, Bq = Q.AB(x, 2)
        g = [(Ap[n] - Aq[n]) + T * (Bp[n] - Bq[n]) for n in range(3)]
        F = [g[0], g[1]]
        J = [[g[1], Bp[0] - Bq[0]], [g[2], Bp[1] - Bq[1]]]
        d = _solve(J, [-F[0], -F[1]])
        if d is None or not np.all(np.isfinite(d)):
            return None
        fac = min(1.0, 0.02 / max(1e-300, abs(float(d[0]))), 2.0 / max(1e-300, abs(float(d[1]))))
        x, T = x + fac * d[0], T + fac * d[1]
        if not (0 < x < 1) or T <= 0:
            return None
        if fac == 1.0 and conv(d[0], d[1], T):
            return {"T": float(T), "x": float(x)}
    return None


def refine_critical(sysm, P, x0, T0, max_iter=80):
    P = sysm.phase(P)
    if P.kind != "sol":
        return None
    x, T = LD(x0), LD(T0)
    conv = _Conv()
    for _ in range(max_iter):
        A, B = P.AB(x, 4)
        g = [A[n] + T * B[n] for n in range(5)]
        J = [[g[3], B[2]], [g[4], B[3]]]
        d = _solve(J, [-g[2], -g[3]])
        if d is None or not np.all(np.isfinite(d)):
            return None
        fac = min(1.0, 0.02 / max(1e-300, abs(float(d[0]))), 2.0 / max(1e-300, abs(float(d[1]))))
        x, T = x + fac * d[0], T + fac * d[1]
        if not (0 < x < 1) or T <= 0:
            return None
        if fac == 1.0 and conv(d[0], d[1], T):
            return {"T": float(T), "x": float(x)}
    return None


# ----------------------------------------------------------------------------
# stability on the fine grid (long double)
# ----------------------------------------------------------------------------
class FineGrid:
    def __init__(self, sysm, n_uniform=200001, per_decade=50):
        self.sysm = sysm
        self.x = make_x(n_uniform, per_decade).astype(LD)
        self.n = len(self.x)
        self.AB = [p.AB(self.x, 2) for p in sysm.sols]

    def G(self, T, nmax=0):
        T = LD(T)
        return [[A[n] + T * B[n] for n in range(nmax + 1)] for A, B in self.AB]


def line_violation(sysm, fine, T, m, c):
    """Largest amount by which any phase lies below the line m x + c (positive = violation)."""
    m, c, T = LD(m), LD(c), LD(T)
    line = m * fine.x + c
    worst, where = -np.inf, None
    for p, Gs in zip(sysm.sols, fine.G(T, 0)):
        d = line - Gs[0]
        k = int(np.argmax(d))
        if d[k] > worst:
            worst, where = float(d[k]), {"phase": p.name, "x": float(fine.x[k])}
    for cmp_ in sysm.cmps:
        d = float(m * LD(cmp_.x) + c - LD(cmp_.G(T)))
        if d > worst:
            worst, where = d, {"phase": cmp_.name, "x": cmp_.x}
    return worst, where


def state_G(sysm, name, x, T):
    p = sysm.phase(name)
    if p.kind == "cmp":
        return LD(p.G(LD(T)))
    return p.G(LD(x), LD(T), 0)[0]


def hull_violation(sysm, fine, T, regions, ties):
    """Evaluate the reported hull on the fine grid; return worst (hull - phase) over all phases."""
    T = LD(T)
    H = np.full(fine.n, np.inf, dtype=LD)
    Gs = fine.G(T, 0)
    idx = {p.name: k for k, p in enumerate(sysm.sols)}
    for r in regions:
        msk = (fine.x >= r["x_lo"]) & (fine.x <= r["x_hi"])
        H[msk] = Gs[idx[r["phase"]]][0][msk]
    for t in ties:
        xl, xr = LD(t["x_left"]), LD(t["x_right"])
        gl = state_G(sysm, t["left_phase"], t["x_left"], T)
        gr = state_G(sysm, t["right_phase"], t["x_right"], T)
        msk = (fine.x >= xl) & (fine.x <= xr)
        H[msk] = gl + (gr - gl) * (fine.x[msk] - xl) / (xr - xl)
    uncovered = int(np.sum(~np.isfinite(H)))
    worst, where = -np.inf, None
    for p, G in zip(sysm.sols, Gs):
        d = np.where(np.isfinite(H), H - G[0], -np.inf)
        k = int(np.argmax(d))
        if d[k] > worst:
            worst, where = float(d[k]), {"phase": p.name, "x": float(fine.x[k])}
    for c in sysm.cmps:
        hx = None
        for r in regions:
            if r["x_lo"] <= c.x <= r["x_hi"]:
                hx = sysm.phase(r["phase"]).G(LD(c.x), T, 0)[0]
        for t in ties:
            if t["x_left"] <= c.x <= t["x_right"]:
                gl = state_G(sysm, t["left_phase"], t["x_left"], T)
                gr = state_G(sysm, t["right_phase"], t["x_right"], T)
                hx = gl + (gr - gl) * (LD(c.x) - LD(t["x_left"])) / (LD(t["x_right"]) - LD(t["x_left"]))
        if hx is not None:
            d = float(hx - LD(c.G(T)))
            if d > worst:
                worst, where = d, {"phase": c.name, "x": c.x}
    return worst, where, uncovered


# ----------------------------------------------------------------------------
# items helpers for class / side determination
# ----------------------------------------------------------------------------
def piece_containing(pieces, x):
    """Index of the piece holding composition x: a compound vertex at x wins over the ties
    meeting there, a region wins over a tie at a shared boundary."""
    for k, p in enumerate(pieces):
        if p.kind == "V" and abs(p.lo - x) <= 1e-12:
            return k
    for k, p in enumerate(pieces):
        if p.kind == "R" and p.lo - 1e-15 <= x <= p.hi + 1e-15:
            return k
    for k, p in enumerate(pieces):
        if p.kind == "T" and p.xl - 1e-15 <= x <= p.xr + 1e-15:
            return k
    return None


def middle_stable_near(pieces, P2, x2, d):
    for p in pieces:
        if p.kind == "R" and p.phase == P2 and p.lo - d <= x2 <= p.hi + d:
            return True
        if p.kind == "V" and p.phase == P2 and abs(p.lo - x2) <= d:
            return True
        if p.kind == "T":
            if p.pl == P2 and abs(p.xl - x2) <= d:
                return True
            if p.pr == P2 and abs(p.xr - x2) <= d:
                return True
    return False


def outer_tie_covers(pieces, P1, P3, x1, x2, x3):
    for p in pieces:
        if p.kind == "T" and p.pl == P1 and p.pr == P3 and p.xl <= x2 <= p.xr:
            if abs(p.xl - x1) < 0.5 * (x2 - x1) + 1e-9 and abs(p.xr - x3) < 0.5 * (x3 - x2) + 1e-9:
                return True
    return False


def invariant_name(cls, P1, P2, P3, sysm):
    l1, l2, l3 = sysm.is_liquid(P1), sysm.is_liquid(P2), sysm.is_liquid(P3)
    nliq_outer = int(l1) + int(l3)
    if cls == "eutectic":
        if l2:
            return "eutectic" if nliq_outer == 0 else ("monotectic" if nliq_outer == 1 else None)
        return "eutectoid" if nliq_outer == 0 else "metatectic"
    if cls == "peritectic":
        if l2:
            return "inverse_monotectic"
        return {1: "peritectic", 2: "syntectic", 0: "peritectoid"}[nliq_outer]
    return None


def classify_invariant(sysm, grid, T, P1, x1, P2, x2, P3, x3):
    d = 0.5 * min(x2 - x1, x3 - x2)
    out = {}
    for side, Ts in (("above", T + DT_SIDE), ("below", T - DT_SIDE)):
        pcs, _ = hull_pieces(sysm, Ts, grid, refine=True)
        out["middle_stable_" + side] = middle_stable_near(pcs, P2, x2, d)
        out["outer_tie_covers_" + side] = outer_tie_covers(pcs, P1, P3, x1, x2, x3)
    a, b = out["middle_stable_above"], out["middle_stable_below"]
    if a and not b:
        cls = "eutectic"
    elif b and not a:
        cls = "peritectic"
    else:
        cls = None
    ca, cb = out["outer_tie_covers_above"], out["outer_tie_covers_below"]
    consistent = (cls == "eutectic" and cb and not ca) or (cls == "peritectic" and ca and not cb)
    out["class"] = cls
    out["outer_tie_consistent"] = bool(consistent)
    out["name"] = invariant_name(cls, P1, P2, P3, sysm) if cls else None
    return out


def congruent_sides(sysm, grid, T, x, P, Q):
    """Which side holds the two-phase lens of {P, Q}; phase stable at x on each side."""
    pair = {P, Q}
    out = {}
    for side, Ts in (("above", T + DT_SIDE), ("below", T - DT_SIDE)):
        pcs, _ = hull_pieces(sysm, Ts, grid, refine=True)
        k = piece_containing(pcs, x)
        if k is None:
            out["phase_" + side] = None
            out["lens_" + side] = False
            continue
        p = pcs[k]
        phase = p.phase if p.kind in ("R", "V") else None
        lens = False
        if p.kind in ("R", "V") and 0 < k < len(pcs) - 1:
            l, r = pcs[k - 1], pcs[k + 1]
            lens = (l.kind == "T" and r.kind == "T" and {l.pl, l.pr} == pair and {r.pl, r.pr} == pair)
        out["phase_" + side] = phase
        out["lens_" + side] = bool(lens)
    la, lb = out["lens_above"], out["lens_below"]
    out["two_phase_side"] = "above" if (la and not lb) else ("below" if (lb and not la) else None)
    return out


def critical_side(sysm, grid, T, x, P):
    out = {}
    for side, Ts in (("above", T + DT_SIDE), ("below", T - DT_SIDE)):
        pcs, _ = hull_pieces(sysm, Ts, grid, refine=True)
        k = piece_containing(pcs, x)
        p = pcs[k] if k is not None else None
        out["gap_" + side] = bool(p is not None and p.kind == "T" and p.pl == P and p.pr == P)
        out["region_" + side] = bool(p is not None and p.kind == "R" and p.phase == P)
    ga, gb = out["gap_above"], out["gap_below"]
    out["gap_side"] = "above" if (ga and not gb) else ("below" if (gb and not ga) else None)
    return out


# ----------------------------------------------------------------------------
# independent event finder: scan + bisection + classification + polishing
# ----------------------------------------------------------------------------
def pure_end_transitions(sysm):
    """Temperatures in the window where the stable phase at x=0 or x=1 changes."""
    out = []
    for end in ("A", "B"):
        hs = [(p.hA, p.sA) if end == "A" else (p.hB, p.sB) for p in sysm.sols]
        names = [p.name for p in sysm.sols]
        n = len(hs)
        for i in range(n):
            for j in range(i + 1, n):
                if hs[i][1] == hs[j][1]:
                    continue
                T = (hs[i][0] - hs[j][0]) / (hs[i][1] - hs[j][1])
                if not (sysm.T_lo < T < sysm.T_hi):
                    continue
                vals = [h - s * T for h, s in hs]
                vmin = min(vals)
                tol = 1e-9 * max(1.0, abs(vmin))
                if vals[i] - vmin <= tol and vals[j] - vmin <= tol:
                    lo = names[i] if hs[i][1] < hs[j][1] else names[j]   # smaller s is stable below
                    hi = names[j] if lo == names[i] else names[i]
                    out.append({"end": end, "T": T, "phase_below": lo, "phase_above": hi})
    out.sort(key=lambda e: e["T"])
    dedup = []
    for e in out:
        if not any(abs(e["T"] - f["T"]) < 1e-9 and e["end"] == f["end"] for f in dedup):
            dedup.append(e)
    return dedup


def _overlap(p, q, margin):
    return p.start() <= q.end() + margin and q.start() <= p.end() + margin


def _unmatched(rich, poor, margin):
    out = []
    for k, p in enumerate(rich):
        if not any(p.label() == q.label() and _overlap(p, q, margin) for q in poor):
            out.append(k)
    return out


def classify_change(sysm, grid, fine, Ta, Tb, pa, pb, pure_ends):
    """Interpret the topology change between hulls pa (at Ta) and pb (at Tb), Ta < Tb."""
    if len(pa) == len(pb):
        return {"kind": "unknown", "note": "same number of pieces on both sides",
                "labels_below": labels(pa), "labels_above": labels(pb)}
    rich, poor, rich_side = (pa, pb, "below") if len(pa) > len(pb) else (pb, pa, "above")
    T_rich = Ta if rich_side == "below" else Tb
    margin = 3 * grid.h
    um = _unmatched(rich, poor, margin)
    cands = [k for k in um if rich[k].kind in ("R", "V")]
    attempts = []
    if cands:
        k = min(cands, key=lambda i: rich[i].width())
        if k == 0 or k == len(rich) - 1:
            near = [e for e in pure_ends if Ta - 1.0 <= e["T"] <= Tb + 1.0]
            return {"kind": "pure_end", "end": "A" if k == 0 else "B", "piece": repr(rich[k]),
                    "analytic": near[0] if near else None}
        left, right = rich[k - 1], rich[k + 1]
        if left.kind == "T" and right.kind == "T":
            P1, x1 = left.pl, left.xl
            P2, x2 = rich[k].phase, 0.5 * (rich[k].start() + rich[k].end())
            P3, x3 = right.pr, right.xr
            tiny = left.width() < 1e-3 and right.width() < 1e-3
            if P1 == P3 and tiny:
                attempts += [("congruent", (P1, P2, x2)), ("invariant", (P1, x1, P2, x2, P3, x3))]
            else:
                attempts += [("invariant", (P1, x1, P2, x2, P3, x3))]
                if P1 == P3:
                    attempts.append(("congruent", (P1, P2, x2)))
    tie_cands = [k for k in um if rich[k].kind == "T" and rich[k].pl == rich[k].pr]
    for k in tie_cands:
        attempts.append(("critical", (rich[k].pl, 0.5 * (rich[k].xl + rich[k].xr))))
    for kind, args in attempts:
        ev = polish_event(sysm, grid, fine, kind, args, T_rich)
        if ev is None:
            continue
        if not (Ta - 0.1 <= ev["temperature_K"] <= Tb + 0.1):
            continue
        if ev.get("stability_violation", 0.0) > 1e-4:
            continue
        ev["rich_side"] = rich_side
        return ev
    return {"kind": "unknown", "note": "no interpretation polished", "labels_below": labels(pa),
            "labels_above": labels(pb), "unmatched": [repr(rich[k]) for k in um]}


def polish_event(sysm, grid, fine, kind, args, T0):
    if kind == "invariant":
        P1, x1, P2, x2, P3, x3 = args
        res = refine_invariant(sysm, [(P1, x1), (P2, x2), (P3, x3)], T0)
        if res is None:
            return None
        viol, where = line_violation(sysm, fine, res["T"], res["m"], res["c"])
        cl = classify_invariant(sysm, grid, res["T"], P1, res["x"][0], P2, res["x"][1], P3, res["x"][2])
        return {"kind": "invariant", "temperature_K": res["T"], "class": cl["class"], "name": cl["name"],
                "phases": [{"phase": P1, "x": res["x"][0]}, {"phase": P2, "x": res["x"][1]},
                           {"phase": P3, "x": res["x"][2]}],
                "stability_violation": viol, "class_detail": cl}
    if kind == "congruent":
        P, Q, x0 = args
        res = refine_congruent(sysm, P, Q, x0, T0)
        if res is None:
            return None
        T, x = res["T"], res["x"]
        S = sysm.phase(P) if sysm.phase(P).kind == "sol" else sysm.phase(Q)
        g = S.G(LD(x), LD(T), 1)
        viol, where = line_violation(sysm, fine, T, g[1], g[0] - LD(x) * g[1])
        sd = congruent_sides(sysm, grid, T, x, P, Q)
        return {"kind": "congruent", "temperature_K": T, "x": x, "phase_above": sd["phase_above"],
                "phase_below": sd["phase_below"], "two_phase_side": sd["two_phase_side"],
                "stability_violation": viol, "pair": sorted([P, Q])}
    if kind == "critical":
        P, x0 = args
        res = refine_critical(sysm, P, x0, T0)
        if res is None:
            return None
        T, x = res["T"], res["x"]
        g = sysm.phase(P).G(LD(x), LD(T), 1)
        viol, where = line_violation(sysm, fine, T, g[1], g[0] - LD(x) * g[1])
        sd = critical_side(sysm, grid, T, x, P)
        return {"kind": "critical", "temperature_K": T, "x": x, "phase": P, "gap_side": sd["gap_side"],
                "stability_violation": viol}
    return None


def find_events(sysm, grid_scan, grid_topo, fine, step, log=None):
    """Scan the window, bisect every topology change, classify and polish it."""
    T_lo, T_hi = sysm.T_lo, sysm.T_hi
    nsteps = int(math.ceil((T_hi - T_lo) / step))
    Ts = np.linspace(T_lo, T_hi, nsteps + 1)
    t0 = time.time()
    labs = []
    spins = []
    for T in Ts:
        pcs, _ = hull_pieces(sysm, float(T), grid_scan, refine=False)
        labs.append(labels(pcs))
        spins.append(grid_scan.spinodal_min(float(T), pcs))
    scan_time = time.time() - t0
    pure = pure_end_transitions(sysm)
    changes = []
    events = []
    # critical points from the sign of min G'' over each phase's stable support (regions plus
    # own-phase gaps): negative exactly when a gap exists, so the sign flips at T_c itself, without
    # the lag of detecting a shallow gap on a sampled hull.  G'' is linear in T, so bisection is exact.
    spin_events = []
    for p in sysm.sols:
        for k in range(nsteps):
            fa, fb = spins[k].get(p.name), spins[k + 1].get(p.name)
            if fa is None or fb is None or fa[0] * fb[0] >= 0:
                continue
            Ta, Tb = float(Ts[k]), float(Ts[k + 1])
            va, vb = fa, fb

            def fval(T):
                pcs, _ = hull_pieces(sysm, T, grid_scan, refine=False)
                return grid_scan.spinodal_min(T, pcs).get(p.name)
            for _ in range(60):
                if Tb - Ta < 1e-9 * max(1.0, Ta):
                    break
                Tm = 0.5 * (Ta + Tb)
                vm = fval(Tm)
                if vm is None:
                    break
                if vm[0] * va[0] > 0:
                    Ta, va = Tm, vm
                else:
                    Tb, vb = Tm, vm
            rec = {"phase": p.name, "bracket_K": [Ta, Tb], "minG2_bracket": [va[0], vb[0]],
                   "x_at_min": 0.5 * (va[1] + vb[1]), "scan_interval_K": [float(Ts[k]), float(Ts[k + 1])]}
            # a continuous zero crossing has |min G''| ~ B2 * bracket width at both ends; a jump
            # (gap created by an invariant, not a consolute point) does not
            if abs(va[0]) + abs(vb[0]) > 1e-3:
                rec["kind"] = "spinodal_jump"
                spin_events.append(rec)
                continue
            ev = polish_event(sysm, grid_topo, fine, "critical", (p.name, rec["x_at_min"]), 0.5 * (Ta + Tb))
            if ev is None or abs(ev["temperature_K"] - 0.5 * (Ta + Tb)) > 1e-3 or ev.get("stability_violation", 0.0) > 1e-4:
                rec["kind"] = "unknown"
                rec["note"] = "spinodal zero crossing but critical polish failed"
                spin_events.append(rec)
                continue
            ev.update(rec)
            ev["detector"] = "spinodal"
            spin_events.append(ev)
            events.append(ev)
    for k in range(nsteps):
        if labs[k] == labs[k + 1]:
            continue
        Ta, Tb = float(Ts[k]), float(Ts[k + 1])
        pa, _ = hull_pieces(sysm, Ta, grid_topo, refine=False)
        pb, _ = hull_pieces(sysm, Tb, grid_topo, refine=False)
        la, lb = labels(pa), labels(pb)
        g = grid_topo if la != lb else grid_scan
        if la == lb:
            la, lb = labs[k], labs[k + 1]
        for _ in range(60):
            if Tb - Ta < 1e-9 * max(1.0, Ta):
                break
            Tm = 0.5 * (Ta + Tb)
            pm, _ = hull_pieces(sysm, Tm, g, refine=False)
            lm = labels(pm)
            if lm == la:
                Ta = Tm
            elif lm == lb:
                Tb = Tm
            else:
                # a third topology inside: keep the lower change, the upper one is found later
                Tb = Tm
                lb = lm
        pa, _ = hull_pieces(sysm, Ta, g, refine=True)
        pb, _ = hull_pieces(sysm, Tb, g, refine=True)
        ev = classify_change(sysm, grid_topo, fine, Ta, Tb, pa, pb, pure)
        ev["bracket_K"] = [Ta, Tb]
        ev["scan_interval_K"] = [float(Ts[k]), float(Ts[k + 1])]
        ev["labels_below"] = list(labels(pa))
        ev["labels_above"] = list(labels(pb))
        if _attribute_to_spinodal(ev, spin_events):
            continue
        changes.append(ev)
        if ev["kind"] in ("invariant", "congruent", "critical"):
            events.append(ev)
    # a third topology hidden inside one scan interval: re-scan intervals that produced an event
    # whose upper label differs from the next sample
    extra = []
    for ev in changes:
        Ta, Tb = ev["scan_interval_K"]
        lb_sample = labs[int(round((Tb - T_lo) / (T_hi - T_lo) * nsteps))]
        if tuple(ev["labels_above"]) != lb_sample:
            Tc = ev["bracket_K"][1]
            pa, _ = hull_pieces(sysm, Tc, grid_topo, refine=False)
            la = labels(pa)
            Tx, Ty = Tc, Tb
            lb2 = lb_sample
            for _ in range(60):
                if Ty - Tx < 1e-9 * max(1.0, Tx):
                    break
                Tm = 0.5 * (Tx + Ty)
                pm, _ = hull_pieces(sysm, Tm, grid_topo, refine=False)
                lm = labels(pm)
                if lm == la:
                    Tx = Tm
                else:
                    Ty = Tm
                    lb2 = lm
            pa, _ = hull_pieces(sysm, Tx, grid_topo, refine=True)
            pb, _ = hull_pieces(sysm, Ty, grid_topo, refine=True)
            ev2 = classify_change(sysm, grid_topo, fine, Tx, Ty, pa, pb, pure)
            ev2["bracket_K"] = [Tx, Ty]
            ev2["scan_interval_K"] = [Ta, Tb]
            ev2["labels_below"] = list(labels(pa))
            ev2["labels_above"] = list(labels(pb))
            if _attribute_to_spinodal(ev2, spin_events):
                continue
            extra.append(ev2)
            if ev2["kind"] in ("invariant", "congruent", "critical"):
                events.append(ev2)
    changes += extra
    jumps = [e for e in spin_events if e.get("kind") == "spinodal_jump"]
    changes += [e for e in spin_events if e.get("kind") in ("critical", "unknown")]
    changes.sort(key=lambda e: e["bracket_K"][0])
    events.sort(key=lambda e: e["temperature_K"])
    return {"step_K": float((T_hi - T_lo) / nsteps), "n_hulls": nsteps + 1, "scan_seconds": scan_time,
            "changes": changes, "events": events, "pure_end_transitions": pure, "spinodal_jumps": jumps}


def _attribute_to_spinodal(ev, spin_events):
    """A label change that is (or fails to be) a critical point and lies within MATCH_T of a
    spinodal-detected critical point is the lagging sampled-hull signature of that point."""
    if ev["kind"] not in ("critical", "unknown"):
        return False
    Tm = 0.5 * (ev["bracket_K"][0] + ev["bracket_K"][1])
    for se in spin_events:
        if se.get("kind") == "critical" and abs(se["temperature_K"] - Tm) <= MATCH_T:
            se.setdefault("label_change_brackets_K", []).append(ev["bracket_K"])
            return True
    return False


# ----------------------------------------------------------------------------
# report checks
# ----------------------------------------------------------------------------
def check_schema(sysm, rep):
    errs = []
    want = {"system_id", "isotherms", "invariants", "congruent_points", "critical_points"}
    if set(rep.keys()) != want:
        errs.append("top-level keys %s" % sorted(rep.keys()))
        return errs
    if rep["system_id"] != sysm.id:
        errs.append("system_id mismatch")
    if len(rep["isotherms"]) != len(sysm.isotherms):
        errs.append("isotherm count %d vs %d" % (len(rep["isotherms"]), len(sysm.isotherms)))
    for k, iso in enumerate(rep["isotherms"]):
        if set(iso.keys()) != {"temperature_K", "single_phase_regions", "tie_lines"}:
            errs.append("isotherm %d keys" % k)
            continue
        if k < len(sysm.isotherms) and iso["temperature_K"] != sysm.isotherms[k]:
            errs.append("isotherm %d temperature %r != %r" % (k, iso["temperature_K"], sysm.isotherms[k]))
        for r in iso["single_phase_regions"]:
            if set(r.keys()) != {"phase", "x_lo", "x_hi"}:
                errs.append("isotherm %d region keys" % k)
            elif sysm.phase(r["phase"]) is None or sysm.phase(r["phase"]).kind != "sol":
                errs.append("isotherm %d region phase %r" % (k, r["phase"]))
        for t in iso["tie_lines"]:
            if set(t.keys()) != {"left_phase", "x_left", "right_phase", "x_right"}:
                errs.append("isotherm %d tie keys" % k)
                continue
            for side in ("left", "right"):
                p = sysm.phase(t[side + "_phase"])
                if p is None:
                    errs.append("isotherm %d unknown phase %r" % (k, t[side + "_phase"]))
                elif p.kind == "cmp" and t["x_" + side] != p.x:
                    errs.append("isotherm %d compound end %s not exactly x_theta" % (k, p.name))
    for e in rep["invariants"]:
        if set(e.keys()) != {"temperature_K", "class", "name", "phases"} or len(e["phases"]) != 3:
            errs.append("invariant keys")
        elif any(set(p.keys()) != {"phase", "x"} for p in e["phases"]):
            errs.append("invariant phase keys")
        elif not (e["phases"][0]["x"] < e["phases"][1]["x"] < e["phases"][2]["x"]):
            errs.append("invariant phases not in increasing x")
    for e in rep["congruent_points"]:
        if set(e.keys()) != {"temperature_K", "x", "phase_above", "phase_below", "two_phase_side"}:
            errs.append("congruent keys")
    for e in rep["critical_points"]:
        if set(e.keys()) != {"temperature_K", "x", "phase", "gap_side"}:
            errs.append("critical keys")
    for key in ("invariants", "congruent_points", "critical_points"):
        Ts = [e.get("temperature_K", 0) for e in rep[key]]
        if any(Ts[i] >= Ts[i + 1] for i in range(len(Ts) - 1)):
            errs.append("%s not strictly increasing in temperature" % key)
        if any(not (sysm.T_lo < t < sysm.T_hi) for t in Ts):
            errs.append("%s has a temperature outside the open window" % key)
    return errs


def check_sequence(sysm, regions, ties):
    """(a) pieces alternate correctly and cover [0,1]."""
    errs = []
    items = [("R", r) for r in regions] + [("T", t) for t in ties]
    items.sort(key=lambda it: (it[1]["x_lo"] if it[0] == "R" else it[1]["x_left"], 0 if it[0] == "R" else 1))
    if not items or items[0][0] != "R" or items[0][1]["x_lo"] != 0.0:
        errs.append("first piece is not a region starting at x=0")
    if not items or items[-1][0] != "R" or items[-1][1]["x_hi"] != 1.0:
        errs.append("last piece is not a region ending at x=1")
    for r in regions:
        if not (r["x_lo"] < r["x_hi"]):
            errs.append("region %s has x_lo >= x_hi" % r["phase"])
    for t in ties:
        if not (t["x_left"] < t["x_right"]):
            errs.append("tie %s-%s has x_left >= x_right" % (t["left_phase"], t["right_phase"]))
    worst_gap = 0.0
    for a, b in zip(items, items[1:]):
        if a[0] == "R" and b[0] == "R":
            errs.append("two consecutive regions %s, %s" % (a[1]["phase"], b[1]["phase"]))
        elif a[0] == "R" and b[0] == "T":
            gap = abs(a[1]["x_hi"] - b[1]["x_left"])
            worst_gap = max(worst_gap, gap)
            if gap > TOL_SEQ:
                errs.append("region %s ends at %r but tie starts at %r" % (a[1]["phase"], a[1]["x_hi"], b[1]["x_left"]))
            if a[1]["phase"] != b[1]["left_phase"]:
                errs.append("region %s followed by tie with left phase %s" % (a[1]["phase"], b[1]["left_phase"]))
        elif a[0] == "T" and b[0] == "R":
            gap = abs(a[1]["x_right"] - b[1]["x_lo"])
            worst_gap = max(worst_gap, gap)
            if gap > TOL_SEQ:
                errs.append("tie ends at %r but region %s starts at %r" % (a[1]["x_right"], b[1]["phase"], b[1]["x_lo"]))
            if a[1]["right_phase"] != b[1]["phase"]:
                errs.append("tie with right phase %s followed by region %s" % (a[1]["right_phase"], b[1]["phase"]))
        else:
            p = sysm.phase(a[1]["right_phase"])
            if p is None or p.kind != "cmp":
                errs.append("two consecutive ties not sharing a compound vertex (%s)" % a[1]["right_phase"])
            else:
                if b[1]["left_phase"] != p.name or a[1]["x_right"] != p.x or b[1]["x_left"] != p.x:
                    errs.append("ties around compound %s do not meet exactly at x_theta" % p.name)
    return errs, worst_gap


def check_isotherm(sysm, grid_topo, fine, iso):
    T = float(iso["temperature_K"])
    regions, ties = iso["single_phase_regions"], iso["tie_lines"]
    out = {"temperature_K": T, "n_regions": len(regions), "n_tie_lines": len(ties), "failures": []}
    seq_errs, worst_gap = check_sequence(sysm, regions, ties)
    out["sequence_errors"] = seq_errs
    out["worst_shared_boundary_gap"] = worst_gap
    out["failures"] += seq_errs
    # (b) tangent residuals and Newton refinement from the reported values
    tie_out = []
    max_res, max_dx_newton = 0.0, 0.0
    for t in ties:
        res = tie_residuals(sysm, t["left_phase"], t["x_left"], t["right_phase"], t["x_right"], T)
        sl = (sysm.phase(t["left_phase"]).kind, t["left_phase"], t["x_left"])
        sr = (sysm.phase(t["right_phase"]).kind, t["right_phase"], t["x_right"])
        xl, xr, ok = refine_tie(sysm, sl, sr, T)
        d = {"left_phase": t["left_phase"], "right_phase": t["right_phase"], "residuals": res,
             "newton_from_report": {"x_left": xl, "x_right": xr, "converged": ok,
                                    "dx_left": xl - t["x_left"], "dx_right": xr - t["x_right"]}}
        tie_out.append(d)
        max_res = max(max_res, res.get("max", 0.0))
        if ok:
            max_dx_newton = max(max_dx_newton, abs(xl - t["x_left"]), abs(xr - t["x_right"]))
        else:
            out["failures"].append("Newton from reported tie %s-%s did not converge" % (t["left_phase"], t["right_phase"]))
    out["tie_lines"] = tie_out
    out["max_tangent_residual"] = max_res
    out["max_dx_newton_from_report"] = max_dx_newton
    if max_res > TOL_TANGENT:
        out["failures"].append("tangent residual %.3g J/mol > %g" % (max_res, TOL_TANGENT))
    if max_dx_newton > TOL_X:
        out["failures"].append("reported tie compositions off by %.3g > %g" % (max_dx_newton, TOL_X))
    # (c) global stability of the reported hull
    if not seq_errs:
        viol, where, uncovered = hull_violation(sysm, fine, T, regions, ties)
        out["stability_violation"] = viol
        out["stability_violation_at"] = where
        out["uncovered_grid_points"] = uncovered
        if viol > TOL_STAB:
            out["failures"].append("phase %s at x=%.9g lies %.3g J/mol below the reported hull" % (where["phase"], where["x"], viol))
        if uncovered:
            out["failures"].append("%d grid points not covered by any piece" % uncovered)
    # (d) convexity of regions, region phase lowest, hull slope monotone
    Gs = fine.G(T, 2)
    idx = {p.name: k for k, p in enumerate(sysm.sols)}
    reg_out = []
    for r in regions:
        k = idx[r["phase"]]
        msk = (fine.x > r["x_lo"]) & (fine.x < r["x_hi"]) & (fine.x > 0) & (fine.x < 1)
        g2 = Gs[k][2][msk]
        min_g2 = float(np.min(g2)) if g2.size else float("nan")
        margin = np.inf
        for q, Gq in enumerate(Gs):
            if q != k and msk.any():
                margin = min(margin, float(np.min(Gq[0][msk] - Gs[k][0][msk])))
        for c in sysm.cmps:
            if r["x_lo"] < c.x < r["x_hi"]:
                margin = min(margin, float(sysm.sols[k].G(LD(c.x), LD(T), 0)[0] * -1 + LD(c.G(T))))
        rd = {"phase": r["phase"], "x_lo": r["x_lo"], "x_hi": r["x_hi"], "min_G2": min_g2,
              "min_margin_other_phases": None if margin == np.inf else margin}
        reg_out.append(rd)
        if not (min_g2 > 0):
            out["failures"].append("region %s is not convex (min G'' = %.3g)" % (r["phase"], min_g2))
        if margin < -TOL_STAB:
            out["failures"].append("region %s is not the lowest phase (margin %.3g J/mol)" % (r["phase"], margin))
    out["regions"] = reg_out
    # slope sequence along the hull
    slopes = []
    items = [("R", r) for r in regions] + [("T", t) for t in ties]
    items.sort(key=lambda it: (it[1]["x_lo"] if it[0] == "R" else it[1]["x_left"], 0 if it[0] == "R" else 1))
    for kind, it in items:
        if kind == "R":
            p = sysm.phase(it["phase"])
            if it["x_lo"] > 0:
                slopes.append(float(p.G(LD(it["x_lo"]), LD(T), 1)[1]))
            if it["x_hi"] < 1:
                slopes.append(float(p.G(LD(it["x_hi"]), LD(T), 1)[1]))
        else:
            gl = state_G(sysm, it["left_phase"], it["x_left"], T)
            gr = state_G(sysm, it["right_phase"], it["x_right"], T)
            m = float((gr - gl) / (LD(it["x_right"]) - LD(it["x_left"])))
            slopes += [m, m]
    jumps = [slopes[i + 1] - slopes[i] for i in range(len(slopes) - 1)]
    out["min_slope_increment"] = min(jumps) if jumps else None
    if jumps and min(jumps) < -TOL_TANGENT:
        out["failures"].append("hull slope decreases by %.3g along x (non-convex hull)" % (-min(jumps)))
    # independent construction
    pcs, flags = hull_pieces(sysm, T, grid_topo, refine=True)
    my_regions = [{"phase": p.phase, "x_lo": p.lo, "x_hi": p.hi} for p in pcs if p.kind == "R"]
    my_ties = [{"left_phase": p.pl, "x_left": p.xl, "right_phase": p.pr, "x_right": p.xr} for p in pcs if p.kind == "T"]
    ind = {"n_regions": len(my_regions), "n_tie_lines": len(my_ties), "regions": my_regions, "tie_lines": my_ties,
           "flags": flags}
    if any(p.kind == "T" and not p.refined for p in pcs):
        ind["flags"].append("some independent tie-lines not refined")
    if len(my_regions) != len(regions) or len(my_ties) != len(ties):
        out["failures"].append("independent hull has %d regions / %d ties, report has %d / %d" %
                               (len(my_regions), len(my_ties), len(regions), len(ties)))
        ind["max_dx"] = None
    else:
        dx = 0.0
        for a, b in zip(my_regions, regions):
            if a["phase"] != b["phase"]:
                out["failures"].append("region phase %s vs independent %s" % (b["phase"], a["phase"]))
            dx = max(dx, abs(a["x_lo"] - b["x_lo"]), abs(a["x_hi"] - b["x_hi"]))
        for a, b in zip(my_ties, ties):
            if a["left_phase"] != b["left_phase"] or a["right_phase"] != b["right_phase"]:
                out["failures"].append("tie phases %s-%s vs independent %s-%s" %
                                       (b["left_phase"], b["right_phase"], a["left_phase"], a["right_phase"]))
            dx = max(dx, abs(a["x_left"] - b["x_left"]), abs(a["x_right"] - b["x_right"]))
        ind["max_dx"] = dx
        if dx > TOL_X:
            out["failures"].append("independent tie-lines differ by %.3g > %g" % (dx, TOL_X))
    out["independent"] = ind
    return out


def check_invariant(sysm, grid_topo, fine, e):
    T = float(e["temperature_K"])
    states = [(p["phase"], float(p["x"])) for p in e["phases"]]
    out = {"temperature_K": T, "class": e["class"], "name": e["name"], "phases": states, "failures": []}
    TL = LD(T)
    G = [state_G(sysm, n, x, TL) for n, x in states]
    x = [LD(v) for _, v in states]
    m = (G[2] - G[0]) / (x[2] - x[0])
    c = G[0] - m * x[0]
    out["collinearity_residual"] = float(G[1] - (m * x[1] + c))
    tang = []
    for (n, xv), xl in zip(states, x):
        p = sysm.phase(n)
        if p.kind == "sol":
            g = p.G(xl, TL, 1)
            muA = g[0] - xl * g[1] - c
            muB = g[0] + (1 - xl) * g[1] - (m + c)
            tang.append({"phase": n, "mu_A": float(muA), "mu_B": float(muB), "slope": float(g[1] - m)})
        else:
            tang.append({"phase": n, "on_line": float(LD(p.G(TL)) - (m * xl + c))})
    out["tangency"] = tang
    max_res = max([abs(out["collinearity_residual"])] +
                  [abs(v) for t in tang for k, v in t.items() if k in ("mu_A", "mu_B", "on_line")])
    out["max_residual"] = max_res
    if max_res > TOL_TANGENT:
        out["failures"].append("three-phase line residual %.3g J/mol > %g" % (max_res, TOL_TANGENT))
    viol, where = line_violation(sysm, fine, T, m, c)
    out["stability_violation"] = viol
    out["stability_violation_at"] = where
    if viol > TOL_STAB:
        out["failures"].append("phase %s at x=%.9g lies %.3g J/mol below the three-phase line" % (where["phase"], where["x"], viol))
    res = refine_invariant(sysm, states, T)
    if res is None:
        out["failures"].append("Newton refinement from the reported invariant did not converge")
    else:
        dT = abs(res["T"] - T)
        dx = max(abs(a - b[1]) for a, b in zip(res["x"], states))
        out["refined"] = {"temperature_K": res["T"], "x": res["x"], "dT": dT, "dT_rel": dT / T, "max_dx": dx}
        if dT / T > TOL_T_REL:
            out["failures"].append("refined T differs by %.3g relative" % (dT / T))
        if dx > TOL_X:
            out["failures"].append("refined compositions differ by %.3g" % dx)
    P1, P2, P3 = [n for n, _ in states]
    cl = classify_invariant(sysm, grid_topo, T, P1, states[0][1], P2, states[1][1], P3, states[2][1])
    out["class_check"] = cl
    if cl["class"] is None:
        out["failures"].append("class undetermined: middle phase stable above=%s below=%s" %
                               (cl["middle_stable_above"], cl["middle_stable_below"]))
    elif cl["class"] != e["class"]:
        out["failures"].append("class %s reported, %s found" % (e["class"], cl["class"]))
    if not cl["outer_tie_consistent"]:
        out["failures"].append("outer tie-line test disagrees with middle-phase test")
    if cl["name"] != e["name"]:
        out["failures"].append("name %s reported, %s per spec table" % (e["name"], cl["name"]))
    return out


def check_congruent(sysm, grid_topo, fine, e):
    T, x = float(e["temperature_K"]), float(e["x"])
    P, Q = e["phase_above"], e["phase_below"]
    out = {"temperature_K": T, "x": x, "phase_above": P, "phase_below": Q, "two_phase_side": e["two_phase_side"],
           "failures": []}
    pP, pQ = sysm.phase(P), sysm.phase(Q)
    if pP is None or pQ is None or P == Q:
        out["failures"].append("phases %r / %r invalid" % (P, Q))
        return out
    TL, xl = LD(T), LD(x)
    if pP.kind == "sol" and pQ.kind == "sol":
        gP, gQ = pP.G(xl, TL, 1), pQ.G(xl, TL, 1)
        out["residual_G"] = float(gP[0] - gQ[0])
        out["residual_dG"] = float(gP[1] - gQ[1])
        max_res = max(abs(out["residual_G"]), abs(out["residual_dG"]))
        m, c = gP[1], gP[0] - xl * gP[1]
    else:
        S, C = (pP, pQ) if pP.kind == "sol" else (pQ, pP)
        if abs(x - C.x) > 0:
            out["failures"].append("x %r is not exactly the compound composition %r" % (x, C.x))
        g = S.G(LD(C.x), TL, 1)
        out["residual_G"] = float(g[0] - LD(C.G(TL)))
        max_res = abs(out["residual_G"])
        m, c = g[1], g[0] - LD(C.x) * g[1]
    out["max_residual"] = max_res
    if max_res > TOL_TANGENT:
        out["failures"].append("tangency residual %.3g J/mol > %g" % (max_res, TOL_TANGENT))
    viol, where = line_violation(sysm, fine, T, m, c)
    out["stability_violation"] = viol
    out["stability_violation_at"] = where
    if viol > TOL_STAB:
        out["failures"].append("phase %s at x=%.9g lies %.3g J/mol below the tangent line" % (where["phase"], where["x"], viol))
    res = refine_congruent(sysm, P, Q, x, T)
    if res is None:
        out["failures"].append("Newton refinement from the reported congruent point did not converge")
    else:
        dT = abs(res["T"] - T)
        dx = abs(res["x"] - x)
        out["refined"] = {"temperature_K": res["T"], "x": res["x"], "dT": dT, "dT_rel": dT / T, "dx": dx}
        if dT / T > TOL_T_REL:
            out["failures"].append("refined T differs by %.3g relative" % (dT / T))
        if dx > TOL_X:
            out["failures"].append("refined x differs by %.3g" % dx)
    sd = congruent_sides(sysm, grid_topo, T, x, P, Q)
    out["side_check"] = sd
    if sd["two_phase_side"] is None:
        out["failures"].append("two_phase_side undetermined (lens above=%s below=%s)" % (sd["lens_above"], sd["lens_below"]))
    elif sd["two_phase_side"] != e["two_phase_side"]:
        out["failures"].append("two_phase_side %s reported, %s found" % (e["two_phase_side"], sd["two_phase_side"]))
    if sd["phase_above"] != P:
        out["failures"].append("phase_above %s reported, %s found" % (P, sd["phase_above"]))
    if sd["phase_below"] != Q:
        out["failures"].append("phase_below %s reported, %s found" % (Q, sd["phase_below"]))
    return out


def check_critical(sysm, grid_topo, fine, e):
    T, x, P = float(e["temperature_K"]), float(e["x"]), e["phase"]
    out = {"temperature_K": T, "x": x, "phase": P, "gap_side": e["gap_side"], "failures": []}
    p = sysm.phase(P)
    if p is None or p.kind != "sol":
        out["failures"].append("phase %r is not a solution phase" % P)
        return out
    g = p.G(LD(x), LD(T), 3)
    out["residual_G2"] = float(g[2])
    out["residual_G3"] = float(g[3])
    max_res = max(abs(out["residual_G2"]), abs(out["residual_G3"]))
    out["max_residual"] = max_res
    if max_res > TOL_TANGENT:
        out["failures"].append("critical residual %.3g > %g" % (max_res, TOL_TANGENT))
    viol, where = line_violation(sysm, fine, T, g[1], g[0] - LD(x) * g[1])
    out["stability_violation"] = viol
    out["stability_violation_at"] = where
    if viol > TOL_STAB:
        out["failures"].append("phase %s at x=%.9g lies %.3g J/mol below the tangent at the critical point" % (where["phase"], where["x"], viol))
    res = refine_critical(sysm, P, x, T)
    if res is None:
        out["failures"].append("Newton refinement from the reported critical point did not converge")
    else:
        dT, dx = abs(res["T"] - T), abs(res["x"] - x)
        out["refined"] = {"temperature_K": res["T"], "x": res["x"], "dT": dT, "dT_rel": dT / T, "dx": dx}
        if dT / T > TOL_T_REL:
            out["failures"].append("refined T differs by %.3g relative" % (dT / T))
        if dx > TOL_X:
            out["failures"].append("refined x differs by %.3g" % dx)
    sd = critical_side(sysm, grid_topo, T, x, P)
    out["side_check"] = sd
    if sd["gap_side"] is None:
        out["failures"].append("gap_side undetermined")
    elif sd["gap_side"] != e["gap_side"]:
        out["failures"].append("gap_side %s reported, %s found" % (e["gap_side"], sd["gap_side"]))
    return out


def check_completeness(sysm, rep, scan):
    """Match every topology change found by the scan to a reported event or pure-end transition."""
    out = {"scan_step_K": scan["step_K"], "n_hulls": scan["n_hulls"], "scan_seconds": scan["scan_seconds"],
           "pure_end_transitions": scan["pure_end_transitions"], "changes": [], "failures": []}
    reported = []
    for e in rep["invariants"]:
        reported.append(("invariant", float(e["temperature_K"]), e))
    for e in rep["congruent_points"]:
        reported.append(("congruent", float(e["temperature_K"]), e))
    for e in rep["critical_points"]:
        reported.append(("critical", float(e["temperature_K"]), e))
    used = set()
    for ch in scan["changes"]:
        Ta, Tb = ch["bracket_K"]
        ch.setdefault("scan_interval_K", ch["bracket_K"])
        rec = {"interval_K": ch["scan_interval_K"], "bracket_K": ch["bracket_K"], "kind_found": ch["kind"],
               "labels_below": ch.get("labels_below"), "labels_above": ch.get("labels_above"), "detector": ch.get("detector", "labels")}
        if ch["kind"] == "pure_end":
            rec["matched"] = "pure_end"
            rec["analytic"] = ch.get("analytic")
            if ch.get("analytic") is None:
                rec["matched"] = None
                out["failures"].append("pure-end-like change in [%.4f, %.4f] without an analytic end transition" % (Ta, Tb))
        elif ch["kind"] in ("invariant", "congruent", "critical"):
            Te = ch["temperature_K"]
            rec["found_event"] = {k: v for k, v in ch.items() if k in ("kind", "temperature_K", "class", "name",
                                                                       "phases", "x", "phase", "phase_above",
                                                                       "phase_below", "two_phase_side", "gap_side",
                                                                       "stability_violation")}
            best = None
            for i, (kind, T, e) in enumerate(reported):
                if i in used:
                    continue
                if abs(T - Te) <= MATCH_T and (best is None or abs(T - Te) < abs(reported[best][1] - Te)):
                    best = i
            if best is None:
                rec["matched"] = None
                out["failures"].append("topology change at T=%.6f K (%s) has no reported event within %.2f K" %
                                       (Te, ch["kind"], MATCH_T))
            else:
                used.add(best)
                kind, T, e = reported[best]
                rec["matched"] = {"kind": kind, "temperature_K": T, "dT": T - Te}
                if kind != ch["kind"]:
                    out["failures"].append("change at T=%.6f K is a %s but the report has a %s there" % (Te, ch["kind"], kind))
                else:
                    dx = 0.0
                    if kind == "invariant":
                        dx = max(abs(a["x"] - b["x"]) for a, b in zip(ch["phases"], e["phases"]))
                        if [a["phase"] for a in ch["phases"]] != [b["phase"] for b in e["phases"]]:
                            out["failures"].append("invariant at T=%.6f K: phases %s found, %s reported" %
                                                   (Te, [a["phase"] for a in ch["phases"]], [b["phase"] for b in e["phases"]]))
                    else:
                        dx = abs(ch["x"] - e["x"])
                    rec["matched"]["max_dx"] = dx
        else:
            rec["matched"] = None
            out["failures"].append("unclassified topology change in [%.6f, %.6f] K: %s" % (Ta, Tb, ch.get("note")))
        out["changes"].append(rec)
    missing = [(k, T) for i, (k, T, e) in enumerate(reported) if i not in used]
    out["reported_without_change"] = [{"kind": k, "temperature_K": T} for k, T in missing]
    for k, T in missing:
        out["failures"].append("reported %s at T=%.6f K has no corresponding topology change" % (k, T))
    # pure-end transitions must each have a change
    for pe in scan["pure_end_transitions"]:
        hit = any(ch["kind"] == "pure_end" and ch["bracket_K"][0] - MATCH_T <= pe["T"] <= ch["bracket_K"][1] + MATCH_T
                  for ch in scan["changes"])
        if not hit:
            out["failures"].append("pure-end transition at T=%.6f K (%s) not seen in the scan" % (pe["T"], pe["end"]))
    out["independent_events"] = [{k: v for k, v in ev.items() if k not in ("class_detail",)} for ev in scan["events"]]
    return out


# ----------------------------------------------------------------------------
# drivers
# ----------------------------------------------------------------------------
def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating, np.longdouble)):
        v = float(o)
        return v if math.isfinite(v) else str(v)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, float) and not math.isfinite(o):
        return str(o)
    return o


def pick_scan_step(sysm, requested):
    width = sysm.T_hi - sysm.T_lo
    if requested:
        return requested
    step = 0.1 if _load_lib() is not None else max(0.1, min(0.25, width / 2400.0))
    return step


def referee(sysm, rep, scan_step=None, do_scan=True, log=print):
    t0 = time.time()
    grid_topo = Grid(sysm, 50001, 20)
    grid_scan = Grid(sysm, 20001, 10)
    fine = FineGrid(sysm, 200001, 50)
    verdict = {"system_id": sysm.id, "thresholds": {"tangent_J_mol": TOL_TANGENT, "stability_J_mol": TOL_STAB,
                                                    "T_relative": TOL_T_REL, "x_absolute": TOL_X,
                                                    "match_K": MATCH_T},
               "grids": {"topology_points": grid_topo.n, "scan_points": grid_scan.n, "fine_points": fine.n},
               "hull_backend": "C monotone chain" if _load_lib() is not None else "python monotone chain"}
    failures = []
    schema = check_schema(sysm, rep)
    verdict["schema_errors"] = schema
    failures += ["schema: " + s for s in schema]
    if any("keys" in s for s in schema) or "top-level" in " ".join(schema):
        verdict["pass"] = False
        verdict["failures"] = failures
        return verdict
    isos = []
    for iso in rep["isotherms"]:
        r = check_isotherm(sysm, grid_topo, fine, iso)
        isos.append(r)
        failures += ["isotherm %g K: %s" % (r["temperature_K"], f) for f in r["failures"]]
    verdict["isotherms"] = isos
    verdict["invariants"] = []
    for e in rep["invariants"]:
        r = check_invariant(sysm, grid_topo, fine, e)
        verdict["invariants"].append(r)
        failures += ["invariant %.6f K: %s" % (r["temperature_K"], f) for f in r["failures"]]
    verdict["congruent_points"] = []
    for e in rep["congruent_points"]:
        r = check_congruent(sysm, grid_topo, fine, e)
        verdict["congruent_points"].append(r)
        failures += ["congruent %.6f K: %s" % (r["temperature_K"], f) for f in r["failures"]]
    verdict["critical_points"] = []
    for e in rep["critical_points"]:
        r = check_critical(sysm, grid_topo, fine, e)
        verdict["critical_points"].append(r)
        failures += ["critical %.6f K: %s" % (r["temperature_K"], f) for f in r["failures"]]
    t1 = time.time()
    if do_scan:
        step = pick_scan_step(sysm, scan_step)
        scan = find_events(sysm, grid_scan, grid_topo, fine, step)
        comp = check_completeness(sysm, rep, scan)
        verdict["completeness"] = comp
        failures += ["completeness: " + f for f in comp["failures"]]
    verdict["summary"] = {
        "max_tangent_residual": max([i["max_tangent_residual"] for i in isos] +
                                    [e.get("max_residual", 0.0) for e in verdict["invariants"] + verdict["congruent_points"] + verdict["critical_points"]] + [0.0]),
        "max_stability_violation": max([i.get("stability_violation", -np.inf) for i in isos] +
                                       [e.get("stability_violation", -np.inf) for e in verdict["invariants"] + verdict["congruent_points"] + verdict["critical_points"]] + [-np.inf]),
        "max_dx_isotherms_newton": max([i["max_dx_newton_from_report"] for i in isos] + [0.0]),
        "max_dx_isotherms_independent": max([i["independent"].get("max_dx") or 0.0 for i in isos] + [0.0]),
        "max_dT_rel_events": max([e.get("refined", {}).get("dT_rel", 0.0) for e in verdict["invariants"] + verdict["congruent_points"] + verdict["critical_points"]] + [0.0]),
        "max_dx_events": max([e.get("refined", {}).get("max_dx", e.get("refined", {}).get("dx", 0.0)) for e in verdict["invariants"] + verdict["congruent_points"] + verdict["critical_points"]] + [0.0]),
    }
    verdict["timing_seconds"] = {"certificates": t1 - t0, "completeness": time.time() - t1, "total": time.time() - t0}
    verdict["failures"] = failures
    verdict["pass"] = len(failures) == 0
    return verdict


def solve(sysm, scan_step=None):
    """Independent solver: dense hull + Newton at isotherms, scan + bisection + Newton for events."""
    grid_topo = Grid(sysm, 50001, 20)
    grid_scan = Grid(sysm, 20001, 10)
    fine = FineGrid(sysm, 200001, 50)
    rep = {"system_id": sysm.id, "isotherms": []}
    for T in sysm.isotherms:
        pcs, flags = hull_pieces(sysm, T, grid_topo, refine=True)
        rep["isotherms"].append({
            "temperature_K": T,
            "single_phase_regions": [{"phase": p.phase, "x_lo": p.lo, "x_hi": p.hi} for p in pcs if p.kind == "R"],
            "tie_lines": [{"left_phase": p.pl, "x_left": p.xl, "right_phase": p.pr, "x_right": p.xr}
                          for p in pcs if p.kind == "T"]})
    scan = find_events(sysm, grid_scan, grid_topo, fine, pick_scan_step(sysm, scan_step))
    inv, con, cri = [], [], []
    for ev in scan["events"]:
        if ev["kind"] == "invariant":
            inv.append({"temperature_K": ev["temperature_K"], "class": ev["class"], "name": ev["name"],
                        "phases": ev["phases"]})
        elif ev["kind"] == "congruent":
            con.append({"temperature_K": ev["temperature_K"], "x": ev["x"], "phase_above": ev["phase_above"],
                        "phase_below": ev["phase_below"], "two_phase_side": ev["two_phase_side"]})
        else:
            cri.append({"temperature_K": ev["temperature_K"], "x": ev["x"], "phase": ev["phase"],
                        "gap_side": ev["gap_side"]})
    rep["invariants"] = sorted(inv, key=lambda e: e["temperature_K"])
    rep["congruent_points"] = sorted(con, key=lambda e: e["temperature_K"])
    rep["critical_points"] = sorted(cri, key=lambda e: e["temperature_K"])
    unknown = [c for c in scan["changes"] if c["kind"] == "unknown"]
    return rep, scan, unknown


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", required=True)
    ap.add_argument("--report")
    ap.add_argument("--out")
    ap.add_argument("--solve", action="store_true")
    ap.add_argument("--output")
    ap.add_argument("--scan-step", type=float, default=None)
    ap.add_argument("--no-scan", action="store_true", help="skip the completeness scan")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    with open(args.system) as f:
        sysm = System(json.load(f))
    if args.solve:
        if not args.output:
            ap.error("--solve needs --output")
        t0 = time.time()
        rep, scan, unknown = solve(sysm, args.scan_step)
        with open(args.output, "w") as f:
            json.dump(_jsonable(rep), f, indent=1)
        if not args.quiet:
            print("solved %s in %.1f s: %d invariants, %d congruent, %d critical, %d unclassified changes" %
                  (sysm.id, time.time() - t0, len(rep["invariants"]), len(rep["congruent_points"]),
                   len(rep["critical_points"]), len(unknown)))
            for u in unknown:
                print("  unclassified:", u.get("note"), u.get("bracket_K"))
        return 0
    if not args.report:
        ap.error("--report is required unless --solve")
    with open(args.report) as f:
        rep = json.load(f)
    verdict = _jsonable(referee(sysm, rep, args.scan_step, not args.no_scan))
    text = json.dumps(verdict, indent=1)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    if args.quiet:
        s = verdict["summary"]
        print("%s pass=%s res=%.2e stab=%.2e dx_iso=%.2e dx_ind=%.2e dT_rel=%.2e dx_ev=%.2e t=%.1fs" %
              (sysm.id, verdict["pass"], s["max_tangent_residual"], s["max_stability_violation"],
               s["max_dx_isotherms_newton"], s["max_dx_isotherms_independent"], s["max_dT_rel_events"],
               s["max_dx_events"], verdict["timing_seconds"]["total"]))
        for f_ in verdict["failures"]:
            print("  FAIL:", f_)
    else:
        print(text)
    return 0 if verdict["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
