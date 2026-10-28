#!/usr/bin/env python3
"""Reference A for FRAME_SPEC: plane-frame statics, exact natural frequencies, harmonic response.

    python reference.py --frame <frame.json> --output <report.json> [--diag <diag.json>]

Route (independent of any closed-form dynamic-stiffness / Wittrick-Williams implementation):

* Member state systems. Along xi = s/L in [0, 1] each member carries the axial state (u, N)
  and the bending state (v, theta, M, Q), Q = dM/ds, in dimensionless variables scaled by
  sigma = max(lambda, 1) (bending) and max(alpha, 1) (axial), so that the system matrix is sigma
  times a cyclic-shift (bending) or rotation-generator (axial) matrix. The transfer over a
  segment is exp(h A) from a Taylor series summed to machine precision (scipy.linalg.expm is the
  cross-check). The 4-dimensional subspace of admissible bending end-state pairs
  [z(0); z(1)] is propagated segment by segment (growth at most e per segment) with a QR whose
  R has a positive diagonal, so the final orthonormal basis is the unique positive-R QR factor
  of [I; T] and depends continuously on omega (no exp(lambda) is ever formed).
* One global linear system G(omega): unknowns are the 6 basis coordinates of every member
  (i.e. its 12 end states) and the 3 displacements of every node; equations are compatibility
  of ux, uy, rz at every member end and, at every node dof, either the support condition or
  equilibrium of the member end forces with the lumped-mass inertia m omega^2. Natural
  frequencies are the zeros of det G(omega) (LU, sign tracked; positive row scaling); a member
  vibrating between two nodes that do not move is a zero like any other.
* Counting. An independent conforming FE model (one p-version element per member: cubic
  Hermite bending and linear axial nodal functions plus integrated-Legendre bubbles,
  consistent mass) at two degrees (nested spaces, Rayleigh-Ritz upper bounds). The number of
  FE eigenvalues below omega^2 is the inertia of K - omega^2 M by a block LDL^T with the member
  interiors eliminated first (Haynsworth additivity; interior stiffness is diagonal, so the
  elimination has no cancellation). FE eigenvalues (bisection on the count) bracket every exact
  root, which brentq refines on det G; the FE count at both degrees must step by exactly one
  between consecutive roots, and count_below is certified at f_max (1 - 1e-8, 1, 1 + 1e-8).
* Statics: the same end-state system at omega = 0 with the particular solution of the uniform
  member load (augmented nilpotent state, exact polynomial transfer), solved by LU with
  iterative refinement on exactly evaluated (rational) residuals. Harmonic: G(omega_h) with the
  nodal force on the right-hand side, same refinement.
* --diag writes certification data and cross-checks (classical stiffness method for statics,
  p-version FE for harmonic, det roots for count_below) to a JSON file.
"""
import argparse
import json
import math
import sys
import warnings
from fractions import Fraction

import numpy as np
import scipy.linalg as sla
from scipy.optimize import brentq

TWO_PI = 2.0 * math.pi
DIAG = {}


def warn(msg):
    DIAG.setdefault("warnings", []).append(msg)
    try:
        sys.stderr.write("reference: " + msg + "\n")
    except Exception:
        pass


# ----------------------------------------------------------------------------- input

def _pairs_no_dup(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError("duplicate key %r" % k)
        d[k] = v
    return d


def read_frame(path):
    with open(path, "rb") as f:
        raw = f.read()
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs_no_dup)


class Frame:
    def __init__(self, fr):
        self.raw = fr
        nodes = fr["nodes"]
        mems = fr["members"]
        self.N = len(nodes)
        self.M = len(mems)
        self.x = np.array([float(n["x"]) for n in nodes])
        self.y = np.array([float(n["y"]) for n in nodes])
        self.mass = np.array([float(n["mass_kg"]) for n in nodes])
        self.sup = np.array([[bool(n["support"][d]) for d in ("ux", "uy", "rz")]
                             for n in nodes], dtype=bool)
        self.mi = np.array([int(m["i"]) - 1 for m in mems], dtype=int)
        self.mj = np.array([int(m["j"]) - 1 for m in mems], dtype=int)
        self.E = np.array([float(m["E"]) for m in mems])
        self.A = np.array([float(m["A"]) for m in mems])
        self.I = np.array([float(m["I"]) for m in mems])
        self.rho = np.array([float(m["rho"]) for m in mems])
        dx = self.x[self.mj] - self.x[self.mi]
        dy = self.y[self.mj] - self.y[self.mi]
        self.L = np.hypot(dx, dy)
        self.c = dx / self.L
        self.s = dy / self.L
        self.EA = self.E * self.A
        self.EI = self.E * self.I
        self.rA = self.rho * self.A
        self.beta4 = self.rA * self.L ** 4 / self.EI       # lambda^4 = beta4 omega^2
        self.alc = self.L * np.sqrt(self.rho / self.E)       # alpha = alc omega
        # loads
        self.P = np.zeros((self.N, 3))
        for ld in fr.get("nodal_loads", []):
            n = int(ld["node"]) - 1
            self.P[n, 0] += float(ld["Fx"])
            self.P[n, 1] += float(ld["Fy"])
            self.P[n, 2] += float(ld["Mz"])
        self.w = np.zeros((self.M, 2))
        for ld in fr.get("member_loads", []):
            k = int(ld["member"]) - 1
            self.w[k, 0] += float(ld["wx"])
            self.w[k, 1] += float(ld["wy"])
        self.free = ~self.sup.reshape(-1)
        self.n_unk = 6 * self.M + 3 * self.N

    def lam(self, omega):
        return (self.beta4 * omega * omega) ** 0.25

    def alpha(self, omega):
        return self.alc * omega


# ----------------------------------------------------------------------------- exponentials

def taylor_expm_batch(A):
    """exp(A) for a stack of small matrices with modest norm (<= ~1.5), Taylor series
    summed until the next term is below 1e-18 relative (machine precision)."""
    n = A.shape[-1]
    E = np.zeros_like(A)
    E[..., np.arange(n), np.arange(n)] = 1.0
    T = E.copy()
    for k in range(1, 60):
        T = (T @ A) / k
        E = E + T
        if np.max(np.abs(T)) <= 1e-18 * max(1.0, float(np.max(np.abs(E)))):
            break
    return E


def expm_scaled_batch(A, target=0.5):
    """exp(A) by scaling-and-squaring around the Taylor sum (used only for the axial block,
    whose exponential is a rotation, and for the nilpotent static transfer)."""
    nrm = float(np.max(np.sum(np.abs(A), axis=-1))) if A.size else 0.0
    sq = 0
    if nrm > target:
        sq = int(math.ceil(math.log2(nrm / target)))
    E = taylor_expm_batch(A / (2.0 ** sq))
    for _ in range(sq):
        E = E @ E
    return E


def qr_pos(X):
    """Batched reduced QR with the diagonal of R made positive."""
    Q, R = np.linalg.qr(X)
    d = np.sign(np.diagonal(R, axis1=-2, axis2=-1))
    d[d == 0] = 1.0
    return Q * d[..., None, :]


# ----------------------------------------------------------------------------- member bases

STEP_SIGMA = 1.0   # growth per marching segment is at most exp(STEP_SIGMA)


def bending_bases(fr, omega, step_sigma=STEP_SIGMA, use_scipy=False):
    """Orthonormal basis (8x4 per member) of admissible bending end-state pairs
    [z(0); z(1)], z = (v, thL/s, M L^2/(EI s^2), Q L^3/(EI s^3)), s = max(lambda, 1)."""
    lam = fr.lam(omega)
    sig = np.maximum(lam, 1.0)
    mu = (lam / sig) ** 4
    ns = max(1, int(math.ceil(float(np.max(sig)) / step_sigma)))
    h = 1.0 / ns
    M = fr.M
    Az = np.zeros((M, 4, 4))
    Az[:, 0, 1] = sig * h
    Az[:, 1, 2] = sig * h
    Az[:, 2, 3] = sig * h
    Az[:, 3, 0] = sig * h * mu
    if use_scipy:
        Phi = np.array([sla.expm(Az[k]) for k in range(M)])
    else:
        Phi = taylor_expm_batch(Az)
    W = np.zeros((M, 8, 4))
    W[:, 0:4, :] = np.eye(4) / math.sqrt(2.0)
    W[:, 4:8, :] = np.eye(4) / math.sqrt(2.0)
    for _ in range(ns):
        X = W.copy()
        X[:, 4:8, :] = Phi @ W[:, 4:8, :]
        W = qr_pos(X)
    return W, sig, Phi


def axial_bases(fr, omega):
    """Orthonormal basis (4x2 per member) of admissible axial end-state pairs
    [w(0); w(1)], w = (u, N L/(EA sa)), sa = max(alpha, 1)."""
    al = fr.alpha(omega)
    sa = np.maximum(al, 1.0)
    mu = (al / sa) ** 2
    M = fr.M
    A = np.zeros((M, 2, 2))
    A[:, 0, 1] = sa
    A[:, 1, 0] = -sa * mu
    T = expm_scaled_batch(A)
    X = np.zeros((M, 4, 2))
    X[:, 0:2, :] = np.eye(2)
    X[:, 2:4, :] = T
    return qr_pos(X), sa


# ----------------------------------------------------------------------------- global G(omega)

def assemble_G(fr, omega, step_sigma=STEP_SIGMA, use_scipy=False):
    Wa, sa = axial_bases(fr, omega)
    Wb, sb, _ = bending_bases(fr, omega, step_sigma, use_scipy)
    M, N = fr.M, fr.N
    n = 6 * M + 3 * N
    G = np.zeros((n, n))
    w2 = omega * omega
    off = 6 * M
    for k in range(M):
        c, s, L = fr.c[k], fr.s[k], fr.L[k]
        kN = fr.EA[k] / L * sa[k]
        kM = fr.EI[k] / L ** 2 * sb[k] ** 2
        kQ = fr.EI[k] / L ** 3 * sb[k] ** 3
        cols = slice(6 * k, 6 * k + 6)
        for e in (0, 1):
            node = fr.mi[k] if e == 0 else fr.mj[k]
            u = np.zeros(6); Nf = np.zeros(6); v = np.zeros(6)
            thL = np.zeros(6); Mm = np.zeros(6); Qf = np.zeros(6)
            u[0:2] = Wa[k, 2 * e + 0, :]
            Nf[0:2] = kN * Wa[k, 2 * e + 1, :]
            v[2:6] = Wb[k, 4 * e + 0, :]
            thL[2:6] = sb[k] * Wb[k, 4 * e + 1, :]
            Mm[2:6] = kM * Wb[k, 4 * e + 2, :]
            Qf[2:6] = kQ * Wb[k, 4 * e + 3, :]
            r0 = 6 * k + 3 * e
            G[r0, cols] = c * u - s * v
            G[r0, off + 3 * node] = -1.0
            G[r0 + 1, cols] = s * u + c * v
            G[r0 + 1, off + 3 * node + 1] = -1.0
            G[r0 + 2, cols] = thL
            G[r0 + 2, off + 3 * node + 2] = -L
            sg = 1.0 if e == 0 else -1.0
            Fa = sg * Nf
            Ft = -sg * Qf
            Mn = sg * Mm
            rn = off + 3 * node
            if not fr.sup[node, 0]:
                G[rn, cols] += c * Fa - s * Ft
            if not fr.sup[node, 1]:
                G[rn + 1, cols] += s * Fa + c * Ft
            if not fr.sup[node, 2]:
                G[rn + 2, cols] += Mn
    for node in range(N):
        for d in range(3):
            r = off + 3 * node + d
            if fr.sup[node, d]:
                G[r, :] = 0.0
                G[r, r] = 1.0
            elif d < 2:
                G[r, r] += fr.mass[node] * w2
    return G


def row_scale(G):
    r = np.sum(np.abs(G), axis=1)
    r[r == 0] = 1.0
    return 1.0 / r


def signed_logdet(G):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")       # an exactly zero pivot means det G = 0
        lu, piv = sla.lu_factor(G, check_finite=False)
    d = np.diagonal(lu)
    sgn = 1.0
    if np.any(d == 0):
        return 0.0, -np.inf
    sgn *= float(np.prod(np.sign(d)))
    nswap = int(np.sum(piv != np.arange(len(piv))))
    if nswap % 2:
        sgn = -sgn
    return sgn, float(np.sum(np.log(np.abs(d))))


def det_eval(fr, omega, **kw):
    G = assemble_G(fr, omega, **kw)
    G = G * row_scale(G)[:, None]
    return signed_logdet(G)


# ----------------------------------------------------------------------------- statics

def static_transfer(fr):
    """Exact transfer of the dimensionless state y = (u, N L/EA, v, thL, M L^2/EI, Q L^3/EI)
    with the uniform-load particular solution: y(1) = T y(0) + p (augmented nilpotent system)."""
    M = fr.M
    A = np.zeros((M, 7, 7))
    qa = fr.w[:, 0] * fr.c + fr.w[:, 1] * fr.s
    qt = -fr.w[:, 0] * fr.s + fr.w[:, 1] * fr.c
    A[:, 0, 1] = 1.0
    A[:, 1, 6] = -qa * fr.L ** 2 / fr.EA
    A[:, 2, 3] = 1.0
    A[:, 3, 4] = 1.0
    A[:, 4, 5] = 1.0
    A[:, 5, 6] = qt * fr.L ** 4 / fr.EI
    E = expm_scaled_batch(A, target=1e300)   # nilpotent: the Taylor series terminates
    return E[:, 0:6, 0:6], E[:, 0:6, 6]


def assemble_static(fr):
    M, N = fr.M, fr.N
    nm = 12 * M
    n = nm + 3 * N
    G = np.zeros((n, n))
    b = np.zeros(n)
    T, p = static_transfer(fr)
    off_eq = 6 * M     # compatibility rows start
    off_nd = 12 * M    # node rows / node unknowns
    for k in range(M):
        c0 = 12 * k
        # member transfer rows: y1 - T y0 = p
        for r in range(6):
            G[6 * k + r, c0 + 6 + r] = 1.0
            G[6 * k + r, c0:c0 + 6] = -T[k, r, :]
            b[6 * k + r] = p[k, r]
        c, s, L = fr.c[k], fr.s[k], fr.L[k]
        kN = fr.EA[k] / L
        kM = fr.EI[k] / L ** 2
        kQ = fr.EI[k] / L ** 3
        for e in (0, 1):
            node = fr.mi[k] if e == 0 else fr.mj[k]
            ce = c0 + 6 * e
            r0 = off_eq + 6 * k + 3 * e
            rn = off_nd + 3 * node
            G[r0, ce + 0] = c
            G[r0, ce + 2] = -s
            G[r0, rn] = -1.0
            G[r0 + 1, ce + 0] = s
            G[r0 + 1, ce + 2] = c
            G[r0 + 1, rn + 1] = -1.0
            G[r0 + 2, ce + 3] = 1.0
            G[r0 + 2, rn + 2] = -L
            sg = 1.0 if e == 0 else -1.0
            # force on node: axial sg*N, transverse -sg*Q, moment sg*M
            if not fr.sup[node, 0]:
                G[rn, ce + 1] += c * sg * kN
                G[rn, ce + 5] += -s * (-sg) * kQ
            if not fr.sup[node, 1]:
                G[rn + 1, ce + 1] += s * sg * kN
                G[rn + 1, ce + 5] += c * (-sg) * kQ
            if not fr.sup[node, 2]:
                G[rn + 2, ce + 4] += sg * kM
    for node in range(N):
        for d in range(3):
            r = off_nd + 3 * node + d
            if fr.sup[node, d]:
                G[r, :] = 0.0
                G[r, r] = 1.0
                b[r] = 0.0
            else:
                b[r] = -fr.P[node, d]
    return G, b


def exact_residual(G, x, b):
    """r = b - G x evaluated exactly in rationals (G, x, b are doubles), rounded once."""
    n = G.shape[0]
    r = np.zeros(n)
    xf = [Fraction(float(v)) for v in x]
    for i in range(n):
        idx = np.nonzero(G[i])[0]
        acc = Fraction(float(b[i]))
        for j in idx:
            acc -= Fraction(float(G[i, j])) * xf[j]
        r[i] = float(acc)
    return r


def solve_refined(G, b, iters=4):
    rs = row_scale(G)
    Gs = G * rs[:, None]
    bs = b * rs
    lu = sla.lu_factor(Gs, check_finite=False)
    x = sla.lu_solve(lu, bs, check_finite=False)
    hist = []
    for _ in range(iters):
        r = exact_residual(Gs, x, bs)
        dx = sla.lu_solve(lu, r, check_finite=False)
        x = x + dx
        rel = float(np.max(np.abs(dx)) / max(np.max(np.abs(x)), 1e-300))
        hist.append(rel)
        if rel < 1e-17:
            break
    return x, hist


def statics(fr):
    G, b = assemble_static(fr)
    x, hist = solve_refined(G, b)
    DIAG["static_refinement"] = hist
    return x[12 * fr.M:].reshape(fr.N, 3)


# ----------------------------------------------------------------------------- harmonic

def harmonic(fr, omega, node, dof, amp):
    G = assemble_G(fr, omega)
    b = np.zeros(fr.n_unk)
    r = 6 * fr.M + 3 * node + dof
    if not fr.sup[node, dof]:
        b[r] = -amp
    x, hist = solve_refined(G, b, iters=3)
    return x[6 * fr.M:].reshape(fr.N, 3), hist


# ----------------------------------------------------------------------------- finite elements
# Conforming FE model of the frame used only for counting: one element per member with the
# cubic Hermite (bending) and linear (axial) nodal shape functions plus hierarchical bubbles
# (twice-integrated Legendre polynomials for bending, once-integrated for axial), consistent
# mass. The bubbles are orthogonal in energy to each other and to the nodal functions, so the
# member-interior stiffness is diagonal and there is no cancellation when the interior is
# eliminated. Raising the degree refines the model (nested spaces, Rayleigh-Ritz upper bounds).

_REF_CACHE = {}


def ref_matrices(pb, pa):
    """Reference matrices on xi in [-1, 1]: bending mass (pb+1)^2 with the four Hermite
    functions first (v(-1), dv/dxi(-1), v(1), dv/dxi(1)), the 4x4 Hermite stiffness
    int v'' v'' dxi, axial mass (pa+1)^2 (linear functions first) and 2x2 axial stiffness."""
    key = (pb, pa)
    if key in _REF_CACHE:
        return _REF_CACHE[key]
    Leg = np.polynomial.legendre
    x, wg = Leg.leggauss(max(pb, pa) + 6)
    Bv = [(1 - x) ** 2 * (2 + x) / 4, (1 - x) ** 2 * (1 + x) / 4,
          (1 + x) ** 2 * (2 - x) / 4, -(1 + x) ** 2 * (1 - x) / 4]
    Bd2 = [1.5 * x, (3 * x - 1) / 2, -1.5 * x, (3 * x + 1) / 2]
    for k in range(4, pb + 1):
        cf = np.zeros(k - 1)
        cf[k - 2] = 1.0
        sc = math.sqrt((2 * k - 3) / 2.0)
        Bv.append(sc * Leg.legval(x, Leg.legint(cf, m=2, lbnd=-1)))
    Bv = np.array(Bv)
    Bd2 = np.array(Bd2)
    Mb = (Bv * wg) @ Bv.T
    Kb4 = (Bd2 * wg) @ Bd2.T
    Av = [(1 - x) / 2, (1 + x) / 2]
    for k in range(2, pa + 1):
        cf = np.zeros(k)
        cf[k - 1] = 1.0
        sc = math.sqrt((2 * k - 1) / 2.0)
        Av.append(sc * Leg.legval(x, Leg.legint(cf, m=1, lbnd=-1)))
    Av = np.array(Av)
    Ma = (Av * wg) @ Av.T
    Ka2 = np.array([[0.5, -0.5], [-0.5, 0.5]])
    out = (Mb, Kb4, Ma, Ka2)
    _REF_CACHE[key] = out
    return out


_MEMBER_CACHE = {}


def member_fe(EA, EI, rA, L, pb, pa):
    """Interior eigen-decomposition (eigenvalues lam = omega^2 of the member with its ends
    clamped, in the FE space) and boundary coupling P = Phi^T M_ib in the local end dofs
    (u0, v0, th0, u1, v1, th1); K_ib = 0 by orthogonality of the bubbles."""
    key = (EA, EI, rA, L, pb, pa)
    if key in _MEMBER_CACHE:
        return _MEMBER_CACHE[key]
    Mb, Kb4, Ma, Ka2 = ref_matrices(pb, pa)
    mu0 = rA * L / 2.0
    Kbb = np.zeros((6, 6))
    Mbb = np.zeros((6, 6))
    lams, Ps = [], []
    # bending
    kap = EI * (2.0 / L) ** 3
    fac = np.array([1.0, L / 2.0, 1.0, L / 2.0])
    loc = [1, 2, 4, 5]
    Kbb[np.ix_(loc, loc)] += kap * Kb4 * np.outer(fac, fac)
    Mbb[np.ix_(loc, loc)] += mu0 * Mb[:4, :4] * np.outer(fac, fac)
    if pb > 3:
        m, V = np.linalg.eigh(Mb[4:, 4:])
        m = np.maximum(m, 1e-300)
        P = np.zeros((pb - 3, 6))
        P[:, loc] = (V.T @ Mb[4:, :4]) * fac[None, :] * np.sqrt(mu0 / m)[:, None]
        lams.append(kap / (mu0 * m))
        Ps.append(P)
    # axial
    kap = EA * (2.0 / L)
    loc = [0, 3]
    Kbb[np.ix_(loc, loc)] += kap * Ka2
    Mbb[np.ix_(loc, loc)] += mu0 * Ma[:2, :2]
    if pa > 1:
        m, V = np.linalg.eigh(Ma[2:, 2:])
        m = np.maximum(m, 1e-300)
        P = np.zeros((pa - 1, 6))
        P[:, loc] = (V.T @ Ma[2:, :2]) * np.sqrt(mu0 / m)[:, None]
        lams.append(kap / (mu0 * m))
        Ps.append(P)
    lam = np.concatenate(lams) if lams else np.zeros(0)
    P = np.vstack(Ps) if Ps else np.zeros((0, 6))
    o = np.argsort(lam, kind="stable")
    res = (lam[o], P[o], Kbb, Mbb)
    _MEMBER_CACHE[key] = res
    return res


class FrameFE:
    def __init__(self, fr, pb, pa):
        self.fr = fr
        self.pb = np.array(pb, dtype=int)
        self.pa = np.array(pa, dtype=int)
        parts = []
        for k in range(fr.M):
            lam, P, Kbb, Mbb = member_fe(fr.EA[k], fr.EI[k], fr.rA[k], fr.L[k],
                                         int(self.pb[k]), int(self.pa[k]))
            c, s = fr.c[k], fr.s[k]
            R = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])
            T = np.zeros((6, 6))
            T[0:3, 0:3] = R
            T[3:6, 3:6] = R
            i, j = fr.mi[k], fr.mj[k]
            idx = np.array([3 * i, 3 * i + 1, 3 * i + 2, 3 * j, 3 * j + 1, 3 * j + 2])
            parts.append((lam, P @ T, T.T @ Kbb @ T, T.T @ Mbb @ T, idx))
        self.ndof = 3 * fr.N
        M = fr.M
        nmax = max(1, max(len(p[0]) for p in parts))
        # padded member arrays (padding: infinite interior eigenvalue, zero coupling)
        self.LAM = np.full((M, nmax), np.inf)
        self.PP = np.zeros((M, nmax, 6))
        self.KBB = np.zeros((M, 6, 6))
        self.MBB = np.zeros((M, 6, 6))
        rows = np.zeros((M, 6, 6), dtype=int)
        cols = np.zeros((M, 6, 6), dtype=int)
        for k, (lam, P, Kbb, Mbb, idx) in enumerate(parts):
            self.LAM[k, :len(lam)] = lam
            self.PP[k, :len(lam), :] = P
            self.KBB[k] = Kbb
            self.MBB[k] = Mbb
            rows[k] = idx[:, None]
            cols[k] = idx[None, :]
        self.flat = (rows * self.ndof + cols).reshape(-1)
        self.free = fr.free
        self.mdiag = np.zeros(self.ndof)
        self.mdiag[0::3] = fr.mass
        self.mdiag[1::3] = fr.mass
        self.ncount = 0

    def schur(self, omega):
        """Node-dof Schur complement of K - omega^2 M after eliminating every member interior,
        and the number of negative interior pivots (interior eigenvalues below omega^2)."""
        w = omega * omega
        nint = int(np.count_nonzero(self.LAM < w))
        d = self.LAM - w
        if np.any(d == 0.0):
            # omega^2 hit an interior eigenvalue exactly: it is not counted (strict "<"), so
            # treat it as lying just above omega^2
            d = np.where(d == 0.0, max(w, 1.0) * 1e-15, d)
        Q = self.PP / d[:, :, None]
        Sm = self.KBB - w * self.MBB - (w * w) * (np.transpose(self.PP, (0, 2, 1)) @ Q)
        S = np.bincount(self.flat, weights=Sm.reshape(-1),
                        minlength=self.ndof * self.ndof).reshape(self.ndof, self.ndof)
        S[np.diag_indices(self.ndof)] -= w * self.mdiag
        return S, nint

    def count(self, omega):
        """Number of FE eigenvalues below omega^2: inertia of K - omega^2 M by block LDL^T
        (interior blocks first; Haynsworth inertia additivity)."""
        self.ncount += 1
        S, nint = self.schur(omega)
        if not np.all(np.isfinite(S)):
            S, nint = self.schur(omega * (1.0 + 1e-15))
        Sf = S[np.ix_(self.free, self.free)]
        if Sf.size == 0:
            return nint
        dg = np.sqrt(np.maximum(np.abs(np.diagonal(Sf)), 1e-300))
        ev = np.linalg.eigvalsh(Sf / np.outer(dg, dg))   # congruence: same inertia
        return nint + int(np.sum(ev < 0.0))

    def eigs(self, K, rtol=1e-12, hi=None):
        """Lowest K FE eigenvalues (as omega) by bisection on the count."""
        cache = {}

        def cnt(om):
            if om not in cache:
                cache[om] = self.count(om)
            return cache[om]
        if hi is None or hi <= 0:
            hi = 1.0
        while cnt(hi) < K:
            hi *= 2.0
        lo = hi
        while lo > 1e-8 and cnt(lo) > 0:
            lo *= 0.5
        res = [None] * K
        stack = [(lo, cnt(lo), hi, cnt(hi))]
        while stack:
            a, na_, b, nb_ = stack.pop()
            if nb_ <= na_ or na_ >= K:
                continue
            if b - a <= rtol * b:
                for k in range(na_, min(nb_, K)):
                    res[k] = 0.5 * (a + b)
                continue
            m = math.sqrt(a * b) if (a > 0 and b > 2 * a) else 0.5 * (a + b)
            nm = cnt(m)
            stack.append((m, nm, b, nb_))
            stack.append((a, na_, m, nm))
        return np.array(res, dtype=float)


def degrees(fr, omega, extra, bmin=8, amin=6):
    pb = np.maximum(bmin, np.ceil(fr.lam(omega)).astype(int) + extra)
    pa = np.maximum(amin, np.ceil(fr.alpha(omega)).astype(int) + extra)
    return pb, pa


# ----------------------------------------------------------------------------- frequencies

class DetFun:
    def __init__(self, fr):
        self.fr = fr
        self.n = 0
        self.cache = {}

    def __call__(self, om):
        if om not in self.cache:
            self.n += 1
            self.cache[om] = det_eval(self.fr, om)
        return self.cache[om]


def find_root(df, lo, hi):
    slo, llo = df(lo)
    shi, lhi = df(hi)
    if slo == 0.0:
        return lo
    if shi == 0.0:
        return hi
    if slo == shi:
        return None
    C = 0.5 * (llo + lhi)

    def f(om):
        sg, ld = df(om)
        if sg == 0.0:
            return 0.0
        return sg * math.exp(min(ld - C, 700.0))
    return brentq(f, lo, hi, xtol=1e-300, rtol=8.9e-16, maxiter=300)


def exact_roots_from_fe(df, ef, ec):
    """One exact root of det G per FE eigenvalue, in increasing order. The window around the
    fine FE eigenvalue starts at the fine/coarse difference and widens until det G changes
    sign; it never reaches below the previous root."""
    roots = []
    last = None
    for k in range(len(ef)):
        e = ef[k]
        tau0 = max(4.0 * abs(ec[k] - e) / e, 1e-11)
        found = None
        tau = tau0
        while tau < 2e-3:
            lo = e * (1.0 - tau)
            hi = e * (1.0 + min(tau, 1e-9))
            if last is not None and lo <= last:
                lo = last * (1.0 + 1e-13)
            if lo < hi:
                found = find_root(df, lo, hi)
            if found is not None:
                break
            tau *= 10.0
        if found is None:
            return roots, k
        roots.append(found)
        last = found
    return roots, None


def locate(fr, df, K, om_top, extra):
    """FE eigenvalues (two degrees) up to index K, one exact root per eigenvalue, and the
    count certification at the midpoints between consecutive roots."""
    pbf, paf = degrees(fr, om_top, extra)
    pbc, pac = degrees(fr, om_top, extra - 8)
    fef = FrameFE(fr, pbf, paf)
    fec = FrameFE(fr, pbc, pac)
    ef = fef.eigs(K, rtol=1e-13, hi=om_top)
    ec = fec.eigs(K, rtol=1e-13, hi=om_top)
    roots, fail = exact_roots_from_fe(df, ef, ec)
    out = {"K": K, "fail_index": fail, "count_checks": [],
           "degree_fine_bending": [int(v) for v in pbf], "degree_fine_axial": [int(v) for v in paf],
           "degree_coarse_bending": [int(v) for v in pbc], "degree_coarse_axial": [int(v) for v in pac],
           "fe_fine_Hz": [float(v) / TWO_PI for v in ef],
           "fe_coarse_Hz": [float(v) / TWO_PI for v in ec]}
    ok = fail is None
    if ok:
        r = np.array(roots)
        if np.any(np.diff(r) <= 0):
            ok = False
        mids = [0.5 * r[0]] + [0.5 * (r[q] + r[q + 1]) for q in range(K - 1)]
        for q, m in enumerate(mids):
            nf_, nc_ = fef.count(m), fec.count(m)
            out["count_checks"].append([q, nf_, nc_])
            if nf_ != q or nc_ != q:
                ok = False
        out["max_rel_exact_vs_fe_fine"] = float(np.max(np.abs(r / ef - 1.0)))
        out["max_rel_fe_fine_vs_coarse"] = float(np.max(np.abs(ec / ef - 1.0)))
        if out["max_rel_exact_vs_fe_fine"] > 1e-8:
            ok = False
    out["certified"] = bool(ok)
    out["fe_counts"] = fef.ncount + fec.ncount
    return roots, ok, out, fef


def frequencies(fr, n_modes, omega_max, omega_hs):
    K = n_modes + 1
    df = DetFun(fr)
    floor_top = max([omega_max] + list(omega_hs))
    # pre-passes: converge the K-th FE eigenvalue to fix the frequency range
    pb = np.full(fr.M, 12)
    pa = np.full(fr.M, 8)
    eK_prev = None
    hi = floor_top
    for it in range(8):
        fe = FrameFE(fr, pb, pa)
        ev = fe.eigs(K, rtol=1e-7, hi=hi)
        eK = float(ev[-1])
        hi = eK
        if eK_prev is not None and abs(eK / eK_prev - 1.0) < 1e-5:
            break
        eK_prev = eK
        pb, pa = degrees(fr, max(eK, floor_top) * 1.02, 8)
    om_top = max(eK, floor_top) * 1.02
    extra = 18
    for attempt in range(4):
        roots, ok, info, fef = locate(fr, df, K, om_top, extra)
        if ok:
            break
        warn("frequency certification failed (attempt %d: %s); raising degree"
             % (attempt, {k: info[k] for k in ("fail_index", "count_checks")}))
        extra += 12
    info["top_Hz"] = om_top / TWO_PI
    if not ok:
        raise RuntimeError("frequency certification failed")
    cnt = count_below(fr, omega_max, extra, df, info)
    # cross-check of count_below by exact roots (diagnostic): locate every root up to the
    # first one above f_max when that reaches beyond the K roots already located
    r_all, ok_all = list(roots), True
    if cnt + 1 > K and cnt + 1 <= 120:
        try:
            eK2 = float(fef.eigs(cnt + 1, rtol=1e-9, hi=omega_max)[-1])
            r_all, ok_all, _, _ = locate(fr, df, cnt + 1, max(eK2, floor_top) * 1.02, extra)
        except Exception as exc:
            r_all, ok_all = [], False
            info["count_below_det_error"] = repr(exc)
    if r_all:
        ra = np.array(r_all)
        n_det = int(np.sum(ra <= omega_max))
        info["count_below_det_check"] = {
            "certified": bool(ok_all), "roots_below": n_det, "located": len(r_all),
            "nearest_root_rel_to_fmax": float(np.min(np.abs(ra / omega_max - 1.0))),
            "located_Hz": [float(v) / TWO_PI for v in ra]}
        if ok_all and len(r_all) > cnt and n_det != cnt:
            warn("count_below FE %d vs det roots %d" % (cnt, n_det))
    else:
        info["count_below_det_check"] = {"certified": False}
    info["det_evals"] = df.n
    return np.array(roots), cnt, info


def count_below(fr, omega_max, extra, df, info):
    """Number of natural frequencies <= omega_max. Certified when, at two FE degrees, the count
    is the same at omega_max and at omega_max (1 +- 1e-8): an exact frequency lies within
    [e/(1+err), e] of its FE eigenvalue e (err ~ 1e-12 here) and is at least 1e-6 relative away
    from omega_max, so no FE eigenvalue can straddle the threshold."""
    eps = 1e-8
    for attempt in range(4):
        pbf, paf = degrees(fr, omega_max * 1.02, extra)
        pbc, pac = degrees(fr, omega_max * 1.02, extra - 8)
        fef, fec = FrameFE(fr, pbf, paf), FrameFE(fr, pbc, pac)
        vals = [fe.count(omega_max * f) for fe in (fef, fec) for f in (1 - eps, 1.0, 1 + eps)]
        info.setdefault("count_below_checks", []).append(vals)
        if len(set(vals)) == 1:
            return vals[0]
        warn("count_below not certified (attempt %d: %s); raising degree" % (attempt, vals))
        extra += 12
    # fallback: resolve the FE eigenvalues in the window by exact roots
    nlo = fef.count(omega_max * (1 - 1e-4))
    nhi = fef.count(omega_max * (1 + 1e-4))
    ev = fef.eigs(nhi, rtol=1e-13, hi=omega_max * (1 + 1e-4))
    n = nlo
    for k in range(nlo, nhi):
        r = find_root(df, ev[k] * (1 - 1e-6), ev[k] * (1 + 1e-9))
        val = r if r is not None else ev[k]
        if val <= omega_max:
            n += 1
    warn("count_below resolved by det roots: %d" % n)
    return n

# ----------------------------------------------------------------------------- diagnostics only

def classical_statics(fr):
    """Classical stiffness method with fixed-end actions (diagnostic cross-check of statics)."""
    fe = FrameFE(fr, np.full(fr.M, 3), np.full(fr.M, 1))
    S, _ = fe.schur(0.0)
    F = fr.P.reshape(-1).copy()
    for k in range(fr.M):
        c, s, L = fr.c[k], fr.s[k], fr.L[k]
        qa = fr.w[k, 0] * c + fr.w[k, 1] * s
        qt = -fr.w[k, 0] * s + fr.w[k, 1] * c
        f = np.array([qa * L / 2, qt * L / 2, qt * L * L / 12, qa * L / 2, qt * L / 2,
                      -qt * L * L / 12])
        R = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])
        Tm = np.zeros((6, 6))
        Tm[0:3, 0:3] = R
        Tm[3:6, 3:6] = R
        i, j = fr.mi[k], fr.mj[k]
        F[[3 * i, 3 * i + 1, 3 * i + 2, 3 * j, 3 * j + 1, 3 * j + 2]] += Tm.T @ f
    D = np.zeros(3 * fr.N)
    fr_ = fr.free
    D[fr_] = np.linalg.solve(S[np.ix_(fr_, fr_)], F[fr_])
    return D.reshape(fr.N, 3)


def fe_harmonic(fr, omega, node, dof, amp, extra=18):
    pb, pa = degrees(fr, omega * 1.02, extra)
    fe = FrameFE(fr, pb, pa)
    S, _ = fe.schur(omega)
    F = np.zeros(3 * fr.N)
    F[3 * node + dof] = amp
    D = np.zeros(3 * fr.N)
    f = fr.free
    D[f] = np.linalg.solve(S[np.ix_(f, f)], F[f])
    return D.reshape(fr.N, 3)


# ----------------------------------------------------------------------------- driver

def finite(v):
    v = float(v)
    if not math.isfinite(v):
        raise ValueError("non-finite value")
    return v


def run(frame_path, out_path, diag_path=None):
    raw = read_frame(frame_path)
    fr = Frame(raw)
    n_modes = int(raw["n_modes"])
    omega_max = TWO_PI * float(raw["f_max_Hz"])
    hq = raw["harmonic_queries"]
    omega_hs = [TWO_PI * float(q["f_Hz"]) for q in hq]

    # statics
    D = statics(fr)
    static_out = []
    for nid in raw["static_query_nodes"]:
        n = int(nid) - 1
        static_out.append({"node": nid, "ux": finite(D[n, 0]), "uy": finite(D[n, 1]),
                           "rz": finite(D[n, 2])})

    try:
        Dc = classical_statics(fr)
        q = [int(nid) - 1 for nid in raw["static_query_nodes"]]
        errs = {}
        for d, name in ((0, "ux"), (1, "uy"), (2, "rz")):
            sc = max(float(np.max(np.abs(D[q, d]))), 1e-300)
            errs[name] = float(np.max(np.abs(D[q, d] - Dc[q, d]))) / sc
        DIAG["static_vs_classical_stiffness"] = errs
    except Exception as exc:
        DIAG["static_vs_classical_stiffness"] = repr(exc)

    # frequencies
    roots, cnt, info = frequencies(fr, n_modes, omega_max, omega_hs)
    freqs = [finite(r / TWO_PI) for r in roots[:n_modes]]
    DIAG["frequencies"] = info
    DIAG["omega_K_plus1_Hz"] = float(roots[-1] / TWO_PI)

    # harmonic
    dofs = {"ux": 0, "uy": 1, "rz": 2}
    harm_out = []
    for q in hq:
        om = TWO_PI * float(q["f_Hz"])
        Dh, hist = harmonic(fr, om, int(q["load_node"]) - 1, dofs[q["load_dof"]],
                            float(q["amplitude"]))
        U = Dh[int(q["response_node"]) - 1, dofs[q["response_dof"]]]
        harm_out.append({"load_node": q["load_node"], "load_dof": q["load_dof"],
                         "amplitude": q["amplitude"], "f_Hz": q["f_Hz"],
                         "response_node": q["response_node"],
                         "response_dof": q["response_dof"], "U": finite(U)})
        DIAG.setdefault("harmonic_refinement", []).append(hist)
        try:
            Df = fe_harmonic(fr, om, int(q["load_node"]) - 1, dofs[q["load_dof"]],
                             float(q["amplitude"]))
            Uf = Df[int(q["response_node"]) - 1, dofs[q["response_dof"]]]
            DIAG.setdefault("harmonic_vs_fe", []).append(
                [float(U), float(Uf), float(abs(U - Uf) / max(abs(U), 1e-300))])
        except Exception as exc:
            DIAG.setdefault("harmonic_vs_fe", []).append(repr(exc))

    rep = {"frame_id": raw["frame_id"], "static": static_out, "frequencies_Hz": freqs,
           "count_below": int(cnt), "harmonic": harm_out}
    txt = json.dumps(rep, indent=2, allow_nan=False)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    if diag_path:
        with open(diag_path, "w", encoding="utf-8") as f:
            json.dump(DIAG, f, indent=1, default=float)
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--frame", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--diag", default=None)
    a = ap.parse_args(argv)
    run(a.frame, a.output, a.diag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
