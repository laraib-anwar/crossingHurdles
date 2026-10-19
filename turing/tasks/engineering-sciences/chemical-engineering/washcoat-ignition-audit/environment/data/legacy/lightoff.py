#!/usr/bin/env python3
"""lightoff.py - washcoat light-off estimator (aftertreatment group, rev 4).

Same command line and report layout as the new program:

    python lightoff.py --recipe <recipe.json> --output <report.json>

Method (unchanged since rev 2). The film is thin compared with the washcoat, so the exposed face
is taken at bulk-gas conditions (c = 1, theta = 0) and the layer obeys theta + beta c = beta.
For a wall concentration c0 the reactant equation c'' = phi^2 c R(beta (1 - c)) is integrated
from the wall in the stretched coordinate xi = phi x until c reaches 1; the xi reached is the
Thiele modulus of that steady state. Sweeping c0 over a grid gives the steady-state curve; its
turning points on the grid are the ignition and extinction points. States at a given phi are
read off the curve by linear interpolation. Stability follows the usual slope rule: on an
S-shaped curve the middle state is the unstable one, the outer two are stable.
"""
import argparse
import json
import math

import numpy as np
from scipy.integrate import solve_ivp

N_GRID = 120


def curve(beta, gamma):
    """(phi, theta_c, eta) on a grid of wall concentrations, Dirichlet face."""
    R = lambda th: np.exp(gamma * th / (1.0 + th))
    out = []
    for c0 in np.concatenate([np.logspace(-12, -1, N_GRID // 2), np.linspace(0.1, 0.999, N_GRID // 2)]):
        def rhs(xi, y):
            c = y[0]
            return [y[1], c * R(beta * (1.0 - c))]

        def hit(xi, y):
            return y[0] - 1.0
        hit.terminal, hit.direction = True, 1.0
        s = solve_ivp(rhs, (0.0, 1e4), [c0, 0.0], events=hit, rtol=1e-8, atol=1e-14, max_step=1.0)
        if not s.t_events[0].size:
            continue
        phi = float(s.t_events[0][0])
        dc = float(s.y_events[0][0][1])              # dc/dxi at the face
        eta = dc / phi                               # (dc/dx)/phi^2 with dc/dx = phi dc/dxi
        out.append((phi, beta * (1.0 - c0), eta))
    out.sort(key=lambda p: p[1])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    with open(a.recipe, encoding="utf-8") as fh:
        r = json.load(fh)
    pts = curve(float(r["beta"]), float(r["gamma"]))
    ph = [p[0] for p in pts]
    folds = []
    for i in range(1, len(pts) - 1):
        if (ph[i] - ph[i - 1]) * (ph[i + 1] - ph[i]) < 0.0 and r["phi_min"] < ph[i] < r["phi_max"]:
            kind = "ignition" if ph[i] > ph[i - 1] else "extinction"
            folds.append(dict(phi=ph[i], theta_c=pts[i][1], eta=pts[i][2], kind=kind))
    folds.sort(key=lambda f: f["phi"])
    states = []
    for q in r["phi_query"]:
        br = []
        for i in range(len(pts) - 1):
            p0, p1 = pts[i], pts[i + 1]
            if (p0[0] - q) * (p1[0] - q) <= 0.0 and p0[0] != p1[0]:
                w = (q - p0[0]) / (p1[0] - p0[0])
                br.append([p0[1] + w * (p1[1] - p0[1]), p0[2] + w * (p1[2] - p0[2])])
        br.sort()
        n = len(br)
        rows = []
        for k, (th, eta) in enumerate(br):
            stab = "unstable_real" if (n == 3 and k == 1) else "stable"
            rows.append(dict(theta_c=th, eta=eta, stability=stab))
        states.append(dict(phi=q, branches=rows))
    rep = dict(recipe_id=r["recipe_id"], folds=folds, hopf_points=[], states=states)
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
