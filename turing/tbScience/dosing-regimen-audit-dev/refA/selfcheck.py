#!/usr/bin/env python3
"""Self-consistency evidence and guarantee checks for reference.py (Reference A).

Usage: python selfcheck.py <regimen_dir> <out_json>
"""
import glob
import json
import math
import os
import sys
import time

import numpy as np
from scipy.integrate import solve_ivp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reference as ref  # noqa: E402


def compare(r1, r2):
    S = r1["cmax"]
    c = [abs(a - b) / S for a, b in zip(r1["concentrations"], r2["concentrations"])]
    for k in ("cmax", "cmin", "trough"):
        c.append(abs(r1["steady_state"][k] - r2["steady_state"][k]) / S)
    c.append(abs(r1["cmax"] - r2["cmax"]) / S)
    return dict(conc_over_S=max(c),
                auc_rel=abs(r1["auc"] - r2["auc"]) / abs(r1["auc"]),
                t_cmax_abs=abs(r1["t_cmax"] - r2["t_cmax"]),
                tiw_abs=abs(r1["steady_state"]["time_in_window"] - r2["steady_state"]["time_in_window"]),
                n_equal=r1["steady_state"]["n_cycles_to_steady"] == r2["steady_state"]["n_cycles_to_steady"])


def dop853(reg):
    """Independent external check: scipy DOP853 at rtol 1e-13 between events, AUC as a state."""
    model = ref.Model(reg)
    H = float(reg["horizon"])
    imp, inf = ref.actual_events(reg, model, H)
    qt = [float(t) for t in reg["query_times"]]
    pts = sorted({0.0, H} | {t for (t, _, _) in imp if t <= H} |
                 {t for (a, b, _) in inf for t in (a, b) if 0 < t < H} | set(qt))
    n = model.n
    y = np.zeros(n + 1)
    conc = {}
    amax = max(float(d["amount"]) for d in reg["loading_doses"] + reg["maintenance"]["doses"])
    for j, t in enumerate(pts):
        for (ti, i, a) in imp:
            if ti == t:
                y[i] += a
        if t in qt:
            conc[t] = y[0] / model.V1
        if j == len(pts) - 1:
            break
        t2 = pts[j + 1]
        mid = 0.5 * (t + t2)
        R = sum(r for (a, b, r) in inf if a <= mid < b)

        def f(_, z):
            dz = np.empty(n + 1)
            dz[:n] = model.rhs(z[:n], R)[0]
            dz[n] = z[0] / model.V1
            return dz
        sol = solve_ivp(f, (t, t2), y, method="DOP853", rtol=1e-13, atol=1e-13 * amax)
        y = sol.y[:, -1].copy()
    return [conc[t] for t in qt], y[n]


def direct60(reg, diag):
    """Troughs of cycles 1..60 by direct event-by-event simulation (no period map)."""
    model = ref.Model(reg)
    prop = ref.LinearProp(model) if model.linear else ref.TaylorProp(model)
    mt = reg["maintenance"]
    start, P = float(mt["start"]), float(mt["period"])
    t_end = start + ref.N_CHECK * P
    imp, inf = ref.actual_events(reg, model, t_end)
    bounds = [start + k * P for k in range(1, ref.N_CHECK + 1)]
    xe, _, left, _, _, _ = ref.run_events(prop, np.zeros(model.n), 0.0, t_end, imp, inf, obs=bounds)
    tr = [float(left[b][0]) / model.V1 if b != t_end else float(xe[0]) / model.V1 for b in bounds]
    return max(abs(a - b) / abs(b) for a, b in zip(diag["troughs"], tr))


def brute(reg, rep):
    """Fine uniform grid scan (no root finding) of the steady-state period and of [0, horizon]."""
    model = ref.Model(reg)
    prop = ref.LinearProp(model) if model.linear else ref.TaylorProp(model)
    rep2, diag = ref.solve(reg)
    P = float(reg["maintenance"]["period"])
    pimp, pinf = ref.periodic_events(reg, model)
    x0 = ref.steady_state(reg, model, prop, {})["x"]
    hb = min(0.005, P / 2000.0)
    N = int(math.ceil(P / hb))
    grid = sorted(set([P * k / N for k in range(N + 1)] + [t for (t, i, _) in pimp if i == 0]))
    N = len(grid) - 1
    _, _, left, right, _, _ = ref.run_events(prop, x0, 0.0, P, pimp, pinf, obs=grid)
    low, high = float(reg["window"]["low"]), float(reg["window"]["high"])
    cr = np.array([right[t][0] for t in grid]) / model.V1
    cl = np.array([left[t][0] for t in grid]) / model.V1
    cr[-1] = cl[-1]
    tiw = 0.0
    nsc = 0
    for k in range(N):
        a, b = cr[k], cl[k + 1]
        ina, inb = int(low <= a <= high), int(low <= b <= high)
        tiw += (grid[k + 1] - grid[k]) * 0.5 * (ina + inb)
        for lev in (low, high):
            if (a - lev) * (b - lev) < 0:
                nsc += 1
    ss = rep["steady_state"]
    out = dict(ss_cmax_minus_grid=(ss["cmax"] - max(cr.max(), cl.max())) / ss["cmax"],
               ss_cmin_minus_grid=(min(cr.min(), cl.min()) - ss["cmin"]) / ss["cmax"],
               ss_tiw_minus_grid=ss["time_in_window"] - tiw,
               grid_h=P / N, grid_sign_changes=nsc,
               found_crossings=len(diag["ss_info"]["crossings"]))
    H = float(reg["horizon"])
    hb2 = min(0.005, H / 4000.0)
    N2 = int(math.ceil(H / hb2))
    g2 = [H * k / N2 for k in range(N2 + 1)]
    imp, inf = ref.actual_events(reg, model, H)
    _, _, _, r2, _, _ = ref.run_events(prop, np.zeros(model.n), 0.0, H, imp, inf, obs=g2)
    c2 = np.array([r2[t][0] for t in g2]) / model.V1
    k = int(np.argmax(c2))
    out.update(cmax_minus_grid=(rep["cmax"] - c2[k]) / rep["cmax"], t_grid_max=g2[k],
               t_cmax_minus_grid=rep["t_cmax"] - g2[k], grid_h2=H / N2)
    return out


def guarantees(reg, rep, diag):
    out = {}
    mt = reg["maintenance"]
    start, P = float(mt["start"]), float(mt["period"])
    H = float(reg["horizon"])
    bol = [float(d["time"]) for d in reg["loading_doses"] if d["route"] == "iv_bolus"]
    m = 0
    while start + m * P <= H + 1.0:
        bol += [start + m * P + float(d["offset"]) for d in mt["doses"] if d["route"] == "iv_bolus"]
        m += 1
    tq = [float(t) for t in reg["query_times"]] + [H]
    out["g1_min_dist_h"] = min((abs(a - b) for a in tq for b in bol), default=math.inf)
    cm, tc = rep["cmax"], rep["t_cmax"]
    others = [v for (t, v, kind, _) in diag["actual_info"]["local_maxima"] if abs(t - tc) > 1e-7]
    out["g2_second_max_ratio"] = max(others) / cm if others else 0.0
    interior = [d2 for (t, v, kind, d2) in diag["actual_info"]["local_maxima"]
                if kind == "interior" and abs(t - tc) <= 1e-7]
    out["g2_cmax_kind"] = [kind for (t, v, kind, _) in diag["actual_info"]["local_maxima"]
                           if abs(t - tc) <= 1e-7]
    out["g2_curv_over_cmax"] = abs(interior[0]) / cm if interior else None
    ss = rep["steady_state"]
    low, high = float(reg["window"]["low"]), float(reg["window"]["high"])
    pairs = [(low, ss["cmin"]), (low, ss["cmax"]), (high, ss["cmin"]), (high, ss["cmax"])]
    out["g3_level_vs_extrema_rel"] = min(abs(l - c) / max(l, c) for l, c in pairs)
    cr = diag["ss_info"]["crossings"]
    out["g3_n_crossings"] = len(cr)
    out["g3_min_slope_over_sscmax"] = min((abs(s) for (_, _, s) in cr), default=math.inf) / ss["cmax"]
    out["g3_min_slope_over_cmax"] = min((abs(s) for (_, _, s) in cr), default=math.inf) / cm
    jumps = diag["ss_info"]["jumps"]
    vals = [v for (_, pre, post) in jumps for v in (pre, post)]
    out["g3_bolus_vs_level_rel"] = min((abs(v - l) / l for v in vals for l in (low, high)), default=math.inf)
    out["g4_min_margin_rel"] = diag["min_trough_margin_rel"]
    tr = diag["troughs"]
    out["g4_trough60_ok"] = abs(tr[-1] - ss["trough"]) <= 0.01 * ss["trough"]
    out["trough60_minus_ss_rel"] = abs(tr[-1] - ss["trough"]) / ss["trough"]
    out["g5_ss_cmin_pos"] = ss["cmin"] > 0.0
    out["g5_cmax_ge_1e-3"] = cm >= 1e-3
    viol = []
    if out["g1_min_dist_h"] < 1e-3:
        viol.append("G1")
    if out["g2_second_max_ratio"] > 1 - 1e-4:
        viol.append("G2-unique")
    if out["g2_curv_over_cmax"] is not None and out["g2_curv_over_cmax"] < 1e-2:
        viol.append("G2-curvature")
    if out["g3_level_vs_extrema_rel"] < 1e-3:
        viol.append("G3-levels")
    if out["g3_min_slope_over_sscmax"] < 1e-3:
        viol.append("G3-slope")
    if out["g3_min_slope_over_cmax"] < 1e-3:
        out["note"] = "G3 slope >= 1e-3 holds for the steady-state cmax but not for the report cmax"

    if out["g3_bolus_vs_level_rel"] < 1e-3:
        viol.append("G3-bolus")
    if out["g4_min_margin_rel"] < 1e-4 or not out["g4_trough60_ok"]:
        viol.append("G4")
    if not (out["g5_ss_cmin_pos"] and out["g5_cmax_ge_1e-3"]):
        viol.append("G5")
    out["violations"] = viol
    out["g2_cmax_kind"] = out["g2_cmax_kind"]
    return out


def main():
    rdir, outp = sys.argv[1], sys.argv[2]
    res = {}
    for f in sorted(glob.glob(os.path.join(rdir, "*.json"))):
        name = os.path.basename(f)[:-5]
        reg = json.load(open(f))
        t0 = time.time()
        rep, diag = ref.solve(reg)
        rt = time.time() - t0
        e = dict(engine=diag["engine"], runtime_s=rt, newton_residual_rel=diag["newton_residual_rel"],
                 newton_iterations=diag["newton_iterations"], taylor_steps=diag["taylor_steps"])
        e["guarantees"] = guarantees(reg, rep, diag)
        if diag["engine"] == "expm":
            rep2, _ = ref.solve(reg, engine="taylor")
            e["expm_vs_taylor"] = compare(rep, rep2)
        else:
            rep2, _ = ref.solve(reg, hscale=0.5)
            e["taylor_step_halving"] = compare(rep, rep2)
            rep3, _ = ref.solve(reg, order=22)
            e["taylor_order22_vs_28"] = compare(rep, rep3)
        c, auc = dop853(reg)
        S = rep["cmax"]
        e["dop853"] = dict(conc_over_S=max(abs(a - b) / S for a, b in zip(c, rep["concentrations"])),
                           auc_rel=abs(auc - rep["auc"]) / rep["auc"])
        e["direct60_trough_maxrel"] = direct60(reg, diag)
        op = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", name + ".json")
        if os.path.exists(op):
            e["out_file_reproduced_exactly"] = json.load(open(op)) == rep
        if "--brute" in sys.argv:
            e["brute"] = brute(reg, rep)
        res[name] = e
        print(name, json.dumps({k: v for k, v in e.items() if k != "guarantees"}, default=str),
              "viol", e["guarantees"]["violations"], flush=True)
    json.dump(res, open(outp, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
