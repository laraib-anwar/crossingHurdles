"""Generate the graded washcoat recipes and screen them with the oracle for the guarantees of
WASHCOAT_SPEC.md sections 1 and 2. One random stream per recipe (deterministic).

usage: gen_recipes.py <lightoff_exact.py> <out_dir> <first_index> <last_index>
writes <out_dir>/recipes/<id>.json and <out_dir>/log/<id>.json (summary of the oracle result)
"""
import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("lo", sys.argv[1])
lo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lo)
OUT = Path(sys.argv[2])
(OUT / "recipes").mkdir(parents=True, exist_ok=True)
(OUT / "log").mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------------ steady curve (fast)
def steady_folds(beta, gamma, Bim, Bih):
    L = lo.Layer(dict(beta=beta, gamma=gamma, Bi_m=Bim, Bi_h=Bih, Le=1.0))
    zs = np.linspace(-30.0, 23.0, 400)
    hint, ph, th = None, [], []
    for z in zs:
        s = L.state(lo.cs_of(z), hint)
        hint = s[3]; ph.append(s[0]); th.append(s[1])
    ph = np.array(ph)
    ext = [i for i in range(1, len(ph) - 1) if (ph[i] - ph[i - 1]) * (ph[i + 1] - ph[i]) < 0.0]
    return [float(ph[i]) for i in ext], ph, np.array(th)


def draw_params(rng, kind):
    """Random steady parameters inside the domain, biased towards the wanted fold structure."""
    for _ in range(10000):
        beta = float(round(math.exp(rng.uniform(math.log(0.05), math.log(0.6))), 4))
        gamma = float(round(rng.uniform(8.0, 40.0), 3))
        if kind == "biot_extreme":
            Bim = float(round(rng.uniform(150.0, 200.0), 2))
            Bih = float(round(rng.uniform(max(0.5, beta * Bim), min(50.0, Bim)), 3)) if beta * Bim <= 50 else None
            if Bih is None:
                continue
        else:
            Bim = float(round(math.exp(rng.uniform(math.log(1.0), math.log(200.0))), 3))
            lo_h, hi_h = max(0.5, beta * Bim), min(50.0, Bim)
            if lo_h > hi_h:
                continue
            Bih = float(round(math.exp(rng.uniform(math.log(lo_h), math.log(hi_h))), 3))
        if Bih <= Bim and beta * Bim / Bih <= 1.0 and 0.5 <= Bih <= 50.0:
            return beta, gamma, Bim, Bih
    raise RuntimeError("no parameters")


# ------------------------------------------------------------------ full screening
def tolphi(v):
    return 1e-6 * abs(v)


def eig_ok(w):
    """Spec guarantee at a query state: classification unambiguous."""
    l1 = w[0]
    sc = max(1.0, abs(l1))
    if abs(l1.real) < 1e-4 * sc:
        return False
    if 0.0 < abs(l1.imag) < 1e-3 * sc:
        return False
    return True


def converged(L, cs, c0, phi):
    a = lo.spectrum_n(L, cs, c0, phi, 108)[0]
    b = lo.spectrum_n(L, cs, c0, phi, 162)[0]
    return abs(a - b) <= 1e-6 * max(1.0, abs(b))


def screen(r):
    """Run the oracle and check every guarantee; returns (ok, reason, report, seconds)."""
    t = time.time()
    rep = lo.solve(r)
    secs = time.time() - t
    if secs > 40.0:
        return False, f"slow {secs:.0f}s", rep, secs
    L = lo.Layer(r)
    events = [f["phi"] for f in rep["folds"]] + [h["phi"] for h in rep["hopf_points"]]
    ev = sorted(events)
    for a, b in zip(ev, ev[1:]):
        if (b - a) / b < 1e-3:
            return False, "events too close", rep, secs
    for q in r["phi_query"]:
        for e in ev:
            if abs(q - e) / e < 1e-3:
                return False, "query near event", rep, secs
    for h in rep["hopf_points"]:
        if h["omega"] < 0.05:
            return False, "small omega", rep, secs
    # one state at each window end, every fold strictly inside
    for end in (r["phi_min"], r["phi_max"]):
        rr = dict(r, phi_query=[end])
        n = len(lo.solve_states_only(L, rr)[0]["branches"]) if hasattr(lo, "solve_states_only") else None
        if n is not None and n != 1:
            return False, "multiple states at a window end", rep, secs
    # query states: unambiguous and converged spectra
    zs = np.linspace(-30.0, 23.0, 400)
    for st in rep["states"]:
        for b in st["branches"]:
            pass
    for st in rep["states"]:
        q = st["phi"]
        for zq in crossings(L, q):
            cs = lo.cs_of(zq)
            phi, thc, eta, c0 = L.state(cs)
            w = lo.spectrum(L, cs, c0, phi)
            if not eig_ok(w):
                return False, f"ambiguous spectrum at phi {q}", rep, secs
            if not converged(L, cs, c0, phi):
                return False, f"unconverged spectrum at phi {q}", rep, secs
    for h in rep["hopf_points"]:
        zq = crossings(L, h["phi"])
        # the Hopf state itself must be resolved too
        for z in zq:
            cs = lo.cs_of(z)
            phi, thc, eta, c0 = L.state(cs)
            if abs(thc - h["theta_c"]) < 1e-6 and not converged(L, cs, c0, phi):
                return False, "unconverged spectrum at a Hopf point", rep, secs
    return True, "ok", rep, secs


_CURVES = {}


def curve(L):
    key = (L.beta, L.gamma, L.Bim, L.Bih)
    if key not in _CURVES:
        zs = np.linspace(-30.0, 23.0, 400)
        hint, ph = None, []
        for z in zs:
            s = L.state(lo.cs_of(z), hint)
            hint = s[3]; ph.append(s[0])
        _CURVES[key] = (zs, np.array(ph))
    return _CURVES[key]


def crossings(L, q):
    from scipy.optimize import brentq
    zs, ph = curve(L)
    out = []
    for i in range(len(zs) - 1):
        if (ph[i] - q) * (ph[i + 1] - q) < 0.0:
            out.append(brentq(lambda z: L.state(lo.cs_of(z))[0] - q, zs[i], zs[i + 1], xtol=1e-12))
    return out


def window_and_queries(rng, folds, extra_events=()):
    """Window strictly around every fold (one state at both ends) and queries on every branch."""
    if folds:
        fmin, fmax = min(folds), max(folds)
        phi_min = float(round(max(0.01, fmin / rng.uniform(2.5, 6.0)), 4))
        phi_max = float(round(min(30.0, fmax * rng.uniform(2.5, 6.0)), 3))
    else:
        phi_min = float(round(math.exp(rng.uniform(math.log(0.01), math.log(0.3))), 4))
        phi_max = float(round(min(30.0, phi_min * rng.uniform(10.0, 200.0)), 3))
    phi_max = max(phi_max, 3.0 * phi_min, 0.3)
    pts = sorted(set(list(folds) + list(extra_events)))
    qs = [phi_min * rng.uniform(1.2, 2.0)]
    edges = [phi_min] + pts + [phi_max]
    for a, b in zip(edges[:-1], edges[1:]):
        if b > a * 1.002:
            qs.append(a + rng.uniform(0.3, 0.7) * (b - a))
    qs.append(phi_max / rng.uniform(1.2, 2.0))
    qs = sorted(set(float(f"{q:.6g}") for q in qs if phi_min <= q <= phi_max))
    qs = [q for i, q in enumerate(qs) if i == 0 or q > qs[i - 1] * 1.0001][:8]
    return phi_min, phi_max, qs


def ends_single(L, phi_min, phi_max):
    zs, ph = curve(L)
    return len(crossings(L, phi_min)) == 1 and len(crossings(L, phi_max)) == 1


# ------------------------------------------------------------------ categories
# (id, shipped, n_folds wanted, Le range, n_hopf wanted, extra predicate name, label)
PLAN = [
    ("lightoff_01", True, 2, (1.0, 1.0), 0, None, "two folds, Le = 1 (base case)"),
    ("lightoff_02", True, 0, (0.5, 3.0), 0, None, "unique steady state"),
    ("lightoff_03", True, 2, (0.05, 0.5), 1, None, "two folds, one Hopf point, Le < 1"),
    ("lightoff_04", True, 4, (0.5, 3.0), 0, None, "four folds (two hysteresis loops)"),
    ("lightoff_05", True, 2, (2.0, 20.0), 0, None, "two folds, Le > 1"),
    ("lightoff_06", True, 2, (0.05, 0.5), 2, None, "two folds, two Hopf points"),
    ("held_01", False, 0, (0.05, 20.0), 0, None, "unique steady state"),
    ("held_02", False, 0, (0.05, 20.0), 0, "biot_extreme", "unique, Biot numbers at the domain bounds"),
    ("held_03", False, 2, (1.0, 1.0), 0, None, "two folds, Le = 1"),
    ("held_04", False, 2, (0.8, 1.5), 0, None, "two folds"),
    ("held_05", False, 2, (2.0, 20.0), 0, None, "two folds, Le > 1"),
    ("held_06", False, 2, (5.0, 20.0), 0, None, "two folds, large Le"),
    ("held_07", False, 2, (0.05, 0.5), 1, None, "one Hopf point, Le < 1"),
    ("held_08", False, 2, (0.05, 0.5), 1, None, "one Hopf point, Le < 1"),
    ("held_09", False, 2, (0.05, 0.1), 1, None, "one Hopf point, small Le"),
    ("held_10", False, 2, (0.05, 0.5), 2, None, "two Hopf points"),
    ("held_11", False, 2, (0.05, 0.5), 2, None, "two Hopf points"),
    ("held_12", False, 4, (0.5, 3.0), 0, None, "four folds"),
    ("held_13", False, 4, (0.5, 3.0), 0, None, "four folds"),
    ("held_14", False, 4, (0.05, 0.5), -1, None, "four folds, Le < 1"),
    ("held_15", False, 2, (0.5, 3.0), 0, "near_cusp", "two nearly coincident folds"),
    ("held_16", False, 2, (0.05, 0.5), 1, "hopf_near_fold", "Hopf point close to a fold"),
    ("held_17", False, 2, (0.5, 3.0), 0, "biot_extreme", "two folds, Biot numbers at the bounds"),
    ("held_18", False, 2, (0.05, 0.5), -1, "biot_extreme", "two folds, Biot extreme, Le < 1"),
    ("held_19", False, 2, (1.0, 1.0), 0, None, "two folds, Le = 1"),
    ("held_20", False, 2, (0.2, 0.8), -1, None, "two folds, Le near the Hopf onset"),
    ("held_21", False, 0, (0.05, 0.3), -1, None, "unique, small Le"),
    ("held_22", False, 2, (0.5, 3.0), 0, None, "two folds"),
]


def build(index):
    rid, shipped, nf, (le0, le1), nh, extra, label = PLAN[index]
    rng = np.random.RandomState(20261020 + 7919 * index)
    t0 = time.time()
    for attempt in range(400):
        if time.time() - t0 > 1800:
            break
        beta, gamma, Bim, Bih = draw_params(rng, "biot_extreme" if extra == "biot_extreme" else "any")
        try:
            folds, ph, th = steady_folds(beta, gamma, Bim, Bih)
        except Exception:
            continue
        if len(folds) != nf:
            continue
        if folds and (min(folds) < 0.03 or max(folds) > 8.0):
            continue
        fs = sorted(folds)
        seps = [(b - a) / b for a, b in zip(fs, fs[1:])]
        if extra == "near_cusp" and not (seps and 1e-3 <= min(seps) <= 1.5e-2):
            continue
        if extra != "near_cusp" and seps and min(seps) < 1.5e-2:
            continue
        Le = 1.0 if le0 == le1 else float(round(math.exp(rng.uniform(math.log(le0), math.log(le1))), 4))
        L = lo.Layer(dict(beta=beta, gamma=gamma, Bi_m=Bim, Bi_h=Bih, Le=Le))
        phi_min, phi_max, qs = window_and_queries(rng, folds)
        if not ends_single(L, phi_min, phi_max):
            continue
        r = dict(recipe_id=rid, beta=beta, gamma=gamma, Bi_m=Bim, Bi_h=Bih, Le=Le,
                 phi_min=phi_min, phi_max=phi_max, phi_query=qs)
        try:
            rep = lo.solve(r)
        except Exception:
            continue
        hops = [h["phi"] for h in rep["hopf_points"]]
        if nh >= 0 and len(hops) != nh:
            continue
        if extra == "hopf_near_fold" and not any(1e-3 <= abs(h - f) / f <= 2e-2 for h in hops for f in folds):
            continue
        # requery so that every interval between events (folds and Hopf points) holds a query
        phi_min, phi_max, qs = window_and_queries(rng, folds, hops)
        r.update(phi_min=phi_min, phi_max=phi_max, phi_query=qs)
        if not ends_single(L, phi_min, phi_max):
            continue
        try:
            ok, why, rep, secs = screen(r)
        except Exception as e:
            ok, why = False, f"error {e}"
        if not ok:
            continue
        json.dump(r, open(OUT / "recipes" / f"{rid}.json", "w"), indent=1)
        nstates = [len(s["branches"]) for s in rep["states"]]
        log = dict(recipe_id=rid, shipped=shipped, label=label, folds=len(rep["folds"]), hopf=len(rep["hopf_points"]),
                   states=nstates, secs=round(secs, 1), attempts=attempt + 1)
        json.dump(log, open(OUT / "log" / f"{rid}.json", "w"), indent=1)
        print(json.dumps(log), flush=True)
        return
    print(json.dumps(dict(recipe_id=rid, failed=True, label=label)), flush=True)


if __name__ == "__main__":
    for i in range(int(sys.argv[3]), int(sys.argv[4]) + 1):
        build(i)
