#!/usr/bin/env python
"""qwell.py - quantum-well levels and tunnelling transmission of a heterostructure.

Reads a structure file (layers with effective masses and band-edge profile, leads, transmission
energies and an energy window) and writes the bound states, the transmission coefficients and
the transmission maxima.

Method
------
The electron effective mass is taken as that of the left contact throughout, the usual
approximation for GaAs-based structures. Bound states come from a finite-difference
discretisation of the Schrodinger equation on a uniform 0.1 nm grid extending 10 nm into each
contact, with the wavefunction set to zero at the ends of the grid; the eigenvalues below the
lower contact band edge are the levels. Transmission uses the transfer-matrix method with plane
waves in piecewise-constant regions; graded or biased layers are approximated by five flat steps
each, and the transmission coefficient is the squared modulus of the transmitted amplitude. The
transmission maxima are read off a 1 meV scan of the window.

usage: qwell.py --structure <structure.json> --output <report.json>
"""
import argparse
import json
import math

import numpy as np
from scipy.linalg import eigh_tridiagonal

C = 0.0380998212
STEPS = 5


def potential_at(layers, VL, VR, x):
    if x < 0:
        return VL
    pos = 0.0
    for ly in layers:
        if x < pos + ly["thickness_nm"]:
            f = (x - pos) / ly["thickness_nm"]
            return ly["vl_eV"] + f * (ly["vr_eV"] - ly["vl_eV"])
        pos += ly["thickness_nm"]
    return VR


def bound_states(d):
    m = d["left_lead"]["mass"]
    VL, VR = d["left_lead"]["v_eV"], d["right_lead"]["v_eV"]
    X = sum(ly["thickness_nm"] for ly in d["layers"])
    h = 0.1
    xs = np.arange(-10.0 + h, X + 10.0, h)
    V = np.array([potential_at(d["layers"], VL, VR, x) for x in xs])
    t = C / (m * h * h)
    w = eigh_tridiagonal(V + 2 * t, -t * np.ones(len(xs) - 1), eigvals_only=True)
    E_th = min(VL, VR)
    return [float(e) for e in w if e < E_th]


def staircase(d):
    regions = []
    for ly in d["layers"]:
        if ly["vl_eV"] == ly["vr_eV"]:
            regions.append((ly["thickness_nm"], ly["vl_eV"]))
        else:
            for i in range(STEPS):
                v = ly["vl_eV"] + (ly["vr_eV"] - ly["vl_eV"]) * (i + 0.5) / STEPS
                regions.append((ly["thickness_nm"] / STEPS, v))
    return regions


def transmission(d, E):
    m = d["left_lead"]["mass"]
    VL, VR = d["left_lead"]["v_eV"], d["right_lead"]["v_eV"]
    regions = [(0.0, VL)] + staircase(d) + [(0.0, VR)]
    k = [np.sqrt(complex(m * (E - v) / C)) for _, v in regions]
    M = np.eye(2, dtype=complex)
    x = 0.0
    for j in range(len(regions) - 1):
        x += regions[j][0] if j > 0 else 0.0
        k1, k2 = k[j], k[j + 1]
        # interface matrix (amplitudes of e^{ikx}, e^{-ikx}) at position x, equal masses
        A1 = np.array([[np.exp(1j * k1 * x), np.exp(-1j * k1 * x)], [1j * k1 * np.exp(1j * k1 * x), -1j * k1 * np.exp(-1j * k1 * x)]])
        A2 = np.array([[np.exp(1j * k2 * x), np.exp(-1j * k2 * x)], [1j * k2 * np.exp(1j * k2 * x), -1j * k2 * np.exp(-1j * k2 * x)]])
        M = np.linalg.solve(A2, A1) @ M
    # outgoing only on the right: [t, 0] = M [1, r]
    r = -M[1, 0] / M[1, 1]
    t = M[0, 0] + M[0, 1] * r
    return float(abs(t) ** 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--structure", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    with open(a.structure, encoding="utf-8") as fh:
        d = json.load(fh)
    bs = [dict(E_eV=E) for E in bound_states(d)]
    tr = [dict(E_eV=E, T=transmission(d, E)) for E in d["transmission_energies_eV"]]
    E_lo, E_hi = d["window_eV"]
    grid = np.arange(E_lo, E_hi + 1e-12, 1e-3)
    Tg = [transmission(d, E) for E in grid]
    mx = [dict(E_eV=float(grid[k]), T=Tg[k]) for k in range(1, len(grid) - 1) if Tg[k] > Tg[k - 1] and Tg[k] >= Tg[k + 1]]
    rep = dict(structure_id=d["structure_id"], bound_states=bs, transmission=tr, maxima=mx)
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
