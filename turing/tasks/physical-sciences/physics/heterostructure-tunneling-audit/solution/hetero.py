#!/usr/bin/env python
"""Bound states and transmission of a layered semiconductor heterostructure (HETERO_SPEC.md).

Every region is solved exactly: trigonometric or hyperbolic functions in flat layers and leads,
Airy functions in sloped layers. The state (psi, psi'/m), which is continuous at every interface
(BenDaniel-Duke), is carried through the layers with exponentially scaled layer transfer
matrices: hyperbolic functions are written with decaying exponentials and Airy functions of
positive argument through their scaled forms, the large exponent being kept apart as a log
scale, so that barriers of any opacity neither overflow nor lose the dominant solution.

Bound states: the number of bound states below E equals the number of nodes of the solution that
decays at -infinity (oscillation theorem). Nodes are counted exactly: inside a layer by sampling
psi more finely than the shortest possible node spacing pi / k_max (Sturm comparison), in the
right lead from the decomposition into growing and decaying exponentials. Bisection on the node
count isolates every bound state; each is then the unique root, in its isolating interval, of
the mismatch between the propagated direction of (psi, psi'/m) and the decaying right-lead
solution. Transmission: the outgoing right-lead wave is carried leftwards (the stable direction
for the physical solution) and decomposed into incident and reflected waves in the left lead.
Maxima: T is scanned on a 1e-5 eV grid (guarantee 3 spaces the extrema 2e-4 eV apart) and each
discrete maximum is refined as the root of a fourth-order central difference of T.

usage: hetero.py --structure <structure.json> --output <report.json>
"""
import argparse
import json
import math

import numpy as np
from scipy.optimize import brentq
from scipy.special import airy, airye

C = 0.0380998212            # hbar^2 / (2 m0) in eV nm^2
SCAN_STEP = 1e-5            # eV


def airy_scaled(z):
    """Ai, Ai', Bi, Bi' with the exponential factors removed for z > 0, and the exponent zeta:
    true Ai = A e^{-zeta}, Ai' = Ap e^{-zeta}, Bi = B e^{zeta}, Bi' = Bp e^{zeta} (zeta = 0 for z <= 0)."""
    z = np.asarray(z, dtype=float)
    pos = z > 0
    ai, aip, bi, bip = airy(np.where(pos, 0.0, z))
    zp = np.where(pos, z, 1.0)
    eai, eaip, ebi, ebip = airye(zp)
    zeta = np.where(pos, (2.0 / 3.0) * zp * np.sqrt(zp), 0.0)
    return (np.where(pos, eai, ai), np.where(pos, eaip, aip), np.where(pos, ebi, bi),
            np.where(pos, ebip, bip), zeta)


class Layer:
    def __init__(self, d):
        self.d = float(d["thickness_nm"])
        self.m = float(d["mass"])
        self.vl = float(d["vl_eV"])
        self.vr = float(d["vr_eV"])
        self.F = 0.0 if self.vl == self.vr else (self.vr - self.vl) / self.d

    def matrix(self, E, t):
        """Scaled transfer matrix from the layer's left edge to depth t:
        true M = e^L [[m11, m12], [m21, m22]] acting on (psi, psi'/m). det M = 1."""
        E = np.asarray(E, dtype=float)
        t = np.asarray(t, dtype=float)
        m = self.m
        if self.F == 0.0:
            q = m * (self.vl - E) / C
            q, t = np.broadcast_arrays(q, t)
            pos = q > 0
            kap = np.sqrt(np.where(pos, q, 0.0))
            k = np.sqrt(np.where(pos, 0.0, -q))
            x = kap * t
            em1 = -np.expm1(-2.0 * x)                     # 1 - e^{-2x}
            c_e = 1.0 - 0.5 * em1                         # (1 + e^{-2x}) / 2
            s_e = np.where(kap > 0, em1 / (2.0 * np.where(kap > 0, kap, 1.0)), t)
            qs_e = 0.5 * kap * em1
            kt = k * t
            c_o = np.cos(kt)
            s_o = np.where(k > 0, np.sin(kt) / np.where(k > 0, k, 1.0), t)
            qs_o = -k * np.sin(kt)
            c = np.where(pos, c_e, c_o)
            s = np.where(pos, s_e, s_o)
            qs = np.where(pos, qs_e, qs_o)
            L = np.where(pos, x, 0.0)
            return c, m * s, qs / m, c, L
        alpha = float(np.cbrt(m * self.F / C))
        tt = (E - self.vl) / self.F
        A0, A0p, B0, B0p, Z0 = airy_scaled(alpha * (0.0 - tt))
        A, Ap, B, Bp, Z = airy_scaled(alpha * (t - tt))
        dz = Z - Z0
        L = np.abs(dz)
        f1 = np.exp(-dz - L)          # products Ai-type(z) x Bi-type(z0)
        f2 = np.exp(dz - L)           # products Bi-type(z) x Ai-type(z0)
        pi = math.pi
        m11 = pi * (A * B0p * f1 - B * A0p * f2)
        m12 = (pi * m / alpha) * (B * A0 * f2 - A * B0 * f1)
        m21 = (pi * alpha / m) * (Ap * B0p * f1 - Bp * A0p * f2)
        m22 = pi * (Bp * A0 * f2 - Ap * B0 * f1)
        return m11, m12, m21, m22, L

    def vmin(self):
        return min(self.vl, self.vr)


class Structure:
    def __init__(self, d):
        self.id = d["structure_id"]
        self.mL, self.VL = float(d["left_lead"]["mass"]), float(d["left_lead"]["v_eV"])
        self.mR, self.VR = float(d["right_lead"]["mass"]), float(d["right_lead"]["v_eV"])
        self.layers = [Layer(x) for x in d["layers"]]
        self.d = d

    # ------------------------------------------------------------ bound states
    def nodes_and_mismatch(self, E):
        """(number of nodes of the solution decaying at -infinity, direction mismatch with the
        decaying right-lead solution at x = X)."""
        kapL = math.sqrt(self.mL * (self.VL - E) / C)
        kapR = math.sqrt(self.mR * (self.VR - E) / C)
        psi, p = 1.0, kapL / self.mL
        nrm = math.hypot(psi, p)
        psi, p = psi / nrm, p / nrm
        nodes = 0
        for ly in self.layers:
            kmax = math.sqrt(max(0.0, ly.m * (E - ly.vmin()) / C))
            n = 2 if kmax == 0.0 else max(2, int(math.ceil(ly.d * kmax * 4.0 / math.pi)))
            ts = np.linspace(0.0, ly.d, n + 1)[1:]
            m11, m12, m21, m22, _ = ly.matrix(E, ts)
            vals = m11 * psi + m12 * p
            s_prev = np.sign(psi)
            for v in np.sign(vals):
                if v != 0:
                    if s_prev != 0 and v != s_prev:
                        nodes += 1
                    s_prev = v
            psi_e = float(m11[-1] * psi + m12[-1] * p)
            p_e = float(m21[-1] * psi + m22[-1] * p)
            nrm = math.hypot(psi_e, p_e)
            psi, p = psi_e / nrm, p_e / nrm
        # right lead: psi = A e^{-kap s} + B e^{kap s}
        A = 0.5 * (psi - self.mR * p / kapR)
        B = 0.5 * (psi + self.mR * p / kapR)
        if A * B < 0 and abs(A) > abs(B):
            nodes += 1
        g = -(p + kapR / self.mR * psi) / math.sqrt(1.0 + (kapR / self.mR) ** 2)
        return nodes, g

    def bound_states(self):
        E_th = min(self.VL, self.VR)
        vmin = min([self.VL, self.VR] + [v for ly in self.layers for v in (ly.vl, ly.vr)])
        if vmin >= E_th:
            return []
        lo = vmin - 1e-9 * max(1.0, abs(vmin))
        hi = E_th - 1e-6
        if hi <= lo:
            return []
        n_lo = self.nodes_and_mismatch(lo)[0]
        n_hi = self.nodes_and_mismatch(hi)[0]
        if n_lo != 0:
            raise RuntimeError("nodes below the potential minimum")
        roots = []
        g = lambda E: self.nodes_and_mismatch(E)[1]

        def isolate(a, b, na, nb):
            if nb == na:
                return
            if nb - na == 1:
                roots.append(brentq(g, a, b, xtol=1e-15, rtol=1e-15, maxiter=400))
                return
            if b - a < 1e-11:
                raise RuntimeError(f"bound states closer than {b - a} eV near {a}")
            mid = 0.5 * (a + b)
            nm = self.nodes_and_mismatch(mid)[0]
            isolate(a, mid, na, nm)
            isolate(mid, b, nm, nb)
        isolate(lo, hi, n_lo, n_hi)
        return sorted(roots)

    # ------------------------------------------------------------ transmission
    def log_transmission(self, E):
        """ln T for an array of energies above both lead edges."""
        E = np.atleast_1d(np.asarray(E, dtype=float))
        kL = np.sqrt(self.mL * (E - self.VL) / C)
        kR = np.sqrt(self.mR * (E - self.VR) / C)
        psi = np.ones_like(E, dtype=complex)
        p = 1j * kR / self.mR
        S = np.zeros_like(E)
        for ly in reversed(self.layers):
            m11, m12, m21, m22, L = ly.matrix(E, ly.d)
            psi_n = m22 * psi - m12 * p                   # inverse of a unit-determinant matrix
            p_n = -m21 * psi + m11 * p
            nrm = np.sqrt(np.abs(psi_n) ** 2 + np.abs(p_n) ** 2)
            S = S + L + np.log(nrm)
            psi, p = psi_n / nrm, p_n / nrm
        a = 0.5 * (psi - 1j * self.mL * p / kL)
        return np.log(kR * self.mL / (kL * self.mR)) - 2.0 * S - 2.0 * np.log(np.abs(a))

    def T(self, E):
        return np.exp(self.log_transmission(E))

    def maxima(self, E_lo, E_hi):
        n = int(math.ceil((E_hi - E_lo) / SCAN_STEP)) + 1
        grid = np.linspace(E_lo, E_hi, n)
        Tg = self.T(grid)
        out = []
        for k in range(1, n - 1):
            if Tg[k] > Tg[k - 1] and Tg[k] >= Tg[k + 1]:
                h = grid[1] - grid[0]
                curv = abs(Tg[k + 1] - 2 * Tg[k] + Tg[k - 1]) / (h * h)
                w = math.sqrt(Tg[k] / curv) if curv > 0 else 1e-2
                delta = min(1e-4, max(1e-9, 3e-3 * w))

                def D(E, delta=delta):
                    t4 = self.T(np.array([E - 2 * delta, E - delta, E + delta, E + 2 * delta]))
                    return (-t4[3] + 8 * t4[2] - 8 * t4[1] + t4[0]) / (12 * delta)
                a, b = grid[k - 1], grid[k + 1]
                j = 1
                while D(a) <= 0 or D(b) >= 0:
                    j += 1
                    if j > 5:
                        raise RuntimeError(f"maximum near {grid[k]} not bracketed")
                    a, b = grid[max(0, k - j)], grid[min(n - 1, k + j)]
                Em = brentq(D, a, b, xtol=1e-14, rtol=1e-15, maxiter=200)
                out.append((Em, float(self.T(Em)[0])))
        return out

    # ------------------------------------------------------------ report
    def report(self):
        d = self.d
        bs = [dict(E_eV=float(E)) for E in self.bound_states()]
        Es = d["transmission_energies_eV"]
        Ts = self.T(np.array(Es, dtype=float))
        tr = [dict(E_eV=E, T=float(T)) for E, T in zip(Es, Ts)]
        mx = [dict(E_eV=float(E), T=T) for E, T in self.maxima(*[float(v) for v in d["window_eV"]])]
        return dict(structure_id=self.id, bound_states=bs, transmission=tr, maxima=mx)


def solve(d):
    return Structure(d).report()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--structure", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    with open(a.structure, encoding="utf-8") as fh:
        d = json.load(fh)
    rep = solve(d)
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
