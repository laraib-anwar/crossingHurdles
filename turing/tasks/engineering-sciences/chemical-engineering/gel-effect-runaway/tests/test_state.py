"""Verifier for gel-effect-runaway.

Reads the agent artifacts /root/results/predictions.json and /root/results/cure_program.json.
Every casting prediction is compared with the verifier-only truth /tests/truth/expected.json
(written by the data generator from the data-generating model). The cure program is checked
against the limits in /tests/truth/design.json (byte-identical to the agent's
/root/data/design.json) and then run through /tests/plant.py, the data-generating model
itself, with the bubble limit enforced in continuous time over the whole cure.

The four tests each grade one physical question, and each first requires the Outputs contract
(exact schema, finite numbers, normalized distribution; program limits) as a prerequisite, so
no test passes on a well-formed file alone: conversion and exotherm of the castings, their
molar masses, their molar-mass distributions, and the D1 program in the plant. `score()` (the
union of the three casting scorers), `program_errors()` and `plant_errors()` are pure functions
so the author-side comparators are graded by exactly this logic.
"""
import json
import math
from pathlib import Path

import numpy as np
from scipy.integrate import LSODA
from scipy.optimize import minimize_scalar

import plant

HERE = Path(__file__).resolve().parent
PRED_PATH = Path("/root/results/predictions.json")
PROGRAM_PATH = Path("/root/results/cure_program.json")
TRUTH_PATH = HERE / "truth" / "expected.json"
DESIGN_PATH = HERE / "truth" / "design.json"

FIELDS = ["t80_min", "dT_mid_max_K", "t_dT_mid_max_min", "X_avg_t1", "X_avg_end",
          "Mn_avg_end_g_per_mol", "Mw_avg_end_g_per_mol", "Mw_inner_end_g_per_mol",
          "Mw_outer_end_g_per_mol"]
MOLAR_MASSES = FIELDS[5:]
MWD_KEY = "mwd_weight_fractions"
N_BINS = 16                      # bins of log10 M from 4.0 to 8.0, width 0.25, tails folded
TOP_KEYS = {"castings"}          # exact top-level key set
CASTING_KEYS = {"id", *FIELDS, MWD_KEY}   # exact key set of every casting object
PROGRAM_KEYS = {"bath_program"}  # exact key set of cure_program.json

# Acceptance bands (listed in README.md "Verification" and "Calibration of the casting bands").
# Identifiability and calibration:
# - truth/expected.json is generated from plant.py at its HIDDEN constants. instruction.md
#   states plant.py's gel- and glass-effect laws for kp and kt in closed form and withholds the
#   seven constants, which the agent infers from the 7 supplied ampoule conversion and GPC
#   series (137 residuals across 50-70 C and three initiator loadings, w_AIBN = 0.001, 0.002,
#   0.003). The scored extrapolations (C1's low initiator loading, C3's 120 C post-cure, the
#   interior of D1) are therefore fixed by the stated laws and the fitted constants; the bands
#   below cover the error of constants fitted to those series within their stated measurement
#   uncertainties, plus numerical error.
# - The reference solution (`oracle`, the stated laws, 7 constants fitted from neutral starts,
#   137-residual cost 43.64; every converged start reaches the same constants) has worst errors
#   across C1-C4 of t80 1.5 % (band 6 %), t_dT_mid_max 1.2 % (band 12 %), dT_mid_max 0.38x
#   band, X_avg_t1 0.0012 (band 0.010), X_avg_end 0.0032 (band 0.006), molar-mass factor 1.072
#   (band 1.10), MWD L1 0.017 (band 0.05).
# - The bands are not tuned to the reference implementation: an independent piecewise
#   Marten-Hamielec power-law/exponential family fitted solely to the same ampoule data
#   (`marten_ham_pubf`, 5 fitted constants, neither logistic switches nor the stated reference
#   points, cost 127.4; from the revisions in which the laws were withheld) also passes every
#   band on C1-C4 and D1: worst errors t80 4.1 % (band 6 %), t_dT_mid_max 7.8 % (band 12 %),
#   dT_mid_max 0.71x band, X_avg_t1 0.0029 (band 0.010), X_avg_end 0.0010 (band 0.006),
#   molar-mass factor 1.051 (band 1.10), MWD L1 0.042 (band 0.05).
# - Why every term of the stated laws matters (and why the rollouts of the revisions that
#   withheld the laws missed): omitting a term constrained by the joint conversion + GPC
#   ampoule data degrades the 137-residual ampoule fit cost by 2.6x to 112x and fails the
#   castings: omitting the chain-length (Mw) dependence of the gel onset (`no_chain`) worsens
#   the ampoule cost 2.6x (43.64 -> 113) and fails C1 t80 (+8.5 %); omitting its temperature
#   dependence (`no_Et`) worsens the cost 7.5x (to 327) and fails C1/C3; omitting the
#   reaction-diffusion floor (`no_rd`) worsens it 112x (to 4868); fitting the ampoules as
#   isothermal worsens it to 210 (MWD L1 0.131). Both rollout models of the previous revision
#   omitted the chain-length dependence required to jointly fit the GPC and conversion series
#   across initiator loadings (`model_1` / gpt-6-sol had no chain-length term and landed in a
#   high-error ampoule fit with C3/C4 MWD L1 0.128 and 0.106; `model_2` / claude-opus-5-5
#   fitted chain-length exponent n = 0, misplacing low-initiator C1 t80 to 417.80 vs 372.96 min
#   and D1 to 95.017 C < 0.90 X).
T_REL = 0.06                  # t80_min within 6 % (relative)
TPK_REL = 0.12                # t_dT_mid_max_min within 12 % (relative)
DT_REL, DT_ABS = 0.25, 1.5    # dT_mid_max_K within max(1.5 K, 25 % of the true value)
X_T1_ABS = 0.010              # X_avg_t1 within 0.010 (absolute)
X_END_ABS = 0.006             # X_avg_end within 0.006 (absolute)
M_FACTOR = 1.10               # every molar mass within a factor of 1.10
MWD_SUM_TOL = 0.01            # the 16 weight fractions must sum to 1 within 0.01
MWD_L1 = 0.05                 # sum over the bins of |predicted - reference| at most 0.05

# Plant run of the cure program: the data-generating model on 80 finite volumes per
# half-thickness, integrated by LSODA with exactly the settings of plant.simulate_slab
# (integration steps of at most 10 s). On the programs in README.md the hottest temperature of
# a layer below the bubble conversion is within 0.03 K of a 160-volume run, at the mid-plane
# and at the walls. The bubble limit is enforced in continuous time on the integrator's
# solution, not on output samples. For every layer the violation
#     g(t) = min(T(t) - T_bubble, BUBBLE_X_SCALE_K * (X_bubble - X(t)))
# is positive exactly when the layer's conversion is below the bubble conversion and its
# temperature above the bubble temperature. Each integration step's dense output is sampled at
# BUBBLE_SAMPLES equally spaced times, step ends included; around every sampled local maximum
# of a layer's g within BUBBLE_REFINE_K of zero, the maximum of g on the dense output is located
# by a bounded Brent search. Any g > 0 anywhere in [0, cycle time], resolved to about 1e-5 K,
# fails the program.
PLANT_N_EL = 80
PLANT_RTOL = 1e-7
BUBBLE_SAMPLES = 17           # 16 sub-intervals per integration step, so at most 0.625 s apart
BUBBLE_REFINE_K = 2.0
BUBBLE_X_SCALE_K = 100.0      # K per unit conversion; scales g but never changes its sign
BUBBLE_XATOL_S = 1e-4         # time resolution of the Brent search, s


def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(v)
    except (OverflowError, ValueError):   # integer too large for a float
        return False


def _shown(v):
    """repr() raises on integers past the decimal-digit limit; still reject them."""
    try:
        return repr(v)
    except (ValueError, OverflowError):
        return f"<{type(v).__name__} too large to display>"


def _outside(err, limit):
    """Closed band, exact: an error equal to `limit` passes, one above it by any amount fails.
    Every inequality is evaluated in double precision exactly as instruction.md states it,
    with no tolerance beyond the stated band (instruction.md, Acceptance)."""
    return err > limit


def structure_errors(pred, truth):
    """Exact schema: {"castings": [one object per truth id with exactly CASTING_KEYS]}."""
    if not isinstance(pred, dict):
        return [f"top level must be a JSON object, got {type(pred).__name__}"]
    if set(pred) != TOP_KEYS:
        return [f"top-level keys must be exactly {sorted(TOP_KEYS)}, got {sorted(pred)}"]
    cs = pred["castings"]
    if not isinstance(cs, list):
        return [f"'castings' must be a list, got {type(cs).__name__}"]
    if not all(isinstance(c, dict) for c in cs):
        return ["every entry of 'castings' must be a JSON object"]
    ids = [c.get("id") for c in cs]
    want = sorted(c["id"] for c in truth["castings"])
    if not all(isinstance(i, str) for i in ids) or sorted(ids) != want:
        return [f"casting ids {ids!r} != {want} (each exactly once)"]
    errs = []
    for c in cs:
        missing, extra = sorted(CASTING_KEYS - set(c)), sorted(set(c) - CASTING_KEYS)
        if missing:
            errs.append(f"{c['id']}: missing keys {missing}")
        if extra:
            errs.append(f"{c['id']}: unexpected keys {extra}")
        for f in FIELDS:
            if f in c and not _num(c[f]):
                errs.append(f"{c['id']}.{f} not a finite number: {_shown(c[f])}")
        if MWD_KEY in c:
            v = c[MWD_KEY]
            if not isinstance(v, list) or len(v) != N_BINS or not all(_num(x) for x in v):
                errs.append(f"{c['id']}.{MWD_KEY} must be a list of {N_BINS} finite numbers")
            elif min(v) < 0 or _outside(abs(math.fsum(v) - 1.0), MWD_SUM_TOL):
                errs.append(f"{c['id']}.{MWD_KEY} must be non-negative and sum to 1, "
                            f"got sum {math.fsum(v):.4f}")
    return errs


def _pairs(pred, truth):
    """(casting id, predicted object, truth object) for every casting; structure assumed valid."""
    by_id = {c["id"]: c for c in pred["castings"]}
    return [(t["id"], by_id[t["id"]], t) for t in truth["castings"]]


def score_conversion_and_exotherm(pred, truth):
    """Failures of t80_min, dT_mid_max_K, t_dT_mid_max_min, X_avg_t1 and X_avg_end; the
    prediction must already satisfy structure_errors()."""
    errs = []
    for cid, p, t in _pairs(pred, truth):
        for f, tol in (("t80_min", T_REL), ("t_dT_mid_max_min", TPK_REL)):
            if not p[f] > 0 or _outside(abs(p[f] / t[f] - 1.0), tol):
                errs.append(f"{cid}: {f} {p[f]:.2f} vs {t[f]:.2f} (rel tol {tol})")
        dt_tol = max(DT_ABS, DT_REL * t["dT_mid_max_K"])
        if _outside(abs(p["dT_mid_max_K"] - t["dT_mid_max_K"]), dt_tol):
            errs.append(f"{cid}: dT_mid_max_K {p['dT_mid_max_K']:.2f} vs {t['dT_mid_max_K']:.2f} (abs tol {dt_tol:.2f} K)")
        if _outside(abs(p["X_avg_t1"] - t["X_avg_t1"]), X_T1_ABS):
            errs.append(f"{cid}: X_avg_t1 {p['X_avg_t1']:.4f} vs {t['X_avg_t1']:.4f} (abs tol {X_T1_ABS})")
        if _outside(abs(p["X_avg_end"] - t["X_avg_end"]), X_END_ABS):
            errs.append(f"{cid}: X_avg_end {p['X_avg_end']:.4f} vs {t['X_avg_end']:.4f} (abs tol {X_END_ABS})")
    return errs


def score_molar_masses(pred, truth):
    """Failures of the four cumulative molar masses; structure assumed valid."""
    errs = []
    for cid, p, t in _pairs(pred, truth):
        for f in MOLAR_MASSES:
            r = p[f] / t[f] if p[f] > 0 else 0.0   # r underflows to 0 for denormal p: fail, not crash
            if not r > 0 or _outside(abs(math.log(r)), math.log(M_FACTOR)):
                errs.append(f"{cid}: {f} {p[f]:.4g} vs {t[f]:.4g} (factor tol {M_FACTOR})")
    return errs


def score_mwd(pred, truth):
    """Failures of the binned molar-mass distribution (L1 distance); structure assumed valid."""
    errs = []
    for cid, p, t in _pairs(pred, truth):
        l1 = math.fsum(abs(a - b) for a, b in zip(p[MWD_KEY], t[MWD_KEY]))
        if _outside(l1, MWD_L1):
            errs.append(f"{cid}: {MWD_KEY} L1 distance {l1:.3f} (tol {MWD_L1})")
    return errs


def score(pred, truth):
    """Return a list of human-readable failures over every graded quantity; empty list means
    pass. The union of the three casting tests, for the author-side graders."""
    errs = structure_errors(pred, truth)
    if errs:
        return errs
    return score_conversion_and_exotherm(pred, truth) + score_molar_masses(pred, truth) + score_mwd(pred, truth)


def program_errors(doc, spec):
    """Exact schema {"bath_program": [[time_min, temperature_C], ...]} within the limits of
    design.json. Nothing is simulated."""
    if not isinstance(doc, dict):
        return [f"top level must be a JSON object, got {type(doc).__name__}"]
    if set(doc) != PROGRAM_KEYS:
        return [f"top-level keys must be exactly {sorted(PROGRAM_KEYS)}, got {sorted(doc)}"]
    prog, n_max = doc["bath_program"], spec["max_points"]
    if not isinstance(prog, list) or not 2 <= len(prog) <= n_max:
        return [f"'bath_program' must be a list of 2 to {n_max} points"]
    if not all(isinstance(q, list) and len(q) == 2 and _num(q[0]) and _num(q[1]) for q in prog):
        return ["every point must be a list [time_min, temperature_C] of two finite numbers"]
    t, T = [float(q[0]) for q in prog], [float(q[1]) for q in prog]
    errs = []
    if t[0] != 0.0:
        errs.append(f"the first point must be at time 0, got {t[0]}")
    if any(not b > a for a, b in zip(t, t[1:])):
        return errs + ["times must be strictly increasing"]
    if _outside(t[-1], spec["max_cycle_time_min"]):
        errs.append(f"cycle time {t[-1]:.2f} min exceeds {spec['max_cycle_time_min']} min")
    lo, hi = spec["bath_temperature_min_C"], spec["bath_temperature_max_C"]
    if any(_outside(lo - x, 0.0) or _outside(x - hi, 0.0) for x in T):
        errs.append(f"bath temperatures must stay within [{lo}, {hi}] C")
    ramp = spec["max_ramp_K_per_min"]
    for (ta, Ta), (tb, Tb) in zip(zip(t, T), zip(t[1:], T[1:])):
        if _outside(abs(Tb - Ta), ramp * (tb - ta)):
            errs.append(f"ramp from {Ta} C at {ta} min to {Tb} C at {tb} min exceeds {ramp} K/min")
    return errs


def _layer_state(Y, n_el):
    """Conversion and temperature (K) of every layer from flat states Y (n_el*NS, ...)."""
    Y = Y.reshape((n_el, plant.NS) + Y.shape[1:])
    return 1.0 - Y[:, 0] * plant.MM, Y[:, 8]


def _bubble_g(X, T, X_lim, T_lim_K):
    """Violation g: positive exactly when conversion < X_lim and temperature > T_lim_K."""
    return np.minimum(T - T_lim_K, BUBBLE_X_SCALE_K * (X_lim - X))


def _step_violations(dense, ts, g, n_el, X_lim, T_lim_K):
    """All bubble-limit violations found in one integration step, as (t_s, layer, g, X, T_K).
    ts are the sample times, g (n_el, len(ts)) the sampled violation."""
    found = []
    for j in np.flatnonzero(g.max(axis=1) > -BUBBLE_REFINE_K):
        gj = g[j]
        hit = np.flatnonzero(gj > 0.0)
        if hit.size:
            X, T = _layer_state(dense(ts[hit[0]]), n_el)
            found.append((float(ts[hit[0]]), int(j), float(gj[hit[0]]), float(X[j]), float(T[j])))
            continue
        last = len(ts) - 1
        for k in range(len(ts)):
            if gj[k] <= -BUBBLE_REFINE_K or (k > 0 and gj[k - 1] > gj[k]) or (k < last and gj[k + 1] > gj[k]):
                continue                             # not a sampled local maximum near the limit
            lo, hi = ts[max(k - 1, 0)], ts[min(k + 1, last)]

            def neg_g(t, j=j):
                X, T = _layer_state(dense(t), n_el)
                return -float(_bubble_g(X[j], T[j], X_lim, T_lim_K))
            r = minimize_scalar(neg_g, bounds=(lo, hi), method="bounded",
                                options=dict(xatol=BUBBLE_XATOL_S))
            if -r.fun > 0.0:
                X, T = _layer_state(dense(r.x), n_el)
                found.append((float(r.x), int(j), -float(r.fun), float(X[j]), float(T[j])))
    return found


def run_plant(prog, spec, n_el=PLANT_N_EL, rtol=PLANT_RTOL):
    """Integrate sheet D1 under a valid program in the plant and monitor the bubble limit in
    continuous time (see the comment at PLANT_N_EL). The integration always runs to the cycle
    time. Returns the first violation, (t_s, layer, g, X, T_K) for the earliest one found in
    the first integration step that contains any, or None; the hottest temperature (C) of any
    layer below the bubble conversion over the step samples (plus that first violation); and
    the mass-average conversion at the cycle time."""
    program = [[float(a), float(b)] for a, b in prog]
    rhs, y0 = plant.slab_system(float(spec["w_AIBN"]), program, 0.5e-3 * spec["thickness_mm"],
                                spec["h_W_per_m2K"], n_el)
    X_lim, T_lim_K = spec["bubble_conversion"], spec["bubble_temperature_C"] + 273.15
    solver = LSODA(rhs, 0.0, y0, program[-1][0] * 60.0, **plant.slab_solver_options(n_el, rtol))
    first, hottest, dense = None, -np.inf, None
    while solver.status == "running":
        message = solver.step()
        if solver.status == "failed":
            raise RuntimeError(f"plant integration failed at t = {solver.t:.1f} s: {message}")
        dense = solver.dense_output()
        ts = np.linspace(solver.t_old, solver.t, BUBBLE_SAMPLES)
        X, T = _layer_state(dense(ts), n_el)
        under = X < X_lim
        if under.any():
            hottest = max(hottest, float(T[under].max()) - 273.15)
        if first is None:
            found = _step_violations(dense, ts, _bubble_g(X, T, X_lim, T_lim_K), n_el, X_lim, T_lim_K)
            if found:
                first = min(found)
                if first[3] < X_lim:
                    hottest = max(hottest, first[4] - 273.15)
    X_end, _ = _layer_state(dense(solver.t), n_el)   # the state at the cycle time
    return first, hottest, float(X_end.mean())


def plant_errors(prog, spec):
    """Run a valid program through the plant, check the bubble limit in continuous time over
    the whole cure and the mass-average conversion at the cycle time. Returns
    (failures, summary)."""
    first, hottest, X_avg_end = run_plant(prog, spec)
    summary = dict(max_temperature_below_bubble_conversion_C=hottest, X_avg_end=X_avg_end,
                   cycle_time_min=float(prog[-1][0]))
    errs = []
    if first is not None:
        t, j, g, X, T = first
        errs.append(f"bubble limit: at {t / 60.0:.3f} min the layer {j} of {PLANT_N_EL} from the "
                    f"mid-plane is at {T - 273.15:.3f} C with conversion {X:.4f} "
                    f"(limit {spec['bubble_temperature_C']} C below conversion {spec['bubble_conversion']})")
    if _outside(spec["target_conversion"] - X_avg_end, 0.0):
        errs.append(f"mass-average conversion {X_avg_end:.4f} at the end of the program is "
                    f"below {spec['target_conversion']}")
    return errs, summary


def _load():
    truth = json.loads(TRUTH_PATH.read_text())
    assert PRED_PATH.is_file(), f"missing {PRED_PATH}"
    try:
        pred = json.loads(PRED_PATH.read_text(encoding="utf-8"))
    except (ValueError, RecursionError) as e:   # JSONDecodeError and UnicodeDecodeError are ValueErrors
        raise AssertionError(f"{PRED_PATH} is not valid JSON: {e}")
    return pred, truth


def _load_program():
    spec = json.loads(DESIGN_PATH.read_text())
    assert PROGRAM_PATH.is_file(), f"missing {PROGRAM_PATH}"
    try:
        doc = json.loads(PROGRAM_PATH.read_text(encoding="utf-8"))
    except (ValueError, RecursionError) as e:
        raise AssertionError(f"{PROGRAM_PATH} is not valid JSON: {e}")
    return doc, spec


def _valid_predictions():
    """predictions.json loaded and checked against the Outputs contract: a JSON object with
    exactly the required schema, one object per casting C1-C4 holding the nine scalar fields
    as finite numbers and a 16-entry, non-negative, normalized mwd_weight_fractions array.
    Every casting test requires this before it grades anything."""
    pred, truth = _load()
    errs = structure_errors(pred, truth)
    assert not errs, "predictions.json does not meet the Outputs contract:\n" + "\n".join(errs)
    return pred, truth


def test_castings_conversion_and_exotherm():
    """predictions.json meets the Outputs contract and, for every casting, the conversion and
    exotherm quantities t80_min, dT_mid_max_K, t_dT_mid_max_min, X_avg_t1 and X_avg_end lie
    within their acceptance bands around the verifier-only truth."""
    pred, truth = _valid_predictions()
    errs = score_conversion_and_exotherm(pred, truth)
    assert not errs, "\n".join(errs)


def test_castings_molar_masses():
    """predictions.json meets the Outputs contract and, for every casting, the cumulative
    molar masses Mn_avg_end, Mw_avg_end, Mw_inner_end and Mw_outer_end lie within a factor
    M_FACTOR of the verifier-only truth."""
    pred, truth = _valid_predictions()
    errs = score_molar_masses(pred, truth)
    assert not errs, "\n".join(errs)


def test_castings_mwd_fractions():
    """predictions.json meets the Outputs contract and, for every casting, the binned
    molar-mass distribution mwd_weight_fractions is within L1 distance MWD_L1 of the
    verifier-only truth."""
    pred, truth = _valid_predictions()
    errs = score_mwd(pred, truth)
    assert not errs, "\n".join(errs)


def test_cure_program_in_plant():
    """cure_program.json holds only bath_program and the program meets every limit in
    design.json (point count, first time 0, increasing times, temperature range, ramp rate
    and cycle time; an invalid program is never run). Run on sheet D1 in the data-generating
    plant model, it keeps every layer below the bubble conversion at or under the bubble
    temperature at every instant of the cure (checked in continuous time on the integrator's
    dense output, not at output samples) and reaches the target mass-average conversion at
    its last time."""
    doc, spec = _load_program()
    errs = program_errors(doc, spec)
    assert not errs, "an invalid program is not run in the plant:\n" + "\n".join(errs)
    errs, summary = plant_errors(doc["bath_program"], spec)
    print(json.dumps(summary))
    assert not errs, "\n".join(errs)
