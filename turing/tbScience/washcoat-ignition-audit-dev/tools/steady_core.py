"""Exact steady-state core for the washcoat layer (prototype; becomes part of the oracle).

theta + beta c = A across the layer (zero flux at the wall), with A fixed by the surface
concentration cs: A = beta (Bi_m/Bi_h)(1 - cs) + beta cs. Then c'' = phi^2 f(c),
f(c) = c R(A - beta c), with first integral c'^2 = 2 phi^2 D(c), D(c) = int_{c0}^{c} f.
The layer thickness gives phi = I(c0, cs) = int_{c0}^{cs} dc / sqrt(2 D(c)), and the film
condition gives phi = Bi_m (1 - cs) / sqrt(2 D(cs)). A steady state is a root c0 of
    H(c0; cs) = I(c0, cs) - Bi_m (1 - cs) / sqrt(2 D(cs)).
H -> +inf as c0 -> 0 (log divergence of I) and -> -inf as c0 -> cs, so every cs has at least
one root. Quadrature: [c0, c_sp] with c = c0 cosh t (smooth integrand), c_sp = max(C1, 3 c0);
below C1 = 1e-14 the kinetics are frozen at R(A) (relative error < 1e-12) and that piece is
closed form; [c_sp, cs] in s = ln(c / c_sp). Roots below C_FLOOR = 1e-300 are the dead-core
limit: phi = Bi_m (1 - cs)/sqrt(2 G(cs)), theta_c = A (exact in double precision).
"""
import math

import numpy as np
from scipy.optimize import brentq

C1, C_FLOOR = 1e-14, 1e-300
X32, W32 = np.polynomial.legendre.leggauss(32)
X64, W64 = np.polynomial.legendre.leggauss(64)


def gl(a, b, n=64):
    x, w = (X64, W64) if n == 64 else (X32, W32)
    return 0.5 * (b - a) * x + 0.5 * (b + a), 0.5 * (b - a) * w


class Steady:
    def __init__(self, beta, gamma, Bim, Bih):
        self.beta, self.gamma, self.Bim, self.Bih = beta, gamma, Bim, Bih

    def R(self, th):
        return np.exp(self.gamma * th / (1.0 + th))

    def A(self, cs):
        return self.beta * (self.Bim / self.Bih) * (1.0 - cs) + self.beta * cs

    def f(self, c, A):
        return c * self.R(A - self.beta * c)

    def DI(self, c0, cs, A):
        """(D(cs), I) for centre value c0 < cs."""
        RA = float(self.R(A))
        if c0 < C1 / 3.0:                                   # frozen kinetics up to C1
            csp = min(C1, cs)
            z = csp / c0
            I = (math.log(2.0 * z) if z > 1e8 else math.acosh(z)) / math.sqrt(RA)
            Dsp = 0.5 * RA * (csp * csp - c0 * c0)
        else:
            csp = min(3.0 * c0, cs)
            T = math.acosh(csp / c0)
            t, wt = gl(0.0, T, 32)
            # D at each outer node by inner GL on [0, t_i]
            u, wu = X32, W32
            tau = 0.5 * t[:, None] * (u + 1.0)               # (32, 32)
            integ = self.f(c0 * np.cosh(tau), A) * c0 * np.sinh(tau)
            Dt = 0.5 * t * np.sum(wu * integ, axis=1)
            I = float(np.sum(wt * c0 * np.sinh(t) / np.sqrt(2.0 * Dt)))
            tau = 0.5 * T * (u + 1.0)
            Dsp = 0.5 * T * float(np.sum(wu * self.f(c0 * np.cosh(tau), A) * c0 * np.sinh(tau)))
        if cs <= csp:
            return Dsp, I
        S = math.log(cs / csp)
        s, ws = gl(0.0, S, 64)
        v = 0.5 * s[:, None] * (X64 + 1.0)
        cv = csp * np.exp(v)
        Ds = Dsp + 0.5 * s * np.sum(W64 * self.f(cv, A) * cv, axis=1)
        c = csp * np.exp(s)
        I += float(np.sum(ws * c / np.sqrt(2.0 * Ds)))
        v = 0.5 * S * (X64 + 1.0)
        cv = csp * np.exp(v)
        Dcs = Dsp + 0.5 * S * float(np.sum(W64 * self.f(cv, A) * cv))
        return Dcs, I

    def H(self, c0, cs):
        A = float(self.A(cs))
        D, I = self.DI(c0, cs, A)
        return I - self.Bim * (1.0 - cs) / math.sqrt(2.0 * D)

    def G0(self, cs, A):
        """int_0^cs f, the dead-core limit of D(cs)."""
        D, _ = self.DI(C_FLOOR, cs, A)
        return D

    def c0_grid(self, cs, n=90):
        lo = np.logspace(math.log10(C_FLOOR), math.log10(0.5), n) * cs
        hi = cs * (1.0 - np.logspace(math.log10(0.5), -12, n // 2))
        return np.unique(np.concatenate([lo, hi]))

    def roots(self, cs):
        """All roots c0 of H(.; cs); 0.0 stands for the dead-core limit (root below C_FLOOR)."""
        g = self.c0_grid(cs)
        h = np.array([self.H(c, cs) for c in g])
        out = []
        if h[0] < 0.0:
            out.append(0.0)
        for i in range(len(g) - 1):
            if h[i] * h[i + 1] < 0.0:
                out.append(brentq(self.H, g[i], g[i + 1], args=(cs,), xtol=1e-300, rtol=1e-15, maxiter=300))
        return out

    def state(self, cs, c0):
        """(phi, theta_c, eta) of the steady state (cs, c0)."""
        A = float(self.A(cs))
        if c0 == 0.0:
            D = self.G0(cs, A)
        else:
            D, _ = self.DI(c0, cs, A)
        phi = self.Bim * (1.0 - cs) / math.sqrt(2.0 * D)
        return phi, A - self.beta * c0, self.Bim * (1.0 - cs) / phi ** 2
