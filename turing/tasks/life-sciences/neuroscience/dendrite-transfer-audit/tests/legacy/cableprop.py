#!/usr/bin/env python
"""cableprop.py - electrotonic properties of a reconstructed dendritic tree.

Reads a neuron file (soma, cylindrical segments with their passive parameters and terminal
conditions, query locations) and writes the steady-state input resistances, attenuation factors,
transfer impedances and the equalization time constants with their somatic coefficients.

Method
------
The tree is reduced to Rall's equivalent cylinder: at every branch point the daughters obey the
3/2 power rule closely enough that the tree is replaced by one cylinder of the trunk diameter and
of the mean electrotonic path length to the terminals, with sealed ends. Input resistances are
the loaded-cable value at the electrotonic distance of the site along the equivalent cylinder;
attenuation between two sites is exp(-X/lambda) of the electrotonic distance between them (the
infinite-cable law, which the semi-infinite equivalent cylinder follows closely); transfer
impedances are those of the lumped RC circuit (R_in, tau_m) between the two sites. The time
constants are Rall's equalizing time constants of the equivalent cylinder with soma,
tau_n = tau_m / (1 + (n pi / L_eq)^2), with the coefficients of the finite-cylinder step response,
C_n = R_in * 2 / (1 + (n pi / L_eq)^2) (C_0 = R_in for the uniform mode), rescaled so that they
sum to R_in.

usage: cableprop.py --neuron <neuron.json> --output <report.json>
"""
import argparse
import json
import math


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--neuron", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    with open(a.neuron, encoding="utf-8") as fh:
        d = json.load(fh)
    segs = {s["id"]: s for s in d["segments"]}
    for s in segs.values():
        s["lam"] = math.sqrt(s["Rm_ohm_cm2"] * s["d_um"] * 1e-4 / (4 * s["Ri_ohm_cm"]))      # cm
        s["X"] = s["L_um"] * 1e-4 / s["lam"]
        s["tau"] = s["Rm_ohm_cm2"] * s["Cm_uF_cm2"] * 1e-3                                   # ms
        s["children"] = []
    for s in segs.values():
        if s["parent"]:
            segs[s["parent"]]["children"].append(s)
    trunks = [s for s in segs.values() if s["parent"] == 0]

    def X_from_soma(loc):
        if loc["segment"] == 0:
            return 0.0
        s = segs[loc["segment"]]
        x = s["X"] * loc["fraction"]
        while s["parent"]:
            s = segs[s["parent"]]
            x += s["X"]
        return x

    # equivalent cylinder: trunk diameter by the 3/2 rule, mean electrotonic length to the tips
    d_eq = sum(s["d_um"] ** 1.5 for s in trunks) ** (2.0 / 3.0)
    Rm = sum(s["Rm_ohm_cm2"] for s in segs.values()) / len(segs)
    Ri = sum(s["Ri_ohm_cm"] for s in segs.values()) / len(segs)
    Cm = sum(s["Cm_uF_cm2"] for s in segs.values()) / len(segs)
    tips = [s for s in segs.values() if not s["children"]]
    L_eq = sum(X_from_soma({"segment": s["id"], "fraction": 1.0}) for s in tips) / len(tips)
    lam_eq = math.sqrt(Rm * d_eq * 1e-4 / (4 * Ri))
    G_inf = 0.5 * math.pi * (d_eq * 1e-4) ** 1.5 / math.sqrt(Rm * Ri)
    so = d["soma"]
    G_s = math.pi * (so["d_um"] * 1e-4) ** 2 / so["Rm_ohm_cm2"] + so["shunt_nS"] * 1e-9
    tau_m = Rm * Cm * 1e-3                                                  # ms

    def R_in(loc):
        X = min(X_from_soma(loc), L_eq)
        # loaded cable: soma plus proximal cylinder on one side, distal sealed cylinder on the other
        Yprox = G_inf * (G_s + G_inf * math.tanh(X)) / (G_inf + G_s * math.tanh(X)) if X > 0 else G_s + G_inf * math.tanh(L_eq)
        Ydist = G_inf * math.tanh(L_eq - X) if X > 0 else 0.0
        return 1e-6 / (Yprox + Ydist)

    rin = [dict(site=loc, R_MOhm=R_in(loc)) for loc in d["input_resistance_sites"]]
    att = [dict(source=p["source"], target=p["target"], factor=math.exp(-abs(X_from_soma(p["source"]) - X_from_soma(p["target"]))))
           for p in d["attenuation_pairs"]]
    imp = []
    for q in d["impedance_queries"]:
        R = R_in(q["source"]) * math.exp(-abs(X_from_soma(q["source"]) - X_from_soma(q["target"])))
        w = 2 * math.pi * q["frequency_Hz"] * tau_m * 1e-3
        imp.append(dict(source=q["source"], target=q["target"], frequency_Hz=q["frequency_Hz"],
                        magnitude_MOhm=R / math.sqrt(1 + w * w), phase_deg=-math.degrees(math.atan(w))))
    R0 = R_in({"segment": 0, "fraction": 0})
    taus, coefs = [], []
    n = 0
    while True:
        tau_n = tau_m / (1 + (n * math.pi / L_eq) ** 2)
        if tau_n < d["tau_min_ms"]:
            break
        taus.append(tau_n)
        coefs.append(R0 if n == 0 else 2 * R0 / (1 + (n * math.pi / L_eq) ** 2))
        n += 1
    scale = R0 / sum(coefs)
    modes = [dict(tau_ms=t, coefficient_MOhm=c * scale) for t, c in zip(taus, coefs)]
    rep = dict(neuron_id=d["neuron_id"], input_resistance=rin, attenuation=att, impedance=imp, modes=modes)
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
