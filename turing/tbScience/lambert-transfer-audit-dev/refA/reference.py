#!/usr/bin/env python3
"""Reference A for the Keplerian ephemeris / multi-revolution Lambert audit.

Independent answer key.  Route:

  * Ephemerides.  The object's periapsis state is written down exactly from
    the elements and propagated with the universal-variable Kepler equation
    (chi, Stumpff C(z), S(z)) and the Lagrange f, g, fdot, gdot coefficients.
    The universal Kepler equation is solved as a bracketed root (brentq) on an
    interval where it is monotone (dF/dchi = -r < 0), then polished with
    Newton steps.  No eccentric or hyperbolic anomaly is formed.  The time
    since periapsis is formed in 50-digit decimal arithmetic and, for an
    ellipse, reduced into [-P/2, P/2) there, so distant epochs cost no digits.

  * Lambert.  Universal-variable formulation in z (Bate-Mueller-White,
    Vallado): A = sqrt(2 r1 r2) cos(theta/2),
        y(z) = r1 + r2 + A (z S(z) - 1) / sqrt(C(z)),
        sqrt(mu) TOF(z) = (y / C)^(3/2) S + A sqrt(y),
        f = 1 - y/r1, g = A sqrt(y/mu), gdot = 1 - y/r2.
    N-revolution arcs have z in ((2 pi N)^2, (2 pi (N+1))^2), the
    zero-revolution arc z in (z_y0, (2 pi)^2) where z_y0 < 0 is the hyperbolic
    limit (y = 0 when A > 0, z -> -inf when A < 0).  Each solution is a
    bracketed root (brentq) of TOF - T on a monotone piece, polished with
    Newton.  For N >= 1 TOF -> +inf at both ends of the z interval; the single
    interior minimum (root of the analytic dTOF, bracketed) gives T_min(N)
    and splits the interval into two monotone halves.

    For accuracy the functions of z are evaluated through exact half-angle
    identities.  With z = (2 pi N + 2u)^2, u in (0, pi) (elliptic):
        sqrt C = sqrt2 sin u / sqrt z,   (z S - 1)/sqrt C = -sqrt2 cos u,
        y = y0 + 2 sqrt2 |A| sin^2(u/2)   (A > 0)
        y = y0 + 2 sqrt2 |A| cos^2(u/2)   (A < 0),   y0 = c^2/(r1+r2+sqrt2|A|),
        S / C^(3/2) = (2u + 2 pi N - sin 2u) / (2 sqrt2 sin^3 u),
    so y > 0 on every elliptic interval and no subtraction loses digits.  The
    end u -> pi is handled in the variable eps = pi - u.  With z = -w^2
    (hyperbolic) y = y0 - 2 sqrt2 A sinh^2(w/4) (A > 0, solution needs y > 0)
    or r1 + r2 + sqrt2 |A| + 2 sqrt2 |A| sinh^2(w/4) (A < 0), and
    S / C^(3/2) = (sinh w - w) / (2 sqrt2 sinh^3(w/2)).  x - sin x,
    sinh x - x (the Stumpff series) are summed as series for small x.

Command line:  python reference.py --system <system.json> --output <report.json>
Dependencies: Python 3.11 standard library, NumPy, SciPy (brentq only).
"""

import argparse
import json
import math
import sys
from decimal import Decimal, getcontext
from fractions import Fraction

import numpy as np
from scipy.optimize import brentq

getcontext().prec = 50
PI_DEC = Decimal("3.1415926535897932384626433832795028841971693993751058209749445923")
DAY = 86400
EPS = float(np.finfo(float).eps)
PI = math.pi
TWO_PI = 2.0 * math.pi
HALF_PI = 0.5 * math.pi
SQRT2 = math.sqrt(2.0)
RTOL = 4.0 * EPS           # smallest rtol brentq accepts
XTOL = 1e-300
MAXITER = 500


def root(func, lo, hi):
    """Bracketed root of func on [lo, hi]; func(lo), func(hi) of opposite sign (or zero)."""
    flo = func(lo)
    if flo == 0.0:
        return lo
    fhi = func(hi)
    if fhi == 0.0:
        return hi
    if (flo > 0.0) == (fhi > 0.0):
        raise RuntimeError("root not bracketed")
    return brentq(func, lo, hi, xtol=XTOL, rtol=RTOL, maxiter=MAXITER)


def newton_polish(func, dfunc, t, lo, hi, steps=3):
    """Newton steps from a bracketed root; keep only steps that stay in [lo, hi] and improve."""
    ft = func(t)
    for _ in range(steps):
        if ft == 0.0:
            break
        d = dfunc(t)
        if d == 0.0 or not math.isfinite(d):
            break
        tn = t - ft / d
        if not (lo <= tn <= hi):
            break
        fn = func(tn)
        if abs(fn) < abs(ft):
            t, ft = tn, fn
        else:
            break
    return t


# --------------------------------------------------------------------------
# Stumpff functions and their series
# --------------------------------------------------------------------------

def x_minus_sin(x):
    """x - sin x (series below 1)."""
    if abs(x) >= 1.0:
        return x - math.sin(x)
    x2 = x * x
    term = x * x2 / 6.0
    total = 0.0
    k = 1
    while k < 40:
        total += term
        k += 1
        term *= -x2 / ((2 * k) * (2 * k + 1))
        if abs(term) <= 1e-18 * abs(total):
            break
    return total


def sinh_minus_x(x):
    """sinh x - x (series below 1)."""
    if abs(x) >= 1.0:
        return math.sinh(x) - x
    x2 = x * x
    term = x * x2 / 6.0
    total = 0.0
    k = 1
    while k < 40:
        total += term
        k += 1
        term *= x2 / ((2 * k) * (2 * k + 1))
        if abs(term) <= 1e-18 * abs(total):
            break
    return total


def stumpff(z):
    """Return (C(z), S(z)); series for |z| < 1, half-angle closed forms otherwise."""
    if abs(z) < 1.0:
        c = 0.0
        s = 0.0
        term_c = 0.5          # 1/2!
        term_s = 1.0 / 6.0    # 1/3!
        k = 0
        while k < 30:
            c += term_c
            s += term_s
            k += 1
            term_c *= -z / ((2 * k + 1) * (2 * k + 2))
            term_s *= -z / ((2 * k + 2) * (2 * k + 3))
            if abs(term_c) < 1e-20 * c and abs(term_s) < 1e-20 * s:
                break
        return c, s
    if z > 0.0:
        x = math.sqrt(z)
        sh = math.sin(0.5 * x)
        return 2.0 * sh * sh / z, x_minus_sin(x) / (z * x)
    x = math.sqrt(-z)
    sh = math.sinh(0.5 * x)
    return 2.0 * sh * sh / (-z), sinh_minus_x(x) / ((-z) * x)


def kernel_hyp(w):
    """S / C^(3/2) at z = -w^2:  (sinh w - w) / (2 sqrt2 sinh^3(w/2)), w >= 0."""
    if w == 0.0:
        return SQRT2 / 3.0
    h = 0.5 * w
    if w < 20.0:
        s = math.sinh(h)
        return sinh_minus_x(w) / (2.0 * SQRT2 * s * s * s)
    s = math.sinh(h)
    ch = math.cosh(h)
    return (2.0 * (ch / s) / s - ((w / s) / s) / s) / (2.0 * SQRT2)


def kernel_hyp_L(w):
    """(2 sinh(w/2) - w cosh(w/2)) / (2 sinh^3(w/2))  (negative; -1/3 at w = 0)."""
    if w == 0.0:
        return -1.0 / 3.0
    h = 0.5 * w
    s = math.sinh(h)
    if w < 3.0:
        # 2 sinh h - 2 h cosh h = -sum_{k>=1} 4 k h^(2k+1)/(2k+1)!
        h2 = h * h
        p = h * h2 / 6.0
        total = 0.0
        k = 1
        while k < 60:
            term = -4.0 * k * p
            total += term
            if abs(term) <= 1e-18 * abs(total):
                break
            k += 1
            p *= h2 / ((2 * k) * (2 * k + 1))
        return total / (2.0 * s * s * s)
    ch = math.cosh(h)
    return (1.0 / s) / s - 0.5 * w * ((ch / s) / s) / s


# --------------------------------------------------------------------------
# Universal-variable Kepler propagation
# --------------------------------------------------------------------------

def wrap_half_period(dt, period):
    """Reduce dt into [-P/2, P/2) exactly with respect to the double `period`."""
    k = math.floor(dt / period + 0.5)
    if k == 0 and -0.5 * period <= dt < 0.5 * period:
        return dt
    fd = Fraction(dt)
    fp = Fraction(period)
    rem = fd - k * fp
    while rem >= fp / 2:
        k += 1
        rem = fd - k * fp
    while rem < -fp / 2:
        k -= 1
        rem = fd - k * fp
    return float(rem)


def kepler_universal(r0v, v0v, dt, mu, alpha=None):
    """Propagate (r0v, v0v) by dt seconds; alpha = 1/a may be supplied exactly.

    Returns r, v and the Lagrange coefficients (f, g, fdot, gdot)."""
    r0v = np.asarray(r0v, dtype=float)
    v0v = np.asarray(v0v, dtype=float)
    r0 = math.sqrt(float(r0v @ r0v))
    sm = math.sqrt(mu)
    sigma0 = float(r0v @ v0v) / sm
    if alpha is None:
        alpha = 2.0 / r0 - float(v0v @ v0v) / mu

    if alpha > 0.0:
        sa = math.sqrt(1.0 / alpha)
        period = TWO_PI * sa * sa * sa / sm
        dt = wrap_half_period(dt, period)

    def stf(chi):
        z = alpha * chi * chi
        C, S = stumpff(z)
        return z, C, S

    def F(chi):
        z, C, S = stf(chi)
        return sm * dt - (chi * chi * chi * S + sigma0 * chi * chi * C + r0 * chi * (1.0 - z * S))

    def radius(chi):
        z, C, S = stf(chi)
        return chi * chi * C + sigma0 * chi * (1.0 - z * S) + r0 * (1.0 - z * C)

    if dt == 0.0:
        chi = 0.0
    else:
        if alpha > 0.0:
            # F(-2 pi sqrt a) = sm (dt + P) > 0, F(2 pi sqrt a) = sm (dt - P) < 0
            lo, hi = -TWO_PI * sa, TWO_PI * sa
        else:
            scale = math.sqrt(-1.0 / alpha) if alpha < 0.0 else math.sqrt(r0)
            if dt > 0.0:
                lo, hi = 0.0, scale
                while F(hi) > 0.0:
                    lo = hi
                    hi *= 2.0
                    if hi > 1e4 * scale:
                        raise RuntimeError("hyperbolic Kepler bracket exceeded")
            else:
                lo, hi = -scale, 0.0
                while F(lo) < 0.0:
                    hi = lo
                    lo *= 2.0
                    if -lo > 1e4 * scale:
                        raise RuntimeError("hyperbolic Kepler bracket exceeded")
        chi = root(F, lo, hi)
        chi = newton_polish(F, lambda c: -radius(c), chi, lo, hi)

    z, C, S = stf(chi)
    chi2C = chi * chi * C
    one_m_zS = 1.0 - z * S
    r = chi2C + sigma0 * chi * one_m_zS + r0 * (1.0 - z * C)
    f = 1.0 - chi2C / r0
    g = (sigma0 * chi2C + r0 * chi * one_m_zS) / sm      # = dt - chi^3 S / sm without cancellation
    gdot = 1.0 - chi2C / r
    fdot = -sm / (r * r0) * chi * one_m_zS
    rv = f * r0v + g * v0v
    vv = fdot * r0v + gdot * v0v
    return rv, vv, (f, g, fdot, gdot)


# --------------------------------------------------------------------------
# Objects from classical elements
# --------------------------------------------------------------------------

def rotation_matrix(Omega_deg, i_deg, omega_deg):
    O = math.radians(Omega_deg)
    I = math.radians(i_deg)
    w = math.radians(omega_deg)
    cO, sO = math.cos(O), math.sin(O)
    ci, si = math.cos(I), math.sin(I)
    cw, sw = math.cos(w), math.sin(w)
    Rz_O = np.array([[cO, -sO, 0.0], [sO, cO, 0.0], [0.0, 0.0, 1.0]])
    Rx_i = np.array([[1.0, 0.0, 0.0], [0.0, ci, -si], [0.0, si, ci]])
    Rz_w = np.array([[cw, -sw, 0.0], [sw, cw, 0.0], [0.0, 0.0, 1.0]])
    return Rz_O @ Rx_i @ Rz_w


class Body:
    """An object given by elements, propagated from its periapsis state."""

    def __init__(self, obj, mu):
        self.name = obj["name"]
        self.mu = mu
        self.a = float(obj["a_km"])
        self.e = float(obj["e"])
        self.t0 = float(obj["t0_days"])
        self.M0_deg = float(obj["M0_deg"])
        self.R = rotation_matrix(float(obj["Omega_deg"]), float(obj["i_deg"]), float(obj["omega_deg"]))
        if self.a > 0.0:
            self.rp = self.a * (1.0 - self.e)
        else:
            self.rp = -self.a * (self.e - 1.0)
        self.vp = math.sqrt(mu * (1.0 + self.e) / self.rp)
        self.alpha = 1.0 / self.a
        abs_a = Decimal(abs(self.a))
        self.n_dec = (Decimal(mu) / (abs_a * abs_a * abs_a)).sqrt()
        self.period_dec = 2 * PI_DEC / self.n_dec if self.a > 0.0 else None

    def dt_from_periapsis(self, t_days):
        """Seconds since periapsis passage (50 digits), reduced into [-P/2, P/2) for ellipses."""
        dt = (Decimal(t_days) - Decimal(self.t0)) * DAY + Decimal(self.M0_deg) * PI_DEC / (180 * self.n_dec)
        if self.a > 0.0:
            P = self.period_dec
            k = (dt / P + Decimal("0.5")).to_integral_value(rounding="ROUND_FLOOR")
            dt = dt - k * P
            if dt >= P / 2:
                dt -= P
            if dt < -P / 2:
                dt += P
        return float(dt)

    def state(self, t_days):
        dt = self.dt_from_periapsis(t_days)
        rpf, vpf, _ = kepler_universal(np.array([self.rp, 0.0, 0.0]), np.array([0.0, self.vp, 0.0]),
                                       dt, self.mu, alpha=self.alpha)
        return self.R @ rpf, self.R @ vpf


# --------------------------------------------------------------------------
# Lambert: universal variable formulation
# --------------------------------------------------------------------------

class Lambert:
    """TOF(z) for fixed r1, r2 (prograde), in cancellation-free half-angle form.

    Elliptic points are (N, side, t): side 0 means u = t, side 1 means
    eps = pi - u = t, with z = (2 pi N + 2 u)^2.  Hyperbolic points use w =
    sqrt(-z) (or y itself when A > 0 and y < y0/2)."""

    def __init__(self, r1v, r2v, T, mu):
        self.r1v = np.asarray(r1v, dtype=float)
        self.r2v = np.asarray(r2v, dtype=float)
        self.T = float(T)
        self.mu = float(mu)
        self.sm = math.sqrt(self.mu)
        self.r1 = math.sqrt(float(self.r1v @ self.r1v))
        self.r2 = math.sqrt(float(self.r2v @ self.r2v))
        cross = np.cross(self.r1v, self.r2v)
        dot = float(self.r1v @ self.r2v)
        theta = math.atan2(math.sqrt(float(cross @ cross)), dot)
        if cross[2] < 0.0:
            theta = TWO_PI - theta
        self.theta = theta
        self.A = SQRT2 * math.sqrt(self.r1 * self.r2) * math.cos(0.5 * theta)
        self.absA = abs(self.A)
        self.Y0 = self.r1 + self.r2
        self.q = 2.0 * SQRT2 * self.absA
        dvec = self.r2v - self.r1v
        c2 = float(dvec @ dvec)
        self.y0 = c2 / (self.Y0 + SQRT2 * self.absA)     # = r1 + r2 - sqrt2 |A|
        self.Tsm = self.T * self.sm                       # target of F = sqrt(mu) TOF
        self.setup_frame()

    # ---- elliptic ---------------------------------------------------------
    def ell(self, N, side, t):
        """Return (sin u, cos u, W = 2u + 2 pi N - sin 2u, y)."""
        h = 0.5 * t
        if side == 0:
            su = math.sin(t)
            cu = math.cos(t)
            s2h = math.sin(h) ** 2
            c2h = math.cos(h) ** 2
            W = TWO_PI * N + x_minus_sin(2.0 * t)
        else:
            su = math.sin(t)
            cu = -math.cos(t)
            s2h = math.cos(h) ** 2
            c2h = math.sin(h) ** 2
            W = TWO_PI * (N + 1) - x_minus_sin(2.0 * t)
        y = self.y0 + self.q * (s2h if self.A > 0.0 else c2h)
        return su, cu, W, y

    def ell_K(self, N, side, t):
        su, cu, W, y = self.ell(N, side, t)
        if su == 0.0:
            if N == 0 and side == 0:
                return su, cu, W, y, SQRT2 / 3.0          # parabolic limit
            return su, cu, W, y, math.inf
        return su, cu, W, y, W / (2.0 * SQRT2 * su * su * su)

    def F_ell(self, N, side, t):
        """sqrt(mu) * TOF."""
        su, cu, W, y, K = self.ell_K(N, side, t)
        return math.sqrt(y) * (y * K + self.A)

    def dF_ell(self, N, side, t):
        """d(sqrt(mu) TOF)/dt (t = u for side 0, t = eps for side 1)."""
        su, cu, W, y, K = self.ell_K(N, side, t)
        sy = math.sqrt(y)
        dy = SQRT2 * self.A * su
        dK = (4.0 * su * su * su - 3.0 * cu * W) / (2.0 * SQRT2 * su * su * su * su)
        d = dy * (1.5 * sy * K + 0.5 * self.A / sy) + y * sy * dK
        return d if side == 0 else -d

    def a_ell(self, N, side, t):
        su, cu, W, y = self.ell(N, side, t)
        return y / (2.0 * su * su)             # chi^2 / z

    # ---- hyperbolic ------------------------------------------------------
    def y_hyp(self, w):
        s = math.sinh(0.25 * w)
        if self.A > 0.0:
            return self.y0 - self.q * s * s
        return self.Y0 + SQRT2 * self.absA + self.q * s * s

    def F_hyp_w(self, w):
        y = self.y_hyp(w)
        if self.A > 0.0:
            if y <= 0.0:
                return 0.0
            return math.sqrt(y) * (y * kernel_hyp(w) + self.A)
        return math.sqrt(y) * (self.Y0 * kernel_hyp(w) + self.absA * kernel_hyp_L(w))

    def w_of_y(self, y):
        """A > 0: w from y = y0 - q sinh^2(w/4); accurate when y0 - y is not small."""
        s = (self.y0 - y) / self.q
        return 4.0 * math.asinh(math.sqrt(max(s, 0.0)))

    def F_hyp_y(self, y):
        if y <= 0.0:
            return 0.0
        return math.sqrt(y) * (y * kernel_hyp(self.w_of_y(y)) + self.A)

    # ---- velocities from y and cos u ---------------------------------------
    def setup_frame(self):
        """Unit vectors r1^, r2^ and the prograde plane normal h^."""
        self.e1 = self.r1v / self.r1
        self.e2 = self.r2v / self.r2
        cross = np.cross(self.r1v, self.r2v)
        n = cross / math.sqrt(float(cross @ cross))
        self.hhat = n if self.theta < PI else -n
        self.t1 = np.cross(self.hhat, self.e1)
        self.t2 = np.cross(self.hhat, self.e2)

    def velocities(self, y, cosU):
        """Radial / transverse components (no f, g cancellation near theta = pi).

        From v1 = (r2 - f r1)/g, v2 = (gdot r2 - r1)/g with f = 1 - y/r1,
        g = A sqrt(y/mu), gdot = 1 - y/r2 and y = r1 + r2 - sqrt2 A cosU
        (cosU = cos u elliptic, cosh(w/2) hyperbolic):
            v_r1 = 2k (sqrt(r2/r1) cos(theta/2) - cosU),  v_t1 = 2k sqrt(r2/r1) sin(theta/2),
            v_r2 = 2k (cosU - sqrt(r1/r2) cos(theta/2)),  v_t2 = 2k sqrt(r1/r2) sin(theta/2),
        with k = sqrt(mu / (2 y))."""
        k2 = 2.0 * math.sqrt(self.mu / (2.0 * y))
        ch = math.cos(0.5 * self.theta)
        sh = math.sin(0.5 * self.theta)
        q12 = math.sqrt(self.r2 / self.r1)
        q21 = math.sqrt(self.r1 / self.r2)
        v1 = k2 * (q12 * ch - cosU) * self.e1 + k2 * q12 * sh * self.t1
        v2 = k2 * (cosU - q21 * ch) * self.e2 + k2 * q21 * sh * self.t2
        return v1, v2

    def velocities_fg(self, y):
        """Classical f, g form (used only as a cross-check)."""
        f = 1.0 - y / self.r1
        g = self.A * math.sqrt(y / self.mu)
        gdot = 1.0 - y / self.r2
        return (self.r2v - f * self.r1v) / g, (gdot * self.r2v - self.r1v) / g

    # ---- monotone-piece root solve ----------------------------------------
    def _solve_piece(self, N, side, lo, hi):
        """Root of F_ell - Tsm on [lo, hi] in variable t of `side`."""
        func = lambda t: self.F_ell(N, side, t) - self.Tsm
        t = root(func, lo, hi)
        t = newton_polish(func, lambda s: self.dF_ell(N, side, s), t, lo, hi)
        return t

    def _toward_pole(self, N, side, t_far):
        """Point t in (0, t_far) with F_ell(t) > Tsm (F -> +inf as t -> 0 on this side)."""
        t = t_far
        for _ in range(1100):
            t *= 0.5
            if self.F_ell(N, side, t) > self.Tsm:
                return t
        raise RuntimeError("pole bracket failed")

    # ---- zero-revolution solution ----------------------------------------
    def solve_zero_rev(self):
        """Return (y, a_lambert, cosU, descriptor)."""
        Fp = self.F_ell(0, 0, 0.0)             # parabolic
        if self.Tsm > Fp:
            # elliptic: F increasing in u on (0, pi)
            if self.F_ell(0, 0, HALF_PI) >= self.Tsm:
                t = self._solve_piece(0, 0, 0.0, HALF_PI)
                side = 0
            else:
                lo = self._toward_pole(0, 1, HALF_PI)
                t = self._solve_piece(0, 1, lo, HALF_PI)
                side = 1
            su, cu, W, y = self.ell(0, side, t)
            return y, self.a_ell(0, side, t), cu, ("ell", side, t)
        # hyperbolic: F decreasing in w
        if self.A > 0.0:
            w_half = 4.0 * math.asinh(math.sqrt(0.5 * self.y0 / self.q))     # y = y0/2
            if self.F_hyp_w(w_half) <= self.Tsm:
                func = lambda w: self.F_hyp_w(w) - self.Tsm
                w = root(func, 0.0, w_half)
                w = newton_polish(func, lambda s: self._numd(func, s), w, 0.0, w_half)
                y = self.y_hyp(w)
                sh = math.sinh(0.5 * w)
                return y, -y / (2.0 * sh * sh), 1.0 + 2.0 * math.sinh(0.25 * w) ** 2, ("hyp_w", w)
            func = lambda y: self.F_hyp_y(y) - self.Tsm
            hi = 0.5 * self.y0
            lo = hi
            for _ in range(1100):
                lo *= 0.5
                if func(lo) < 0.0:
                    break
            else:
                raise RuntimeError("hyperbolic y bracket failed")
            y = root(func, lo, hi)
            y = newton_polish(func, lambda s: self._numd(func, s), y, lo, hi)
            s = (self.y0 - y) / self.q
            return y, -y / (8.0 * s * (1.0 + s)), 1.0 + 2.0 * s, ("hyp_y", self.w_of_y(y))
        func = lambda w: self.F_hyp_w(w) - self.Tsm
        lo, hi = 0.0, 1.0
        while func(hi) > 0.0:
            lo = hi
            hi *= 2.0
            if hi > 1200.0:
                raise RuntimeError("hyperbolic w bracket failed")
        w = root(func, lo, hi)
        w = newton_polish(func, lambda s: self._numd(func, s), w, lo, hi)
        y = self.y_hyp(w)
        sh = math.sinh(0.5 * w)
        return y, -y / (2.0 * sh * sh), 1.0 + 2.0 * math.sinh(0.25 * w) ** 2, ("hyp_w", w)

    @staticmethod
    def _numd(func, x):
        h = 1e-7 * max(abs(x), 1e-3)
        return (func(x + h) - func(x - h)) / (2.0 * h)

    # ---- N-revolution: minimiser and T_min ---------------------------------
    def minimise(self, N):
        """Return (side, t_min, F_min); dF changes sign once on (0, pi)."""
        d_mid = self.dF_ell(N, 0, HALF_PI)
        if d_mid == 0.0:
            return 0, HALF_PI, self.F_ell(N, 0, HALF_PI)
        side = 0 if d_mid > 0.0 else 1
        # on either side dF/dt < 0 near t -> 0 and dF/dt >= 0 at t = pi/2 (sign flips with side 1)
        t = HALF_PI
        for _ in range(1100):
            t *= 0.5
            if self.dF_ell(N, side, t) < 0.0:
                break
        else:
            raise RuntimeError("T_min derivative bracket failed")
        tm = root(lambda s: self.dF_ell(N, side, s), t, HALF_PI)
        return side, tm, self.F_ell(N, side, tm)

    def solve_multi_rev(self, N, side_m, t_m, F_m):
        """Both N-revolution roots (side, t) when Tsm > F_m, else []."""
        if not (self.Tsm > F_m):
            return []
        out = []
        # piece on the minimiser's side, towards that side's pole (t -> 0):
        lo = self._toward_pole(N, side_m, t_m)
        out.append((side_m, self._solve_piece(N, side_m, lo, t_m)))
        # piece across u = pi/2 on the far side of the minimiser:
        other = 1 - side_m
        if self.F_ell(N, side_m, HALF_PI) >= self.Tsm:
            out.append((side_m, self._solve_piece(N, side_m, t_m, HALF_PI)))
        else:
            lo = self._toward_pole(N, other, HALF_PI)
            out.append((other, self._solve_piece(N, other, lo, HALF_PI)))
        return out


def orbit_a_e(rv, vv, mu):
    r = math.sqrt(float(rv @ rv))
    v2 = float(vv @ vv)
    a = 1.0 / (2.0 / r - v2 / mu)
    evec = ((v2 - mu / r) * rv - float(rv @ vv) * vv) / mu
    e = math.sqrt(float(evec @ evec))
    return a, e


def solve_transfer(r1v, vA, r2v, vB, T, mu, n_max, diagnostics=None):
    lam = Lambert(r1v, r2v, T, mu)
    solutions = []

    def make(N, y, a_lam, cosU, desc):
        v1, v2 = lam.velocities(y, cosU)
        # a = chi^2 / z from the Lambert variables (cancellation-free); the
        # vis-viva value agrees to ~1e-14 and is kept as a diagnostic.
        a_vis, e = orbit_a_e(lam.r1v, v1, mu)
        dv = float(np.linalg.norm(v1 - vA) + np.linalg.norm(vB - v2))
        rec = {"N": N, "branch": "single", "v1_km_s": [float(t) for t in v1],
               "v2_km_s": [float(t) for t in v2], "a_km": float(a_lam), "e": float(e),
               "dv_km_s": dv}
        diag = {"N": N, "y": y, "a_lambert": a_lam, "a_vis_viva": a_vis, "cosU": cosU, "desc": desc}
        return rec, diag

    diags = []
    y, a_lam, cosU, desc = lam.solve_zero_rev()
    rec, dg = make(0, y, a_lam, cosU, desc)
    solutions.append(rec)
    diags.append(dg)

    t_min = []
    for N in range(1, n_max + 1):
        side_m, t_m, F_m = lam.minimise(N)
        t_min.append(F_m / lam.sm / DAY)
        roots = lam.solve_multi_rev(N, side_m, t_m, F_m)
        if roots:
            pair = []
            for (side, t) in roots:
                su, cu, W, yy = lam.ell(N, side, t)
                pair.append(make(N, yy, lam.a_ell(N, side, t), cu, ("ell", side, t)))
            pair.sort(key=lambda p: p[0]["a_km"])
            pair[0][0]["branch"] = "low"
            pair[1][0]["branch"] = "high"
            for rec, dg in pair:
                dg["branch"] = rec["branch"]
                solutions.append(rec)
                diags.append(dg)
        if diagnostics is not None:
            diagnostics.setdefault("minima", []).append((N, side_m, t_m, F_m / lam.sm))

    best = min(range(len(solutions)), key=lambda i: solutions[i]["dv_km_s"])
    if diagnostics is not None:
        diagnostics["solutions"] = diags
    return lam, t_min, solutions, best


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

def compute_report(system, diagnostics=None):
    mu = float(system["mu_km3_s2"])
    bodies = {obj["name"]: Body(obj, mu) for obj in system["objects"]}

    ephemeris = []
    for q in system["ephemeris_queries"]:
        rv, vv = bodies[q["object"]].state(float(q["t_days"]))
        ephemeris.append({"object": q["object"], "t_days": q["t_days"],
                          "r_km": [float(t) for t in rv], "v_km_s": [float(t) for t in vv]})

    transfers = []
    for q in system["transfer_queries"]:
        A = bodies[q["from"]]
        B = bodies[q["to"]]
        t1 = float(q["t1_days"])
        t2 = float(q["t2_days"])
        T = float((Decimal(t2) - Decimal(t1)) * DAY)
        r1v, vA = A.state(t1)
        r2v, vB = B.state(t2)
        n_max = int(q["n_max"])
        dg = {} if diagnostics is not None else None
        lam, t_min, solutions, best = solve_transfer(r1v, vA, r2v, vB, T, mu, n_max, dg)
        if diagnostics is not None:
            dg.update({"r1": r1v, "v_from": vA, "r2": r2v, "v_to": vB, "T": T, "lam": lam})
            diagnostics.append(dg)
        transfers.append({"from": q["from"], "t1_days": q["t1_days"], "to": q["to"],
                          "t2_days": q["t2_days"], "n_max": q["n_max"],
                          "theta_deg": math.degrees(lam.theta), "t_min_days": t_min,
                          "solutions": solutions, "best": best})

    return {"system_id": system["system_id"], "ephemeris": ephemeris, "transfers": transfers}


def check_finite(obj, path="report"):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        if not math.isfinite(obj):
            raise ValueError("non-finite number at %s" % path)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            check_finite(v, path + "." + str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            check_finite(v, path + "[%d]" % i)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    with open(args.system, "r", encoding="utf-8") as fh:
        system = json.load(fh)
    report = compute_report(system)
    check_finite(report)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, allow_nan=False)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
