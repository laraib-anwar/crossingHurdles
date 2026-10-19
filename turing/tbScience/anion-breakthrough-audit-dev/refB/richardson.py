#!/usr/bin/env python
"""Grid-convergence driver for fv_referee.py.

Runs the finite-volume referee at several resolutions, matches plateaus and fronts across the
levels, Richardson-extrapolates the scalar outputs (plateau compositions, sample compositions,
nitrate peak, nitrate limit BV, shock BVs) and classifies each front as a shock (10-90 width
shrinking like 1/N) or a spreading wave (width independent of N).

CLI:
    python richardson.py --recipe <recipe.json> --cells 2000 4000 8000 --out <dir>
        [--reuse] [--order 2] [--limiter minmod] [--cfl 0.4] [--jobs 1]

Per level the solver writes <dir>/N<cells>/{effluent.npz,summary.json}; the extrapolation is
written to <dir>/extrapolated.json. With more than three levels, the three finest are used for
the extrapolation and the rest are reported as additional evidence of the convergence order.

Extrapolation rule for a scalar f with values f1, f2, f3 on N, 2N, 4N (d1 = f2-f1, d2 = f3-f2):
  * |d1|, |d2| both below 1e-12 (relative 1e-13): converged, value f3, error max(|d1|,|d2|).
  * d1*d2 > 0 and |d2| < |d1|: observed order p = log2(d1/d2), clipped to [0.5, 3] for the
    extrapolation, value f3 + d2/(2^p - 1), error |value - f3| (the Richardson correction);
    |d2| is reported as well and bounds the fine-level error whenever p >= 1.
  * otherwise (non-monotone or not shrinking): value f3, error max(|d1|,|d2|), flagged.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
IONS = ["chloride", "nitrate", "sulfate", "bicarbonate"]


def run_level(py, recipe, N, outdir, extra, reuse):
    d = os.path.join(outdir, f"N{N}")
    sfile = os.path.join(d, "summary.json")
    if reuse and os.path.exists(sfile) and os.path.exists(os.path.join(d, "effluent.npz")):
        return d, 0.0
    os.makedirs(d, exist_ok=True)
    cmd = [py, os.path.join(HERE, "fv_referee.py"), "--recipe", recipe, "--cells", str(N), "--out", d,
           "--quiet"] + extra
    t0 = time.time()
    with open(os.path.join(d, "run.log"), "w") as log:
        subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT)
    return d, time.time() - t0


def richardson(vals, rel_floor=1e-13, abs_floor=1e-12):
    """vals: list of 3 floats (coarse -> fine) or with None entries."""
    if any(v is None for v in vals) or len(vals) < 3:
        fine = next((v for v in reversed(vals) if v is not None), None)
        return {"value": fine, "error": None, "fine_value": fine, "diff_two_finest": None,
                "observed_order": None, "levels": vals, "flag": "missing level"}
    f1, f2, f3 = [float(v) for v in vals[-3:]]
    d1, d2 = f2 - f1, f3 - f2
    tiny = max(abs_floor, rel_floor * abs(f3))
    out = {"fine_value": f3, "diff_two_finest": abs(d2), "levels": vals}
    if abs(d1) <= tiny and abs(d2) <= tiny:
        out.update(value=f3, error=max(abs(d1), abs(d2)), observed_order=None, flag="converged")
    elif d1 * d2 > 0 and abs(d2) < abs(d1):
        p = math.log2(d1 / d2)
        pc = min(max(p, 0.5), 3.0)
        fx = f3 + d2 / (2.0 ** pc - 1.0)
        out.update(value=fx, error=abs(fx - f3), observed_order=p, flag="extrapolated" if 0.5 <= p <= 3.0
                   else "extrapolated (order clipped)")
    else:
        out.update(value=f3, error=max(abs(d1), abs(d2)), observed_order=None,
                   flag="non-monotone or not shrinking; fine value kept")
    return out


def rich_vec(list_of_vecs):
    """list over levels of 4-vectors (or None) -> list over ions of richardson dicts."""
    res = []
    for k in range(4):
        vals = [None if v is None else float(v[k]) for v in list_of_vecs]
        res.append(richardson(vals))
    return res


def overlap(a, b):
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def match(template, items, key_start="bv_start", key_end="bv_end"):
    """For each template interval return the index of the item with the largest overlap (or None)."""
    out = []
    for t in template:
        best, bo = None, 0.0
        for i, it in enumerate(items):
            o = overlap((t[key_start], t[key_end]), (it[key_start], it[key_end]))
            if o > bo:
                best, bo = i, o
        out.append(best)
    return out


def classify_widths(widths):
    """widths: list over levels (coarse->fine) of 10-90 widths in BV (or None)."""
    ws = [w for w in widths if w is not None]
    if len(ws) < 2:
        return "unknown", None
    ratios = [ws[i] / ws[i + 1] if ws[i + 1] else None for i in range(len(ws) - 1)]
    r = ratios[-1]
    if r is None:
        return "unknown", ratios
    if r >= 1.6:
        return "shock (width ~ 1/N)", ratios
    if r <= 1.3:
        return "spreading wave (width independent of N)", ratios
    return "mixed or unresolved (width ratio between 1.3 and 1.6)", ratios


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--cells", type=int, nargs="+", default=[2000, 4000, 8000])
    ap.add_argument("--out", required=True)
    ap.add_argument("--reuse", action="store_true", help="do not rerun levels whose summary.json exists")
    ap.add_argument("--jobs", type=int, default=1, help="levels to run concurrently")
    ap.add_argument("--order", type=int, default=2)
    ap.add_argument("--limiter", default="minmod")
    ap.add_argument("--cfl", type=float, default=0.4)
    ap.add_argument("--rk", type=int, default=2)
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args(argv)

    cells = sorted(set(args.cells))
    extra = ["--order", str(args.order), "--limiter", args.limiter, "--cfl", str(args.cfl), "--rk", str(args.rk)]
    os.makedirs(args.out, exist_ok=True)
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        futs = {N: ex.submit(run_level, args.python, args.recipe, N, args.out, extra, args.reuse) for N in cells}
        dirs = {N: futs[N].result()[0] for N in cells}

    summaries = {}
    for N in cells:
        with open(os.path.join(dirs[N], "summary.json")) as f:
            summaries[N] = json.load(f)
    fine = summaries[cells[-1]]
    three = cells[-3:] if len(cells) >= 3 else cells
    rec = fine["recipe_id"]

    timings = {str(N): {"runtime_s": summaries[N]["solver"]["runtime_s"], "n_steps": summaries[N]["solver"]["n_steps"],
                        "dt_min": summaries[N]["solver"]["dt_min"], "dt_max": summaries[N]["solver"]["dt_max"],
                        "steady_state_exit_bv": summaries[N]["solver"]["steady_state_exit_bv"],
                        "max_abs_mass_balance_error": float(np.abs(summaries[N]["solver"]["mass_balance"]["error_per_ion"]).max()),
                        "inversion_failures": summaries[N]["solver"]["inversion_failures"]}
               for N in cells}

    # ---- plateaus -------------------------------------------------------------------------------
    plat_matches = {N: match(fine["plateaus"], summaries[N]["plateaus"]) for N in cells}
    plateaus = []
    for ip, P in enumerate(fine["plateaus"]):
        comps = []
        starts, ends = [], []
        for N in three:
            m = plat_matches[N][ip]
            if m is None:
                comps.append(None); starts.append(None); ends.append(None)
            else:
                q = summaries[N]["plateaus"][m]
                comps.append(q["composition_meq_per_L"]); starts.append(q["bv_start"]); ends.append(q["bv_end"])
        plateaus.append({
            "index": ip,
            "bv_start_fine": P["bv_start"], "bv_end_fine": P["bv_end"],
            "bv_start_levels": starts, "bv_end_levels": ends,
            "composition_meq_per_L": rich_vec(comps),
            "spread_fine": P["spread_central_half_meq_per_L"],
            "matched_in_all_levels": all(plat_matches[N][ip] is not None for N in three),
            "n_plateaus_per_level": {str(N): summaries[N]["n_plateaus"] for N in cells},
        })

    # ---- fronts ---------------------------------------------------------------------------------
    front_matches = {N: match(fine["fronts"], summaries[N]["fronts"]) for N in cells}
    fronts = []
    for jf, Fr in enumerate(fine["fronts"]):
        lead = Fr["leading_ion"]
        widths_lead = []
        kinds = []
        per_ion_bv50 = {ion: [] for ion in IONS}
        per_ion_bv50c = {ion: [] for ion in IONS}
        per_ion_bv10 = {ion: [] for ion in IONS}
        per_ion_bv90 = {ion: [] for ion in IONS}
        per_ion_width = {ion: [] for ion in IONS}
        steep_fracs = []
        for N in cells:
            m = front_matches[N][jf]
            if m is None:
                widths_lead.append(None); kinds.append(None); steep_fracs.append(None)
                for ion in IONS:
                    per_ion_bv50[ion].append(None); per_ion_bv10[ion].append(None)
                    per_ion_bv50c[ion].append(None)
                    per_ion_bv90[ion].append(None); per_ion_width[ion].append(None)
                continue
            q = summaries[N]["fronts"][m]
            widths_lead.append(q["width_10_90_bv"].get(lead))
            kinds.append(q["kind_single_resolution"])
            steep_fracs.append(q["steep_fraction_of_jump"])
            for ion in IONS:
                cr = q["crossings"].get(ion)
                per_ion_bv50[ion].append(cr["bv50"] if cr else None)
                per_ion_bv50c[ion].append(cr.get("bv50_cell") if cr else None)
                per_ion_bv10[ion].append(cr["bv10"] if cr else None)
                per_ion_bv90[ion].append(cr["bv90"] if cr else None)
                per_ion_width[ion].append(q["width_10_90_bv"].get(ion))
        kind, ratios = classify_widths(widths_lead)
        nlev = len(cells)
        sel = slice(nlev - 3, nlev) if nlev >= 3 else slice(0, nlev)
        shock_bv = {}
        shock_bv_cell = {}
        for ion in IONS:
            if any(v is not None for v in per_ion_bv50[ion]):
                shock_bv[ion] = richardson(per_ion_bv50[ion][sel])
            if any(v is not None for v in per_ion_bv50c[ion]):
                shock_bv_cell[ion] = richardson(per_ion_bv50c[ion][sel])
        onset = {ion: richardson(per_ion_bv10[ion][sel]) for ion in IONS if any(v is not None for v in per_ion_bv10[ion])}
        finish = {ion: richardson(per_ion_bv90[ion][sel]) for ion in IONS if any(v is not None for v in per_ion_bv90[ion])}
        fronts.append({
            "index": jf,
            "bv_start_fine": Fr["bv_start"], "bv_end_fine": Fr["bv_end"], "cut_by_window_end": Fr["cut_by_window_end"],
            "leading_ion": lead,
            "before_meq_per_L_fine": Fr["before_meq_per_L"], "after_meq_per_L_fine": Fr["after_meq_per_L"],
            "jump_meq_per_L_fine": Fr["jump_meq_per_L"],
            "width_10_90_leading_ion_bv_per_level": dict(zip([str(N) for N in cells], widths_lead)),
            "width_ratio_consecutive_levels": ratios,
            "kind_from_width_scaling": kind,
            "kind_single_resolution_per_level": dict(zip([str(N) for N in cells], kinds)),
            "steep_fraction_per_level": dict(zip([str(N) for N in cells], steep_fracs)),
            "steep_parts_fine": Fr["steep_parts"],
            "shock_bv_midpoint_crossing": shock_bv,
            "shock_bv_midpoint_crossing_cell_history": shock_bv_cell,
            "onset_bv10": onset, "finish_bv90": finish,
            "per_ion_width_10_90_bv_per_level": {ion: dict(zip([str(N) for N in cells], v))
                                                 for ion, v in per_ion_width.items() if any(x is not None for x in v)},
            "monotonicity_fine": Fr["monotonicity"],
            "matched_in_all_levels": all(front_matches[N][jf] is not None for N in cells),
            "n_fronts_per_level": {str(N): summaries[N]["n_fronts"] for N in cells},
        })

    # ---- scalars --------------------------------------------------------------------------------
    peak_val = richardson([summaries[N]["nitrate_peak"]["meq_per_L"] for N in three])
    peak_bv = richardson([summaries[N]["nitrate_peak"]["bv_estimate"] for N in three])
    def limit_rich(key):
        nl = [summaries[N][key] for N in three]
        if all(v is None for v in nl):
            return {"value": None, "error": None, "flag": "never exceeded at any level", "levels": nl}
        if any(v is None for v in nl):
            return {"value": nl[-1], "error": None, "flag": "exceeded at some levels only", "levels": nl}
        return richardson(nl)

    nlim = limit_rich("nitrate_limit_bv")
    nlim_cell = limit_rich("nitrate_limit_bv_cell")
    peak_face = richardson([summaries[N]["nitrate_peak"]["meq_per_L_face_history"] for N in three])
    samples = []
    for i, sb in enumerate(fine["sample_bv"]):
        comps = [summaries[N]["samples"][i] for N in three]
        samples.append({"bv": sb, "composition_meq_per_L": rich_vec(comps)})

    # roll-up based on extrapolated plateau compositions and the finest level's spreading-wave extremes
    rollup = {}
    c0 = fine["effluent_at_0"]
    feeds = fine["rollup"][IONS[0]]["feeds"]  # per ion below
    for k, ion in enumerate(IONS):
        ref_max = max([c0[k]] + fine["rollup"][ion]["feeds"])
        ref_min = min([c0[k]] + fine["rollup"][ion]["feeds"])
        plateau_vals = [p["composition_meq_per_L"][k]["value"] for p in plateaus if p["composition_meq_per_L"][k]["value"] is not None]
        pmax = max(plateau_vals) if plateau_vals else None
        pmin = min(plateau_vals) if plateau_vals else None
        rollup[ion] = {
            "initial": c0[k], "feeds": fine["rollup"][ion]["feeds"],
            "max_plateau_extrapolated": pmax, "min_plateau_extrapolated": pmin,
            "roll_up_on_a_plateau": bool(pmax is not None and pmax > ref_max + 1e-6),
            "roll_down_on_a_plateau": bool(pmin is not None and pmin < ref_min - 1e-6),
            "raw_max_effluent_fine": fine["rollup"][ion]["max_effluent"],
            "raw_min_effluent_fine": fine["rollup"][ion]["min_effluent"],
        }

    # structure string
    seq = []
    events = [("P", p["bv_start_fine"], p) for p in plateaus] + [("F", f["bv_start_fine"], f) for f in fronts]
    events.sort(key=lambda e: e[1])
    for kind_, bv0, obj in events:
        if kind_ == "P":
            comp = [round(c["value"], 5) if c["value"] is not None else None for c in obj["composition_meq_per_L"]]
            seq.append(f"plateau[{obj['index']}] {bv0:.2f}-{obj['bv_end_fine']:.2f}: {comp}")
        else:
            seq.append(f"front[{obj['index']}] {bv0:.2f}-{obj['bv_end_fine']:.2f}: {obj['kind_from_width_scaling']}"
                       f" (lead {obj['leading_ion']}, jump {[round(v, 4) for v in obj['jump_meq_per_L_fine']]})")

    out = {
        "recipe_id": rec, "ions": IONS, "cells": cells, "levels_used_for_extrapolation": three,
        "scheme": {"order": args.order, "limiter": args.limiter, "cfl": args.cfl, "rk": args.rk},
        "timings": timings,
        "structure_fine_level": seq,
        "n_plateaus_per_level": {str(N): summaries[N]["n_plateaus"] for N in cells},
        "n_fronts_per_level": {str(N): summaries[N]["n_fronts"] for N in cells},
        "plateaus": plateaus, "fronts": fronts,
        "nitrate_peak": {"meq_per_L": peak_val, "bv": peak_bv,
                         "meq_per_L_face_history": peak_face,
                         "location_fine": fine["nitrate_peak"]["location"],
                         "raw_argmax_bv_fine": fine["nitrate_peak"]["bv_of_argmax"]},
        "nitrate_limit_bv": nlim,
        "nitrate_limit_bv_cell_history": nlim_cell,
        "samples": samples,
        "rollup": rollup,
        "effluent_at_run_bv_fine": fine["effluent_at_run_bv"],
    }
    with open(os.path.join(args.out, "extrapolated.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(f"{rec}: levels {cells}")
    for s in seq:
        print("  " + s)
    print(f"  nitrate peak {peak_val['value']:.6f} +- {peak_val['error'] if peak_val['error'] is not None else float('nan'):.1e} "
          f"at BV {peak_bv['value']}; nitrate limit BV {nlim['value']}")
    for N in cells:
        print(f"  N={N}: {timings[str(N)]['n_steps']} steps, {timings[str(N)]['runtime_s']:.1f} s, "
              f"mass balance {timings[str(N)]['max_abs_mass_balance_error']:.1e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
