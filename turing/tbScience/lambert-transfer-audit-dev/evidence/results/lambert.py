#!/usr/bin/env python
"""Keplerian ephemerides and complete multi-revolution Lambert transfers (LAMBERT_SPEC.md).

Ephemerides: Kepler's equation in the eccentric or hyperbolic anomaly (Newton-Halley from a safe
start, mean anomaly wrapped first) and the perifocal-to-inertial rotation. Lambert: Izzo's
formulation in the Lancaster-Blanchard variable x with lambda = +-sqrt(1 - c/s) (sign from the
prograde transfer angle), the dimensionless time of flight evaluated by the Lagrange form away
from x = 1 and by Battin's hypergeometric series near it, Householder (third order) iterations
started from Izzo's initial guesses, the N-revolution minimum from Halley on dT/dx = 0, and
velocities from the radial/tangential decomposition. Every root is polished to machine precision.

usage: lambert.py --system <system.json> --output <report.json>
"""
import argparse
import json
import math
from fractions import Fraction

import numpy as np

DAY = 86400.0


# ------------------------------------------------------------------ Kepler propagation
def elapsed_s(t_from_days, t_to_days):
    """86400 (t_to - t_from) with the difference of the two given doubles formed exactly."""
    return float((Fraction(t_to_days) - Fraction(t_from_days)) * 86400)


def kepler_E(M, e):
    """Eccentric anomaly for mean anomaly M (any real) and 0 <= e < 1."""
    M = math.fmod(M, 2 * math.pi)
    if M < 0:
        M += 2 * math.pi
    E = M + e * math.sin(M) if e < 0.8 else math.pi
    for _ in range(60):
        f = E - e * math.sin(E) - M
        fp = 1 - e * math.cos(E)
        fpp = e * math.sin(E)
        d = -f / fp
        d = -f / (fp + 0.5 * d * fpp)          # Halley
        E += d
        if abs(d) < 1e-15:
            break
    # final Newton clean-up
    for _ in range(2):
        E -= (E - e * math.sin(E) - M) / (1 - e * math.cos(E))
    return E


def kepler_H(M, e):
    """Hyperbolic anomaly for hyperbolic mean anomaly M and e > 1."""
    H = math.asinh(M / e) if abs(M) > 1 else M / (e - 1) if abs(M / (e - 1)) < 1 else math.asinh(M / e)
    for _ in range(80):
        f = e * math.sinh(H) - H - M
        fp = e * math.cosh(H) - 1
        fpp = e * math.sinh(H)
        d = -f / fp
        d = -f / (fp + 0.5 * d * fpp)
        if abs(d) > 1.0:
            d = math.copysign(1.0, d)
        H += d
        if abs(d) < 1e-15:
            break
    for _ in range(2):
        H -= (e * math.sinh(H) - H - M) / (e * math.cosh(H) - 1)
    return H


def rotation(i, Om, om):
    ci, si = math.cos(i), math.sin(i)
    cO, sO = math.cos(Om), math.sin(Om)
    co, so = math.cos(om), math.sin(om)
    return np.array([
        [cO * co - sO * so * ci, -cO * so - sO * co * ci, sO * si],
        [sO * co + cO * so * ci, -sO * so + cO * co * ci, -cO * si],
        [so * si, co * si, ci],
    ])


class Body:
    def __init__(self, d, mu):
        self.name = d["name"]
        self.mu = mu
        self.a, self.e = float(d["a_km"]), float(d["e"])
        self.t0_days = d["t0_days"]
        self.M0 = math.radians(d["M0_deg"])
        self.R = rotation(math.radians(d["i_deg"]), math.radians(d["Omega_deg"]), math.radians(d["omega_deg"]))
        self.n = math.sqrt(mu / abs(self.a) ** 3)

    def state(self, t_days):
        M = self.M0 + self.n * elapsed_s(self.t0_days, t_days)
        a, e, mu = self.a, self.e, self.mu
        if e < 1:
            E = kepler_E(M, e)
            cE, sE = math.cos(E), math.sin(E)
            r = a * (1 - e * cE)
            x, y = a * (cE - e), a * math.sqrt(1 - e * e) * sE
            fac = math.sqrt(mu * a) / r
            vx, vy = -fac * sE, fac * math.sqrt(1 - e * e) * cE
        else:
            H = kepler_H(M, e)
            cH, sH = math.cosh(H), math.sinh(H)
            r = -a * (e * cH - 1)                       # a < 0
            x, y = -a * (e - cH), -a * math.sqrt(e * e - 1) * sH
            fac = math.sqrt(-mu * a) / r
            vx, vy = -fac * sH, fac * math.sqrt(e * e - 1) * cH
        rp = np.array([x, y, 0.0])
        vp = np.array([vx, vy, 0.0])
        return self.R @ rp, self.R @ vp


# ------------------------------------------------------------------ Lambert (Izzo 2015)
def hypergeometric_F(z, tol=1e-16):
    """2F1(3, 1; 5/2; z) by its series (|z| < 1)."""
    Sj, Cj, j = 1.0, 1.0, 0.0
    while True:
        Cj1 = Cj * (3.0 + j) * (1.0 + j) / (2.5 + j) * z / (j + 1.0)
        Sj1 = Sj + Cj1
        if abs(Cj1) < tol or j > 1e4:
            return Sj1
        Sj, Cj, j = Sj1, Cj1, j + 1.0


def x2tof(x, lam, N):
    """Dimensionless time of flight T(x) for the Lancaster-Blanchard variable x."""
    battin, lagrange = 0.01, 0.2
    dist = abs(x - 1.0)
    if dist < lagrange and dist > battin:
        # Lagrange form
        a = 1.0 / (1.0 - x * x)
        if a > 0:
            alfa = 2.0 * math.acos(x)
            beta = 2.0 * math.asin(math.sqrt(lam * lam / a))
            if lam < 0:
                beta = -beta
            tof = a * math.sqrt(a) * ((alfa - math.sin(alfa)) - (beta - math.sin(beta)) + 2.0 * math.pi * N) / 2.0
        else:
            alfa = 2.0 * math.acosh(x)
            beta = 2.0 * math.asinh(math.sqrt(-lam * lam / a))
            if lam < 0:
                beta = -beta
            tof = -a * math.sqrt(-a) * ((beta - math.sinh(beta)) - (alfa - math.sinh(alfa))) / 2.0
        return tof
    K = lam * lam
    E = x * x - 1.0
    rho = abs(E)
    z = math.sqrt(1 + K * E)
    if dist < battin:
        # Battin series
        eta = z - lam * x
        S1 = 0.5 * (1.0 - lam - x * eta)
        Q = hypergeometric_F(S1)
        Q = 4.0 / 3.0 * Q
        return (eta ** 3 * Q + 4.0 * lam * eta) / 2.0 + N * math.pi / (rho ** 1.5)
    # Lancaster-Blanchard form
    y = math.sqrt(rho)
    g = x * z - lam * E
    if E < 0:
        l = math.acos(g)
        d = N * math.pi + l
    else:
        f = y * (z - lam * x)
        d = math.log(f + g)
    return (x - lam * z - d / y) / E


def dTdx(x, T, lam):
    """First, second and third derivatives of T(x) (Izzo eqs. 22)."""
    l2 = lam * lam
    l3 = l2 * lam
    umx2 = 1.0 - x * x
    y = math.sqrt(1.0 - l2 * umx2)
    y2 = y * y
    y3 = y2 * y
    DT = 1.0 / umx2 * (3.0 * T * x - 2.0 + 2.0 * l3 * x / y)
    DDT = 1.0 / umx2 * (3.0 * T + 5.0 * x * DT + 2.0 * (1.0 - l2) * l3 / y3)
    DDDT = 1.0 / umx2 * (7.0 * x * DDT + 8.0 * DT - 6.0 * (1.0 - l2) * l2 * l3 * x / y3 / y2)
    return DT, DDT, DDDT


def householder(T, x0, N, lam, eps=1e-15, iters=60):
    x = x0
    for _ in range(iters):
        tof = x2tof(x, lam, N)
        DT, DDT, DDDT = dTdx(x, tof, lam)
        delta = tof - T
        DT2 = DT * DT
        xnew = x - delta * (DT2 - delta * DDT / 2.0) / (DT * (DT2 - delta * DDT) + DDDT * delta * delta / 6.0)
        err = abs(x - xnew)
        x = xnew
        if err < eps:
            break
    # final Newton polish on the residual
    for _ in range(3):
        tof = x2tof(x, lam, N)
        DT = dTdx(x, tof, lam)[0]
        if DT != 0:
            x -= (tof - T) / DT
    return x


def halley_tmin(lam, N, x0=0.0, iters=60, eps=1e-15):
    """x at which T(x) is minimal for N revolutions (dT/dx = 0)."""
    x = x0
    for _ in range(iters):
        tof = x2tof(x, lam, N)
        DT, DDT, DDDT = dTdx(x, tof, lam)
        if DT == 0.0:
            break
        xnew = x - DT * DDT / (DDT * DDT - DT * DDDT / 2.0)
        err = abs(x - xnew)
        x = xnew
        if err < eps:
            break
    return x, x2tof(x, lam, N)


def lambert(r1, r2, tof, mu, n_max):
    """All prograde solutions with 0 <= N <= n_max. Returns (theta, t_min list (s), solutions)."""
    r1 = np.asarray(r1, float)
    r2 = np.asarray(r2, float)
    c_vec = r2 - r1
    c, R1, R2 = np.linalg.norm(c_vec), np.linalg.norm(r1), np.linalg.norm(r2)
    s = 0.5 * (R1 + R2 + c)
    ir1, ir2 = r1 / R1, r2 / R2
    ih = np.cross(ir1, ir2)
    lam2 = 1.0 - c / s
    lam = math.sqrt(lam2)
    cos_theta = float(np.dot(ir1, ir2))
    cos_theta = max(-1.0, min(1.0, cos_theta))
    sin_theta = float(np.linalg.norm(ih))
    theta = math.atan2(sin_theta, cos_theta)       # in (0, pi)
    if ih[2] < 0:                                  # transfer angle > pi for a prograde arc
        theta = 2 * math.pi - theta
        lam = -lam
        it1 = np.cross(ir1, ih)
        it2 = np.cross(ir2, ih)
    else:
        it1 = np.cross(ih, ir1)
        it2 = np.cross(ih, ir2)
    it1 /= np.linalg.norm(it1)
    it2 /= np.linalg.norm(it2)
    T = math.sqrt(2.0 * mu / s ** 3) * tof
    scale = 1.0 / math.sqrt(2.0 * mu / s ** 3)    # seconds per unit of T
    xs = []                                        # (N, x)
    # N = 0
    T00 = math.acos(lam) + lam * math.sqrt(1.0 - lam2)
    T0 = T00                                       # T at x = 0 for N = 0
    T1 = 2.0 / 3.0 * (1.0 - lam2 * lam)            # parabolic
    if T >= T0:
        x0 = (T0 / T) ** (2.0 / 3.0) - 1.0
    elif T <= T1:
        x0 = 5.0 / 2.0 * T1 / T * (T1 - T) / (1.0 - lam2 * lam2 * lam) + 1.0
    else:
        x0 = (T0 / T) ** (math.log(T1 / T0) / math.log(2.0)) - 1.0
    xs.append((0, householder(T, x0, 0, lam)))
    tmins = []
    for N in range(1, n_max + 1):
        x_tm, T_min = halley_tmin(lam, N)
        tmins.append(T_min * scale)
        if T > T_min:
            tmp = ((N * math.pi + math.pi) / (8.0 * T)) ** (2.0 / 3.0)
            x_left = (tmp - 1.0) / (tmp + 1.0)
            tmp = ((8.0 * T) / (N * math.pi)) ** (2.0 / 3.0)
            x_right = (tmp - 1.0) / (tmp + 1.0)
            xl = householder(T, x_left, N, lam)
            xr = householder(T, x_right, N, lam)
            xs.append((N, xl))
            xs.append((N, xr))
    gamma = math.sqrt(mu * s / 2.0)
    rho = (R1 - R2) / c
    sigma = math.sqrt(1.0 - rho * rho)
    sols = []
    for N, x in xs:
        y = math.sqrt(1.0 - lam2 + lam2 * x * x)
        vr1 = gamma * ((lam * y - x) - rho * (lam * y + x)) / R1
        vr2 = -gamma * ((lam * y - x) + rho * (lam * y + x)) / R2
        vt = gamma * sigma * (y + lam * x)
        vt1, vt2 = vt / R1, vt / R2
        v1 = vr1 * ir1 + vt1 * it1
        v2 = vr2 * ir2 + vt2 * it2
        # polish the arc: a from x, e from the state
        a = s / (2.0 * (1.0 - x * x))
        hv = np.cross(r1, v1)
        ev = (np.cross(v1, hv) / mu) - ir1
        e = float(np.linalg.norm(ev))
        a_vv = 1.0 / (2.0 / R1 - float(np.dot(v1, v1)) / mu)
        sols.append(dict(N=N, x=x, v1=v1, v2=v2, a=a_vv, e=e))
    return theta, tmins, sols


# ------------------------------------------------------------------ report
def solve(d):
    mu = float(d["mu_km3_s2"])
    bodies = {o["name"]: Body(o, mu) for o in d["objects"]}
    eph = []
    for q in d["ephemeris_queries"]:
        r, v = bodies[q["object"]].state(float(q["t_days"]))
        eph.append(dict(object=q["object"], t_days=q["t_days"], r_km=[float(x) for x in r], v_km_s=[float(x) for x in v]))
    trans = []
    for q in d["transfer_queries"]:
        rA, vA = bodies[q["from"]].state(float(q["t1_days"]))
        rB, vB = bodies[q["to"]].state(float(q["t2_days"]))
        tof = elapsed_s(q["t1_days"], q["t2_days"])
        theta, tmins, sols = lambert(rA, rB, tof, mu, int(q["n_max"]))
        out = []
        by_N = {}
        for s_ in sols:
            by_N.setdefault(s_["N"], []).append(s_)
        for N in sorted(by_N):
            group = sorted(by_N[N], key=lambda s_: s_["a"])
            labels = ["single"] if N == 0 else ["low", "high"]
            for lab, s_ in zip(labels, group):
                dv = float(np.linalg.norm(s_["v1"] - vA) + np.linalg.norm(vB - s_["v2"]))
                out.append(dict(N=N, branch=lab, v1_km_s=[float(x) for x in s_["v1"]], v2_km_s=[float(x) for x in s_["v2"]],
                                a_km=float(s_["a"]), e=float(s_["e"]), dv_km_s=dv))
        best = min(range(len(out)), key=lambda k: out[k]["dv_km_s"])
        trans.append(dict(**{"from": q["from"]}, t1_days=q["t1_days"], to=q["to"], t2_days=q["t2_days"], n_max=q["n_max"],
                          theta_deg=math.degrees(theta), t_min_days=[t / DAY for t in tmins], solutions=out, best=best))
    return dict(system_id=d["system_id"], ephemeris=eph, transfers=trans)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    with open(a.system, encoding="utf-8") as fh:
        d = json.load(fh)
    rep = solve(d)
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
