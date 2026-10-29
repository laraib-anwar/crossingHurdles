#!/usr/bin/env python3
"""Reference B for the multi-dose regimen task (REGIMEN_SPEC.md).

Numerical route: fixed-step Taylor-series integration of the compartment ODE in numpy
longdouble (80-bit extended), order K (default 30), with the Michaelis-Menten term
expanded by the Cauchy-product recurrence of y = C/(Km+C). Steps restart exactly at every
event (IV bolus, lagged oral arrival, infusion start and end); event times are kept as exact
rationals (decimal value of each JSON number). The periodic steady state is the fixed point
of the period map, found by Newton's method with the exact Jacobian from the variational
equations (also Taylor-integrated). Extrema and window crossings are bracketed on the dense
Taylor polynomial of each step and polished by bisection in longdouble.

Usage: python referee.py --regimen in.json --output out.json [--check out.check.json]
The whole pipeline runs twice (step h and h/2); the h/2 run is reported, and the per-quantity
differences go to the check file together with all guarantee checks of spec section 2.
"""
import argparse
import json
import math
import sys
import time
from fractions import Fraction

import numpy as np

LD = np.longdouble
EPS = np.finfo(LD).eps


def frac(x):
    """Exact rational value of the shortest decimal repr of a JSON number."""
    return Fraction(repr(float(x)))


def ld(fr):
    if isinstance(fr, Fraction):
        return LD(str(fr.numerator)) / LD(str(fr.denominator))
    return LD(fr)


def ldp(x):
    """Model parameter: the exact double value carried to longdouble."""
    return LD(float(x))


# ----------------------------------------------------------------------------------------
# System
# ----------------------------------------------------------------------------------------
class System:
    def __init__(self, reg, K):
        self.reg = reg
        self.K = K
        m = reg['model']
        self.V1 = ldp(m['V1'])
        self.invV1 = LD(1) / self.V1
        CL = ldp(m['CL'])
        self.Vmax = ldp(m['Vmax'])
        self.Km = ldp(m['Km'])
        self.mm = float(m['Vmax']) > 0.0
        per = m['peripheral']
        doses = list(reg['loading_doses']) + list(reg['maintenance']['doses'])
        used = sorted({d['formulation'] for d in doses if d['route'] == 'oral'})
        forms = {f['id']: f for f in reg['formulations']}
        n = 1 + len(per)
        layout = {}
        for fid in used:
            nt = int(forms[fid]['n_transit'])
            layout[fid] = (n, nt)
            n += nt + 1
        n += 1  # AUC
        self.n = n
        self.nx = n - 1
        self.iauc = n - 1
        L = np.zeros((n, n), LD)
        L[0, 0] = -CL * self.invV1
        rho_c = float(m['CL']) / float(m['V1'])
        rates = []
        for k, p in enumerate(per):
            Q = ldp(p['Q'])
            V = ldp(p['V'])
            i = 1 + k
            L[0, 0] -= Q * self.invV1
            L[0, i] += Q / V
            L[i, 0] += Q * self.invV1
            L[i, i] -= Q / V
            rho_c += float(p['Q']) / float(m['V1'])
            rates.append(float(p['Q']) / float(p['V']))
        self.target = {}
        self.Fbio = {}
        self.tlag = {}
        for fid in used:
            f = forms[fid]
            i0, nt = layout[fid]
            ktr = ldp(f['ktr'])
            ka = ldp(f['ka'])
            for j in range(nt):
                L[i0 + j, i0 + j] = -ktr
                if j > 0:
                    L[i0 + j, i0 + j - 1] = ktr
            iD = i0 + nt
            if nt > 0:
                L[iD, iD - 1] = ktr
                rates.append(float(f['ktr']))
            L[iD, iD] = -ka
            L[0, iD] += ka
            rates.append(float(f['ka']))
            self.target[fid] = i0  # T_{f,1}, or D_f when n_transit = 0
            self.Fbio[fid] = ldp(f['F'])
            self.tlag[fid] = frac(f['tlag'])
        L[self.iauc, 0] = self.invV1
        self.L = L
        self.lam_mm = 0.0
        if self.mm:
            self.lam_mm = float(m['Vmax']) / (float(m['V1']) * float(m['Km']))
            rho_c += self.lam_mm
        self.rho = max([rho_c] + rates)
        # 1-norm of the linear part (amount states only): bounds ||hL||^k/k! truncation
        Lx = np.abs(L[:self.nx, :self.nx].astype(float))
        self.rho_lin = float(Lx.sum(axis=0).max())
        if self.mm:
            Lx[0, 0] += self.lam_mm
        self.rho_lin_mm = float(Lx.sum(axis=0).max())
        self._M = {}
        kk = np.arange(1, K + 1).astype(LD)
        self._inv = LD(1) / kk
        self.tol = LD('1e-22')
        self.step_factor = LD(1)
        self._hsug = LD(1)
        self.nsteps = 0
        self.nreject = 0

    def h_radius(self, c, h):
        """Step allowed by the coefficient decay: h * min_j (tol*scale/|c_j|)^(1/j), j = K-1, K,
        times the run's step factor (1 for theta = 1/2, 1/2 for the half-step run)."""
        K = self.K
        scale = max(np.max(np.abs(c[0])), np.max(np.abs(c[1])))
        r = None
        if scale > 0:
            for j in (K - 1, K):
                a = np.max(np.abs(c[j]))
                if a > 0:
                    v = h * (self.tol * scale / a) ** (LD(1) / j)
                    r = v if r is None else min(r, v)
        if r is None:
            r = LD(1e300)
        return r * self.step_factor

    def hmax(self, theta):
        """Step bound: ||h J||_1 <= 4 theta with J the linear part plus the low-concentration
        Michaelis-Menten rate Vmax/(V1 Km) (linear modes are entire functions; 2^31/31! ~ 3e-25
        at theta = 1/2), and h <= 2 theta hours. With Michaelis-Menten elimination the
        radius-of-convergence control of integrate() reduces the step further."""
        h = 2.0 * theta
        if self.rho_lin_mm > 0:
            h = min(h, 4.0 * theta / self.rho_lin_mm)
        return h

    # ------------------------------------------------------------------ Taylor steps
    def mats(self, h):
        """Per step size: M_k = h L/(k+1), and h Vmax/(k+1), h Vmax Km/(V1 (k+1))."""
        v = self._M.get(h)
        if v is None:
            hL = h * self.L
            Ms = hL[None, :, :] * self._inv[:, None, None]
            hV = h * self.Vmax * self._inv
            g = h * self.Vmax * self.Km * self.invV1 * self._inv
            v = (Ms, hV, g)
            if len(self._M) > 400:
                self._M.clear()
            self._M[h] = v
        return v

    def coeffs(self, x0, R, h):
        """Scaled Taylor coefficients c[k] (shape (K+1, n)) of x(t0 + h*tau), tau in [0,1].

        (k+1) c[k+1] = h (L c[k] + R e1 [k=0] - Vmax y[k] e1), y = C/(Km+C) expanded by
        y[k] = (C[k] - sum_{j=1..k} C[j] y[k-j]) / (Km + C[0])."""
        K = self.K
        n = self.n
        c = np.empty((K + 1, n), LD)
        c[0] = x0
        Ms, hVk, _ = self.mats(h)
        hR = h * R
        mm = np.matmul
        if self.mm:
            invV1 = self.invV1
            Cs = np.empty(K + 1, LD)
            ys = np.empty(K + 1, LD)
            C0 = x0[0] * invV1
            Cs[0] = C0
            iu0 = LD(1) / (self.Km + C0)
            ys[0] = C0 * iu0
            dot = np.dot
            for k in range(K):
                mm(Ms[k], c[k], out=c[k + 1])
                if k == 0:
                    c[1, 0] += hR
                else:
                    Ck = c[k, 0] * invV1
                    Cs[k] = Ck
                    ys[k] = (Ck - dot(Cs[1:k + 1], ys[k - 1::-1])) * iu0
                c[k + 1, 0] -= hVk[k] * ys[k]
        else:
            mm(Ms[0], c[0], out=c[1])
            c[1, 0] += hR
            for k in range(1, K):
                mm(Ms[k], c[k], out=c[k + 1])
        return c

    def coeffs_tan(self, X0, R, h):
        """Trajectory (column 0) plus tangent columns of the variational equation
        dPhi/dt = (L - e1 e1^T Vmax Km / (V1 (Km+C)^2)) Phi, w = 1/(Km+C) by recurrence."""
        K = self.K
        c = np.empty((K + 1,) + X0.shape, LD)
        c[0] = X0
        Ms, hVk, gk = self.mats(h)
        hR = h * R
        mm = np.matmul
        if self.mm:
            invV1 = self.invV1
            Cs = np.empty(K + 1, LD)
            ys = np.empty(K + 1, LD)
            ws = np.empty(K + 1, LD)
            w2 = np.empty(K + 1, LD)
            C0 = X0[0, 0] * invV1
            Cs[0] = C0
            iu0 = LD(1) / (self.Km + C0)
            ys[0] = C0 * iu0
            ws[0] = iu0
            w2[0] = iu0 * iu0
            for k in range(K):
                mm(Ms[k], c[k], out=c[k + 1])
                if k == 0:
                    c[1, 0, 0] += hR
                else:
                    Ck = c[k, 0, 0] * invV1
                    Cs[k] = Ck
                    ys[k] = (Ck - np.dot(Cs[1:k + 1], ys[k - 1::-1])) * iu0
                    ws[k] = -np.dot(Cs[1:k + 1], ws[k - 1::-1]) * iu0
                    w2[k] = np.dot(ws[:k + 1], ws[k::-1])
                c[k + 1, 0, 0] -= hVk[k] * ys[k]
                conv = w2[k::-1] @ c[:k + 1, 0, 1:]
                c[k + 1, 0, 1:] -= gk[k] * conv
        else:
            mm(Ms[0], c[0], out=c[1])
            c[1, 0, 0] += hR
            for k in range(1, K):
                mm(Ms[k], c[k], out=c[k + 1])
        return c

    def rhs(self, x, R):
        f = self.L @ x
        f[0] += R
        if self.mm:
            C = x[0] * self.invV1
            f[0] -= self.Vmax * C / (self.Km + C)
        return f

    # ------------------------------------------------------------------ events
    def dose_events(self, dose, t):
        """Events (time, jump index, jump amount, rate change) of one dose given at t."""
        r = dose['route']
        a = frac(dose['amount'])
        if r == 'iv_bolus':
            return [(t, 0, a, Fraction(0))]
        if r == 'iv_infusion':
            dur = frac(dose['duration'])
            rate = a / dur
            return [(t, None, None, rate), (t + dur, None, None, -rate)]
        if r == 'oral':
            fid = dose['formulation']
            return [(t + self.tlag[fid], self.target[fid], ('oral', fid, a), Fraction(0))]
        raise ValueError(r)

    def build_schedule(self, evs, lo, hi):
        """Group raw events with lo <= t < hi into {t: [jump vector, rate change, kinds]}."""
        sch = {}
        for (t, idx, amt, dr) in evs:
            if not (lo <= t < hi):
                continue
            e = sch.get(t)
            if e is None:
                e = [np.zeros(self.n, LD), Fraction(0), set()]
                sch[t] = e
            if idx is not None:
                if isinstance(amt, tuple):
                    _, fid, a = amt
                    e[0][idx] += self.Fbio[fid] * ld(a)
                    e[2].add('oral')
                else:
                    e[0][idx] += ld(amt)
                    e[2].add('bolus')
            if dr != 0:
                e[1] += dr
                e[2].add('inf_start' if dr > 0 else 'inf_end')
        return sch

    def actual_events(self, t_end):
        reg = self.reg
        evs = []
        for d in reg['loading_doses']:
            evs += self.dose_events(d, frac(d['time']))
        mt = reg['maintenance']
        st = frac(mt['start'])
        P = frac(mt['period'])
        mmax = int(math.ceil((t_end - st) / P)) + 1
        for m in range(0, mmax + 1):
            base = st + m * P
            for d in mt['doses']:
                evs += self.dose_events(d, base + frac(d['offset']))
        return evs

    def periodic_events(self):
        """Events of one period [0, P) of the maintenance regimen continued indefinitely."""
        mt = self.reg['maintenance']
        P = frac(mt['period'])
        evs = []
        for d in mt['doses']:
            o = frac(d['offset'])
            r = d['route']
            if r == 'iv_bolus':
                evs.append((o, 0, frac(d['amount']), Fraction(0)))
            elif r == 'oral':
                fid = d['formulation']
                a = o + self.tlag[fid]
                while a >= P:
                    a -= P
                evs.append((a, self.target[fid], ('oral', fid, frac(d['amount'])), Fraction(0)))
            else:
                dur = frac(d['duration'])
                rate = frac(d['amount']) / dur
                jmin = -int(math.ceil(dur / P)) - 2
                for j in range(jmin, 1):
                    s = o + j * P
                    e = s + dur
                    if e <= 0 or s >= P:
                        continue
                    evs.append((max(s, Fraction(0)), None, None, rate))
                    if e < P:
                        evs.append((e, None, None, -rate))
        return evs

    # ------------------------------------------------------------------ driver
    def integrate(self, sch, t0, t1, x0, hmax, record=(), dense_until=None, tangent=None,
                  R0=Fraction(0)):
        """Integrate from t0 (state x0 = left limit, infusion rate R0 just before t0) to t1-.

        Events at t0 are applied at the start, events at t1 are not. Returns dict with the
        final state (left limit at t1), the rate in force just before t1, records
        {t: (left, right)} and the dense step list for steps inside [t0, dense_until]."""
        bps = set(t for t in sch if t0 <= t < t1)
        bps.add(t0)
        for t in record:
            if t0 <= t <= t1:
                bps.add(t)
        if dense_until is not None and t0 < dense_until < t1:
            bps.add(dense_until)
        bps = sorted(bps)
        bps.append(t1) if bps[-1] != t1 else None
        x = x0.copy()
        R = R0
        rec = {}
        dense = []
        recset = set(record)
        hmax = LD(hmax)
        self._hsug = hmax
        for i in range(len(bps) - 1):
            b = bps[i]
            if b in recset:
                left = x.copy()
            e = sch.get(b)
            kinds = set()
            if e is not None:
                if tangent is None:
                    x = x + e[0]
                else:
                    x[:, 0] = x[:, 0] + e[0]
                R += e[1]
                kinds = e[2]
            if b in recset:
                rec[b] = (left, x.copy())
            length = ld(bps[i + 1] - b)
            Rl = ld(R)
            want_dense = dense_until is not None and bps[i + 1] <= dense_until
            if not self.mm:
                # linear model: equal fixed steps inside each event interval
                ns = max(1, int(math.ceil(float(length / hmax) - 1e-12)))
                while length / ns > hmax * (1 + LD(1e-9)):
                    ns += 1
                h = length / ns
                for s in range(ns):
                    if tangent is None:
                        c = self.coeffs(x, Rl, h)
                        if want_dense:
                            dense.append((b, s * h, None, h, Rl, x.copy(), c[:, 0].copy(),
                                          c[:, self.iauc].copy(), kinds if s == 0 else set()))
                        x = c[::-1].sum(axis=0)
                    else:
                        c = self.coeffs_tan(x, Rl, h)
                        x = c[::-1].sum(axis=0)
                    self.nsteps += 1
                continue
            # Michaelis-Menten: the series of C/(Km+C) has a finite radius (singularity
            # where C(t) = -Km, distance ~ (Km+C)/|dC/dt|), so the step is limited by the
            # radius estimated from the last two Taylor coefficients (Jorba-Zou rule)
            off = LD(0)
            h = min(self._hsug, hmax)
            first = True
            while True:
                rem = length - off
                if rem <= 0:
                    break
                last = False
                if h >= rem * (1 - LD(1e-12)):
                    h = rem
                    last = True
                elif h > rem / 2:
                    h = rem / 2
                for _try in range(60):
                    if tangent is None:
                        c = self.coeffs(x, Rl, h)
                        hr = self.h_radius(c[:, :self.nx], h)
                    else:
                        c = self.coeffs_tan(x, Rl, h)
                        hr = self.h_radius(c[:, :self.nx, 0], h)
                    if h <= hr * LD('1.02'):
                        break
                    h = hr * LD('0.9')
                    last = False
                    self.nreject += 1
                if tangent is None and want_dense:
                    dense.append((b, off, None, h, Rl, x.copy(), c[:, 0].copy(),
                                  c[:, self.iauc].copy(), kinds if first else set()))
                x = c[::-1].sum(axis=0)
                self.nsteps += 1
                first = False
                off = length if last else off + h
                self._hsug = min(hr, hmax)
                h = self._hsug
        if t1 in recset:
            rec[t1] = (x.copy(), None)
        return {'x': x, 'rec': rec, 'dense': dense, 'R': R}


# ----------------------------------------------------------------------------------------
# Linear algebra in longdouble
# ----------------------------------------------------------------------------------------
def solve_ld(A, b):
    A = A.astype(LD).copy()
    b = b.astype(LD).copy()
    n = len(b)
    for k in range(n):
        p = k + int(np.argmax(np.abs(A[k:, k])))
        if p != k:
            A[[k, p]] = A[[p, k]]
            b[[k, p]] = b[[p, k]]
        if A[k, k] == 0:
            raise ZeroDivisionError('singular')
        f = A[k + 1:, k] / A[k, k]
        A[k + 1:, k:] -= np.outer(f, A[k, k:])
        b[k + 1:] -= f * b[k]
    x = np.zeros(n, LD)
    for k in range(n - 1, -1, -1):
        x[k] = (b[k] - np.dot(A[k, k + 1:], x[k + 1:])) / A[k, k]
    return x


# ----------------------------------------------------------------------------------------
# Dense-output analysis
# ----------------------------------------------------------------------------------------
def horner(c, tau):
    p = c[-1]
    for k in range(len(c) - 2, -1, -1):
        p = p * tau + c[k]
    return p


def dcoef(c):
    K = len(c) - 1
    return c[1:] * np.arange(1, K + 1).astype(LD)


def bisect_root(c, a, b, fa=None):
    """Root of polynomial c on [a, b] (tau units) with sign change; longdouble bisection."""
    if fa is None:
        fa = horner(c, a)
    for _ in range(200):
        m = (a + b) / 2
        if m <= a or m >= b:
            break
        fm = horner(c, m)
        if fm == 0:
            return m
        if (fm > 0) == (fa > 0):
            a, fa = m, fm
        else:
            b = m
    return (a + b) / 2


class Dense:
    """Dense Taylor polynomials of C (and AUC) on a sequence of steps."""

    def __init__(self, sysm, steps, NS):
        self.sys = sysm
        self.steps = steps
        self.NS = NS
        K = sysm.K
        S = len(steps)
        self.S = S
        self.Cc = np.array([st[6] for st in steps], dtype=LD) * sysm.invV1  # (S, K+1)
        self.h = np.array([st[3] for st in steps], dtype=LD)
        self.t0 = np.array([ld(st[0]) + st[1] for st in steps], dtype=LD)
        taus = np.array([LD(i) / NS for i in range(NS + 1)], dtype=LD)
        self.taus = taus
        Vc = np.empty((NS + 1, K + 1), LD)
        for k in range(K + 1):
            Vc[:, k] = taus ** k
        self.vals = self.Cc @ Vc.T
        Dc = self.Cc[:, 1:] * np.arange(1, K + 1).astype(LD)
        self.ders = (Dc @ Vc[:, :K].T) / self.h[:, None]
        # event kinds at step starts
        self.kinds = [st[8] for st in steps]

    def t_of(self, j, tau):
        return self.t0[j] + tau * self.h[j]

    def deriv_rhs(self, j, tau):
        """dC/dt from the right-hand side at the dense state of step j, tau."""
        st = self.steps[j]
        sysm = self.sys
        c = sysm.coeffs(st[5], st[4], st[3])
        x = np.array([horner(c[:, i], tau) for i in range(sysm.n)], dtype=LD)
        return sysm.rhs(x, st[4])[0] * sysm.invV1

    def second_deriv(self, j, tau):
        c = self.Cc[j]
        d2 = dcoef(dcoef(c))
        return horner(d2, tau) / (self.h[j] ** 2)

    def critical_points(self):
        """All interior critical points (bracketed on samples, polished); kind max/min."""
        out = []
        NS = self.NS
        D = self.ders
        for j in range(self.S):
            row = D[j]
            sg = np.sign(row.astype(float))
            idx = np.nonzero(sg[:-1] * sg[1:] < 0)[0]
            for i in idx:
                dc = dcoef(self.Cc[j])
                a = self.taus[i]
                b = self.taus[i + 1]
                r = bisect_root(dc, a, b)
                v = horner(self.Cc[j], r)
                kind = 'max' if row[i] > 0 else 'min'
                out.append((kind, j, r, v))
            # an exact zero at an interior sample
            z = np.nonzero(sg[1:-1] == 0)[0] + 1
            for i in z:
                if sg[i - 1] > 0 and sg[i + 1] < 0:
                    out.append(('max', j, self.taus[i], self.vals[j, i]))
                elif sg[i - 1] < 0 and sg[i + 1] > 0:
                    out.append(('min', j, self.taus[i], self.vals[j, i]))
        return out

    def boundaries(self, t_first_left_value, end_info=True):
        """Step boundaries: (index j of right step or S at end, left val, left der, right val,
        right der, kinds of events at that boundary)."""
        out = []
        NS = self.NS
        for j in range(self.S + 1):
            if j == 0:
                lv, ldv = t_first_left_value, None
            else:
                lv, ldv = self.vals[j - 1, NS], self.ders[j - 1, NS]
            if j < self.S:
                rv, rdv = self.vals[j, 0], self.ders[j, 0]
                kinds = self.kinds[j]
            else:
                rv, rdv, kinds = None, None, set()
            out.append((j, lv, ldv, rv, rdv, kinds))
        return out

    def level_roots(self, level):
        """Roots of C = level within steps (sign change between samples), polished."""
        out = []
        for j in range(self.S):
            g = (self.vals[j] - level)
            sg = np.sign(g.astype(float))
            idx = np.nonzero(sg[:-1] * sg[1:] < 0)[0]
            if len(idx) == 0 and not np.any(sg[1:-1] == 0):
                continue
            c = self.Cc[j].copy()
            c[0] -= level
            for i in idx:
                r = bisect_root(c, self.taus[i], self.taus[i + 1], g[i])
                out.append((j, r))
            for i in np.nonzero(sg[1:-1] == 0)[0] + 1:
                out.append((j, self.taus[i]))
        return out


# ----------------------------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------------------------
def compute(reg, theta, K=30, NS=16):
    tstart = time.time()
    S = System(reg, K)
    hmax = S.hmax(theta)
    S.step_factor = LD(theta) / LD('0.5')
    mt = reg['maintenance']
    st = frac(mt['start'])
    P = frac(mt['period'])
    H = frac(reg['horizon'])
    Pl = ld(P)
    qts = [frac(q) for q in reg['query_times']]
    diag = {'theta': theta, 'K': K, 'hmax': float(hmax), 'rho_max_rate': S.rho, 'rho_lin_1norm': S.rho_lin,
            'lam_mm': S.lam_mm, 'n_states': S.n}

    # ---------------- periodic steady state: Newton on the period map ----------------
    psch = S.build_schedule(S.periodic_events(), Fraction(0), P)
    nx = S.nx

    def pmap_tan(xv):
        X0 = np.zeros((S.n, 1 + nx), LD)
        X0[:nx, 0] = xv
        for i in range(nx):
            X0[i, 1 + i] = 1
        out = S.integrate(psch, Fraction(0), P, X0, hmax, tangent=True)
        X = out['x']
        return X[:nx, 0].copy(), X[:nx, 1:].copy()

    def pmap(xv):
        x0 = np.zeros(S.n, LD)
        x0[:nx] = xv
        out = S.integrate(psch, Fraction(0), P, x0, hmax)
        return out['x'][:nx].copy()

    x = np.zeros(nx, LD)
    hist = []
    prev_step = None
    J = None
    for it in range(60):
        Px, J = pmap_tan(x)
        r = Px - x
        scale = max(float(np.max(np.abs(Px))), 1e-300)
        rn = float(np.max(np.abs(r))) / scale
        A = J - np.eye(nx, dtype=LD)
        dx = solve_ld(A, -r)
        # damping: keep central concentration above -0.5 Km and residual decreasing
        lam = LD(1)
        if S.mm:
            for _ in range(40):
                xn = x + lam * dx
                if xn[0] * S.invV1 > -0.5 * S.Km:
                    break
                lam /= 2
        xnew = x + lam * dx
        stepn = float(np.max(np.abs(lam * dx))) / scale
        hist.append({'iter': it, 'residual_rel': rn, 'step_rel': stepn, 'lambda': float(lam)})
        x = xnew
        if it >= 1 and (stepn < 1e-18 or (prev_step is not None and stepn > 0.5 * prev_step and stepn < 1e-14)):
            break
        prev_step = stepn
    xs = x
    Pjac = J
    # final residual with an independent trajectory-only map
    res_final = pmap(xs) - xs
    diag['newton'] = hist
    diag['fixed_point_residual_rel'] = float(np.max(np.abs(res_final))) / max(float(np.max(np.abs(xs))), 1e-300)
    diag['period_map_spectral_radius'] = float(max(abs(np.linalg.eigvals(Pjac.astype(float)))))

    # ---------------- steady-state window with dense output ----------------
    x0 = np.zeros(S.n, LD)
    x0[:nx] = xs
    wout = S.integrate(psch, Fraction(0), P, x0, hmax, dense_until=P)
    Dw = Dense(S, wout['dense'], NS)
    trough = wout['x'][0] * S.invV1
    trough_from_fp = xs[0] * S.invV1
    ss_cands_max = []
    ss_cands_min = []
    crit = Dw.critical_points()
    for (kind, j, r, v) in crit:
        (ss_cands_max if kind == 'max' else ss_cands_min).append((v, Dw.t_of(j, r), 'crit'))
    bnds = Dw.boundaries(t_first_left_value=trough)
    bolus_prepost = []
    for (j, lv, ldv, rv, rdv, kinds) in bnds:
        if j < Dw.S:
            tb = Dw.t0[j]
        else:
            tb = Pl
        if lv is not None:
            ss_cands_max.append((lv, tb, 'left'))
            ss_cands_min.append((lv, tb, 'left'))
        if rv is not None:
            ss_cands_max.append((rv, tb, 'right'))
            ss_cands_min.append((rv, tb, 'right'))
        if 'bolus' in kinds:
            bolus_prepost.append((float(tb), lv, rv))
    allv = Dw.vals
    ss_cmax = max(max(c[0] for c in ss_cands_max), np.max(allv))
    ss_cmin = min(min(c[0] for c in ss_cands_min), np.min(allv))
    # window crossings and time in window
    low = ldp(reg['window']['low'])
    high = ldp(reg['window']['high'])
    roots = {}
    for lev_name, lev in (('low', low), ('high', high)):
        for (j, r) in Dw.level_roots(lev):
            roots.setdefault(j, []).append((r, lev_name))
    tiw = LD(0)
    crossings = []
    for j in range(Dw.S):
        rs = sorted(roots.get(j, []), key=lambda z: z[0])
        cuts = [LD(0)] + [z[0] for z in rs] + [LD(1)]
        if not rs:
            v = Dw.vals[j]
            if np.all(v >= low) and np.all(v <= high):
                tiw += Dw.h[j]
                continue
            if np.all(v < low) or np.all(v > high):
                continue
        for a, b in zip(cuts[:-1], cuts[1:]):
            if b <= a:
                continue
            vm = horner(Dw.Cc[j], (a + b) / 2)
            if low <= vm <= high:
                tiw += (b - a) * Dw.h[j]
        for (r, nm) in rs:
            dpoly = horner(dcoef(Dw.Cc[j]), r) / Dw.h[j]
            drhs = Dw.deriv_rhs(j, r)
            crossings.append({'t': float(Dw.t_of(j, r)), 'level': nm, 'dCdt_poly': float(dpoly),
                              'dCdt_rhs': float(drhs)})
    ss = {'cmax': ss_cmax, 'cmin': ss_cmin, 'trough': trough, 'tiw': tiw,
          'trough_from_fixed_point': trough_from_fp}

    # ---------------- tail-bound constant B = sup_j ||P^j||_2 (P = period-map Jacobian) ----
    Pf = Pjac.astype(float)
    Qm = np.eye(nx)
    B = 1.0
    Jn = None
    for jj in range(1, 400000):
        Qm = Pf @ Qm
        nrm = np.linalg.norm(Qm, 2)
        if nrm <= 0.5:
            Jn = jj
            break
        B = max(B, nrm)
    if Jn is None:
        B = float('inf')
    cnorm = float(S.invV1)
    trough_f = float(trough)

    def tail_bound(e):
        """Upper bound of |trough_{m+j} - trough| over j >= 0 from the deviation e at t_m."""
        return cnorm * B * float(np.linalg.norm(e.astype(float)))

    STOP = 1e-7 * trough_f   # all later troughs within 1e-7 relative: far inside the 1 % band

    # ---------------- actual regimen: horizon, then cycle by cycle ----------------
    def t_of(mm_):
        return st + mm_ * P

    m_carry = 1
    for d in mt['doses']:
        o = frac(d['offset'])
        if d['route'] == 'iv_infusion':
            ext = frac(d['duration'])
        elif d['route'] == 'oral':
            ext = S.tlag[d['formulation']]
        else:
            ext = Fraction(0)
        m_carry = max(m_carry, int(math.ceil((o + ext) / P)))
    m_a = max(1, int(math.ceil((H - st) / P)), m_carry)
    MDIR = max(61, m_a)
    t_build = t_of(MDIR + 2)
    asch = S.build_schedule(S.actual_events(t_build), Fraction(0), t_build)
    t_m = [t_of(mm_) for mm_ in range(1, m_a + 1)]
    record = set(t_m) | set(qts) | {H}
    aout = S.integrate(asch, Fraction(0), t_of(m_a), np.zeros(S.n, LD), hmax, record=record,
                       dense_until=H)
    rec = aout['rec']
    conc = []
    for q in qts:
        left, right = rec[q]
        xq = right if right is not None else left
        conc.append(xq[0] * S.invV1)
    xH = rec[H][0]
    auc = xH[S.iauc]
    Da = Dense(S, aout['dense'], NS)
    # maxima on [0, H]
    cands = []
    crit_a = Da.critical_points()
    local_max = []
    for (kind, j, r, v) in crit_a:
        if kind == 'max':
            tt = Da.t_of(j, r)
            cands.append((v, tt, 'crit', j, r))
            local_max.append({'t': float(tt), 'C': v, 'type': 'smooth', 'j': j, 'tau': r})
    bnds_a = Da.boundaries(t_first_left_value=LD(0))
    post_bolus = []
    for (j, lv, ldv, rv, rdv, kinds) in bnds_a:
        tb = Da.t0[j] if j < Da.S else ld(H)
        if rv is not None:
            cands.append((rv, tb, 'bnd', j, LD(0)))
        if lv is not None:
            cands.append((lv, tb, 'bndleft', j, LD(0)))
        if 'bolus' in kinds:
            post_bolus.append({'t': float(tb), 'C': rv, 'dC_right': float(rdv)})
        # local maximum at a boundary
        if j == Da.S:
            if ldv is not None and ldv > 0:
                local_max.append({'t': float(tb), 'C': lv, 'type': 'horizon_end'})
            continue
        jump = rv - lv
        tol = 1e3 * EPS * max(abs(rv), LD(1e-300))
        if rdv < 0 and (jump > tol or (ldv is not None and ldv > 0)):
            typ = 'post_bolus' if 'bolus' in kinds else ('kink' if kinds else 'smooth_at_step_boundary')
            local_max.append({'t': float(tb), 'C': rv, 'type': typ, 'kinds': sorted(kinds)})
    cands.append((np.max(Da.vals), None, 'sample', None, None))
    best = max(cands[:-1], key=lambda z: z[0])
    cmax = best[0]
    t_cmax = best[1]
    if np.max(Da.vals) > cmax * (1 + 1e3 * EPS):
        diag['warning_sample_exceeds_candidates'] = True
    # curvature at the maximum if smooth
    max_info = {'kind': best[2], 't': float(t_cmax)}
    if best[2] == 'crit':
        j, r = best[3], best[4]
        c2 = Da.second_deriv(j, r)
        max_info['d2C'] = float(c2)
        max_info['dC_rhs_at_max'] = float(Da.deriv_rhs(j, r))
    else:
        # kinds at that boundary
        jb = best[3]
        kinds = Da.kinds[jb] if (jb is not None and jb < Da.S) else set()
        max_info['event_kinds'] = sorted(kinds)
        if not kinds and best[2] == 'bnd' and jb is not None and jb < Da.S:
            max_info['d2C'] = float(Da.second_deriv(jb, LD(0)))

    res = {
        'concentrations': conc, 'auc': auc, 'cmax': cmax, 't_cmax': t_cmax,
        'ss': ss,
    }

    # ---------------- troughs and n_cycles_to_steady ----------------
    # trough_m = C((start + m period)-): left-limit state recorded at t_m
    troughs = [rec[t][0][0] * S.invV1 for t in t_m]
    xcur_full = aout['x'].copy()
    Rcur = aout['R']
    m = m_a
    # direct simulation of the actual regimen, one cycle per chunk, until the tail bound
    # proves every later trough lies within 1e-7 relative of the steady trough
    while m < MDIR and tail_bound(xcur_full[:nx] - xs) > STOP:
        o = S.integrate(asch, t_of(m), t_of(m + 1), xcur_full, hmax, R0=Rcur)
        xcur_full, Rcur = o['x'], o['R']
        m += 1
        troughs.append(xcur_full[0] * S.invV1)
    m_direct = m
    # cross-check of the periodic-window schedule against the actual-regimen schedule:
    # one more direct cycle m -> m+1 (m >= carry-over cycles) versus the period map
    o = S.integrate(asch, t_of(m), t_of(m + 1), xcur_full, hmax, R0=Rcur)
    x_next_direct = o['x'][:nx]
    x_next_map = pmap(xcur_full[:nx])
    xsc = max(float(np.max(np.abs(xs))), 1e-300)
    diag['cycle_map_vs_actual_rel'] = float(np.max(np.abs(x_next_map - x_next_direct))) / xsc
    diag['cycle_map_check_cycle'] = m_direct
    diag['m_direct'] = m_direct
    diag['last_direct_trough_vs_ss_rel'] = float(abs(troughs[-1] - trough) / trough)
    dev = [abs(tr - trough) - LD('0.01') * trough for tr in troughs]
    tail = {'B_sup_norm_powers': B, 'J_halving': Jn, 'stop_threshold_rel': 1e-7}
    ext_dev = []
    xcur = xcur_full[:nx].copy()
    verified = tail_bound(xcur - xs) <= STOP
    tail['bound_at_m_direct_rel'] = tail_bound(xcur - xs) / trough_f
    nl_ext = 0
    lin_steps = 0
    lin_last_bad = None
    if not verified:
        # cycles beyond MDIR: exact period map (nonlinear) until the deviation is 1e-6
        # relative, then the linearised recursion e <- P e with the bound check
        if S.mm:
            while nl_ext < 600 and float(np.max(np.abs(xcur - xs))) > 1e-6 * xsc \
                    and tail_bound(xcur - xs) > STOP:
                xcur = pmap(xcur)
                nl_ext += 1
                ext_dev.append(abs(xcur[0] * S.invV1 - trough) - LD('0.01') * trough)
        e = xcur - xs
        PL = Pjac
        mlin0 = m_direct + nl_ext
        for jj in range(4000000):
            if tail_bound(e) <= 0.999 * 0.01 * trough_f:
                verified = True
                break
            e = PL @ e
            lin_steps += 1
            dv = abs(e[0] * S.invV1) - LD('0.01') * trough
            if dv > 0:
                lin_last_bad = mlin0 + lin_steps
    tail['nonlinear_extension_cycles'] = nl_ext
    tail['linear_tail_cycles'] = lin_steps
    tail['linear_tail_last_violation_cycle'] = lin_last_bad
    tail['verified_all_later_cycles_inside'] = bool(verified and lin_last_bad is None
                                                    and all(d <= 0 for d in ext_dev))
    alldev = list(dev) + list(ext_dev)
    last_bad = 0
    for i, d in enumerate(alldev):
        if d > 0:
            last_bad = i + 1
    if lin_last_bad is not None:
        last_bad = max(last_bad, lin_last_bad)
    ncyc = last_bad + 1
    res['n_cycles'] = ncyc
    res['troughs'] = troughs
    res['dev'] = dev
    res['ext_dev'] = ext_dev

    # ---------------- guarantee checks (section 2) ----------------
    g = {}
    # G1
    bolus_times = sorted(t for t, e in asch.items() if 'bolus' in e[2])
    g1 = None
    for tq in list(qts) + [H]:
        for tb in bolus_times:
            dd = abs(tq - tb)
            if g1 is None or dd < g1:
                g1 = dd
    g['G1_min_sep_query_horizon_to_bolus_h'] = float(g1) if g1 is not None else None
    g['G1_ok'] = g1 is None or g1 >= Fraction(1, 1000)
    # G2
    lm_vals = sorted([z for z in local_max], key=lambda z: -float(z['C']))
    others = [z for z in lm_vals if abs(float(z['t']) - float(t_cmax)) > 1e-9]
    second = max([float(z['C']) for z in others], default=0.0)
    pb_other = [z for z in post_bolus if abs(z['t'] - float(t_cmax)) > 1e-9]
    pb_max = max([float(z['C']) for z in pb_other], default=0.0)
    g['G2_cmax'] = float(cmax)
    g['G2_max_kind'] = max_info
    g['G2_second_local_max_ratio'] = second / float(cmax)
    g['G2_max_other_post_bolus_ratio'] = pb_max / float(cmax)
    g['G2_n_local_max'] = len(local_max)
    g2ok = second <= (1 - 1e-4) * float(cmax) and pb_max <= (1 - 1e-4) * float(cmax)
    if 'd2C' in max_info and best[2] == 'crit':
        g['G2_curvature_rel'] = abs(max_info['d2C']) / float(cmax)
        g2ok = g2ok and g['G2_curvature_rel'] >= 1e-2
    g['G2_ok'] = bool(g2ok)
    # G3
    sc = float(ss_cmax)
    rel = []
    for wv in (float(low), float(high)):
        for cv in (float(ss_cmin), float(ss_cmax)):
            rel.append(abs(wv - cv) / wv)
    g['G3_window_vs_ss_extrema_min_rel'] = min(rel)
    if crossings:
        mind = min(abs(c['dCdt_rhs']) for c in crossings)
        g['G3_min_abs_dCdt_at_crossing_over_ss_cmax'] = mind / sc
        g['G3_min_abs_dCdt_at_crossing_over_cmax'] = mind / float(cmax)
    else:
        g['G3_min_abs_dCdt_at_crossing_over_ss_cmax'] = None
    pp = []
    for (tb, lv, rv) in bolus_prepost:
        for v in (lv, rv):
            for wv in (float(low), float(high)):
                pp.append(abs(float(v) - wv) / wv)
    g['G3_bolus_prepost_vs_window_min_rel'] = min(pp) if pp else None
    g['G3_n_crossings'] = len(crossings)
    g3ok = min(rel) >= 1e-3 and (not crossings or g['G3_min_abs_dCdt_at_crossing_over_ss_cmax'] >= 1e-3) \
        and (not pp or min(pp) >= 1e-3)
    g['G3_ok'] = bool(g3ok)
    # G4
    # cycles simulated (or mapped) explicitly: alldev; later cycles are covered by the tail
    # bound (|trough_m - trough| <= 1e-7 trough, so the margin there is >= 0.01 - 1e-7)
    margins = [abs(float(d)) / float(trough) for d in alldev[:60]]
    implied = 0.01 - tail['bound_at_m_direct_rel'] if len(alldev) < 60 else None
    g['G4_min_margin_rel_m1_60'] = min(margins + ([implied] if implied is not None else []))
    g['G4_argmin_m'] = int(np.argmin(margins)) + 1
    g['G4_cycles_explicit'] = len(alldev)
    later_ok = all(d <= 0 for d in alldev[59:]) and tail['verified_all_later_cycles_inside']
    g['G4_all_m_ge_60_inside'] = bool(later_ok)
    g['G4_ok'] = bool(g['G4_min_margin_rel_m1_60'] >= 1e-4 and later_ok)
    # G5
    g['G5_ss_cmin'] = float(ss_cmin)
    g['G5_ok'] = bool(ss_cmin > 0 and float(cmax) >= 1e-3 and float(ss_cmax) >= 1e-3)
    diag['guarantees'] = g
    diag['tail'] = tail
    diag['ss_crossings'] = crossings
    diag['local_maxima_top'] = [{'t': z['t'], 'C': float(z['C']), 'type': z['type']} for z in lm_vals[:6]]
    diag['trough_window_vs_fixed_point_rel'] = float(abs(trough - trough_from_fp) / trough)
    diag['taylor_steps'] = S.nsteps
    diag['taylor_rejected_steps'] = S.nreject
    diag['seconds'] = time.time() - tstart
    return res, diag


def domain_check(reg):
    """Section 2/3 domain checks (not the guarantees)."""
    bad = []
    m = reg['model']

    def rng(name, v, lo, hi):
        if not (lo <= v <= hi):
            bad.append('%s=%r outside [%r,%r]' % (name, v, lo, hi))

    rng('V1', m['V1'], 3, 100)
    rng('CL', m['CL'], 0.1, 50)
    if not (0 <= len(m['peripheral']) <= 2):
        bad.append('peripheral count')
    for p in m['peripheral']:
        rng('Q', p['Q'], 0.1, 100)
        rng('V', p['V'], 1, 500)
    if m['Vmax'] != 0:
        rng('Vmax', m['Vmax'], 0.5, 500)
    rng('Km', m['Km'], 0.05, 50)
    fs = reg['formulations']
    if not (1 <= len(fs) <= 2):
        bad.append('formulation count')
    for i, f in enumerate(fs):
        if f['id'] != i + 1:
            bad.append('formulation id order')
        rng('F', f['F'], 0.1, 1)
        rng('ka', f['ka'], 0.1, 5)
        rng('tlag', f['tlag'], 0, 2)
        rng('n_transit', f['n_transit'], 0, 5)
        rng('ktr', f['ktr'], 0.5, 10)
    mt = reg['maintenance']
    rng('start', mt['start'], 0, 72)
    rng('period', mt['period'], 4, 168)
    if not (1 <= len(mt['doses']) <= 6):
        bad.append('maintenance dose count')
    ld_ = reg['loading_doses']
    if not (0 <= len(ld_) <= 4):
        bad.append('loading dose count')
    st = frac(mt['start'])
    for d in ld_ + mt['doses']:
        rng('amount', d['amount'], 1, 5000)
        if d['route'] == 'iv_infusion':
            rng('duration', d['duration'], 0.1, 24)
    for d in ld_:
        t = frac(d['time'])
        if not (0 <= t <= st):
            bad.append('loading time outside [0,start]')
        if d['route'] == 'iv_infusion' and t + frac(d['duration']) > st:
            bad.append('loading infusion ends after start')
    P = frac(mt['period'])
    for d in mt['doses']:
        if not (0 <= frac(d['offset']) < P):
            bad.append('offset outside [0,period)')
    H = frac(reg['horizon'])
    if not (st + P <= H <= 360):
        bad.append('horizon outside [start+period,360]')
    q = reg['query_times']
    if not (3 <= len(q) <= 10):
        bad.append('query count')
    for t in q:
        if not (0 <= frac(t) <= H):
            bad.append('query time outside [0,horizon]')
    w = reg['window']
    if not (0 < w['low'] < w['high']):
        bad.append('window')
    return bad


def to_report(reg, res):
    ss = res['ss']
    return {
        'regimen_id': reg['regimen_id'],
        'concentrations': [float(v) for v in res['concentrations']],
        'auc': float(res['auc']),
        'cmax': float(res['cmax']),
        't_cmax': float(res['t_cmax']),
        'steady_state': {
            'cmax': float(ss['cmax']),
            'cmin': float(ss['cmin']),
            'trough': float(ss['trough']),
            'time_in_window': float(ss['tiw']),
            'n_cycles_to_steady': int(res['n_cycles']),
        },
    }


def compare(rA, rB):
    """Differences between two runs (A coarse, B fine)."""
    S = float(rB['cmax'])
    out = {}
    out['concentrations_absdiff_over_cmax'] = [float(abs(a - b)) / S for a, b in
                                               zip(rA['concentrations'], rB['concentrations'])]
    out['concentrations_max_over_cmax'] = max(out['concentrations_absdiff_over_cmax'])
    out['auc_rel'] = float(abs(rA['auc'] - rB['auc']) / abs(rB['auc']))
    out['cmax_over_cmax'] = float(abs(rA['cmax'] - rB['cmax'])) / S
    out['t_cmax_h'] = float(abs(rA['t_cmax'] - rB['t_cmax']))
    for k in ('cmax', 'cmin', 'trough'):
        out['ss_' + k + '_over_cmax'] = float(abs(rA['ss'][k] - rB['ss'][k])) / S
    out['time_in_window_h'] = float(abs(rA['ss']['tiw'] - rB['ss']['tiw']))
    out['n_cycles_equal'] = rA['n_cycles'] == rB['n_cycles']
    tr = float(rB['ss']['trough'])
    out['troughs_direct_max_absdiff_over_trough'] = max(float(abs(a - b)) / tr for a, b in
                                                       zip(rA['troughs'][:60], rB['troughs'][:60]))
    rels = [out['concentrations_max_over_cmax'], out['auc_rel'], out['cmax_over_cmax'],
            out['ss_cmax_over_cmax'], out['ss_cmin_over_cmax'], out['ss_trough_over_cmax']]
    out['max_rel_value_diff'] = max(rels)
    out['max_time_diff_h'] = max(out['t_cmax_h'], out['time_in_window_h'])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--regimen', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--check', default=None)
    ap.add_argument('--theta', type=float, default=0.5)
    ap.add_argument('--order', type=int, default=30)
    ap.add_argument('--single', action='store_true', help='one run only (no halving check)')
    args = ap.parse_args()
    with open(args.regimen, encoding='utf-8') as f:
        reg = json.load(f)
    t0 = time.time()
    if args.single:
        rB, dB = compute(reg, args.theta, args.order)
        cmpd = None
        dA = None
    else:
        rA, dA = compute(reg, args.theta, args.order)
        rB, dB = compute(reg, args.theta / 2, args.order)
        cmpd = compare(rA, rB)
    rep = to_report(reg, rB)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(rep, f, indent=1)
        f.write('\n')
    if args.check:
        chk = {
            'regimen_id': reg['regimen_id'],
            'method': 'Taylor series order %d, longdouble, fixed step min(theta/rho, 2 theta) per '
                      'event interval; reported run theta=%g, comparison run theta=%g'
                      % (args.order, args.theta / 2, args.theta),
            'error_estimates_half_step': cmpd,
            'fine_run': dB,
            'coarse_run': dA,
            'domain_violations': domain_check(reg),
            'troughs_fine_direct': [float(v) for v in rB['troughs']],
            'trough_condition_dev_over_trough_direct': [float(d / rB['ss']['trough']) for d in rB['dev']],
            'total_seconds': time.time() - t0,
        }
        with open(args.check, 'w', encoding='utf-8') as f:
            json.dump(chk, f, indent=1, default=lambda o: float(o) if isinstance(o, (np.floating,)) else str(o))
            f.write('\n')


if __name__ == '__main__':
    main()
