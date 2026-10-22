#!/usr/bin/env python3
"""Independent consistency checker for a (system, report) pair.

It re-evaluates the Gibbs model directly from the system file (no code shared with
reference.py except the formula in PHASE_SPEC.md) and measures:
  * tie-lines: chemical-potential residuals |mu_A^L - mu_A^R|, |mu_B^L - mu_B^R| (J/mol);
  * every tie-line lies below every phase curve and compound (dense grid, log-spaced ends);
  * single-phase regions: the region's phase is the lowest curve on a grid inside it;
  * invariants: three states on one line (residuals), and the line is below everything;
  * congruent points: G and dG/dx equality (or compound equality) residuals;
  * critical points: G'' and G''' residuals;
  * schema: keys, orders, exact outer bounds, exact compound compositions.
Usage: python check_report.py system.json report.json
"""
import json
import math
import sys

import numpy as np

R = 8.314462618


def G_terms(ph, x, T):
    """G, G', G'', G''' of a solution phase at composition array x (0<x<1)."""
    x = np.asarray(x, dtype=float)
    y = 1.0 - x
    em = ph["end_members"]
    GA = em["A"]["h"] - em["A"]["s"] * T
    GB = em["B"]["h"] - em["B"]["s"] * T
    L = [rk["a"] + rk["b"] * T for rk in ph["redlich_kister"]]
    s = 1.0 - 2.0 * x
    S = L[0] + L[1] * s + L[2] * s * s
    S1 = L[1] + 2.0 * L[2] * s
    S2 = 2.0 * L[2]
    p = x * y
    G = y * GA + x * GB + R * T * (x * np.log(x) + y * np.log(y)) + p * S
    G1 = (GB - GA) + R * T * (np.log(x) - np.log(y)) + s * S - 2.0 * p * S1
    G2 = R * T / p - 2.0 * S - 4.0 * s * S1 + 4.0 * p * S2
    G3 = R * T * (1.0 / (y * y) - 1.0 / (x * x)) + 12.0 * S1 + 12.0 * s * S2
    return G, G1, G2, G3


def grid():
    a = np.logspace(-9, -1, 400)
    mid = np.linspace(0.1, 0.9, 1601)
    return np.unique(np.concatenate([a, mid, 1.0 - a]))


def main(sys_path, rep_path):
    S = json.load(open(sys_path))
    Rp = json.load(open(rep_path))
    phases = {p["name"]: p for p in S["solution_phases"]}
    cmps = {c["name"]: c for c in S["compounds"]}
    problems = []
    worst = {"mu": 0.0, "below": 0.0, "region": 0.0, "inv": 0.0, "cong": 0.0, "crit": 0.0}
    xs = grid()

    def state_G(name, x, T):
        if name in cmps:
            return cmps[name]["h"] - cmps[name]["s"] * T
        return float(G_terms(phases[name], np.array([x]), T)[0][0])

    def line_below_all(m, c, T, tol=1e-6):
        """Largest violation (positive = some point below the line) over all phases/compounds."""
        v = 0.0
        for ph in phases.values():
            G = G_terms(ph, xs, T)[0]
            v = max(v, float(np.max((m * xs + c) - G)))
        for cm in cmps.values():
            v = max(v, (m * cm["x_b"] + c) - (cm["h"] - cm["s"] * T))
        return v

    assert list(Rp.keys()) == ["system_id", "isotherms", "invariants", "congruent_points", "critical_points"], "top-level keys"
    assert Rp["system_id"] == S["system_id"]
    assert len(Rp["isotherms"]) == len(S["isotherms_K"])
    for iso, T in zip(Rp["isotherms"], S["isotherms_K"]):
        assert iso["temperature_K"] == T, "isotherm temperature not exact"
        regs, ties = iso["single_phase_regions"], iso["tie_lines"]
        assert regs[0]["x_lo"] == 0 and regs[-1]["x_hi"] == 1, "outer bounds not exact"
        for t in ties:
            for side in ("left", "right"):
                nm = t[side + "_phase"]
                if nm in cmps:
                    assert t["x_" + side] == cmps[nm]["x_b"], "compound x not exact"
            # chemical potentials
            mus = []
            for side in ("left", "right"):
                nm, x = t[side + "_phase"], t["x_" + side]
                if nm in cmps:
                    mus.append(None)
                else:
                    G, G1, _, _ = G_terms(phases[nm], np.array([x]), T)
                    mus.append((float(G[0] - x * G1[0]), float(G[0] + (1 - x) * G1[0])))
            xl, xr = t["x_left"], t["x_right"]
            Gl, Gr = state_G(t["left_phase"], xl, T), state_G(t["right_phase"], xr, T)
            m = (Gr - Gl) / (xr - xl)
            c = Gl - m * xl
            if mus[0] and mus[1]:
                worst["mu"] = max(worst["mu"], abs(mus[0][0] - mus[1][0]), abs(mus[0][1] - mus[1][1]))
            for k, side in enumerate(("left", "right")):
                if mus[k]:
                    # tangent slope must equal the chord slope
                    nm, x = t[side + "_phase"], t["x_" + side]
                    G1 = float(G_terms(phases[nm], np.array([x]), T)[1][0])
                    worst["mu"] = max(worst["mu"], abs(G1 - m) * (xr - xl))
            worst["below"] = max(worst["below"], line_below_all(m, c, T))
        for rg in regs:
            lo, hi = max(rg["x_lo"], 1e-9), min(rg["x_hi"], 1 - 1e-9)
            if hi <= lo:
                continue
            xg = np.linspace(lo, hi, 400)
            Gp = G_terms(phases[rg["phase"]], xg, T)[0]
            for nm, ph in phases.items():
                if nm == rg["phase"]:
                    continue
                worst["region"] = max(worst["region"], float(np.max(Gp - G_terms(ph, xg, T)[0])))
            for cm in cmps.values():
                if lo <= cm["x_b"] <= hi:
                    worst["region"] = max(worst["region"], float(G_terms(phases[rg["phase"]], np.array([cm["x_b"]]), T)[0][0]) - (cm["h"] - cm["s"] * T))
        # coverage: regions and ties alternate and cover [0,1]
        pieces = sorted([(r["x_lo"], r["x_hi"], "R") for r in regs] + [(t["x_left"], t["x_right"], "T") for t in ties])
        pos = 0.0
        for lo, hi, k in pieces:
            if abs(lo - pos) > 1e-12:
                problems.append("gap/overlap at T=%g x=%.9f" % (T, pos))
            pos = hi
        if abs(pos - 1.0) > 1e-12:
            problems.append("hull does not end at 1 at T=%g" % T)
    Ts = [e["temperature_K"] for e in Rp["invariants"]]
    assert Ts == sorted(Ts)
    for e in Rp["invariants"]:
        T = e["temperature_K"]
        st = e["phases"]
        assert st[0]["x"] < st[1]["x"] < st[2]["x"]
        Gs = [state_G(s["phase"], s["x"], T) for s in st]
        m = (Gs[2] - Gs[0]) / (st[2]["x"] - st[0]["x"])
        c = Gs[0] - m * st[0]["x"]
        worst["inv"] = max(worst["inv"], abs(Gs[1] - (m * st[1]["x"] + c)))
        for s in st:
            if s["phase"] in phases:
                G1 = float(G_terms(phases[s["phase"]], np.array([s["x"]]), T)[1][0])
                worst["inv"] = max(worst["inv"], abs(G1 - m) * 1e-3)
            else:
                assert s["x"] == cmps[s["phase"]]["x_b"]
        worst["below"] = max(worst["below"], line_below_all(m, c, T))
        liq = [s["phase"] == "liquid" for s in st]
        table = {("eutectic", True, 0): "eutectic", ("eutectic", True, 1): "monotectic",
                 ("eutectic", False, 0): "eutectoid", ("eutectic", False, 1): "metatectic", ("eutectic", False, 2): "metatectic",
                 ("peritectic", False, 1): "peritectic", ("peritectic", False, 2): "syntectic", ("peritectic", False, 0): "peritectoid",
                 ("peritectic", True, 0): "inverse_monotectic", ("peritectic", True, 1): "inverse_monotectic", ("peritectic", True, 2): "inverse_monotectic"}
        nm = table[(e["class"], liq[1], liq[0] + liq[2])]
        if nm != e["name"]:
            problems.append("invariant name %s should be %s" % (e["name"], nm))
    for e in Rp["congruent_points"]:
        T, x = e["temperature_K"], e["x"]
        a, b = e["phase_above"], e["phase_below"]
        if a in cmps or b in cmps:
            cm = cmps[a] if a in cmps else cmps[b]
            ph = phases[b] if a in cmps else phases[a]
            assert x == cm["x_b"]
            worst["cong"] = max(worst["cong"], abs(float(G_terms(ph, np.array([x]), T)[0][0]) - (cm["h"] - cm["s"] * T)))
        else:
            GA_, G1A, _, _ = G_terms(phases[a], np.array([x]), T)
            GB_, G1B, _, _ = G_terms(phases[b], np.array([x]), T)
            worst["cong"] = max(worst["cong"], abs(float(GA_[0] - GB_[0])), abs(float(G1A[0] - G1B[0])) * 1e-3)
        # the touching point must be on the hull
        Gt = state_G(a, x, T)
        for nm, ph in phases.items():
            worst["below"] = max(worst["below"], Gt - float(G_terms(ph, np.array([x]), T)[0][0]))
    for e in Rp["critical_points"]:
        T, x = e["temperature_K"], e["x"]
        _, _, G2, G3 = G_terms(phases[e["phase"]], np.array([x]), T)
        worst["crit"] = max(worst["crit"], abs(float(G2[0])) * 1e-3, abs(float(G3[0])) * 1e-6)
    print("%-28s mu_res=%.2e  below_hull_viol=%.2e  region_viol=%.2e  inv_res=%.2e  cong_res=%.2e  crit_res=%.2e  problems=%d"
          % (S["system_id"], worst["mu"], worst["below"], worst["region"], worst["inv"], worst["cong"], worst["crit"], len(problems)))
    for p in problems:
        print("   PROBLEM:", p)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
