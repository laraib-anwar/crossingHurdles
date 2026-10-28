#!/usr/bin/env python
"""framefreq.py - static analysis, natural frequencies and harmonic response of plane frames.

Reads a frame file (nodes with supports and lumped masses, members, loads, queries) and writes
the nodal displacements, the lowest natural frequencies, the number of frequencies below a limit
and the harmonic response amplitudes.

Method
------
Each member is one standard two-node frame finite element (axial bar plus cubic Hermite beam).
Uniform member loads are converted to statically equivalent nodal forces (half the load to each
end). The mass of each member is lumped: half of it at each end node on the translational
degrees of freedom, as is customary for frame vibration estimates; lumped nodal masses are added.
Natural frequencies are the eigenvalues of the resulting generalized eigenvalue problem, and the
harmonic response is the solution of (K - omega^2 M) U = F.

usage: framefreq.py --frame <frame.json> --output <report.json>
"""
import argparse
import json
import math

import numpy as np
from scipy.linalg import eigh


def member_matrices(E, A, I, rho, L, cx, cy):
    k = E * I / L ** 3
    K = np.array([
        [E * A / L, 0, 0, -E * A / L, 0, 0],
        [0, 12 * k, 6 * k * L, 0, -12 * k, 6 * k * L],
        [0, 6 * k * L, 4 * k * L * L, 0, -6 * k * L, 2 * k * L * L],
        [-E * A / L, 0, 0, E * A / L, 0, 0],
        [0, -12 * k, -6 * k * L, 0, 12 * k, -6 * k * L],
        [0, 6 * k * L, 2 * k * L * L, 0, -6 * k * L, 4 * k * L * L]])
    m = rho * A * L / 2
    M = np.diag([m, m, 0.0, m, m, 0.0])
    T = np.zeros((6, 6))
    for b in (0, 3):
        T[b, b], T[b, b + 1], T[b + 1, b], T[b + 1, b + 1], T[b + 2, b + 2] = cx, cy, -cy, cx, 1.0
    return T.T @ K @ T, M


def build(d):
    nodes = {n["id"]: (n["x"], n["y"]) for n in d["nodes"]}
    N = len(d["nodes"])
    K = np.zeros((3 * N, 3 * N))
    M = np.zeros((3 * N, 3 * N))
    F = np.zeros(3 * N)
    for m in d["members"]:
        xi, yi = nodes[m["i"]]
        xj, yj = nodes[m["j"]]
        L = math.hypot(xj - xi, yj - yi)
        cx, cy = (xj - xi) / L, (yj - yi) / L
        Ke, Me = member_matrices(m["E"], m["A"], m["I"], m["rho"], L, cx, cy)
        idx = [3 * (m["i"] - 1), 3 * (m["i"] - 1) + 1, 3 * (m["i"] - 1) + 2, 3 * (m["j"] - 1), 3 * (m["j"] - 1) + 1, 3 * (m["j"] - 1) + 2]
        K[np.ix_(idx, idx)] += Ke
        M[np.ix_(idx, idx)] += Me
    for n in d["nodes"]:
        M[3 * (n["id"] - 1), 3 * (n["id"] - 1)] += n["mass_kg"]
        M[3 * (n["id"] - 1) + 1, 3 * (n["id"] - 1) + 1] += n["mass_kg"]
    for ld in d["nodal_loads"]:
        b = 3 * (ld["node"] - 1)
        F[b] += ld["Fx"]
        F[b + 1] += ld["Fy"]
        F[b + 2] += ld["Mz"]
    by_id = {m["id"]: m for m in d["members"]}
    for ld in d["member_loads"]:
        m = by_id[ld["member"]]
        xi, yi = nodes[m["i"]]
        xj, yj = nodes[m["j"]]
        L = math.hypot(xj - xi, yj - yi)
        for nid in (m["i"], m["j"]):
            F[3 * (nid - 1)] += ld["wx"] * L / 2
            F[3 * (nid - 1) + 1] += ld["wy"] * L / 2
    free = [3 * (n["id"] - 1) + k for n in d["nodes"] for k, dof in enumerate(("ux", "uy", "rz")) if not n["support"][dof]]
    return K, M, F, free, N


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frame", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    with open(a.frame, encoding="utf-8") as fh:
        d = json.load(fh)
    K, M, F, free, N = build(d)
    Kf, Mf, Ff = K[np.ix_(free, free)], M[np.ix_(free, free)], F[free]
    u = np.zeros(3 * N)
    u[free] = np.linalg.solve(Kf, Ff)
    static = [dict(node=n, ux=float(u[3 * (n - 1)]), uy=float(u[3 * (n - 1) + 1]), rz=float(u[3 * (n - 1) + 2])) for n in d["static_query_nodes"]]
    # massless rotational dofs: condense them statically
    has_mass = np.diag(Mf) > 0
    im, i0 = np.flatnonzero(has_mass), np.flatnonzero(~has_mass)
    Kc = Kf[np.ix_(im, im)] - Kf[np.ix_(im, i0)] @ np.linalg.solve(Kf[np.ix_(i0, i0)], Kf[np.ix_(i0, im)])
    w2 = eigh(Kc, Mf[np.ix_(im, im)], eigvals_only=True)
    freqs = [math.sqrt(max(w, 0.0)) / (2 * math.pi) for w in w2]
    n_modes = d["n_modes"]
    frequencies = (freqs + [freqs[-1]] * n_modes)[:n_modes]
    count_below = int(sum(1 for f in freqs if f <= d["f_max_Hz"]))
    harmonic = []
    for q in d["harmonic_queries"]:
        omega = 2 * math.pi * q["f_Hz"]
        Fh = np.zeros(3 * N)
        Fh[3 * (q["load_node"] - 1) + ("ux", "uy", "rz").index(q["load_dof"])] = q["amplitude"]
        uh = np.zeros(3 * N)
        uh[free] = np.linalg.solve(Kf - omega * omega * Mf, Fh[free])
        harmonic.append(dict(load_node=q["load_node"], load_dof=q["load_dof"], amplitude=q["amplitude"], f_Hz=q["f_Hz"],
                             response_node=q["response_node"], response_dof=q["response_dof"],
                             U=float(uh[3 * (q["response_node"] - 1) + ("ux", "uy", "rz").index(q["response_dof"])])))
    rep = dict(frame_id=d["frame_id"], static=static, frequencies_Hz=frequencies, count_below=count_below, harmonic=harmonic)
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
