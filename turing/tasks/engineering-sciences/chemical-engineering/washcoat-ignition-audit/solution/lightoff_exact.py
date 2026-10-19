"""Steady states, folds, Hopf points and stability of a catalytic washcoat layer
(WASHCOAT_SPEC.md).

Steady states. Adding beta times the reactant equation to the energy equation gives
(theta + beta c)'' = 0, so theta + beta c = A across the layer (zero flux at the wall), and the
two film conditions fix A = beta (Bi_m/Bi_h)(1 - c_s) + beta c_s from the surface concentration
c_s. The reactant equation c'' = phi^2 f(c), f(c) = c R(A - beta c), has the first integral
c'^2 = 2 phi^2 D(c), D(c) = int_{c0}^{c} f, c0 the wall concentration. The layer thickness and
the film condition give two expressions for phi,
    phi = I(c0, c_s) = int_{c0}^{c_s} dc / sqrt(2 D(c)),    phi = Bi_m (1 - c_s) / sqrt(2 D(c_s)),
so a steady state is a root c0 of H(c0; c_s) = I - Bi_m (1 - c_s)/sqrt(2 D(c_s)) for a given
c_s. H -> +inf as c0 -> 0 and -inf as c0 -> c_s; the root is located by a scan and Brent's
method. The steady-state set is the curve c_s -> (phi, theta_c, eta) for 0 < c_s < 1; folds are
the zeros of d phi / d c_s along it, and every steady state at a given phi is a crossing of that
curve. Quadrature is Gauss-Legendre: c = c0 cosh t on [c0, max(C1, 3 c0)] (smooth integrand),
log(c) above; below C1 = 1e-14 the kinetics are frozen at R(A) (relative error below 1e-12) and
that piece is closed form; wall values below 1e-300 are the dead-core limit (exact in double).

Stability. The linearised two-field problem with Le is discretised by Chebyshev collocation
(the steady profile is polished by collocation Newton from the first-integral profile) and the
rightmost eigenvalues of the generalised eigenproblem are computed at increasing resolution
until they agree. Hopf points are zeros, along the curve, of the real part of the rightmost
complex pair, refined by Brent's method in c_s.
"""
import argparse
import json
import math

import numpy as np
from scipy.linalg import eig
from scipy.optimize import brentq

C1, C_FLOOR = 1e-14, 1e-300
X32, W32 = np.polynomial.legendre.leggauss(32)
X64, W64 = np.polynomial.legendre.leggauss(64)
N_LEVELS = (48, 72, 108, 162)            # collocation resolutions tried for the spectrum
EIG_TOL = 1e-7                           # agreement required between two resolutions
OMEGA_MIN = 1e-3                         # a crossing with |Im| below this is a real-pair merger, not a Hopf point


# ------------------------------------------------------------------ steady states
class Layer:
    def __init__(self, r):
        self.beta, self.gamma = float(r["beta"]), float(r["gamma"])
        self.Bim, self.Bih, self.Le = float(r["Bi_m"]), float(r["Bi_h"]), float(r["Le"])

    def R(self, th):
        return np.exp(self.gamma * th / (1.0 + th))

    def dR(self, th):
        return self.R(th) * self.gamma / (1.0 + th) ** 2

    def A(self, cs):
        return self.beta * (self.Bim / self.Bih) * (1.0 - cs) + self.beta * cs

    def f(self, c, A):
        return c * self.R(A - self.beta * c)

    def DI(self, c0, cs, A):
        """(D(cs), I(c0, cs)) for a wall value c0 < cs (c0 = 0: the dead-core limit)."""
        RA = float(self.R(A))
        if c0 < C1 / 3.0:
            csp = min(C1, cs)
            if c0 <= 0.0:
                I, Dsp = math.inf, 0.5 * RA * csp * csp
            else:
                z = csp / c0
                I = (math.log(2.0 * z) if z > 1e8 else math.acosh(z)) / math.sqrt(RA)
                Dsp = 0.5 * RA * (csp * csp - c0 * c0)
        else:
            csp = min(3.0 * c0, cs)
            T = math.acosh(csp / c0)
            t, wt = 0.5 * T * (X32 + 1.0), 0.5 * T * W32
            tau = 0.5 * t[:, None] * (X32 + 1.0)
            Dt = 0.5 * t * np.sum(W32 * self.f(c0 * np.cosh(tau), A) * c0 * np.sinh(tau), axis=1)
            I = float(np.sum(wt * c0 * np.sinh(t) / np.sqrt(2.0 * Dt)))
            tau = 0.5 * T * (X32 + 1.0)
            Dsp = 0.5 * T * float(np.sum(W32 * self.f(c0 * np.cosh(tau), A) * c0 * np.sinh(tau)))
        if cs <= csp:
            return Dsp, I
        S = math.log(cs / csp)
        s, ws = 0.5 * S * (X64 + 1.0), 0.5 * S * W64
        cv = csp * np.exp(0.5 * s[:, None] * (X64 + 1.0))
        Ds = Dsp + 0.5 * s * np.sum(W64 * self.f(cv, A) * cv, axis=1)
        I += float(np.sum(ws * csp * np.exp(s) / np.sqrt(2.0 * Ds)))
        cv = csp * np.exp(0.5 * S * (X64 + 1.0))
        Dcs = Dsp + 0.5 * S * float(np.sum(W64 * self.f(cv, A) * cv))
        return Dcs, I

    def H(self, c0, cs):
        A = float(self.A(cs))
        D, I = self.DI(c0, cs, A)
        return I - self.Bim * (1.0 - cs) / math.sqrt(2.0 * D)

    def wall_value(self, cs, hint=None):
        """The wall concentration c0 of the steady state with surface value cs (0.0: dead core).
        H(c0; cs) has exactly one sign change in c0 (positive below the root, negative above), so
        any bracket with that sign pattern holds the root; a hint from a neighbouring point on the
        curve gives one after a few evaluations, otherwise the full range is scanned."""
        top = cs * (1.0 - 1e-13)
        if hint is not None and hint > C_FLOOR and hint < top:
            for k in (0.05, 0.5, 3.0, 20.0):
                a, b = max(hint * math.exp(-k), C_FLOOR), min(hint * math.exp(k), top)
                if self.H(a, cs) > 0.0 and self.H(b, cs) < 0.0:
                    return brentq(self.H, a, b, args=(cs,), xtol=1e-300, rtol=1e-15, maxiter=300)
        lo = np.logspace(math.log10(C_FLOOR), math.log10(0.5), 70) * cs
        hi = cs * (1.0 - np.logspace(math.log10(0.5), -13, 40))
        g = np.unique(np.concatenate([lo, hi]))
        h0 = self.H(g[0], cs)
        if h0 < 0.0:
            return 0.0
        prev_c, prev_h = g[0], h0
        for c in g[1:]:
            h = self.H(c, cs)
            if prev_h * h < 0.0:
                return brentq(self.H, prev_c, c, args=(cs,), xtol=1e-300, rtol=1e-15, maxiter=300)
            prev_c, prev_h = c, h
        raise RuntimeError(f"no wall value for c_s = {cs!r}")

    def state(self, cs, hint=None):
        """(phi, theta_c, eta, c0) of the steady state with surface concentration cs."""
        c0 = self.wall_value(cs, hint)
        A = float(self.A(cs))
        D, _ = self.DI(c0, cs, A) if c0 > 0.0 else self.DI(0.0, cs, A)
        phi = self.Bim * (1.0 - cs) / math.sqrt(2.0 * D)
        return phi, A - self.beta * c0, self.Bim * (1.0 - cs) / phi ** 2, c0


def cs_of(z):
    return 1.0 / (1.0 + math.exp(-z))         # the curve is parametrised by z = logit(c_s)


# ------------------------------------------------------------------ spectrum
_CHEB = {}


def cheb(n):
    if n not in _CHEB:
        x = np.cos(np.pi * np.arange(n + 1) / n)
        c = np.r_[2.0, np.ones(n - 1), 2.0] * (-1.0) ** np.arange(n + 1)
        X = np.tile(x, (n + 1, 1)).T
        D = np.outer(c, 1.0 / c) / (X - X.T + np.eye(n + 1))
        D -= np.diag(D.sum(axis=1))
        x01 = 0.5 * (1.0 - x)                    # x = (1 - xi)/2: node 0 is the surface x = 1
        D1 = -2.0 * D
        _CHEB[n] = (x01, D1, D1 @ D1, int(np.argmin(x01)), int(np.argmax(x01)))
    return _CHEB[n]


def profile(L, cs, c0, phi, n):
    """Steady c at the collocation nodes: first-integral profile polished by Newton."""
    x01, D1, D2, iw, isf = cheb(n)
    A = float(L.A(cs))
    if c0 > 0.0:
        if c0 >= C1:
            cg = c0 + (cs - c0) * np.linspace(0.0, 1.0, 120)[1:] ** 2
        else:
            cg = c0 * (cs / c0) ** np.linspace(0.0, 1.0, 120)[1:]
        xg = np.array([L.DI(c0, float(v), A)[1] for v in cg]) / phi
        c = np.interp(x01, np.r_[0.0, xg / xg[-1]], np.r_[c0, cg])
    else:
        c = cs * np.exp(-phi * math.sqrt(float(L.R(A))) * (1.0 - x01))
    phi2, dA = phi * phi, L.beta * (1.0 - L.Bim / L.Bih)
    for _ in range(100):
        Ac = float(L.A(c[isf]))
        th = Ac - L.beta * c
        Rv, dRv = L.R(th), L.dR(th)
        res = D2 @ c - phi2 * c * Rv
        J = D2 - phi2 * np.diag(Rv - L.beta * c * dRv)
        J[:, isf] -= phi2 * c * dRv * dA
        res[iw], J[iw] = (D1 @ c)[iw], D1[iw]
        res[isf] = (D1 @ c)[isf] - L.Bim * (1.0 - c[isf])
        J[isf] = D1[isf]
        J[isf, isf] += L.Bim
        dc = np.linalg.solve(J, -res)
        c = c + dc
        if np.max(np.abs(dc)) < 1e-14 * max(1.0, np.max(np.abs(c))):
            break
    return c


def spectrum_n(L, cs, c0, phi, n):
    x01, D1, D2, iw, isf = cheb(n)
    c = profile(L, cs, c0, phi, n)
    th = float(L.A(c[isf])) - L.beta * c
    Rv, dRv = L.R(th), L.dR(th)
    phi2, m = phi * phi, n + 1
    K, M = np.zeros((2 * m, 2 * m)), np.zeros((2 * m, 2 * m))
    K[:m, :m] = D2 + L.beta * phi2 * np.diag(c * dRv)
    K[:m, m:] = L.beta * phi2 * np.diag(Rv)
    M[:m, :m] = L.Le * np.eye(m)
    K[m:, :m] = -phi2 * np.diag(c * dRv)
    K[m:, m:] = D2 - phi2 * np.diag(Rv)
    M[m:, m:] = np.eye(m)
    for blk, Bi in ((0, L.Bih), (m, L.Bim)):
        for row, extra in ((iw, 0.0), (isf, Bi)):
            K[blk + row, :] = 0.0
            K[blk + row, blk:blk + m] = D1[row]
            K[blk + row, blk + row] += extra
            M[blk + row, :] = 0.0
    w = eig(K, M, right=False)
    w = w[np.isfinite(w) & (np.abs(w) < 1e8)]
    return w[np.argsort(-w.real)][:6]


def spectrum(L, cs, c0, phi):
    """Rightmost eigenvalues, converged between two consecutive resolutions."""
    prev = None
    for n in N_LEVELS:
        w = spectrum_n(L, cs, c0, phi, n)
        if prev is not None and abs(w[0] - prev[0]) <= EIG_TOL * max(1.0, abs(w[0])):
            return w
        prev = w
    return w


def complex_lead(w):
    """(real part, |imag|) of the rightmost complex-conjugate pair, or (-inf, 0)."""
    cpx = [v for v in w if abs(v.imag) > 1e-8 * max(1.0, abs(v.real))]
    return (cpx[0].real, abs(cpx[0].imag)) if cpx else (-math.inf, 0.0)


def classify(w):
    lead = w[0]
    if lead.real < 0.0:
        return "stable"
    return "unstable_complex" if abs(lead.imag) > 1e-8 * max(1.0, abs(lead.real)) else "unstable_real"


# ------------------------------------------------------------------ the curve
def solve(r):
    L = Layer(r)
    phi_min, phi_max = float(r["phi_min"]), float(r["phi_max"])
    # sample the curve in z = logit(c_s) from the large-phi end (c_s -> 0) to the small-phi end
    zs = np.linspace(-30.0, 23.0, 400)
    S, hint = [], None
    for z in zs:
        S.append(L.state(cs_of(z), hint))
        hint = S[-1][3]
    ph = np.array([s[0] for s in S])
    # the window is crossed once at each end (spec guarantee); keep the part of the curve between
    # the last crossing of phi_max and the first crossing of phi_min (in increasing z)
    phi_z = lambda z: L.state(cs_of(z))[0]

    def dphi(z, h=1e-6):
        return (phi_z(z + h) - phi_z(z - h)) / (2.0 * h)

    folds = []
    for i in range(1, len(zs) - 1):
        if (ph[i] - ph[i - 1]) * (ph[i + 1] - ph[i]) < 0.0:
            a, b = zs[i - 1], zs[i + 1]
            za = brentq(dphi, a, b, xtol=1e-13, rtol=1e-15, maxiter=200) if dphi(a) * dphi(b) < 0.0 else zs[i]
            phi, thc, eta, c0 = L.state(cs_of(za))
            # a local maximum of phi along the curve is an ignition point (spec section 1)
            kind = "ignition" if ph[i] > ph[i - 1] else "extinction"
            folds.append(dict(phi=phi, theta_c=thc, eta=eta, kind=kind, z=za))
    folds = [f for f in folds if phi_min < f["phi"] < phi_max]
    folds.sort(key=lambda f: f["phi"])

    # Hopf points: sign changes of the rightmost complex pair's real part along the curve
    # Hopf points: scan the rightmost complex pair's real part at the coarsest resolution, then
    # refine every sign change with the converged spectrum and keep it only if the root is a true
    # crossing (an eigenvalue with real part ~0 and imaginary part bounded away from 0), not the
    # point where a complex pair merges into two real eigenvalues.
    def hopf_fn(z, conv=True):
        cs = cs_of(z)
        phi, thc, eta, c0 = SC[z] if z in SC else L.state(cs)
        w = spectrum(L, cs, c0, phi) if conv else spectrum_n(L, cs, c0, phi, N_LEVELS[0])
        return complex_lead(w)[0]
    SC = {z: s for z, s in zip(zs, S)}
    inside = [i for i in range(len(zs)) if phi_min <= ph[i] <= phi_max]
    hopf = []
    if inside:
        idx = list(range(max(min(inside) - 1, 0), min(max(inside) + 2, len(zs))))
        vals = {i: hopf_fn(zs[i], conv=False) for i in idx}
        for i, j in zip(idx[:-1], idx[1:]):
            a, b = vals[i], vals[j]
            if not (math.isfinite(a) and math.isfinite(b) and a * b < 0.0):
                continue
            fa, fb = hopf_fn(zs[i]), hopf_fn(zs[j])
            if not (math.isfinite(fa) and math.isfinite(fb) and fa * fb < 0.0):
                continue
            zh = brentq(hopf_fn, zs[i], zs[j], xtol=1e-13, rtol=1e-15, maxiter=200)
            cs = cs_of(zh)
            phi, thc, eta, c0 = L.state(cs)
            w = spectrum(L, cs, c0, phi)
            re, om = complex_lead(w)
            if om > OMEGA_MIN and abs(re) < 1e-6 * max(1.0, om) and phi_min < phi < phi_max:
                hopf.append(dict(phi=phi, theta_c=thc, eta=eta, omega=om))
    hopf.sort(key=lambda h: h["phi"])

    states = []
    for q in r["phi_query"]:
        q = float(q)
        br = []
        for i in range(len(zs) - 1):
            if (ph[i] - q) * (ph[i + 1] - q) < 0.0:
                zq = brentq(lambda z: phi_z(z) - q, zs[i], zs[i + 1], xtol=1e-14, rtol=1e-15, maxiter=200)
                cs = cs_of(zq)
                phi, thc, eta, c0 = L.state(cs)
                br.append(dict(theta_c=thc, eta=eta, stability=classify(spectrum(L, cs, c0, phi))))
        br.sort(key=lambda b: b["theta_c"])
        states.append(dict(phi=q, branches=br))
    return dict(recipe_id=r["recipe_id"],
                folds=[{k: f[k] for k in ("phi", "theta_c", "eta", "kind")} for f in folds],
                hopf_points=hopf, states=states)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    with open(a.recipe, encoding="utf-8") as fh:
        r = json.load(fh)
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump(solve(r), fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
