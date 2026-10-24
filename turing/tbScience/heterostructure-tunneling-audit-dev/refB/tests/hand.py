#!/usr/bin/env python3
"""Hand-derived reference answers for the three closed-form test structures.

These closed forms are used ONLY to verify Ref B; referee.py never uses them.

  barrier  : one rectangular barrier (split over two identical layers) between
             leads of different mass and band edge.  Matching psi and psi'/m at
             both interfaces gives, with q_j = k_j / m_j and k_2 possibly imaginary,
                 t = 2 i q1 / [ i (q1 + q3) cos(k2 d) + (q1 q3 / q2 + q2) sin(k2 d) ]
                 T = (q3 / q1) |t|^2
                   = 4 q1 q3 / [ (q1+q3)^2 cos^2(k2 d) + (q1 q3/q2 + q2)^2 sin^2(k2 d) ].
             The last form is an even function of k2 (entire in E), so it is
             evaluated in complex arithmetic for both tunnelling and above-barrier E.
  well     : finite square well of width L (mass m_w) in barrier material (m_b, V0).
             With a = L/2, k = sqrt(m_w E / C), kappa = sqrt(m_b (V0 - E) / C):
                 even:  (k/m_w) sin(k a) - (kappa/m_b) cos(k a) = 0
                 odd :  (k/m_w) cos(k a) + (kappa/m_b) sin(k a) = 0
             (both written without poles).  Transmission is the single-layer
             formula above with the well as the layer; with identical leads the
             maxima are T = 1 exactly at k_w L = n pi.
  triangle : biased triangular well: two sloped layers (different masses, a band
             offset between them) between leads.  Inside a sloped layer
             psi = a Ai(z) + b Bi(z), z = lambda (xi + (vl - E)/g), lambda^3 = m g / C;
             the layer matrix is F(z1) F(z0)^-1 with F = [[Ai, Bi], [lambda Ai'/m, lambda Bi'/m]].
             Bound states: zeros of phi(X) + (kappa_R/m_R) psi(X) for the solution
             starting as exp(kappa_L x); found by a dense scan plus brentq.

Maxima energies: roots of dT/dE.  T(E) extends to a holomorphic function
T_h(E) = K(E) / (A(E) * conj(A(conj E))) (or the real-analytic closed form);
dT/dE is taken from the Cauchy integral on a circle of radius rho around E
(trapezoid rule, exponentially convergent), and brentq finds its zero.
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np
from scipy.optimize import brentq
from scipy.special import airy

C = 0.0380998212
HERE = os.path.dirname(os.path.abspath(__file__))
SDIR = os.path.join(HERE, "structures")
HDIR = os.path.join(HERE, "hand_reports")


# ------------------------------------------------------------------ structures
def lead(m, v):
    return {"mass": m, "v_eV": v}


def layer(d, m, vl, vr=None):
    return {"thickness_nm": d, "mass": m, "vl_eV": vl, "vr_eV": vl if vr is None else vr}


HAND_STRUCTURES = {
    # rectangular barrier, 5.5 nm split 3.0 + 2.5, masses 0.067 | 0.092 | 0.080, band edges 0 | 0.32 | -0.05
    "hand_barrier": {
        "structure_id": "hand_barrier",
        "left_lead": lead(0.067, 0.0),
        "right_lead": lead(0.080, -0.05),
        "layers": [layer(3.0, 0.092, 0.32), layer(2.5, 0.092, 0.32)],
        "transmission_energies_eV": [0.02, 0.1, 0.2, 0.3, 0.33, 0.5],
        "window_eV": [0.40, 1.30],
    },
    # finite square well 10 nm, m_w = 0.067, barrier m_b = 0.092, V0 = 0.35
    "hand_well": {
        "structure_id": "hand_well",
        "left_lead": lead(0.092, 0.35),
        "right_lead": lead(0.092, 0.35),
        "layers": [layer(4.0, 0.092, 0.35), layer(10.0, 0.067, 0.0), layer(5.0, 0.092, 0.35)],
        "transmission_energies_eV": [0.36, 0.40, 0.55, 0.80],
        "window_eV": [0.40, 1.20],
    },
    # square well tuned so that the 4th level sits ~1.5e-4 eV below E_th (guarantee 1 edge)
    "hand_well_edge": {
        "structure_id": "hand_well_edge",
        "left_lead": lead(0.092, 0.35),
        "right_lead": lead(0.092, 0.35),
        "layers": [layer(3.0, 0.092, 0.35), layer(12.06, 0.067, 0.0), layer(3.5, 0.092, 0.35)],
        "transmission_energies_eV": [0.351, 0.36, 0.5],
        "window_eV": [0.36, 0.9],
    },
    # biased triangular well: slope 0.02 eV/nm in both layers, offset 0.30 eV at x = 18 nm
    "hand_triangle": {
        "structure_id": "hand_triangle",
        "left_lead": lead(0.092, 0.90),
        "right_lead": lead(0.067, 0.40),
        "layers": [layer(18.0, 0.067, 0.0, 0.36), layer(6.0, 0.092, 0.66, 0.78)],
        "transmission_energies_eV": [0.91, 1.0, 1.2, 1.5],
        "window_eV": [0.95, 1.65],
    },
}


# ------------------------------------------------------------------ closed forms
def k_of(m, E, V):
    return np.sqrt(m * (np.asarray(E, dtype=complex) - V) / C)


def T_single(E, mL, VL, m2, V2, d, mR, VR):
    """Closed-form single-layer T, holomorphic in E (complex E allowed)."""
    q1 = k_of(mL, E, VL) / mL
    q3 = k_of(mR, E, VR) / mR
    k2 = k_of(m2, E, V2)
    q2 = k2 / m2
    c = np.cos(k2 * d)
    # (q1 q3 / q2 + q2) sin(k2 d) written with sin(k2 d)/k2 to stay entire in k2^2
    sk = np.sinc(k2 * d / np.pi) * d          # sin(k2 d) / k2
    s_term = q1 * q3 * m2 * sk + (k2 * k2 / m2) * sk
    return 4 * q1 * q3 / ((q1 + q3) ** 2 * c * c + s_term * s_term)


def airy_F(z, lam, m):
    ai, aip, bi, bip = airy(z)
    return np.array([[ai, bi], [lam * aip / m, lam * bip / m]])


def layer_matrix(E, L):
    """Closed-form (psi, phi) transfer matrix across one layer, rightwards."""
    d, m, vl, vr = L["thickness_nm"], L["mass"], L["vl_eV"], L["vr_eV"]
    if vl == vr:
        k = np.sqrt(m * (complex(E) - vl) / C)
        c = np.cos(k * d)
        sk = np.sinc(k * d / np.pi) * d     # sin(kd)/k
        return np.array([[c, m * sk], [-(k * k / m) * sk, c]])
    g = (vr - vl) / d
    lam = np.cbrt(m * g / C)
    z0 = lam * ((vl - E) / g)
    z1 = lam * (d + (vl - E) / g)
    F0 = airy_F(z0, lam, m)
    F1 = airy_F(z1, lam, m)
    return F1 @ np.linalg.inv(F0)


def total_matrix(E, st):
    M = np.eye(2, dtype=complex)
    for L in st["layers"]:
        M = layer_matrix(E, L) @ M
    return M


def T_general(E, st):
    """Holomorphic continuation of T for the general closed-form route."""
    mL, VL = st["left_lead"]["mass"], st["left_lead"]["v_eV"]
    mR, VR = st["right_lead"]["mass"], st["right_lead"]["v_eV"]

    def A_of(Ec):
        kL = np.sqrt(mL * (Ec - VL) / C)
        kR = np.sqrt(mR * (Ec - VR) / C)
        M = total_matrix(Ec, st)
        Minv = np.array([[M[1, 1], -M[0, 1]], [-M[1, 0], M[0, 0]]]) / (M[0, 0] * M[1, 1] - M[0, 1] * M[1, 0])
        v0 = Minv @ np.array([1.0, 1j * kR / mR])
        return 0.5 * (v0[0] + v0[1] * mL / (1j * kL)), kL, kR

    Ec = complex(E)
    A, kL, kR = A_of(Ec)
    Ab = np.conj(A_of(np.conj(Ec))[0])
    K = (kR / mR) / (kL / mL)
    return K / (A * Ab)


def dT_cauchy(f, E, rho=2e-3, n=32):
    w = np.exp(2j * np.pi * (np.arange(n) + 0.5) / n)
    vals = np.array([f(E + rho * wj) for wj in w])
    return float(np.real(np.mean(vals / (rho * w))))


def maxima_of(Tfun, Elo, Ehi, step=2e-4, rho=2e-3):
    grid = np.linspace(Elo, Ehi, int(round((Ehi - Elo) / step)) + 1)
    d = np.array([dT_cauchy(Tfun, e, rho) for e in grid])
    out = []
    for i in range(len(grid) - 1):
        if d[i] > 0 and d[i + 1] < 0:
            r = brentq(lambda e: dT_cauchy(Tfun, e, rho), grid[i], grid[i + 1], xtol=1e-15, rtol=8.9e-16)
            out.append((r, float(np.real(Tfun(r)))))
    return out


def well_bound(V0, mw, mb, Lw):
    a = Lw / 2

    def fe(E):
        k = math.sqrt(mw * E / C)
        kap = math.sqrt(mb * (V0 - E) / C)
        return (k / mw) * math.sin(k * a) - (kap / mb) * math.cos(k * a)

    def fo(E):
        k = math.sqrt(mw * E / C)
        kap = math.sqrt(mb * (V0 - E) / C)
        return (k / mw) * math.cos(k * a) + (kap / mb) * math.sin(k * a)

    roots = []
    grid = np.linspace(1e-12, V0 - 1e-12, 20001)
    for f in (fe, fo):
        vals = [f(e) for e in grid]
        for i in range(len(grid) - 1):
            if vals[i] * vals[i + 1] < 0:
                roots.append(brentq(f, grid[i], grid[i + 1], xtol=1e-16, rtol=8.9e-16))
    return sorted(roots)


def general_bound(st):
    mL, VL = st["left_lead"]["mass"], st["left_lead"]["v_eV"]
    mR, VR = st["right_lead"]["mass"], st["right_lead"]["v_eV"]
    Eth = min(VL, VR)
    Vmin = min(min(L["vl_eV"], L["vr_eV"]) for L in st["layers"])

    def f(E):
        kL = math.sqrt(mL * (VL - E) / C)
        kR = math.sqrt(mR * (VR - E) / C)
        M = np.real(total_matrix(E, st))
        v = M @ np.array([1.0, kL / mL])
        # normalised so that the sign is meaningful and the size bounded
        return (v[1] + (kR / mR) * v[0]) / math.hypot(v[0], v[1])

    grid = np.linspace(Vmin + 1e-9, Eth - 1e-9, 40001)
    vals = [f(e) for e in grid]
    roots = []
    for i in range(len(grid) - 1):
        if vals[i] * vals[i + 1] < 0:
            roots.append(brentq(f, grid[i], grid[i + 1], xtol=1e-16, rtol=8.9e-16))
    return roots


def hand_report(sid):
    st = HAND_STRUCTURES[sid]
    mL, VL = st["left_lead"]["mass"], st["left_lead"]["v_eV"]
    mR, VR = st["right_lead"]["mass"], st["right_lead"]["v_eV"]
    Elo, Ehi = st["window_eV"]
    extra = {}
    if sid == "hand_barrier":
        L = st["layers"][0]
        d = sum(x["thickness_nm"] for x in st["layers"])
        Tf = lambda E: T_single(E, mL, VL, L["mass"], L["vl_eV"], d, mR, VR)
        bound = []
    elif sid in ("hand_well", "hand_well_edge"):
        W = st["layers"][1]
        Tf = lambda E: T_single(E, mL, VL, W["mass"], W["vl_eV"], W["thickness_nm"], mR, VR)
        bound = well_bound(VL, W["mass"], mL, W["thickness_nm"])
        n = np.arange(1, 40)
        Eres = C * (n * np.pi / W["thickness_nm"]) ** 2 / W["mass"]
        extra["analytic_maxima_T1"] = [float(e) for e in Eres if Elo < e < Ehi]
    else:
        Tf = lambda E: T_general(E, st)
        bound = general_bound(st)
    trans = [{"E_eV": e, "T": float(np.real(Tf(e)))} for e in st["transmission_energies_eV"]]
    mx = maxima_of(Tf, Elo, Ehi)
    rep = {"structure_id": sid,
           "bound_states": [{"E_eV": float(e)} for e in bound],
           "transmission": trans,
           "maxima": [{"E_eV": float(e), "T": float(t)} for e, t in mx]}
    # cross-check of the general Airy/trig route against the single-layer formula
    if sid in ("hand_barrier", "hand_well", "hand_well_edge"):
        extra["route_check_T_rel"] = max(abs(float(np.real(T_general(e, st))) / float(np.real(Tf(e))) - 1)
                                         for e in st["transmission_energies_eV"])
        if sid in ("hand_well", "hand_well_edge"):
            gb = general_bound(st)
            extra["route_check_bound_dE"] = max(abs(a - b) for a, b in zip(gb, bound)) if len(gb) == len(bound) else None
    return rep, extra


def main():
    os.makedirs(SDIR, exist_ok=True)
    os.makedirs(HDIR, exist_ok=True)
    only = sys.argv[1:]
    for sid, st in HAND_STRUCTURES.items():
        if only and sid not in only:
            continue
        with open(os.path.join(SDIR, sid + ".json"), "w") as fh:
            json.dump(st, fh, indent=1)
            fh.write("\n")
        rep, extra = hand_report(sid)
        with open(os.path.join(HDIR, sid + ".json"), "w") as fh:
            json.dump(rep, fh, indent=1)
            fh.write("\n")
        print(sid, "bound:", [round(b["E_eV"], 12) for b in rep["bound_states"]])
        print("   T:", [f"{t['T']:.15g}" for t in rep["transmission"]])
        print("   maxima:", [(round(m["E_eV"], 12), f"{m['T']:.15g}") for m in rep["maxima"]])
        if extra:
            print("   extra:", extra)


if __name__ == "__main__":
    main()
