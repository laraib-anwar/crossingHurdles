"""Generate the 28 graded recipes (6 shipped + 22 held-out) with the coverage listed in
IX_SPEC.md section 7, screened with the oracle for the structural guarantees of sections 2
and 4. Deterministic (fixed seed). Dev tool, not shipped.

usage: gen_recipes.py <ixfront.py> <out_dir>
writes <out_dir>/recipes/*.json, <out_dir>/shipped.txt, <out_dir>/recipes.md
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("ixfront", sys.argv[1])
ix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ix)
OUT = Path(sys.argv[2])
(OUT / "recipes").mkdir(parents=True, exist_ok=True)
IONS = ix.IONS
rng = np.random.RandomState(20261019)
TOL_BV_REL, TOL_C = 2e-4, 1e-4
LIMIT = 0.714                          # 10 mg/L as N


def tol_bv(b):
    return max(TOL_BV_REL * abs(b), 1e-6)


# ------------------------------------------------------------------ random pieces
def alphas(nitsel=False, extremes=False):
    while True:
        if extremes:
            a_n = float(rng.choice([1.5, 6.0]))
            a_s = float(rng.choice([2.0, 25.0]))
            a_b = float(rng.choice([0.10, 0.60]))
        else:
            a_n = round(rng.uniform(1.8, 5.0), 3)
            a_s = round(rng.uniform(2.5, 20.0), 3)
            a_b = round(rng.uniform(0.12, 0.55), 3)
        if nitsel and not a_n > a_s + 0.05:
            if a_s > 5.9:
                continue
            a_n = round(rng.uniform(a_s + 0.1, 6.0), 3)
        vals = [1.0, a_n, a_s, a_b]
        if min(abs(u - v) for i, u in enumerate(vals) for v in vals[i + 1:]) >= 0.05:
            return dict(zip(IONS, vals))


def column():
    return dict(eps=round(rng.uniform(0.35, 0.45), 3), Q=round(rng.uniform(0.8, 1.6), 3))


def feed(CT, cl=None, no3=None, so4=None, hco3=None):
    """Composition in meq/L summing exactly to CT; chloride takes the remainder."""
    vals = {}
    vals["nitrate"] = round(rng.uniform(0.3, 1.6), 3) if no3 is None else no3
    vals["sulfate"] = round(rng.uniform(0.4, 0.45 * CT), 3) if so4 is None else so4
    vals["bicarbonate"] = round(rng.uniform(0.3, 0.4 * CT), 3) if hco3 is None else hco3
    rest = CT - vals["nitrate"] - vals["sulfate"] - vals["bicarbonate"]
    if rest < 0.2 * CT:
        return None
    vals["chloride"] = rest
    return {i: float(vals[i]) for i in IONS}


def resin(**fixed):
    y = {i: 0.0 for i in IONS}
    y.update(fixed)
    rest = 1.0 - sum(y.values())
    if rest < 0:
        return None
    y["chloride"] = y.get("chloride", 0.0) + rest
    return {i: float(y[i]) for i in IONS}


def make(rid, al, col, CT, y0, feeds, run_bv, limit=LIMIT):
    return {"recipe_id": rid, "ions": IONS, "alpha": al, "eps": col["eps"], "Q_eq_per_L_bed": col["Q"],
            "C_T_meq_per_L": float(CT), "initial_resin_fraction": y0,
            "feed_program": [{"start_bv": float(s), "composition_meq_per_L": c} for s, c in feeds],
            "run_bv": float(run_bv), "sample_bv": [], "nitrate_limit_meq_per_L": float(limit)}


# ------------------------------------------------------------------ analysis with the oracle
def events_of(rep):
    sh = [s["bv"] for s in rep["shocks"]]
    tr = [(t["bv_start"], t["bv_end"]) for t in rep["transitions"]]
    return sh, tr


def superposition(recipe):
    """Outlet events with the feed change placed after every first-feed wave has left."""
    r = json.loads(json.dumps(recipe))
    if len(r["feed_program"]) < 2:
        return None
    r["feed_program"][1]["start_bv"] = 1e7
    r["run_bv"] = 1e9
    rep = ix.solve(r, n_pieces=NP)
    return rep


def generic_ok(recipe, rep, near=False, min_len=2e-3):
    """Structural guarantees of the spec: separations, plateau lengths, bound margins."""
    run_bv = recipe["run_bv"]
    sh, tr = events_of(rep)
    pts = sorted(sh + [t[0] for t in tr] + [t[1] for t in tr])
    for u, v in zip(pts[:-1], pts[1:]):
        sep = (v - u) / max(1.0, v)
        if sep <= 0 and v != u:
            return False
        if 0 < sep < (3e-4 if near else 1e-3) and not (u in sh and v in sh and u == v):
            return False
    for t0, t1 in tr:
        if (t1 - t0) / max(1.0, t1) < min_len:
            return False
    for p in rep["plateaus"]:
        if (p["bv_end"] - p["bv_start"]) / max(1.0, p["bv_end"]) < (3e-4 if near else 2e-3):
            return False
    for b in sh + [t[0] for t in tr] + [t[1] for t in tr]:
        if b != run_bv and abs(run_bv - b) <= 3 * tol_bv(run_bv):
            return False
    limit = recipe["nitrate_limit_meq_per_L"]
    if abs(rep["nitrate_peak"]["meq_per_L"] - limit) <= 3 * TOL_C:
        return False
    # the limit crossing, when inside a transition, must be steep enough to be well defined
    lb = rep["nitrate_limit_bv"]
    if lb is not None and lb not in sh and lb > 0:
        for t0, t1 in tr:
            if t0 < lb < t1:
                r2 = json.loads(json.dumps(recipe))
                d = 1e-3 * max(1.0, lb)
                r2["sample_bv"] = [lb - d, lb + d]
                s = ix.solve(r2, n_pieces=NP)["samples"]
                slope = (s[1][1] - s[0][1]) / (2 * d)
                if abs(slope) < 5e-3:
                    return False
    return True


def choose_samples(recipe, rep, n):
    """n sample BVs: inside transitions where possible, otherwise on plateaus; never within
    1e-3 (relative) of a shock; rounded to 2 decimals; strictly increasing."""
    run_bv = recipe["run_bv"]
    sh, tr = events_of(rep)
    cands = []
    for t0, t1 in tr:
        for f in (0.25, 0.5, 0.75):
            cands.append(round(t0 + f * (t1 - t0), 2))
    for p in rep["plateaus"]:
        cands.append(round(0.5 * (p["bv_start"] + p["bv_end"]), 2))
    if len(recipe["feed_program"]) == 2:
        s = recipe["feed_program"][1]["start_bv"]
        cands += [round(v, 2) for v in np.linspace(s, run_bv, 6)[1:-1]]
    cands = [c for c in cands if 0 < c <= run_bv and all(abs(c - b) > 1e-3 * max(1.0, b) + 0.01 for b in sh)]
    cands = sorted(set(cands))
    if len(cands) > n:
        idx = sorted(rng.choice(len(cands), n, replace=False))
        cands = [cands[i] for i in idx]
    return cands


NP = 60                                # fan pieces for screening runs (events are exact at any N)


def set_window(recipe, factor=None):
    """Set run_bv from the actual events: a little past the last event (every wave seen), or
    the given fraction of the way to it."""
    r = json.loads(json.dumps(recipe))
    r["run_bv"] = 1e9
    rep = ix.solve(r, n_pieces=NP)
    sh, tr = events_of(rep)
    last = max(sh + [t[1] for t in tr] + [1.0])
    f = factor if factor is not None else rng.uniform(1.08, 1.35)
    recipe["run_bv"] = float(round(min(5000.0, last * f), 0))
    return recipe


def set_limit(recipe, mode):
    """Place the nitrate limit relative to the exact history: inside a transition on which
    nitrate changes, between the two sides of a shock, above the peak, or below the initial
    effluent nitrate."""
    rep = ix.solve(recipe, n_pieces=NP)
    nit = lambda c: c[1]
    if mode == "fan":
        opts = [(nit(t["start_meq_per_L"]), nit(t["end_meq_per_L"])) for t in rep["transitions"]
                if abs(nit(t["end_meq_per_L"]) - nit(t["start_meq_per_L"])) > 0.08]
        # the crossing must be the FIRST exceedance: pick the earliest such transition whose
        # start is below everything reported before it
        for t in rep["transitions"]:
            a, b = nit(t["start_meq_per_L"]), nit(t["end_meq_per_L"])
            if b - a > 0.08:
                prior = [p["composition_meq_per_L"][1] for p in rep["plateaus"] if p["bv_end"] <= t["bv_start"] + 1e-9]
                prior += [s["after_meq_per_L"][1] for s in rep["shocks"] if s["bv"] <= t["bv_start"] + 1e-9]
                lo = max([a] + prior)
                if b - lo > 0.06 and 0.1 <= lo + 0.4 * (b - lo) <= 2.0:
                    recipe["nitrate_limit_meq_per_L"] = round(lo + rng.uniform(0.3, 0.7) * (b - lo), 4)
                    return recipe
        return None
    if mode == "shock":
        for s in rep["shocks"]:
            a, b = nit(s["before_meq_per_L"]), nit(s["after_meq_per_L"])
            prior = [p["composition_meq_per_L"][1] for p in rep["plateaus"] if p["bv_end"] <= s["bv"] + 1e-9]
            prior += [t["end_meq_per_L"][1] for t in rep["transitions"] if t["bv_end"] <= s["bv"] + 1e-9]
            prior += [t["start_meq_per_L"][1] for t in rep["transitions"] if t["bv_end"] <= s["bv"] + 1e-9]
            lo = max([a] + prior)
            if b - lo > 0.06 and 0.1 <= lo + 0.4 * (b - lo) <= 2.0:
                recipe["nitrate_limit_meq_per_L"] = round(lo + rng.uniform(0.3, 0.7) * (b - lo), 4)
                return recipe
        return None
    if mode == "never":
        pk = rep["nitrate_peak"]["meq_per_L"]
        if pk + 0.05 > 2.0:
            return None
        recipe["nitrate_limit_meq_per_L"] = round(min(2.0, pk + rng.uniform(0.05, 0.3)), 4)
        return recipe
    if mode == "zero":
        x0 = rep["plateaus"][0]["composition_meq_per_L"][1] if rep["plateaus"] and rep["plateaus"][0]["bv_start"] == 0 else None
        if x0 is None or x0 < 0.2:
            return None
        recipe["nitrate_limit_meq_per_L"] = round(rng.uniform(0.1, x0 - 0.05), 4)
        return recipe
    return recipe


def finish(recipe, n_samples, near=False, extra_ok=None, min_len=2e-3):
    """Attach samples, run the oracle, check the guarantees and the category predicate."""
    rep = ix.solve(recipe, n_pieces=NP)
    if not generic_ok(recipe, rep, near, min_len):
        return None
    if extra_ok is not None and not extra_ok(recipe, rep):
        return None
    recipe["sample_bv"] = choose_samples(recipe, rep, n_samples)
    rep = ix.solve(recipe, n_pieces=NP)
    return recipe, rep


# ------------------------------------------------------------------ categories
def cat_base(rid, **kw):
    al, col, CT = alphas(**kw), column(), round(rng.uniform(3.0, 9.0), 2)
    f = feed(CT)
    if f is None:
        return None
    return make(rid, al, col, CT, resin(), [(0.0, f)], round(rng.uniform(1.4, 2.2) * 1000 * col["Q"] / CT * 0.5, 0))


def cat_preload(rid, ion):
    al, col, CT = alphas(), column(), round(rng.uniform(3.0, 9.0), 2)
    f = feed(CT, so4=round(rng.uniform(0.3, 0.9), 3)) if ion == "sulfate" else feed(CT)
    if f is None:
        return None
    y0 = resin(**{ion: round(rng.uniform(0.3, 0.7), 3)})
    return make(rid, al, col, CT, y0, [(0.0, f)], round(rng.uniform(1.4, 2.2) * 1000 * col["Q"] / CT * 0.5, 0))


def cat_elution(rid):
    al, col, CT = alphas(), column(), round(rng.uniform(3.0, 12.0), 2)
    y0 = {"chloride": round(rng.uniform(0.1, 0.3), 3), "nitrate": round(rng.uniform(0.15, 0.35), 3),
          "sulfate": round(rng.uniform(0.2, 0.4), 3)}
    y0["bicarbonate"] = round(1.0 - sum(y0.values()), 3)
    if y0["bicarbonate"] < 0.02:
        return None
    f = {"chloride": float(CT), "nitrate": 0.0, "sulfate": 0.0, "bicarbonate": 0.0}
    return make(rid, al, col, CT, {i: float(y0[i]) for i in IONS}, [(0.0, f)], round(rng.uniform(1.5, 2.5) * 1000 * col["Q"] / CT * 0.5, 0))


def cat_absent(rid):
    al, col, CT = alphas(), column(), round(rng.uniform(3.0, 9.0), 2)
    f = feed(CT, hco3=0.0)
    if f is None:
        return None
    return make(rid, al, col, CT, resin(), [(0.0, f)], round(rng.uniform(1.4, 2.2) * 1000 * col["Q"] / CT * 0.5, 0))


def cat_trace(rid):
    al, col, CT = alphas(), column(), round(rng.uniform(3.0, 9.0), 2)
    f = feed(CT, hco3=round(2e-3 * CT, 6))
    if f is None:
        return None
    return make(rid, al, col, CT, resin(), [(0.0, f)], round(rng.uniform(1.4, 2.2) * 1000 * col["Q"] / CT * 0.5, 0))


def cat_limit_never(rid):
    al, col, CT = alphas(), column(), round(rng.uniform(3.0, 9.0), 2)
    f = feed(CT, no3=round(rng.uniform(0.05, 0.25), 3))
    if f is None:
        return None
    return make(rid, al, col, CT, resin(), [(0.0, f)], round(rng.uniform(1.4, 2.2) * 1000 * col["Q"] / CT * 0.5, 0))


def cat_limit_zero(rid):
    al, col, CT = alphas(), column(), round(rng.uniform(3.0, 9.0), 2)
    f = feed(CT)
    if f is None:
        return None
    y0 = resin(nitrate=round(rng.uniform(0.3, 0.6), 3), sulfate=round(rng.uniform(0.1, 0.3), 3))
    return make(rid, al, col, CT, y0, [(0.0, f)], round(rng.uniform(1.4, 2.2) * 1000 * col["Q"] / CT * 0.5, 0))


def cat_two(rid, kind):
    al, col, CT = alphas(), column(), round(rng.uniform(3.0, 9.0), 2)
    if kind in ("cross", "unseen", "late"):
        y0 = resin() if rng.rand() < 0.5 else resin(sulfate=round(rng.uniform(0.2, 0.5), 3))
        f1 = feed(CT)
        f2 = feed(CT)
    else:                                   # absorb: a loaded resin eluted, then more sulfate
        y0 = resin(sulfate=round(rng.uniform(0.3, 0.6), 3))
        f1 = feed(CT, so4=round(rng.uniform(0.3, 0.8), 3))
        f2 = feed(CT, so4=round(rng.uniform(1.5, 0.45 * CT), 3), no3=f1["nitrate"] if f1 else None)
    if f1 is None or f2 is None:
        return None
    base = make(rid, al, col, CT, y0, [(0.0, f1)], 1e9)
    rep = ix.solve(base, n_pieces=NP)
    sh, tr = events_of(rep)
    pts = sorted(sh + [t[0] for t in tr] + [t[1] for t in tr])
    if not pts:
        return None
    first, last = pts[0], pts[-1]
    if kind == "late":
        switch = round(last * rng.uniform(1.05, 1.3), 0)
        run_bv = 1e9                                     # set from the events afterwards
    elif kind == "unseen":
        # the switch comes after the second-to-last first-feed event (the nitrate history is
        # already in the window) and the window closes a fraction of a bed volume later
        anchor = pts[-2] if len(pts) >= 2 else 0.9 * last
        switch = round(anchor + rng.uniform(0.05, 0.3) * (last - anchor), 0)
        # the window closes before the second feed's fastest wave (at least eps BV after the
        # switch, usually much more) can arrive: keep it within a few BV of the switch
        run_bv = round(switch + rng.uniform(0.3, 0.9) * col["eps"], 1)
        if run_bv <= switch:
            return None
    else:
        switch = round(rng.uniform(0.15, 0.75) * last, 0)
        run_bv = 1e9
    if not 0 < switch < run_bv:
        return None
    return make(rid, al, col, CT, y0, [(0.0, f1), (switch, f2)], run_bv)


def cat_short(rid):
    al, col, CT = alphas(), column(), round(rng.uniform(3.0, 9.0), 2)
    f = feed(CT)
    if f is None:
        return None
    r = make(rid, al, col, CT, resin(), [(0.0, f)], 1e9)
    rep = ix.solve(r, n_pieces=NP)
    sh, tr = events_of(rep)
    first = min(sh + [t[0] for t in tr])
    r["run_bv"] = round(rng.uniform(0.5, 0.9) * first, 1)
    return r if r["run_bv"] >= 1 else None


# predicates
def p_limit_in_fan(recipe, rep):
    lb = rep["nitrate_limit_bv"]
    return lb is not None and any(t0 < lb < t1 for t0, t1 in events_of(rep)[1])


def p_limit_never(recipe, rep):
    return rep["nitrate_limit_bv"] is None and rep["nitrate_peak"]["meq_per_L"] < recipe["nitrate_limit_meq_per_L"] - 0.01


def p_limit_zero(recipe, rep):
    return rep["nitrate_limit_bv"] == 0.0


def p_limit_at_shock(recipe, rep):
    lb = rep["nitrate_limit_bv"]
    return lb is not None and lb > 0 and lb in events_of(rep)[0]


def p_has_fan(recipe, rep):
    return len(rep["transitions"]) >= 1


def p_near(recipe, rep):
    sh, tr = events_of(rep)
    pts = sorted(sh + [t[0] for t in tr] + [t[1] for t in tr])
    seps = [(v - u) / max(1.0, v) for u, v in zip(pts[:-1], pts[1:])]
    return any(3e-4 <= s <= 1e-3 for s in seps)


def p_absent_wave(recipe, rep):
    # three waves at most two of which show: with bicarbonate absent, the bicarbonate wave is absent
    return len(rep["shocks"]) + len(rep["transitions"]) <= 2 and len(rep["shocks"]) + len(rep["transitions"]) >= 1


def p_trace(recipe, rep):
    return len(rep["shocks"]) + len(rep["transitions"]) == 3


def interaction_kind(recipe, rep):
    """'cross' when a second-feed wave changed an event without removing a transition,
    'absorb' when a first-feed transition vanished or shortened, None otherwise."""
    sup = superposition(recipe)
    if sup is None:
        return None
    sh0, tr0 = events_of(sup)
    sh1, tr1 = events_of(rep)
    s = recipe["feed_program"][1]["start_bv"]
    run_bv = recipe["run_bv"]
    tr0 = [(a, min(b, run_bv)) for a, b in tr0 if a < run_bv]
    sh0 = [b for b in sh0 if b <= run_bv]
    first_fans = [(a, b) for a, b in tr0 if a < s + 1e-9 or True]
    vanished = any(not any(abs(a - c) < 1e-6 and abs(b - d) < 1e-6 for c, d in tr1) for a, b in tr0 if a < 1e6)
    shocks_changed = len(sh0) != len(sh1) or any(abs(u - v) > 1e-6 for u, v in zip(sorted(sh0), sorted(sh1)))
    after_switch_events = any(b > s for b in sh1) or any(a > s for a, _ in tr1)
    if not after_switch_events:
        return "unseen" if len(recipe["feed_program"]) == 2 else None
    if vanished:
        return "absorb"
    if shocks_changed:
        return "cross"
    return "none"


def p_cross(recipe, rep):
    return interaction_kind(recipe, rep) == "cross"


def p_absorb(recipe, rep):
    return interaction_kind(recipe, rep) == "absorb"


def p_late(recipe, rep):
    sup = superposition(recipe)
    sh0, tr0 = events_of(sup)
    sh1, tr1 = events_of(rep)
    s = recipe["feed_program"][1]["start_bv"]
    return interaction_kind(recipe, rep) == "none" and any(b > s for b in sh1 + [t[0] for t in tr1])


def p_unseen(recipe, rep):
    return interaction_kind(recipe, rep) == "unseen" and (len(rep["shocks"]) + len(rep["transitions"])) >= 2 \
        and rep["nitrate_peak"]["meq_per_L"] > 0.1


def p_short(recipe, rep):
    return len(rep["shocks"]) == 0 and len(rep["transitions"]) == 0 and len(rep["plateaus"]) == 1


# ------------------------------------------------------------------ plan
PLAN = [
    # shipped
    ("service_01", True, lambda rid: cat_base(rid), 6, None, "chloride-form bed, four-ion feed (base case)"),
    ("service_02", True, lambda rid: cat_preload(rid, "sulfate"), 8, p_has_fan, "sulfate-loaded bed"),
    ("service_03", True, lambda rid: cat_elution(rid), 5, None, "complete elution with chloride"),
    ("service_04", True, lambda rid: cat_base(rid, nitsel=True), 7, None, "nitrate-selective resin"),
    ("service_05", True, lambda rid: cat_two(rid, "cross"), 12, p_cross, "feed change, second waves cross first waves"),
    ("service_06", True, lambda rid: cat_preload(rid, "sulfate"), 6, p_limit_in_fan, "limit exceeded inside a spreading wave"),
    # held-out
    ("held_01", False, lambda rid: cat_base(rid), 5, None, "chloride-form bed, four-ion feed"),
    ("held_02", False, lambda rid: cat_base(rid), 9, None, "chloride-form bed, four-ion feed"),
    ("held_03", False, lambda rid: cat_preload(rid, "bicarbonate"), 6, None, "bicarbonate-loaded bed"),
    ("held_04", False, lambda rid: cat_preload(rid, "sulfate"), 7, p_has_fan, "sulfate-loaded bed"),
    ("held_05", False, lambda rid: cat_elution(rid), 6, None, "complete elution with chloride"),
    ("held_06", False, lambda rid: cat_absent(rid), 4, p_absent_wave, "bicarbonate absent from feed and bed"),
    ("held_07", False, lambda rid: cat_trace(rid), 6, p_trace, "bicarbonate at trace level in the feed"),
    ("held_08", False, lambda rid: cat_base(rid, nitsel=True), 6, None, "nitrate-selective resin"),
    ("held_09", False, lambda rid: cat_base(rid), 5, p_near, "nearly coincident outlet events"),
    ("held_10", False, lambda rid: cat_preload(rid, "sulfate"), 6, p_limit_in_fan, "limit exceeded inside a spreading wave"),
    ("held_11", False, lambda rid: cat_limit_never(rid), 5, p_limit_never, "limit never exceeded"),
    ("held_12", False, lambda rid: cat_limit_zero(rid), 5, p_limit_zero, "limit exceeded at BV = 0"),
    ("held_13", False, lambda rid: cat_base(rid), 6, p_limit_at_shock, "limit exceeded at a shock"),
    ("held_14", False, lambda rid: cat_two(rid, "cross"), 8, p_cross, "feed change, crossing waves"),
    ("held_15", False, lambda rid: cat_two(rid, "cross"), 10, p_cross, "feed change, crossing waves"),
    ("held_16", False, lambda rid: cat_two(rid, "absorb"), 8, p_absorb, "feed change, a shock absorbs a spreading wave"),
    ("held_17", False, lambda rid: cat_two(rid, "absorb"), 9, p_absorb, "feed change, a shock absorbs a spreading wave"),
    ("held_18", False, lambda rid: cat_two(rid, "late"), 7, p_late, "feed change after every first wave has left"),
    ("held_19", False, lambda rid: cat_two(rid, "unseen"), 5, p_unseen, "feed change whose waves do not reach the outlet"),
    ("held_20", False, lambda rid: cat_short(rid), 3, p_short, "window ends before the first event"),
    ("held_21", False, lambda rid: cat_base(rid, extremes=True), 0, None, "selectivities at the domain bounds, no samples"),
    ("held_22", False, lambda rid: cat_base(rid), 12, None, "C_T at a domain bound"),
]


LIMIT_MODE = {"service_06": "fan", "held_10": "fan", "held_11": "never", "held_12": "zero", "held_13": "shock"}


def near_coincident(rid):
    """Bisection on alpha_sulfate (close to alpha_nitrate) until two consecutive outlet events
    are 3e-4 to 1e-3 apart in relative BV."""
    base = cat_base(rid)
    if base is None:
        return None
    a_n = base["alpha"]["nitrate"]
    if a_n + 0.6 > 6.0 or a_n + 0.06 < 2.0:
        return None

    def sep_at(a_s):
        r = json.loads(json.dumps(base))
        r["alpha"]["sulfate"] = a_s
        r["run_bv"] = 1e9
        rep = ix.solve(r, n_pieces=NP)
        sh, tr = events_of(rep)
        pts = sorted(sh + [t[0] for t in tr] + [t[1] for t in tr])
        seps = [(v - u) / max(1.0, v) for u, v in zip(pts[:-1], pts[1:]) if v > u]
        return min(seps) if seps else 1.0, r
    lo, hi = max(a_n + 0.005, 2.0), min(a_n + 0.05, 25.0)
    s_lo, _ = sep_at(lo)
    s_hi, _ = sep_at(hi)
    if not (s_lo < 5e-4 < s_hi):
        return None
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        s_mid, r = sep_at(mid)
        if 3.5e-4 <= s_mid <= 9e-4:
            r["alpha"]["sulfate"] = round(mid, 6)
            return r
        if s_mid < 5e-4:
            lo = mid
        else:
            hi = mid
    return None


def main():
    rows, shipped = [], []
    for index, (rid, is_shipped, builder, n_samples, pred, label) in enumerate(PLAN):
        rng.seed(20261019 + 7919 * index)         # one stream per recipe: fixing one leaves the rest unchanged
        got = None
        for attempt in range(300):
            try:
                r = near_coincident(rid) if rid == "held_09" else builder(rid)
                if r is None:
                    continue
                two = len(r["feed_program"]) == 2
                if rid == "held_22":
                    r["C_T_meq_per_L"] = float(rng.choice([2.0, 15.0]))
                    f = r["feed_program"][0]["composition_meq_per_L"]
                    sc = r["C_T_meq_per_L"] / sum(f.values())
                    r["feed_program"][0]["composition_meq_per_L"] = {i: f[i] * sc for i in IONS}
                if rid == "held_20":
                    pass                                   # window set by its builder
                elif two and label.startswith("feed change whose waves do not reach"):
                    pass                                   # window set by its builder
                else:
                    set_window(r)
                    if two and r["feed_program"][1]["start_bv"] >= r["run_bv"]:
                        continue
                if rid in LIMIT_MODE:
                    r = set_limit(r, LIMIT_MODE[rid])
                    if r is None:
                        continue
                got = finish(r, n_samples, near=(rid == "held_09"), extra_ok=pred,
                             min_len=(4e-4 if rid == "held_07" else 2e-3))
            except (AssertionError, ValueError, ZeroDivisionError):
                got = None
            if got is not None:
                break
        if got is None:
            print(f"!! could not build {rid} ({label})")
            continue
        recipe, rep = got
        json.dump(recipe, open(OUT / "recipes" / f"{rid}.json", "w"), indent=1)
        if is_shipped:
            shipped.append(rid)
        sh, tr = events_of(rep)
        rows.append((rid, label, len(sh), len(tr), len(rep["plateaus"]), rep["nitrate_peak"]["meq_per_L"],
                     rep["nitrate_peak"]["bv"], rep["nitrate_limit_bv"], len(recipe["sample_bv"]),
                     len(recipe["feed_program"]), attempt + 1))
        print(f"{rid}: {label}: {len(sh)} shocks, {len(tr)} transitions, peak {rep['nitrate_peak']['meq_per_L']:.3f} @ {rep['nitrate_peak']['bv']:.1f}, limit {rep['nitrate_limit_bv']}, {len(recipe['sample_bv'])} samples ({attempt + 1} tries)")
    (OUT / "shipped.txt").write_text("\n".join(shipped) + "\n")
    with open(OUT / "recipes.md", "w") as fh:
        fh.write("| recipe | covers | shocks | transitions | plateaus | nitrate peak (meq/L) | at BV | limit BV | samples | feeds |\n|---|---|---|---|---|---|---|---|---|---|\n")
        for r in rows:
            lb = "null" if r[7] is None else f"{r[7]:.2f}"
            fh.write(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]:.3f} | {r[6]:.1f} | {lb} | {r[8]} | {r[9]} |\n")


if __name__ == "__main__":
    main()
