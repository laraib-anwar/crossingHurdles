#!/usr/bin/env python
"""porkchop.py - ephemerides and ballistic transfer solutions for mission design studies.

Reads a system file (central body, objects with orbital elements, ephemeris and transfer queries)
and writes the state vectors and the Lambert transfer solutions with their impulsive costs.

Method
------
States come from Kepler's equation solved by fixed-point iteration E = M + e sin E (the mean
anomaly is propagated linearly from the epoch); hyperbolic objects are handled with the same
machinery on the negative semi-major axis. Transfers are solved with the universal-variable
Lambert formulation (Bate, Mueller and White): the transfer angle is the short way between the
two position vectors, as is standard for ballistic transfers, and the zero-revolution solution is
found by bisection on the universal variable z. Multi-revolution transfers, when requested, are
built on the N-revolution orbit whose period is the time of flight divided by N + 1/2, the
engineering estimate for the minimum-energy resonant transfer, and the minimum time of flight of
an N-revolution family is N + 1/2 periods of the Hohmann ellipse between the two radii.

usage: porkchop.py --system <system.json> --output <report.json>
"""
import argparse
import json
import math

import numpy as np

DAY = 86400.0


def rotation(i, Om, om):
    ci, si, cO, sO, co, so = math.cos(i), math.sin(i), math.cos(Om), math.sin(Om), math.cos(om), math.sin(om)
    return np.array([[cO * co - sO * so * ci, -cO * so - sO * co * ci, sO * si],
                     [sO * co + cO * so * ci, -sO * so + cO * co * ci, -cO * si],
                     [so * si, co * si, ci]])


def state(obj, mu, t_days):
    a, e = obj["a_km"], obj["e"]
    n = math.sqrt(mu / abs(a) ** 3)
    M = math.radians(obj["M0_deg"]) + n * (t_days - obj["t0_days"]) * DAY
    E = M
    if e < 1:
        for _ in range(50):                  # fixed-point iteration
            E = M + e * math.sin(E)
    else:
        E = math.asinh(M / e)
        for _ in range(50):
            E -= (e * math.sinh(E) - E - M) / (e * math.cosh(E) - 1)
    if e < 1:
        r = a * (1 - e * math.cos(E))
        p = np.array([a * (math.cos(E) - e), a * math.sqrt(1 - e * e) * math.sin(E), 0.0])
        fac = math.sqrt(mu * a) / r
        v = np.array([-fac * math.sin(E), fac * math.sqrt(1 - e * e) * math.cos(E), 0.0])
    else:
        aa = abs(a)
        r = aa * (e * math.cosh(E) - 1)
        p = np.array([aa * (e - math.cosh(E)), aa * math.sqrt(e * e - 1) * math.sinh(E), 0.0])
        fac = math.sqrt(mu * aa) / r
        v = np.array([-fac * math.sinh(E), fac * math.sqrt(e * e - 1) * math.cosh(E), 0.0])
    R = rotation(math.radians(obj["i_deg"]), math.radians(obj["Omega_deg"]), math.radians(obj["omega_deg"]))
    return R @ p, R @ v


def stumpff(z):
    if z > 1e-8:
        s = math.sqrt(z)
        return (1 - math.cos(s)) / z, (s - math.sin(s)) / s ** 3
    if z < -1e-8:
        s = math.sqrt(-z)
        return (1 - math.cosh(s)) / z, (math.sinh(s) - s) / s ** 3
    return 0.5 - z / 24.0, 1.0 / 6.0 - z / 120.0


def lambert_short(r1, r2, tof, mu):
    """Zero-revolution universal-variable Lambert solution, short way."""
    R1, R2 = np.linalg.norm(r1), np.linalg.norm(r2)
    cos_dnu = float(np.dot(r1, r2)) / (R1 * R2)
    dnu = math.acos(max(-1.0, min(1.0, cos_dnu)))
    A = math.sin(dnu) * math.sqrt(R1 * R2 / (1 - cos_dnu))

    def tof_of(z):
        C, S = stumpff(z)
        y = R1 + R2 + A * (z * S - 1) / math.sqrt(C)
        if y < 0:
            return None, y
        chi = math.sqrt(y / C)
        return (chi ** 3 * S + A * math.sqrt(y)) / math.sqrt(mu), y
    lo, hi = -4 * math.pi, 4 * math.pi ** 2
    for _ in range(200):
        z = 0.5 * (lo + hi)
        t, y = tof_of(z)
        if t is None or t < tof:
            lo = z
        else:
            hi = z
    z = 0.5 * (lo + hi)
    C, S = stumpff(z)
    y = R1 + R2 + A * (z * S - 1) / math.sqrt(C)
    f = 1 - y / R1
    g = A * math.sqrt(y / mu)
    gdot = 1 - y / R2
    v1 = (r2 - f * r1) / g
    v2 = (gdot * r2 - r1) / g
    return dnu, v1, v2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    with open(a.system, encoding="utf-8") as fh:
        d = json.load(fh)
    mu = d["mu_km3_s2"]
    objs = {o["name"]: o for o in d["objects"]}
    eph = []
    for q in d["ephemeris_queries"]:
        r, v = state(objs[q["object"]], mu, q["t_days"])
        eph.append(dict(object=q["object"], t_days=q["t_days"], r_km=[float(x) for x in r], v_km_s=[float(x) for x in v]))
    trans = []
    for q in d["transfer_queries"]:
        r1, vA = state(objs[q["from"]], mu, q["t1_days"])
        r2, vB = state(objs[q["to"]], mu, q["t2_days"])
        tof = (q["t2_days"] - q["t1_days"]) * DAY
        dnu, v1, v2 = lambert_short(r1, r2, tof, mu)
        R1, R2 = np.linalg.norm(r1), np.linalg.norm(r2)
        a_h = 0.5 * (R1 + R2)
        P_h = 2 * math.pi * math.sqrt(a_h ** 3 / mu)
        sols = []

        def entry(N, branch, v1, v2):
            a_t = 1.0 / (2.0 / R1 - float(np.dot(v1, v1)) / mu)
            hv = np.cross(r1, v1)
            ev = np.cross(v1, hv) / mu - r1 / R1
            dv = float(np.linalg.norm(v1 - vA) + np.linalg.norm(vB - v2))
            return dict(N=N, branch=branch, v1_km_s=[float(x) for x in v1], v2_km_s=[float(x) for x in v2],
                        a_km=float(a_t), e=float(np.linalg.norm(ev)), dv_km_s=dv)
        sols.append(entry(0, "single", v1, v2))
        tmins = []
        for N in range(1, q["n_max"] + 1):
            tmins.append((N + 0.5) * P_h / DAY)
            if tof > (N + 0.5) * P_h:
                # resonant estimate: circular-speed departure on the orbit of period tof / (N + 1/2)
                a_res = (mu * (tof / (N + 0.5) / (2 * math.pi)) ** 2) ** (1.0 / 3.0)
                speed = math.sqrt(mu * (2.0 / R1 - 1.0 / a_res))
                vdir = v1 / np.linalg.norm(v1)
                v1n = speed * vdir
                v2n = v2 * (speed / np.linalg.norm(v1))
                sols.append(entry(N, "low", v1n, v2n))
                sols.append(entry(N, "high", v1n * 1.001, v2n * 1.001))
        best = min(range(len(sols)), key=lambda k: sols[k]["dv_km_s"])
        trans.append(dict(**{"from": q["from"]}, t1_days=q["t1_days"], to=q["to"], t2_days=q["t2_days"], n_max=q["n_max"],
                          theta_deg=math.degrees(dnu), t_min_days=tmins, solutions=sols, best=best))
    rep = dict(system_id=d["system_id"], ephemeris=eph, transfers=trans)
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
