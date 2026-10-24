#!/usr/bin/env python3
"""Second-integrator cross-check: scipy solve_ivp DOP853 (rtol 1e-12 and 1e-13).

  python tests/crosscheck_dop853.py STRUCT.json REPORT.json [--max-states 8]

Recomputes T at the queried energies and at the reported maxima, and refines
up to --max-states bound states (first, last, spread) by brentq on the matching
residual, integrating the ODE with DOP853 layer by layer (renormalised at every
interface).  Prints the largest deviation from the report for each rtol."""
from __future__ import annotations

import argparse
import json
import math
import warnings

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

C = 0.0380998212
warnings.filterwarnings("ignore", category=RuntimeWarning)


class Dop:
    def __init__(self, st, rtol):
        self.st = st
        self.rtol = rtol
        self.L = st["layers"]
        self.x = np.concatenate([[0.0], np.cumsum([l["thickness_nm"] for l in self.L])])

    def _layer(self, j, y0, E, direction, cplx):
        L = self.L[j]
        m, vl, vr, d = L["mass"], L["vl_eV"], L["vr_eV"], L["thickness_nm"]
        g = (vr - vl) / d
        x0 = self.x[j]

        def f(x, y):
            V = vl + g * (x - x0)
            q = (V - E) / C
            if cplx:
                return [m * y[2], m * y[3], q * y[0], q * y[1]]
            return [m * y[1], q * y[0]]

        a, b = (self.x[j], self.x[j + 1]) if direction > 0 else (self.x[j + 1], self.x[j])
        sol = solve_ivp(f, (a, b), y0, method="DOP853", rtol=self.rtol, atol=1e-300)
        y = sol.y[:, -1]
        return y / np.max(np.abs(y)), math.log(np.max(np.abs(y)))

    def T(self, E):
        st = self.st
        mL, VL = st["left_lead"]["mass"], st["left_lead"]["v_eV"]
        mR, VR = st["right_lead"]["mass"], st["right_lead"]["v_eV"]
        kL = math.sqrt(mL * (E - VL) / C)
        kR = math.sqrt(mR * (E - VR) / C)
        y = np.array([1.0, 0.0, 0.0, kR / mR])
        logs = 0.0
        for j in range(len(self.L) - 1, -1, -1):
            y, ls = self._layer(j, y, E, -1, True)
            logs += ls
        psi = y[0] + 1j * y[1]
        phi = y[2] + 1j * y[3]
        A = 0.5 * (psi + phi * mL / (1j * kL))
        return (kR / mR) / (kL / mL) / abs(A) ** 2 * math.exp(-2 * logs)

    def resid(self, E):
        st = self.st
        mL, VL = st["left_lead"]["mass"], st["left_lead"]["v_eV"]
        mR, VR = st["right_lead"]["mass"], st["right_lead"]["v_eV"]
        N = len(self.L)
        jmin = min(range(N), key=lambda j: min(self.L[j]["vl_eV"], self.L[j]["vr_eV"]))
        km = jmin if self.L[jmin]["vl_eV"] <= self.L[jmin]["vr_eV"] else jmin + 1
        yl = np.array([1.0, math.sqrt(mL * (VL - E) / C) / mL])
        for j in range(km):
            yl, _ = self._layer(j, yl, E, +1, False)
        yr = np.array([1.0, -math.sqrt(mR * (VR - E) / C) / mR])
        for j in range(N - 1, km - 1, -1):
            yr, _ = self._layer(j, yr, E, -1, False)
        s = math.sqrt(C * self.L[min(km, N - 1)]["mass"])
        return s * (yl[0] * yr[1] - yl[1] * yr[0]) / (math.hypot(yl[0], s * yl[1]) * math.hypot(yr[0], s * yr[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("structure")
    ap.add_argument("report")
    ap.add_argument("--max-states", type=int, default=8)
    a = ap.parse_args()
    st = json.load(open(a.structure))
    rep = json.load(open(a.report))
    bs = [b["E_eV"] for b in rep["bound_states"]]
    if len(bs) > a.max_states:
        idx = sorted(set(np.linspace(0, len(bs) - 1, a.max_states).round().astype(int)))
    else:
        idx = list(range(len(bs)))
    for rtol in (1e-12, 1e-13):
        D = Dop(st, rtol)
        tr = max([abs(D.T(t["E_eV"]) / t["T"] - 1) for t in rep["transmission"]], default=0.0)
        mx = max([abs(D.T(t["E_eV"]) / t["T"] - 1) for t in rep["maxima"]], default=0.0)
        dE = 0.0
        for i in idx:
            e = bs[i]
            w = 2e-9
            while D.resid(e - w) * D.resid(e + w) > 0 and w < 1e-5:
                w *= 10
            r = brentq(D.resid, e - w, e + w, xtol=1e-15, rtol=8.9e-16)
            dE = max(dE, abs(r - e))
        print(f"{st['structure_id']} DOP853 rtol={rtol:.0e}: T_rel={tr:.1e} T_at_maxima_rel={mx:.1e} "
              f"bound_dE={dE:.1e} ({len(idx)} of {len(bs)} states)")


if __name__ == "__main__":
    main()
