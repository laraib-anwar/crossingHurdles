#!/usr/bin/env python
"""Reference A: independent answer key for the passive branched-cable task (CABLE_SPEC.md).

Route (deliberately different from the admittance-recursion oracle):

* DC / AC: a nodal admittance matrix over the soma, every branch point, every terminal and
  every query location (query locations split their segment into two cables). Each cable piece
  contributes the exact two-port admittance  G_inf*gamma*[[coth x, -csch x], [-csch x, coth x]]
  with x = gamma*l/lambda, evaluated with overflow-free exponential forms. One dense linear solve
  per injection site gives every potential at once.
* Time constants: the whole tree is propagated as (V, I) transfer pairs (ABCD matrices per
  segment, product rule at junctions) which yields an entire function E(s) with Z_soma = V/E.
  Candidate roots come from a second-order compartmental model solved at two resolutions
  (Richardson extrapolated) and from a dense sign scan; each root is refined with brentq on E;
  completeness is verified with the argument principle on a closed contour around [-1/tau_min, 0]
  and with the compartmental count.
* Coefficients: C_k = tau_k * V(s_k) / E'(s_k) with E' from a complex step (E is entire and
  real on the real axis, so the complex step is exact to rounding).

Usage: python reference.py --neuron <neuron.json> --output <report.json>
"""
import argparse
import json
import math
import sys

import numpy as np
import scipy.linalg
import scipy.optimize
import scipy.sparse
import scipy.sparse.linalg

UM = 1e-4            # um -> cm
NS = 1e-9            # nS -> S
UF = 1e-6            # uF -> F
MS = 1e-3            # ms -> s


# ----------------------------------------------------------------------------------------------
# model
# ----------------------------------------------------------------------------------------------
class Segment:
    __slots__ = ("id", "parent", "L", "d", "Rm", "Ri", "Cm", "end_type", "g_end",
                 "lam", "tau", "Ginf", "children")

    def __init__(self, obj):
        self.id = int(obj["id"])
        self.parent = int(obj["parent"])
        self.L = float(obj["L_um"]) * UM
        self.d = float(obj["d_um"]) * UM
        self.Rm = float(obj["Rm_ohm_cm2"])
        self.Ri = float(obj["Ri_ohm_cm"])
        self.Cm = float(obj["Cm_uF_cm2"]) * UF
        end = obj.get("end")
        if end is None:
            self.end_type = None
            self.g_end = 0.0
        else:
            self.end_type = end["type"]
            self.g_end = float(end["g_nS"]) * NS if self.end_type == "shunt" else 0.0
        self.lam = math.sqrt(self.Rm * self.d / (4.0 * self.Ri))
        self.tau = self.Rm * self.Cm
        self.Ginf = 0.5 * math.pi * self.d ** 1.5 / math.sqrt(self.Rm * self.Ri)
        self.children = []


class Neuron:
    def __init__(self, obj):
        self.obj = obj
        self.neuron_id = obj["neuron_id"]
        soma = obj["soma"]
        ds = float(soma["d_um"]) * UM
        area = math.pi * ds * ds
        self.Gs = area / float(soma["Rm_ohm_cm2"]) + float(soma["shunt_nS"]) * NS
        self.Cs = area * float(soma["Cm_uF_cm2"]) * UF
        self.segs = {}
        for so in obj["segments"]:
            seg = Segment(so)
            self.segs[seg.id] = seg
        self.roots = []
        for seg in self.segs.values():
            if seg.parent == 0:
                self.roots.append(seg)
            else:
                self.segs[seg.parent].children.append(seg)
        for seg in self.segs.values():
            seg.children.sort(key=lambda c: c.id)
        self.roots.sort(key=lambda c: c.id)
        # a segment listed with children but end != null, or without children and end == null
        for seg in self.segs.values():
            if not seg.children and seg.end_type is None:
                seg.end_type = "sealed"
        self.tau_min = float(obj["tau_min_ms"]) * MS
        self.Gref = max(s.Ginf for s in self.segs.values())
        self.tau_max = max(s.tau for s in self.segs.values())
        self.Ltot = sum(s.L for s in self.segs.values())


# ----------------------------------------------------------------------------------------------
# stable hyperbolic helpers (Re x >= 0 assumed for the nodal form)
# ----------------------------------------------------------------------------------------------
def coth_csch(x):
    """coth(x), csch(x) for complex x with Re x > 0, overflow free."""
    e2 = np.exp(-2.0 * x)
    den = -np.expm1(-2.0 * x)            # 1 - e^{-2x}, accurate for small x
    coth = (1.0 + e2) / den
    csch = 2.0 * np.exp(-x) / den
    return coth, csch


def gamma_of(s, tau):
    return np.sqrt(1.0 + s * tau + 0j)


# ----------------------------------------------------------------------------------------------
# nodal network for DC / AC
# ----------------------------------------------------------------------------------------------
def _ratio_terms(x, xi):
    """For complex x (Re x > 0) and 0 <= Re xi <= Re x: returns
    sinh(x - xi)/sinh(x), sinh(xi)/sinh(x)  in overflow-free form."""
    den = -np.expm1(-2.0 * x)
    a = np.exp(-xi) * (-np.expm1(-2.0 * (x - xi))) / den
    b = np.exp(-(x - xi)) * (-np.expm1(-2.0 * xi)) / den
    return a, b


def _green(x, xi, xa):
    """sinh(min) sinh(x - max)/sinh(x) for the killed-killed cable Green's function (times 1/(G gamma))."""
    lo, hi = (xi, xa) if xi.real <= xa.real else (xa, xi)
    den = -np.expm1(-2.0 * x)
    return np.exp(lo - hi) * (-np.expm1(-2.0 * lo)) * (-np.expm1(-2.0 * (x - hi))) / (2.0 * den)


class Network:
    """Nodes: 0 = soma, one per segment distal end (none for a killed terminal).  Interior
    locations are handled analytically: a source inside a segment is replaced by its two end
    currents plus the killed-killed Green's function of that segment, and potentials inside a
    segment follow from the two end potentials by hyperbolic interpolation."""

    def __init__(self, neuron):
        self.nrn = neuron
        self.node_of_seg_end = {}
        nnodes = 1
        for sid in sorted(neuron.segs):
            seg = neuron.segs[sid]
            if seg.end_type == "killed":
                self.node_of_seg_end[sid] = None
            else:
                self.node_of_seg_end[sid] = nnodes
                nnodes += 1
        self.n = nnodes

    def ends(self, sid):
        seg = self.nrn.segs[sid]
        prox = 0 if seg.parent == 0 else self.node_of_seg_end[seg.parent]
        return seg, prox, self.node_of_seg_end[sid]

    def admittance(self, s):
        n = self.n
        Y = np.zeros((n, n), dtype=complex)
        Y[0, 0] += self.nrn.Gs + s * self.nrn.Cs
        for sid in sorted(self.nrn.segs):
            seg, na, nb = self.ends(sid)
            g = gamma_of(s, seg.tau)
            x = g * seg.L / seg.lam
            coth, csch = coth_csch(x)
            a = seg.Ginf * g * coth
            b = seg.Ginf * g * csch
            Y[na, na] += a
            if nb is not None:
                Y[nb, nb] += a
                Y[na, nb] -= b
                Y[nb, na] -= b
            if seg.end_type == "shunt":
                Y[nb, nb] += seg.g_end
        return Y

    def response(self, s, loc_a):
        """Returns a function loc -> complex potential, for a unit current injected at loc_a."""
        Y = self.admittance(s)
        rhs = np.zeros(self.n, dtype=complex)
        sid_a, fa = loc_a
        if sid_a == 0:
            rhs[0] = 1.0
            xa = None
        else:
            seg, na, nb = self.ends(sid_a)
            g = gamma_of(s, seg.tau)
            x = g * seg.L / seg.lam
            xa = fa * x
            fp, fq = _ratio_terms(x, xa)
            rhs[na] += fp
            if nb is not None:
                rhs[nb] += fq
        if s == 0:
            Vn = np.linalg.solve(Y.real, rhs.real).astype(complex)
        else:
            Vn = np.linalg.solve(Y, rhs)

        def at(loc):
            sid, f = loc
            if sid == 0:
                return Vn[0]
            seg, na, nb = self.ends(sid)
            g = gamma_of(s, seg.tau)
            x = g * seg.L / seg.lam
            xi = f * x
            hp, hq = _ratio_terms(x, xi)
            V = hp * Vn[na] + (hq * Vn[nb] if nb is not None else 0.0)
            if sid == sid_a:
                V = V + _green(x, xi, xa) / (seg.Ginf * g)
            return V
        return at

# ----------------------------------------------------------------------------------------------
# entire characteristic function via transfer pairs
# ----------------------------------------------------------------------------------------------
class Characteristic:
    """E(s) with Z_soma(s) = V(s) / E(s); E entire, real on the real axis.

    evaluate(s, scales=None) -> (V, E, scales).  s may be a numpy array (real or complex).
    Positive scale factors (from magnitudes) are recorded so that a later call can reuse them
    (needed for the complex-step derivative: scales must not depend on Im s).
    """

    def __init__(self, neuron):
        self.nrn = neuron
        self.order = []                  # post-order list of segments
        for r in neuron.roots:
            self._post(r)

    def _post(self, seg):
        for c in seg.children:
            self._post(c)
        self.order.append(seg)

    @staticmethod
    def _hyp(x, r):
        """Scaled cosh, sinh/x for complex x and real scale r >= 0: e^{-r} cosh x, e^{-r} sinh(x)/x."""
        ep = np.exp(x - r)
        em = np.exp(-x - r)
        ch = 0.5 * (ep + em)
        small = np.abs(x) < 1e-3
        xs = np.where(small, 1.0, x)
        shc = np.where(small, np.exp(-r) * (1.0 + x * x / 6.0 + x ** 4 / 120.0),
                       0.5 * (ep - em) / xs)
        return ch, shc

    def evaluate(self, s, scales=None):
        s = np.asarray(s, dtype=complex)
        sr = s.real
        rec = []
        use = scales is not None
        k = 0
        Gref = self.nrn.Gref
        pair = {}
        for seg in self.order:
            # (V, I) at the distal end of seg from its load
            if not seg.children:
                if seg.end_type == "killed":
                    V = np.zeros_like(s)
                    I = np.full_like(s, Gref)
                else:
                    V = np.ones_like(s)
                    I = np.full_like(s, seg.g_end)
            else:
                V, I = self._junction([pair[c.id] for c in seg.children], s)
                if use:
                    c = scales[k]
                else:
                    c = 1.0 / np.maximum(np.abs(V), np.abs(I) / Gref)
                    rec.append(c)
                k += 1
                V = V * c
                I = I * c
            g2 = 1.0 + s * seg.tau
            g = np.sqrt(g2)
            x = g * seg.L / seg.lam
            r = np.abs(np.sqrt(1.0 + sr * seg.tau + 0j).real) * seg.L / seg.lam
            ch, shc = self._hyp(x, r)
            lol = seg.L / seg.lam
            # [Vp; Ip] = [[cosh, sinh/(G g)], [G g sinh, cosh]] [Vd; Id]
            Vp = ch * V + (lol * shc / seg.Ginf) * I
            Ip = (seg.Ginf * g2 * lol * shc) * V + ch * I
            pair[seg.id] = (Vp, Ip)
        V, I = self._junction([pair[r.id] for r in self.nrn.roots], s)
        if use:
            c = scales[k]
        else:
            c = 1.0 / np.maximum(np.abs(V), np.abs(I) / Gref)
            rec.append(c)
        V = V * c
        I = I * c
        E = I + (self.nrn.Gs + s * self.nrn.Cs) * V
        return V, E, (scales if use else rec)

    @staticmethod
    def _junction(pairs, s):
        if len(pairs) == 1:
            return pairs[0]
        V = np.ones_like(s)
        for (Vc, Ic) in pairs:
            V = V * Vc
        I = np.zeros_like(s)
        for i, (Vc, Ic) in enumerate(pairs):
            term = Ic.copy()
            for j, (Vo, Io) in enumerate(pairs):
                if j != i:
                    term = term * Vo
            I = I + term
        return V, I

    @staticmethod
    def _hyp_real(u):
        """For real u = x^2: scaled C = e^{-r} cosh x, S = e^{-r} sinh(x)/x with r = Re x >= 0,
        and their u-derivatives holding the scale e^{-r} fixed (exact at a root for V/E')."""
        u = np.asarray(u, dtype=float)
        C = np.empty_like(u)
        S = np.empty_like(u)
        dC = np.empty_like(u)
        dS = np.empty_like(u)
        small = np.abs(u) < 1e-6
        pos = (u >= 0) & ~small
        neg = (u < 0) & ~small
        if pos.any():
            w = np.sqrt(u[pos])
            e2 = np.exp(-2.0 * w)
            C[pos] = 0.5 * (1.0 + e2)
            S[pos] = 0.5 * (1.0 - e2) / w
            dC[pos] = 0.5 * S[pos]
            dS[pos] = (C[pos] - S[pos]) / (2.0 * u[pos])
        if neg.any():
            w = np.sqrt(-u[neg])
            C[neg] = np.cos(w)
            S[neg] = np.sin(w) / w
            dC[neg] = 0.5 * S[neg]
            dS[neg] = (C[neg] - S[neg]) / (2.0 * u[neg])
        if small.any():
            us = u[small]
            er = np.exp(-np.sqrt(np.maximum(us, 0.0)))
            C[small] = er * (1.0 + us / 2.0 + us * us / 24.0)
            S[small] = er * (1.0 + us / 6.0 + us * us / 120.0)
            dC[small] = er * (0.5 + us / 12.0 + us * us / 240.0)
            dS[small] = er * (1.0 / 6.0 + us / 60.0 + us * us / 1680.0)
        return C, S, dC, dS

    def evaluate_real(self, s):
        """Real s (array): returns V, E, dV/ds, dE/ds (scales treated as constants)."""
        s = np.asarray(s, dtype=float)
        Gref = self.nrn.Gref
        pair = {}
        zero = np.zeros_like(s)
        for seg in self.order:
            if not seg.children:
                if seg.end_type == "killed":
                    V, I = zero.copy(), np.full_like(s, Gref)
                else:
                    V, I = np.ones_like(s), np.full_like(s, seg.g_end)
                dV, dI = zero.copy(), zero.copy()
            else:
                V, I, dV, dI = self._junction_d([pair[c.id] for c in seg.children], s)
                c = 1.0 / np.maximum(np.abs(V), np.abs(I) / Gref)
                V, I, dV, dI = V * c, I * c, dV * c, dI * c
            lol = seg.L / seg.lam
            g2 = 1.0 + s * seg.tau
            u = g2 * lol * lol
            du = seg.tau * lol * lol
            C, S, dCu, dSu = self._hyp_real(u)
            dC, dS = dCu * du, dSu * du
            a12 = lol * S / seg.Ginf
            da12 = lol * dS / seg.Ginf
            a21 = seg.Ginf * g2 * lol * S
            da21 = seg.Ginf * lol * (seg.tau * S + g2 * dS)
            Vp = C * V + a12 * I
            Ip = a21 * V + C * I
            dVp = dC * V + C * dV + da12 * I + a12 * dI
            dIp = da21 * V + a21 * dV + dC * I + C * dI
            pair[seg.id] = (Vp, Ip, dVp, dIp)
        V, I, dV, dI = self._junction_d([pair[r.id] for r in self.nrn.roots], s)
        c = 1.0 / np.maximum(np.abs(V), np.abs(I) / Gref)
        V, I, dV, dI = V * c, I * c, dV * c, dI * c
        Ys = self.nrn.Gs + s * self.nrn.Cs
        E = I + Ys * V
        dE = dI + Ys * dV + self.nrn.Cs * V
        return V, E, dV, dE

    @staticmethod
    def _junction_d(pairs, s):
        if len(pairs) == 1:
            return pairs[0]
        n = len(pairs)
        Vs = [p[0] for p in pairs]
        V = np.ones_like(s)
        dV = np.zeros_like(s)
        for i in range(n):
            dV = dV * Vs[i] + V * pairs[i][2]
            V = V * Vs[i]
        I = np.zeros_like(s)
        dI = np.zeros_like(s)
        for i in range(n):
            # product of the other V's and its derivative
            P = np.ones_like(s)
            dP = np.zeros_like(s)
            for j in range(n):
                if j != i:
                    dP = dP * Vs[j] + P * pairs[j][2]
                    P = P * Vs[j]
            I = I + pairs[i][1] * P
            dI = dI + pairs[i][3] * P + pairs[i][1] * dP
        return V, I, dV, dI

    def real(self, s):
        scalar = np.ndim(s) == 0
        V, E, dV, dE = self.evaluate_real(np.atleast_1d(np.asarray(s, dtype=float)))
        return E[0] if scalar else E

    def residue_ratio(self, sk):
        """V(s_k)/E'(s_k) with the analytic derivative (forward-mode), scales frozen."""
        V0, E0, dV, dE = self.evaluate_real(np.array([sk]))
        return V0[0] / dE[0], E0[0], dE[0]


# ----------------------------------------------------------------------------------------------
# compartmental model (second order, vertex centred, lumped membrane)
# ----------------------------------------------------------------------------------------------
def compartmental_eigs(neuron, npoints, s_floor, kmax=None):
    """Eigenvalues s (1/s) of the compartmental tree model with about npoints nodes, all >= s_floor.

    Returns (eigs sorted decreasing (nearest 0 first), n_per_segment dict).
    """
    segs = neuron.segs
    h = neuron.Ltot / npoints
    nseg = {sid: max(2, int(round(seg.L / h))) for sid, seg in segs.items()}
    return _comp_eigs(neuron, nseg, s_floor, kmax), nseg


def _comp_eigs(neuron, nseg, s_floor, kmax):
    segs = neuron.segs
    idx_end = {}
    idx_int = {}
    n = 1
    for sid in sorted(segs):
        idx_int[sid] = list(range(n, n + nseg[sid] - 1))
        n += nseg[sid] - 1
        if segs[sid].end_type != "killed":
            idx_end[sid] = n
            n += 1
        else:
            idx_end[sid] = None
    diagG = np.zeros(n)
    diagC = np.zeros(n)
    rows, cols, vals = [], [], []
    diagG[0] -= neuron.Gs
    diagC[0] += neuron.Cs
    for sid in sorted(segs):
        seg = segs[sid]
        m = nseg[sid]
        hh = seg.L / m
        gm = math.pi * seg.d * hh / seg.Rm
        cm = math.pi * seg.d * hh * seg.Cm
        ga = math.pi * seg.d * seg.d / (4.0 * seg.Ri * hh)
        prox = 0 if seg.parent == 0 else idx_end[seg.parent]
        pts = [prox] + idx_int[sid] + [idx_end[sid]]
        for j, p in enumerate(pts):
            if p is None:
                continue
            w = 0.5 if (j == 0 or j == m) else 1.0
            diagG[p] -= w * gm
            diagC[p] += w * cm
        if seg.end_type == "shunt" and idx_end[sid] is not None:
            diagG[idx_end[sid]] -= seg.g_end
        for a, b in zip(pts[:-1], pts[1:]):
            if a is not None:
                diagG[a] -= ga
            if b is not None:
                diagG[b] -= ga
            if a is not None and b is not None:
                rows += [a, b]
                cols += [b, a]
                vals += [ga, ga]
    G = scipy.sparse.coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()
    G = G + scipy.sparse.diags(diagG)
    dinv = 1.0 / np.sqrt(diagC)
    D = scipy.sparse.diags(dinv)
    A = (D @ G @ D).tocsc()
    if n <= 600:
        w = scipy.linalg.eigh(A.toarray(), eigvals_only=True)
        w = np.sort(w)[::-1]
    else:
        k = 64 if kmax is None else kmax
        v0 = np.ones(n)
        while True:
            k = min(k, n - 2)
            w = scipy.sparse.linalg.eigsh(A, k=k, sigma=0.0, which="LM", v0=v0,
                                          return_eigenvectors=False, tol=1e-13)
            w = np.sort(w)[::-1]
            if w[-1] < s_floor or k >= n - 2:
                break
            k *= 2
    return w[w >= s_floor]


# ----------------------------------------------------------------------------------------------
# argument principle
# ----------------------------------------------------------------------------------------------
def winding_number(func, pts, max_rounds=40):
    """Winding number of func along the closed polygon through pts (complex array, closed by
    returning to pts[0]).  Adaptively refines until consecutive phase steps are < pi/3."""
    pts = np.asarray(pts, dtype=complex)
    vals = func(pts)
    for _ in range(max_rounds):
        nxt = np.roll(vals, -1)
        dphi = np.angle(nxt / vals)
        bad = np.abs(dphi) > math.pi / 3
        if not bad.any():
            break
        idx = np.nonzero(bad)[0]
        mids = 0.5 * (pts[idx] + np.roll(pts, -1)[idx])
        mvals = func(mids)
        pts = np.insert(pts, idx + 1, mids)
        vals = np.insert(vals, idx + 1, mvals)
    else:
        return None
    total = np.sum(np.angle(np.roll(vals, -1) / vals))
    return total / (2.0 * math.pi)


def contour_points(s_left, s_right, eta, n_rays):
    """Closed contour around [s_left, s_right] (s_left < s_right < 0): rays at angle eta."""
    sig = np.geomspace(-s_right, -s_left, n_rays)
    top = -sig + 1j * eta * sig           # from right to left above the axis
    left = np.array([s_left + 1j * eta * (-s_left) * t for t in np.linspace(1, -1, 9)[1:-1]])
    bottom = (-sig - 1j * eta * sig)[::-1]
    right = np.array([s_right - 1j * eta * (-s_right) * t for t in np.linspace(1, -1, 9)[1:-1]])
    return np.concatenate([top, left, bottom, right])


# ----------------------------------------------------------------------------------------------
# modes
# ----------------------------------------------------------------------------------------------
def find_modes(neuron, s_min, log):
    """All roots s_k of E in [s_min, 0) and the coefficients; returns list of (tau_k, C_k) in s, ohm."""
    chi = Characteristic(neuron)

    # --- candidate 1: compartmental model at two resolutions, Richardson extrapolated
    margin = 1.0 + 2e-3
    s_floor = s_min * margin
    comp = None
    try:
        # WKB estimate of the number of modes above s_floor sets the resolution
        n_est = sum(seg.L / seg.lam * math.sqrt(max(-s_floor * seg.tau - 1.0, 0.0))
                    for seg in neuron.segs.values()) / math.pi
        npts = int(max(1500, 40 * n_est))
        w1, nseg1 = compartmental_eigs(neuron, npts, s_floor * 1.1)
        nseg2 = {k: 2 * v for k, v in nseg1.items()}
        w2 = _comp_eigs(neuron, nseg2, s_floor * 1.1, kmax=max(64, 2 * len(w1)))
        m = min(len(w1), len(w2))
        ext = w2[:m] + (w2[:m] - w1[:m]) / 3.0
        err = np.abs(w2[:m] - w1[:m]) / 3.0 + 1e-12 * np.abs(ext)
        keep = ext >= s_floor
        comp = (ext[keep], err[keep])
        log.append("compartmental: n1=%d n2=%d, %d eigen-estimates >= s_floor" %
                   (sum(nseg1.values()), sum(nseg2.values()), int(keep.sum())))
    except Exception as exc:  # pragma: no cover - fallback path
        log.append("compartmental model failed: %r" % (exc,))

    # --- candidate 2: dense geometric sign scan of E on [s_floor, s_hi]
    s_hi = -1e-4 / neuron.tau_max        # E has no zero in (-1/tau_max*1e-4, 0]
    ratio = 2.5e-4
    npts_scan = int(math.ceil(math.log(s_floor / s_hi) / ratio)) + 2
    grid = -np.geomspace(-s_hi, -s_floor, npts_scan)
    Eg = chi.real(grid)
    brackets = []
    for i in range(len(grid) - 1):
        if Eg[i] == 0.0:
            brackets.append((grid[i], grid[i]))
        elif Eg[i] * Eg[i + 1] < 0:
            brackets.append((grid[i + 1], grid[i]))
    roots = []
    for a, b in brackets:
        if a == b:
            roots.append(a)
            continue
        rt = scipy.optimize.brentq(chi.real, a, b, xtol=1e-300, rtol=1e-15, maxiter=200)
        roots.append(rt)
    roots = sorted(roots, reverse=True)
    log.append("scan: %d points, %d sign changes" % (npts_scan, len(brackets)))

    # --- reconcile with compartmental estimates
    if comp is not None:
        ext, err = comp
        roots_arr = np.array(roots)
        unmatched = 0
        maxrel = 0.0
        for e, er in zip(ext, err):
            if len(roots_arr):
                j = np.argmin(np.abs(roots_arr - e))
                rel = abs(roots_arr[j] - e) / abs(e)
            else:
                rel = np.inf
            if rel > 1e-3:
                unmatched += 1
                # try to bracket around the estimate
                for fac in (3.0, 10.0, 30.0):
                    a, b = e - fac * er, e + fac * er
                    if b >= 0:
                        b = -1e-300
                    if chi.real(a) * chi.real(b) < 0:
                        rt = scipy.optimize.brentq(chi.real, a, b, xtol=1e-300, rtol=1e-15,
                                                   maxiter=200)
                        if not len(roots_arr) or np.min(np.abs(roots_arr - rt)) > 1e-9 * abs(rt):
                            roots.append(rt)
                            roots_arr = np.array(sorted(roots, reverse=True))
                        break
            else:
                maxrel = max(maxrel, rel)
        roots = sorted(roots, reverse=True)
        log.append("compartmental vs exact: %d estimates, %d unmatched, max rel dev of "
                   "matched %.2e" % (len(ext), unmatched, maxrel))

    # --- argument principle on a contour around [s_min, s_hi]
    def Ec(z):
        _, E, _ = chi.evaluate(z)
        return E

    n_in = sum(1 for r in roots if r >= s_min)
    wn = None
    try:
        eta = 2e-3
        n_rays = int(math.ceil(math.log(s_min / s_hi) / (eta / 4.0))) + 2
        pts = contour_points(s_min, s_hi, eta, n_rays)
        wn = winding_number(Ec, pts)
    except Exception as exc:  # pragma: no cover
        log.append("winding number failed: %r" % (exc,))
    if wn is not None:
        log.append("argument principle: winding %.6f, roots in [s_min, 0): %d" % (wn, n_in))
        if abs(wn - n_in) > 0.25:
            # denser scan as a fallback
            log.append("MISMATCH: rescanning 10x denser")
            grid = -np.geomspace(-s_hi, -s_floor, 10 * npts_scan)
            Eg = chi.real(grid)
            roots = []
            for i in range(len(grid) - 1):
                if Eg[i] * Eg[i + 1] < 0:
                    roots.append(scipy.optimize.brentq(chi.real, grid[i + 1], grid[i],
                                                       xtol=1e-300, rtol=1e-15, maxiter=200))
                elif Eg[i] == 0.0:
                    roots.append(grid[i])
            roots = sorted(roots, reverse=True)
            n_in = sum(1 for r in roots if r >= s_min)
            log.append("after rescan: %d roots in [s_min, 0)" % n_in)

    # --- coefficients
    modes = []
    for sk in roots:
        if sk < s_min:
            continue
        ratio_ve, E0, dE = chi.residue_ratio(sk)
        tau = -1.0 / sk
        Ck = tau * ratio_ve
        modes.append((tau, Ck))
    return modes


# ----------------------------------------------------------------------------------------------
# report
# ----------------------------------------------------------------------------------------------
def loc_key(loc):
    return (int(loc["segment"]), float(loc["fraction"]))


def finite(x):
    x = float(x)
    if not math.isfinite(x):
        return 0.0
    return x


def compute(obj, log):
    nrn = Neuron(obj)
    net = Network(nrn)
    report = {"neuron_id": obj["neuron_id"]}
    dc_cache = {}

    def dc(loc):
        if loc not in dc_cache:
            dc_cache[loc] = net.response(0.0, loc)
        return dc_cache[loc]

    rin = []
    for site in obj["input_resistance_sites"]:
        a = loc_key(site)
        R = dc(a)(a).real
        rin.append({"site": site, "R_MOhm": finite(R / 1e6)})
    report["input_resistance"] = rin

    att = []
    for p in obj["attenuation_pairs"]:
        a, b = loc_key(p["source"]), loc_key(p["target"])
        if a == b:
            factor = 1.0
        else:
            resp = dc(a)
            Va, Vb = resp(a).real, resp(b).real
            factor = Vb / Va if Va != 0.0 else 0.0
        att.append({"source": p["source"], "target": p["target"], "factor": finite(factor)})
    report["attenuation"] = att

    imp = []
    for q in obj["impedance_queries"]:
        a, b = loc_key(q["source"]), loc_key(q["target"])
        f = float(q["frequency_Hz"])
        s = 1j * 2.0 * math.pi * f
        z = net.response(s, a)(b)
        mag = abs(z) / 1e6
        ph = math.degrees(math.atan2(z.imag, z.real)) if mag > 0 else 0.0
        if ph <= -180.0:
            ph += 360.0
        imp.append({"source": q["source"], "target": q["target"], "frequency_Hz": q["frequency_Hz"],
                    "magnitude_MOhm": finite(mag), "phase_deg": finite(ph)})
    report["impedance"] = imp

    s_min = -1.0 / nrn.tau_min
    modes = find_modes(nrn, s_min, log)
    report["modes"] = [{"tau_ms": finite(t / MS), "coefficient_MOhm": finite(c / 1e6)}
                       for t, c in modes]
    # internal consistency: sum of coefficients vs R_in(soma)
    Rsoma = dc((0, 0.0))((0, 0.0)).real
    log.append("R_in(soma) = %.12g MOhm; sum of reported coefficients = %.12g MOhm (%d modes)" %
               (Rsoma / 1e6, sum(c for _, c in modes) / 1e6, len(modes)))
    return report


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--neuron", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)
    with open(args.neuron, "r", encoding="utf-8") as fh:
        obj = json.load(fh)
    log = []
    report = compute(obj, log)
    text = json.dumps(report, indent=1, allow_nan=False)
    with open(args.output, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.write("\n")
    for line in log:
        print(line, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
