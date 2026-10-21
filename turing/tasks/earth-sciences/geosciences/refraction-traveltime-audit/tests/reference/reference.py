#!/usr/bin/env python3
"""Reference A: ray-theoretical P traveltimes in flat layers with linear velocity.

Method: X(p) and T(p) are evaluated by numerical quadrature of the ray integrals
    X = 2 sum_k int p v / sqrt(1 - p^2 v^2) dz,   T = 2 sum_k int 1 / (v sqrt(1 - p^2 v^2)) dz
over each layer segment crossed by the ray.  No per-layer antiderivative is used.  The inverse
square-root factor 1/sqrt(1 - p v) is removed by a substitution in depth anchored at the
fastest end of the segment (turning depth, or grazing end), and the remaining smooth factor is
integrated by composite Gauss-Legendre on panels graded toward the slow end.  dX/dp comes from a
complex-step derivative of the same discrete quadrature.  Usage:
    python reference.py --model M.json --output R.json
"""
import argparse
import json
import math
import sys

import numpy as np
from scipy.interpolate import CubicHermiteSpline
from scipy.optimize import brentq, minimize_scalar

HC = 1e-30          # complex-step size for dX/dp
N_PER_PANEL = 12    # Gauss-Legendre nodes per panel
N_GRADED = 12       # panels graded toward tau = 1: edges 0, 1/2, 3/4, ..., 1 - 2^-12, 1


def quad_rule(n_per_panel=N_PER_PANEL, n_graded=N_GRADED):
    xg, wg = np.polynomial.legendre.leggauss(n_per_panel)
    edges = [0.0] + [1.0 - 2.0 ** (-j) for j in range(1, n_graded + 1)] + [1.0]
    nodes, weights = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        nodes.append(lo + (hi - lo) * (xg + 1.0) / 2.0)
        weights.append((hi - lo) / 2.0 * wg)
    return np.concatenate(nodes), np.concatenate(weights)


TAU, WTS = quad_rule()


def set_rule(n_per_panel, n_graded):
    global TAU, WTS
    TAU, WTS = quad_rule(n_per_panel, n_graded)


# ----------------------------------------------------------------------------------------------
# model

class Model:
    def __init__(self, d):
        L = d["layers"]
        self.model_id = d["model_id"]
        self.N = len(L)
        self.a = [float(l["v_top_km_s"]) for l in L]
        self.b = [float(l["gradient_per_s"]) for l in L]
        self.h = [float(l["thickness_km"]) if l["thickness_km"] is not None else math.inf
                  for l in L]
        self.x_max = float(d["x_max_km"])
        self.offsets = list(d["offsets_km"])
        self.vbot = [self.a[k] + self.b[k] * self.h[k] if k < self.N - 1 else math.nan
                     for k in range(self.N)]
        # maximum (supremum) of v inside each finite layer
        self.vlay = [max(self.a[k], self.vbot[k]) for k in range(self.N - 1)]
        # V_i^- for i = 1..N-1
        self.Vm = [None] + [max(self.vlay[:i]) for i in range(1, self.N)]


# ----------------------------------------------------------------------------------------------
# quadrature of one ray segment inside one layer
#
# Inside the segment v is linear; let d >= 0 be the distance from the segment's fastest end,
# v = vmax - |b| d, so that 1 - p v = q + c d with q = 1 - p vmax >= 0 and c = p |b|.
# With d = t^2 + 2 t sqrt(lambda), lambda = q / c, one has dd / sqrt(q + c d) = 2 dt / sqrt(c),
# which removes the inverse square-root factor exactly (turning point q = 0, grazing q -> 0).
# Written with tau = t / t_end in [0, 1] and D = sqrt(q + c h) + sqrt(q):
#     int_0^h F(d) / sqrt(q + c d) dd = (2 h / D) int_0^1 F(d(tau)) dtau,
#     d(tau) = (h^2 c / D^2) tau^2 + (2 h sqrt(q) / D) tau,
# valid for every c >= 0 (c = 0 is the constant-velocity layer).  F is the smooth remainder:
#     F_X = p v / sqrt(1 + p v),   F_T = 1 / (v sqrt(1 + p v)).

def seg_integrals(p, vmax, absb, h, q):
    c = p * absb
    sq = np.sqrt(q)
    D = np.sqrt(q + c * h) + sq
    zero = (h == 0)
    Ds = np.where(zero, 1.0, D)
    pref = np.where(zero, 0.0, 2.0 * h / Ds)
    A = h * h * c / (Ds * Ds)
    B = 2.0 * h * sq / Ds
    d = (A[:, None] * TAU[None, :] + B[:, None]) * TAU[None, :]
    v = vmax[:, None] - absb * d
    pv = p[:, None] * v
    s1 = np.sqrt(1.0 + pv)
    IX = pref * ((pv / s1) @ WTS)
    IT = pref * ((1.0 / (v * s1)) @ WTS)
    return IX, IT


class Branch:
    """kind in {'turning', 'reflection'}; p in (plo, phi)."""

    def __init__(self, model, kind, index, plo, phi, lo_div, hi_div):
        self.m = model
        self.kind, self.index = kind, index
        self.plo, self.phi = plo, phi
        self.lo_div, self.hi_div = lo_div, hi_div
        self.full = list(range(index))    # layers crossed completely
        self.turn = index if kind == "turning" else None
        # turning branch whose upper end p = 1/a_k is the ray grazing the top of layer k
        self.top_graze = kind == "turning" and phi == 1.0 / model.a[index]

    def eval(self, p, clamp=False, top_end=False):
        """X(p), T(p) for an array p (real or complex)."""
        m = self.m
        p = np.asarray(p)
        X = np.zeros(p.shape, dtype=p.dtype)
        T = np.zeros(p.shape, dtype=p.dtype)
        one = np.ones(p.shape)
        for j in self.full:
            vmax = m.vlay[j]
            q = 1.0 - p * vmax
            if clamp:
                q = np.maximum(q, 0.0)
            IX, IT = seg_integrals(p, vmax * one, abs(m.b[j]), m.h[j] * one, q)
            X = X + IX
            T = T + IT
        if self.turn is not None:
            k = self.turn
            vt = 1.0 / p
            hh = (vt - m.a[k]) / m.b[k]
            if clamp:
                hh = np.maximum(hh, 0.0)
            if top_end:
                # exactly at p = 1/a_k the turning depth is the top of the layer; 1/p - a_k
                # would leave a rounding residue (~1e-16) whose square root is not negligible
                hh = np.zeros(p.shape, dtype=p.dtype)
            IX, IT = seg_integrals(p, vt, m.b[k], hh, np.zeros(p.shape, dtype=p.dtype))
            X = X + IX
            T = T + IT
        return 2.0 * X, 2.0 * T

    def xdt(self, p):
        """X, dX/dp, T at real p (array) via one complex-step evaluation."""
        p = np.asarray(p, dtype=float)
        Xc, Tc = self.eval(p + 1j * HC)
        return Xc.real, Xc.imag / HC, Tc.real

    def x_end(self, p):
        top_end = self.top_graze and p == self.phi
        X, T = self.eval(np.array([p], dtype=float), clamp=True, top_end=top_end)
        return float(X[0]), float(T[0])


def build_branches(m):
    br = []
    for k in range(m.N):
        if m.b[k] > 0:
            top = m.a[k] if k == 0 else max(m.a[k], m.Vm[k])
            phi = 1.0 / top
            plo = 0.0 if k == m.N - 1 else 1.0 / m.vbot[k]
            if plo < phi:
                # divergence at phi: grazing in a constant layer above whose velocity is 1/phi
                hi_div = any(m.b[j] == 0 and m.a[j] == top for j in range(k))
                br.append(Branch(m, "turning", k, plo, phi, k == m.N - 1, hi_div))
    for i in range(1, m.N):
        V = m.Vm[i]
        hi_div = any(m.b[j] == 0 and m.a[j] == V for j in range(i))
        br.append(Branch(m, "reflection", i, 0.0, 1.0 / V, False, hi_div))
    return br


# ----------------------------------------------------------------------------------------------
# sampling, caustics, segments

def sample_branch(B, x_max):
    plo, phi = B.plo, B.phi
    s = np.linspace(0.0, 1.0, 2001)[1:-1]
    w = 0.5 * (1.0 - np.cos(np.pi * s))
    P = [plo + (phi - plo) * w]
    eps = np.geomspace(1e-14, 1e-3, 45)
    P.append(phi - (phi - plo) * eps)
    if plo > 0:
        P.append(plo + (phi - plo) * eps)
    else:
        P.append(phi * eps)
    P = np.unique(np.concatenate(P))
    P = P[(P > plo) & (P < phi)]
    X, dX, T = B.xdt(P)
    for _ in range(40):
        if P.size > 60000:
            break
        X1, X2 = X[:-1], X[1:]
        D1, D2 = dX[:-1], dX[1:]
        tol = 1e-3 * np.maximum(np.maximum(X1, X2), 0.01 * x_max)
        jump_x = np.abs(X2 - X1) > tol
        jump_d = (D1 * D2 > 0) & (np.abs(D2 - D1) > 0.1 * np.maximum(np.abs(D1), np.abs(D2)))
        need = (np.minimum(X1, X2) < 2.0 * x_max) & (jump_x | jump_d) & \
               (P[1:] - P[:-1] > 1e-13 * P[1:])
        if not need.any():
            break
        Pn = 0.5 * (P[:-1][need] + P[1:][need])
        Xn, dXn, Tn = B.xdt(Pn)
        P = np.concatenate([P, Pn])
        X = np.concatenate([X, Xn])
        dX = np.concatenate([dX, dXn])
        T = np.concatenate([T, Tn])
        o = np.argsort(P)
        P, X, dX, T = P[o], X[o], dX[o], T[o]
    return P, X, dX, T


def dxdp_scalar(B, p):
    return float(B.xdt(np.array([p]))[1][0])


def find_caustics(B, P, dX):
    roots = []
    sgn = np.sign(dX)
    for i in np.nonzero(sgn[:-1] * sgn[1:] < 0)[0]:
        roots.append(brentq(lambda pp: dxdp_scalar(B, pp), P[i], P[i + 1],
                            xtol=1e-17, rtol=1e-15, maxiter=300))
    # safety net: a local extremum of dX/dp that touches zero between two samples
    for i in range(1, len(P) - 1):
        if sgn[i - 1] == sgn[i] == sgn[i + 1] and sgn[i] != 0:
            a = sgn[i] * dX[i]
            if a < sgn[i] * dX[i - 1] and a < sgn[i] * dX[i + 1]:
                s0 = sgn[i]
                r = minimize_scalar(lambda pp: s0 * dxdp_scalar(B, pp),
                                    bounds=(P[i - 1], P[i + 1]), method="bounded",
                                    options={"xatol": 1e-15})
                if r.fun < 0:
                    pm = r.x
                    roots.append(brentq(lambda pp: dxdp_scalar(B, pp), P[i - 1], pm,
                                        xtol=1e-17, rtol=1e-15, maxiter=300))
                    roots.append(brentq(lambda pp: dxdp_scalar(B, pp), pm, P[i + 1],
                                        xtol=1e-17, rtol=1e-15, maxiter=300))
    return sorted(roots)


class Segment:
    pass


def make_segments(B, x_max):
    P, X, dX, T = sample_branch(B, x_max)
    caus = find_caustics(B, P, dX)
    # end points in p (divergent ends replaced by the outermost sample) and their X
    if B.lo_div:
        e_lo = (P[0], X[0], math.inf, T[0])
    else:
        xe, te = B.x_end(B.plo)
        e_lo = (B.plo, xe, xe, te)
    if B.hi_div:
        e_hi = (P[-1], X[-1], math.inf, T[-1])
    else:
        xe, te = B.x_end(B.phi)
        e_hi = (B.phi, xe, xe, te)
    cx = []
    for pc in caus:
        xc, tc = B.x_end(pc)
        cx.append((pc, xc, xc, tc))
    bounds = [e_lo] + cx + [e_hi]
    segs = []
    for (pa, xa, xa_true, ta), (pb, xb, xb_true, tb) in zip(bounds[:-1], bounds[1:]):
        S = Segment()
        S.kind, S.index, S.branch = B.kind, B.index, B
        S.pa, S.pb, S.xa, S.xb = pa, pb, xa, xb
        S.sgn = 1.0 if xb > xa else -1.0
        S.xlo = min(xa_true, xb_true)
        S.xhi = max(xa_true, xb_true)
        sel = (P > pa) & (P < pb)
        tp = np.concatenate([[pa], P[sel], [pb]])
        tx = np.concatenate([[xa], X[sel], [xb]])
        tt = np.concatenate([[ta], T[sel], [tb]])
        if S.sgn < 0:
            tp, tx, tt = tp[::-1], tx[::-1], tt[::-1]
        # keep a strictly increasing table (drops rounding-level wiggles next to the ends)
        ok = tx > np.concatenate([[-np.inf], np.maximum.accumulate(tx)[:-1]])
        S.tab_p, S.tab_x, S.tab_t = tp[ok], tx[ok], tt[ok]
        S.ends = [(x_, p_, t_) for x_, p_, t_ in ((xa_true, pa, ta), (xb_true, pb, tb))
                  if math.isfinite(x_)]
        segs.append(S)
    caustics = [{"kind": B.kind, "index": B.index, "p_s_km": c[0], "x_km": c[1], "t_s": c[3]}
                for c in cx]
    return segs, caustics


def seg_solve(S, Xt):
    """p and T on segment S at the offsets Xt (array, all inside the segment's range)."""
    Xt = np.asarray(Xt, dtype=float)
    if S.kind in ("direct", "head"):
        return np.full(Xt.shape, S.p), Xt * S.p + S.tau
    B = S.branch
    p = np.interp(Xt, S.tab_x, S.tab_p)
    lo = np.full(Xt.shape, S.pa)
    hi = np.full(Xt.shape, S.pb)
    T = np.empty(Xt.shape)
    act = np.arange(Xt.size)
    for _ in range(200):
        pa_ = p[act]
        X, dX, Ta = B.xdt(pa_)
        xt = Xt[act]
        # T at the target offset through the intercept tau = T - p X (d tau/dp = -X), which
        # makes the result insensitive to the residual X(p) - Xt to first order
        T[act] = (Ta - pa_ * X) + pa_ * xt
        r = (X - xt) * S.sgn
        lo[act] = np.where(r < 0, pa_, lo[act])
        hi[act] = np.where(r > 0, pa_, hi[act])
        l_, h_ = lo[act], hi[act]
        pn = pa_ - (X - xt) / dX
        bad = ~np.isfinite(pn) | (pn <= l_) | (pn >= h_)
        pn = np.where(bad, 0.5 * (l_ + h_), pn)
        conv = (~bad & (np.abs(pn - pa_) <= 1e-15 * np.abs(pa_))) | (r == 0) | \
               (h_ - l_ <= 2e-16 * h_)
        # a converged Newton step is accepted only after T is re-evaluated at it
        p[act] = np.where(r == 0, pa_, pn)
        fin = act[conv & (r == 0)]
        act_next = act[~conv]
        redo = act[conv & (r != 0)]
        if redo.size:
            Xr, dXr, Tr = B.xdt(p[redo])
            T[redo] = (Tr - p[redo] * Xr) + p[redo] * Xt[redo]
        act = act_next
        if act.size == 0:
            break
    return p, T


def seg_has(S, X):
    return (X > S.xlo) & (X < S.xhi)


# ----------------------------------------------------------------------------------------------
# the report

def solve_model(m):
    branches = build_branches(m)
    segs, caustics = [], []
    for B in branches:
        s, c = make_segments(B, m.x_max)
        segs += s
        caustics += c
    if m.b[0] == 0:
        S = Segment()
        S.kind, S.index, S.p, S.tau = "direct", 0, 1.0 / m.a[0], 0.0
        S.xlo, S.xhi = 0.0, math.inf
        S.ends = []
        segs.append(S)
    for i in range(1, m.N):
        if m.b[i] == 0 and m.a[i] > m.Vm[i]:
            R = [B for B in branches if B.kind == "reflection" and B.index == i][0]
            pc = 1.0 / m.a[i]
            xc, tc = R.x_end(pc)
            S = Segment()
            S.kind, S.index, S.p, S.tau = "head", i, pc, tc - pc * xc
            S.xlo, S.xhi = xc, math.inf
            S.ends = [(xc, pc, tc)]
            segs.append(S)

    # arrivals at the queried offsets
    arrivals = []
    for x in m.offsets:
        xf = float(x)
        rays = []
        for S in segs:
            if S.kind == "head":
                ok = xf >= S.xlo
            else:
                ok = seg_has(S, xf)
            if ok:
                pp, tt = seg_solve(S, np.array([xf]))
                rays.append({"kind": S.kind, "index": S.index,
                             "p_s_km": float(pp[0]), "t_s": float(tt[0])})
        rays.sort(key=lambda r: r["t_s"])
        arrivals.append({"x_km": x, "rays": rays})

    caus_out = sorted([c for c in caustics if 0 < c["x_km"] <= m.x_max],
                      key=lambda c: c["x_km"])
    caus_out = [{"kind": c["kind"], "index": c["index"], "p_s_km": float(c["p_s_km"]),
                 "x_km": float(c["x_km"]), "t_s": float(c["t_s"])} for c in caus_out]

    first = first_arrival(m, segs)
    return {"model_id": m.model_id, "arrivals": arrivals, "caustics": caus_out,
            "first_arrival": first}


def first_arrival(m, segs):
    xm = m.x_max
    nS = len(segs)
    events = sorted({v for S in segs for v in (S.xlo, S.xhi) if 0 < v < xm})

    def avail(j, x):
        S = segs[j]
        if S.kind in ("head", "direct"):
            return S.xlo <= x <= S.xhi
        return bool(seg_has(S, x))

    def solve1(j, x):
        pp, tt = seg_solve(segs[j], np.array([x]))
        return float(pp[0]), float(tt[0])

    # Touching pairs.  When the end point (X_e, p_e, T_e) of segment a lies on segment b with the
    # same ray parameter (a cusp where two segments meet, a turning branch leaving a reflection
    # tangentially, a head wave leaving its critical reflection), T_a - T_b is the integral of
    # p_a - p_b from X_e, so the earlier of the two is the one with the larger p for X < X_e and
    # the smaller p for X > X_e, and they do not cross.  Close to X_e the time difference falls
    # below rounding, so within ZONE of X_e this rule replaces the comparison of times.
    ZONE = 1e-5
    touching = []   # (winner, loser, x_e, side) side = +1: X > X_e, -1: X < X_e
    for ja, A in enumerate(segs):
        for (xe, pe, te) in A.ends:
            if not (0 < xe < xm * (1 + ZONE)):
                continue
            for side in (-1.0, 1.0):
                xs = xe * (1 + side * 1e-6)
                if not avail(ja, xs):
                    continue
                for jb in range(nS):
                    if jb == ja or not avail(jb, xe * (1 + side * 1e-9)) or \
                            not avail(jb, xs):
                        continue
                    pb_e, tb_e = solve1(jb, xe * (1 + side * 1e-9))
                    if abs(pb_e - pe) > 1e-4 * pe or abs(tb_e - te) > 1e-8 * te:
                        continue
                    pa_s, _ = solve1(ja, xs)
                    pb_s, _ = solve1(jb, xs)
                    a_wins = (pa_s > pb_s) if side < 0 else (pa_s < pb_s)
                    w, l = (ja, jb) if a_wins else (jb, ja)
                    touching.append((w, l, xe, side))

    def in_zone(xe, side, x):
        return 0 < side * (x - xe) <= ZONE * xe

    def rule_patch(TTcol_get, TTcol_set, x):
        for (w, l, xe, side) in touching:
            if in_zone(xe, side, x):
                tw, tl = TTcol_get(w), TTcol_get(l)
                if math.isfinite(tw) and math.isfinite(tl) and tl <= tw:
                    TTcol_set(l, tw + 1e-13 * abs(tw))

    # dense screening grid (ratio 1 + 1e-4, finer than the 1e-3 crossover separation),
    # each segment's T(X) from a cubic Hermite interpolant of its (X, T, p = dT/dX) samples;
    # every change of the minimising segment is then resolved with exact evaluations
    grid = [np.geomspace(1e-6 * xm, xm, int(math.log(1e6) / 1e-4)), np.array([xm])]
    for e in events:
        grid.append(np.array([e * (1 - 1e-9), e * (1 + 1e-9)]))
    G = np.unique(np.concatenate(grid))
    G = G[(G > 0) & (G <= xm)]
    TT = np.full((nS, G.size), np.inf)
    for j, S in enumerate(segs):
        if S.kind in ("head", "direct"):
            msk = (G >= S.xlo) & (G <= S.xhi)
            TT[j, msk] = G[msk] * S.p + S.tau
        else:
            msk = seg_has(S, G)
            if msk.any() and S.tab_x.size >= 2:
                H = CubicHermiteSpline(S.tab_x, S.tab_t, S.tab_p)
                TT[j, msk] = H(G[msk])
    for (w, l, xe, side) in touching:
        z = (side * (G - xe) > 0) & (side * (G - xe) <= ZONE * xe) & \
            np.isfinite(TT[w]) & np.isfinite(TT[l])
        TT[l, z] = np.maximum(TT[l, z], TT[w, z] + 1e-13 * np.abs(TT[w, z]))
    empty = ~np.isfinite(TT).any(axis=0)
    if empty.any():
        raise ValueError("no arrival at x = %r km: the model violates the section-2 guarantee "
                         "that every offset has an arrival" % float(G[empty][0]))
    ids = np.argmin(TT, axis=0)

    def T_at(j, x):
        return solve1(j, x)[1]

    def argmin_at(x):
        col = {j: (T_at(j, x) if avail(j, x) else math.inf) for j in range(nS)}

        def st(j, v):
            col[j] = v
        rule_patch(lambda j: col[j], st, x)
        bj = min(col, key=lambda j: col[j])
        return bj, col[bj]

    def is_touching_pair(a, b, xl, xr):
        for (w, l, xe, side) in touching:
            if {w, l} == {a, b} and (in_zone(xe, side, xl) or in_zone(xe, side, xr)):
                return True
        return False

    bnds = []   # (x, new_segment)

    def resolve(xl, sl, xr, sr, depth=0):
        if sl == sr:
            return
        both = avail(sl, xl) and avail(sl, xr) and avail(sr, xl) and avail(sr, xr)
        if not both:
            # availability changes inside: the interval brackets an event
            cand = [e for e in events if xl <= e <= xr]
            if cand and (depth > 40 or xr - xl <= 1e-8 * xr):
                S1, S2 = segs[sl], segs[sr]
                pick = None
                for e in cand:
                    for v in (S1.xhi, S2.xlo, S1.xlo, S2.xhi):
                        if abs(e - v) <= 1e-12 * e:
                            pick = e
                if pick is None:
                    pick = cand[0]
                bnds.append((pick, sr))
                return
        elif not is_touching_pair(sl, sr, xl, xr):
            f = lambda x: T_at(sl, x) - T_at(sr, x)
            fl, fr = f(xl), f(xr)
            if fl < 0 < fr or fl == 0 or fr == 0:
                xc = brentq(f, xl, xr, xtol=1e-14 * xr, rtol=1e-15, maxiter=300)
                tc = T_at(sl, xc)
                ok = True
                for j in range(nS):
                    if j not in (sl, sr) and avail(j, xc) and T_at(j, xc) < tc - 1e-12 * tc:
                        ok = False
                if ok:
                    bnds.append((xc, sr))
                    return
        if depth > 80:
            raise RuntimeError("first-arrival resolution failed near x=%r" % xl)
        xmid = 0.5 * (xl + xr)
        sm, _ = argmin_at(xmid)
        resolve(xl, sl, xmid, sm, depth + 1)
        resolve(xmid, sm, xr, sr, depth + 1)

    for k in range(G.size - 1):
        if ids[k] != ids[k + 1]:
            resolve(G[k], int(ids[k]), G[k + 1], int(ids[k + 1]))
    bnds.sort()
    out = []
    cur, xs = int(ids[0]), 0.0
    for xb, snew in bnds:
        if snew == cur:
            continue
        out.append((cur, xs, xb))
        cur, xs = snew, xb
    out.append((cur, xs, xm))
    return [{"kind": segs[j].kind, "index": segs[j].index, "x_start_km": float(a),
             "x_end_km": float(b)} for j, a, b in out]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--panel-nodes", type=int, default=N_PER_PANEL)
    ap.add_argument("--graded-panels", type=int, default=N_GRADED)
    a = ap.parse_args(argv)
    set_rule(a.panel_nodes, a.graded_panels)
    with open(a.model) as f:
        m = Model(json.load(f))
    rep = solve_model(m)
    with open(a.output, "w") as f:
        json.dump(rep, f, indent=1, allow_nan=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
