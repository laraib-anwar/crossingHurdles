#!/usr/bin/env python
"""regimencalc.py - plasma concentrations, exposure and steady state of a dosing regimen.

Reads a regimen file (compartment model, formulations, loading doses, maintenance cycle, horizon,
query times, therapeutic window) and writes the concentrations at the query times, the AUC and
peak over the horizon, and the steady-state peak, trough, time in window and number of cycles to
steady state.

Method
------
Linear superposition. The disposition matrix of the mammillary model is diagonalised once; each
dose contributes an exponential sum from its administration time. Saturable elimination is
represented by its first-order equivalent CL + Vmax/Km. Oral doses enter an absorption depot at
the dosing time with the formulation's rate constant ka (absorption lag and transit are second-
order effects and are not modelled). Infusions are handled with the short-infusion approximation
(dose placed at the infusion start). Peak, AUC (linear trapezoid) and time in window are evaluated
on a 0.1 h grid. Steady state is the 20th maintenance cycle; the number of cycles to steady state
follows from the terminal rate constant, ln(100) / (k_term * period).

usage: regimencalc.py --regimen <regimen.json> --output <report.json>
"""
import argparse
import json
import math

import numpy as np

DT = 0.1
N_SS = 20


def system(d):
    m = d["model"]
    forms = d["formulations"]
    n = 1 + len(m["peripheral"]) + len(forms)
    A = np.zeros((n, n))
    cl_eff = m["CL"] + (m["Vmax"] / m["Km"] if m["Vmax"] > 0 else 0.0)
    A[0, 0] = -cl_eff / m["V1"]
    for k, p in enumerate(m["peripheral"], start=1):
        A[0, 0] -= p["Q"] / m["V1"]
        A[0, k] = p["Q"] / p["V"]
        A[k, 0] = p["Q"] / m["V1"]
        A[k, k] = -p["Q"] / p["V"]
    slot = {}
    for i, f in enumerate(forms):
        s = 1 + len(m["peripheral"]) + i
        slot[f["id"]] = s
        A[s, s] = -f["ka"]
        A[0, s] = f["ka"]
    lam, V = np.linalg.eig(A)
    Vinv = np.linalg.inv(V)
    return lam, V, Vinv, slot, m["V1"], {f["id"]: f for f in forms}


def impulses(d, doses, times, slot, forms, n):
    """Unit impulse vectors (state increments) for a list of doses at the given times."""
    out = []
    for dose, t in zip(doses, times):
        b = np.zeros(n)
        if dose["route"] == "oral":
            b[slot[dose["formulation"]]] = forms[dose["formulation"]]["F"] * dose["amount"]
        else:
            b[0] = dose["amount"]
        out.append((t, b))
    return out


def conc_on(ts, imps, lam, V, Vinv, V1):
    """Concentration at the times ts from the superposition of impulse responses."""
    C = np.zeros(len(ts))
    row = V[0, :]
    for t0, b in imps:
        coef = row * (Vinv @ b)
        tau = ts - t0
        mask = tau >= 0
        C[mask] += np.real(np.exp(np.outer(tau[mask], lam)) @ coef)
    return C / V1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regimen", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    with open(a.regimen, encoding="utf-8") as fh:
        d = json.load(fh)
    lam, V, Vinv, slot, V1, forms = system(d)
    n = len(lam)
    mt = d["maintenance"]
    start, period, horizon = mt["start"], mt["period"], d["horizon"]
    n_cyc = int(math.ceil((horizon - start) / period)) + 1
    doses = list(d["loading_doses"]) + [dict(dd, time=start + m * period + dd["offset"]) for m in range(n_cyc) for dd in mt["doses"]]
    imps = impulses(d, doses, [dd["time"] for dd in doses], slot, forms, n)
    grid = np.arange(0.0, horizon + DT / 2, DT)
    grid[-1] = min(grid[-1], horizon)
    Cg = conc_on(grid, imps, lam, V, Vinv, V1)
    conc = conc_on(np.array(d["query_times"], dtype=float), imps, lam, V, Vinv, V1)
    auc = float(np.trapz(Cg, grid))
    k = int(np.argmax(Cg))
    # steady state: maintenance cycles alone, 20th cycle
    sdoses = [dict(dd, time=m * period + dd["offset"]) for m in range(N_SS) for dd in mt["doses"]]
    simps = impulses(d, sdoses, [dd["time"] for dd in sdoses], slot, forms, n)
    sgrid = np.arange((N_SS - 1) * period, N_SS * period + DT / 2, DT)
    Cs = conc_on(sgrid, simps, lam, V, Vinv, V1)
    low, high = d["window"]["low"], d["window"]["high"]
    tiw = float(np.sum((Cs[:-1] >= low) & (Cs[:-1] <= high)) * DT)
    k_term = float(min(-np.real(lam)))
    n_cycles = int(math.ceil(math.log(100.0) / (k_term * period)))
    rep = dict(regimen_id=d["regimen_id"], concentrations=[float(c) for c in conc], auc=auc,
               cmax=float(Cg[k]), t_cmax=float(grid[k]),
               steady_state=dict(cmax=float(Cs.max()), cmin=float(Cs.min()), trough=float(Cs[-1]),
                                 time_in_window=tiw, n_cycles_to_steady=max(1, n_cycles)))
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
