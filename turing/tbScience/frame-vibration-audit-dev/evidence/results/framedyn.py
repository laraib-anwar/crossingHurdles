#!/usr/bin/env python
"""Statics, natural frequencies and harmonic response of plane frames (FRAME_SPEC.md).

Members are exact Euler-Bernoulli beams with axial deformation and distributed mass: the member
dynamic stiffness matrix is the closed form in lambda = L (rho A omega^2 / EI)^(1/4) (bending)
and alpha = omega L sqrt(rho / E) (axial); for small lambda the bending functions suffer from
cancellation and are evaluated in 40-digit decimal arithmetic. Natural frequencies are counted
with the Wittrick-Williams algorithm, J(omega) = sum over members of J0 (clamped-clamped member
frequencies below omega, bending and axial) + s{K(omega)} (negative pivots of the assembled
dynamic stiffness on the free degrees of freedom), and each frequency is isolated and located by
bisection on J to machine precision, so that member-local modes, repeated roots and poles of the
dynamic stiffness are all handled by counting rather than by root finding. Statics: exact
stiffness method with fixed-end actions. Harmonic response: K(omega_h) U = F.

usage: framedyn.py --frame <frame.json> --output <report.json>
"""
import argparse
import json
import math
from decimal import Decimal, getcontext

import numpy as np

getcontext().prec = 45
LAMBDA_DECIMAL = 1.5      # below this, bending functions in decimal arithmetic


# ------------------------------------------------------------------ member functions
def _dec_trig(x):
    """sin, cos, sinh, cosh of a Decimal by Taylor series (|x| small)."""
    s, c, sh, ch = Decimal(0), Decimal(0), Decimal(0), Decimal(0)
    term = Decimal(1)
    n = 0
    while True:
        if n % 2 == 0:
            c += term * (1 if n % 4 == 0 else -1)
            ch += term
        else:
            s += term * (1 if n % 4 == 1 else -1)
            sh += term
        n += 1
        term = term * x / n
        if abs(term) < Decimal(10) ** -44:
            break
    return s, c, sh, ch


def bending_functions(lam):
    """a, b, c, d, e, f of the Euler-Bernoulli dynamic stiffness (lam >= 0)."""
    if lam == 0.0:
        return 12.0, 6.0, 4.0, 12.0, 6.0, 2.0
    if lam < LAMBDA_DECIMAL:
        x = Decimal(repr(lam))
        s, c, sh, ch = _dec_trig(x)
        D = 1 - c * ch
        l2, l3 = x * x, x * x * x
        vals = (l3 * (s * ch + c * sh) / D, l2 * (s * sh) / D, x * (s * ch - c * sh) / D,
                l3 * (s + sh) / D, l2 * (ch - c) / D, x * (sh - s) / D)
        return tuple(float(v) for v in vals)
    s, c, sh, ch = math.sin(lam), math.cos(lam), math.sinh(lam), math.cosh(lam)
    D = 1.0 - c * ch
    l2, l3 = lam * lam, lam ** 3
    return (l3 * (s * ch + c * sh) / D, l2 * (s * sh) / D, lam * (s * ch - c * sh) / D,
            l3 * (s + sh) / D, l2 * (ch - c) / D, lam * (sh - s) / D)


def axial_functions(alpha):
    """Diagonal and off-diagonal factors of the axial dynamic stiffness (times EA/L)."""
    if alpha == 0.0:
        return 1.0, -1.0
    if alpha < 1e-3:
        x = Decimal(repr(alpha))
        s, c, _, _ = _dec_trig(x)
        return float(x * c / s), float(-x / s)
    s, c = math.sin(alpha), math.cos(alpha)
    return alpha * c / s, -alpha / s


# clamped-clamped bending roots of 1 - cos(l) cosh(l) = 0 (cos l = 1 / cosh l, no overflow)
def _cc_roots(n_max=400):
    from scipy.optimize import brentq
    roots = []
    for n in range(1, n_max + 1):
        guess = (2 * n + 1) * math.pi / 2
        f = lambda l: math.cos(l) - 1.0 / math.cosh(l)
        a, b = guess - 0.6, guess + 0.6
        if n <= 6:
            roots.append(brentq(f, a, b, xtol=1e-15, rtol=1e-15, maxiter=300))
        else:
            roots.append(guess)          # (2n+1) pi / 2 exact to below 1e-15 for n > 6
    return np.array(roots)


CC_ROOTS = _cc_roots()


def j0_bending(lam):
    return int(np.searchsorted(CC_ROOTS, lam, side="right"))


def j0_axial(alpha):
    return int(math.floor(alpha / math.pi - 1e-15)) if alpha > 0 else 0


# ------------------------------------------------------------------ frame
class Member:
    def __init__(self, d, nodes):
        self.id, self.i, self.j = d["id"], d["i"], d["j"]
        xi, yi = nodes[self.i]
        xj, yj = nodes[self.j]
        self.L = math.hypot(xj - xi, yj - yi)
        self.cx, self.cy = (xj - xi) / self.L, (yj - yi) / self.L
        self.E, self.A, self.I, self.rho = float(d["E"]), float(d["A"]), float(d["I"]), float(d["rho"])
        self.T = np.zeros((6, 6))
        for k in (0, 3):
            self.T[k, k], self.T[k, k + 1] = self.cx, self.cy
            self.T[k + 1, k], self.T[k + 1, k + 1] = -self.cy, self.cx
            self.T[k + 2, k + 2] = 1.0

    def params(self, omega):
        lam = self.L * (self.rho * self.A * omega * omega / (self.E * self.I)) ** 0.25
        alpha = omega * self.L * math.sqrt(self.rho / self.E)
        return lam, alpha

    def local_matrix(self, omega):
        L, E, A, I = self.L, self.E, self.A, self.I
        lam, alpha = self.params(omega)
        a, b, c, d, e, f = bending_functions(lam)
        p, q = axial_functions(alpha)
        K = np.zeros((6, 6))
        K[0, 0] = K[3, 3] = E * A / L * p
        K[0, 3] = K[3, 0] = E * A / L * q
        k = E * I / L ** 3
        B = k * np.array([[a, b * L, -d, e * L], [b * L, c * L * L, -e * L, f * L * L],
                          [-d, -e * L, a, -b * L], [e * L, f * L * L, -b * L, c * L * L]])
        idx = [1, 2, 4, 5]
        for r, ri in enumerate(idx):
            for s, si in enumerate(idx):
                K[ri, si] = B[r, s]
        return K

    def global_matrix(self, omega):
        return self.T.T @ self.local_matrix(omega) @ self.T

    def j0(self, omega):
        lam, alpha = self.params(omega)
        return j0_bending(lam) + j0_axial(alpha)

    def fixed_end_global(self, wx, wy):
        """Equivalent nodal load vector (global) of a uniform member load (global components)."""
        qa = wx * self.cx + wy * self.cy          # axial component (local x)
        qt = -wx * self.cy + wy * self.cx         # transverse component (local y)
        L = self.L
        local = np.array([qa * L / 2, qt * L / 2, qt * L * L / 12, qa * L / 2, qt * L / 2, -qt * L * L / 12])
        return self.T.T @ local


class Frame:
    def __init__(self, d):
        self.id = d["frame_id"]
        self.d = d
        self.nodes = {n["id"]: (float(n["x"]), float(n["y"])) for n in d["nodes"]}
        self.N = len(d["nodes"])
        self.mass = {n["id"]: float(n["mass_kg"]) for n in d["nodes"]}
        self.members = [Member(m, self.nodes) for m in d["members"]]
        self.free = []
        for n in d["nodes"]:
            for k, dof in enumerate(("ux", "uy", "rz")):
                if not n["support"][dof]:
                    self.free.append(3 * (n["id"] - 1) + k)
        self.free = np.array(self.free, dtype=int)

    def dof(self, node, name):
        return 3 * (node - 1) + ("ux", "uy", "rz").index(name)

    def assemble(self, omega):
        n = 3 * self.N
        K = np.zeros((n, n))
        for m in self.members:
            idx = [3 * (m.i - 1), 3 * (m.i - 1) + 1, 3 * (m.i - 1) + 2, 3 * (m.j - 1), 3 * (m.j - 1) + 1, 3 * (m.j - 1) + 2]
            K[np.ix_(idx, idx)] += m.global_matrix(omega)
        for nid, ms in self.mass.items():
            if ms:
                for k in (0, 1):
                    K[3 * (nid - 1) + k, 3 * (nid - 1) + k] -= ms * omega * omega
        return K[np.ix_(self.free, self.free)]

    @staticmethod
    def sign_count(K):
        """Number of negative pivots of the LDL^T factorisation without pivoting. The matrix is
        first scaled symmetrically by its diagonal (a congruence, which preserves the inertia) and
        eliminated in extended precision, so that pivot growth cannot flip a sign near a root."""
        d = np.sqrt(np.abs(np.diag(K)))
        d[d == 0.0] = 1.0
        A = (K / d[:, None] / d[None, :]).astype(np.longdouble)
        n = A.shape[0]
        neg = 0
        for k in range(n):
            p = A[k, k]
            if p == 0.0:
                p = np.longdouble(1e-300)
            if p < 0:
                neg += 1
            if k + 1 < n:
                row = A[k, k + 1:] / p
                A[k + 1:, k + 1:] -= np.outer(A[k + 1:, k], row)
        return neg

    def count(self, omega):
        return sum(m.j0(omega) for m in self.members) + self.sign_count(self.assemble(omega))

    def frequencies(self, n_modes):
        hi = 1.0
        while self.count(hi) < n_modes:
            hi *= 2.0
        out = []
        for k in range(1, n_modes + 1):
            lo, up = 0.0, hi
            # bisection on the count: frequency k is where the count reaches k
            for _ in range(200):
                mid = 0.5 * (lo + up)
                if self.count(mid) >= k:
                    up = mid
                else:
                    lo = mid
                if up - lo <= 1e-15 * up:
                    break
            out.append(0.5 * (lo + up))
        return out

    def static(self):
        d = self.d
        n = 3 * self.N
        F = np.zeros(n)
        for ld in d["nodal_loads"]:
            b = 3 * (ld["node"] - 1)
            F[b] += ld["Fx"]
            F[b + 1] += ld["Fy"]
            F[b + 2] += ld["Mz"]
        by_id = {m.id: m for m in self.members}
        for ld in d["member_loads"]:
            m = by_id[ld["member"]]
            fe = m.fixed_end_global(ld["wx"], ld["wy"])
            idx = [3 * (m.i - 1), 3 * (m.i - 1) + 1, 3 * (m.i - 1) + 2, 3 * (m.j - 1), 3 * (m.j - 1) + 1, 3 * (m.j - 1) + 2]
            F[idx] += fe
        u = np.zeros(n)
        u[self.free] = np.linalg.solve(self.assemble(0.0), F[self.free])
        return u

    def harmonic(self, q):
        omega = 2 * math.pi * q["f_Hz"]
        n = 3 * self.N
        F = np.zeros(n)
        F[self.dof(q["load_node"], q["load_dof"])] = q["amplitude"]
        u = np.zeros(n)
        u[self.free] = np.linalg.solve(self.assemble(omega), F[self.free])
        return float(u[self.dof(q["response_node"], q["response_dof"])])

    def report(self):
        d = self.d
        u = self.static()
        st = [dict(node=nid, ux=float(u[3 * (nid - 1)]), uy=float(u[3 * (nid - 1) + 1]), rz=float(u[3 * (nid - 1) + 2]))
              for nid in d["static_query_nodes"]]
        fr = [w / (2 * math.pi) for w in self.frequencies(int(d["n_modes"]))]
        cb = self.count(2 * math.pi * float(d["f_max_Hz"]))
        hm = [dict(load_node=q["load_node"], load_dof=q["load_dof"], amplitude=q["amplitude"], f_Hz=q["f_Hz"],
                   response_node=q["response_node"], response_dof=q["response_dof"], U=self.harmonic(q)) for q in d["harmonic_queries"]]
        return dict(frame_id=self.id, static=st, frequencies_Hz=fr, count_below=cb, harmonic=hm)


def solve(d):
    return Frame(d).report()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    with open(a.frame, encoding="utf-8") as fh:
        d = json.load(fh)
    rep = solve(d)
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
