"""Generate the graded structures and screen them with the oracle for every guarantee of
HETERO_SPEC.md section 2. One random stream per slot.

usage: gen_structures.py <hetero.py> <out_dir> [indices...]
"""
import importlib
import importlib.util
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("ht", sys.argv[1])
ht = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ht)
sys.modules["pytest"] = importlib.import_module("pytest")
_tv = importlib.util.spec_from_file_location("tv", Path(sys.argv[1]).resolve().parents[1] / "tests/test_outputs.py")
tv = importlib.util.module_from_spec(_tv)
_tv.loader.exec_module(tv)
OUT = Path(sys.argv[2])
(OUT / "structures").mkdir(parents=True, exist_ok=True)
(OUT / "log").mkdir(parents=True, exist_ok=True)
DEBUG = bool(os.environ.get("GEN_DEBUG"))


def r4(v):
    return float(f"{v:.4g}")


def U(rng, lo, hi):
    return float(rng.uniform(lo, hi))


def mass(rng, kind):
    return r4({"gaas": U(rng, 0.06, 0.075), "algaas": U(rng, 0.08, 0.15), "ingaas": U(rng, 0.035, 0.05),
               "heavy": U(rng, 0.2, 1.0)}[kind])


def build(rng, style):
    """Flat band profile (thickness, mass, v) list, lead masses/edges, before bias."""
    Vb = U(rng, 0.15, 1.0)
    mw, mb = mass(rng, "gaas"), mass(rng, "algaas")
    lead_low = dict(mass=mw, v=0.0)
    lead_high = dict(mass=mb, v=Vb)
    layers, lead_L, lead_R, bias = [], lead_low, dict(lead_low), 0.0
    if style == "rtd":
        well_v = -U(rng, 0.05, 0.25) if rng.rand() < 0.6 else 0.0
        mi = mass(rng, "ingaas") if well_v < 0 else mw
        layers = [(U(rng, 2, 10), mw, 0.0), (U(rng, 1.5, 5), mb, Vb), (U(rng, 3, 8), mi, well_v), (U(rng, 1.5, 5), mb, Vb), (U(rng, 2, 10), mw, 0.0)]
        bias = U(rng, 0.0, 0.3)
    elif style == "confined":
        n_w = int(rng.randint(1, 4))
        for k in range(n_w):
            layers += [(U(rng, 1, 6), mb, Vb), (U(rng, 2, 15), mw, U(rng, -0.1, 0.0))]
        layers += [(U(rng, 1, 6), mb, Vb)]
        lead_L, lead_R = lead_high, dict(lead_high)
    elif style == "double_well":
        w = U(rng, 4, 10)
        layers = [(U(rng, 3, 8), mb, Vb), (w, mw, 0.0), (U(rng, 1.5, 6), mb, Vb), (w * U(rng, 0.97, 1.03), mw, 0.0), (U(rng, 3, 8), mb, Vb)]
        lead_L, lead_R = lead_high, dict(lead_high)
    elif style == "double_well_tight":
        w = U(rng, 4, 10)
        Vb = U(rng, 0.4, 1.0)
        layers = [(U(rng, 3, 8), mb, Vb), (w, mw, 0.0), (U(rng, 5, 10), mb, Vb), (w * U(rng, 0.995, 1.005), mw, 0.0), (U(rng, 3, 8), mb, Vb)]
        lead_L, lead_R = dict(mass=mb, v=Vb), dict(mass=mb, v=Vb)
    elif style == "triangular":
        layers = [(U(rng, 15, 30), mw, None), (U(rng, 2, 10), mb, Vb)]
        lead_L = dict(mass=mb, v=Vb + U(rng, 0.0, 0.2))
        lead_R = dict(lead_high)
    elif style == "superlattice":
        n = int(rng.randint(3, 7))
        dw, db = U(rng, 2, 8), U(rng, 1, 4)
        for k in range(n):
            layers += [(db, mb, Vb), (dw, mw, 0.0)]
        layers += [(db, mb, Vb)]
        if rng.rand() < 0.5:
            lead_L, lead_R = lead_high, dict(lead_high)
    elif style == "barrier_only":
        n = int(rng.randint(1, 4))
        for k in range(n):
            layers += [(U(rng, 1, 8), mb, U(rng, 0.1, Vb)), (U(rng, 1, 8), mw, U(rng, 0.0, 0.05))]
        layers = layers[:-1] if len(layers) > 2 else layers + [(U(rng, 1, 5), mw, 0.0)]
    elif style == "thick":
        layers = [(U(rng, 2, 5), mw, 0.0), (U(rng, 12, 25), mb, Vb), (U(rng, 4, 8), mw, 0.0), (U(rng, 12, 25), mb, Vb), (U(rng, 2, 5), mw, 0.0)]
    elif style == "contrast":
        layers = [(U(rng, 2, 8), mass(rng, "heavy"), U(rng, 0.2, 0.8)), (U(rng, 3, 10), mass(rng, "ingaas"), U(rng, -0.3, 0.0)),
                  (U(rng, 2, 8), mass(rng, "heavy"), U(rng, 0.2, 0.8))]
        lead_L = dict(mass=mass(rng, "gaas"), v=U(rng, 0.0, 0.1))
        lead_R = dict(mass=mass(rng, "heavy"), v=U(rng, -0.2, 0.15))
    elif style == "graded":
        layers = [(U(rng, 5, 20), mb, None), (U(rng, 3, 10), mw, 0.0), (U(rng, 5, 20), mb, None)]
        lead_L, lead_R = lead_high, dict(lead_high)
    return layers, lead_L, lead_R, bias, Vb, style


def finish(rng, built):
    layers, lead_L, lead_R, bias, Vb, style = built
    X = sum(t for t, _, _ in layers)
    out, x = [], 0.0
    for k, (t, m, v) in enumerate(layers):
        if v is None:                       # graded or triangular layer: linear ramp
            if style == "triangular":
                va, vb_ = U(rng, -0.2, 0.05), Vb * U(rng, 0.5, 1.0)
            else:
                va, vb_ = (Vb, 0.0) if k == 0 else (0.0, Vb)
            vl, vr = va, vb_
        else:
            vl = vr = v
        vl -= bias * x / X
        vr -= bias * (x + t) / X
        out.append(dict(thickness_nm=r4(t), mass=r4(m), vl_eV=r4(vl), vr_eV=r4(vr)))
        x += t
    for ly in out:                          # flat after rounding or too gentle a slope -> flat
        if ly["vl_eV"] != ly["vr_eV"] and abs(ly["vr_eV"] - ly["vl_eV"]) / ly["thickness_nm"] < 1e-3:
            ly["vr_eV"] = ly["vl_eV"]
    L = dict(mass=r4(lead_L["mass"]), v_eV=r4(lead_L["v"]))
    R = dict(mass=r4(lead_R["mass"]), v_eV=r4(lead_R["v"] - bias))
    return out, L, R


def choose_queries(rng, st, layers, L, R):
    vmax = max([L["v_eV"], R["v_eV"]] + [v for ly in layers for v in (ly["vl_eV"], ly["vr_eV"])])
    edge = max(L["v_eV"], R["v_eV"])
    n = int(rng.randint(2, 9))
    Es = sorted({r4(U(rng, edge + 2e-3, vmax + 0.5)) for _ in range(n)})
    width = U(rng, 0.05, 0.6)
    lo = r4(vmax + U(rng, 0.011, 0.2))
    return Es, [lo, r4(lo + width)]


def extrema(T, grid):
    d = np.diff(T)
    s = np.sign(d)
    idx = [k for k in range(1, len(s)) if s[k] != s[k - 1] and s[k] != 0 and s[k - 1] != 0]
    return idx


def screen(m, want):
    try:
        tv.validate_structure(m, m["structure_id"])
    except AssertionError as error:
        return False, f"domain: {str(error)[:80]}", None
    t0 = time.time()
    try:
        rep = ht.solve(m)
    except Exception as error:
        return False, f"oracle: {error!r}"[:100], None
    secs = time.time() - t0
    if secs > 40:
        return False, "slow", rep
    st = ht.Structure(m)
    E_th = min(m["left_lead"]["v_eV"], m["right_lead"]["v_eV"])
    bs = [b["E_eV"] for b in rep["bound_states"]]
    if len(bs) > 40:
        return False, "too many bound states", rep
    if any(b - a < 1e-6 for a, b in zip(bs, bs[1:])):
        return False, "bound states too close", rep
    if bs and E_th - bs[-1] < 1e-4:
        return False, "bound state near threshold", rep
    for t in rep["transmission"]:
        E = t["E_eV"]
        if t["T"] < 1e-30:
            return False, "T too small", rep
        h = 1e-6
        dl = (st.log_transmission(E + h)[0] - st.log_transmission(E - h)[0]) / (2 * h)
        if abs(dl) > 1e3:
            return False, "T ill-conditioned at a query", rep
    lo, hi = m["window_eV"]
    for step in (1e-5, 2.5e-6):
        grid = np.linspace(lo, hi, int(math.ceil((hi - lo) / step)) + 1)
        T = st.T(grid)
        ex = extrema(T, grid)
        Ee = [grid[k] for k in ex]
        if any(b - a < 2e-4 for a, b in zip(Ee, Ee[1:])):
            return False, "extrema too close", rep
        if Ee and (Ee[0] - lo < 2e-4 or hi - Ee[-1] < 2e-4):
            return False, "extremum near window end", rep
        nmax = sum(1 for k in ex if T[k] > T[k - 1])
        if nmax != len(rep["maxima"]):
            return False, f"maxima count mismatch at step {step}", rep
        # prominence
        vals = [T[0]] + [T[k] for k in ex] + [T[-1]]
        kinds = ["end"] + ["max" if T[k] > T[k - 1] else "min" for k in ex] + ["end"]
        for j, kd in enumerate(kinds):
            if kd == "max":
                nb = [vals[j - 1], vals[j + 1]]
                if any(vals[j] < 1.001 * v for v in nb):
                    return False, "maximum not prominent", rep
    return True, "ok", rep


def predicate(want, m, rep):
    nb, nm = len(rep["bound_states"]), len(rep["maxima"])
    Ts = [t["T"] for t in rep["transmission"]]
    if "min_bound" in want and nb < want["min_bound"]: return False
    if "max_bound" in want and nb > want["max_bound"]: return False
    if "min_maxima" in want and nm < want["min_maxima"]: return False
    if "max_maxima" in want and nm > want["max_maxima"]: return False
    if "min_T_below" in want and min(Ts) > want["min_T_below"]: return False
    if want.get("tight_pair"):
        bs = [b["E_eV"] for b in rep["bound_states"]]
        if not any(b - a < 2e-5 for a, b in zip(bs, bs[1:])): return False
    if want.get("pair"):
        bs = [b["E_eV"] for b in rep["bound_states"]]
        if not any(b - a < 1e-3 for a, b in zip(bs, bs[1:])): return False
    if want.get("sloped") and not any(ly["vl_eV"] != ly["vr_eV"] for ly in m["layers"]): return False
    if want.get("lead_contrast") and not (m["left_lead"]["mass"] != m["right_lead"]["mass"] and m["left_lead"]["v_eV"] != m["right_lead"]["v_eV"]): return False
    return True


PLAN = [
    ("model_01", True, "confined", dict(min_bound=2, max_bound=6, min_maxima=1), "quantum wells confined by the lead band edge (base case)"),
    ("model_02", True, "rtd", dict(sloped=True, min_maxima=1), "resonant-tunnelling diode under bias"),
    ("model_03", True, "double_well", dict(pair=True), "double well with closely spaced levels"),
    ("model_04", True, "triangular", dict(min_bound=5, sloped=True), "triangular well with many levels"),
    ("model_05", True, "thick", dict(min_T_below=1e-15), "thick double barrier, tiny transmission"),
    ("model_06", True, "contrast", dict(lead_contrast=True), "different lead masses and band edges"),
    ("held_01", False, "confined", dict(min_bound=1), "single confined well"),
    ("held_02", False, "confined", dict(min_bound=6), "multiple confined wells"),
    ("held_03", False, "double_well_tight", dict(tight_pair=True), "double well, pair split by less than 2e-5 eV"),
    ("held_04", False, "double_well", dict(min_bound=4), "double well, several pairs"),
    ("held_05", False, "triangular", dict(min_bound=8), "triangular well, eight or more levels"),
    ("held_06", False, "triangular", dict(sloped=True, max_bound=4), "shallow triangular well"),
    ("held_07", False, "rtd", dict(sloped=True, min_T_below=1e-6), "biased RTD, tunnelling queries"),
    ("held_08", False, "rtd", dict(min_bound=1), "RTD with a well below the leads"),
    ("held_09", False, "superlattice", dict(min_maxima=4), "superlattice, four or more maxima"),
    ("held_10", False, "superlattice", dict(min_maxima=8), "superlattice, eight or more maxima"),
    ("held_11", False, "barrier_only", dict(max_bound=0), "barriers only: no bound state"),
    ("held_12", False, "barrier_only", dict(max_bound=0, max_maxima=0), "no bound state, window with no maximum"),
    ("held_13", False, "thick", dict(min_T_below=1e-22), "thick barriers, transmission below 1e-22"),
    ("held_14", False, "thick", dict(min_T_below=1e-10), "thick barriers"),
    ("held_15", False, "contrast", dict(lead_contrast=True, min_bound=1), "lead contrast with a bound state"),
    ("held_16", False, "contrast", dict(lead_contrast=True), "lead contrast"),
    ("held_17", False, "graded", dict(sloped=True, min_bound=1), "graded barriers around a well"),
    ("held_18", False, "graded", dict(sloped=True, min_maxima=2), "graded barriers, several maxima"),
    ("held_19", False, "rtd", dict(sloped=True, min_maxima=3), "RTD, several maxima"),
    ("held_20", False, "confined", dict(min_bound=3, min_maxima=3), "confined wells with maxima above"),
    ("held_21", False, "superlattice", dict(min_bound=3), "superlattice with bound miniband"),
    ("held_22", False, "double_well", dict(pair=True, min_maxima=2), "double well, close pair and maxima"),
]


def build_slot(index):
    sid, shipped, style, want, label = PLAN[index]
    rng = np.random.RandomState(20261025 + 7919 * index)
    t0 = time.time()
    for attempt in range(2000):
        if time.time() - t0 > 1800:
            break
        built = build(rng, style)
        layers, L, R = finish(rng, built)
        Es, win = choose_queries(rng, None, layers, L, R)
        m = dict(structure_id=sid, left_lead=L, right_lead=R, layers=layers, transmission_energies_eV=Es, window_eV=win)
        ok, why, rep = screen(m, want)
        if not ok:
            if DEBUG:
                print("  reject", why, flush=True)
            continue
        if not predicate(want, m, rep):
            if DEBUG:
                print("  reject predicate", len(rep["bound_states"]), len(rep["maxima"]), flush=True)
            continue
        json.dump(m, open(OUT / "structures" / f"{sid}.json", "w"), indent=1)
        log = dict(structure_id=sid, shipped=shipped, style=style, label=label, attempts=attempt + 1, layers=len(layers),
                   bound=len(rep["bound_states"]), maxima=len(rep["maxima"]), minT=min(t["T"] for t in rep["transmission"]))
        json.dump(log, open(OUT / "log" / f"{sid}.json", "w"), indent=1)
        print(json.dumps(log), flush=True)
        return
    print(json.dumps(dict(structure_id=sid, failed=True, label=label)), flush=True)


if __name__ == "__main__":
    idx = [int(v) for v in sys.argv[3:]] or list(range(len(PLAN)))
    for i in idx:
        build_slot(i)
