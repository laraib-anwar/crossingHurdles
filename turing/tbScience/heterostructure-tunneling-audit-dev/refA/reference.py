#!/usr/bin/env python3
"""Reference A for HETERO_SPEC (bound states and transmission of a layered heterostructure).

Formulation: one GLOBAL linear system for the whole structure.

* psi is written in every layer as c1 f1 + c2 f2 on a basis normalised at the layer ends so that
  the coefficients stay O(1):
    flat, q d^2 > 1  (q = m (E - V) / C):  cos(k s), sin(k s)
    flat, |q| d^2 <= 1:                      C(q, s), S(q, s) / d   (entire in E, power series)
    flat, q d^2 < -1:                        exp(-kappa s), exp(kappa (s - d))
    sloped:                                  Ai(z) / S_A, Bi(z) / S_B,  z = lambda (V(x) - E),
                                             S_A = Ai(max(z_min, 0)), S_B = Bi(max(z_max, 0)),
                                             exponentially scaled Airy (airye) for z > 0;
      z > 0 on the whole layer: zeta(z_max) - zeta(z_min) formed without cancellation;
      z <= -12 on the whole layer: the same basis rotated by the Airy phase at the left end,
      M(x) sin(theta - theta_a), M(x) cos(theta - theta_a) (x = -z) from the large-argument
      modulus/phase series, with theta_b - theta_a formed without cancellation.
  All normalisations are positive and continuous in E (or change by a positive factor), so
  det D(E) keeps a consistent sign and vanishes exactly at the bound states.
* The 2 (N + 1) continuity equations (psi and psi'/m) at the N + 1 interfaces form D(E) x = b.
  Bound states: roots of det D(E) with decaying leads (LU sign and log-magnitude), isolated and
  certified by an independent Sturm count (number of nodes of the solution decaying at -inf,
  Prufer phase: exact phase in flat layers, Airy modulus/phase in sloped layers).
  Transmission: solve D x = b with unit incident amplitude, T = (k_R/m_R)/(k_L/m_L) |t|^2.
  Maxima: dT/dE from dx/dE = D^-1 (db/dE - dD/dE x) with analytic basis derivatives; sign scan
  on a grid of step <= 5e-5 eV (< 2e-4 eV extremum spacing of guarantee 3), Brent on dT/dE.

Command line: python reference.py --structure <structure.json> --output <report.json>
"""
import argparse
import json
import math

import numpy as np
from scipy.optimize import brentq
from scipy.special import airy, airye

C = 0.0380998212            # eV nm^2
MU = math.sqrt(C * 0.3)     # constant positive scale of the flux rows (conditioning only)
PI = math.pi
_A0 = airy(0.0)
AI0 = float(_A0[0])         # Ai(0)
BI0 = float(_A0[2])         # Bi(0)
LN_AI0 = math.log(AI0)
LN_BI0 = math.log(BI0)
SCAN_STEP = 5.0e-5          # eV, < 2e-4 eV (guarantee 3)

# reciprocal factorials for the regime-2 power series
_NSER = 24
_INV_FACT_EVEN = [1.0 / math.factorial(2 * n) for n in range(_NSER)]
_INV_FACT_ODD = [1.0 / math.factorial(2 * n + 1) for n in range(_NSER)]

# large-argument Airy modulus/phase: M^2 = (pi sqrt(x))^-1 sum_k (-1)^k (6k-1)!!/(k! 96^k) x^-3k,
# theta = pi/4 + (2/3) x^1.5 + sum_k>=1 th_k x^(1.5-3k) from theta' = 1/(pi M^2) (exact fractions)
ZASY = 12.0
_NASY = 9


def _asy_coefficients(K):
    from fractions import Fraction
    c = []
    for k in range(K):
        num = 1
        for j in range(1, 6 * k, 2):
            num *= j
        c.append(Fraction((-1) ** k * num, math.factorial(k) * 96 ** k))
    e = [Fraction(1)]
    for k in range(1, K):
        e.append(-sum(c[j] * e[k - j] for j in range(1, k + 1)))
    th = [Fraction(0)] + [e[k] / (Fraction(3, 2) - 3 * k) for k in range(1, K)]
    return [float(v) for v in c], [float(v) for v in th]


_ASY_M2, _ASY_TH = _asy_coefficients(_NASY)


class Layer:
    __slots__ = ("d", "m", "vl", "vr", "flat", "slope", "lam", "beta")

    def __init__(self, d, m, vl, vr):
        self.d = float(d)
        self.m = float(m)
        self.vl = float(vl)
        self.vr = float(vr)
        self.flat = (self.vl == self.vr)
        if self.flat:
            self.slope = 0.0
            self.lam = 0.0
            self.beta = 0.0
        else:
            self.slope = (self.vr - self.vl) / self.d
            # z = lam (V(x) - E) = beta (x - x_turn);  lam = beta / slope > 0
            self.lam = (self.m / (C * self.slope * self.slope)) ** (1.0 / 3.0)
            self.beta = math.copysign((self.m * abs(self.slope) / C) ** (1.0 / 3.0), self.slope)


class Model:
    def __init__(self, s):
        self.sid = s["structure_id"]
        self.mL = float(s["left_lead"]["mass"])
        self.VL = float(s["left_lead"]["v_eV"])
        self.mR = float(s["right_lead"]["mass"])
        self.VR = float(s["right_lead"]["v_eV"])
        self.layers = [Layer(L["thickness_nm"], L["mass"], L["vl_eV"], L["vr_eV"])
                       for L in s["layers"]]
        self.Eq_raw = list(s["transmission_energies_eV"])
        self.Eq = [float(e) for e in self.Eq_raw]
        self.win = (float(s["window_eV"][0]), float(s["window_eV"][1]))
        self.N = len(self.layers)
        self.n = 2 * self.N + 2
        vals = [self.VL, self.VR]
        for L in self.layers:
            vals += [L.vl, L.vr]
        self.Vmin = min(vals)
        self.Vmax = max(vals)


# ----------------------------------------------------------------------------------------------
# Basis values at the two ends of a layer, vectorised over energies.
# Row order: f1(0), f2(0), w1(0), w2(0), f1(d), f2(d), w1(d), w2(d)   (w = psi' / m)
# ----------------------------------------------------------------------------------------------
def _basis_flat(L, E, need_d):
    nE = E.shape[0]
    B = np.zeros((8, nE))
    dB = np.zeros((8, nE)) if need_d else None
    m, d = L.m, L.d
    q = m * (E - L.vl) / C
    qd2 = q * d * d
    g = m / C                                   # dq/dE
    r1 = qd2 > 1.0
    r3 = qd2 < -1.0
    r2 = ~(r1 | r3)
    if r1.any():                                # oscillatory: cos(ks), sin(ks)
        k = np.sqrt(q[r1])
        kd = k * d
        c, s = np.cos(kd), np.sin(kd)
        B[0, r1] = 1.0
        B[3, r1] = k / m
        B[4, r1] = c
        B[5, r1] = s
        B[6, r1] = -(k / m) * s
        B[7, r1] = (k / m) * c
        if need_d:
            dk = m / (2.0 * C * k)
            dB[3, r1] = dk / m
            dB[4, r1] = -d * s * dk
            dB[5, r1] = d * c * dk
            dB[6, r1] = -(s + kd * c) * dk / m
            dB[7, r1] = (c - kd * s) * dk / m
    if r2.any():                                # entire basis C(q,s), S(q,s)/d
        qq = q[r2]
        y = -qq * d * d                         # |y| <= 1
        Cd = np.zeros_like(y)
        Sd = np.zeros_like(y)
        dCd = np.zeros_like(y)
        dSd = np.zeros_like(y)
        yp = np.ones_like(y)                    # y^n
        ypm = np.zeros_like(y)                  # n y^(n-1)
        for nn in range(_NSER):
            Cd += yp * _INV_FACT_EVEN[nn]
            Sd += yp * _INV_FACT_ODD[nn]
            if nn >= 1:
                dCd += ypm * _INV_FACT_EVEN[nn]
                dSd += ypm * _INV_FACT_ODD[nn]
            ypm = yp * (nn + 1)
            yp = yp * y
        Sd = Sd * d                             # S(q, d)
        dCd = -d * d * dCd                      # dC(q,d)/dq
        dSd = -d * d * d * dSd                  # dS(q,d)/dq
        B[0, r2] = 1.0
        B[3, r2] = 1.0 / (m * d)
        B[4, r2] = Cd
        B[5, r2] = Sd / d
        B[6, r2] = -qq * Sd / m
        B[7, r2] = Cd / (m * d)
        if need_d:
            dB[4, r2] = g * dCd
            dB[5, r2] = g * dSd / d
            dB[6, r2] = -g * (Sd + qq * dSd) / m
            dB[7, r2] = g * dCd / (m * d)
    if r3.any():                                # evanescent: exp(-kap s), exp(kap (s - d))
        kap = np.sqrt(-q[r3])
        e = np.exp(-kap * d)
        B[0, r3] = 1.0
        B[1, r3] = e
        B[2, r3] = -kap / m
        B[3, r3] = kap * e / m
        B[4, r3] = e
        B[5, r3] = 1.0
        B[6, r3] = -kap * e / m
        B[7, r3] = kap / m
        if need_d:
            dkap = -m / (2.0 * C * kap)
            dB[1, r3] = -d * e * dkap
            dB[2, r3] = -dkap / m
            dB[3, r3] = e * (1.0 - kap * d) * dkap / m
            dB[4, r3] = -d * e * dkap
            dB[6, r3] = -e * (1.0 - kap * d) * dkap / m
            dB[7, r3] = dkap / m
    return B, dB


def _airy_scaled(z):
    """Ai, Ai', Bi, Bi' with exponents: Ai = a * exp(xa), Bi = b * exp(xb) (vectorised)."""
    zn = np.minimum(z, 0.0)
    zp = np.maximum(z, 0.0)
    an, apn, bn, bpn = airy(zn)
    ap, app, bp, bpp = airye(zp)
    pos = z > 0.0
    zeta = (2.0 / 3.0) * zp * np.sqrt(zp)
    a = np.where(pos, ap, an)
    ad = np.where(pos, app, apn)
    b = np.where(pos, bp, bn)
    bd = np.where(pos, bpp, bpn)
    xa = np.where(pos, -zeta, 0.0)
    xb = np.where(pos, zeta, 0.0)
    return a, ad, b, bd, xa, xb


def _x15_diff(x1, x2, dx):
    """x2^1.5 - x1^1.5 for x1, x2 >= 0 without cancellation, given dx = x2 - x1 exactly."""
    s1 = np.sqrt(x1)
    s2 = np.sqrt(x2)
    return dx * (x1 + s1 * s2 + x2) / (s1 + s2)


def _modphase(x):
    """Large-argument modulus/phase of Ai(-x) = M sin(theta), Bi(-x) = M cos(theta), x >= ZASY.

    Returns M, dM/dx, dtheta/dx = 1 / (pi M^2), and theta - pi/4 - (2/3) x^1.5."""
    if x.size <= 8:
        r = np.array([_modphase_scalar(float(v)) for v in x]).reshape(x.size, 4)
        return r[:, 0], r[:, 1], r[:, 2], r[:, 3]
    y = x ** -3.0
    S = np.zeros_like(x)
    dS = np.zeros_like(x)                    # d S / d x
    corr = np.zeros_like(x)
    yk = np.ones_like(x)
    for k in range(_NASY):
        S += _ASY_M2[k] * yk
        if k >= 1:
            dS += _ASY_M2[k] * (-3.0 * k) * yk / x
            corr += _ASY_TH[k] * yk * x * np.sqrt(x)
        yk = yk * y
    rx = np.sqrt(x)
    M2 = S / (PI * rx)
    dM2 = (dS - 0.5 * S / x) / (PI * rx)
    M = np.sqrt(M2)
    return M, dM2 / (2.0 * M), 1.0 / (PI * M2), corr


def _modphase_scalar(x):
    """Scalar version of _modphase (same series, Horner form)."""
    y = x ** -3.0
    S = 0.0
    dSy = 0.0
    corr = 0.0
    for k in range(_NASY - 1, -1, -1):
        S = S * y + _ASY_M2[k]
        if k >= 1:
            dSy = dSy * y + k * _ASY_M2[k]
            corr = corr * y + _ASY_TH[k]
    rx = math.sqrt(x)
    dS = dSy * (-3.0 * y / x)                    # (dS/dy)(dy/dx), dS/dy = sum k c_k y^(k-1)
    corr = corr * y * x * rx
    M2 = S / (PI * rx)
    dM2 = (dS - 0.5 * S / x) / (PI * rx)
    M = math.sqrt(M2)
    return M, dM2 / (2.0 * M), 1.0 / (PI * M2), corr


def _sloped_general(L, za, zb, need_d):
    """Basis Ai(z)/S_A, Bi(z)/S_B, S_A = Ai(max(z_min,0)), S_B = Bi(max(z_max,0)) (scaled Airy)."""
    nE = za.shape[0]
    B = np.zeros((8, nE))
    dB = np.zeros((8, nE)) if need_d else None
    lam, beta, m = L.lam, L.beta, L.m
    zmin = np.minimum(za, zb)
    zmax = np.maximum(za, zb)
    a1, ad1, _, _, xa1, _ = _airy_scaled(np.maximum(zmin, 0.0))
    lnSA = np.where(zmin > 0.0, np.log(a1) + xa1, LN_AI0)
    lA = np.where(zmin > 0.0, ad1 / a1, 0.0)              # d ln S_A / dz_min
    _, _, b2, bd2, _, xb2 = _airy_scaled(np.maximum(zmax, 0.0))
    lnSB = np.where(zmax > 0.0, np.log(b2) + xb2, LN_BI0)
    lB = np.where(zmax > 0.0, bd2 / b2, 0.0)
    fac = beta / m
    for off, z in ((0, za), (4, zb)):
        a, ad, b, bd, xa, xb = _airy_scaled(z)
        sa = np.exp(xa - lnSA)
        sb = np.exp(xb - lnSB)
        fA, fAz = a * sa, ad * sa
        fB, fBz = b * sb, bd * sb
        B[off + 0] = fA
        B[off + 1] = fB
        B[off + 2] = fac * fAz
        B[off + 3] = fac * fBz
        if need_d:
            # dz/dE = -lam at every point (also for z_min, z_max)
            dB[off + 0] = -lam * (fAz - fA * lA)
            dB[off + 1] = -lam * (fBz - fB * lB)
            dB[off + 2] = -lam * fac * (z * fA - fAz * lA)
            dB[off + 3] = -lam * fac * (z * fB - fBz * lB)
    return B, dB


def _sloped_evanescent(L, za, zb, need_d):
    """z > 0 on the whole layer: same basis as _sloped_general (S_A = Ai(z_min), S_B = Bi(z_max)),
    with the decay exponent zeta(z_max) - zeta(z_min) formed without cancellation."""
    nE = za.shape[0]
    B = np.zeros((8, nE))
    dB = np.zeros((8, nE)) if need_d else None
    lam, beta, m = L.lam, L.beta, L.m
    zmin = np.minimum(za, zb)
    zmax = np.maximum(za, zb)
    dz = lam * abs(L.vr - L.vl)                            # z_max - z_min, independent of E
    dzeta = (2.0 / 3.0) * _x15_diff(zmin, zmax, dz)
    eAmin, eApmin, eBmin, eBpmin = airye(zmin)
    eAmax, eApmax, eBmax, eBpmax = airye(zmax)
    lA = eApmin / eAmin
    lB = eBpmax / eBmax
    g = np.exp(-dzeta)
    # at z_min: Ai/S_A = 1, Bi/S_B = (eBi(zmin)/eBi(zmax)) exp(-dzeta); at z_max the reverse
    ends = {"min": (np.ones_like(za), lA, eBmin / eBmax * g, eBpmin / eBmax * g),
            "max": (eAmax / eAmin * g, eApmax / eAmin * g, np.ones_like(za), lB)}
    fac = beta / m
    left_is_min = L.slope > 0.0
    for off, z, key in ((0, za, "min" if left_is_min else "max"), (4, zb, "max" if left_is_min else "min")):
        fA, fAz, fB, fBz = ends[key]
        B[off + 0] = fA
        B[off + 1] = fB
        B[off + 2] = fac * fAz
        B[off + 3] = fac * fBz
        if need_d:
            dB[off + 0] = -lam * (fAz - fA * lA)
            dB[off + 1] = -lam * (fBz - fB * lB)
            dB[off + 2] = -lam * fac * (z * fA - fAz * lA)
            dB[off + 3] = -lam * fac * (z * fB - fBz * lB)
    return B, dB


def _sloped_asymptotic(L, za, zb, need_d):
    """z <= -ZASY on the whole layer: rotated basis f1 = M sin(theta - theta_a),
    f2 = M cos(theta - theta_a) of x = -z (theta_a at the left end), i.e. the Ai, Bi basis
    rotated by theta_a (positive determinant); the phase difference across the layer is
    formed without cancellation."""
    nE = za.shape[0]
    B = np.zeros((8, nE))
    dB = np.zeros((8, nE)) if need_d else None
    lam, beta, m = L.lam, L.beta, L.m
    xa = -za
    xb = -zb
    dx = lam * (L.vl - L.vr)                               # x_b - x_a, independent of E
    Ma, dMa, tpa, ca = _modphase(xa)
    Mb, dMb, tpb, cb = _modphase(xb)
    dth = (2.0 / 3.0) * _x15_diff(xa, xb, dx) + (cb - ca)
    sn, cs = np.sin(dth), np.cos(dth)
    wf = -beta / m                                         # w = (1/m) d/dpos = -(beta/m) d/dx
    # left end: f1 = 0, f2 = Ma ; right end: f1 = Mb sin, f2 = Mb cos
    vals = ((0, xa, np.zeros_like(xa), Ma, Ma * tpa, dMa, tpa),
            (4, xb, Mb * sn, Mb * cs, dMb * sn + Mb * tpb * cs, dMb * cs - Mb * tpb * sn, tpb))
    for off, x, f1, f2, f1x, f2x, _ in vals:
        B[off + 0] = f1
        B[off + 1] = f2
        B[off + 2] = wf * f1x
        B[off + 3] = wf * f2x
        if need_d:
            # dx/dE = lam everywhere, d theta_a / dE = lam * theta'(x_a); f'' = -x f
            dB[off + 0] = lam * (f1x - tpa * f2)
            dB[off + 1] = lam * (f2x + tpa * f1)
            dB[off + 2] = wf * lam * (-x * f1 - tpa * f2x)
            dB[off + 3] = wf * lam * (-x * f2 + tpa * f1x)
    return B, dB


def _basis_sloped(L, E, need_d):
    nE = E.shape[0]
    za = L.lam * (L.vl - E)
    zb = L.lam * (L.vr - E)
    asy = np.maximum(za, zb) <= -ZASY
    eva = np.minimum(za, zb) > 0.0
    gen = ~(asy | eva)
    if gen.all():
        return _sloped_general(L, za, zb, need_d)
    B = np.zeros((8, nE))
    dB = np.zeros((8, nE)) if need_d else None
    for mask, fn in ((gen, _sloped_general), (eva, _sloped_evanescent), (asy, _sloped_asymptotic)):
        if mask.any():
            b, db = fn(L, za[mask], zb[mask], need_d)
            B[:, mask] = b
            if need_d:
                dB[:, mask] = db
    return B, dB


def layer_basis(L, E, need_d=False):
    if L.flat:
        return _basis_flat(L, E, need_d)
    return _basis_sloped(L, E, need_d)


def assemble(model, E, mode, need_d=False):
    """Global matrix D(E) (shape (nE, n, n)), right-hand side b and E-derivatives.

    mode 'bound': unknowns [cL, c11, c12, ..., cN1, cN2, cR] with decaying leads, b = 0.
    mode 'trans': unknowns [r, c11, ..., cN2, t], incident amplitude 1 from the left.
    """
    E = np.atleast_1d(np.asarray(E, dtype=float))
    nE = E.shape[0]
    n = model.n
    dt = float if mode == "bound" else complex
    D = np.zeros((nE, n, n), dtype=dt)
    dD = np.zeros((nE, n, n), dtype=dt) if need_d else None
    for j, L in enumerate(model.layers):
        Bv, dBv = layer_basis(L, E, need_d)
        c = 1 + 2 * j
        r = 2 * j
        D[:, r, c] = -Bv[0]
        D[:, r, c + 1] = -Bv[1]
        D[:, r + 1, c] = -MU * Bv[2]
        D[:, r + 1, c + 1] = -MU * Bv[3]
        D[:, r + 2, c] = Bv[4]
        D[:, r + 2, c + 1] = Bv[5]
        D[:, r + 3, c] = MU * Bv[6]
        D[:, r + 3, c + 1] = MU * Bv[7]
        if need_d:
            dD[:, r, c] = -dBv[0]
            dD[:, r, c + 1] = -dBv[1]
            dD[:, r + 1, c] = -MU * dBv[2]
            dD[:, r + 1, c + 1] = -MU * dBv[3]
            dD[:, r + 2, c] = dBv[4]
            dD[:, r + 2, c + 1] = dBv[5]
            dD[:, r + 3, c] = MU * dBv[6]
            dD[:, r + 3, c + 1] = MU * dBv[7]
    mL, VL, mR, VR = model.mL, model.VL, model.mR, model.VR
    if mode == "bound":
        kL = np.sqrt(mL * (VL - E) / C)
        kR = np.sqrt(mR * (VR - E) / C)
        D[:, 0, 0] = 1.0
        D[:, 1, 0] = MU * kL / mL
        D[:, n - 2, n - 1] = -1.0
        D[:, n - 1, n - 1] = MU * kR / mR
        return D, None, dD, None
    kL = np.sqrt(mL * (E - VL) / C)
    kR = np.sqrt(mR * (E - VR) / C)
    D[:, 0, 0] = 1.0
    D[:, 1, 0] = -1j * MU * kL / mL
    D[:, n - 2, n - 1] = -1.0
    D[:, n - 1, n - 1] = -1j * MU * kR / mR
    b = np.zeros((nE, n), dtype=complex)
    b[:, 0] = -1.0
    b[:, 1] = -1j * MU * kL / mL
    db = None
    if need_d:
        dkL = mL / (2.0 * C * kL)
        dkR = mR / (2.0 * C * kR)
        dD[:, 1, 0] = -1j * MU * dkL / mL
        dD[:, n - 1, n - 1] = -1j * MU * dkR / mR
        db = np.zeros((nE, n), dtype=complex)
        db[:, 1] = -1j * MU * dkL / mL
    return D, b, dD, db


def transmission(model, E, need_d=False, return_r=False):
    """T(E) (and dT/dE) for an array of energies above both lead band edges."""
    E = np.atleast_1d(np.asarray(E, dtype=float))
    D, b, dD, db = assemble(model, E, "trans", need_d)
    x = np.linalg.solve(D, b[:, :, None])[:, :, 0]
    t = x[:, -1]
    mL, VL, mR, VR = model.mL, model.VL, model.mR, model.VR
    kL = np.sqrt(mL * (E - VL) / C)
    kR = np.sqrt(mR * (E - VR) / C)
    pref = (kR / mR) / (kL / mL)
    T = pref * (t.real * t.real + t.imag * t.imag)
    out = [T]
    if need_d:
        rhs = db - np.einsum("eij,ej->ei", dD, x)
        dx = np.linalg.solve(D, rhs[:, :, None])[:, :, 0]
        dtt = dx[:, -1]
        dkL = mL / (2.0 * C * kL)
        dkR = mR / (2.0 * C * kR)
        dT = T * (dkR / kR - dkL / kL) + pref * 2.0 * (t.real * dtt.real + t.imag * dtt.imag)
        out.append(dT)
    if return_r:
        out.append(x[:, 0])
    return tuple(out) if len(out) > 1 else T


def bound_det(model, E):
    """(sign, log|det|) of the bound-state matrix D(E)."""
    D, _, _, _ = assemble(model, np.array([E]), "bound")
    sgn, la = np.linalg.slogdet(D[0])
    return float(sgn), float(la)


# ----------------------------------------------------------------------------------------------
# Independent Sturm count: number of nodes of the solution decaying at -infinity
# ----------------------------------------------------------------------------------------------
def _sgn(v):
    return 1 if v > 0.0 else -1


def _start_sign(u, w):
    return _sgn(u) if u != 0.0 else _sgn(w)


def _zeros_evanescent(u, w, u1, w1):
    """Zeros in (x_s, x_e] of a piece where V >= E (at most one zero)."""
    if u1 == 0.0:
        return 1
    return 1 if _start_sign(u, w) != _sgn(u1) else 0


def _zeros_oscillatory(u, w, u1, w1, xph):
    """Zeros in (x_s, x_e] when the Prufer-type phase advances by pi * xph over the piece.

    The open-interval count is the integer of the parity given by the end signs that is
    nearest to xph (it lies within 1 of xph)."""
    ss = _start_sign(u, w)
    if u1 != 0.0:
        se, endz = _sgn(u1), 0
    else:
        se, endz = -_sgn(w1), 1
    p = 1 if ss != se else 0
    n0 = int(math.floor(xph))
    nopen = n0 if (n0 % 2) == p else n0 + 1
    return nopen + endz


def _airy_theta(z, ai, bi):
    """Continuous Airy phase: Ai = M cos(theta), Bi = M sin(theta), theta(0) = pi/3, for z <= 0."""
    p = math.atan2(bi, ai)
    if z >= -1.0:
        return p
    approx = 0.25 * PI - (2.0 / 3.0) * (-z) ** 1.5
    return p + 2.0 * PI * round((approx - p) / (2.0 * PI))


def _normalise(u, w):
    s = max(abs(u), abs(w))
    return u / s, w / s


def node_count(model, E):
    """Number of eigenvalues below E (< min(V_L, V_R)) = nodes of the left-decaying solution."""
    kap = math.sqrt(model.mL * (model.VL - E) / C)
    u, w = 1.0, kap / model.mL
    nodes = 0
    for L in model.layers:
        m = L.m
        if L.flat:
            q = m * (E - L.vl) / C
            if q > 0.0:
                k = math.sqrt(q)
                th = k * L.d
                c, s = math.cos(th), math.sin(th)
                u1 = u * c + (m * w / k) * s
                w1 = -(k / m) * u * s + w * c
                nodes += _zeros_oscillatory(u, w, u1, w1, th / PI)
            elif q < 0.0:
                kp = math.sqrt(-q)
                x2 = 2.0 * kp * L.d
                ch = 0.5 * (1.0 + math.exp(-x2))
                sh = -0.5 * math.expm1(-x2)
                u1 = u * ch + (m * w / kp) * sh
                w1 = (kp / m) * u * sh + w * ch
                nodes += _zeros_evanescent(u, w, u1, w1)
            else:
                u1 = u + m * w * L.d
                w1 = w
                nodes += _zeros_evanescent(u, w, u1, w1)
            u, w = _normalise(u1, w1)
            continue
        za = L.lam * (L.vl - E)
        zb = L.lam * (L.vr - E)
        pts = [za, zb] if (za >= 0.0) == (zb >= 0.0) or za == 0.0 or zb == 0.0 else [za, 0.0, zb]
        for zs, ze in zip(pts[:-1], pts[1:]):
            if zs == ze:
                continue
            v = m * w / L.beta                     # du/dz
            if zs <= 0.0 and ze <= 0.0:           # oscillatory piece
                ais, aps, bis, bps = (float(t) for t in airy(zs))
                aie, ape, bie, bpe = (float(t) for t in airy(ze))
                a = PI * (u * bps - v * bis)
                b = PI * (v * ais - u * aps)
                u1 = a * aie + b * bie
                v1 = a * ape + b * bpe
                w1 = L.beta * v1 / m
                ph = abs(_airy_theta(ze, aie, bie) - _airy_theta(zs, ais, bis)) / PI
                nodes += _zeros_oscillatory(u, w, u1, w1, ph)
            else:                                  # evanescent piece (z >= 0), scaled
                eas, eaps, ebs, ebps = (float(t) for t in airye(zs))
                eae, eape, ebe, ebpe = (float(t) for t in airye(ze))
                zts = (2.0 / 3.0) * zs * math.sqrt(zs)
                zte = (2.0 / 3.0) * ze * math.sqrt(ze)
                p = u * ebps - v * ebs             # Ai coefficient / (pi e^{zeta_s})
                qq = v * eas - u * eaps            # Bi coefficient / (pi e^{-zeta_s})
                dz = zte - zts
                if dz >= 0.0:
                    g1, g2 = math.exp(-2.0 * dz), 1.0
                else:
                    g1, g2 = 1.0, math.exp(2.0 * dz)
                u1 = p * g1 * eae + qq * g2 * ebe
                v1 = p * g1 * eape + qq * g2 * ebpe
                w1 = L.beta * v1 / m
                nodes += _zeros_evanescent(u, w, u1, w1)
            u, w = _normalise(u1, w1)
    kR = math.sqrt(model.mR * (model.VR - E) / C)
    A = u + model.mR * w / kR                      # 2 x coefficient of exp(+kR (x - X))
    if A != 0.0 and _sgn(A) != _start_sign(u, w):
        nodes += 1
    return nodes


# ----------------------------------------------------------------------------------------------
# Bound states
# ----------------------------------------------------------------------------------------------
def bound_states(model):
    Eth = min(model.VL, model.VR)
    Etop = Eth - 2.0e-5                    # guarantee 1: highest state >= 1e-4 below E_th
    Ebot = model.Vmin - 1.0e-3             # no state below min V
    if Etop <= Ebot:
        return []
    ntot = node_count(model, Etop)
    if ntot == 0:
        return []
    nbot = node_count(model, Ebot)
    brackets = {}
    stack = [(Ebot, nbot, Etop, ntot)]
    while stack:
        a, na, b, nb = stack.pop()
        if nb <= na:
            continue
        if nb - na == 1 or b - a < 1e-13:
            for i in range(na, nb):
                brackets[i] = (a, b)
            continue
        mid = 0.5 * (a + b)
        nm = min(max(node_count(model, mid), na), nb)
        stack.append((a, na, mid, nm))
        stack.append((mid, nm, b, nb))
    out = []
    for i in sorted(brackets):
        a, b = brackets[i]
        out.append(_refine_bound(model, a, b))
    return out


def _refine_bound(model, a, b):
    sa, la = bound_det(model, a)
    sb, lb = bound_det(model, b)
    ref = 0.5 * (la + lb)

    def f(E):
        s, l = bound_det(model, E)
        if s == 0.0:
            return 0.0
        return s * math.exp(min(max(l - ref, -700.0), 700.0))

    if sa * sb < 0.0:
        return brentq(f, a, b, xtol=1e-15, rtol=8.9e-16, maxiter=300)
    # fallback (should not happen): bisection on the Sturm count
    na = node_count(model, a)
    for _ in range(200):
        mid = 0.5 * (a + b)
        if mid <= a or mid >= b:
            break
        if node_count(model, mid) > na:
            b = mid
        else:
            a = mid
    return 0.5 * (a + b)


# ----------------------------------------------------------------------------------------------
# Transmission maxima in the window
# ----------------------------------------------------------------------------------------------
def _dT(model, E):
    _, d = transmission(model, np.array([E]), need_d=True)
    return float(d[0])


def maxima(model, step=SCAN_STEP, chunk=1024, stats=None):
    lo, hi = model.win
    nint = max(int(math.ceil((hi - lo) / step)), 2)
    grid = np.linspace(lo, hi, nint + 1)
    T = np.empty_like(grid)
    dT = np.empty_like(grid)
    for i0 in range(0, grid.size, chunk):
        Tc, dTc = transmission(model, grid[i0:i0 + chunk], need_d=True)
        T[i0:i0 + chunk] = Tc
        dT[i0:i0 + chunk] = dTc
    # extrema: sign changes of the analytic derivative between grid points
    ext = []                                   # (kind, E, T); kind +1 max, -1 min
    for i in range(grid.size - 1):
        s0, s1 = dT[i], dT[i + 1]
        if s0 > 0.0 and s1 <= 0.0:
            kind = 1
        elif s0 < 0.0 and s1 >= 0.0:
            kind = -1
        else:
            continue
        a, b = float(grid[i]), float(grid[i + 1])
        if s1 == 0.0:
            Ex = b
        else:
            Ex = brentq(lambda e: _dT(model, e), a, b, xtol=1e-15, rtol=8.9e-16, maxiter=300)
        Tx = float(transmission(model, np.array([Ex]))[0])
        ext.append([kind, Ex, Tx])
    # remove numerical-noise pairs (genuine maxima exceed adjacent minima by >= 1e-3 relative)
    changed = True
    while changed:
        changed = False
        for i in range(len(ext) - 1):
            t1, t2 = ext[i][2], ext[i + 1][2]
            if abs(t1 - t2) <= 1e-7 * max(t1, t2):
                del ext[i:i + 2]
                changed = True
                if stats is not None:
                    stats["noise_pairs"] = stats.get("noise_pairs", 0) + 1
                break
    return [(e[1], e[2]) for e in ext if e[0] == 1]


# ----------------------------------------------------------------------------------------------
def compute_report(struct):
    model = Model(struct)
    bs = bound_states(model)
    Tq = transmission(model, np.array(model.Eq))
    mx = maxima(model)
    rep = {
        "structure_id": model.sid,
        "bound_states": [{"E_eV": float(e)} for e in bs],
        "transmission": [{"E_eV": e_raw, "T": float(t)} for e_raw, t in zip(model.Eq_raw, Tq)],
        "maxima": [{"E_eV": float(e), "T": float(t)} for e, t in mx],
    }
    return rep


def _check_finite(rep):
    for key in ("bound_states", "transmission", "maxima"):
        for item in rep[key]:
            for v in item.values():
                if not math.isfinite(float(v)):
                    raise ValueError("non-finite value in report")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--structure", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    with open(args.structure, "r", encoding="utf-8") as fh:
        struct = json.load(fh)
    rep = compute_report(struct)
    _check_finite(rep)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1, allow_nan=False)
        fh.write("\n")


if __name__ == "__main__":
    main()
