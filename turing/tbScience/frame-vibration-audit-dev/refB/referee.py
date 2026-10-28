#!/usr/bin/env python3
"""
Reference B: independent referee for FRAME_SPEC (plane frames: exact statics, natural frequencies of
Euler-Bernoulli frames with distributed and lumped mass, undamped harmonic response).

Method (shares nothing with closed-form dynamic stiffness):
  * statics: classical 2-node frame element (linear axial + cubic Hermite bending) with exact
    fixed-end actions, cross-checked on split meshes and on the dynamic mesh at omega = 0;
  * dynamics: conforming finite elements (cubic Hermite bending, cubic Lagrange axial with two
    internal nodes, consistent mass, lumped nodal masses) on nested meshes n_k * 2^l, longdouble
    deformation-based operators (refined subspace step + Rayleigh-Ritz, iteratively refined
    solves), Richardson (Romberg) extrapolation in h^4, h^6, h^8, ...; counts by Sylvester inertia.

Usage:
  python referee.py --frame F.json --report R.json [--out verdict.json] [--quiet]
  python referee.py --solve --frame F.json --output R.json [--out diagnostics.json] [--quiet]
Exit status: 0 = pass (or solve succeeded), 1 = fail, 2 = referee cannot certify / input error.
"""
import argparse
import json
import math
import os
import stat
import sys
import time
import math
from fractions import Fraction
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.sparse.csgraph import reverse_cuthill_mckee

LD = np.longdouble
PI_LD = 4 * np.arctan(LD(1))


# ----------------------------------------------------------------------------------------------
# Exact element matrices (rational arithmetic)
# ----------------------------------------------------------------------------------------------
def _pmul(a, b):
    r = [Fraction(0)] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            r[i + j] += x * y
    return r


def _pder(a):
    return [i * a[i] for i in range(1, len(a))] or [Fraction(0)]


def _pint01(a):
    return sum(c / (i + 1) for i, c in enumerate(a))


def _lagrange(z):
    basis = []
    for i, zi in enumerate(z):
        p = [Fraction(1)]
        for j, zj in enumerate(z):
            if j != i:
                p = _pmul(p, [-zj / (zi - zj), Fraction(1) / (zi - zj)])
        basis.append(p)
    return basis


def _gram(funcs, der):
    fs = funcs
    for _ in range(der):
        fs = [_pder(f) for f in fs]
    n = len(fs)
    return [[_pint01(_pmul(fs[i], fs[j])) for j in range(n)] for i in range(n)]


_HERM = [[Fraction(c) for c in p] for p in ([1, 0, -3, 2], [0, 1, -2, 1], [0, 0, 3, -2], [0, 0, -1, 1])]
_LAG3 = _lagrange([Fraction(0), Fraction(1, 3), Fraction(2, 3), Fraction(1)])
_LAG1 = _lagrange([Fraction(0), Fraction(1)])

KB_HAT_F = _gram(_HERM, 2)   # int phi_i'' phi_j''  (rotational shape functions without the h factor)
MB_HAT_F = _gram(_HERM, 0)
KA3_HAT_F = _gram(_LAG3, 1)  # nodes xi = 0, 1/3, 2/3, 1
MA3_HAT_F = _gram(_LAG3, 0)
KA1_HAT_F = _gram(_LAG1, 1)
MA1_HAT_F = _gram(_LAG1, 0)


def _ld(mat):
    return np.array([[LD(x.numerator) / LD(x.denominator) for x in row] for row in mat], dtype=LD)


KB_HAT = _ld(KB_HAT_F)
MB_HAT = _ld(MB_HAT_F)
KA3_HAT = _ld(KA3_HAT_F)
MA3_HAT = _ld(MA3_HAT_F)
KA1_HAT = _ld(KA1_HAT_F)
MA1_HAT = _ld(MA1_HAT_F)


def _chol_ld(A):
    n = A.shape[0]
    Lm = np.zeros_like(A)
    for j in range(n):
        s = A[j, j] - np.dot(Lm[j, :j], Lm[j, :j])
        if not s > 0:
            raise np.linalg.LinAlgError("matrix not positive definite")
        Lm[j, j] = np.sqrt(s)
        for i in range(j + 1, n):
            Lm[i, j] = (A[i, j] - np.dot(Lm[i, :j], Lm[j, :j])) / Lm[j, j]
    return Lm


# axial strain coordinates: K3 = KA3_HAT[1:,1:] (relative displacements q1-u1, q2-u1, u2-u1)
KA3_RED_CHOL_T = _chol_ld(KA3_HAT[1:, 1:]).T.copy()
SQRT3_2 = np.sqrt(LD(3)) / 2

# local DOF layouts
AX3 = [0, 6, 7, 3]   # u1, q1, q2, u2  (xi = 0, 1/3, 2/3, 1)
AX1 = [0, 3]
BEND = [1, 2, 4, 5]  # v1, t1, v2, t2


# ----------------------------------------------------------------------------------------------
# Frame geometry
# ----------------------------------------------------------------------------------------------
class FrameModel:
    def __init__(self, frame):
        self.frame = frame
        nodes = frame["nodes"]
        mem = frame["members"]
        self.N = len(nodes)
        self.xy = np.array([[LD(float(n["x"])), LD(float(n["y"]))] for n in nodes], dtype=LD)
        self.mass = np.array([LD(float(n["mass_kg"])) for n in nodes], dtype=LD)
        self.fixed = np.array([[bool(n["support"][d]) for d in ("ux", "uy", "rz")] for n in nodes])
        self.M = len(mem)
        self.mi = np.array([m["i"] - 1 for m in mem], dtype=int)
        self.mj = np.array([m["j"] - 1 for m in mem], dtype=int)
        d = self.xy[self.mj] - self.xy[self.mi]
        self.L = np.sqrt(d[:, 0] ** 2 + d[:, 1] ** 2)
        self.c = d[:, 0] / self.L
        self.s = d[:, 1] / self.L
        self.E = np.array([LD(float(m["E"])) for m in mem], dtype=LD)
        self.A = np.array([LD(float(m["A"])) for m in mem], dtype=LD)
        self.I = np.array([LD(float(m["I"])) for m in mem], dtype=LD)
        self.rho = np.array([LD(float(m["rho"])) for m in mem], dtype=LD)
        self.EA = self.E * self.A
        self.EI = self.E * self.I
        self.rhoA = self.rho * self.A

    def lam(self, omega):
        """bending parameter lambda_k = L (rho A omega^2 / EI)^(1/4) for every member"""
        omega = LD(omega)
        return self.L * np.sqrt(np.sqrt(self.rhoA * omega * omega / self.EI))

    def alp(self, omega):
        return LD(omega) * self.L * np.sqrt(self.rho / self.E)


# ----------------------------------------------------------------------------------------------
# Mesh: n_k elements on member k; axial order 3 (cubic Lagrange, 2 internal DOFs) or 1 (linear)
# ----------------------------------------------------------------------------------------------
class Mesh:
    def __init__(self, fm, counts, axial_order=3):
        self.fm = fm
        self.order = axial_order
        self.ndl = 8 if axial_order == 3 else 6
        counts = [int(n) for n in counts]
        self.counts = counts
        nn = fm.N
        el_nodes, el_mem, el_int = [], [], []
        nint_ax = 0
        for k in range(fm.M):
            n = counts[k]
            chain = [fm.mi[k]] + list(range(nn, nn + n - 1)) + [fm.mj[k]]
            nn += n - 1
            for e in range(n):
                el_nodes.append((chain[e], chain[e + 1]))
                el_mem.append(k)
        self.n_fe_nodes = nn
        ne = len(el_nodes)
        self.ne = ne
        el_nodes = np.array(el_nodes, dtype=int)
        el_mem = np.array(el_mem, dtype=int)
        self.el_mem = el_mem
        ndof = 3 * nn
        dofs = np.zeros((ne, self.ndl), dtype=int)
        dofs[:, 0:3] = 3 * el_nodes[:, [0]] + np.arange(3)
        dofs[:, 3:6] = 3 * el_nodes[:, [1]] + np.arange(3)
        if axial_order == 3:
            dofs[:, 6] = ndof + 2 * np.arange(ne)
            dofs[:, 7] = ndof + 2 * np.arange(ne) + 1
            ndof += 2 * ne
        self.ndof_full = ndof
        self.dofs = dofs
        free = np.ones(ndof, dtype=bool)
        fx = fm.fixed.reshape(-1)
        free[: 3 * fm.N] = ~fx
        self.free = free
        self.red = -np.ones(ndof, dtype=int)
        self.red[free] = np.arange(free.sum())
        self.n = int(free.sum())
        # element data (longdouble)
        self.h = fm.L[el_mem] / np.array([LD(counts[k]) for k in el_mem], dtype=LD)
        self.c = fm.c[el_mem]
        self.s = fm.s[el_mem]
        self.EA = fm.EA[el_mem]
        self.EI = fm.EI[el_mem]
        self.rhoA = fm.rhoA[el_mem]
        # scatter matrix (full dofs x element dofs)
        cols = np.arange(ne * self.ndl)
        self.S = sp.csr_matrix((np.ones(ne * self.ndl, dtype=LD), (dofs.reshape(-1), cols)),
                               shape=(ndof, ne * self.ndl))
        # nodal masses on frame-node translations
        md = []
        mv = []
        for p in range(fm.N):
            if fm.mass[p] != 0:
                for d in (0, 1):
                    md.append(3 * p + d)
                    mv.append(fm.mass[p])
        self.mass_dofs = np.array(md, dtype=int)
        self.mass_vals = np.array(mv, dtype=LD)
        self._K = None
        self._M = None

    # ---------------- double-precision sparse matrices (reduced) ----------------
    def local_mats(self, dtype=float):
        ne, ndl = self.ne, self.ndl
        h = self.h.astype(dtype)
        k = np.zeros((ne, ndl, ndl), dtype=dtype)
        m = np.zeros((ne, ndl, ndl), dtype=dtype)
        ax = AX3 if self.order == 3 else AX1
        Ka = (KA3_HAT if self.order == 3 else KA1_HAT).astype(dtype)
        Ma = (MA3_HAT if self.order == 3 else MA1_HAT).astype(dtype)
        ea = (self.EA.astype(dtype) / h)[:, None, None]
        ra = (self.rhoA.astype(dtype) * h)[:, None, None]
        k[np.ix_(np.arange(ne), ax, ax)] += ea * Ka[None]
        m[np.ix_(np.arange(ne), ax, ax)] += ra * Ma[None]
        sc = np.stack([np.ones_like(h), h, np.ones_like(h), h], axis=1)
        ss = sc[:, :, None] * sc[:, None, :]
        ei = (self.EI.astype(dtype) / h ** 3)[:, None, None]
        k[np.ix_(np.arange(ne), BEND, BEND)] += ei * KB_HAT.astype(dtype)[None] * ss
        m[np.ix_(np.arange(ne), BEND, BEND)] += ra * MB_HAT.astype(dtype)[None] * ss
        return k, m

    def transforms(self, dtype=float):
        ne, ndl = self.ne, self.ndl
        T = np.zeros((ne, ndl, ndl), dtype=dtype)
        c = self.c.astype(dtype)
        s = self.s.astype(dtype)
        for b in (0, 3):
            T[:, b, b] = c
            T[:, b, b + 1] = s
            T[:, b + 1, b] = -s
            T[:, b + 1, b + 1] = c
            T[:, b + 2, b + 2] = 1
        for b in range(6, ndl):
            T[:, b, b] = 1
        return T

    def assemble(self):
        if self._K is not None:
            return self._K, self._M
        k, m = self.local_mats(float)
        T = self.transforms(float)
        Kg = np.einsum("eji,ejk,ekl->eil", T, k, T)
        Mg = np.einsum("eji,ejk,ekl->eil", T, m, T)
        r = self.red[self.dofs]
        rows = np.broadcast_to(r[:, :, None], Kg.shape).reshape(-1)
        cols = np.broadcast_to(r[:, None, :], Kg.shape).reshape(-1)
        ok = (rows >= 0) & (cols >= 0)
        n = self.n
        K = sp.coo_matrix((Kg.reshape(-1)[ok], (rows[ok], cols[ok])), shape=(n, n)).tocsc()
        Mv = Mg.reshape(-1)[ok]
        mr, mc = rows[ok], cols[ok]
        rd = self.red[self.mass_dofs] if len(self.mass_dofs) else np.zeros(0, int)
        okm = rd >= 0
        Mv = np.concatenate([Mv, self.mass_vals[okm].astype(float)])
        mr = np.concatenate([mr, rd[okm]])
        mc = np.concatenate([mc, rd[okm]])
        M = sp.coo_matrix((Mv, (mr, mc)), shape=(n, n)).tocsc()
        K = ((K + K.T) * 0.5).tocsc()
        M = ((M + M.T) * 0.5).tocsc()
        self._K, self._M = K, M
        return K, M

    # ---------------- longdouble operators (reduced vectors, shape (n, k)) ----------------
    def _embed(self, x):
        x = np.asarray(x, dtype=LD)
        one = x.ndim == 1
        if one:
            x = x[:, None]
        full = np.zeros((self.ndof_full, x.shape[1]), dtype=LD)
        full[self.free] = x
        return full, one

    def _local(self, full):
        xe = full[self.dofs]  # (ne, ndl, k)
        c = self.c[:, None]
        s = self.s[:, None]
        ql = np.empty_like(xe)
        for b in (0, 3):
            ql[:, b] = c * xe[:, b] + s * xe[:, b + 1]
            ql[:, b + 1] = -s * xe[:, b] + c * xe[:, b + 1]
            ql[:, b + 2] = xe[:, b + 2]
        if self.ndl == 8:
            ql[:, 6:8] = xe[:, 6:8]
        return ql

    def _to_global_scatter(self, fl):
        c = self.c[:, None]
        s = self.s[:, None]
        fg = np.empty_like(fl)
        for b in (0, 3):
            fg[:, b] = c * fl[:, b] - s * fl[:, b + 1]
            fg[:, b + 1] = s * fl[:, b] + c * fl[:, b + 1]
            fg[:, b + 2] = fl[:, b + 2]
        if self.ndl == 8:
            fg[:, 6:8] = fl[:, 6:8]
        k = fg.shape[2]
        out = self.S @ fg.reshape(self.ne * self.ndl, k)
        return out

    def _deform(self, ql):
        h = self.h[:, None]
        psi = (ql[:, 4] - ql[:, 1]) / h
        a1 = ql[:, 2] - psi
        a2 = ql[:, 5] - psi
        if self.order == 3:
            u1 = ql[:, 0]
            d = np.stack([ql[:, 6] - u1, ql[:, 7] - u1, ql[:, 3] - u1], axis=1)  # (ne, 3, k)
        else:
            d = (ql[:, 3] - ql[:, 0])[:, None, :]
        return a1, a2, d

    def K_apply(self, x):
        full, one = self._embed(x)
        ql = self._local(full)
        a1, a2, d = self._deform(ql)
        h = self.h[:, None]
        eih = (self.EI[:, None] / h)
        M1 = eih * (4 * a1 + 2 * a2)
        M2 = eih * (2 * a1 + 4 * a2)
        V = (M1 + M2) / h
        fl = np.zeros_like(ql)
        fl[:, 1] = V
        fl[:, 2] = M1
        fl[:, 4] = -V
        fl[:, 5] = M2
        eah = (self.EA[:, None] / h)
        if self.order == 3:
            fa = np.einsum("ij,ejk->eik", KA3_HAT[:, 1:], d) * eah[:, None, :]
            for t, idx in enumerate(AX3):
                fl[:, idx] += fa[:, t]
        else:
            N = eah * d[:, 0]
            fl[:, 0] += -N
            fl[:, 3] += N
        out = self._to_global_scatter(fl)[self.free]
        return out[:, 0] if one else out

    def M_apply(self, x):
        full, one = self._embed(x)
        ql = self._local(full)
        h = self.h[:, None]
        rah = self.rhoA[:, None] * h
        fl = np.zeros_like(ql)
        w = np.stack([ql[:, 1], h * ql[:, 2], ql[:, 4], h * ql[:, 5]], axis=1)
        fw = np.einsum("ij,ejk->eik", MB_HAT, w) * rah[:, None, :]
        fl[:, 1] = fw[:, 0]
        fl[:, 2] = h * fw[:, 1]
        fl[:, 4] = fw[:, 2]
        fl[:, 5] = h * fw[:, 3]
        ax = AX3 if self.order == 3 else AX1
        Ma = MA3_HAT if self.order == 3 else MA1_HAT
        ua = np.stack([ql[:, i] for i in ax], axis=1)
        fa = np.einsum("ij,ejk->eik", Ma, ua) * rah[:, None, :]
        for t, idx in enumerate(ax):
            fl[:, idx] += fa[:, t]
        out = self._to_global_scatter(fl)
        if len(self.mass_dofs):
            out[self.mass_dofs] += self.mass_vals[:, None] * full[self.mass_dofs]
        out = out[self.free]
        return out[:, 0] if one else out

    def strain_coords(self, x):
        """G such that x^T K y = G(x) . G(y); returned shape (ne*nd, k)"""
        full, one = self._embed(x)
        ql = self._local(full)
        a1, a2, d = self._deform(ql)
        h = self.h[:, None]
        sb = np.sqrt(4 * self.EI[:, None] / h)
        g = [sb * (a1 + a2 / 2), sb * SQRT3_2 * a2]
        sa = np.sqrt(self.EA[:, None] / h)
        if self.order == 3:
            gd = np.einsum("ij,ejk->eik", KA3_RED_CHOL_T, d)
            for t in range(3):
                g.append(sa * gd[:, t])
        else:
            g.append(sa * d[:, 0])
        G = np.concatenate(g, axis=0)
        return G


# ----------------------------------------------------------------------------------------------
# Linear algebra helpers
# ----------------------------------------------------------------------------------------------
def solve_refined(lu, apply_ld, b, iters=4):
    b = np.asarray(b, dtype=LD)
    x = lu.solve(np.ascontiguousarray(b.astype(float))).astype(LD)
    last = None
    for _ in range(iters):
        r = b - apply_ld(x)
        dx = lu.solve(np.ascontiguousarray(r.astype(float))).astype(LD)
        x = x + dx
        nx = np.max(np.abs(x)) if x.size else LD(0)
        last = float(np.max(np.abs(dx)) / nx) if nx > 0 else 0.0
    return x, last


def jacobi_ld(C, maxsweep=60):
    C = np.array(C, dtype=LD)
    n = C.shape[0]
    V = np.eye(n, dtype=LD)
    for _ in range(maxsweep):
        off = np.sqrt(np.sum(np.triu(C, 1) ** 2))
        nrm = np.sqrt(np.sum(C ** 2))
        if off <= LD(1e-34) * nrm:
            break
        for p in range(n - 1):
            for q in range(p + 1, n):
                apq = C[p, q]
                if apq == 0:
                    continue
                theta = (C[q, q] - C[p, p]) / (2 * apq)
                t = (LD(1) if theta >= 0 else LD(-1)) / (abs(theta) + np.sqrt(theta * theta + 1))
                cs = 1 / np.sqrt(t * t + 1)
                sn = t * cs
                cp = C[:, p].copy()
                cq = C[:, q].copy()
                C[:, p] = cs * cp - sn * cq
                C[:, q] = sn * cp + cs * cq
                rp = C[p, :].copy()
                rq = C[q, :].copy()
                C[p, :] = cs * rp - sn * rq
                C[q, :] = sn * rp + cs * rq
                vp = V[:, p].copy()
                vq = V[:, q].copy()
                V[:, p] = cs * vp - sn * vq
                V[:, q] = sn * vp + cs * vq
    w = np.diag(C).copy()
    o = np.argsort(w.astype(float), kind="stable")
    return w[o], V[:, o]


def gen_eig_ld(A, B):
    Lc = _chol_ld(B)
    n = A.shape[0]
    Li = np.zeros_like(Lc)
    for j in range(n):
        e = np.zeros(n, dtype=LD)
        e[j] = 1
        y = np.zeros(n, dtype=LD)
        for i in range(n):
            y[i] = (e[i] - np.dot(Lc[i, :i], y[:i])) / Lc[i, i]
        Li[:, j] = y
    C = Li @ A @ Li.T
    C = (C + C.T) / 2
    w, V = jacobi_ld(C)
    Y = Li.T @ V
    return w, Y


def inertia(A_csc, ordering="mmd"):
    """number of negative eigenvalues of symmetric A via LDL^T (SuperLU, diagonal pivoting)"""
    if ordering == "mmd":
        lu = spla.splu(A_csc, permc_spec="MMD_AT_PLUS_A", diag_pivot_thresh=0.0,
                       options=dict(SymmetricMode=True))
    else:
        p = reverse_cuthill_mckee(A_csc.tocsr(), symmetric_mode=True)
        Ap = A_csc[p][:, p].tocsc()
        lu = spla.splu(Ap, permc_spec="NATURAL", diag_pivot_thresh=0.0,
                       options=dict(SymmetricMode=True))
    if not np.array_equal(lu.perm_r, lu.perm_c):
        raise RuntimeError("inertia: off-diagonal pivoting occurred")
    d = lu.U.diagonal()
    if np.any(d == 0) or not np.all(np.isfinite(d)):
        raise RuntimeError("inertia: zero pivot")
    return int(np.sum(d < 0)), float(np.min(np.abs(d)) / np.max(np.abs(d)))


def romberg(vals, p0=4, dp=2, jmax=4):
    """vals: list of longdouble values on meshes t, t/2, t/4 ...; expansion c_p t^p, p = p0, p0+dp, ...
    (at most jmax elimination columns: h^4, h^6, h^8, h^10)"""
    n = len(vals)
    T = [[LD(v)] for v in vals]
    for i in range(1, n):
        for j in range(1, min(i, jmax) + 1):
            p = p0 + dp * (j - 1)
            f = LD(2) ** p - 1
            T[i].append(T[i][j - 1] + (T[i][j - 1] - T[i - 1][j - 1]) / f)
    best = T[-1][-1]
    if n >= 2:
        unc = max(abs(T[-1][-1] - T[-2][-2]), abs(T[-1][-1] - T[-1][-2]))
    else:
        unc = LD("inf")
    return best, unc, T


def observed_orders(vals):
    out = []
    for i in range(len(vals) - 2):
        d1 = vals[i] - vals[i + 1]
        d2 = vals[i + 1] - vals[i + 2]
        if d1 != 0 and d2 != 0 and (d1 > 0) == (d2 > 0):
            out.append(float(np.log2(abs(d1 / d2))))
        else:
            out.append(float("nan"))
    return out


# ----------------------------------------------------------------------------------------------
# Eigenpairs on one mesh: double shift-invert Lanczos, then longdouble refined subspace step and
# Rayleigh-Ritz with deformation-based (exact rigid-body null space) stiffness form
# ----------------------------------------------------------------------------------------------
def level_eigs(mesh, k, refine_steps=2):
    import scipy.linalg as sla
    K, M = mesh.assemble()
    n = K.shape[0]
    k = min(k, n - 2)
    lu = spla.splu(K)
    if n <= max(80, 4 * k):
        vals, X = sla.eigh(K.toarray(), M.toarray())
        vals = vals[:k]
        X = X[:, :k]
    else:
        op = spla.LinearOperator(K.shape, matvec=lu.solve, dtype=float)
        v0 = np.random.default_rng(12345).standard_normal(n)
        ncv = min(n - 1, max(2 * k + 1, k + 24))
        try:
            vals, X = spla.eigsh(K, k=k, M=M, sigma=0.0, OPinv=op, which="LM", tol=1e-12, ncv=ncv,
                                 v0=v0, maxiter=50000)
        except spla.ArpackNoConvergence:
            vals, X = spla.eigsh(K, k=k, M=M, sigma=0.0, OPinv=op, which="LM", tol=1e-10,
                                 ncv=min(n - 1, 4 * k + 40), v0=v0, maxiter=200000)
        o = np.argsort(vals)
        vals = vals[o]
        X = X[:, o]
    Y = X.astype(LD)
    for _ in range(refine_steps):
        Z = mesh.M_apply(Y)
        Y, _ = solve_refined(lu, mesh.K_apply, Z, iters=3)
        Y = Y / np.max(np.abs(Y), axis=0)
    G = mesh.strain_coords(Y)
    A = G.T @ G
    B = Y.T @ mesh.M_apply(Y)
    w, W = gen_eig_ld(A, B)
    return w, vals, lu


def near_eigs(K, M, sigma, k):
    n = K.shape[0]
    k = min(k, n - 2)
    v0 = np.random.default_rng(54321).standard_normal(n)
    vals = spla.eigsh(K, k=k, M=M, sigma=sigma, which="LM", tol=1e-13, v0=v0,
                      ncv=min(n - 1, max(2 * k + 1, 30)), maxiter=50000, return_eigenvectors=False)
    return np.sort(vals)


def count_below(K, M, sigma, both=False):
    A = (K - sigma * M).tocsc()
    out = {}
    for ordering in (("mmd", "rcm") if both else ("mmd",)):
        try:
            out[ordering] = inertia(A, ordering)[0]
        except Exception as e:  # noqa: BLE001
            out[ordering] = None
            out[ordering + "_error"] = str(e)
    vals = [v for kk, v in out.items() if not kk.endswith("_error") and v is not None]
    if not vals:
        import scipy.linalg as sla
        if A.shape[0] > 6000:
            raise RuntimeError("inertia failed: %s" % out)
        lu_, d_, _ = sla.ldl(A.toarray())
        ev = np.linalg.eigvalsh(d_)
        out["dense"] = int(np.sum(ev < 0))
        vals = [out["dense"]]
    if len(set(vals)) != 1:
        raise RuntimeError("inertia orderings disagree: %s" % out)
    return vals[0], out


# ----------------------------------------------------------------------------------------------
# Strict JSON and schema
# ----------------------------------------------------------------------------------------------
class _DupKey(ValueError):
    pass


def _pairs(pairs):
    d = {}
    for kk, v in pairs:
        if kk in d:
            raise _DupKey("duplicate key %r" % kk)
        d[kk] = v
    return d


def _bad_const(x):
    raise ValueError("non-finite constant %s" % x)


def _walk_nonfinite(o):
    if isinstance(o, float):
        return not math.isfinite(o)
    if isinstance(o, dict):
        return any(_walk_nonfinite(v) for v in o.values())
    if isinstance(o, list):
        return any(_walk_nonfinite(v) for v in o)
    return False


def load_json_strict(path):
    try:
        st = os.lstat(path)
    except OSError as e:
        return None, ["cannot stat %s: %s" % (path, e)]
    if stat.S_ISLNK(st.st_mode):
        return None, ["is a symbolic link"]
    if not stat.S_ISREG(st.st_mode):
        return None, ["not a regular file"]
    if st.st_size == 0:
        return None, ["empty file"]
    if st.st_size > 1000000:
        return None, ["larger than 1 MB (%d bytes)" % st.st_size]
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, ["not UTF-8"]
    try:
        obj = json.loads(txt, object_pairs_hook=_pairs, parse_constant=_bad_const)
    except _DupKey as e:
        return None, [str(e)]
    except ValueError as e:
        return None, ["invalid JSON: %s" % e]
    if _walk_nonfinite(obj):
        return None, ["non-finite number"]
    return obj, []


def _num(x):
    return type(x) in (int, float) and math.isfinite(x)


def _int(x):
    return type(x) is int


DOFS = ("ux", "uy", "rz")


def validate_frame(fr):
    """returns (fatal problems, warnings) for sections 2 and 3"""
    fat, war = [], []
    keys = {"frame_id", "nodes", "members", "nodal_loads", "member_loads", "static_query_nodes",
            "n_modes", "f_max_Hz", "harmonic_queries"}
    if not isinstance(fr, dict):
        return ["frame is not an object"], war
    if set(fr) != keys:
        (fat if not keys <= set(fr) else war).append("frame keys %s" % sorted(set(fr) ^ keys))
    if not keys <= set(fr):
        return fat, war
    fid = fr["frame_id"]
    import re
    if not (isinstance(fid, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", fid)):
        war.append("frame_id format")
    nodes, mems = fr["nodes"], fr["members"]
    if not isinstance(nodes, list) or not isinstance(mems, list):
        return fat + ["nodes/members not lists"], war
    N, M = len(nodes), len(mems)
    if not 2 <= N <= 12:
        war.append("domain: %d nodes" % N)
    if not 1 <= M <= 16:
        war.append("domain: %d members" % M)
    for p, nd in enumerate(nodes):
        if not isinstance(nd, dict) or set(nd) != {"id", "x", "y", "mass_kg", "support"}:
            fat.append("node %d keys" % (p + 1))
            continue
        if nd["id"] != p + 1 or not _int(nd["id"]):
            fat.append("node %d id" % (p + 1))
        for kk in ("x", "y", "mass_kg"):
            if not _num(nd[kk]):
                fat.append("node %d %s" % (p + 1, kk))
        sup = nd["support"]
        if not isinstance(sup, dict) or set(sup) != set(DOFS) or any(type(sup[d]) is not bool for d in DOFS):
            fat.append("node %d support" % (p + 1))
        if _num(nd["x"]) and _num(nd["y"]) and not (-30 <= nd["x"] <= 30 and -30 <= nd["y"] <= 30):
            war.append("domain: node %d coordinates" % (p + 1))
        if _num(nd["mass_kg"]) and not 0 <= nd["mass_kg"] <= 5e4:
            war.append("domain: node %d mass" % (p + 1))
    rng = {"E": (2e10, 2.1e11), "A": (1e-4, 5e-2), "I": (1e-7, 5e-3), "rho": (1500, 8000)}
    for k, m in enumerate(mems):
        if not isinstance(m, dict) or set(m) != {"id", "i", "j", "E", "A", "I", "rho"}:
            fat.append("member %d keys" % (k + 1))
            continue
        if m["id"] != k + 1 or not _int(m["id"]):
            fat.append("member %d id" % (k + 1))
        if not (_int(m["i"]) and _int(m["j"]) and 1 <= m["i"] <= N and 1 <= m["j"] <= N and m["i"] != m["j"]):
            fat.append("member %d ends" % (k + 1))
            continue
        for kk, (lo, hi) in rng.items():
            if not _num(m[kk]) or m[kk] <= 0:
                fat.append("member %d %s" % (k + 1, kk))
            elif not lo <= m[kk] <= hi:
                war.append("domain: member %d %s=%g" % (k + 1, kk, m[kk]))
        if not fat:
            a, b = nodes[m["i"] - 1], nodes[m["j"] - 1]
            L = math.hypot(b["x"] - a["x"], b["y"] - a["y"])
            if not 0.5 <= L <= 20:
                (fat if L == 0 else war).append("domain: member %d length %.6g" % (k + 1, L))
    for q in fr["nodal_loads"] if isinstance(fr["nodal_loads"], list) else [None]:
        if not isinstance(q, dict) or set(q) != {"node", "Fx", "Fy", "Mz"} or not _int(q["node"]) \
                or not 1 <= q["node"] <= N or not all(_num(q[x]) for x in ("Fx", "Fy", "Mz")):
            fat.append("nodal_loads entry %r" % (q,))
            continue
        if max(abs(q["Fx"]), abs(q["Fy"]), abs(q["Mz"])) > 1e6:
            war.append("domain: nodal load magnitude")
    for q in fr["member_loads"] if isinstance(fr["member_loads"], list) else [None]:
        if not isinstance(q, dict) or set(q) != {"member", "wx", "wy"} or not _int(q["member"]) \
                or not 1 <= q["member"] <= M or not all(_num(q[x]) for x in ("wx", "wy")):
            fat.append("member_loads entry %r" % (q,))
            continue
        if max(abs(q["wx"]), abs(q["wy"])) > 1e5:
            war.append("domain: member load magnitude")
    sq = fr["static_query_nodes"]
    if not isinstance(sq, list) or not all(_int(x) and 1 <= x <= N for x in sq):
        fat.append("static_query_nodes")
    elif not 1 <= len(sq) <= 6:
        war.append("domain: %d static query nodes" % len(sq))
    if not _int(fr["n_modes"]) or fr["n_modes"] < 1:
        fat.append("n_modes")
    elif not 3 <= fr["n_modes"] <= 12:
        war.append("domain: n_modes=%d" % fr["n_modes"])
    if not _num(fr["f_max_Hz"]) or fr["f_max_Hz"] <= 0:
        fat.append("f_max_Hz")
    elif not 1 <= fr["f_max_Hz"] <= 500:
        war.append("domain: f_max_Hz=%g" % fr["f_max_Hz"])
    hq = fr["harmonic_queries"]
    hk = {"load_node", "load_dof", "amplitude", "f_Hz", "response_node", "response_dof"}
    if not isinstance(hq, list):
        fat.append("harmonic_queries")
    else:
        if not 1 <= len(hq) <= 4:
            war.append("domain: %d harmonic queries" % len(hq))
        for q in hq:
            if not isinstance(q, dict) or set(q) != hk or not _int(q["load_node"]) or not _int(q["response_node"]) \
                    or not 1 <= q["load_node"] <= N or not 1 <= q["response_node"] <= N \
                    or q["load_dof"] not in DOFS or q["response_dof"] not in DOFS \
                    or not _num(q["amplitude"]) or not _num(q["f_Hz"]) or q["f_Hz"] <= 0:
                fat.append("harmonic query %r" % (q,))
    return fat, war


def validate_report(rep, fr):
    """section 4, exactly; returns list of problems"""
    P = []
    keys = {"frame_id", "static", "frequencies_Hz", "count_below", "harmonic"}
    if not isinstance(rep, dict):
        return ["report is not a JSON object"]
    if set(rep) != keys:
        P.append("report keys differ: extra %s missing %s" % (sorted(set(rep) - keys), sorted(keys - set(rep))))
    if rep.get("frame_id") != fr["frame_id"] or not isinstance(rep.get("frame_id"), str):
        P.append("frame_id mismatch")
    st = rep.get("static")
    sq = fr["static_query_nodes"]
    if not isinstance(st, list) or len(st) != len(sq):
        P.append("static must be a list of %d objects" % len(sq))
    else:
        for q, (o, nd) in enumerate(zip(st, sq)):
            if not isinstance(o, dict) or set(o) != {"node", "ux", "uy", "rz"}:
                P.append("static[%d] keys" % q)
                continue
            if not (_int(o["node"]) and o["node"] == nd):
                P.append("static[%d].node is not %r" % (q, nd))
            for d in DOFS:
                if not _num(o[d]):
                    P.append("static[%d].%s not a finite number" % (q, d))
    fq = rep.get("frequencies_Hz")
    if not isinstance(fq, list) or len(fq) != fr["n_modes"] or not all(_num(x) for x in fq):
        P.append("frequencies_Hz must be a list of exactly %d finite numbers" % fr["n_modes"])
    if not _int(rep.get("count_below")):
        P.append("count_below not an integer")
    hm = rep.get("harmonic")
    hq = fr["harmonic_queries"]
    hk = ["load_node", "load_dof", "amplitude", "f_Hz", "response_node", "response_dof"]
    if not isinstance(hm, list) or len(hm) != len(hq):
        P.append("harmonic must be a list of %d objects" % len(hq))
    else:
        for q, (o, g) in enumerate(zip(hm, hq)):
            if not isinstance(o, dict) or set(o) != set(hk) | {"U"}:
                P.append("harmonic[%d] keys" % q)
                continue
            for kk in hk:
                a, b = o[kk], g[kk]
                if isinstance(b, str):
                    ok = a == b and isinstance(a, str)
                elif kk in ("load_node", "response_node"):
                    ok = _int(a) and a == b
                else:
                    ok = _num(a) and a == b
                if not ok:
                    P.append("harmonic[%d].%s is not %r" % (q, kk, b))
            if not _num(o["U"]):
                P.append("harmonic[%d].U not a finite number" % q)
    return P


# ----------------------------------------------------------------------------------------------
# Statics (classical element, exact fixed-end actions)
# ----------------------------------------------------------------------------------------------
def load_vector_static(mesh, frame):
    fm = mesh.fm
    F = np.zeros(mesh.ndof_full, dtype=LD)
    for nl in frame["nodal_loads"]:
        b = 3 * (int(nl["node"]) - 1)
        F[b] += LD(float(nl["Fx"]))
        F[b + 1] += LD(float(nl["Fy"]))
        F[b + 2] += LD(float(nl["Mz"]))
    if frame["member_loads"]:
        w = np.zeros((fm.M, 2), dtype=LD)
        for ml in frame["member_loads"]:
            k = int(ml["member"]) - 1
            w[k, 0] += LD(float(ml["wx"]))
            w[k, 1] += LD(float(ml["wy"]))
        wx, wy = w[mesh.el_mem, 0], w[mesh.el_mem, 1]
        c, s, h = mesh.c, mesh.s, mesh.h
        qa = wx * c + wy * s
        qt = -wx * s + wy * c
        fl = np.zeros((mesh.ne, mesh.ndl), dtype=LD)
        if mesh.order == 3:
            for t, idx in enumerate(AX3):
                fl[:, idx] = qa * h * (LD(1) / 8 if t in (0, 3) else LD(3) / 8)
        else:
            fl[:, 0] = qa * h / 2
            fl[:, 3] = qa * h / 2
        fl[:, 1] = qt * h / 2
        fl[:, 4] = qt * h / 2
        fl[:, 2] = qt * h * h / 12
        fl[:, 5] = -qt * h * h / 12
        fg = fl.copy()
        for b in (0, 3):
            fg[:, b] = c * fl[:, b] - s * fl[:, b + 1]
            fg[:, b + 1] = s * fl[:, b] + c * fl[:, b + 1]
        np.add.at(F, mesh.dofs, fg)
    return F


def static_solve(fm, frame, counts, order):
    mesh = Mesh(fm, counts, order)
    K, _ = mesh.assemble()
    F = load_vector_static(mesh, frame)
    lu = spla.splu(K)
    U, last = solve_refined(lu, mesh.K_apply, F[mesh.free], iters=6)
    full = np.zeros(mesh.ndof_full, dtype=LD)
    full[mesh.free] = U
    return full[: 3 * fm.N].reshape(fm.N, 3), K, last


# ----------------------------------------------------------------------------------------------
# Full analysis
# ----------------------------------------------------------------------------------------------
OPTS = dict(theta_b=2.0, theta_a=2.0, nmin=4, levels=5, max_levels=7, dof_cap=200000,
            unc_goal=1e-10, unc_refuse=1e-7, time_budget=150.0, pair_gap=1e-3)


def _dof_index(node, dof):
    return 3 * (int(node) - 1) + DOFS.index(dof)


def design_counts(fm, omega, opts):
    lam = fm.lam(omega)
    alp = fm.alp(omega)
    return [max(opts["nmin"], int(math.ceil(float(lam[k]) / opts["theta_b"])),
                int(math.ceil(float(alp[k]) / opts["theta_a"]))) for k in range(fm.M)]


def _groups(frame):
    """section 5 kinds. 'unit': translations (static ux, uy, harmonic ux/uy) vs rotations (static rz,
    harmonic rz). 'fine': static ux, static uy, static rz, harmonic translations, harmonic rotations."""
    items = []
    for q in range(len(frame["static_query_nodes"])):
        for d in DOFS:
            items.append(("static", q, d, "rot" if d == "rz" else "tr", "s_" + d))
    for q, hq in enumerate(frame["harmonic_queries"]):
        rd = hq["response_dof"]
        items.append(("harmonic", q, rd, "rot" if rd == "rz" else "tr", "h_rot" if rd == "rz" else "h_tr"))
    return items


UNC_FLOOR = LD(1e-15)
UNC_SAFETY = LD(10)  # u = 10 x (last two extrapolants); bounded every observed error (max ratio 6.9)


def _harm_unc_over_scale(frame, stat_vals, U, U_unc):
    """harmonic uncertainty divided by the section 5 scale max(|U|, S) with S over the unit group"""
    S = {"tr": LD(0), "rot": LD(0)}
    for row in stat_vals:
        S["tr"] = max(S["tr"], abs(row[0]), abs(row[1]))
        S["rot"] = max(S["rot"], abs(row[2]))
    grp = ["rot" if q["response_dof"] == "rz" else "tr" for q in frame["harmonic_queries"]]
    for g, u in zip(grp, U):
        S[g] = max(S[g], abs(u))
    out = []
    for g, u, du in zip(grp, U, U_unc):
        sc = max(abs(u), S[g])
        out.append(float(du / sc) if sc > 0 else 0.0)
    return out


def analyze(frame, opts=None, log=None):
    opts = dict(OPTS, **(opts or {}))
    t0 = time.time()
    say = log or (lambda *a: None)
    fm = FrameModel(frame)
    nm = int(frame["n_modes"])
    twopi = 2 * PI_LD
    om_max = twopi * LD(float(frame["f_max_Hz"]))
    sig = om_max * om_max
    hq = frame["harmonic_queries"]
    om_h = [twopi * LD(float(q["f_Hz"])) for q in hq]
    warn = []
    diag = {}

    # ---------------- statics ----------------
    D1, Kst, last1 = static_solve(fm, frame, [1] * fm.M, 1)
    split = {}
    for n in (8, 32):
        Dn, _, _ = static_solve(fm, frame, [n] * fm.M, 1)
        split["linear_axial_n%d" % n] = Dn
    Dd, _, _ = static_solve(fm, frame, [8] * fm.M, 3)
    split["cubic_axial_n8"] = Dd
    sq = frame["static_query_nodes"]
    stat_vals = [[D1[int(nd) - 1, d] for d in range(3)] for nd in sq]
    S_tr = max([abs(v) for row in stat_vals for v in row[:2]] + [LD(0)])
    S_rt = max([abs(row[2]) for row in stat_vals] + [LD(0)])
    split_dev = {}
    for kk, Dn in split.items():
        dv = 0.0
        for q, nd in enumerate(sq):
            for d in range(3):
                Sg = S_rt if d == 2 else S_tr
                if Sg > 0:
                    dv = max(dv, float(abs(Dn[int(nd) - 1, d] - D1[int(nd) - 1, d]) / Sg))
        split_dev[kk] = dv
    stat_unc = max(split_dev.values()) if split_dev else 0.0
    diag["static"] = {"split_max_dev_over_S": split_dev, "last_refinement_correction": last1}
    # guarantee 1: positive definiteness of the supported static stiffness
    try:
        ev = np.linalg.eigvalsh(Kst.toarray())
        diag["static"]["stiffness_eig_min_over_max"] = float(ev[0] / ev[-1])
        if not ev[0] > 0:
            warn.append("guarantee 1: static stiffness not positive definite (min eig %.3e)" % ev[0])
        np.linalg.cholesky(Kst.toarray())
    except np.linalg.LinAlgError:
        warn.append("guarantee 1: static stiffness Cholesky failed")
    say("statics done %.1fs split dev %s" % (time.time() - t0, {k: "%.1e" % v for k, v in split_dev.items()}))

    # ---------------- dynamic mesh design ----------------
    om_g = max([om_max] + om_h)
    kreq = nm + 3
    c_pre = design_counts(fm, om_g, opts)
    w_pre, vd_pre, _ = level_eigs(Mesh(fm, c_pre, 3), kreq, refine_steps=0)
    om_T = max(om_g, np.sqrt(LD(max(vd_pre[min(nm, len(vd_pre) - 1)], 0))))
    n0 = design_counts(fm, om_T, opts)
    diag["design"] = {"omega_T_Hz": float(om_T / twopi), "base_counts": n0,
                      "lambda_T": [float(x) for x in fm.lam(om_T)], "alpha_T": [float(x) for x in fm.alp(om_T)]}
    say("design f_T=%.4g Hz base counts %s" % (float(om_T / twopi), n0))

    levels = []

    def run_level(lv):
        tl = time.time()
        counts = [n * 2 ** lv for n in n0]
        mesh = Mesh(fm, counts, 3)
        K, M = mesh.assemble()
        w, vd, luK = level_eigs(mesh, kreq)
        rec = {"level": lv, "counts": counts, "dof": mesh.n, "ritz": w, "eigsh": vd}
        rec["ritz_vs_double_maxrel"] = float(np.max(np.abs((w[: len(vd)] - vd.astype(LD)) / w[: len(vd)])))
        # completeness of the computed lowest nm+1 eigenvalues (inertia between nm+1-th and nm+2-th)
        if len(w) >= nm + 2:
            mid = float((w[nm] + w[nm + 1]) / 2)
            cnt, _ = count_below(K, M, mid)
            rec["complete_check"] = (cnt, nm + 1)
        # harmonic responses
        hv = []
        for q, (g, om) in enumerate(zip(hq, om_h)):
            o2 = om * om
            A = (K - float(o2) * M).tocsc()
            luA = spla.splu(A)
            F = np.zeros(mesh.ndof_full, dtype=LD)
            F[_dof_index(g["load_node"], g["load_dof"])] = LD(float(g["amplitude"]))
            U, last = solve_refined(luA, lambda y: mesh.K_apply(y) - o2 * mesh.M_apply(y), F[mesh.free], 5)
            full = np.zeros(mesh.ndof_full, dtype=LD)
            full[mesh.free] = U
            hv.append(full[_dof_index(g["response_node"], g["response_dof"])])
        rec["harm"] = hv
        # count below f_max (Sylvester inertia) and eigenvalues nearest f_max
        rec["N_below"], rec["inertia"] = count_below(K, M, float(sig), both=False)
        nv = near_eigs(K, M, float(sig), 8)
        rec["near"] = {}
        b = nv[nv < float(sig)][::-1]
        a = nv[nv > float(sig)]
        for j, v in enumerate(b):
            rec["near"][rec["N_below"] - 1 - j] = v
        for j, v in enumerate(a):
            rec["near"][rec["N_below"] + j] = v
        rec["mesh"] = (K, M)
        rec["time"] = time.time() - tl
        say("level %d dof %d N_below %d t %.1fs" % (lv, mesh.n, rec["N_below"], rec["time"]))
        return rec

    for lv in range(opts["levels"]):
        levels.append(run_level(lv))

    def extrapolate():
        res = {}
        nf = nm + 1
        lam_best, lam_unc, lam_diag, orders = [], [], [], []
        for i in range(nf):
            seq = [r["ritz"][i] for r in levels]
            b, _, T = romberg(seq)
            lam_best.append(b)
            lam_unc.append(max(UNC_SAFETY * abs(T[-1][-1] - T[-1][-2]), UNC_FLOOR * abs(b)))
            lam_diag.append(abs(T[-1][-1] - T[-2][-2]))
            orders.append(observed_orders([float(x) for x in seq]) if False else observed_orders(seq))
        # pair-invariant cross-check for close pairs
        pairs = []
        for i in range(nf - 1):
            fa, fb = levels[-1]["ritz"][i], levels[-1]["ritz"][i + 1]
            if (fb - fa) / fa < opts["pair_gap"]:
                ssum = [r["ritz"][i] + r["ritz"][i + 1] for r in levels]
                dsq = [(r["ritz"][i + 1] - r["ritz"][i]) ** 2 for r in levels]
                s_inf, _, Ts = romberg(ssum)
                d_inf, _, Td = romberg(dsq)
                if d_inf < 0:
                    d_inf = LD(0)
                la = (s_inf - np.sqrt(d_inf)) / 2
                lb = (s_inf + np.sqrt(d_inf)) / 2
                dev = max(abs(la - lam_best[i]), abs(lb - lam_best[i + 1]))
                pairs.append({"i": i, "gap_rel": float((fb - fa) / fa), "dev_rel": float(dev / fa)})
                if dev > 3 * max(lam_unc[i], lam_unc[i + 1]):
                    lam_unc[i] = max(lam_unc[i], dev)
                    lam_unc[i + 1] = max(lam_unc[i + 1], dev)
                    pairs[-1]["widened"] = True
        f_best = [np.sqrt(x) / twopi for x in lam_best]
        f_unc = [float(u / x / 2) for u, x in zip(lam_unc, lam_best)]
        f_diag = [float(u / x / 2) for u, x in zip(lam_diag, lam_best)]
        res.update(lam=lam_best, f=f_best, f_unc=f_unc, f_unc_diag=f_diag, orders=orders, pairs=pairs)
        # irregular convergence -> fall back to the diagonal (conservative) estimate
        irregular = []
        for i in range(nf):
            seq = [r["ritz"][i] for r in levels]
            d = abs(seq[-2] - seq[-1]) / seq[-1]
            o = orders[i][-1] if orders[i] else float("nan")
            if d > 1e-13 and not (3.5 <= o <= 4.6 or 5.4 <= o <= 6.6):
                irregular.append(i)
                f_unc[i] = max(f_unc[i], f_diag[i])
        res["irregular"] = irregular
        # harmonic
        U_best, U_unc, U_ord = [], [], []
        for q in range(len(hq)):
            seq = [r["harm"][q] for r in levels]
            b, _, T = romberg(seq)
            u = max(UNC_SAFETY * abs(T[-1][-1] - T[-1][-2]), UNC_FLOOR * max(abs(x) for x in seq))
            o = observed_orders(seq)
            d = abs(seq[-2] - seq[-1]) / max(abs(seq[-1]), LD(1e-300))
            if d > 1e-13 and o and not (3.5 <= o[-1] <= 4.6 or 5.4 <= o[-1] <= 6.6):
                u = max(u, abs(T[-1][-1] - T[-2][-2]))
            U_best.append(b)
            U_unc.append(u)
            U_ord.append(o)
        res.update(U=U_best, U_unc=U_unc, U_orders=U_ord)
        return res

    res = extrapolate()

    def worst_unc(r):
        fu = max(r["f_unc"]) if r["f_unc"] else 0.0
        return max([fu] + _harm_unc_over_scale(frame, stat_vals, r["U"], r["U_unc"]))

    while worst_unc(res) > opts["unc_goal"] and len(levels) < opts["max_levels"]:
        nxt = sum(levels[-1]["counts"]) * 2 * 5
        el = time.time() - t0
        if nxt > opts["dof_cap"] or el + 2.5 * levels[-1]["time"] > opts["time_budget"]:
            break
        levels.append(run_level(len(levels)))
        res = extrapolate()

    # ---------------- count below f_max ----------------
    fin = levels[-1]
    Kf, Mf = fin["mesh"]
    N_L, inert = count_below(Kf, Mf, float(sig), both=True)
    count = N_L
    crossings = []
    cnt_info = {"N_finest": N_L, "inertia_orderings": inert, "N_by_level": [r["N_below"] for r in levels]}

    def extrap_index(g):
        seq = [r["near"].get(g) for r in levels[-3:]]
        if any(v is None for v in seq):
            return None, None
        b, _, T = romberg([LD(v) for v in seq])
        return b, abs(T[-1][-1] - T[-1][-2])

    g = N_L
    while True:
        b, u = extrap_index(g)
        if b is None or not b <= sig:
            break
        crossings.append(g)
        count += 1
        g += 1
    up, uu = extrap_index(count)
    dn, du = extrap_index(count - 1) if count >= 1 else (None, None)
    seps = {}
    if up is not None:
        seps["above_rel_f"] = float(np.sqrt(up / sig) - 1)
    if dn is not None:
        seps["below_rel_f"] = float(1 - np.sqrt(dn / sig))
    if fin["near"].get(count) is not None:
        seps["finest_fe_above_rel_f"] = float(np.sqrt(LD(fin["near"][count]) / sig) - 1)
        if len(levels) >= 2 and levels[-2]["near"].get(count) is not None:
            e = (levels[-2]["near"][count] - fin["near"][count]) / 15 / fin["near"][count]
            seps["finest_fe_err_est_rel_lam"] = float(e)
    cnt_info.update(crossings=crossings, separations=seps)
    if up is None:
        warn.append("count: eigenvalue above f_max not tracked across the last three levels")
    for kk in ("above_rel_f", "below_rel_f"):
        if kk in seps and seps[kk] < 1e-6:
            warn.append("guarantee 2: f_max within %.2e relative of a natural frequency" % seps[kk])
    if crossings:
        warn.append("count: %d FE eigenvalue(s) above f_max at the finest mesh extrapolate below it" % len(crossings))

    # ---------------- domain warnings ----------------
    f = res["f"]
    for i in range(nm):
        if (f[i + 1] - f[i]) / f[i] < 1e-6:
            warn.append("guarantee 2: frequencies %d and %d separated by %.2e relative" % (i, i + 1, float((f[i + 1] - f[i]) / f[i])))
    for q, om in enumerate(om_h):
        nv = near_eigs(Kf, Mf, float(om * om), 3)
        fe_f = np.sqrt(np.abs(nv)) / float(twopi)
        fh = float(hq[q]["f_Hz"])
        sep = float(np.min(np.abs(fe_f - fh) / fe_f))
        allf = [float(x) for x in f]
        sep = min(sep, min(abs(x - fh) / x for x in allf))
        if sep < 1e-2:
            warn.append("guarantee 2: harmonic query %d f_Hz within %.2e relative of a natural frequency" % (q, sep))
    om3 = max([twopi * f[nm - 1], om_max] + om_h)
    lam3 = fm.lam(om3)
    alp3 = fm.alp(om3)
    if float(np.max(lam3)) > 40 or float(np.max(alp3)) > 40:
        warn.append("guarantee 3: max lambda %.3f, max alpha %.3f" % (float(np.max(lam3)), float(np.max(alp3))))
    for r in levels:
        if "complete_check" in r and r["complete_check"][0] != r["complete_check"][1]:
            warn.append("lowest-eigenvalue completeness check failed at level %d: %s" % (r["level"], r["complete_check"]))
    if res["irregular"]:
        warn.append("irregular convergence for modes %s (conservative uncertainty used)" % res["irregular"])
    # guarantee 4 with reference values
    vals = {}
    for kind, q, d, ug, fg in _groups(frame):
        v = stat_vals[q][DOFS.index(d)] if kind == "static" else res["U"][q]
        vals[(kind, q, d)] = (v, ug, fg)
    S_unit, S_fine = {}, {}
    for v, ug, fg in vals.values():
        S_unit[ug] = max(S_unit.get(ug, LD(0)), abs(v))
        S_fine[fg] = max(S_fine.get(fg, LD(0)), abs(v))
    for (kind, q, d), (v, ug, fg) in vals.items():
        if abs(v) < LD(1e-9) * S_unit[ug]:
            warn.append("guarantee 4: %s[%d].%s magnitude %.3e below 1e-9 of its kind" % (kind, q, d, float(v)))
        elif abs(v) < LD(1e-9) * S_fine[fg]:
            warn.append("guarantee 4 (per-quantity grouping): %s[%d].%s magnitude %.3e" % (kind, q, d, float(v)))

    diag["levels"] = [{"level": r["level"], "dof": r["dof"], "counts_sum": int(sum(r["counts"])),
                       "time_s": round(r["time"], 2), "N_below": r["N_below"],
                       "ritz_vs_double_maxrel": r["ritz_vs_double_maxrel"],
                       "complete_check": r.get("complete_check")} for r in levels]
    diag["frequencies"] = [{"i": i, "f_Hz": float(res["f"][i]), "unc_rel": res["f_unc"][i],
                            "unc_rel_diagonal": res["f_unc_diag"][i],
                            "observed_orders": [round(o, 3) for o in res["orders"][i]]} for i in range(nm + 1)]
    diag["pairs"] = res["pairs"]
    diag["harmonic"] = [{"q": q, "U": float(res["U"][q]), "unc_abs": float(res["U_unc"][q]),
                         "observed_orders": [round(o, 3) for o in res["U_orders"][q]]} for q in range(len(hq))]
    diag["count"] = cnt_info
    diag["runtime_s"] = round(time.time() - t0, 2)
    ref = {"frame_id": frame["frame_id"], "static": stat_vals, "static_unc_over_S": stat_unc,
           "f": res["f"][:nm], "f_next": res["f"][nm], "f_unc": res["f_unc"][:nm], "count_below": count,
           "U": res["U"], "U_unc": res["U_unc"], "warnings": warn, "diag": diag}
    return ref


def make_report(frame, ref):
    st = []
    for q, nd in enumerate(frame["static_query_nodes"]):
        st.append({"node": nd, "ux": float(ref["static"][q][0]), "uy": float(ref["static"][q][1]),
                   "rz": float(ref["static"][q][2])})
    hm = []
    for q, g in enumerate(frame["harmonic_queries"]):
        o = {kk: g[kk] for kk in ("load_node", "load_dof", "amplitude", "f_Hz", "response_node", "response_dof")}
        o["U"] = float(ref["U"][q])
        hm.append(o)
    return {"frame_id": frame["frame_id"], "static": st, "frequencies_Hz": [float(x) for x in ref["f"]],
            "count_below": int(ref["count_below"]), "harmonic": hm}


# ----------------------------------------------------------------------------------------------
# Comparison
# ----------------------------------------------------------------------------------------------
def compare(frame, rep, ref, opts=None):
    opts = dict(OPTS, **(opts or {}))
    fails, refuse = [], []
    out = {"frequencies": [], "static": [], "harmonic": []}
    worst = {"frequency": 0.0, "static": 0.0, "harmonic": 0.0}
    # referee self-certification
    fu = max(ref["f_unc"]) if ref["f_unc"] else 0.0
    U_rel = _harm_unc_over_scale(frame, ref["static"], ref["U"], ref["U_unc"])
    if fu > opts["unc_refuse"] or any(x > opts["unc_refuse"] for x in U_rel) or ref["static_unc_over_S"] > opts["unc_refuse"]:
        refuse.append("referee uncertainty above %.0e (freq %.2e, harmonic %s, static %.2e)" %
                      (opts["unc_refuse"], fu, ["%.1e" % x for x in U_rel], ref["static_unc_over_S"]))
    # frequencies
    fq = rep["frequencies_Hz"]
    for i, (fr_, fv) in enumerate(zip(ref["f"], fq)):
        r = float(abs(LD(fv) - fr_) / fr_)
        tol = max(1e-9, 3 * ref["f_unc"][i])
        ok = r <= tol
        out["frequencies"].append({"i": i, "report": fv, "reference": float(fr_), "rel_res": r, "tol": tol, "ok": ok})
        worst["frequency"] = max(worst["frequency"], r)
        if not ok:
            fails.append("frequency[%d]: report %.15g reference %.15g rel residual %.2e > %.2e" % (i, fv, float(fr_), r, tol))
    # count
    cb = rep["count_below"]
    out["count"] = {"report": cb, "reference": ref["count_below"], "ok": cb == ref["count_below"]}
    if cb != ref["count_below"]:
        fails.append("count_below: report %d reference %d" % (cb, ref["count_below"]))
    # static and harmonic (section 5 rule; grouping by unit, also evaluated per quantity)
    items = _groups(frame)
    refv, repv = {}, {}
    for kind, q, d, ug, fg in items:
        if kind == "static":
            refv[(kind, q, d)] = ref["static"][q][DOFS.index(d)]
            repv[(kind, q, d)] = rep["static"][q][d]
        else:
            refv[(kind, q, d)] = ref["U"][q]
            repv[(kind, q, d)] = rep["harmonic"][q]["U"]
    S_unit, S_fine = {}, {}
    for kind, q, d, ug, fg in items:
        S_unit[ug] = max(S_unit.get(ug, LD(0)), abs(refv[(kind, q, d)]))
        S_fine[fg] = max(S_fine.get(fg, LD(0)), abs(refv[(kind, q, d)]))
    fine_fail = []
    for kind, q, d, ug, fg in items:
        v, vr = LD(repv[(kind, q, d)]), refv[(kind, q, d)]
        sc = max(abs(vr), S_unit[ug])
        scf = max(abs(vr), S_fine[fg])
        if kind == "static":
            unc_s = ref["static_unc_over_S"] * float(S_unit[ug] / sc) if sc > 0 else 0.0
        else:
            unc_s = float(ref["U_unc"][q] / sc) if sc > 0 else 0.0
        tol = max(1e-9, 3 * unc_s)
        r = float(abs(v - vr) / sc) if sc > 0 else (0.0 if v == 0 else float("inf"))
        rf = float(abs(v - vr) / scf) if scf > 0 else r
        ok = r <= tol
        rec = {"q": q, "dof": d, "report": float(v), "reference": float(vr), "res_over_scale": r,
               "scale": float(sc), "tol": tol, "ok": ok, "res_over_scale_per_quantity_grouping": rf}
        out[kind].append(rec)
        worst[kind] = max(worst[kind], r)
        if not ok:
            fails.append("%s[%d].%s: report %.15g reference %.15g residual/scale %.2e > %.2e" %
                         (kind, q, d, float(v), float(vr), r, tol))
        if rf > tol:
            fine_fail.append("%s[%d].%s" % (kind, q, d))
    out["per_quantity_grouping_failures"] = fine_fail
    return fails, refuse, out, worst


# ----------------------------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------------------------
def _dump(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, sort_keys=False)
        fh.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frame", required=True)
    ap.add_argument("--report")
    ap.add_argument("--out")
    ap.add_argument("--solve", action="store_true")
    ap.add_argument("--output")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    log = (lambda *x: print(*x, file=sys.stderr, flush=True)) if a.verbose else None
    frame, prob = load_json_strict(a.frame)
    if prob:
        print("frame file: %s" % "; ".join(prob), file=sys.stderr)
        return 2
    fat, fwarn = validate_frame(frame)
    if fat:
        print("frame invalid: %s" % "; ".join(fat), file=sys.stderr)
        return 2
    fid = frame["frame_id"]
    try:
        return _main_body(a, ap, frame, fwarn, fid, log, t0)
    except Exception as e:  # noqa: BLE001  internal failure: cannot certify (never a silent pass/fail)
        import traceback
        traceback.print_exc()
        print("%s pass=False referee error: %s: %s" % (fid, type(e).__name__, e))
        return 2


def _main_body(a, ap, frame, fwarn, fid, log, t0):
    if a.solve:
        if not a.output:
            ap.error("--solve needs --output")
        ref = analyze(frame, log=log)
        _dump(a.output, make_report(frame, ref))
        if a.out:
            _dump(a.out, {"frame_id": fid, "warnings": fwarn + ref["warnings"], "f_unc": ref["f_unc"],
                          "U_unc": [float(u) for u in ref["U_unc"]], "static_unc_over_S": ref["static_unc_over_S"],
                          "diagnostics": ref["diag"]})
        if not a.quiet:
            print("%s solved max_f_unc=%.1e warnings=%d t=%.1fs" % (fid, max(ref["f_unc"]), len(fwarn + ref["warnings"]), time.time() - t0))
        return 0
    if not a.report:
        ap.error("--report is required unless --solve")
    verdict = {"frame_id": fid, "pass": False, "failures": [], "refusals": [], "warnings": list(fwarn)}
    rep, rprob = load_json_strict(a.report)
    if rprob:
        verdict["failures"] = ["report file convention: %s" % "; ".join(rprob)]
    else:
        sp4 = validate_report(rep, frame)
        if sp4:
            verdict["failures"] = ["section 4: %s" % p for p in sp4]
    worst = {}
    if not verdict["failures"]:
        ref = analyze(frame, log=log)
        fails, refuse, details, worst = compare(frame, rep, ref)
        verdict["failures"] = fails
        verdict["refusals"] = refuse
        verdict["warnings"] += ref["warnings"]
        verdict["checks"] = details
        verdict["reference"] = make_report(frame, ref)
        verdict["referee"] = {"f_unc_rel": ref["f_unc"], "f_next_Hz": float(ref["f_next"]),
                              "U_unc_abs": [float(u) for u in ref["U_unc"]],
                              "static_unc_over_S": ref["static_unc_over_S"], "diagnostics": ref["diag"]}
    verdict["pass"] = not verdict["failures"] and not verdict["refusals"]
    verdict["worst_residual"] = worst
    verdict["runtime_s"] = round(time.time() - t0, 2)
    if a.out:
        _dump(a.out, verdict)
    if not a.quiet:
        w = worst or {}
        print("%s pass=%s freq=%.2e static=%.2e harmonic=%.2e count=%s t=%.1fs%s" % (
            fid, verdict["pass"], w.get("frequency", float("nan")), w.get("static", float("nan")),
            w.get("harmonic", float("nan")),
            ("%s/%s" % (rep.get("count_below"), verdict["reference"]["count_below"])) if "reference" in verdict else "n/a",
            verdict["runtime_s"], "" if verdict["pass"] else " | " + "; ".join((verdict["failures"] + verdict["refusals"])[:3])))
    if verdict["pass"]:
        return 0
    return 2 if (verdict["refusals"] and not verdict["failures"]) else 1


if __name__ == "__main__":
    sys.exit(main())
