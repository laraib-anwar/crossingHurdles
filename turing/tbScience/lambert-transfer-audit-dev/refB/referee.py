#!/usr/bin/env python3
"""Reference B: an independent referee (and third-opinion solver) for LAMBERT_SPEC reports.

Check mode : python referee.py --system S.json --report R.json [--out verdict.json] [--quiet]
Solve mode : python referee.py --solve --system S.json --output R.json

No Lambert algorithm is used to check a report (no Izzo, no Gooding, no universal-variable
iteration).  The checks rest on

  * a from-scratch Kepler solver in numpy.longdouble for every object state,
  * recovery of the orbital elements and of the time since periapsis from each reported
    ephemeris state,
  * numerical integration of the two-body equations from (r1, v1) over the time of flight:
    DOP853 (scipy, rtol 1e-13) in physical time and in Sundman time, and a longdouble
    Kustaanheimo-Stiefel integration with a Gragg-Bulirsch-Stoer extrapolation integrator, which
    decides the verdict (its error is estimated by a coarser second KS run and by the longdouble
    Kepler propagator); the in-plane angle is integrated alongside, so the end state and the
    number of revolutions are measured; the end-point miss is turned into the departure-velocity
    error it implies through the arc's state-transition matrix,
  * a dense scan of Lagrange's time-of-flight equation over the one-parameter family of
    prograde N-revolution conics through r1 and r2 (parameter: Lagrange's angle alpha), refined
    with minimize_scalar, for T_min(N) and for the number of solutions of each N.

The solve mode is a third opinion built on a different family parametrisation: the empty-focus
construction (semi-major axis and the choice of circle intersection), Kepler's equation in
longdouble for the time of flight, and Newton shooting on the departure velocity with the exact
longdouble propagator.  Exit status 0 iff the verdict passes (check mode).
"""
import argparse
import json
import sys
import time

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq, minimize_scalar

LD = np.longdouble
PI = LD("3.141592653589793238462643383279502884197")
TWO_PI = LD(2) * PI
DAY = LD(86400)
EPS_LD = np.finfo(LD).eps
DEG = PI / LD(180)

# ------------------------------------------------------------------ contract tolerances (LAMBERT_SPEC 5)
TOL_VEC = 1e-9          # |w - w_ref| <= 1e-9 |w_ref|
TOL_SCALAR = 1e-9       # a, e, dv, T_min relative
TOL_THETA_DEG = 1e-9    # theta absolute degrees
# ------------------------------------------------------------------ referee-internal tolerances
TOL_INTEG_EST = 1e-10   # integration-error estimate (in implied v1/v2 terms) must stay below this
TOL_DOP853_SANITY = 1e-6  # DOP853 vs KS in implied velocity: a gross-error guard on the referee itself
TOL_THETA_INTEG_DEG = 1e-2  # integrated angle mod 360 vs geometric theta (revolution-count sanity)
TOL_A_LAGRANGE = 1e-8   # a of a reported solution vs a of the matching Lagrange root (cross-check)
RTOL_INTEG = 1e-13
ATOL_INTEG = 1e-15


# ------------------------------------------------------------------ small linear algebra in longdouble
def vec(x):
    return np.array([LD(x[0]), LD(x[1]), LD(x[2])], dtype=LD)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def norm(a):
    return np.sqrt(dot(a, a))


def cross(a, b):
    return np.array([a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]], dtype=a.dtype)


def f64(a):
    return [float(a[0]), float(a[1]), float(a[2])]


def rel_vec(w, w_ref):
    w = np.asarray(w, dtype=LD)
    w_ref = np.asarray(w_ref, dtype=LD)
    return float(norm(w - w_ref) / norm(w_ref))


def rel_scalar(x, x_ref):
    return float(abs(LD(x) - LD(x_ref)) / abs(LD(x_ref)))


def wrap_pi(x):
    """Reduce a longdouble angle to [-pi, pi)."""
    k = np.floor((x + PI) / TWO_PI)
    return x - k * TWO_PI


# ------------------------------------------------------------------ Kepler's equation (longdouble)
def kepler_ell(M, e):
    """E with E - e sin E = M, on the same unwrapped revolution as M (safeguarded Newton)."""
    k = np.floor((M + PI) / TWO_PI)
    Mr = M - k * TWO_PI
    lo, hi = Mr - e, Mr + e
    E = Mr + LD(0.85) * e * (LD(1) if Mr >= 0 else LD(-1))
    for _ in range(200):
        f = E - e * np.sin(E) - Mr
        if f > 0:
            hi = min(hi, E)
        else:
            lo = max(lo, E)
        dE = f / (LD(1) - e * np.cos(E))
        En = E - dE
        if not (lo <= En <= hi):
            En = (lo + hi) / 2
            dE = E - En
        E = En
        if abs(dE) <= 4 * EPS_LD * max(LD(1), abs(E)):
            break
    return E + k * TWO_PI


def kepler_hyp(M, e):
    """H with e sinh H - H = M (Newton from asinh(M/e); f is convex on each side of 0)."""
    H = np.arcsinh(M / e)
    for _ in range(300):
        f = e * np.sinh(H) - H - M
        dH = f / (e * np.cosh(H) - LD(1))
        H = H - dH
        if abs(dH) <= 4 * EPS_LD * max(LD(1), abs(H)):
            break
    return H


def pqw_from_angles(i_deg, Om_deg, om_deg):
    """Columns of R_z(Omega) R_x(i) R_z(omega): perifocal P, Q, W in the inertial frame."""
    i, Om, om = LD(i_deg) * DEG, LD(Om_deg) * DEG, LD(om_deg) * DEG
    cO, sO, ci, si, co, so = np.cos(Om), np.sin(Om), np.cos(i), np.sin(i), np.cos(om), np.sin(om)
    P = np.array([cO * co - sO * so * ci, sO * co + cO * so * ci, so * si], dtype=LD)
    Q = np.array([-cO * so - sO * co * ci, -sO * so + cO * co * ci, co * si], dtype=LD)
    W = np.array([sO * si, -cO * si, ci], dtype=LD)
    return P, Q, W


def state_from_anomaly(mu, a, e, P, Q, X):
    """State from the eccentric (a > 0) or hyperbolic (a < 0) anomaly X."""
    if a > 0:
        cE, sE = np.cos(X), np.sin(X)
        b = np.sqrt(LD(1) - e * e)
        r = a * (LD(1) - e * cE)
        rv = a * (cE - e) * P + a * b * sE * Q
        vv = (np.sqrt(mu * a) / r) * (-sE * P + b * cE * Q)
    else:
        A = -a
        cH, sH = np.cosh(X), np.sinh(X)
        b = np.sqrt(e * e - LD(1))
        r = A * (e * cH - LD(1))
        rv = A * (e - cH) * P + A * b * sH * Q
        vv = (np.sqrt(mu * A) / r) * (-sH * P + b * cH * Q)
    return rv, vv


def mean_motion(mu, a):
    aa = abs(a)
    return np.sqrt(mu / (aa * aa * aa))   # not aa ** 3: longdouble ** is only double-accurate here


class Orbit:
    """An object of the system file, with longdouble elements."""

    def __init__(self, mu, obj):
        self.name = obj["name"]
        self.mu = LD(mu)
        self.a = LD(obj["a_km"])
        self.e = LD(obj["e"])
        self.i_deg = LD(obj["i_deg"])
        self.Om_deg = LD(obj["Omega_deg"])
        self.om_deg = LD(obj["omega_deg"])
        self.M0 = LD(obj["M0_deg"]) * DEG
        self.t0 = LD(obj["t0_days"])
        self.P, self.Q, self.W = pqw_from_angles(self.i_deg, self.Om_deg, self.om_deg)
        self.n = mean_motion(self.mu, self.a)
        self.period = TWO_PI / self.n if self.a > 0 else None

    def mean_anomaly(self, t_days):
        return self.M0 + self.n * (LD(t_days) - self.t0) * DAY

    def state(self, t_days):
        M = self.mean_anomaly(t_days)
        X = kepler_ell(M, self.e) if self.a > 0 else kepler_hyp(M, self.e)
        return state_from_anomaly(self.mu, self.a, self.e, self.P, self.Q, X)


# ------------------------------------------------------------------ elements from a state (longdouble)
def elements_from_state(mu, r, v):
    rn = norm(r)
    h = cross(r, v)
    hn = norm(h)
    energy = dot(v, v) / 2 - mu / rn
    a = -mu / (2 * energy)
    evec = cross(v, h) / mu - r / rn
    e = norm(evec)
    W = h / hn
    i = np.arctan2(np.hypot(W[0], W[1]), W[2])
    nvec = np.array([-h[1], h[0], LD(0)], dtype=LD)
    nn = norm(nvec)
    if nn > 0:
        nhat = nvec / nn
        Om = np.arctan2(nhat[1], nhat[0]) % TWO_PI
    else:
        nhat = np.array([LD(1), LD(0), LD(0)], dtype=LD)
        Om = LD(0)
    if e > 0:
        P = evec / e
        Q = cross(W, P)
        om = np.arctan2(dot(cross(nhat, P), W), dot(nhat, P)) % TWO_PI
    else:
        P = nhat
        Q = cross(W, P)
        om = LD(0)
    nu = np.arctan2(dot(Q, r), dot(P, r))
    return dict(a=a, e=e, i=i, Om=Om, om=om, nu=nu, P=P, Q=Q, W=W, h=hn, p=hn * hn / mu)


def anomaly_from_nu(e, nu):
    """Eccentric (e < 1) or hyperbolic (e > 1) anomaly from the true anomaly."""
    if e < 1:
        return 2 * np.arctan2(np.sqrt(LD(1) - e) * np.sin(nu / 2), np.sqrt(LD(1) + e) * np.cos(nu / 2))
    return 2 * np.arctanh(np.sqrt((e - LD(1)) / (e + LD(1))) * np.tan(nu / 2))


def mean_from_anomaly(e, X):
    if e < 1:
        return X - e * np.sin(X)
    return e * np.sinh(X) - X


def propagate_kepler(mu, r0, v0, dt):
    """Exact two-body propagation of (r0, v0) by dt seconds in longdouble.

    Returns (r, v, dnu), dnu the unwrapped true-anomaly advance."""
    el = elements_from_state(mu, r0, v0)
    a, e, P, Q = el["a"], el["e"], el["P"], el["Q"]
    n = mean_motion(mu, a)
    X1 = anomaly_from_nu(e, el["nu"])
    M1 = mean_from_anomaly(e, X1)
    M2 = M1 + n * dt
    X2 = kepler_ell(M2, e) if a > 0 else kepler_hyp(M2, e)
    r, v = state_from_anomaly(mu, a, e, P, Q, X2)
    if a > 0:
        # true anomaly on the same unwrapped revolution as the eccentric anomaly
        k = np.floor((X2 + PI) / TWO_PI)
        Xr = X2 - k * TWO_PI
        nu2 = 2 * np.arctan2(np.sqrt(LD(1) + e) * np.sin(Xr / 2), np.sqrt(LD(1) - e) * np.cos(Xr / 2)) + k * TWO_PI
    else:
        nu2 = 2 * np.arctan(np.sqrt((e + LD(1)) / (e - LD(1))) * np.tanh(X2 / 2))
    dnu = nu2 - el["nu"]
    return r, v, dnu


def kepler_jacobian(mu, r0, v0, dt):
    """d(r, v)(dt) / d v0 by central differences of the longdouble propagator (6 x 3)."""
    J = np.zeros((6, 3), dtype=LD)
    h = LD(1e-6) * norm(v0)
    for k in range(3):
        vp = v0.copy()
        vm = v0.copy()
        vp[k] += h
        vm[k] -= h
        rp, wp, _ = propagate_kepler(mu, r0, vp, dt)
        rm, wm, _ = propagate_kepler(mu, r0, vm, dt)
        J[:3, k] = (rp - rm) / (2 * h)
        J[3:, k] = (wp - wm) / (2 * h)
    return J


# ------------------------------------------------------------------ transfer geometry
def geometry(r1, r2):
    rn1, rn2 = norm(r1), norm(r2)
    c = norm(r2 - r1)
    s = (rn1 + rn2 + c) / 2
    u1, u2 = r1 / rn1, r2 / rn2
    sum_u = u1 + u2
    # s - c without cancellation: (r1 r2 + r1.r2) / (r1 + r2 + c), r1 r2 + r1.r2 = r1 r2 |u1+u2|^2 / 2
    s_minus_c = rn1 * rn2 * dot(sum_u, sum_u) / 2 / (rn1 + rn2 + c)
    cr = cross(r1, r2)
    if cr[2] == 0:
        raise ValueError("(r1 x r2)_z = 0: prograde direction undefined")
    th = np.arctan2(norm(cr), dot(r1, r2))
    gt_pi = bool(cr[2] < 0)
    if gt_pi:
        th = TWO_PI - th
    W = cr / norm(cr) * (LD(-1) if gt_pi else LD(1))
    return dict(c=c, s=s, smc=s_minus_c, theta=th, gt_pi=gt_pi, W=W, rn1=rn1, rn2=rn2)


# ------------------------------------------------------------------ Lagrange's time equation over the family
def _x_minus_sin(x):
    x = np.asarray(x, dtype=float)
    x2 = x * x
    ser = x ** 3 / 6.0 * (1 - x2 / 20.0 * (1 - x2 / 42.0 * (1 - x2 / 72.0 * (1 - x2 / 110.0))))
    return np.where(np.abs(x) < 1e-2, ser, x - np.sin(x))


def _sinh_minus_x(x):
    x = np.asarray(x, dtype=float)
    x2 = x * x
    ser = x ** 3 / 6.0 * (1 + x2 / 20.0 * (1 + x2 / 42.0 * (1 + x2 / 72.0 * (1 + x2 / 110.0))))
    return np.where(np.abs(x) < 1e-2, ser, np.sinh(x) - x)


class Family:
    """Time of flight of the prograde conics through r1, r2 (Lagrange's equation).

    Ellipses: alpha in (0, 2 pi), a = s / (2 sin^2(alpha/2)), sin(beta/2) = sqrt((s-c)/s) sin(alpha/2),
    beta < 0 when theta > pi, sqrt(mu) T = a^1.5 (2 pi N + (alpha - sin alpha) - (beta - sin beta)).
    alpha < pi and alpha > pi are the two arcs of one a; alpha -> 0 is the parabolic limit, so
    for N = 0 the variable u (u = alpha for ellipses, u = -gamma for hyperbolas with
    |a| = s / (2 sinh^2(gamma/2)), sqrt(mu) T = |a|^1.5 ((sinh gamma - gamma) -/+ (sinh delta - delta)))
    runs monotonically from T = 0 (u -> -inf) to T = inf (u -> 2 pi)."""

    def __init__(self, g, mu):
        self.s = float(g["s"])
        self.smc = float(g["smc"])
        self.q = np.sqrt(self.smc / self.s)
        self.mu = float(mu)
        self.sg = -1.0 if g["gt_pi"] else 1.0

    def a_of(self, u):
        if u > 0:
            return self.s / (2 * np.sin(u / 2) ** 2)
        return -self.s / (2 * np.sinh(-u / 2) ** 2)

    def tof_ell(self, al, N):
        al = np.asarray(al, dtype=float)
        sa = np.sin(al / 2)
        a = self.s / (2 * sa * sa)
        be = self.sg * 2 * np.arcsin(np.minimum(1.0, self.q * sa))
        return np.sqrt(a ** 3 / self.mu) * (2 * np.pi * N + _x_minus_sin(al) - _x_minus_sin(be))

    def tof_hyp(self, ga):
        ga = np.asarray(ga, dtype=float)
        sa = np.sinh(ga / 2)
        A = self.s / (2 * sa * sa)
        de = self.sg * 2 * np.arcsinh(self.q * sa)
        return np.sqrt(A ** 3 / self.mu) * (_sinh_minus_x(ga) - _sinh_minus_x(de))

    def tof_par(self):
        return np.sqrt(2.0 / self.mu) / 3.0 * (self.s ** 1.5 - self.sg * self.smc ** 1.5)

    def tof0(self, u):
        if u > 0:
            return float(self.tof_ell(u, 0))
        if u < 0:
            return float(self.tof_hyp(-u))
        return float(self.tof_par())

    def scan(self, N, T, n_grid=6001):
        """T_min(N) by a dense alpha grid + bounded Brent, and the number of grid crossings of T."""
        f = lambda al: float(self.tof_ell(al, N))
        lo, hi = 1e-3, 2 * np.pi - 1e-3
        grid = np.linspace(lo, hi, n_grid)
        vals = self.tof_ell(grid, N)
        k = int(np.argmin(vals))
        if k < 2 or k > n_grid - 3:
            raise RuntimeError("T_min scan: minimum at the grid boundary (N=%d)" % N)
        res = minimize_scalar(f, bounds=(grid[k - 2], grid[k + 2]), method="bounded",
                              options={"xatol": 1e-13, "maxiter": 1000})
        t_min = min(float(res.fun), float(vals[k]))
        al_min = float(res.x) if res.fun <= vals[k] else float(grid[k])
        d = np.diff(vals)
        rel = np.abs(d) > 1e-13 * vals[1:]
        sgn = np.sign(d[rel])
        n_turn = int(np.sum(sgn[1:] != sgn[:-1]))
        # crossings of T along the grid with the refined minimum inserted (T may sit 1e-6 above T_min)
        ins = int(np.searchsorted(grid, al_min))
        cv = np.insert(vals, ins, t_min)
        crossings = int(np.sum(np.diff(np.sign(cv - T)) != 0))
        if f(lo) < T or f(hi) < T:
            raise RuntimeError("T_min scan: family time at the grid ends below T (N=%d)" % N)
        roots = []
        if T > t_min:
            g = lambda al: f(al) - T
            roots = [brentq(g, lo, al_min, xtol=1e-15, rtol=1e-15, maxiter=500),
                     brentq(g, al_min, hi, xtol=1e-15, rtol=1e-15, maxiter=500)]
        return dict(t_min_s=t_min, alpha_min=al_min, n_turning_points=n_turn, grid_crossings=crossings,
                    roots=roots, a_roots=[self.a_of(u) for u in roots],
                    curve=[(float(grid[j]), float(vals[j])) for j in range(max(0, k - 3), min(n_grid, k + 4))])

    def root0(self, T):
        g = lambda u: self.tof0(u) - T
        hi = 2 * np.pi - 1e-9
        lo = -1.0
        while g(lo) > 0:
            lo *= 2
            if lo < -600:
                raise RuntimeError("N=0 root bracket failed")
        u = brentq(g, lo, hi, xtol=1e-15, rtol=1e-15, maxiter=500)
        return u, self.a_of(u)


# ------------------------------------------------------------------ numerical propagation of an arc
def integrate_arc(mu, r1, v1, T, rtol=RTOL_INTEG, atol=ATOL_INTEG):
    """Propagate (r1, v1) over T seconds with DOP853 in physical time and in Sundman time
    (dt/ds = r).  Returns end states (km, km/s) and integrated in-plane angle of each."""
    L = float(norm(r1))
    V = float(np.sqrt(LD(mu) / LD(L)))
    TU = L / V
    r0 = np.array(f64(r1)) / L
    v0 = np.array(f64(v1)) / V
    Tn = float(T) / TU
    h = float(np.linalg.norm(np.cross(r0, v0)))

    def f_cart(t, y):
        r = y[:3]
        rn = np.sqrt(r[0] * r[0] + r[1] * r[1] + r[2] * r[2])
        return np.concatenate((y[3:6], -r / rn ** 3, [h / rn ** 2]))

    def f_sund(sv, y):
        r = y[:3]
        rn = np.sqrt(r[0] * r[0] + r[1] * r[1] + r[2] * r[2])
        return np.concatenate((rn * y[3:6], -r / rn ** 2, [rn, h / rn]))

    out = dict(ok=True, messages=[])
    sol = solve_ivp(f_cart, (0.0, Tn), np.concatenate((r0, v0, [0.0])), method="DOP853", rtol=rtol, atol=atol)
    if not sol.success:
        out["ok"] = False
        out["messages"].append("cartesian: " + str(sol.message))
        return out
    yc = sol.y[:, -1]
    out["cart_r"], out["cart_v"], out["cart_theta"] = yc[:3] * L, yc[3:6] * V, float(yc[6])
    out["cart_nfev"] = int(sol.nfev)

    def hit(sv, y):
        return y[6] - Tn

    hit.terminal = True
    hit.direction = 1
    y0s = np.concatenate((r0, v0, [0.0, 0.0]))
    s1 = solve_ivp(f_sund, (0.0, 1e12), y0s, method="DOP853", rtol=rtol, atol=atol, events=hit)
    if not s1.success or len(s1.t_events[0]) == 0:
        out["ok"] = False
        out["messages"].append("sundman: " + (str(s1.message) if not s1.success else "time-of-flight event not reached"))
        return out
    s_ev = float(s1.t_events[0][0])
    # re-integrate to the located s so that the end state is a step end point, not an interpolant,
    # then close the residual time gap (a few ulps of T) with a second-order Taylor step
    s2 = solve_ivp(f_sund, (0.0, s_ev), y0s, method="DOP853", rtol=rtol, atol=atol)
    ys = s2.y[:, -1]
    r, v = ys[:3], ys[3:6]
    dt = Tn - ys[6]
    rn = np.linalg.norm(r)
    acc = -r / rn ** 3
    r_end = r + v * dt + 0.5 * acc * dt * dt
    v_end = v + acc * dt
    out["sund_r"], out["sund_v"] = r_end * L, v_end * V
    out["sund_theta"] = float(ys[7] + h / rn ** 2 * dt)
    out["sund_time_gap_rel"] = abs(dt) / Tn
    out["sund_nfev"] = int(s1.nfev + s2.nfev)
    return out


# ------------------------------------------------------------------ longdouble KS-regularised integration
def _ks_L(u):
    """The KS matrix L(u); the physical position is the first three components of L(u) u."""
    u1, u2, u3, u4 = u
    return np.array([[u1, -u2, -u3, u4], [u2, u1, -u4, -u3], [u3, u4, u1, u2], [u4, -u3, u2, -u1]], dtype=LD)


def _ks_from_rv(r, v):
    rn = norm(r)
    x, y, z = r
    if x >= 0:
        u1 = np.sqrt((rn + x) / 2)
        u = np.array([u1, y / (2 * u1), z / (2 * u1), LD(0)], dtype=LD)
    else:
        u2 = np.sqrt((rn - x) / 2)
        u = np.array([y / (2 * u2), u2, LD(0), z / (2 * u2)], dtype=LD)
    up = _ks_L(u).T.dot(np.array([v[0], v[1], v[2], LD(0)], dtype=LD)) / 2
    return u, up


_GBS_SEQ = (2, 4, 6, 8, 10, 12, 14, 16)


def dot4(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]


def _gbs_step(f, y, H):
    """One Gragg-Bulirsch-Stoer step (modified midpoint, polynomial extrapolation in h^2) in
    longdouble; returns the extrapolated state and the difference of the last two columns."""
    tab = []
    f0 = f(y)
    for j, n in enumerate(_GBS_SEQ):
        h = H / LD(n)
        z0 = y
        z1 = y + h * f0
        for _ in range(n - 1):
            z0, z1 = z1, z0 + 2 * h * f(z1)
        row = [(z1 + z0 + h * f(z1)) / 2]
        for k in range(1, j + 1):
            m = _GBS_SEQ[j - k]
            ratio = LD(n * n) / LD(m * m)
            row.append(row[k - 1] + (row[k - 1] - tab[j - 1][k - 1]) / (ratio - 1))
        tab.append(row)
    best, prev = tab[-1][-1], tab[-1][-2]
    return best, prev


def ks_integrate(mu, r1, v1, T, tol=LD(1e-16), phase=0.25):
    """Integrate the two-body problem in Kustaanheimo-Stiefel variables (fictitious time s,
    dt/ds = r) in longdouble with an adaptive extrapolation integrator, from (r1, v1) for T seconds.

    The state is (u, u', t, phi) with u'' = (E/2) u, t' = |u|^2 and phi' = |h| / |u|^2 (the in-plane
    angle); E is the Kepler energy.  The end of the arc is located by Newton iteration on the length
    of the last step.  Returns (r, v, phi_total, steps)."""
    L = norm(r1)
    V = np.sqrt(mu / L)
    TU = L / V
    r = r1 / L
    v = v1 / V
    Tn = T / TU
    E = dot(v, v) / 2 - LD(1) / norm(r)
    hang = norm(cross(r, v))
    u, up = _ks_from_rv(r, v)
    halfE = E / 2

    def f(y):
        uu = y[0:4]
        rr = uu[0] * uu[0] + uu[1] * uu[1] + uu[2] * uu[2] + uu[3] * uu[3]
        return np.concatenate((y[4:8], halfE * uu, np.array([rr, hang / rr], dtype=LD)))

    y = np.concatenate((u, up, np.array([LD(0), LD(0)], dtype=LD)))

    def err_of(a, b):
        scale = np.maximum(np.abs(a), LD(1))
        scale[8] = max(abs(a[8]), Tn)
        return float(np.max(np.abs(a - b) / scale))

    H = LD(1e300)
    steps = 0
    for _ in range(100000):
        # never let one step cover more than `phase` radians of the local oscillator phase
        uu, upu = y[0:4], y[4:8]
        H_cap = LD(phase) / np.sqrt(abs(halfE) + dot4(upu, upu) / dot4(uu, uu))
        H = min(H, H_cap)
        y1, y1p = _gbs_step(f, y, H)
        err = err_of(y1, y1p)
        if err > float(tol):
            H = H * LD(0.5)
            continue
        steps += 1
        if y1[8] >= Tn:
            # last step: Newton on its length so that t = Tn
            sig = H * (Tn - y[8]) / (y1[8] - y[8])
            for _ in range(30):
                ys, _ = _gbs_step(f, y, sig)
                g = ys[8] - Tn
                rr = ys[0] * ys[0] + ys[1] * ys[1] + ys[2] * ys[2] + ys[3] * ys[3]
                ds = g / rr
                sig = sig - ds
                if abs(g) <= 4 * EPS_LD * Tn:
                    break
            y = ys
            break
        y = y1
        grow = 0.9 * (float(tol) / max(err, 1e-300)) ** (1.0 / 15)
        H = H * LD(min(2.0, max(0.5, grow)))
    else:
        raise RuntimeError("KS integration did not reach the time of flight")
    uu, upu = y[0:4], y[4:8]
    Lu = _ks_L(uu)
    rr = uu[0] * uu[0] + uu[1] * uu[1] + uu[2] * uu[2] + uu[3] * uu[3]
    r_end = Lu.dot(uu)[:3] * L
    v_end = (2 * Lu.dot(upu)[:3] / rr) * V
    # close the residual time gap (a few ulps) with a first-order step
    gap = (Tn - y[8]) * TU
    r_end = r_end + v_end * gap
    return r_end, v_end, y[9], steps


# ------------------------------------------------------------------ JSON helpers
def load_json(path):
    def hook(pairs):
        keys = [k for k, _ in pairs]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate keys in a JSON object")
        return dict(pairs)

    with open(path, "rb") as fh:
        data = fh.read()
    return json.loads(data.decode("utf-8"), object_pairs_hook=hook)


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and bool(np.isfinite(x))


def is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def is_vec(x):
    return isinstance(x, list) and len(x) == 3 and all(is_num(c) for c in x)


def schema_errors(system, report):
    errs = []
    if not isinstance(report, dict):
        return ["report is not an object"]
    if set(report.keys()) != {"system_id", "ephemeris", "transfers"}:
        return ["top-level keys are %s" % sorted(report.keys())]
    if report["system_id"] != system["system_id"]:
        errs.append("system_id mismatch")
    eph = report["ephemeris"]
    if not isinstance(eph, list) or len(eph) != len(system["ephemeris_queries"]):
        errs.append("ephemeris list length")
    else:
        for k, (q, e) in enumerate(zip(system["ephemeris_queries"], eph)):
            if not isinstance(e, dict) or set(e.keys()) != {"object", "t_days", "r_km", "v_km_s"}:
                errs.append("ephemeris[%d] keys" % k)
                continue
            if e["object"] != q["object"] or e["t_days"] != q["t_days"]:
                errs.append("ephemeris[%d] object/t_days differ from the query" % k)
            if not (is_vec(e["r_km"]) and is_vec(e["v_km_s"])):
                errs.append("ephemeris[%d] vectors" % k)
    tr = report["transfers"]
    if not isinstance(tr, list) or len(tr) != len(system["transfer_queries"]):
        errs.append("transfers list length")
    else:
        keys = {"from", "t1_days", "to", "t2_days", "n_max", "theta_deg", "t_min_days", "solutions", "best"}
        skeys = {"N", "branch", "v1_km_s", "v2_km_s", "a_km", "e", "dv_km_s"}
        for k, (q, t) in enumerate(zip(system["transfer_queries"], tr)):
            if not isinstance(t, dict) or set(t.keys()) != keys:
                errs.append("transfers[%d] keys" % k)
                continue
            for key in ("from", "t1_days", "to", "t2_days", "n_max"):
                if t[key] != q[key] or type(t[key]) is not type(q[key]):
                    errs.append("transfers[%d].%s differs from the query" % (k, key))
            if not is_num(t["theta_deg"]) or not (0 < t["theta_deg"] < 360):
                errs.append("transfers[%d].theta_deg" % k)
            if not isinstance(t["t_min_days"], list) or len(t["t_min_days"]) != q["n_max"] or not all(is_num(x) for x in t["t_min_days"]):
                errs.append("transfers[%d].t_min_days" % k)
            if not isinstance(t["solutions"], list):
                errs.append("transfers[%d].solutions" % k)
                continue
            for j, sol in enumerate(t["solutions"]):
                if not isinstance(sol, dict) or set(sol.keys()) != skeys:
                    errs.append("transfers[%d].solutions[%d] keys" % (k, j))
                    continue
                if not is_int(sol["N"]) or sol["N"] < 0 or sol["N"] > q["n_max"]:
                    errs.append("transfers[%d].solutions[%d].N" % (k, j))
                    continue
                if sol["branch"] not in ("low", "high", "single") or (sol["N"] == 0) != (sol["branch"] == "single"):
                    errs.append("transfers[%d].solutions[%d].branch" % (k, j))
                if not (is_vec(sol["v1_km_s"]) and is_vec(sol["v2_km_s"]) and is_num(sol["a_km"]) and is_num(sol["e"]) and is_num(sol["dv_km_s"])):
                    errs.append("transfers[%d].solutions[%d] numbers" % (k, j))
            if not is_int(t["best"]) or not (0 <= t["best"] < len(t["solutions"])):
                errs.append("transfers[%d].best" % k)
    return errs


# ------------------------------------------------------------------ ephemeris check
def _eph_quantities(orb, r, v, use_recovered):
    """Quantities recovered from a state, as differences from the file's values (longdouble)."""
    mu = orb.mu
    el = elements_from_state(mu, r, v)
    q = {}
    q["a"] = np.array([(el["a"] - orb.a) / abs(orb.a)], dtype=LD)          # relative
    q["evec"] = el["e"] * el["P"] - orb.e * orb.P                           # eccentricity vector (smooth at e = 0)
    q["W"] = el["W"] - orb.W                                                # unit vector difference
    if use_recovered:
        q["P"] = el["P"] - orb.P
        P_, Q_, e_ = el["P"], el["Q"], el["e"]
    else:
        P_, Q_, e_ = orb.P, orb.Q, orb.e
    # time since periapsis implied by the state, against M(t)/n from the file
    nu = np.arctan2(dot(Q_, r), dot(P_, r))
    X = anomaly_from_nu(e_, nu)
    Mstate = mean_from_anomaly(e_, X)
    Mfile = orb.mean_anomaly(orb._t)
    if orb.a > 0:
        q["t"] = np.array([wrap_pi(Mstate - Mfile) / TWO_PI], dtype=LD)     # fraction of the period
    else:
        q["t"] = np.array([(Mstate - Mfile) / max(abs(Mfile), LD(1))], dtype=LD)  # relative to max(|t - tp|, 1/n)
    return q, el


def check_ephemeris(orb, q, entry):
    res = dict(object=q["object"], t_days=q["t_days"])
    fails = []
    r = vec(entry["r_km"])
    v = vec(entry["v_km_s"])
    orb._t = LD(q["t_days"])
    # (1) direct comparison with the longdouble Kepler state (the contract's metric)
    r_ref, v_ref = orb.state(q["t_days"])
    res["r_resid"] = rel_vec(r, r_ref)
    res["v_resid"] = rel_vec(v, v_ref)
    if res["r_resid"] > TOL_VEC:
        fails.append("r differs from the longdouble Kepler state by %.3e relative" % res["r_resid"])
    if res["v_resid"] > TOL_VEC:
        fails.append("v differs from the longdouble Kepler state by %.3e relative" % res["v_resid"])
    # (2) elements and time since periapsis recovered from the reported state.  Each is gated at the
    # change that a 1e-9 relative error in r and in v can produce (first order, from a central
    # difference Jacobian), so the gate is exactly as strict as the contract and no stricter.
    use_rec = float(orb.e) >= 1e-6
    qv, el = _eph_quantities(orb, r, v, use_rec)
    hr, hv = LD(1e-7) * norm(r), LD(1e-7) * norm(v)
    jac = {k: np.zeros((len(val), 6)) for k, val in qv.items()}
    for j in range(6):
        rp, rm, vp, vm = r.copy(), r.copy(), v.copy(), v.copy()
        if j < 3:
            rp[j] += hr
            rm[j] -= hr
            step = hr
        else:
            vp[j - 3] += hv
            vm[j - 3] -= hv
            step = hv
        qp, _ = _eph_quantities(orb, rp, vp, use_rec)
        qm, _ = _eph_quantities(orb, rm, vm, use_rec)
        for k in qv:
            jac[k][:, j] = [float(x) for x in (qp[k] - qm[k]) / (2 * step)]
    rn, vn = float(norm(r)), float(norm(v))
    res["elements"] = {}
    for k, val in qv.items():
        resid = float(norm(val)) if len(val) == 3 else float(abs(val[0]))
        J = jac[k]
        tol = TOL_VEC * (np.linalg.norm(J[:, :3], 2) * rn + np.linalg.norm(J[:, 3:], 2) * vn) + 1e-15
        res["elements"][k] = dict(resid=resid, tol=float(tol), ratio=resid / float(tol))
        if resid > tol:
            fails.append("recovered %s off by %.3e (contract-equivalent tolerance %.3e)" % (k, resid, tol))
    res["time_resid_rel_period"] = res["elements"]["t"]["resid"]
    res["time_basis"] = "recovered elements" if use_rec else "file elements (e < 1e-6)"
    res["a_rec_km"], res["e_rec"] = float(el["a"]), float(el["e"])
    res["i_rec_deg"], res["Omega_rec_deg"], res["omega_rec_deg"] = float(el["i"] / DEG), float(el["Om"] / DEG), float(el["om"] / DEG)
    res["fails"] = fails
    res["ok"] = not fails
    return res


# ------------------------------------------------------------------ transfer check
def check_solution(mu, r1, r2, vA, vB, T, g, sol):
    """Check one reported solution by propagating its (r1, v1) over T.

    The decisive propagator is the longdouble KS integration; its error is estimated from a second
    KS run with coarser steps and from the longdouble Kepler propagator.  The two DOP853 runs
    (physical time and Sundman time, double precision) are compared with it and reported.
    The miss at r2 of each end state is turned into the departure-velocity error it implies,
    dv1 = -Phi_rv^-1 (r_end - r2), and the arrival velocity of the true arc is
    v_end + Phi_vv dv1 (Phi from central differences of the longdouble Kepler propagator)."""
    sr = dict(N=sol["N"], branch=sol["branch"])
    sf = []
    v1 = vec(sol["v1_km_s"])
    v2 = vec(sol["v2_km_s"])
    sr["h_z"] = float(cross(r1, v1)[2])
    if not sr["h_z"] > 0:
        sf.append("arc is not prograde (h_z = %g)" % sr["h_z"])
    J = kepler_jacobian(mu, r1, v1, T)
    Jrv = np.array(J[:3], dtype=float)
    Jvv = np.array(J[3:], dtype=float)
    sr["cond_Phi_rv"] = float(np.linalg.cond(Jrv))
    ends = {}
    rK, vK, phK, stK = ks_integrate(mu, r1, v1, T, phase=0.25)
    ends["ks_ld"] = (rK, vK)
    rK2, vK2, phK2, stK2 = ks_integrate(mu, r1, v1, T, phase=0.4)
    ends["ks_ld_coarse"] = (rK2, vK2)
    rk, vk, dnu_k = propagate_kepler(mu, r1, v1, T)
    ends["kepler_ld"] = (rk, vk)
    sr["ks_steps"] = [stK, stK2]
    ig = integrate_arc(mu, r1, v1, T)
    if ig["ok"]:
        ends["dop853_cartesian"] = (vec(ig["cart_r"]), vec(ig["cart_v"]))
        ends["dop853_sundman"] = (vec(ig["sund_r"]), vec(ig["sund_v"]))
        sr["dop853_nfev"] = [ig["cart_nfev"], ig["sund_nfev"]]
    else:
        sf.append("DOP853 integration failed: " + "; ".join(ig["messages"]))
    v1f = np.array(f64(v1))
    imp = {}
    for key, (re_, ve_) in ends.items():
        miss = np.array([float(x) for x in (re_ - r2)])
        dv1 = -np.linalg.solve(Jrv, miss)
        v2t = np.array([float(x) for x in ve_]) + Jvv @ dv1
        imp[key] = (dv1, v2t)
        sr["end_miss_rel_" + key] = float(norm(re_ - r2) / norm(r2))
    dv1_ref, v2_ref = imp["ks_ld"]
    v1_ref = v1f + dv1_ref
    n1, n2 = np.linalg.norm(v1_ref), np.linalg.norm(v2_ref)

    def spread(key):
        return (float(np.linalg.norm(imp[key][0] - dv1_ref) / n1), float(np.linalg.norm(imp[key][1] - v2_ref) / n2))

    sr["integ_err_est"] = max(max(spread("ks_ld_coarse")), max(spread("kepler_ld")))
    sr["ks_vs_kepler_ld"] = spread("kepler_ld")
    sr["ks_vs_ks_coarse"] = spread("ks_ld_coarse")
    if ig["ok"]:
        sr["dop853_err_cartesian"] = spread("dop853_cartesian")
        sr["dop853_err_sundman"] = spread("dop853_sundman")
        if max(sr["dop853_err_cartesian"] + sr["dop853_err_sundman"]) > TOL_DOP853_SANITY:
            sf.append("DOP853 and KS integrations disagree by %.3e in implied velocity: referee inconsistent" % max(sr["dop853_err_cartesian"] + sr["dop853_err_sundman"]))
    if sr["integ_err_est"] > TOL_INTEG_EST:
        sf.append("integration error estimate %.3e in implied velocity: check inconclusive" % sr["integ_err_est"])
    # verdict: reported v1, v2 against the integrated true arc
    sr["v1_resid"] = float(np.linalg.norm(dv1_ref) / n1)
    sr["v2_resid"] = float(np.linalg.norm(np.array(f64(v2)) - v2_ref) / n2)
    if sr["v1_resid"] > TOL_VEC:
        sf.append("v1 differs from the integrated true arc by %.3e relative (end miss %.3e)" % (sr["v1_resid"], sr["end_miss_rel_ks_ld"]))
    if sr["v2_resid"] > TOL_VEC:
        sf.append("v2 differs from the integrated true arc by %.3e relative" % sr["v2_resid"])
    # revolutions actually made, from the integrated in-plane angle (KS and DOP853)
    angles = [("ks_ld", float(phK))]
    if ig["ok"]:
        angles.append(("dop853_cartesian", ig["cart_theta"]))
    for lab, th_tot in angles:
        N_int = int(np.floor(th_tot / (2 * np.pi)))
        sr["N_integrated_" + lab] = N_int
        if N_int != sol["N"]:
            sf.append("%s arc makes %d complete revolutions, N=%d reported" % (lab, N_int, sol["N"]))
    th_tot = float(phK)
    frac = (th_tot - 2 * np.pi * np.floor(th_tot / (2 * np.pi))) * 180 / np.pi
    sr["angle_total_integrated_deg"] = th_tot * 180 / np.pi
    sr["angle_mod_360_minus_theta_deg"] = float(frac - float(g["theta"] / DEG))
    if abs(sr["angle_mod_360_minus_theta_deg"]) > TOL_THETA_INTEG_DEG:
        sf.append("integrated angle mod 360 differs from theta by %.3e deg" % sr["angle_mod_360_minus_theta_deg"])
    # a, e, dv of the true arc
    v1r, v2r = np.array(v1_ref, dtype=LD), np.array(v2_ref, dtype=LD)
    el = elements_from_state(mu, r1, v1r)
    a_ref, e_ref = el["a"], el["e"]
    dv_ref = norm(v1r - vA) + norm(vB - v2r)
    sr["a_refB_km"], sr["e_refB"], sr["dv_refB_km_s"] = float(a_ref), float(e_ref), float(dv_ref)
    sr["periapsis_refB_km"] = float(a_ref * (1 - e_ref)) if a_ref > 0 else float(-a_ref * (e_ref - 1))
    sr["speeds_refB_km_s"] = [float(n1), float(n2)]
    sr["a_resid"] = rel_scalar(sol["a_km"], a_ref)
    sr["e_resid"] = rel_scalar(sol["e"], e_ref)
    sr["dv_resid"] = rel_scalar(sol["dv_km_s"], dv_ref)
    for key, lab in (("a_resid", "a"), ("e_resid", "e"), ("dv_resid", "dv")):
        if sr[key] > TOL_SCALAR:
            sf.append("%s off by %.3e relative" % (lab, sr[key]))
    sr["fails"] = sf
    return sr, float(a_ref)


def check_transfer(mu, orbs, q, tr):
    res = dict(from_=q["from"], t1_days=q["t1_days"], to=q["to"], t2_days=q["t2_days"], n_max=q["n_max"])
    fails = []
    A, B = orbs[q["from"]], orbs[q["to"]]
    r1, vA = A.state(q["t1_days"])
    r2, vB = B.state(q["t2_days"])
    T = (LD(q["t2_days"]) - LD(q["t1_days"])) * DAY
    g = geometry(r1, r2)
    res["T_s"] = float(T)
    res["r_norms_km"] = [float(g["rn1"]), float(g["rn2"])]
    res["theta_refB_deg"] = float(g["theta"] / DEG)
    res["theta_resid_deg"] = float(abs(g["theta"] / DEG - LD(tr["theta_deg"])))
    if res["theta_resid_deg"] > TOL_THETA_DEG:
        fails.append("theta off by %.3e deg" % res["theta_resid_deg"])
    fam = Family(g, mu)
    # ---- completeness from the Lagrange scan
    counts = {}
    for sol in tr["solutions"]:
        counts[sol["N"]] = counts.get(sol["N"], 0) + 1
    u0, a0 = fam.root0(float(T))
    res["N0_lagrange_a_km"] = a0
    res["count_N0"] = counts.get(0, 0)
    if res["count_N0"] != 1:
        fails.append("N=0: %d solutions reported, 1 expected" % res["count_N0"])
    scans = {}
    res["t_min"] = []
    for N in range(1, q["n_max"] + 1):
        sc = fam.scan(N, float(T))
        scans[N] = sc
        tmin_days = sc["t_min_s"] / 86400.0
        rep = tr["t_min_days"][N - 1]
        item = dict(N=N, t_min_refB_days=tmin_days, t_min_report_days=rep, alpha_min=sc["alpha_min"],
                    turning_points=sc["n_turning_points"], grid_crossings=sc["grid_crossings"],
                    lagrange_a_roots_km=sc["a_roots"])
        item["t_min_resid"] = rel_scalar(rep, tmin_days)
        item["T_over_T_min_minus_1"] = float(T) / sc["t_min_s"] - 1
        item["expected_count"] = 2 if float(T) > sc["t_min_s"] else 0
        item["reported_count"] = counts.get(N, 0)
        if item["t_min_resid"] > TOL_SCALAR:
            fails.append("T_min(%d) off by %.3e relative (report %.15g d, refB %.15g d)" % (N, item["t_min_resid"], rep, tmin_days))
        if item["expected_count"] != item["reported_count"]:
            fails.append("N=%d: %d solutions reported, %d expected (T/T_min - 1 = %.3e)" % (N, item["reported_count"], item["expected_count"], item["T_over_T_min_minus_1"]))
        if sc["grid_crossings"] != item["expected_count"] or sc["n_turning_points"] != 1:
            fails.append("N=%d: Lagrange scan not unimodal (%d turning points, %d crossings): referee assumption violated" % (N, sc["n_turning_points"], sc["grid_crossings"]))
        res["t_min"].append(item)
    order = [(sol["N"], {"single": 0, "low": 0, "high": 1}[sol["branch"]]) for sol in tr["solutions"]]
    if order != sorted(order) or len(set(order)) != len(order):
        fails.append("solutions not ordered by N then low/high, or a label repeated")
    # ---- each solution by integration
    res["solutions"] = []
    dvs, a_by_N = [], {}
    for j, sol in enumerate(tr["solutions"]):
        sr, a_ref = check_solution(mu, r1, r2, vA, vB, T, g, sol)
        sr["index"] = j
        if a_ref is not None:
            dvs.append(sr["dv_refB_km_s"])
            a_by_N.setdefault(sol["N"], []).append((sol["branch"], a_ref, j))
            # cross-check against the matching Lagrange root
            if sol["N"] == 0:
                sr["a_vs_lagrange"] = rel_scalar(a_ref, a0)
            elif sol["N"] in scans and len(scans[sol["N"]]["a_roots"]) == 2:
                ar = sorted(scans[sol["N"]]["a_roots"])
                sr["a_vs_lagrange"] = min(rel_scalar(a_ref, ar[0]), rel_scalar(a_ref, ar[1]))
            if sr.get("a_vs_lagrange") is not None and sr["a_vs_lagrange"] > TOL_A_LAGRANGE:
                sr["fails"].append("semi-major axis %.12g km matches no Lagrange root (closest %.3e relative)" % (a_ref, sr["a_vs_lagrange"]))
        else:
            dvs.append(np.inf)
        sr["ok"] = not sr["fails"]
        fails.extend("solutions[%d] (N=%d %s): %s" % (j, sol["N"], sol["branch"], m) for m in sr["fails"])
        res["solutions"].append(sr)
    # ---- branch labels from the semi-major axes of the integrated true arcs
    res["branches"] = []
    for N, items in sorted(a_by_N.items()):
        if N == 0 or len(items) != 2:
            continue
        (b1, a1, j1), (b2, a2, j2) = items
        ok = (b1, b2) == ("low", "high") and a1 < a2
        res["branches"].append(dict(N=N, labels=[b1, b2], a_km=[a1, a2], ok=ok, a_gap_rel=abs(a2 - a1) / max(abs(a1), abs(a2))))
        if not ok:
            fails.append("N=%d: labels %s/%s but a = %.12g / %.12g km" % (N, b1, b2, a1, a2))
    # ---- best
    if dvs:
        res["best_refB"] = int(np.argmin(dvs))
        res["best_report"] = tr["best"]
        srt = sorted(dvs)
        res["best_margin_rel"] = (srt[1] - srt[0]) / srt[0] if len(srt) > 1 else None
        if res["best_refB"] != tr["best"]:
            fails.append("best is %d, refB finds %d" % (tr["best"], res["best_refB"]))
    res["fails"] = fails
    res["ok"] = not fails
    return res


def domain_warnings(system, orbs, verdict):
    """LAMBERT_SPEC section 2 (table and guarantees 1-5) evaluated with refB's own values.
    Reported only: a report is judged against the exact answer whatever the system."""
    w = []
    mu = system["mu_km3_s2"]
    if not (1e4 <= mu <= 2e11):
        w.append("mu %g outside [1e4, 2e11]" % mu)
    if not (2 <= len(system["objects"]) <= 6):
        w.append("%d objects" % len(system["objects"]))
    for o in system["objects"]:
        a, e = o["a_km"], o["e"]
        if a > 0 and not (1e4 <= a <= 1e9 and 0 <= e <= 0.95):
            w.append("%s: ellipse a=%g e=%g outside the table" % (o["name"], a, e))
        if a < 0 and not (-1e9 <= a <= -1e4 and 1.05 <= e <= 4):
            w.append("%s: hyperbola a=%g e=%g outside the table" % (o["name"], a, e))
        if not (0 <= o["i_deg"] <= 180) or not all(0 <= o[k] < 360 for k in ("Omega_deg", "omega_deg", "M0_deg")):
            w.append("%s: angle outside its range" % o["name"])
        if not (-2e4 <= o["t0_days"] <= 2e4):
            w.append("%s: t0 outside [-2e4, 2e4]" % o["name"])
        rp = a * (1 - e) if a > 0 else -a * (e - 1)
        if rp < 1e3:
            w.append("G4: %s periapsis %.6g km < 1e3" % (o["name"], rp))
    if not (2 <= len(system["ephemeris_queries"]) <= 8):
        w.append("%d ephemeris queries" % len(system["ephemeris_queries"]))
    if not (2 <= len(system["transfer_queries"]) <= 6):
        w.append("%d transfer queries" % len(system["transfer_queries"]))
    times = [(q["object"], q["t_days"], "ephemeris %d" % k) for k, q in enumerate(system["ephemeris_queries"])]
    for k, q in enumerate(system["transfer_queries"]):
        times += [(q["from"], q["t1_days"], "transfer %d t1" % k), (q["to"], q["t2_days"], "transfer %d t2" % k)]
        if q["from"] == q["to"]:
            w.append("transfer %d: from == to" % k)
        if not (0 <= q["n_max"] <= 4):
            w.append("transfer %d: n_max %d" % (k, q["n_max"]))
        T = q["t2_days"] - q["t1_days"]
        if not (0.1 <= T <= 6000):
            w.append("transfer %d: T = %.6g d outside [0.1, 6000]" % (k, T))
    for name, t, where in times:
        orb = orbs[name]
        if not (-2e4 <= t <= 2e4):
            w.append("%s: t = %g outside [-2e4, 2e4]" % (where, t))
        if orb.a > 0:
            nper = float(abs(LD(t) - orb.t0) * DAY / orb.period)
            if nper > 2000:
                w.append("G3: %s (%s) is %.6g periods from its epoch (> 2000)" % (where, name, nper))
        else:
            M = float(orb.mean_anomaly(t))
            if abs(M) > 50:
                w.append("G3: %s (%s) hyperbolic |M| = %.6g > 50" % (where, name, abs(M)))
    for k, t in enumerate(verdict["transfers"]):
        if "theta_refB_deg" not in t:
            continue
        th = t["theta_refB_deg"]
        if not (1 <= th <= 179 or 181 <= th <= 359):
            w.append("G1: transfer %d theta %.6f deg" % (k, th))
        if min(t.get("r_norms_km", [1e3])) < 1e3:
            w.append("G1: transfer %d |r| < 1e3 km" % k)
        for it in t.get("t_min", []):
            if abs(it["T_over_T_min_minus_1"]) < 1e-6:
                w.append("G1: transfer %d N=%d T/T_min - 1 = %.3e" % (k, it["N"], it["T_over_T_min_minus_1"]))
        if t.get("best_margin_rel") is not None and t["best_margin_rel"] < 1e-6:
            w.append("G2: transfer %d best dv margin %.3e" % (k, t["best_margin_rel"]))
        for b in t.get("branches", []):
            if b["a_gap_rel"] < 1e-6:
                w.append("G2: transfer %d N=%d a gap %.3e" % (k, b["N"], b["a_gap_rel"]))
        for sr in t.get("solutions", []):
            if "periapsis_refB_km" not in sr:
                continue
            lab = "G5: transfer %d N=%d %s" % (k, sr["N"], sr["branch"])
            if sr["periapsis_refB_km"] < 1e3:
                w.append("%s periapsis %.6g km" % (lab, sr["periapsis_refB_km"]))
            if not (1e-3 <= sr["e_refB"] <= 20):
                w.append("%s e = %.6g" % (lab, sr["e_refB"]))
            vmax = max(sr["speeds_refB_km_s"])
            if vmax > 200:
                w.append("%s speed %.6g km/s" % (lab, vmax))
            if sr["dv_refB_km_s"] < 1e-3 * vmax:
                w.append("%s dv %.6g < 1e-3 max speed" % (lab, sr["dv_refB_km_s"]))
    return w


def referee(system, report):
    t_start = time.time()
    verdict = dict(system_id=system.get("system_id"), referee="refB")
    errs = schema_errors(system, report)
    verdict["schema_errors"] = errs
    failures = list(errs)
    mu = LD(system["mu_km3_s2"])
    orbs = {o["name"]: Orbit(mu, o) for o in system["objects"]}
    verdict["ephemeris"] = []
    verdict["transfers"] = []
    if not errs:
        for k, (q, entry) in enumerate(zip(system["ephemeris_queries"], report["ephemeris"])):
            r = check_ephemeris(orbs[q["object"]], q, entry)
            verdict["ephemeris"].append(r)
            failures.extend("ephemeris %d (%s@%s): %s" % (k, q["object"], q["t_days"], m) for m in r["fails"])
        for k, (q, tr) in enumerate(zip(system["transfer_queries"], report["transfers"])):
            try:
                r = check_transfer(mu, orbs, q, tr)
            except Exception as ex:  # noqa
                r = dict(fails=["referee exception: " + repr(ex)], ok=False)
            verdict["transfers"].append(r)
            failures.extend("transfer %d (%s->%s): %s" % (k, q["from"], q["to"], m) for m in r["fails"])
    verdict["failures"] = failures
    verdict["pass"] = not failures
    try:
        verdict["domain_warnings"] = domain_warnings(system, orbs, verdict)
    except Exception as ex:  # noqa
        verdict["domain_warnings"] = ["domain check failed: " + repr(ex)]
    verdict["runtime_s"] = time.time() - t_start
    worst = {}

    def upd(key, val):
        if val is not None and np.isfinite(val) and (key not in worst or val > worst[key]):
            worst[key] = float(val)

    for e in verdict["ephemeris"]:
        upd("eph_r", e["r_resid"])
        upd("eph_v", e["v_resid"])
        upd("eph_time_rel_period", e["time_resid_rel_period"])
        upd("eph_elem_ratio", max(x["ratio"] for x in e["elements"].values()))
    for t in verdict["transfers"]:
        upd("theta_deg", t.get("theta_resid_deg"))
        for it in t.get("t_min", []):
            upd("t_min", it.get("t_min_resid"))
        for sr in t.get("solutions", []):
            upd("v1", sr.get("v1_resid"))
            upd("v2", sr.get("v2_resid"))
            upd("a", sr.get("a_resid"))
            upd("e", sr.get("e_resid"))
            upd("dv", sr.get("dv_resid"))
            upd("end_miss", sr.get("end_miss_rel_ks_ld"))
            upd("integ_est", sr.get("integ_err_est"))
            upd("dop853_err", max(sr.get("dop853_err_cartesian", (0, 0)) + sr.get("dop853_err_sundman", (0, 0))))
            upd("a_vs_lagrange", sr.get("a_vs_lagrange"))
    verdict["worst_residuals"] = worst
    return verdict


# ------------------------------------------------------------------ third-opinion solver (empty-focus family)
class FocusFamily:
    """Prograde conics through r1, r2 with focus at the origin, built from the empty focus.

    Ellipse of semi-major axis a: the empty focus F* lies on both circles |F* - r_k| = 2a - |r_k|;
    the two intersections are the two arcs of that a.  Parameter xi: a = a_m (1 + xi^2), a_m = s/2,
    sign(xi) picks the intersection.  Hyperbola of |a| = A: circles |F* - r_k| = |r_k| + 2A.
    The time of flight comes from Kepler's equation on the actual conic (longdouble)."""

    def __init__(self, r1, r2, g, mu):
        self.mu = mu
        self.g = g
        W = g["W"]
        self.e1 = r1 / g["rn1"]
        self.e2 = cross(W, self.e1)
        self.W = W
        self.p1 = np.array([g["rn1"], LD(0)], dtype=LD)
        self.p2 = np.array([dot(r2, self.e1), dot(r2, self.e2)], dtype=LD)
        self.rk = (g["rn1"], g["rn2"])
        self.c = g["c"]
        self.am = g["s"] / 2
        self.theta = g["theta"]

    def _foci(self, rho1, rho2):
        d = self.p2 - self.p1
        c = self.c
        x = (rho1 * rho1 - rho2 * rho2 + c * c) / (2 * c)
        y2 = (rho1 - x) * (rho1 + x)
        y = np.sqrt(max(y2, LD(0)))
        ex = d / c
        ey = np.array([-ex[1], ex[0]], dtype=LD)
        return self.p1 + x * ex + y * ey, self.p1 + x * ex - y * ey

    def conic(self, Fs, a):
        """(e, P, Q) of the conic with empty focus Fs (plane coordinates) and semi-major axis a."""
        dF = np.sqrt(Fs[0] * Fs[0] + Fs[1] * Fs[1])
        e = dF / (2 * abs(a))
        # ellipse: periapsis on the far side of the focus from the centre (P = -F*/|F*|);
        # hyperbola: the vertex of the near branch lies between the focus and the centre (P = +F*/|F*|)
        P2 = -Fs / dF if a > 0 else Fs / dF
        P = P2[0] * self.e1 + P2[1] * self.e2
        Q = cross(self.W, P)
        return e, P, Q

    def ell(self, xi, N):
        """(T seconds, a, e, P, Q) of the ellipse with parameter xi and N revolutions."""
        xi = LD(xi)
        a = self.am * (LD(1) + xi * xi)
        Fa, Fb = self._foci(2 * a - self.rk[0], 2 * a - self.rk[1])
        Fs = Fa if xi >= 0 else Fb
        e, P, Q = self.conic(Fs, a)
        E = []
        for p in (self.p1, self.p2):
            rv = p[0] * self.e1 + p[1] * self.e2
            nu = np.arctan2(dot(Q, rv), dot(P, rv))
            E.append(anomaly_from_nu(e, nu))
        dE = (E[1] - E[0]) % TWO_PI
        n = mean_motion(self.mu, a)
        T = (dE + TWO_PI * N - e * (np.sin(E[1]) - np.sin(E[0]))) / n
        return T, a, e, P, Q

    def hyp(self, logA):
        """(T, a, e, P, Q) of the valid hyperbola with |a| = exp(logA), or None."""
        A = np.exp(LD(logA))
        for Fs in self._foci(self.rk[0] + 2 * A, self.rk[1] + 2 * A):
            e, P, Q = self.conic(Fs, -A)
            if not e > 1:
                continue
            nus = []
            for p in (self.p1, self.p2):
                rv = p[0] * self.e1 + p[1] * self.e2
                nus.append(np.arctan2(dot(Q, rv), dot(P, rv)))
            nu_inf = np.arccos(-LD(1) / e)
            if max(abs(nus[0]), abs(nus[1])) >= nu_inf or abs((nus[1] - nus[0]) - self.theta) > LD(1e-9):
                continue
            H = [anomaly_from_nu(e, nu) for nu in nus]
            n = mean_motion(self.mu, -A)
            T = (mean_from_anomaly(e, H[1]) - mean_from_anomaly(e, H[0])) / n
            return T, -A, e, P, Q
        return None

    def tmin(self, N):
        f = lambda xi: float(self.ell(xi, N)[0])
        grid = np.linspace(-20, 20, 1601)
        vals = np.array([f(x) for x in grid])
        k = int(np.argmin(vals))
        if k == 0 or k == len(grid) - 1:
            raise RuntimeError("empty-focus T_min at grid end")
        res = minimize_scalar(f, bounds=(grid[k - 1], grid[k + 1]), method="bounded", options={"xatol": 1e-13, "maxiter": 1000})
        return float(res.fun), float(res.x), grid, vals

    def roots(self, T, N):
        """Conics (T, a, e, P, Q) with time of flight T and N revolutions."""
        Tf = float(T)
        out = []
        if N >= 1:
            tmin, xmin, _, _ = self.tmin(N)
            if Tf <= tmin:
                return [], tmin
            f = lambda xi: float(self.ell(xi, N)[0]) - Tf
            for outer in (20.0, -20.0):
                while f(outer) < 0:
                    outer *= 2
                    if abs(outer) > 1e6:
                        raise RuntimeError("solver: no bracket for N=%d" % N)
                out.append(self.ell(brentq(f, min(xmin, outer), max(xmin, outer), xtol=1e-15, rtol=1e-15, maxiter=500), N))
            return out, tmin
        # N = 0: the ellipse branch is monotone in xi from the parabolic time to infinity; which end
        # is parabolic depends on the intersection, so test both ends
        f = lambda xi: float(self.ell(xi, 0)[0]) - Tf
        big = 1e4
        ends = (f(-big), f(big))
        if min(ends) < 0 < max(ends):
            return [self.ell(brentq(f, -big, big, xtol=1e-15, rtol=1e-15, maxiter=500), 0)], None
        def fh(la):
            c = self.hyp(la)
            return np.nan if c is None else float(c[0]) - Tf

        s = float(self.g["s"])
        grid = np.linspace(np.log(s) + 12, np.log(s) - 25, 741)
        prev = None
        for la in grid:
            val = fh(la)
            if np.isnan(val):
                continue
            if prev is not None and (prev[1] > 0) != (val > 0):
                return [self.hyp(brentq(fh, la, prev[0], xtol=1e-14, rtol=1e-15, maxiter=500))], None
            prev = (la, val)
        raise RuntimeError("solver: no hyperbolic N=0 arc found")


def conic_state(mu, a, e, P, Q, r):
    p = a * (LD(1) - e * e)
    nu = np.arctan2(dot(Q, r), dot(P, r))
    return np.sqrt(mu / p) * (-np.sin(nu) * P + (e + np.cos(nu)) * Q)


def shoot(mu, r1, r2, T, v1, max_iter=12):
    """Newton on the departure velocity with the exact longdouble propagator."""
    best = None
    for _ in range(max_iter):
        r, v, dnu = propagate_kepler(mu, r1, v1, T)
        miss = norm(r - r2) / norm(r2)
        if best is None or miss < best[0]:
            best = (miss, v1.copy(), v, dnu)
        if miss < LD(1e-17):
            break
        J = kepler_jacobian(mu, r1, v1, T)
        Jr = np.array(J[:3], dtype=LD)
        d = r - r2
        # solve the 3x3 system in longdouble by Cramer's rule
        det = (Jr[0, 0] * (Jr[1, 1] * Jr[2, 2] - Jr[1, 2] * Jr[2, 1]) - Jr[0, 1] * (Jr[1, 0] * Jr[2, 2] - Jr[1, 2] * Jr[2, 0])
               + Jr[0, 2] * (Jr[1, 0] * Jr[2, 1] - Jr[1, 1] * Jr[2, 0]))
        x = np.zeros(3, dtype=LD)
        for k in range(3):
            M = Jr.copy()
            M[:, k] = d
            x[k] = (M[0, 0] * (M[1, 1] * M[2, 2] - M[1, 2] * M[2, 1]) - M[0, 1] * (M[1, 0] * M[2, 2] - M[1, 2] * M[2, 0])
                    + M[0, 2] * (M[1, 0] * M[2, 1] - M[1, 1] * M[2, 0])) / det
        v1 = v1 - x
    return dict(miss=float(best[0]), v1=best[1], v2=best[2], dnu=best[3])


def solve_transfer(mu, orbs, q):
    A, B = orbs[q["from"]], orbs[q["to"]]
    r1, vA = A.state(q["t1_days"])
    r2, vB = B.state(q["t2_days"])
    T = (LD(q["t2_days"]) - LD(q["t1_days"])) * DAY
    g = geometry(r1, r2)
    ff = FocusFamily(r1, r2, g, mu)
    out = dict(q)
    out["theta_deg"] = float(g["theta"] / DEG)
    out["t_min_days"] = []
    sols = []
    for N in range(0, q["n_max"] + 1):
        conics, tmin = ff.roots(T, N)
        if N >= 1:
            out["t_min_days"].append(tmin / 86400.0)
        found = []
        for (Tc, a, e, P, Q) in conics:
            v1s = conic_state(mu, a, e, P, Q, r1)
            sh = shoot(mu, r1, r2, T, v1s)
            target = g["theta"] + TWO_PI * N
            if sh["miss"] > 1e-12 or abs(float(sh["dnu"] - target)) > 1e-8:
                raise RuntimeError("solver: shooting failed for N=%d (miss %.3e, dnu %.9f target %.9f)" % (N, sh["miss"], float(sh["dnu"]), float(target)))
            el = elements_from_state(mu, r1, sh["v1"])
            dv = norm(sh["v1"] - vA) + norm(vB - sh["v2"])
            found.append(dict(N=N, branch="single", v1_km_s=f64(sh["v1"]), v2_km_s=f64(sh["v2"]),
                              a_km=float(el["a"]), e=float(el["e"]), dv_km_s=float(dv)))
        if N > 0:
            found.sort(key=lambda d: d["a_km"])
            if len(found) == 2:
                found[0]["branch"], found[1]["branch"] = "low", "high"
        sols.extend(found)
    out["solutions"] = sols
    out["best"] = int(np.argmin([d["dv_km_s"] for d in sols]))
    return out


def solve_system(system):
    mu = LD(system["mu_km3_s2"])
    orbs = {o["name"]: Orbit(mu, o) for o in system["objects"]}
    rep = dict(system_id=system["system_id"], ephemeris=[], transfers=[])
    for q in system["ephemeris_queries"]:
        r, v = orbs[q["object"]].state(q["t_days"])
        rep["ephemeris"].append(dict(object=q["object"], t_days=q["t_days"], r_km=f64(r), v_km_s=f64(v)))
    for q in system["transfer_queries"]:
        rep["transfers"].append(solve_transfer(mu, orbs, q))
    return rep


# ------------------------------------------------------------------ main
def summary_line(v):
    w = v["worst_residuals"]
    keys = ["eph_r", "eph_v", "eph_time_rel_period", "theta_deg", "t_min", "v1", "v2", "a", "e", "dv", "integ_est", "dop853_err"]
    parts = ["%s=%.1e" % (k, w[k]) for k in keys if k in w]
    s = "%s pass=%s %s runtime=%.1fs" % (v["system_id"], v["pass"], " ".join(parts), v["runtime_s"])
    if v.get("domain_warnings"):
        s += " domain_warnings=%d" % len(v["domain_warnings"])
    if v["failures"]:
        s += " failures=%d first: %s" % (len(v["failures"]), v["failures"][0])
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--system", required=True)
    ap.add_argument("--report")
    ap.add_argument("--out")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--solve", action="store_true")
    ap.add_argument("--output")
    args = ap.parse_args(argv)
    system = load_json(args.system)
    if args.solve:
        if not args.output:
            ap.error("--solve needs --output")
        t0 = time.time()
        rep = solve_system(system)
        with open(args.output, "w") as fh:
            json.dump(rep, fh, indent=1)
        if not args.quiet:
            print("%s solved in %.1fs -> %s" % (system["system_id"], time.time() - t0, args.output))
        return 0
    if not args.report:
        ap.error("--report is required unless --solve")
    try:
        report = load_json(args.report)
    except Exception as ex:  # noqa
        report = None
        verdict = dict(system_id=system["system_id"], referee="refB", schema_errors=["unreadable report: " + repr(ex)],
                       failures=["unreadable report: " + repr(ex)], worst_residuals={}, runtime_s=0.0)
        verdict["pass"] = False
    if report is not None:
        verdict = referee(system, report)
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(verdict, fh, indent=1, default=float)
    if not args.quiet:
        print(summary_line(verdict))
    return 0 if verdict["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
