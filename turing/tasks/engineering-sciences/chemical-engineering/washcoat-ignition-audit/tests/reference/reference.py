#!/usr/bin/env python3
"""Reference A for the washcoat steady-state / stability report (WASHCOAT_SPEC section 4).

Method (see METHOD.md):
  * steady states: two-field shooting from the wall x = 0 with unknowns theta(0) and c(0),
    written with u = ln c and w = u' (Riccati form, stable when integrated from the wall),
    four first-order ODEs plus 12 variational equations, solve_ivp DOP853 (Radau when the
    local Thiele number is large), rtol 1e-12;
  * the steady set is traced by pseudo-arclength continuation in (theta0, q, ln phi), with
    q = -ln(1 - ln c0) so that the very negative ln c0 of ignited states stays bounded;
  * folds: sign changes of d(ln phi)/ds, refined by Brent on det(dF/d(theta0, q)) along the curve;
  * spectrum: second-order conservative finite differences on a sinh-mapped grid clustered at the
    exposed face, discrete steady state recomputed on each grid, rightmost eigenvalues refined by
    Rayleigh-quotient shift-invert iteration on grids N, 2N, 4N, Richardson extrapolation (h^2, h^4);
  * Hopf points: sign changes of Re of tracked complex pairs along the curve, refined by Brent.
"""
import argparse
import json
import math
import sys
import time

import numpy as np
import scipy.linalg as sla
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.integrate import odeint
from scipy.optimize import brentq

RTOL = 1e-12
ATOL = 1e-15
N0 = 100                 # coarsest FD grid (intervals); levels N0, 2N0, 4N0
KAPPA = 6.0              # grid clustering: surface spacing ~ KAPPA / (N k)
ZSAT = 0.6               # fraction of the grid in the geometrically graded zone
DS_MAX = 0.6
ANG_MAX = 0.12
DP_MAX = 0.2
DT2_MAX = 0.08           # max change of d(ln phi)/ds per step (resolves nearly coincident folds)
RTOL_TRACE = 1e-9        # continuation points only bracket events; events are refined at RTOL
TOL_TRACE = 1e-7
N_SCAN = 50              # FD grid (intervals) for candidates and the Hopf scan


class Washcoat:
    def __init__(self, rec, n0=N0, rtol=RTOL):
        self.rec = rec
        self.beta = float(rec["beta"])
        self.gamma = float(rec["gamma"])
        self.Bim = float(rec["Bi_m"])
        self.Bih = float(rec["Bi_h"])
        self.Le = float(rec["Le"])
        self.phi_min = float(rec["phi_min"])
        self.phi_max = float(rec["phi_max"])
        self.queries = [float(v) for v in rec["phi_query"]]
        self.thmax = self.beta * self.Bim / self.Bih
        self.TH = max(self.thmax, 1e-3)       # scale of theta0 in the arclength metric
        self.n0 = n0
        self.rtol = rtol
        self.rtol_now = rtol
        self.nsolve = 0
        self.warnings = []

    # ------------------------------------------------------------------ kinetics
    def R(self, th):
        d = 1.0 + th
        if d < 0.05:
            d = 0.05
        return math.exp(self.gamma * th / d)

    # ------------------------------------------------------------------ shooting
    def _rhs(self, phi, sens):
        b = self.beta
        g = self.gamma
        ph2 = phi * phi
        exp = math.exp

        if not sens:
            def f(x, y):
                th, pt, u, w = y[0], y[1], y[2], y[3]
                d = 1.0 + th
                if d < 0.05:
                    d = 0.05
                src = ph2 * exp(g * th / d)
                e = exp(u) if u < 50.0 else 5.184705528587072e21
                return [pt, -b * src * e, w, src - w * w]
            return f

        def f(x, y):
            th, pt, u, w = y[0], y[1], y[2], y[3]
            d = 1.0 + th
            if d < 0.05:
                d = 0.05
            R = exp(g * th / d)
            e = exp(u) if u < 50.0 else 5.184705528587072e21
            src = ph2 * R
            A2 = -b * src * e
            A1 = A2 * g / (d * d)
            B1 = src * g / (d * d)
            m2w = -2.0 * w
            return [pt, A2, w, src - w * w,
                    y[5], A1 * y[4] + A2 * y[6], y[7], B1 * y[4] + m2w * y[7],
                    y[9], A1 * y[8] + A2 * y[10], y[11], B1 * y[8] + m2w * y[11],
                    y[13], A1 * y[12] + A2 * y[14] + 2.0 * A2 / phi, y[15],
                    B1 * y[12] + m2w * y[15] + 2.0 * src / phi]
        return f

    def _jac(self, phi, sens):
        b = self.beta
        g = self.gamma
        ph2 = phi * phi
        n = 16 if sens else 4
        JJ = np.zeros((n, n))
        for m in range(n // 4):
            JJ[4 * m, 4 * m + 1] = 1.0
            JJ[4 * m + 2, 4 * m + 3] = 1.0

        def jac(x, y):
            th, u, w = y[0], y[2], y[3]
            d = max(1.0 + th, 0.05)
            R = math.exp(g * th / d)
            e = math.exp(u) if u < 50.0 else 5.184705528587072e21
            Rp = R * g / (d * d)
            a10 = -b * ph2 * Rp * e
            a12 = -b * ph2 * R * e
            a30 = ph2 * Rp
            a33 = -2.0 * w
            for m in range(n // 4):
                o = 4 * m
                JJ[o + 1, o] = a10
                JJ[o + 1, o + 2] = a12
                JJ[o + 3, o] = a30
                JJ[o + 3, o + 3] = a33
            return JJ
        return jac

    def shoot(self, th0, u0, phi, sens=True, nodes=None):
        """Integrate from the wall with LSODA (odeint).
        Returns (y1, S1 4x3 wrt (theta0, u0, phi) or None, profile at nodes or None)."""
        self.nsolve += 1
        y0 = [th0, 0.0, u0, 0.0]
        if sens:
            y0 = y0 + [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        tt = [0.0, 1.0] if nodes is None else nodes
        out, info = odeint(self._rhs(phi, sens), y0, tt, Dfun=self._jac(phi, sens), tfirst=True,
                           rtol=self.rtol_now, atol=ATOL, mxstep=500000, full_output=True)
        if info["message"] != "Integration successful.":
            raise RuntimeError("integration failed: " + info["message"])
        y1 = out[-1]
        S1 = y1[4:].reshape(3, 4).T if sens else None
        return y1[:4], S1, (out if nodes is not None else None)

    # residuals in variables z = (theta0, q, p) with u0 = 1 - exp(-q), phi = exp(p)
    @staticmethod
    def u_of_q(q):
        return 1.0 - math.exp(-q)

    def residual(self, z, jac=True):
        th0, q, p = z
        u0 = self.u_of_q(q)
        phi = math.exp(p)
        y1, S1, _ = self.shoot(th0, u0, phi, sens=jac)
        th1, pt1, u1, w1 = y1
        c1 = math.exp(u1) if u1 > -745.0 else 0.0
        F = np.array([pt1 + self.Bih * th1, c1 * (w1 + self.Bim) - self.Bim])
        J = None
        if jac:
            dF1 = S1[1] + self.Bih * S1[0]
            dF2 = c1 * (w1 + self.Bim) * S1[2] + c1 * S1[3]
            J = np.vstack([dF1, dF2])           # wrt (theta0, u0, phi)
            J[:, 1] *= math.exp(-q)              # du0/dq
            J[:, 2] *= phi                       # dphi/dp
        eta = c1 * w1 / (phi * phi)
        return F, J, dict(theta_c=th0, eta=eta, phi=phi, u0=u0)

    # scaled coordinates for the arclength metric
    def to_s(self, z):
        return np.array([z[0] / self.TH, z[1], z[2]])

    def from_s(self, zs):
        return np.array([zs[0] * self.TH, zs[1], zs[2]])

    def Js(self, J):
        Jsc = J.copy()
        Jsc[:, 0] *= self.TH
        return Jsc

    @staticmethod
    def tangent(Jsc, tprev=None):
        t = np.cross(Jsc[0], Jsc[1])
        t /= np.linalg.norm(t)
        if tprev is not None and np.dot(t, tprev) < 0:
            t = -t
        return t

    def newton_fixed_p(self, z, tol=1e-13, maxit=30):
        z = np.array(z, float)
        prev = None
        for it in range(maxit):
            F, J, info = self.residual(z)
            A = J[:, :2]
            dz = np.linalg.solve(A, -F)
            lam = 1.0
            # damping for the starting solve
            while abs(lam * dz[0]) > 0.2 * self.TH or abs(lam * dz[1]) > 2.0:
                lam *= 0.5
            z[:2] += lam * dz
            nd = max(abs(dz[0]) / self.TH, abs(dz[1]) / max(1.0, abs(z[1])))
            floor = lam == 1.0 and prev is not None and nd < 1e-10 and nd > 0.2 * prev
            prev = nd if lam == 1.0 else None
            if lam == 1.0 and (nd < tol or floor):
                F, J, info = self.residual(z)
                return z, J, info
        raise RuntimeError("fixed-p Newton did not converge")

    def correct_arc(self, zs_guess, t, zs_base, ds, tol=1e-12, maxit=8, chord=False, M0=None):
        """Solve F(z)=0, t.(zs - zs_base) = ds starting at zs_guess (scaled coordinates).
        Newton with the variational Jacobian at every iterate, or (chord=True) only at the first
        iterate, later iterates needing just the 4-equation residual integration."""
        zs = np.array(zs_guess, float)
        prev = None
        J = None
        M = M0
        if chord:
            maxit = max(maxit, 30)
        for it in range(maxit):
            z = self.from_s(zs)
            if chord and M is not None:
                F, _, info = self.residual(z, jac=False)
            else:
                F, J, info = self.residual(z)
                M = np.vstack([self.Js(J), t])
            G = np.concatenate([F, [np.dot(t, zs - zs_base) - ds]])
            d = np.linalg.solve(M, -G)
            nd = np.linalg.norm(d)
            limit = 0.9 if chord else 1.5
            noise = max(1e-10, 1e3 * self.rtol_now)       # round-off floor of the ODE solve in zs
            if not np.isfinite(nd) or nd > 0.5 or (prev is not None and nd > limit * prev and nd > 10.0 * noise):
                return None, it
            zs = zs + d
            floor = prev is not None and nd < noise and nd > (0.6 if chord else 0.2) * prev
            prev = nd
            if nd < tol or floor:
                # J and info belong to the previous iterate (|dz| < tol): accurate enough
                info["theta_c"] = zs[0] * self.TH
                return (zs, J, info), it + 1
        return None, maxit

    # ------------------------------------------------------------------ continuation
    def trace(self):
        p_start = math.log(min(0.02, 0.5 * self.phi_min))
        p_end = math.log(self.phi_max)
        z = np.array([0.0, 0.0, p_start])
        self.rtol_now = RTOL_TRACE
        z, J, info = self.newton_fixed_p(z, tol=TOL_TRACE)
        t = self.tangent(self.Js(J))
        if t[2] < 0:
            t = -t
        self.det0 = float(np.sign(np.linalg.det(self.Js(J)[:, :2])))
        pts = [dict(zs=self.to_s(z), t=t, J=J, info=info)]
        ds = 0.05
        nstep = 0
        while True:
            nstep += 1
            if nstep > 4000:
                raise RuntimeError("continuation step budget exceeded")
            cur = pts[-1]
            accepted = False
            for tries in range(40):
                ds = min(ds, DP_MAX / max(abs(cur["t"][2]), 1e-12))
                zs_pred = cur["zs"] + ds * cur["t"]
                res, nit = self.correct_arc(zs_pred, cur["t"], cur["zs"], ds, tol=TOL_TRACE)
                if res is not None:
                    zs_new, Jn, infon = res
                    tn = self.tangent(self.Js(Jn), cur["t"])
                    ang = math.acos(max(-1.0, min(1.0, float(np.dot(tn, cur["t"])))))
                    dp = abs(zs_new[2] - cur["zs"][2])
                    dt2 = abs(tn[2] - cur["t"][2])
                    if ang <= ANG_MAX and dp <= 1.5 * DP_MAX and dt2 <= DT2_MAX:
                        accepted = True
                        break
                ds *= 0.5
                if ds < 1e-9:
                    raise RuntimeError("continuation step underflow")
            if not accepted:
                raise RuntimeError("continuation failed")
            pts.append(dict(zs=zs_new, t=tn, J=Jn, info=infon))
            if nit <= 3 and ang < 0.5 * ANG_MAX and dt2 < 0.5 * DT2_MAX:
                ds = min(DS_MAX, ds * 1.6)
            if zs_new[2] > p_end + 0.02 and tn[2] > 0:
                break
            if zs_new[2] < p_start - 0.5:
                raise RuntimeError("continuation went backwards past start")
        self.pts = pts
        self.rtol_now = self.rtol
        return pts

    def point_at(self, base, s, guess_zs, chord=False):
        res, nit = self.correct_arc(guess_zs, base["t"], base["zs"], s, tol=1e-13, maxit=12, chord=chord)
        if res is None and chord:
            res, nit = self.correct_arc(guess_zs, base["t"], base["zs"], s, tol=1e-13, maxit=12)
        if res is None:
            raise RuntimeError("point_at failed")
        return res

    # ------------------------------------------------------------------ finite differences
    def grid(self, N, a):
        """Mapped grid x = g(xi), xi uniform.  a is None (uniform) or (S, delta, A): with
        zeta = 1 - xi the distance from the exposed face is
            eta(zeta) = (S/A) ln((S + delta e^{A zeta}) / (S + delta)),
        whose density eta' = S delta e^{A zeta} / (S + delta e^{A zeta}) grows geometrically from
        delta at the face and saturates at S in the interior (analytic, so the FD error keeps an
        even expansion in h)."""
        h = 1.0 / N
        xi = np.linspace(0.0, 1.0, N + 1)
        if a is None:
            gp = lambda s: np.ones_like(s)
            x = xi.copy()
        else:
            S, dl, A = a
            def gp(s):
                e = dl * np.exp(A * (1.0 - s))
                return S * e / (S + e)
            x = 1.0 - (S / A) * np.log((S + dl * np.exp(A * (1.0 - xi))) / (S + dl))
            x[0] = 0.0
            x[-1] = 1.0
        g0 = gp(xi)
        gm = gp(xi - 0.5 * h)
        gpl = gp(xi + 0.5 * h)
        L = 1.0 / (g0 * h * h * gm)
        U = 1.0 / (g0 * h * h * gpl)
        return x, h, g0, L, U

    def d2(self, N, a, Bi):
        x, h, g0, L, U = self.grid(N, a)
        lo = L.copy()
        up = U.copy()
        dg = -(L + U)
        # wall: ghost f_{-1} = f_1
        up[0] = U[0] + L[0]
        lo[0] = 0.0
        # surface: ghost f_{N+1} = f_{N-1} - 2 h g'_N Bi f_N
        lo[N] = L[N] + U[N]
        dg[N] = -(L[N] + U[N]) - U[N] * 2.0 * h * g0[N] * Bi
        up[N] = 0.0
        D = sp.diags([lo[1:], dg, up[:-1]], [-1, 0, 1], shape=(N + 1, N + 1), format="csr")
        rhs_bc = U[N] * 2.0 * h * g0[N] * Bi   # coefficient of the far-field value at node N
        return x, D, rhs_bc

    def map_param(self, th0, phi):
        """Grid parameters from the largest local Thiele number k = phi sqrt(R(theta0))."""
        k = phi * math.sqrt(self.R(th0))
        dl = KAPPA / k
        if dl >= 0.5:
            return None
        S = 2.0
        for it in range(60):
            A = math.log(S / dl) / ZSAT
            # solve (S/A) ln((S + dl e^A)/(S + dl)) = 1 for S
            Sn = brentq(lambda v: (v / A) * math.log((v + dl * math.exp(A)) / (v + dl)) - 1.0,
                        1e-3, 1e3, xtol=1e-15)
            if abs(Sn - S) < 1e-13:
                S = Sn
                break
            S = Sn
        A = math.log(S / dl) / ZSAT
        S = brentq(lambda v: (v / A) * math.log((v + dl * math.exp(A)) / (v + dl)) - 1.0, 1e-3, 1e3, xtol=1e-15)
        return (S, dl, A)

    def operator(self, N, a, phi, prof, newton=False):
        """FD matrix M = B^-1 A of the linearised problem on the mapped grid.
        Coefficients come from the shooting profile at the nodes (newton=False), or from the
        discrete FD steady state obtained by Newton from that profile (newton=True, used only
        as an independent cross-check of theta_c at query states)."""
        xT, DT, _ = self.d2(N, a, self.Bih)
        xC, DC, bcC = self.d2(N, a, self.Bim)
        th = prof[:, 0].copy()
        c = np.exp(np.maximum(prof[:, 2], -745.0))
        n = N + 1
        b = self.beta
        g = self.gamma
        ph2 = phi * phi
        if newton:
            prev = 1e300
            for it in range(40):
                d = 1.0 + th
                R = np.exp(g * th / d)
                Rp = R * g / (d * d)
                GT = DT @ th + b * ph2 * R * c
                GC = DC @ c - ph2 * R * c
                GC[-1] += bcC
                a_ = ph2 * Rp * c
                b_ = ph2 * R
                Jm = sp.bmat([[DT + sp.diags(b * a_), sp.diags(b * b_)],
                              [sp.diags(-a_), DC - sp.diags(b_)]], format="csc")
                dlt = spla.spsolve(Jm, -np.concatenate([GT, GC]))
                th += dlt[:n]
                c += dlt[n:]
                nd = max(np.max(np.abs(dlt[:n])) / max(1.0, np.max(np.abs(th))), np.max(np.abs(dlt[n:])))
                if nd < 1e-14:
                    break
                if it >= 2 and nd < 1e-10 and nd > 0.3 * prev:
                    break           # stagnation at round-off level
                prev = nd
            else:
                raise RuntimeError("discrete steady Newton failed")
        d = 1.0 + th
        R = np.exp(g * th / d)
        Rp = R * g / (d * d)
        a_ = ph2 * Rp * c
        b_ = ph2 * R
        A = sp.bmat([[DT + sp.diags(b * a_), sp.diags(b * b_)],
                     [sp.diags(-a_), DC - sp.diags(b_)]], format="csr")
        Binv = sp.diags(np.concatenate([np.full(n, 1.0 / self.Le), np.ones(n)]))
        M = (Binv @ A).tocsc()
        x, h, g0, L, U = self.grid(N, a)
        w = g0 * h
        w[0] *= 0.5
        w[-1] *= 0.5
        return dict(M=M, A=A, theta_c=th[0], x=xT, w=w)

    @staticmethod
    def rqi(M, sigma, real=False, maxit=40, nfixed=3):
        """Shift-invert iteration for the eigenvalue of M nearest sigma: nfixed inverse
        iterations with the fixed shift sigma, then Rayleigh-quotient shift updates."""
        n = M.shape[0]
        rng = np.random.RandomState(12345)
        dtype = float if real else complex
        if real:
            sigma = float(np.real(sigma))
            x = rng.standard_normal(n)
        else:
            x = rng.standard_normal(n) + 1j * rng.standard_normal(n)
        x /= np.linalg.norm(x)
        Mc = sp.csc_matrix(M, dtype=dtype)
        Mc.sort_indices()
        data0 = Mc.data.copy()
        # positions of the diagonal entries in the CSC data (every diagonal entry is stored)
        dpos = np.empty(n, dtype=np.int64)
        for col in range(n):
            lo, hi = Mc.indptr[col], Mc.indptr[col + 1]
            k = lo + np.searchsorted(Mc.indices[lo:hi], col)
            dpos[col] = k
        Ms = Mc.copy()
        prev = float("inf")
        for it in range(maxit):
            Ms.data[:] = data0
            Ms.data[dpos] -= sigma
            try:
                lu = spla.splu(Ms)
            except RuntimeError:
                break               # shift equals an eigenvalue to working precision
            y = lu.solve(x)
            lam = sigma + np.vdot(x, x) / np.vdot(x, y)
            if real:
                lam = float(np.real(lam))
            x = y / np.linalg.norm(y)
            dlt = abs(lam - sigma)
            scale = max(1.0, abs(lam))
            if it < nfixed:
                prev = float("inf")
                if it == nfixed - 1:
                    sigma = lam
                continue
            done = dlt < 1e-14 * scale or (it >= nfixed + 3 and dlt < 1e-9 * scale and dlt > 0.3 * prev)
            prev = dlt
            sigma = lam
            if done:
                break                # converged, or at the round-off floor
        r = M @ x - sigma * x
        return sigma, float(np.linalg.norm(r))

    def spectrum_setup(self, z, n0=None, scan=False):
        """FD operators about the steady state z.  Grids (intervals): N_SCAN (QZ candidates),
        n0, 2 n0, 4 n0 (RQI + Richardson), all nested (n0 a multiple of N_SCAN); scan=True
        builds only N_SCAN and n0."""
        n0 = self.n0 if n0 is None else n0
        th0, q, p = z
        phi = math.exp(p)
        a = self.map_param(th0, phi)
        Ns = [N_SCAN, n0] if scan else [N_SCAN, n0, 2 * n0, 4 * n0]
        Ns = sorted(set(Ns))
        Nf = Ns[-1]
        x = self.grid(Nf, a)[0]
        _, _, prof = self.shoot(th0, self.u_of_q(q), phi, sens=False, nodes=x)
        st = dict(a=a, phi=phi, lev={}, prof=prof, n0=n0, Nf=Nf, cand=N_SCAN)
        for N in Ns:
            st["lev"][N] = self.operator(N, a, phi, prof[::Nf // N])
        return st

    def coarse_eigs(self, st):
        """All eigenvalues of the coarse FD problem, from the weighted generalized form
        (W A) v = lambda (W B) v with W the trapezoidal weights of the mapped grid.  W D2 is
        symmetric, which keeps QZ accurate on strongly graded grids (the plain matrix M is far
        too non-normal there).  Used only to choose candidates for the RQI refinement."""
        lev = st["lev"][st["cand"]]
        w = lev["w"]
        n = w.size
        ww = np.concatenate([w, w])
        WA = (sp.diags(ww) @ lev["A"]).toarray()
        WB = np.diag(np.concatenate([w * self.Le, w]))
        ev = sla.eigvals(WA, WB, overwrite_a=True, check_finite=False)
        ev = ev[np.isfinite(ev)]
        ev = ev[np.argsort(-ev.real)]
        return ev

    def refine(self, st, guess, nfixed=3):
        """Richardson-extrapolated eigenvalue near guess on the grids n0, 2 n0, 4 n0."""
        levels = (st["n0"], 2 * st["n0"], 4 * st["n0"])
        is_real = abs(np.imag(guess)) < 1e-7 * max(1.0, abs(guess))
        vals = []
        g = guess
        for i, m in enumerate(levels):
            lam, res = self.rqi(st["lev"][m]["M"], g, real=is_real, nfixed=nfixed)
            vals.append(lam)
            if i == 0:
                g = lam
            else:
                g = lam + (lam - vals[-2]) / 3.0 * 0.75  # rough h^2 prediction to next level
        l1, l2, l4 = vals
        r12 = (4 * l2 - l1) / 3.0
        r24 = (4 * l4 - l2) / 3.0
        lr = (16 * r24 - r12) / 15.0
        return lr, dict(raw=vals, r12=r12, r24=r24, err=abs(lr - r24))

    def rightmost(self, z, ncand=3, odd=False):
        """Refined rightmost eigenvalues at the steady state z.  odd=True means the shooting
        Jacobian determinant has the opposite sign to the cold start, so an odd number of folds
        lies between: the spectrum must contain a positive real eigenvalue (parity check);
        if none is found the search is widened."""
        st = self.spectrum_setup(z)
        ev = self.coarse_eigs(st)
        out = []
        for attempt, (nc, nf) in enumerate(((ncand, 3), (8, 8))):
            cands = [l for l in ev if l.imag >= -1e-7 * max(1.0, abs(l))][:nc]
            out = []
            for lam in cands:
                lr, d = self.refine(st, lam, nfixed=nf)
                d["guess"] = lam
                out.append((lr, d))
            out.sort(key=lambda v: -v[0].real)
            has_pos_real = any(v[0].real > 0 and abs(v[0].imag) <= 1e-6 * max(1.0, abs(v[0])) for v in out)
            if has_pos_real or not odd:
                break
        st["parity_ok"] = (not odd) or has_pos_real
        return out, st

    # ------------------------------------------------------------------ events
    def classify(self, lam):
        if lam.real < 0:
            return "stable"
        if abs(lam.imag) > 1e-6 * max(1.0, abs(lam)):
            return "unstable_complex"
        return "unstable_real"

    def run(self):
        t0 = time.process_time()
        pts = self.trace()
        t_trace = time.process_time() - t0
        pmin = math.log(self.phi_min)
        pmax = math.log(self.phi_max)
        # ---- folds
        folds = []
        for i in range(len(pts) - 1):
            a, b = pts[i], pts[i + 1]
            if a["t"][2] * b["t"][2] < 0:
                folds.append(self.refine_fold(a, b))
        folds = [f for f in folds if pmin <= math.log(f["phi"]) <= pmax]
        folds.sort(key=lambda f: f["phi"])
        t_fold = time.process_time() - t0 - t_trace
        # ---- query states
        states = []
        for phq in self.queries:
            pq = math.log(phq)
            br = []
            for i in range(len(pts) - 1):
                a, b = pts[i], pts[i + 1]
                fa = a["zs"][2] - pq
                fb = b["zs"][2] - pq
                if fa == 0.0:
                    fa = 1e-300 if fb < 0 else -1e-300
                if fa * fb < 0:
                    w = fa / (fa - fb)
                    zg = self.from_s(a["zs"] + w * (b["zs"] - a["zs"]))
                    zg[2] = pq
                    z, J, info = self.newton_fixed_p(zg)
                    info["det_sign"] = float(np.sign(np.linalg.det(self.Js(J)[:, :2])))
                    br.append((z, info))
            # dedupe
            uniq = []
            for z, info in br:
                if all(abs(z[0] - u[0][0]) > 1e-9 * max(1.0, abs(z[0])) or abs(z[1] - u[0][1]) > 1e-9 for u in uniq):
                    uniq.append((z, info))
            uniq.sort(key=lambda v: v[0][0])
            blist = []
            for z, info in uniq:
                odd = info["det_sign"] != self.det0
                eigs, st = self.rightmost(z, odd=odd)
                lam = eigs[0][0]
                if not st["parity_ok"]:
                    self.warnings.append("parity check failed at phi=%r theta_c=%r" % (phq, z[0]))
                blist.append(dict(theta_c=float(z[0]), eta=float(info["eta"]), stability=self.classify(lam),
                                  _lam=[float(lam.real), float(lam.imag)], _err=float(eigs[0][1]["err"]),
                                  _fd_theta_c_err=float(abs(self._fd_thc(st) - z[0])), _odd=bool(odd),
                                  _cands=[[float(v[0].real), float(v[0].imag)] for v in eigs]))
            states.append(dict(phi=phq, branches=blist))
        t_query = time.process_time() - t0 - t_trace - t_fold
        # ---- Hopf
        hopf = self.find_hopf(pmin, pmax)
        t_hopf = time.process_time() - t0 - t_trace - t_fold - t_query
        self.timing = dict(trace=t_trace, folds=t_fold, queries=t_query, hopf=t_hopf,
                           npts=len(pts), nsolve=self.nsolve, scan_splits=self.scan_stats["split"])
        return dict(folds=folds, hopf_points=hopf, states=states)

    def _fd_thc(self, st):
        try:
            v = [self.operator(N, st["a"], st["phi"], st["prof"][::st["Nf"] // N], newton=True)["theta_c"]
                 for N in (st["n0"], 2 * st["n0"], 4 * st["n0"])]
        except RuntimeError:
            return float("nan")
        r12 = (4 * v[1] - v[0]) / 3
        r24 = (4 * v[2] - v[1]) / 3
        return (16 * r24 - r12) / 15

    def segment(self, a, b, chord=False):
        """Points of the curve between trace points a and b, parametrised by the arclength-like
        coordinate s = t_a . (zs - zs_a); memoised, with guesses interpolated from solved points."""
        sb = float(np.dot(a["t"], b["zs"] - a["zs"]))
        known = [(0.0, a["zs"]), (sb, b["zs"])]
        memo = {}

        def solve(s):
            if s in memo:
                return memo[s]
            near = sorted(known, key=lambda v: abs(v[0] - s))[:2]
            (s0, z0), (s1, z1) = near
            w = (s - s0) / (s1 - s0) if s1 != s0 else 0.0
            guess = z0 + w * (z1 - z0)
            res = self.point_at(a, s, guess, chord=chord)
            memo[s] = res
            known.append((s, res[0]))
            return res
        return sb, solve

    def refine_fold(self, a, b):
        sb, solve = self.segment(a, b)

        def detf(s):
            zs, J, info = solve(s)
            return float(np.linalg.det(self.Js(J)[:, :2]))

        s = brentq(detf, 0.0, sb, xtol=1e-11, rtol=1e-15, maxiter=100)
        zs, J, info = solve(s)
        z = self.from_s(zs)
        kind = "ignition" if a["t"][2] > 0 else "extinction"
        return dict(phi=float(math.exp(z[2])), theta_c=float(z[0]), eta=float(info["eta"]), kind=kind)

    @staticmethod
    def _cpx(l):
        return l.imag > 1e-6 * max(1.0, abs(l))

    @staticmethod
    def _relevant(l):
        return l.real > -(1.0 + 0.5 * abs(l))

    def _scan_ev(self, pt):
        """Rightmost coarse eigenvalues at a curve point: QZ on the N_SCAN grid; relevant complex
        ones improved by one RQI on the 2 N_SCAN grid and h^2 extrapolation."""
        if "ev" not in pt:
            st = self.spectrum_setup(self.from_s(pt["zs"]), n0=2 * N_SCAN, scan=True)
            ev = list(self.coarse_eigs(st)[:12])
            M2 = st["lev"][2 * N_SCAN]["M"]
            for k, l in enumerate(ev):
                if self._cpx(l) and self._relevant(l):
                    l2, _ = self.rqi(M2, l)
                    if abs(l2 - l) < 0.3 * max(1.0, abs(l)):
                        ev[k] = (4.0 * l2 - l) / 3.0
            pt["ev"] = ev
        return pt["ev"]

    def _scan_pair(self, a, b, depth, brackets, stats):
        """Compare the coarse spectra at the curve points a and b.  A relevant complex eigenvalue
        (upper half plane, Re > -(1 + |lambda|/2)) matched to a nearby complex eigenvalue at the
        other end with opposite sign of Re gives a Hopf bracket.  An unmatched or poorly matched
        one, with an eigenvalue of opposite Re sign nearby at the other end (a pair that may have
        crossed and merged inside the step), forces a bisection of the step."""
        A = self._scan_ev(a)
        B = self._scan_ev(b)
        split = False
        for X, Y, fwd in ((A, B, True), (B, A, False)):
            Yc = [l for l in Y if self._cpx(l)]
            for lx in X:
                if not (self._cpx(lx) and self._relevant(lx)):
                    continue
                scale = max(1.0, abs(lx))
                ly = min(Yc, key=lambda v: abs(v - lx)) if Yc else None
                if ly is not None and abs(ly - lx) <= 0.25 * scale:
                    if fwd and lx.real * ly.real < 0:
                        brackets.append((a, b, lx, ly))
                    continue
                near = [l for l in Y if abs(l - lx) <= 0.5 * scale + 2.0 * lx.imag]
                if any(l.real * lx.real <= 0 for l in near) or ly is not None and ly.real * lx.real < 0:
                    split = True
        if split and depth < 6:
            sb = float(np.dot(a["t"], b["zs"] - a["zs"]))
            if abs(sb) > 1e-6:
                guess = 0.5 * (a["zs"] + b["zs"])
                res, nit = self.correct_arc(guess, a["t"], a["zs"], 0.5 * sb, tol=TOL_TRACE, maxit=12)
                if res is not None:
                    zs, J, info = res
                    mid = dict(zs=zs, t=self.tangent(self.Js(J), a["t"]), J=J, info=info)
                    stats["split"] += 1
                    # remove brackets found at this level for (a, b): the halves decide
                    brackets[:] = [br for br in brackets if not (br[0] is a and br[1] is b)]
                    self._scan_pair(a, mid, depth + 1, brackets, stats)
                    self._scan_pair(mid, b, depth + 1, brackets, stats)

    def find_hopf(self, pmin, pmax):
        pts = self.pts
        lo = pmin - 0.05
        hi = pmax + 0.05
        idx = [i for i, p in enumerate(pts) if lo <= p["zs"][2] <= hi]
        if not idx:
            return []
        i0 = max(0, idx[0] - 1)
        i1 = min(len(pts) - 1, idx[-1] + 1)
        self.rtol_now = RTOL_TRACE
        brackets = []
        stats = dict(split=0)
        for i in range(i0, i1):
            self._scan_pair(pts[i], pts[i + 1], 0, brackets, stats)
        self.scan_stats = stats
        self.rtol_now = self.rtol
        hopf = []
        for a, b, la, lb in brackets:
            try:
                hp = self.refine_hopf(a, b, la, lb)
            except RuntimeError as exc:
                self.warnings.append("Hopf bracket near phi=%r abandoned: %s" % (math.exp(a["zs"][2]), exc))
                hp = None
            if hp is not None and pmin <= math.log(hp["phi"]) <= pmax and hp["omega"] > 1e-3:
                if all(abs(hp["phi"] - h["phi"]) > 1e-9 * hp["phi"] or abs(hp["theta_c"] - h["theta_c"]) > 1e-9 for h in hopf):
                    hopf.append(hp)
        hopf.sort(key=lambda h: h["phi"])
        return hopf

    def refine_hopf(self, a, b, la, lb):
        """Brent on Re(lambda) of the tracked complex pair along the curve between the points a
        and b (coarse scan bracket, widened outward with the accurate function if needed).
        Repeated on a doubled base grid, inside a narrow bracket around the previous root, until
        the Richardson error estimate implies |d phi|/phi < 1e-8 and |d omega|/omega < 1e-7
        (at most 4 N0)."""
        sb, solve = self.segment(a, b, chord=True)
        result = None
        s_prev = None
        lam_prev = None
        for n0 in (self.n0, 2 * self.n0, 4 * self.n0):
            memo = {}

            def at(s):
                if s in memo:
                    return memo[s]
                zs, J, info = solve(s)
                st = self.spectrum_setup(self.from_s(zs), n0=n0)
                ev = self.coarse_eigs(st)[:16]
                target = la + (s / sb) * (lb - la) if lam_prev is None else lam_prev
                cands = [l for l in ev if l.imag > 1e-7 * max(1.0, abs(l))]
                if not cands:
                    raise RuntimeError("tracked complex pair lost")
                l0 = min(cands, key=lambda v: abs(v - target))
                lr, d = self.refine(st, l0)
                memo[s] = (zs, info, lr, d)
                return memo[s]

            def f(s):
                return float(at(s)[2].real)

            if s_prev is None:
                lo, hi = 0.0, sb
            else:
                dl = 1e-4 * abs(sb)
                lo, hi = s_prev - dl, s_prev + dl
            step = hi - lo
            try:
                flo, fhi = f(lo), f(hi)
            except RuntimeError:
                return result
            ext = 0
            while flo * fhi > 0 and ext < 10:
                # bracket offset from the accurate root: widen on the side where |Re| is smaller
                ext += 1
                try:
                    if abs(fhi) < abs(flo):
                        lo, flo = hi, fhi
                        hi = hi + step
                        fhi = f(hi)
                    else:
                        hi, fhi = lo, flo
                        lo = lo - step
                        flo = f(lo)
                except RuntimeError:
                    break
                if s_prev is not None:
                    step *= 2.0
            if flo * fhi > 0:
                return result
            s = brentq(f, lo, hi, xtol=1e-11, rtol=1e-15, maxiter=100)
            zs, info, lr, d = at(s)
            # slope of Re(lambda) in ln(phi) near the root, from the closest other sample
            s2 = sorted([v for v in memo if v != s], key=lambda v: abs(v - s))[0]
            zs2, _, lr2, _ = memo[s2]
            slope = abs((lr2.real - lr.real) / (zs2[2] - zs[2])) if zs2[2] != zs[2] else float("inf")
            dphi = d["err"] / max(slope, 1e-300)
            dom = abs((lr - d["r24"]).imag) / max(abs(lr.imag), 1e-300)
            z = self.from_s(zs)
            result = dict(phi=float(math.exp(z[2])), theta_c=float(z[0]), eta=float(info["eta"]),
                          omega=float(abs(lr.imag)))
            self.hopf_err = getattr(self, "hopf_err", []) + [dict(
                n0=n0, phi=result["phi"], omega=result["omega"], err=d["err"], re=float(lr.real),
                dphi_rel_est=dphi, domega_rel_est=dom, nevals=len(memo), raw=[str(v) for v in d["raw"]])]
            if dphi < 1e-8 and dom < 1e-7:
                break
            s_prev = s
            lam_prev = lr
        return result


def strip(report):
    out = dict(recipe_id=report["recipe_id"], folds=report["folds"], hopf_points=report["hopf_points"], states=[])
    for s in report["states"]:
        out["states"].append(dict(phi=s["phi"], branches=[dict(theta_c=b["theta_c"], eta=b["eta"], stability=b["stability"]) for b in s["branches"]]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--debug", default=None, help="optional path for diagnostics JSON")
    ap.add_argument("--n0", type=int, default=N0)
    ap.add_argument("--rtol", type=float, default=RTOL)
    args = ap.parse_args()
    with open(args.recipe, "r", encoding="utf-8") as fh:
        rec = json.load(fh)
    t0 = time.process_time()
    wc = Washcoat(rec, n0=args.n0, rtol=args.rtol)
    rep = wc.run()
    rep["recipe_id"] = rec["recipe_id"]
    # query phi exactly as given
    for s, q in zip(rep["states"], rec["phi_query"]):
        s["phi"] = q
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(strip(rep), fh, indent=1)
    if args.debug:
        dbg = dict(report=rep, timing=wc.timing, wall=time.process_time() - t0,
                   hopf_err=getattr(wc, "hopf_err", []), warnings=wc.warnings)
        with open(args.debug, "w", encoding="utf-8") as fh:
            json.dump(dbg, fh, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
