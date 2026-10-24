#!/usr/bin/env python3
"""Reference B: independent referee (and small solver) for HETERO_SPEC.

Bound states and transmission of a layered effective-mass heterostructure with
BenDaniel-Duke interface conditions, checked by direct numerical integration of
the first-order system

    psi' = m phi,     phi' = (V(x) - E) psi / C,     phi = psi' / m,

inside every layer with a high-order Taylor one-step method (recurrence for a
linear potential, step k*h <= 1, truncation below 1e-22 by a majorant series),
plus the variational system for d/dE.  No special functions and no closed-form
layer transfer matrices are used anywhere in this file.

  python referee.py --structure S.json --report R.json [--out verdict.json] [--quiet]
  python referee.py --solve --structure S.json --output R.json

Exit status 0 iff the report passes (or, with --solve, the report was written).
See METHOD.md for the method, the checks and the measured precision.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
import sys
import time

import numpy as np

C_STR = "0.0380998212"          # eV nm^2, hbar^2 / (2 m0)
TOL_BOUND = 1e-9                 # eV
TOL_T = 1e-9                     # relative
TOL_MAXE = 1e-8                  # eV
SCAN_STEP = 1e-4                 # eV, < 2e-4 (guarantee 3 extrema separation)
TWO_PI = 2.0 * math.pi
MAX_FILE = 1_000_000             # bytes ("at most 1 MB")


# --------------------------------------------------------------------------
# strict JSON loading (section 4 file conventions)
# --------------------------------------------------------------------------
class FileConventionError(Exception):
    pass


def _pairs_no_dup(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise FileConventionError(f"duplicate key {k!r}")
        out[k] = v
    return out


def _reject_constant(name):
    raise FileConventionError(f"non-finite constant {name}")


def load_json_strict(path):
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise FileConventionError(f"cannot stat: {exc}")
    if not stat.S_ISREG(st.st_mode):
        raise FileConventionError("not a regular file")
    if st.st_size == 0:
        raise FileConventionError("empty file")
    if st.st_size > MAX_FILE:
        raise FileConventionError("larger than 1 MB")
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FileConventionError(f"not UTF-8: {exc}")
    try:
        return json.loads(text, object_pairs_hook=_pairs_no_dup,
                          parse_constant=_reject_constant)
    except FileConventionError:
        raise
    except ValueError as exc:
        raise FileConventionError(f"invalid JSON: {exc}")


def is_num(v):
    return (not isinstance(v, bool)) and isinstance(v, (int, float)) and math.isfinite(v)


# --------------------------------------------------------------------------
# structure
# --------------------------------------------------------------------------
class StructureError(Exception):
    pass


class Structure:
    KEYS = {"structure_id", "left_lead", "right_lead", "layers",
            "transmission_energies_eV", "window_eV"}
    LEAD = {"mass", "v_eV"}
    LAYER = {"thickness_nm", "mass", "vl_eV", "vr_eV"}

    def __init__(self, obj):
        if not isinstance(obj, dict) or set(obj) != self.KEYS:
            raise StructureError("structure must have exactly the keys %s" % sorted(self.KEYS))
        sid = obj["structure_id"]
        if not isinstance(sid, str):
            raise StructureError("structure_id must be a string")
        self.id = sid
        self.id_ok = bool(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", sid))
        for side in ("left_lead", "right_lead"):
            ld = obj[side]
            if not isinstance(ld, dict) or set(ld) != self.LEAD or not all(is_num(ld[k]) for k in self.LEAD):
                raise StructureError(f"{side} must have exactly numeric mass, v_eV")
        self.mL = float(obj["left_lead"]["mass"])
        self.VL = float(obj["left_lead"]["v_eV"])
        self.mR = float(obj["right_lead"]["mass"])
        self.VR = float(obj["right_lead"]["v_eV"])
        lays = obj["layers"]
        if not isinstance(lays, list) or len(lays) == 0:
            raise StructureError("layers must be a non-empty list")
        for i, L in enumerate(lays):
            if not isinstance(L, dict) or set(L) != self.LAYER or not all(is_num(L[k]) for k in self.LAYER):
                raise StructureError(f"layer {i} must have exactly numeric {sorted(self.LAYER)}")
            if not (L["thickness_nm"] > 0 and L["mass"] > 0):
                raise StructureError(f"layer {i}: thickness and mass must be positive")
        if not (self.mL > 0 and self.mR > 0):
            raise StructureError("lead masses must be positive")
        self.d = [float(L["thickness_nm"]) for L in lays]
        self.m = [float(L["mass"]) for L in lays]
        self.vl = [float(L["vl_eV"]) for L in lays]
        self.vr = [float(L["vr_eV"]) for L in lays]
        self.N = len(lays)
        self.X = float(sum(self.d))
        q = obj["transmission_energies_eV"]
        if not isinstance(q, list) or not all(is_num(e) for e in q):
            raise StructureError("transmission_energies_eV must be a list of numbers")
        self.qE = [float(e) for e in q]
        self.qE_raw = list(q)
        w = obj["window_eV"]
        if not isinstance(w, list) or len(w) != 2 or not all(is_num(e) for e in w):
            raise StructureError("window_eV must be two numbers")
        self.Elo, self.Ehi = float(w[0]), float(w[1])
        if not self.Elo < self.Ehi:
            raise StructureError("window_eV must satisfy E_lo < E_hi")
        self.Eth = min(self.VL, self.VR)
        self.Vlead_max = max(self.VL, self.VR)
        self.Vmax = max(max(self.vl), max(self.vr), self.VL, self.VR)
        self.Vmin_layers = min(min(self.vl), min(self.vr))

    def static_warnings(self):
        w = []

        def inside(v, lo, hi):          # domain bounds with 1e-12 slack for binary rounding
            sl = 1e-12 * max([1.0] + [abs(t) for t in (lo, hi) if math.isfinite(t)])
            return lo - sl <= v <= hi + sl
        if not self.id_ok:
            w.append("structure_id does not match [A-Za-z0-9_-]{1,64}")
        if not 2 <= self.N <= 14:
            w.append(f"N = {self.N} layers outside 2..14")
        for j in range(self.N):
            if not inside(self.d[j], 0.3, 30):
                w.append(f"layer {j}: thickness {self.d[j]} nm outside 0.3..30")
            if not inside(self.m[j], 0.03, 1.0):
                w.append(f"layer {j}: mass {self.m[j]} outside 0.03..1.0")
            for v in (self.vl[j], self.vr[j]):
                if not inside(v, -1.0, 2.0):
                    w.append(f"layer {j}: potential {v} eV outside -1..2")
            if self.vl[j] != self.vr[j]:
                sl = abs(self.vr[j] - self.vl[j]) / self.d[j]
                if not inside(sl, 1e-3, 0.5):
                    w.append(f"layer {j}: slope {sl:.6g} eV/nm outside 1e-3..0.5")
        if not inside(self.X, 0.0, 150.0):
            w.append(f"total thickness {self.X} nm > 150")
        for name, m in (("m_L", self.mL), ("m_R", self.mR)):
            if not inside(m, 0.03, 1.0):
                w.append(f"{name} = {m} outside 0.03..1.0")
        for name, v in (("V_L", self.VL), ("V_R", self.VR)):
            if not inside(v, -1.0, 2.0):
                w.append(f"{name} = {v} eV outside -1..2")
        if not 2 <= len(self.qE) <= 8:
            w.append(f"{len(self.qE)} transmission queries outside 2..8")
        if any(b <= a for a, b in zip(self.qE, self.qE[1:])):
            w.append("transmission energies not strictly increasing")
        wd = self.Ehi - self.Elo
        if not inside(wd, 0.01, 1.0):
            w.append(f"window width {wd:.6g} eV outside 0.01..1.0")
        for e in self.qE:
            if not inside(e, self.Vlead_max + 1e-3, math.inf):
                w.append(f"guarantee 2: query E={e!r} below max(V_L,V_R)+1e-3")
        if not inside(self.Elo, self.Vmax + 0.01, math.inf):
            w.append(f"guarantee 3: E_lo={self.Elo!r} below max V + 0.01 = {self.Vmax + 0.01!r}")
        return w


# --------------------------------------------------------------------------
# Taylor one-step integrator for psi'' = (m/C)(V0 + g xi - E) psi
# --------------------------------------------------------------------------
def _nterm_for(a, b, G, eps):
    """Number of Taylor terms so that a majorant of the remaining terms
    (scaled coefficients, |A|<=a, |B|<=b) and of the E-derivative series
    falls below eps (relative)."""
    p2, p1, p0 = 0.0, 1.0, 1.0      # u_{k-2}, u_{k-1}, u_k
    w2, w1, w0 = 0.0, 0.0, 0.0
    Gs = G if G > 0 else 1.0
    k = 1
    while k < 400:
        un = (a * p1 + b * p2) / ((k + 1) * k)
        wn = (a * w1 + b * w2 + G * p1) / ((k + 1) * k)
        p2, p1, p0 = p1, p0, un
        w2, w1, w0 = w1, w0, wn
        k += 1
        if max(p2, p1, p0) < eps and max(w2, w1, w0) < eps * Gs:
            break
    return k + 3


def taylor_mats(A, B, G, mh, nterm, deriv):
    """Step matrices for (psi, phi) over one step of signed length h.

    A = (m/C)(V0-E) h^2 (array), B = (m/C) g h^3, G = (m/C) h^2 (= -dA/dE),
    mh = m h.  Scaled Taylor coefficients a_k = c_k h^k obey
        (k+1) k a_{k+1} = A a_{k-1} + B a_{k-2}.
    Returns M = (M00, M01, M10, M11) and, if deriv, dM/dE."""
    one = np.ones_like(A)
    zer = np.zeros_like(A)
    # basis P: psi=1, phi=0 -> a0 = 1, a1 = 0 ; basis Q: psi=0, phi=1 -> a1 = m h (scaled out)
    p2, p1, p0 = zer, one, zer
    q2, q1, q0 = zer, zer, one
    SP, DP = one.copy(), zer.copy()
    SQ, DQ = one.copy(), one.copy()
    hasB = B != 0
    if deriv:
        bp2, bp1, bp0 = zer, zer, zer
        bq2, bq1, bq0 = zer, zer, zer
        SbP, DbP, SbQ, DbQ = zer.copy(), zer.copy(), zer.copy(), zer.copy()
    for k in range(1, nterm - 1):
        c = 1.0 / ((k + 1) * k)
        kp1 = k + 1
        if hasB:
            pn = (A * p1 + B * p2) * c
            qn = (A * q1 + B * q2) * c
        else:
            pn = A * p1 * c
            qn = A * q1 * c
        if deriv:
            if hasB:
                bpn = (A * bp1 + B * bp2 - G * p1) * c
                bqn = (A * bq1 + B * bq2 - G * q1) * c
            else:
                bpn = (A * bp1 - G * p1) * c
                bqn = (A * bq1 - G * q1) * c
            SbP += bpn
            DbP += kp1 * bpn
            SbQ += bqn
            DbQ += kp1 * bqn
            bp2, bp1, bp0 = bp1, bp0, bpn
            bq2, bq1, bq0 = bq1, bq0, bqn
        SP += pn
        DP += kp1 * pn
        SQ += qn
        DQ += kp1 * qn
        p2, p1, p0 = p1, p0, pn
        q2, q1, q0 = q1, q0, qn
    M = (SP, mh * SQ, DP / mh, DQ)
    if deriv:
        return M, (SbP, mh * SbQ, DbP / mh, DbQ)
    return M, None


# --------------------------------------------------------------------------
# solver
# --------------------------------------------------------------------------
class Solver:
    def __init__(self, S: Structure, kh=1.0, precision="double", extra_terms=0,
                 renorm_every=32, block_elems=1 << 17):
        self.S = S
        if precision == "long":
            self.rt, self.ctp, eps = np.longdouble, np.clongdouble, 1e-26
        else:
            self.rt, self.ctp, eps = np.float64, np.complex128, 1e-22
        rt = self.rt
        self.eps_terms = eps
        self.kh = float(kh)
        self.extra = int(extra_terms)
        self.renorm_every = int(renorm_every)
        self.block_elems = int(block_elems)
        self.C = rt(C_STR)
        self.Cf = float(C_STR)
        self.mL, self.VL, self.mR, self.VR = rt(S.mL), rt(S.VL), rt(S.mR), rt(S.VR)
        self.d = [rt(v) for v in S.d]
        self.m = [rt(v) for v in S.m]
        self.vl = [rt(v) for v in S.vl]
        self.vr = [rt(v) for v in S.vr]
        self.g = [(self.vr[j] - self.vl[j]) / self.d[j] for j in range(S.N)]
        # matching interface: an edge of the layer holding the lowest potential
        jmin = min(range(S.N), key=lambda j: min(S.vl[j], S.vr[j]))
        self.km = jmin if S.vl[jmin] <= S.vr[jmin] else jmin + 1
        madj = S.m[min(self.km, S.N - 1)]
        self.s_match = rt(math.sqrt(self.Cf * madj))
        self.nevals = 0

    # ---- planning ----
    def _plan(self, j, Emin, Emax):
        S = self.S
        m, vl, vr, d = S.m[j], S.vl[j], S.vr[j], S.d[j]
        g = (vr - vl) / d
        dv = max(abs(vl - Emin), abs(vl - Emax), abs(vr - Emin), abs(vr - Emax))
        mc = m / self.Cf
        k = math.sqrt(mc * dv)
        air = (mc * abs(g)) ** (1.0 / 3.0)
        n = max(1, int(math.ceil(d * max(k, air) / self.kh - 1e-12)))
        h = d / n
        nterm = _nterm_for(mc * dv * h * h, mc * abs(g) * h ** 3, mc * h * h, self.eps_terms) + self.extra
        return n, nterm

    # ---- core propagation through a sequence of layers ----
    def _run(self, layers, direction, E, psi, phi, pE=None, fE=None, prufer=None):
        """Propagate (psi, phi) [and (psi_E, phi_E)] through `layers` (indices, in
        traversal order) in `direction` (+1 rightwards, -1 leftwards).
        Returns psi, phi, pE, fE, logscale, prufer-state."""
        rt = self.rt
        Ef = E.astype(np.float64)
        Emin, Emax = float(Ef.min()), float(Ef.max())
        nE = E.shape[0]
        logs = np.zeros(nE, dtype=rt)
        deriv = pE is not None
        cnt = 0
        for j in layers:
            n, nterm = self._plan(j, Emin, Emax)
            m, vl, vr, g, d = self.m[j], self.vl[j], self.vr[j], self.g[j], self.d[j]
            h = (d / n) * direction
            mc = m / self.C
            mh = m * h
            G = mc * h * h
            B = mc * g * h * h * h
            if prufer is not None:
                theta, thp, zc = prufer
                ks = np.sqrt(mc * np.maximum(np.abs(vl - E), np.abs(vr - E)))
                s = m / np.maximum(ks, rt(1e-12))
                thn = np.arctan2(psi, s * phi)
                dt_ = thn - thp
                dt_ -= TWO_PI * np.rint(dt_ / TWO_PI)
                theta = theta + dt_
                thp = thn
            vedge = vl if direction > 0 else vr
            if self.S.vl[j] == self.S.vr[j]:
                A = (mc * (vl - E) * (h * h))[None, :]
                M, dM = taylor_mats(A, 0, G, mh, nterm, deriv)
                rows = [(0, n)]
                blocks = [(M, dM, rows)]
            else:
                nb = max(1, min(64, self.block_elems // max(nE, 1)))
                blocks = []
                for b0 in range(0, n, nb):
                    b1 = min(n, b0 + nb)
                    idx = np.arange(b0, b1).astype(rt)
                    Vs = vedge + g * h * idx
                    A = mc * (Vs[:, None] - E[None, :]) * (h * h)
                    M, dM = taylor_mats(A, B, G, mh, nterm, deriv)
                    blocks.append((M, dM, None))
            for M, dM, rows in blocks:
                if rows is None:
                    seq = [(r, 1) for r in range(M[0].shape[0])]
                else:
                    seq = [(0, rows[0][1])]
                for r, rep in seq:
                    m00, m01, m10, m11 = M[0][r], M[1][r], M[2][r], M[3][r]
                    if deriv:
                        d00, d01, d10, d11 = dM[0][r], dM[1][r], dM[2][r], dM[3][r]
                    for _ in range(rep):
                        if deriv:
                            pE, fE = (m00 * pE + m01 * fE + d00 * psi + d01 * phi,
                                      m10 * pE + m11 * fE + d10 * psi + d11 * phi)
                        if prufer is not None:
                            psi_old = psi
                        psi, phi = m00 * psi + m01 * phi, m10 * psi + m11 * phi
                        if prufer is not None:
                            thn = np.arctan2(psi, s * phi)
                            dt_ = thn - thp
                            dt_ -= TWO_PI * np.rint(dt_ / TWO_PI)
                            theta = theta + dt_
                            thp = thn
                            zc = zc + (psi * psi_old < 0)
                        cnt += 1
                        if cnt % self.renorm_every == 0:
                            nrm = np.abs(psi) + np.abs(phi)
                            psi = psi / nrm
                            phi = phi / nrm
                            if deriv:
                                pE = pE / nrm
                                fE = fE / nrm
                            logs += np.log(nrm)
            if prufer is not None:
                prufer = (theta, thp, zc)
            nrm = np.abs(psi) + np.abs(phi)
            psi = psi / nrm
            phi = phi / nrm
            if deriv:
                pE = pE / nrm
                fE = fE / nrm
            logs += np.log(nrm)
        return psi, phi, pE, fE, logs, prufer

    # ---- transmission ----
    def trans(self, E, deriv=False):
        """T(E), |r|^2+T-1 and (optionally) d ln T / dE, for E > max(V_L, V_R)."""
        rt, ct = self.rt, self.ctp
        E = np.asarray(E, dtype=rt).reshape(-1)
        self.nevals += E.shape[0]
        C = self.C
        kR = np.sqrt(self.mR * (E - self.VR) / C)
        kL = np.sqrt(self.mL * (E - self.VL) / C)
        psi = np.ones(E.shape, dtype=ct)
        phi = (1j * kR / self.mR).astype(ct)
        pE = fE = None
        if deriv:
            pE = np.zeros(E.shape, dtype=ct)
            fE = (1j / (2 * C * kR)).astype(ct)
        psi, phi, pE, fE, logs, _ = self._run(list(range(self.S.N - 1, -1, -1)), -1, E, psi, phi, pE, fE)
        u = phi * self.mL / (1j * kL)
        A = 0.5 * (psi + u)
        Bc = 0.5 * (psi - u)
        K = (kR / self.mR) / (kL / self.mL)
        absA = np.abs(A)
        logT = np.log(K) - 2 * np.log(absA) - 2 * logs
        T = np.exp(logT)
        r2 = (np.abs(Bc) / absA) ** 2
        cons = r2 + T - 1
        out = {"T": T, "logT": logT, "cons": cons}
        if deriv:
            kLE = self.mL / (2 * C * kL)
            AE = 0.5 * (pE + fE * self.mL / (1j * kL) - phi * self.mL * kLE / (1j * kL * kL))
            g = 0.5 / (E - self.VR) - 0.5 / (E - self.VL) - 2 * np.real(AE / A)
            out["g"] = g
        return out

    # ---- bound states: node count (Prufer) and matching residual ----
    def nodes(self, E):
        rt = self.rt
        E = np.asarray(E, dtype=rt).reshape(-1)
        self.nevals += E.shape[0]
        kL = np.sqrt(self.mL * (self.VL - E) / self.C)
        psi = np.ones(E.shape, dtype=rt)
        phi = kL / self.mL
        # Prufer angle in the left lead with scale s = m_L / kappa_L: psi = s phi -> pi/4
        th0 = np.full(E.shape, math.pi / 4, dtype=rt)
        pr = (th0.copy(), th0.copy(), np.zeros(E.shape, dtype=np.int64))
        psi, phi, _, _, _, pr = self._run(list(range(self.S.N)), +1, E, psi, phi, prufer=pr)
        theta, _, zc = pr
        n_in = np.floor(theta / rt(math.pi)).astype(np.int64)
        kR = np.sqrt(self.mR * (self.VR - E) / self.C)
        Agrow = psi + self.mR * phi / kR
        rz = (psi * Agrow < 0).astype(np.int64)
        return n_in + rz, zc + rz

    def resid(self, E):
        rt = self.rt
        E = np.asarray(E, dtype=rt).reshape(-1)
        self.nevals += E.shape[0]
        N, km = self.S.N, self.km
        kL = np.sqrt(self.mL * (self.VL - E) / self.C)
        psiL = np.ones(E.shape, dtype=rt)
        phiL = kL / self.mL
        if km > 0:
            psiL, phiL, _, _, _, _ = self._run(list(range(0, km)), +1, E, psiL, phiL)
        kR = np.sqrt(self.mR * (self.VR - E) / self.C)
        psiR = np.ones(E.shape, dtype=rt)
        phiR = -kR / self.mR
        if km < N:
            psiR, phiR, _, _, _, _ = self._run(list(range(N - 1, km - 1, -1)), -1, E, psiR, phiR)
        s = self.s_match
        return s * (psiL * phiR - phiL * psiR) / (np.hypot(psiL, s * phiL) * np.hypot(psiR, s * phiR))

    def bound_states(self):
        """All bound states: isolate by bisection on the Prufer node count,
        refine by Ridders on the matching residual."""
        S = self.S
        rt = self.rt
        Etop = S.Eth - 1e-5
        info = {"E_top": Etop}
        Elow = min(S.Vmin_layers, S.Eth) - 1e-9
        ntot = int(self.nodes([Etop])[0][0])
        info["count_at_Etop"] = ntot
        if ntot == 0:
            return [], info
        n = np.arange(ntot)
        lo = np.full(ntot, Elow, dtype=rt)
        hi = np.full(ntot, Etop, dtype=rt)
        Nlo = np.zeros(ntot, dtype=np.int64)
        Nhi = np.full(ntot, ntot, dtype=np.int64)
        for _ in range(200):
            need = (Nlo != n) | (Nhi != n + 1)
            if not need.any():
                break
            if np.all((hi - lo)[need] < 1e-14):
                break
            ii = np.nonzero(need)[0]
            mid = 0.5 * (lo[ii] + hi[ii])
            Nm = self.nodes(mid)[0]
            up = Nm > n[ii]
            hi[ii[up]] = mid[up]
            Nhi[ii[up]] = Nm[up]
            lo[ii[~up]] = mid[~up]
            Nlo[ii[~up]] = Nm[~up]
        info["isolated"] = bool(np.all((Nlo == n) & (Nhi == n + 1)))
        flo = self.resid(lo)
        fhi = self.resid(hi)
        roots = ridders(self.resid, lo, hi, flo, fhi, xtol=1e-14)
        return [rt(r) for r in roots], info

    # ---- maxima scan ----
    def scan(self, Elo, Ehi, chunk=1024):
        nint = max(2, int(math.ceil((Ehi - Elo) / SCAN_STEP - 1e-9)))
        grid = np.array([Elo + (Ehi - Elo) * i / nint for i in range(nint + 1)], dtype=np.float64)
        grid[0], grid[-1] = Elo, Ehi
        Gr = grid.astype(self.rt)
        T = np.empty(grid.shape, dtype=self.rt)
        g = np.empty(grid.shape, dtype=self.rt)
        cons = np.empty(grid.shape, dtype=self.rt)
        for a in range(0, grid.size, chunk):
            o = self.trans(Gr[a:a + chunk], deriv=True)
            T[a:a + chunk] = o["T"]
            g[a:a + chunk] = o["g"]
            cons[a:a + chunk] = o["cons"]
        return Gr, T, g, cons

    def extrema(self, Elo, Ehi):
        Gr, T, g, cons = self.scan(Elo, Ehi)
        sg = np.sign(g)
        sg[sg == 0] = 1
        imax = np.nonzero((sg[:-1] > 0) & (sg[1:] < 0))[0]
        imin = np.nonzero((sg[:-1] < 0) & (sg[1:] > 0))[0]
        idx = np.concatenate([imax, imin])
        kind = np.concatenate([np.ones(imax.size, int), -np.ones(imin.size, int)])
        order = np.argsort(idx, kind="stable")
        idx, kind = idx[order], kind[order]
        res = {"grid_n": int(Gr.size), "scan_cons_max": float(np.max(np.abs(cons))),
               "E_lo": Elo, "E_hi": Ehi,
               "T_lo": T[0], "T_hi": T[-1]}
        # discrete maxima of T itself (consistency diagnostic)
        dmax = int(np.count_nonzero((T[1:-1] > T[:-2]) & (T[1:-1] >= T[2:])))
        res["discrete_T_maxima"] = dmax
        if idx.size == 0:
            res.update(E=np.zeros(0, dtype=self.rt), T=np.zeros(0, dtype=self.rt), kind=kind)
            return res
        a, b = Gr[idx], Gr[idx + 1]
        fa, fb = g[idx], g[idx + 1]
        gf = lambda e: self.trans(e, deriv=True)["g"]
        Ex = ridders(gf, a, b, fa, fb, xtol=1e-13)
        o = self.trans(Ex)
        res.update(E=Ex, T=o["T"], kind=kind, cons_ext=float(np.max(np.abs(o["cons"]))))
        return res

    # ---- full own solution ----
    def solve(self):
        S = self.S
        out = {}
        out["bound"], out["bound_info"] = self.bound_states()
        qE = np.array(S.qE, dtype=np.float64)
        ok = qE > S.Vlead_max
        Tq = np.full(qE.shape, np.nan)
        gq = np.full(qE.shape, np.nan)
        cq = np.full(qE.shape, np.nan)
        if ok.any():
            o = self.trans(qE[ok].astype(self.rt), deriv=True)
            Tq[ok], gq[ok], cq[ok] = o["T"], o["g"], o["cons"]
        out["T"], out["dlnT"], out["cons"], out["q_ok"] = Tq, gq, cq, ok
        if S.Elo > S.Vlead_max:
            out["ext"] = self.extrema(S.Elo, S.Ehi)
        else:
            out["ext"] = None
        return out


# --------------------------------------------------------------------------
# vectorised Ridders root finder (bracketing)
# --------------------------------------------------------------------------
def ridders(f, a, b, fa, fb, xtol, maxit=100):
    a = np.array(a, copy=True)
    b = np.array(b, copy=True)
    fa = np.array(fa, copy=True)
    fb = np.array(fb, copy=True)
    if a.size == 0:
        return a
    for _ in range(maxit):
        act = (np.abs(b - a) > xtol) & (fa != 0) & (fb != 0)
        if not act.any():
            break
        ia = np.nonzero(act)[0]
        A_, B_, FA, FB = a[ia], b[ia], fa[ia], fb[ia]
        m = 0.5 * (A_ + B_)
        fm = f(m)
        s = np.sqrt(fm * fm - FA * FB)
        s = np.where(s == 0, 1, s)
        xn = m + (m - A_) * np.sign(FA - FB) * fm / s
        lo, hi = np.minimum(A_, B_), np.maximum(A_, B_)
        xn = np.clip(xn, lo, hi)
        fx = f(xn)
        c1 = np.sign(fm) * np.sign(fx) < 0
        c2 = (~c1) & (np.sign(FA) * np.sign(fx) < 0)
        nA = np.where(c1, m, np.where(c2, A_, xn))
        nFA = np.where(c1, fm, np.where(c2, FA, fx))
        nB = np.where(c1, xn, np.where(c2, xn, B_))
        nFB = np.where(c1, fx, np.where(c2, fx, FB))
        zm = fm == 0
        zx = (fx == 0) & ~zm
        nA = np.where(zm, m, np.where(zx, xn, nA))
        nB = np.where(zm, m, np.where(zx, xn, nB))
        nFA = np.where(zm | zx, 0, nFA)
        nFB = np.where(zm | zx, 0, nFB)
        a[ia], b[ia], fa[ia], fb[ia] = nA, nB, nFA, nFB
    return np.where(fa == 0, a, np.where(fb == 0, b, 0.5 * (a + b)))


# --------------------------------------------------------------------------
# report format (section 4)
# --------------------------------------------------------------------------
def check_report_format(rep, S):
    errs = []
    keys = {"structure_id", "bound_states", "transmission", "maxima"}
    if not isinstance(rep, dict):
        return ["report is not a JSON object"]
    if set(rep) != keys:
        errs.append(f"report keys {sorted(rep)} != {sorted(keys)}")
        return errs
    if rep["structure_id"] != S.id:
        errs.append("structure_id does not match the structure")
    bs = rep["bound_states"]
    if not isinstance(bs, list):
        errs.append("bound_states is not a list")
    else:
        for i, b in enumerate(bs):
            if not isinstance(b, dict) or set(b) != {"E_eV"} or not is_num(b["E_eV"]):
                errs.append(f"bound_states[{i}] must be {{E_eV: number}}")
        if not errs and any(bs[i + 1]["E_eV"] <= bs[i]["E_eV"] for i in range(len(bs) - 1)):
            errs.append("bound_states not strictly increasing")
    tr = rep["transmission"]
    if not isinstance(tr, list):
        errs.append("transmission is not a list")
    else:
        if len(tr) != len(S.qE):
            errs.append(f"transmission has {len(tr)} entries, structure has {len(S.qE)} queries")
        for i, t in enumerate(tr):
            if not isinstance(t, dict) or set(t) != {"E_eV", "T"} or not is_num(t["E_eV"]) or not is_num(t["T"]):
                errs.append(f"transmission[{i}] must be {{E_eV, T: numbers}}")
            elif i < len(S.qE) and float(t["E_eV"]) != S.qE[i]:
                errs.append(f"transmission[{i}].E_eV {t['E_eV']!r} is not the queried energy {S.qE_raw[i]!r}")
    mx = rep["maxima"]
    if not isinstance(mx, list):
        errs.append("maxima is not a list")
    else:
        ok = True
        for i, t in enumerate(mx):
            if not isinstance(t, dict) or set(t) != {"E_eV", "T"} or not is_num(t["E_eV"]) or not is_num(t["T"]):
                errs.append(f"maxima[{i}] must be {{E_eV, T: numbers}}")
                ok = False
        if ok and any(mx[i + 1]["E_eV"] <= mx[i]["E_eV"] for i in range(len(mx) - 1)):
            errs.append("maxima not strictly increasing in energy")
    return errs


# --------------------------------------------------------------------------
# referee
# --------------------------------------------------------------------------
def fnum(x):
    return float(x)


def referee(S, rep, args):
    t0 = time.time()
    failures, warnings, notes = [], [], []
    warnings += S.static_warnings()
    fmt = check_report_format(rep, S)
    failures += ["format: " + e for e in fmt]
    sol = Solver(S, kh=args.kh, precision=args.precision)
    own = sol.solve()
    worst = {"bound_dE_eV": 0.0, "T_rel": 0.0, "max_dE_eV": 0.0, "max_T_rel": 0.0,
             "cons": 0.0, "self_bound_dE_eV": 0.0, "self_T_rel": 0.0,
             "self_max_dE_eV": 0.0, "self_max_T_rel": 0.0}
    detail = {"bound": [], "transmission": [], "maxima": []}

    # ---------------- 1. bound states ----------------
    ownE = [float(e) for e in own["bound"]]
    detail["own_bound_eV"] = ownE
    binfo = own["bound_info"]
    if not binfo.get("isolated", True):
        warnings.append("guarantee 1: bound states not isolated at 1e-14 eV (spacing violation?)")
    if len(ownE) > 40:
        warnings.append(f"guarantee 1: {len(ownE)} bound states > 40")
    for i in range(len(ownE) - 1):
        if ownE[i + 1] - ownE[i] < 1e-6:
            warnings.append(f"guarantee 1: bound states {i},{i+1} closer than 1e-6 eV")
    if ownE and S.Eth - ownE[-1] < 1e-4:
        warnings.append(f"guarantee 1: highest bound state {S.Eth - ownE[-1]:.3g} eV below E_th (< 1e-4)")
    if isinstance(rep, dict) and isinstance(rep.get("bound_states"), list) and \
            all(isinstance(b, dict) and is_num(b.get("E_eV")) for b in rep["bound_states"]):
        repE = [float(b["E_eV"]) for b in rep["bound_states"]]
    else:
        repE = None
    if repE is not None:
        nrep = len(repE)
        if nrep != binfo["count_at_Etop"]:
            failures.append(f"bound_count: report {nrep}, node count at E_th-1e-5 is {binfo['count_at_Etop']}")
        bad = [e for e in repE if not e < S.Eth]
        if bad:
            failures.append(f"bound_energy: {len(bad)} reported energies not below E_th")
        good = [i for i, e in enumerate(repE) if e < S.Eth - 2e-9]
        if good:
            Ep = np.array([repE[i] for i in good])
            Rm = sol.resid(Ep - TOL_BOUND)
            Rp = sol.resid(Ep + TOL_BOUND)
            Nm, Zm = sol.nodes(Ep - TOL_BOUND)
            Np_, Zp = sol.nodes(Ep + TOL_BOUND)
            if np.any(Nm != Zm) or np.any(Np_ != Zp):
                failures.append("referee self-check: Prufer count != sign-change count")
            for k, i in enumerate(good):
                e = repE[i]
                rec = {"i": i, "E_rep": e,
                       "R_minus": fnum(Rm[k]), "R_plus": fnum(Rp[k]),
                       "nodes_minus": int(Nm[k]), "nodes_plus": int(Np_[k])}
                sc = float(Rm[k]) * float(Rp[k]) <= 0
                rec["sign_change"] = bool(sc)
                if not sc:
                    failures.append(f"bound_energy[{i}]: matching residual has no sign change in E_rep +- 1e-9 eV")
                if not (Nm[k] == i and Np_[k] == i + 1):
                    failures.append(f"bound_energy[{i}]: node count {int(Nm[k])}->{int(Np_[k])} across E_rep +- 1e-9 eV, expected {i}->{i+1}")
                if i < len(ownE):
                    dE = abs(e - ownE[i])
                    rec["E_own"] = ownE[i]
                    rec["dE"] = dE
                    worst["bound_dE_eV"] = max(worst["bound_dE_eV"], dE)
                    if dE > TOL_BOUND:
                        failures.append(f"bound_energy[{i}]: |E_rep - E_own| = {dE:.3e} eV > 1e-9")
                detail["bound"].append(rec)
        if nrep >= 2 and all(repE[i] < repE[i + 1] for i in range(nrep - 1)) and not bad:
            mids = np.array([0.5 * (repE[i] + repE[i + 1]) for i in range(nrep - 1)])
            Nmid = sol.nodes(mids)[0]
            for i in range(nrep - 1):
                if Nmid[i] != i + 1:
                    failures.append(f"bound completeness: node count {int(Nmid[i])} at midpoint {i}/{i+1}, expected {i+1}")
            detail["midpoint_counts"] = [int(v) for v in Nmid]
        if nrep >= 1 and not bad:
            below = repE[0] - 0.5e-6
            nb_ = int(sol.nodes([below])[0][0])
            detail["count_below_lowest"] = nb_
            if nb_ != 0:
                failures.append(f"bound completeness: node count {nb_} at E_0 - 5e-7 eV, expected 0")
    detail["count_at_Etop"] = binfo["count_at_Etop"]

    # ---------------- 2. transmission ----------------
    qok = own["q_ok"]
    for i, e in enumerate(S.qE):
        if not qok[i]:
            warnings.append(f"query {i}: E={e!r} not above both lead band edges; T undefined, not checked")
            continue
        T = float(own["T"][i])
        rec = {"i": i, "E": e, "T_own": T, "dlnT_dE": float(own["dlnT"][i]), "cons": float(own["cons"][i])}
        worst["cons"] = max(worst["cons"], abs(float(own["cons"][i])))
        if T < 1e-30:
            warnings.append(f"guarantee 2: T({e!r}) = {T:.3e} < 1e-30")
        if abs(float(own["dlnT"][i])) > 1e3:
            warnings.append(f"guarantee 2: |d ln T/dE| = {abs(float(own['dlnT'][i])):.3e} > 1e3 at E={e!r}")
        tr = rep.get("transmission") if isinstance(rep, dict) else None
        if isinstance(tr, list) and i < len(tr) and isinstance(tr[i], dict) and is_num(tr[i].get("T")):
            Tr = float(tr[i]["T"])
            rel = abs(Tr - T) / T
            rec["T_rep"] = Tr
            rec["rel"] = rel
            worst["T_rel"] = max(worst["T_rel"], rel)
            if rel > TOL_T:
                failures.append(f"transmission[{i}]: relative error {rel:.3e} > 1e-9")
        detail["transmission"].append(rec)

    # ---------------- 3. maxima ----------------
    ext = own["ext"]
    if ext is None:
        warnings.append("window not above both lead band edges; maxima not checked")
        ownMx = []
    else:
        kind = ext["kind"]
        Ex = [float(v) for v in ext["E"]]
        Tx = [float(v) for v in ext["T"]]
        ownMx = [(Ex[k], Tx[k]) for k in range(len(Ex)) if kind[k] > 0]
        worst["cons"] = max(worst["cons"], ext["scan_cons_max"], ext.get("cons_ext", 0.0))
        detail["own_maxima"] = [{"E_eV": e, "T": t} for e, t in ownMx]
        detail["scan_points"] = ext["grid_n"]
        if ext["discrete_T_maxima"] != len(ownMx):
            warnings.append(f"scan: {ext['discrete_T_maxima']} discrete maxima of T vs {len(ownMx)} sign changes of dT/dE")
        # guarantee 3 diagnostics
        pts = [(S.Elo, None)] + [(Ex[k], kind[k]) for k in range(len(Ex))] + [(S.Ehi, None)]
        for k in range(len(Ex)):
            if Ex[k] - S.Elo < 2e-4 or S.Ehi - Ex[k] < 2e-4:
                warnings.append(f"guarantee 3: extremum at {Ex[k]:.10g} eV within 2e-4 eV of a window end")
        for k in range(len(Ex) - 1):
            if Ex[k + 1] - Ex[k] < 2e-4:
                warnings.append(f"guarantee 3: extrema at {Ex[k]:.10g} and {Ex[k+1]:.10g} eV closer than 2e-4 eV")
        Tends = (float(ext["T_lo"]), float(ext["T_hi"]))
        for k in range(len(Ex)):
            if kind[k] < 0:
                continue
            left = Tx[k - 1] if k > 0 else Tends[0]
            right = Tx[k + 1] if k + 1 < len(Ex) else Tends[1]
            for adj in (left, right):
                if Tx[k] - adj < 1e-3 * Tx[k]:
                    warnings.append(f"guarantee 3: maximum at {Ex[k]:.10g} eV exceeds a neighbour by only {(Tx[k]-adj)/Tx[k]:.3g} relative (< 1e-3)")
        mx = rep.get("maxima") if isinstance(rep, dict) else None
        if isinstance(mx, list) and all(isinstance(t, dict) and is_num(t.get("E_eV")) and is_num(t.get("T")) for t in mx):
            if len(mx) != len(ownMx):
                failures.append(f"maxima_count: report {len(mx)}, own scan {len(ownMx)}")
            for i in range(min(len(mx), len(ownMx))):
                Er, Tr = float(mx[i]["E_eV"]), float(mx[i]["T"])
                Eo, To = ownMx[i]
                dE = abs(Er - Eo)
                rel = abs(Tr - To) / To
                worst["max_dE_eV"] = max(worst["max_dE_eV"], dE)
                worst["max_T_rel"] = max(worst["max_T_rel"], rel)
                detail["maxima"].append({"i": i, "E_rep": Er, "E_own": Eo, "dE": dE, "T_rep": Tr, "T_own": To, "rel": rel})
                if dE > TOL_MAXE:
                    failures.append(f"maximum_energy[{i}]: |dE| = {dE:.3e} eV > 1e-8")
                if rel > TOL_T:
                    failures.append(f"maximum_T[{i}]: relative error {rel:.3e} > 1e-9")
    if worst["cons"] > 1e-10:
        failures.append(f"referee self-check: current conservation |r|^2+T-1 = {worst['cons']:.2e} > 1e-10")

    # ---------------- self-precision: second, tighter run ----------------
    if not args.no_tight:
        tight = Solver(S, kh=args.kh / 2, precision=args.precision, extra_terms=6)
        if ownE:
            Eo = np.array(ownE, dtype=tight.rt)
            dl = np.full(Eo.shape, 1e-10)
            ok = np.zeros(Eo.shape, bool)
            for _ in range(4):
                fa, fb = tight.resid(Eo - dl), tight.resid(Eo + dl)
                ok = fa * fb <= 0
                if ok.all():
                    break
                dl = np.where(ok, dl, dl * 100)
            Et = ridders(tight.resid, Eo - dl, Eo + dl, fa, fb, xtol=1e-14)
            worst["self_bound_dE_eV"] = float(np.max(np.abs(Et - Eo)))
            if not ok.all():
                worst["self_bound_dE_eV"] = max(worst["self_bound_dE_eV"], float(np.max(dl)))
        okq = own["q_ok"]
        if okq.any():
            Tt = tight.trans(np.array(S.qE)[okq])["T"]
            worst["self_T_rel"] = float(np.max(np.abs(Tt / own["T"][okq] - 1)))
        if ownMx:
            Eo = np.array([e for e, _ in ownMx], dtype=tight.rt)
            gf = lambda e: tight.trans(e, deriv=True)["g"]
            dl = np.full(Eo.shape, 1e-9)
            ok = np.zeros(Eo.shape, bool)
            for _ in range(4):
                fa, fb = gf(Eo - dl), gf(Eo + dl)
                ok = fa * fb <= 0
                if ok.all():
                    break
                dl = np.where(ok, dl, dl * 30)
            Et = ridders(gf, Eo - dl, Eo + dl, fa, fb, xtol=1e-13)
            Tt = tight.trans(Et)["T"]
            worst["self_max_dE_eV"] = float(np.max(np.abs(Et - Eo)))
            worst["self_max_T_rel"] = float(np.max(np.abs(Tt / np.array([t for _, t in ownMx]) - 1)))
        lim = {"self_bound_dE_eV": 0.1 * TOL_BOUND, "self_T_rel": 0.1 * TOL_T,
               "self_max_dE_eV": 0.1 * TOL_MAXE, "self_max_T_rel": 0.1 * TOL_T}
        for k, v in lim.items():
            if worst[k] > v:
                failures.append(f"referee self-check: {k} = {worst[k]:.2e} exceeds 10% of the tolerance")

    passed = not failures
    runtime = time.time() - t0
    verdict = {"structure_id": S.id, "pass": passed, "failures": failures, "warnings": warnings,
               "worst": worst, "runtime_s": runtime, "method": "Ref B: Taylor-series integration, Prufer node count, variational dT/dE",
               "config": {"kh": args.kh, "precision": args.precision},
               "detail": detail}
    return verdict


def build_report(S, own):
    rep = {"structure_id": S.id,
           "bound_states": [{"E_eV": float(e)} for e in own["bound"]],
           "transmission": [{"E_eV": S.qE_raw[i], "T": float(own["T"][i])} for i in range(len(S.qE))],
           "maxima": []}
    ext = own["ext"]
    if ext is not None:
        rep["maxima"] = [{"E_eV": float(ext["E"][k]), "T": float(ext["T"][k])}
                         for k in range(len(ext["E"])) if ext["kind"][k] > 0]
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--structure", required=True)
    ap.add_argument("--report")
    ap.add_argument("--out")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--solve", action="store_true", help="write a full report by Ref B's own means")
    ap.add_argument("--output", help="report path for --solve")
    ap.add_argument("--kh", type=float, default=1.0, help="max k*h per Taylor step (default 1)")
    ap.add_argument("--precision", choices=["double", "long"], default="double")
    ap.add_argument("--no-tight", action="store_true", help="skip the second, tighter self-check run")
    args = ap.parse_args(argv)
    t0 = time.time()
    try:
        S = Structure(load_json_strict(args.structure))
    except (FileConventionError, StructureError) as exc:
        print(f"structure error: {exc}", file=sys.stderr)
        return 2
    if args.solve:
        if not args.output:
            ap.error("--solve needs --output")
        sol = Solver(S, kh=args.kh, precision=args.precision)
        own = sol.solve()
        rep = build_report(S, own)
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, indent=1)
            fh.write("\n")
        if not args.quiet:
            print(f"{S.id} solved: {len(rep['bound_states'])} bound, {len(rep['maxima'])} maxima, "
                  f"{time.time() - t0:.1f}s")
        return 0
    if not args.report:
        ap.error("--report is required unless --solve")
    try:
        rep = load_json_strict(args.report)
        conv_err = None
    except FileConventionError as exc:
        rep, conv_err = None, str(exc)
    if conv_err is not None:
        verdict = {"structure_id": S.id, "pass": False, "failures": [f"file conventions: {conv_err}"],
                   "warnings": S.static_warnings(), "worst": {}, "runtime_s": time.time() - t0}
    else:
        verdict = referee(S, rep, args)
    verdict["runtime_s"] = time.time() - t0
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(verdict, fh, indent=1, default=float)
            fh.write("\n")
    if not args.quiet:
        w = verdict.get("worst", {})
        def g(k):
            return f"{w[k]:.1e}" if k in w else "na"
        line = (f"{S.id} pass={verdict['pass']} bound_dE={g('bound_dE_eV')} T_rel={g('T_rel')} "
                f"max_dE={g('max_dE_eV')} max_T_rel={g('max_T_rel')} cons={g('cons')} "
                f"self=({g('self_bound_dE_eV')},{g('self_T_rel')},{g('self_max_dE_eV')},{g('self_max_T_rel')}) "
                f"fail={len(verdict['failures'])} warn={len(verdict['warnings'])} "
                f"runtime={verdict['runtime_s']:.1f}s")
        print(line)
    return 0 if verdict["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
