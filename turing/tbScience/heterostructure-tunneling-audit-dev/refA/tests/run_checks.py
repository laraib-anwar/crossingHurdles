"""Internal and independent checks of refA/reference.py on a set of structure files.

usage: python run_checks.py [--hp] [--out summary.json] structure.json ...

For each structure (report recomputed in-process):
  rev      max relative difference of T between incidence from the left and from the right
           (structure reversed: layers reversed, vl/vr swapped, leads swapped), queries + maxima
  cons     max | |r|^2 + T - 1 | at queries and maxima (both leads open)
  dTfd     max relative difference analytic dT/dE vs Richardson central differences (window)
  count    Sturm count at E_n -/+ 1e-9 equals n / n + 1 for every bound state; count at E_th-2e-5
  bisect   max |E_n(det root) - E_n(bisection on the Sturm count alone)|
  scan     maxima count from an independent T-value scan at step 1e-5 eV (discrete maxima)
  guar     guarantee checks (bound spacing >= 1e-6, top >= 1e-4 below E_th, T(Eq) >= 1e-30,
           |dlnT/dE| <= 1e3 at queries, window extrema spacing >= 2e-4, maxima contrast >= 1e-3)
  hp       (with --hp) max |dE| bound states, max rel dT, max |dE| maxima, max rel dT maxima
           against tests/hp.py (decimal Taylor integration); hp_dT_rel: analytic dT/dE against a
           high-precision central difference, relative to max(|dT/dE|, T)
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import reference as R  # noqa: E402
import hp  # noqa: E402


def reverse_struct(s):
    r = json.loads(json.dumps(s))
    r["left_lead"], r["right_lead"] = s["right_lead"], s["left_lead"]
    r["layers"] = [{"thickness_nm": L["thickness_nm"], "mass": L["mass"], "vl_eV": L["vr_eV"],
                    "vr_eV": L["vl_eV"]} for L in reversed(s["layers"])]
    return r


def check(path, do_hp):
    s = json.load(open(path))
    t0 = time.time()
    rep = R.compute_report(s)
    runtime = time.time() - t0
    M = R.Model(s)
    res = {"id": s["structure_id"], "runtime_s": runtime, "n_bound": len(rep["bound_states"]),
           "n_max": len(rep["maxima"])}
    Eq = np.array(M.Eq)
    Emx = np.array([m["E_eV"] for m in rep["maxima"]])
    Eall = np.concatenate([Eq, Emx]) if Emx.size else Eq
    T, dTq, r = R.transmission(M, Eall, need_d=True, return_r=True)
    Mr = R.Model(reverse_struct(s))
    Tr = R.transmission(Mr, Eall)
    res["rev"] = float(np.max(np.abs(Tr / T - 1.0)))
    res["cons"] = float(np.max(np.abs(np.abs(r) ** 2 + T - 1.0)))
    res["T_min_query"] = float(np.min(T[:Eq.size]))
    # analytic derivative vs Richardson central difference in the window and at queries
    lo, hi = M.win
    Ed = np.concatenate([np.linspace(lo + 1e-4, hi - 1e-4, 7), Eq])
    _, dA = R.transmission(M, Ed, need_d=True)
    h = 1e-5
    def cd(hh):
        return (R.transmission(M, Ed + hh) - R.transmission(M, Ed - hh)) / (2 * hh)
    dF = (4 * cd(h / 2) - cd(h)) / 3
    Tq = R.transmission(M, Ed)
    scale = np.maximum(np.abs(dA), Tq)  # relative to T per eV where dT/dE ~ 0
    res["dTfd"] = float(np.max(np.abs(dA - dF) / scale))
    # Sturm count consistency
    bs = [b["E_eV"] for b in rep["bound_states"]]
    Eth = min(M.VL, M.VR)
    ok = R.node_count(M, Eth - 2e-5) == len(bs)
    for n, e in enumerate(bs):
        ok = ok and R.node_count(M, e - 1e-9) == n and R.node_count(M, e + 1e-9) == n + 1
    res["count"] = bool(ok)
    # bisection on the Sturm count alone
    bmax = 0.0
    for n, e in enumerate(bs):
        a, b = e - 1e-7, e + 1e-7
        if not (R.node_count(M, a) == n and R.node_count(M, b) == n + 1):
            bmax = float("inf")
            continue
        for _ in range(80):
            mid = 0.5 * (a + b)
            if mid <= a or mid >= b:
                break
            if R.node_count(M, mid) > n:
                b = mid
            else:
                a = mid
        bmax = max(bmax, abs(0.5 * (a + b) - e))
    res["bisect"] = bmax
    # independent fine scan of T values (discrete maxima, step 1e-5)
    grid = np.linspace(lo, hi, int(math.ceil((hi - lo) / 1e-5)) + 1)
    Tg = np.concatenate([R.transmission(M, grid[i:i + 2048]) for i in range(0, grid.size, 2048)])
    dmax = np.nonzero((Tg[1:-1] > Tg[:-2]) & (Tg[1:-1] >= Tg[2:]))[0] + 1
    dmin = np.nonzero((Tg[1:-1] < Tg[:-2]) & (Tg[1:-1] <= Tg[2:]))[0] + 1
    res["scan_n_max"] = int(dmax.size)
    res["scan_agree"] = bool(dmax.size == len(rep["maxima"]) and all(
        abs(grid[i] - m["E_eV"]) <= 1e-5 for i, m in zip(dmax, rep["maxima"])))
    # guarantees
    g = {}
    g["bound_spacing_min"] = float(np.min(np.diff(bs))) if len(bs) > 1 else None
    g["bound_top_gap"] = float(Eth - bs[-1]) if bs else None
    g["n_bound_le_40"] = len(bs) <= 40
    g["T_query_ge_1e-30"] = bool(np.all(T[:Eq.size] >= 1e-30))
    g["dlnT_query_max"] = float(np.max(np.abs(dTq[:Eq.size] / T[:Eq.size])))
    g["query_above_leads"] = bool(np.all(Eq >= max(M.VL, M.VR) + 1e-3 - 1e-15))
    g["window_above_Vmax"] = bool(lo >= M.Vmax + 0.01 - 1e-12)
    ext = sorted([(grid[i], Tg[i], 1) for i in dmax] + [(grid[i], Tg[i], -1) for i in dmin])
    pos = [lo] + [x[0] for x in ext] + [hi]
    g["extrema_spacing_min"] = float(np.min(np.diff(pos))) if ext else None
    contrast = []
    for k, (e, tv, kind) in enumerate(ext):
        if kind != 1:
            continue
        left = ext[k - 1][1] if k > 0 else Tg[0]
        right = ext[k + 1][1] if k + 1 < len(ext) else Tg[-1]
        contrast.append(min(tv / left - 1.0, tv / right - 1.0))
    g["max_contrast_min"] = float(min(contrast)) if contrast else None
    res["guarantees"] = g
    if do_hp:
        Hm = hp.HPModel(s)
        th = time.time()
        res["hp_bound_dE"] = max([abs(float(hp.bound_root(Hm, e)) - e) for e in bs], default=0.0)
        res["hp_T_rel"] = max(abs(q["T"] / float(hp.transmission(Hm, q["E_eV"])) - 1.0)
                              for q in rep["transmission"])
        dEm, dTm = 0.0, 0.0
        for mx in rep["maxima"]:
            e, tv = hp.maximum(Hm, mx["E_eV"])
            dEm = max(dEm, abs(float(e) - mx["E_eV"]))
            dTm = max(dTm, abs(mx["T"] / float(tv) - 1.0))
        res["hp_max_dE"] = dEm
        res["hp_max_T_rel"] = dTm
        # analytic dT/dE against a high-precision central difference (step 1e-15 eV)
        Ech = list(np.linspace(lo + 1e-3, hi - 1e-3, 3)) + list(Eq[:2])
        _, dAn = R.transmission(M, np.array(Ech), need_d=True)
        Tch = R.transmission(M, np.array(Ech))
        res["hp_dT_rel"] = max(abs(float(dAn[i]) - float(hp.dT(Hm, e))) / max(abs(float(dAn[i])), float(Tch[i]))
                               for i, e in enumerate(Ech))
        res["hp_time_s"] = time.time() - th
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hp", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    allres = []
    for f in a.files:
        r = check(f, a.hp)
        allres.append(r)
        print(json.dumps(r), flush=True)
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(allres, fh, indent=1)
            fh.write("\n")


if __name__ == "__main__":
    main()
