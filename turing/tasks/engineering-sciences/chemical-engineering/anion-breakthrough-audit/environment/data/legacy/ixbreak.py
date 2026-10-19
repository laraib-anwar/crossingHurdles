#!/usr/bin/env python3
"""ixbreak.py - anion exchanger breakthrough estimator (plant engineering, rev 7).

Estimates the effluent history of a fixed-bed anion exchanger from the resin selectivities,
the initial resin loading and the feed program. Same command line and report layout as the
new program so the two can be compared on the same recipe files:

    python ixbreak.py --recipe <recipe.json> --output <report.json>

Method (unchanged since rev 3): every ion that is exchanged forms one sharp front whose
position in bed volumes follows from the ion's own stoichiometry, run length = exchangeable
capacity / loading change, i.e. BV = eps + Lambda * dy_i / dx_i between the initial and the
final resin and liquid states of that ion. Fronts are sorted by position; the effluent between
fronts is the composition in which the ions whose front has passed are at their feed value and
the others still at their initial value, renormalised to the total normality. A feed change
restarts the estimate from the final state of the previous feed and shifts the new fronts by
the time of the change. Spreading of fronts is neglected (sharp-front assumption), which is
conservative for run-length purposes.
"""
import argparse
import json

IONS = ["chloride", "nitrate", "sulfate", "bicarbonate"]


def equilibrium_resin(x, alpha):
    s = sum(alpha[i] * x[i] for i in IONS)
    return {i: alpha[i] * x[i] / s for i in IONS}


def equilibrium_liquid(y, alpha):
    s = sum(y[i] / alpha[i] for i in IONS)
    return {i: (y[i] / alpha[i]) / s for i in IONS}


def fronts_for_step(x_from, x_to, alpha, eps, lam, bv_offset):
    """Sharp fronts of one feed step, ion by ion, from the ion's own stoichiometry."""
    y_from, y_to = equilibrium_resin(x_from, alpha), equilibrium_resin(x_to, alpha)
    out = []
    for ion in sorted(IONS, key=lambda i: alpha[i]):          # least held ion first
        dx = x_to[ion] - x_from[ion]
        if abs(dx) < 1e-15:
            continue
        dy = y_to[ion] - y_from[ion]
        ratio = dy / dx if dy / dx > 0.0 else 0.0
        out.append((bv_offset + eps + lam * ratio, ion))
    return out


def renormalise(x):
    s = sum(x.values())
    return {i: x[i] / s for i in IONS}


def history(recipe):
    alpha = recipe["alpha"]
    eps = recipe["eps"]
    CT = recipe["C_T_meq_per_L"]
    lam = 1000.0 * recipe["Q_eq_per_L_bed"] / CT
    x0 = equilibrium_liquid(recipe["initial_resin_fraction"], alpha)
    feeds = recipe["feed_program"]
    events = []                         # (bv, ion, target fraction)
    x_prev = x0
    for step in feeds:
        xF = {i: step["composition_meq_per_L"][i] / CT for i in IONS}
        for bv, ion in fronts_for_step(x_prev, xF, alpha, eps, lam, step["start_bv"]):
            events.append((bv, ion, xF[ion]))
        x_prev = xF
    events.sort(key=lambda e: e[0])
    # effluent plateaus between fronts; fronts at the same position act as one front
    plateaus, shocks = [], []
    current = dict(x0)
    cursor = 0.0
    run_bv = recipe["run_bv"]
    i = 0
    while i < len(events):
        bv = events[i][0]
        if bv > run_bv:
            break
        before = renormalise(current)
        while i < len(events) and events[i][0] == bv:
            current[events[i][1]] = events[i][2]
            i += 1
        after = renormalise(current)
        if bv > cursor:
            plateaus.append((cursor, bv, before))
        shocks.append((bv, before, after))
        cursor = bv
    plateaus.append((cursor, run_bv, renormalise(current)))
    return plateaus, shocks


def to_list(x, CT):
    return [x[i] * CT for i in IONS]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    with open(args.recipe, encoding="utf-8") as fh:
        recipe = json.load(fh)
    CT = recipe["C_T_meq_per_L"]
    plateaus, shocks = history(recipe)
    # merge consecutive plateaus of identical composition (a front with no visible change)
    merged = []
    for b0, b1, x in plateaus:
        if merged and all(abs(merged[-1][2][i] - x[i]) < 1e-15 for i in IONS):
            merged[-1] = (merged[-1][0], b1, x)
        else:
            merged.append((b0, b1, x))
    shocks = [s for s in shocks if any(abs(s[1][i] - s[2][i]) >= 1e-15 for i in IONS)]
    plateaus = [(b0, b1, x) for b0, b1, x in merged if b1 > b0]
    nitrate = [(b0, x["nitrate"] * CT) for b0, b1, x in plateaus]
    peak = max(v for _, v in nitrate)
    peak_bv = min(b for b, v in nitrate if v == peak)
    limit = recipe["nitrate_limit_meq_per_L"]
    limit_bv = None
    for b0, v in nitrate:
        if v > limit:
            limit_bv = b0
            break

    def at(bv):
        for b0, b1, x in plateaus:
            if b0 <= bv <= b1:
                return to_list(x, CT)
        return to_list(plateaus[-1][2], CT)
    report = {
        "recipe_id": recipe["recipe_id"],
        "ions": IONS,
        "shocks": [{"bv": bv, "before_meq_per_L": to_list(b, CT), "after_meq_per_L": to_list(a, CT)} for bv, b, a in shocks],
        "transitions": [],
        "plateaus": [{"bv_start": b0, "bv_end": b1, "composition_meq_per_L": to_list(x, CT)} for b0, b1, x in plateaus],
        "nitrate_peak": {"meq_per_L": peak, "bv": peak_bv},
        "nitrate_limit_bv": limit_bv,
        "samples": [at(bv) for bv in recipe["sample_bv"]],
    }
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
        fh.write("\n")


if __name__ == "__main__":
    main()
