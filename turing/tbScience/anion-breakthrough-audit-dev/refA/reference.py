#!/usr/bin/env python
"""Independent reference solver for IX_SPEC (fixed-bed anion exchange effluent history).

Method: the model is treated as a generic strictly hyperbolic system of conservation laws
    d/dBV [eps x + Lambda y(x)] + d/dxi [x] = 0,   x in R^(n-1) (one fraction eliminated),
and solved with generic machinery only: eigen-decomposition of dy/dx with numpy.linalg.eig,
rarefaction curves by integrating the eigenvector ODE (solve_ivp, DOP853, rtol 1e-12),
shocks by Newton on the Rankine-Hugoniot conditions, Riemann problems by nested root-finding
over wave strengths, and (two feeds) exact front tracking in the (xi, BV) plane with shock-path
ODEs through fans and Riemann re-solves at point interactions.  No h-transformation, no
omega/h roots, no Riemann invariants are used anywhere.

usage: python reference.py --recipe <recipe.json> --output <report.json>
"""
import argparse
import json
import math
import sys

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq, minimize_scalar

IONS = ["chloride", "nitrate", "sulfate", "bicarbonate"]

ODE_RTOL = 1e-12
ODE_ATOL = 1e-14
ZERO_WAVE = 1e-9        # wave strength (composition units) below which a wave is absent
WEAK_SHOCK = 1e-5       # below this strength the shock secant value is taken at the midpoint
GAP_TOL = 1e-9          # BV gap below which two outlet events coincide

DIAG = {"max_reflected": 0.0, "max_rh_residual": 0.0, "interactions": [], "passages": 0}


# ======================================================================================
# Equilibrium map and wave curves
# ======================================================================================
class System:
    """Equilibrium map y(x) for the n present ions, reduced to m = n-1 unknowns."""

    def __init__(self, alpha, eps, Lam):
        self.a = np.asarray(alpha, dtype=float)
        self.n = len(self.a)
        self.m = self.n - 1
        self.b = self.a[:-1] - self.a[-1]
        self.eps = float(eps)
        self.Lam = float(Lam)
        self._I = np.eye(self.m)

    def full(self, x):
        return np.concatenate([x, [1.0 - float(np.sum(x))]])

    def reduce(self, xf):
        return np.asarray(xf[:-1], dtype=float)

    def D(self, x):
        return self.a[-1] + self.b @ x

    def y(self, x):
        return self.a[:-1] * x / self.D(x)

    def J(self, x):
        D = self.D(x)
        return np.diag(self.a[:-1]) / D - np.outer(self.a[:-1] * x, self.b) / (D * D)

    def dJ(self, x):
        """T[i,j,m] = d J_ij / d x_m (analytic)."""
        D = self.D(x)
        ai = self.a[:-1]
        b = self.b
        I = self._I
        T = -np.einsum("ij,m->ijm", I, b) * ai[:, None, None] / (D * D)
        T += -np.einsum("im,j->ijm", I, b) * ai[:, None, None] / (D * D)
        T += 2.0 * np.einsum("i,j,m->ijm", ai * x, b, b) / (D ** 3)
        return T

    def eig(self, x):
        """Eigenvalues sorted decreasing (family 0 = largest lambda = slowest), right
        eigenvectors as columns (unit), left eigenvectors as rows with L @ R = I."""
        lam, R = np.linalg.eig(self.J(x))
        if np.max(np.abs(lam.imag)) > 1e-9 * max(1.0, np.max(np.abs(lam.real))):
            raise RuntimeError("complex eigenvalues at x=%r" % (x,))
        lam = lam.real
        R = R.real
        order = np.argsort(-lam)
        lam = lam[order]
        R = R[:, order]
        L = np.linalg.inv(R)
        return lam, R, L

    def grad_lambda(self, x, k, R, L):
        T = self.dJ(x)
        return np.einsum("i,ijm,j->m", L[k], T, R[:, k])

    def speed(self, lam):
        """dxi/dBV of a characteristic (or shock) with eigenvalue (or secant value) lam."""
        return 1.0 / (self.eps + self.Lam * lam)

    def rare_dir(self, x, k):
        """(lam, r, dlam/ds): unit eigenvector of family k oriented so lambda_k decreases."""
        lam, R, L = self.eig(x)
        r = R[:, k]
        g = self.grad_lambda(x, k, R, L)
        d = g @ r
        if d > 0:
            r = -r
            d = -d
        return lam, r, d

    def unit_eigvec(self, x, k, r_ref):
        lam, R = np.linalg.eig(self.J(x))
        order = np.argsort(-lam.real)
        r = R[:, order[k]].real
        r = r / np.linalg.norm(r)
        if r @ r_ref < 0:
            r = -r
        return r

    def rarefaction(self, x0, k, S, r_ref):
        """Integral curve of r_k from x0 over arc length [0, S]; dense output."""
        def rhs(s, x):
            return self.unit_eigvec(x, k, r_ref)
        sol = solve_ivp(rhs, (0.0, S), x0, method="DOP853", rtol=ODE_RTOL, atol=ODE_ATOL,
                        dense_output=True)
        if not sol.success:
            raise RuntimeError("rarefaction ODE failed: " + sol.message)
        return sol

    def hugoniot(self, x0, k, s, r_ref, lam0):
        """State on the k-Hugoniot locus of x0 with r_ref.(x - x0) = s (s < 0 here).
        Scaled unknowns u = (x - x0)/s and mu:  [y(x0+su) - y(x0)]/s = mu u,  r_ref.u = 1."""
        m = self.m
        y0 = self.y(x0)
        u = r_ref.copy()
        mu = lam0
        for it in range(80):
            x = x0 + s * u
            F = np.empty(m + 1)
            F[:m] = (self.y(x) - y0) / s - mu * u
            F[m] = r_ref @ u - 1.0
            Jm = np.empty((m + 1, m + 1))
            Jm[:m, :m] = self.J(x) - mu * self._I
            Jm[:m, m] = -u
            Jm[m, :m] = r_ref
            Jm[m, m] = 0.0
            dz = np.linalg.solve(Jm, -F)
            if not np.all(np.isfinite(dz)):
                raise RuntimeError("hugoniot Newton produced non-finite step")
            u = u + dz[:m]
            mu = mu + dz[m]
            if np.max(np.abs(dz)) < 1e-15:
                break
        x = x0 + s * u
        return x, mu

    def wave_curve(self, x_from, k, s):
        """Composite k-wave curve from x_from: s>0 rarefaction (lambda_k decreasing), s<0 shock."""
        lam, r, dl = self.rare_dir(x_from, k)
        if s == 0.0:
            return x_from.copy(), {"type": "none"}
        if s > 0.0:
            sol = self.rarefaction(x_from, k, s, r)
            return sol.y[:, -1].copy(), {"type": "rare", "sol": sol, "S": s, "r_ref": r}
        x_to, mu = self.hugoniot(x_from, k, s, r, lam[k])
        if abs(s) < WEAK_SHOCK:
            # the divided difference loses ~1e-16/|s| digits; for a weak shock the secant
            # value equals the eigenvalue at the midpoint up to O(s^2) (generic result)
            mu = self.eig(0.5 * (x_from + x_to))[0][k]
        return x_to, {"type": "shock", "mu": mu}

    # ----------------------------------------------------------------------------------
    def riemann(self, xL, xR, s_init=None):
        """Riemann problem (left state xL, right state xR) by nested root-finding over the
        wave strengths s[0..m-1] (family 0 = slowest).  Returns (waves, s)."""
        m = self.m

        def compose(s):
            x = xL.copy()
            infos = []
            for k in range(m):
                x, info = self.wave_curve(x, k, s[k])
                infos.append((x.copy(), info))
            return x, infos

        def newton(s0, target):
            s = s0.copy()
            try:
                xm, infos = compose(s)
            except Exception:
                return s, False
            for it in range(80):
                res = xm - target
                err = np.max(np.abs(res))
                if err < 1e-13:
                    return s, True
                Jm = np.empty((m, m))
                h = 1e-6
                try:
                    for k in range(m):
                        sp = s.copy(); sp[k] += h
                        sm = s.copy(); sm[k] -= h
                        Jm[:, k] = (compose(sp)[0] - compose(sm)[0]) / (2 * h)
                    ds = np.linalg.solve(Jm, -res)
                except Exception:
                    return s, False
                step = 1.0
                nmax = np.max(np.abs(ds))
                if nmax > 0.5:
                    step = 0.5 / nmax
                accepted = False
                for _ in range(25):
                    s_try = s + step * ds
                    try:
                        xt, it_ = compose(s_try)
                        if np.max(np.abs(xt - target)) < err:
                            accepted = True
                            break
                    except Exception:
                        pass
                    step *= 0.5
                if not accepted:
                    return s, np.max(np.abs(xm - target)) < 1e-11
                s = s_try
                xm, infos = xt, it_
            return s, np.max(np.abs(xm - target)) < 1e-11

        if s_init is None:
            xmid = 0.5 * (xL + xR)
            lam, R, L = self.eig(xmid)
            c = L @ (xR - xL)
            s0 = np.empty(m)
            for k in range(m):
                lamk, r, dl = self.rare_dir(xmid, k)
                s0[k] = c[k] * np.sign(R[:, k] @ r) * np.linalg.norm(R[:, k])
        else:
            s0 = np.asarray(s_init, dtype=float)

        s, ok = newton(s0, xR)
        if not ok:
            nsteps = 4
            ok_all = False
            while nsteps <= 512 and not ok_all:
                ok_all = True
                s_run = np.zeros(m)
                for i in range(1, nsteps + 1):
                    t = i / nsteps
                    target = xL + t * (xR - xL)
                    s_run, ok = newton(s_run, target)
                    if not ok:
                        ok_all = False
                        break
                if ok_all:
                    s = s_run
                nsteps *= 2
            if not ok_all:
                raise RuntimeError("Riemann solver failed to converge")

        x, infos = compose(s)
        waves = []
        xl = xL.copy()
        for k in range(m):
            x_to, info = infos[k]
            if abs(s[k]) < ZERO_WAVE:
                xl = x_to
                continue
            w = {"family": k, "xL": xl.copy(), "xR": x_to.copy(), "strength": s[k]}
            w["lamL"] = self.eig(xl)[0][k]
            w["lamR"] = self.eig(x_to)[0][k]
            if info["type"] == "rare":
                w["type"] = "rare"
                w["sol"] = info["sol"]
                w["S"] = info["S"]
                w["r_ref"] = info["r_ref"]
            else:
                w["type"] = "shock"
                w["mu"] = info["mu"]
                viol = max(w["lamL"] - w["mu"], w["mu"] - w["lamR"], 0.0)
                DIAG["max_lax_violation"] = max(DIAG.get("max_lax_violation", 0.0), float(viol))
                if viol > 1e-7:
                    raise RuntimeError("Lax condition violated for a shock (by %.3e)" % viol)
                res = self.y(x_to) - self.y(xl) - w["mu"] * (x_to - xl)
                DIAG["max_rh_residual"] = max(DIAG["max_rh_residual"], float(np.max(np.abs(res))))
            waves.append(w)
            xl = x_to
        return waves, s


# ======================================================================================
# Wave objects in the (xi, BV) plane
# ======================================================================================
class Shock:
    def __init__(self, sysm, family, xL, xR, mu, xi0, bv0):
        self.sysm = sysm
        self.family = family
        self.xL = np.array(xL, dtype=float)
        self.xR = np.array(xR, dtype=float)
        self.mu = float(mu)
        self.sigma = sysm.speed(mu)
        self.xi0 = float(xi0)
        self.bv0 = float(bv0)
        self.born = float(bv0)
        self.died = None
        self.kind = "shock"

    def xi(self, bv):
        return self.xi0 + self.sigma * (bv - self.bv0)

    def exit_bv(self):
        return self.bv0 + (1.0 - self.xi0) / self.sigma

    def left_edge(self, bv):
        return self.xi(bv), self.sigma

    def right_edge(self, bv):
        return self.xi(bv), self.sigma

    def state_left(self):
        return self.xL

    def state_right(self):
        return self.xR


class Fan:
    """Simple wave of one family: a one-parameter family of straight characteristics p in
    [p_lo, p_hi] (p_lo = tail/slow/left, p_hi = head/fast/right), each carrying a constant
    state and passing through its origin point."""

    def __init__(self, sysm, family, p_lo, p_hi, state, dstate, origin, dorigin, tag=""):
        self.sysm = sysm
        self.family = family
        self.p_lo = float(p_lo)
        self.p_hi = float(p_hi)
        self._state = state
        self._dstate = dstate
        self._origin = origin
        self._dorigin = dorigin
        self.kind = "fan"
        self.tag = tag

    def state(self, p):
        return np.asarray(self._state(p), dtype=float)

    def dstate(self, p):
        return np.asarray(self._dstate(p), dtype=float)

    def origin(self, p):
        return self._origin(p)

    def dorigin(self, p):
        return self._dorigin(p)

    def lam(self, p):
        return self.sysm.eig(self.state(p))[0][self.family]

    def speed(self, p):
        return self.sysm.speed(self.lam(p))

    def speed_dspeed(self, p):
        x = self.state(p)
        lam, R, L = self.sysm.eig(x)
        g = self.sysm.grad_lambda(x, self.family, R, L)
        dl = g @ self.dstate(p)
        s = self.sysm.speed(lam[self.family])
        return s, -self.sysm.Lam * dl * s * s

    def xi_at(self, p, bv):
        xi0, bv0 = self.origin(p)
        return xi0 + self.speed(p) * (bv - bv0)

    def exit_bv(self, p):
        xi0, bv0 = self.origin(p)
        return bv0 + (1.0 - xi0) / self.speed(p)

    def left_edge(self, bv):
        return self.xi_at(self.p_lo, bv), self.speed(self.p_lo)

    def right_edge(self, bv):
        return self.xi_at(self.p_hi, bv), self.speed(self.p_hi)

    def state_left(self):
        return self.state(self.p_lo)

    def state_right(self):
        return self.state(self.p_hi)

    def empty(self):
        return self.p_hi - self.p_lo <= 0.0


def centered_fan(sysm, w, xi_c, bv_c, tag=""):
    sol = w["sol"]
    k = w["family"]
    r_ref = w["r_ref"]

    def state(p):
        return sol.sol(p)

    def dstate(p):
        return sysm.unit_eigvec(sol.sol(p), k, r_ref)

    def origin(p):
        return (xi_c, bv_c)

    def dorigin(p):
        return (0.0, 0.0)

    return Fan(sysm, k, 0.0, w["S"], state, dstate, origin, dorigin, tag=tag)


def make_waves(sysm, waves, xi_c, bv_c, tag=""):
    out = []
    for w in waves:
        if w["type"] == "shock":
            out.append(Shock(sysm, w["family"], w["xL"], w["xR"], w["mu"], xi_c, bv_c))
        else:
            out.append(centered_fan(sysm, w, xi_c, bv_c, tag=tag))
    return out


# ======================================================================================
# Shock passing through a fan of another (or the same) family
# ======================================================================================
class Passage:
    """Integrates a shock through the characteristics p of a fan.  The state on the fan side
    of the shock is known (fan state); the state on the other side and the shock's secant
    value mu obey the differentiated Rankine-Hugoniot conditions; the unknown-side state is
    allowed to move along every eigen-direction except the shock's own family (the components
    along families other than the fan's are 'reflected waves' and must come out ~0)."""

    def __init__(self, sysm, shock, fan, side, bv_start):
        self.sysm = sysm
        self.shock = shock
        self.fan = fan
        self.side = side      # 'R': fan is on the right of the shock; 'L': fan on the left
        m = sysm.m
        self.m = m
        j = shock.family
        self.others = [f for f in range(m) if f != j]
        if side == "R":
            p_start, p_end = fan.p_lo, fan.p_hi
            x_unk0 = shock.xL
        else:
            p_start, p_end = fan.p_hi, fan.p_lo
            x_unk0 = shock.xR
        self.p_start = p_start
        u0 = np.concatenate([[bv_start], x_unk0, [shock.mu]])
        self.reflected = 0.0

        def rhs(p, u):
            return self._rhs(p, u)

        def hit_outlet(p, u):
            return self.fan.xi_at(p, u[0]) - 1.0
        hit_outlet.terminal = True

        sol = solve_ivp(rhs, (p_start, p_end), u0, method="DOP853", rtol=ODE_RTOL,
                        atol=ODE_ATOL, dense_output=True, events=hit_outlet)
        if not sol.success:
            raise RuntimeError("passage ODE failed: " + sol.message)
        self.sol = sol
        if sol.t_events[0].size > 0:
            self.p_end = float(sol.t_events[0][0])
            self.hit_outlet = True
        else:
            self.p_end = float(p_end)
            self.hit_outlet = False
        DIAG["max_reflected"] = max(DIAG["max_reflected"], self.reflected)
        DIAG["passages"] += 1

    def _rhs(self, p, u):
        sysm = self.sysm
        m = self.m
        fan = self.fan
        bv = u[0]
        x_unk = u[1:1 + m]
        mu = u[1 + m]
        x_kn = fan.state(p)
        dx_kn = fan.dstate(p)
        s, ds = fan.speed_dspeed(p)
        xi0, bv0 = fan.origin(p)
        dxi0, dbv0 = fan.dorigin(p)
        sigma = sysm.speed(mu)
        dbv = (dxi0 - s * dbv0 + ds * (bv - bv0)) / (sigma - s)
        lam_u, R_u, L_u = sysm.eig(x_unk)
        A = np.empty((m, m))
        for c, f in enumerate(self.others):
            A[:, c] = (lam_u[f] - mu) * R_u[:, f]
        A[:, m - 1] = -(x_unk - x_kn)
        rhs_vec = (sysm.J(x_kn) - mu * sysm._I) @ dx_kn
        coef = np.linalg.solve(A, rhs_vec)
        dx_unk = R_u[:, self.others] @ coef[:m - 1]
        dmu = coef[m - 1]
        # reflected components: along families other than the fan's and the shock's
        for c, f in enumerate(self.others):
            if f != fan.family:
                self.reflected = max(self.reflected, abs(coef[c]) / max(1e-300, np.linalg.norm(dx_kn)))
        out = np.empty(2 + m)
        out[0] = dbv
        out[1:1 + m] = dx_unk
        out[1 + m] = dmu
        return out

    # evaluation helpers --------------------------------------------------------------
    def u(self, p):
        return self.sol.sol(p)

    def bv(self, p):
        return float(self.sol.sol(p)[0])

    def x_unk(self, p):
        return self.sol.sol(p)[1:1 + self.m]

    def mu(self, p):
        return float(self.sol.sol(p)[1 + self.m])

    def xi(self, p):
        return self.fan.xi_at(p, self.bv(p))

    def dx_unk(self, p):
        return self._rhs(p, self.u(p))[1:1 + self.m]

    def dpath(self, p):
        """(dxi/dp, dbv/dp) of the shock path."""
        d = self._rhs(p, self.u(p))
        sigma = self.sysm.speed(self.u(p)[1 + self.m])
        return sigma * d[0], d[0]

    def p_of_bv(self, bv_target):
        a, b = self.p_start, self.p_end
        f = lambda p: self.bv(p) - bv_target
        return brentq(f, a, b, xtol=1e-14, rtol=1e-15, maxiter=200)

    def refracted_fan(self, p_a, p_b, tag=""):
        """Fan of the transmitted characteristics p in [p_a, p_b] (any order given)."""
        lo, hi = (p_a, p_b) if p_a <= p_b else (p_b, p_a)
        return Fan(self.sysm, self.fan.family, lo, hi,
                   self.x_unk, self.dx_unk,
                   lambda p: (self.xi(p), self.bv(p)),
                   self.dpath, tag=tag)

    def shock_at(self, p):
        """Straight shock continuing from the passage point p."""
        u = self.u(p)
        bv = u[0]
        x_unk = u[1:1 + self.m]
        mu = u[1 + self.m]
        x_kn = self.fan.state(p)
        xi = self.fan.xi_at(p, bv)
        if self.side == "R":
            xL, xR = x_unk, x_kn
        else:
            xL, xR = x_kn, x_unk
        res = self.sysm.y(xR) - self.sysm.y(xL) - mu * (xR - xL)
        DIAG["max_rh_residual"] = max(DIAG["max_rh_residual"], float(np.max(np.abs(res))))
        return Shock(self.sysm, self.shock.family, xL, xR, mu, xi, bv)


# ======================================================================================
# Front tracking
# ======================================================================================
def meeting(wa, wb, bv_now):
    """Earliest BV >= bv_now at which the right edge of wa meets the left edge of wb,
    assuming straight motion; None if they do not approach."""
    xa, sa = wa.right_edge(bv_now)
    xb, sb = wb.left_edge(bv_now)
    gap = xb - xa
    if gap < -1e-9:
        # should not happen; treat as touching
        gap = 0.0
    if gap <= 1e-13:
        if sa > sb:
            return bv_now, xa
        return None
    if sa <= sb:
        return None
    dt = gap / (sa - sb)
    return bv_now + dt, xa + sa * dt


def meeting_curve(path, edge_xi, edge_speed, edge_bv_ref):
    """Meeting of a straight edge  xi = edge_xi + edge_speed (bv - edge_bv_ref)  with the
    curved shock path of a Passage; returns p or None."""
    def g(p):
        bv = path.bv(p)
        return (edge_xi + edge_speed * (bv - edge_bv_ref)) - path.xi(p)
    a, b = path.p_start, path.p_end
    ga, gb = g(a), g(b)
    if ga == 0.0:
        return a
    if ga * gb > 0:
        return None
    return brentq(g, a, b, xtol=1e-14, rtol=1e-15, maxiter=200)


class Tracker:
    def __init__(self, sysm, run_bv):
        self.sysm = sysm
        self.run_bv = run_bv
        self.active = []       # waves ordered left (inlet) to right (outlet)
        self.all = []          # every wave ever created
        self.bv_now = 0.0
        self.n_events = 0

    def add(self, waves, index=None):
        for w in waves:
            self.all.append(w)
        if index is None:
            self.active.extend(waves)
        else:
            self.active[index:index] = waves

    def kill(self, w, bv):
        if isinstance(w, Shock):
            w.died = bv
        self.active.remove(w)

    def prune_exited(self):
        """Drop waves that have completely left the bed at bv_now."""
        keep = []
        for w in self.active:
            xi_l, _ = w.left_edge(self.bv_now)
            if xi_l > 1.0 + 1e-12:
                continue
            keep.append(w)
        self.active = keep

    def next_event(self):
        best = None
        for i in range(len(self.active) - 1):
            wa, wb = self.active[i], self.active[i + 1]
            mt = meeting(wa, wb, self.bv_now)
            if mt is None:
                continue
            bv_m, xi_m = mt
            if xi_m > 1.0 + 1e-12 or bv_m > self.run_bv:
                continue
            if best is None or bv_m < best[0]:
                best = (bv_m, xi_m, i)
        return best

    def run(self):
        while True:
            self.prune_exited()
            ev = self.next_event()
            if ev is None:
                return
            self.n_events += 1
            if self.n_events > 500:
                raise RuntimeError("too many interactions")
            bv_m, xi_m, i = ev
            wa, wb = self.active[i], self.active[i + 1]
            self.bv_now = max(self.bv_now, bv_m)
            if isinstance(wa, Shock) and isinstance(wb, Shock):
                self.shock_shock(i, wa, wb, bv_m, xi_m)
            elif isinstance(wa, Shock) and isinstance(wb, Fan):
                self.shock_fan(i, wa, wb, "R", bv_m)
            elif isinstance(wa, Fan) and isinstance(wb, Shock):
                self.shock_fan(i, wb, wa, "L", bv_m)
            else:
                raise NotImplementedError("rarefaction-rarefaction interaction of families %d and %d at BV %.6f, xi %.6f"
                                          % (wa.family, wb.family, bv_m, xi_m))

    def shock_shock(self, i, wa, wb, bv_m, xi_m):
        xL = wa.xL
        xR = wb.xR
        waves, s = self.sysm.riemann(xL, xR)
        DIAG["interactions"].append({"type": "shock-shock", "families": [wa.family, wb.family],
                                     "bv": bv_m, "xi": xi_m,
                                     "out": [(w["family"], w["type"]) for w in waves],
                                     "strengths": [float(v) for v in s]})
        self.kill(wa, bv_m)
        self.kill(wb, bv_m)
        new = make_waves(self.sysm, waves, xi_m, bv_m, tag="ss@%.4f" % bv_m)
        self.add(new, index=i)

    def shock_fan(self, i, shock, fan, side, bv_m):
        """Shock at active index (i or i+1) passes through the adjacent fan."""
        sysm = self.sysm
        passage = Passage(sysm, shock, fan, side, bv_m)
        p_s, p_e = passage.p_start, passage.p_end
        bv_e = passage.bv(p_e)
        # Earliest interference by any other wave before bv_e
        bv_cut = None
        idx_shock = self.active.index(shock)
        idx_fan = self.active.index(fan)
        # (a) pairs not involving shock or fan, straight motion
        for q in range(len(self.active) - 1):
            wq, wr = self.active[q], self.active[q + 1]
            if shock in (wq, wr) or fan in (wq, wr):
                continue
            mt = meeting(wq, wr, self.bv_now)
            if mt is None or mt[1] > 1.0 + 1e-12 or mt[0] > self.run_bv:
                continue
            if bv_cut is None or mt[0] < bv_cut:
                bv_cut = mt[0]
        # (b) the fan's far edge against its other neighbour (straight motion)
        if side == "R":
            # fan to the right of the shock: far edge = fan head vs next wave to the right
            if idx_fan + 1 < len(self.active):
                mt = meeting(fan, self.active[idx_fan + 1], self.bv_now)
                if mt is not None and mt[1] <= 1.0 + 1e-12 and mt[0] <= self.run_bv:
                    if bv_cut is None or mt[0] < bv_cut:
                        bv_cut = mt[0]
            # the shock's other neighbour (to its left) against the curved shock path
            if idx_shock - 1 >= 0:
                nb = self.active[idx_shock - 1]
                exi, esp = nb.right_edge(self.bv_now)
                p_hit = meeting_curve(passage, exi, esp, self.bv_now)
                if p_hit is not None:
                    bvh = passage.bv(p_hit)
                    if bvh <= self.run_bv and (bv_cut is None or bvh < bv_cut):
                        bv_cut = bvh
        else:
            if idx_fan - 1 >= 0:
                mt = meeting(self.active[idx_fan - 1], fan, self.bv_now)
                if mt is not None and mt[1] <= 1.0 + 1e-12 and mt[0] <= self.run_bv:
                    if bv_cut is None or mt[0] < bv_cut:
                        bv_cut = mt[0]
            if idx_shock + 1 < len(self.active):
                nb = self.active[idx_shock + 1]
                exi, esp = nb.left_edge(self.bv_now)
                p_hit = meeting_curve(passage, exi, esp, self.bv_now)
                if p_hit is not None:
                    bvh = passage.bv(p_hit)
                    if bvh <= self.run_bv and (bv_cut is None or bvh < bv_cut):
                        bv_cut = bvh
        truncated = False
        if bv_cut is not None and bv_cut < bv_e - 1e-12:
            p_e = passage.p_of_bv(bv_cut)
            truncated = True
        bv_e = passage.bv(p_e)
        DIAG["interactions"].append({"type": "shock-fan", "families": [shock.family, fan.family],
                                     "side": side, "bv_start": bv_m, "bv_end": bv_e,
                                     "xi_end": passage.xi(p_e), "truncated": truncated,
                                     "hit_outlet": passage.hit_outlet and not truncated,
                                     "p_range": [p_s, p_e]})
        # new straight shock from the end point
        new_shock = passage.shock_at(p_e)
        # refracted fan (transmitted characteristics)
        refr = passage.refracted_fan(p_s, p_e, tag="refr@%.4f" % bv_m)
        x_a = refr.state(refr.p_lo)
        x_b = refr.state(refr.p_hi)
        refr_nonzero = np.max(np.abs(x_a - x_b)) > ZERO_WAVE
        # remaining (unreached) part of the incident fan
        if side == "R":
            fan.p_lo = p_e
        else:
            fan.p_hi = p_e
        fan_remaining = not fan.empty()
        # rebuild the local ordering
        shock.died = bv_e
        self.active.remove(shock)
        pos = self.active.index(fan)
        self.active.remove(fan)
        self.all.append(new_shock)
        if side == "R":
            seq = []
            if refr_nonzero:
                seq.append(refr)
                self.all.append(refr)
            seq.append(new_shock)
            if fan_remaining:
                seq.append(fan)
        else:
            seq = []
            if fan_remaining:
                seq.append(fan)
            seq.append(new_shock)
            if refr_nonzero:
                seq.append(refr)
                self.all.append(refr)
        self.active[pos:pos] = seq
        self.bv_now = bv_e


# ======================================================================================
# Outlet history
# ======================================================================================
def outlet_pieces(tracker, run_bv):
    """Collect the outlet events: shocks (point) and fan pieces (intervals) within [0, run_bv]."""
    pieces = []
    for w in tracker.all:
        if isinstance(w, Shock):
            if w.died is not None:
                continue
            bv = w.exit_bv()
            if bv <= run_bv + 1e-12 and bv >= w.born - 1e-12:
                pieces.append({"kind": "shock", "bv": min(bv, run_bv), "before": w.xR, "after": w.xL, "obj": w})
        else:
            if w.empty():
                continue
            bv_hi = w.exit_bv(w.p_hi)   # head exits first
            bv_lo = w.exit_bv(w.p_lo)
            if bv_hi > bv_lo:
                raise RuntimeError("fan characteristics cross at the outlet")
            if bv_hi > run_bv:
                continue
            p_lo_eff = w.p_lo
            if bv_lo > run_bv:
                p_lo_eff = brentq(lambda p: w.exit_bv(p) - run_bv, w.p_lo, w.p_hi, xtol=1e-15, rtol=1e-15, maxiter=200)
                bv_lo = run_bv
            if bv_lo - bv_hi <= GAP_TOL:
                continue
            pieces.append({"kind": "fan", "bv_start": bv_hi, "bv_end": bv_lo, "obj": w,
                           "p_start": w.p_hi, "p_end": p_lo_eff})
    pieces.sort(key=lambda pc: pc["bv"] if pc["kind"] == "shock" else pc["bv_start"])
    return pieces


def fan_state_at_bv(fan, p_a, p_b, bv):
    """State of the fan characteristic that exits at BV = bv (p between p_a and p_b)."""
    lo, hi = (p_a, p_b) if p_a <= p_b else (p_b, p_a)
    f = lambda p: fan.exit_bv(p) - bv
    fl, fh = f(lo), f(hi)
    if fl * fh > 0:
        # bv outside; clamp to the nearer end
        return fan.state(lo if abs(fl) < abs(fh) else hi)
    p = brentq(f, lo, hi, xtol=1e-15, rtol=1e-15, maxiter=200)
    return fan.state(p)


def build_history(sysm, pieces, x_bed, run_bv):
    """Partition [0, run_bv] into plateaus, transitions and shocks (reduced states)."""
    segs = []   # list of dicts in BV order
    bv = 0.0
    state = np.array(x_bed, dtype=float)
    for pc in pieces:
        if pc["kind"] == "shock":
            b = pc["bv"]
            if b - bv > GAP_TOL:
                segs.append({"kind": "plateau", "bv_start": bv, "bv_end": b, "x": state.copy()})
            if np.max(np.abs(pc["before"] - state)) > 1e-7:
                raise RuntimeError("inconsistent state before shock at BV %.9f: %r vs %r" % (b, pc["before"], state))
            segs.append({"kind": "shock", "bv": b, "before": state.copy(), "after": pc["after"].copy()})
            state = pc["after"].copy()
            bv = b
        else:
            b0, b1 = pc["bv_start"], pc["bv_end"]
            if b0 - bv > GAP_TOL:
                segs.append({"kind": "plateau", "bv_start": bv, "bv_end": b0, "x": state.copy()})
            fan = pc["obj"]
            xs = fan.state(pc["p_start"])
            xe = fan.state(pc["p_end"])
            if np.max(np.abs(xs - state)) > 1e-7:
                raise RuntimeError("inconsistent state at transition start BV %.9f: %r vs %r" % (b0, xs, state))
            segs.append({"kind": "transition", "bv_start": b0, "bv_end": b1, "x_start": xs, "x_end": xe,
                         "fan": fan, "p_start": pc["p_start"], "p_end": pc["p_end"]})
            state = xe.copy()
            bv = b1
    if run_bv - bv > GAP_TOL:
        segs.append({"kind": "plateau", "bv_start": bv, "bv_end": run_bv, "x": state.copy()})
    # merge adjacent transitions that are continuous across their junction (same composition)
    merged = []
    for sg in segs:
        if merged and sg["kind"] == "transition" and merged[-1]["kind"] == "transition" \
                and abs(merged[-1]["bv_end"] - sg["bv_start"]) <= GAP_TOL \
                and np.max(np.abs(merged[-1]["x_end"] - sg["x_start"])) < 1e-7:
            prev = merged[-1]
            new = {"kind": "transition", "bv_start": prev["bv_start"], "bv_end": sg["bv_end"],
                   "x_start": prev["x_start"], "x_end": sg["x_end"],
                   "parts": prev.get("parts", [prev]) + [sg]}
            merged[-1] = new
        else:
            merged.append(sg)
    return merged


def transition_state(seg, bv):
    parts = seg.get("parts", [seg])
    for part in parts:
        if part["bv_start"] - 1e-9 <= bv <= part["bv_end"] + 1e-9:
            return fan_state_at_bv(part["fan"], part["p_start"], part["p_end"], bv)
    raise RuntimeError("bv outside transition")


def state_at_bv(segs, bv):
    for sg in segs:
        if sg["kind"] == "plateau" and sg["bv_start"] - 1e-9 <= bv <= sg["bv_end"] + 1e-9:
            return sg["x"]
        if sg["kind"] == "transition" and sg["bv_start"] - 1e-9 <= bv <= sg["bv_end"] + 1e-9:
            return transition_state(sg, bv)
    for sg in segs:
        if sg["kind"] == "shock" and abs(sg["bv"] - bv) <= 1e-9:
            return sg["after"]
    raise RuntimeError("bv %r not covered" % bv)


# ======================================================================================
# Report
# ======================================================================================
def to_meq(sysm, x, present, CT):
    xf = sysm.full(np.asarray(x, dtype=float))
    out = np.zeros(4)
    out[present] = xf
    out[np.abs(out) < 1e-13] = 0.0
    return [float(v) for v in out * CT]


def nitrate_of(sysm, x, present, CT):
    return to_meq(sysm, x, present, CT)[1]


def analyse_transition(sysm, seg, present, CT, limit, npts=400):
    """Return (peak value, bv of peak, first bv exceeding limit or None) inside a transition.
    The scan runs over the fan parameter p (from the first-exiting characteristic p_start to
    the last p_end), which is cheaper and better conditioned than scanning in BV."""
    parts = seg.get("parts", [seg])
    peak_v = -np.inf
    peak_bv = None
    cross = None
    for part in parts:
        fan = part["fan"]
        ps = np.linspace(part["p_start"], part["p_end"], npts)   # increasing BV order
        vals = np.array([nitrate_of(sysm, fan.state(p), present, CT) for p in ps])
        nit = lambda p: nitrate_of(sysm, fan.state(p), present, CT)
        i = int(np.argmax(vals))
        cand = [(vals[i], ps[i]), (vals[0], ps[0]), (vals[-1], ps[-1])]
        lo = min(ps[max(i - 1, 0)], ps[min(i + 1, npts - 1)])
        hi = max(ps[max(i - 1, 0)], ps[min(i + 1, npts - 1)])
        if hi > lo:
            res = minimize_scalar(lambda p: -nit(p), bounds=(lo, hi), method="bounded",
                                  options={"xatol": 1e-13})
            cand.append((-res.fun, float(res.x)))
        v_best = max(c[0] for c in cand)
        # among (near-)equal maxima take the earliest BV = the largest exit_bv-ordered first
        bvs_best = [fan.exit_bv(c[1]) for c in cand if c[0] >= v_best - 1e-13]
        b_best = min(bvs_best)
        if v_best > peak_v + 1e-13 or (abs(v_best - peak_v) <= 1e-13 and b_best < peak_bv):
            peak_v, peak_bv = v_best, b_best
        if cross is None:
            if vals[0] > limit:
                cross = part["bv_start"]
            else:
                g = lambda p: nit(p) - limit
                for q in range(1, npts):
                    if vals[q] > limit:
                        pa, pb = ps[q - 1], ps[q]
                        pc = brentq(g, min(pa, pb), max(pa, pb), xtol=1e-15, rtol=1e-15, maxiter=200)
                        cross = fan.exit_bv(pc)
                        break
    return peak_v, peak_bv, cross


def solve_recipe(rec):
    a_all = np.array([rec["alpha"][i] for i in IONS], dtype=float)
    CT = float(rec["C_T_meq_per_L"])
    Lam = 1000.0 * float(rec["Q_eq_per_L_bed"]) / CT
    eps = float(rec["eps"])
    run_bv = float(rec["run_bv"])
    y0 = np.array([rec["initial_resin_fraction"][i] for i in IONS], dtype=float)
    x0 = y0 / a_all
    x0 = x0 / x0.sum()
    feeds = []
    for f in rec["feed_program"]:
        xf = np.array([f["composition_meq_per_L"][i] for i in IONS], dtype=float) / CT
        feeds.append((float(f["start_bv"]), xf))
    feeds.sort(key=lambda t: t[0])
    present = [i for i in range(4) if x0[i] > 0 or any(xf[i] > 0 for _, xf in feeds)]
    sysm = System(a_all[present], eps, Lam)
    x_bed = sysm.reduce(x0[present])
    tracker = Tracker(sysm, run_bv)

    # first feed: Riemann problem centred at (xi=0, BV=0)
    xf1 = sysm.reduce(feeds[0][1][present])
    waves, s = sysm.riemann(xf1, x_bed)
    DIAG["riemann_first"] = {"strengths": [float(v) for v in s],
                             "waves": [(w["family"], w["type"]) for w in waves]}
    tracker.add(make_waves(sysm, waves, 0.0, 0.0, tag="feed1"))
    x_inlet = xf1
    if len(feeds) > 1:
        bv2, xf2full = feeds[1]
        xf2 = sysm.reduce(xf2full[present])
        if bv2 < run_bv:
            tracker.bv_now = bv2
            tracker.prune_exited()
            waves2, s2 = sysm.riemann(xf2, x_inlet)
            DIAG["riemann_second"] = {"strengths": [float(v) for v in s2],
                                      "waves": [(w["family"], w["type"]) for w in waves2]}
            tracker.add(make_waves(sysm, waves2, 0.0, bv2, tag="feed2"), index=0)
            tracker.run()
    pieces = outlet_pieces(tracker, run_bv)
    segs = build_history(sysm, pieces, x_bed, run_bv)

    limit = float(rec["nitrate_limit_meq_per_L"])
    report = {"recipe_id": rec["recipe_id"], "ions": list(IONS), "shocks": [], "transitions": [],
              "plateaus": []}
    peak_v = -1.0
    peak_bv = None
    limit_bv = None

    def consider_peak(v, b):
        nonlocal peak_v, peak_bv
        if v > peak_v + 1e-13:
            peak_v, peak_bv = v, b
        elif abs(v - peak_v) <= 1e-13 and b < peak_bv:
            peak_bv = b

    for sg in segs:
        if sg["kind"] == "plateau":
            report["plateaus"].append({"bv_start": sg["bv_start"], "bv_end": sg["bv_end"],
                                       "composition_meq_per_L": to_meq(sysm, sg["x"], present, CT)})
            v = nitrate_of(sysm, sg["x"], present, CT)
            consider_peak(v, sg["bv_start"])
            if limit_bv is None and v > limit:
                limit_bv = sg["bv_start"]
        elif sg["kind"] == "shock":
            report["shocks"].append({"bv": sg["bv"], "before_meq_per_L": to_meq(sysm, sg["before"], present, CT),
                                     "after_meq_per_L": to_meq(sysm, sg["after"], present, CT)})
            # the state immediately after the shock belongs to the following segment, which
            # starts at this bv, so peaks/limits are handled there.
        else:
            report["transitions"].append({"bv_start": sg["bv_start"], "bv_end": sg["bv_end"],
                                          "start_meq_per_L": to_meq(sysm, sg["x_start"], present, CT),
                                          "end_meq_per_L": to_meq(sysm, sg["x_end"], present, CT)})
            pv, pb, cross = analyse_transition(sysm, sg, present, CT, limit)
            consider_peak(pv, pb)
            if limit_bv is None and cross is not None:
                limit_bv = cross
    def num(v):
        v = float(v)
        if v == 0.0:
            return 0
        return v
    for lst in ("shocks", "transitions", "plateaus"):
        for item in report[lst]:
            for key in ("bv", "bv_start", "bv_end"):
                if key in item:
                    item[key] = num(item[key])
    report["nitrate_peak"] = {"meq_per_L": float(peak_v), "bv": num(peak_bv)}
    report["nitrate_limit_bv"] = None if limit_bv is None else num(limit_bv)
    report["samples"] = [to_meq(sysm, state_at_bv(segs, float(b)), present, CT) for b in rec["sample_bv"]]
    return report, segs, sysm, present, CT, tracker


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--diag", default=None, help="optional path for diagnostics JSON")
    args = ap.parse_args(argv)
    with open(args.recipe, "r", encoding="utf-8") as fh:
        rec = json.load(fh)
    report, segs, sysm, present, CT, tracker = solve_recipe(rec)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
        fh.write("\n")
    if args.diag:
        d = dict(DIAG)
        d["n_events"] = tracker.n_events
        with open(args.diag, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
