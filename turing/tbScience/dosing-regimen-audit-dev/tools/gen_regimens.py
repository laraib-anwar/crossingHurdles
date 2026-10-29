"""Generate the graded regimens and screen them with the oracle for every guarantee of
REGIMEN_SPEC.md section 2. One random stream per slot and attempt.

usage: gen_regimens.py <regimen.py> <out_dir> [indices...]
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

spec = importlib.util.spec_from_file_location("rg", sys.argv[1])
rg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rg)
sys.modules["pytest"] = importlib.import_module("pytest")
_tv = importlib.util.spec_from_file_location("tv", Path(sys.argv[1]).resolve().parents[1] / "tests/test_outputs.py")
tv = importlib.util.module_from_spec(_tv)
_tv.loader.exec_module(tv)
OUT = Path(sys.argv[2])
(OUT / "regimens").mkdir(parents=True, exist_ok=True)
(OUT / "expected").mkdir(parents=True, exist_ok=True)
(OUT / "log").mkdir(parents=True, exist_ok=True)
DEBUG = bool(os.environ.get("GEN_DEBUG"))

# slot -> style flags. 6 shipped (model_01..06) then 22 held-out.
PLAN = [
    ("model_01", dict(cpt=1, mm=False, routes=["iv_infusion_load", "iv_bolus"], nd=1)),
    ("model_02", dict(cpt=2, mm=False, routes=["oral"], nd=1, lag=True)),
    ("model_03", dict(cpt=3, mm=False, routes=["iv_infusion"], nd=2)),
    ("model_04", dict(cpt=1, mm=True, routes=["oral"], nd=2, transit=True)),
    ("model_05", dict(cpt=2, mm=True, routes=["iv_bolus", "oral"], nd=2, loading=2)),
    ("model_06", dict(cpt=2, mm=False, routes=["iv_infusion"], nd=2, overlap=True)),
    ("held_01", dict(cpt=1, mm=False, routes=["iv_bolus"], nd=1, slow=True)),
    ("held_02", dict(cpt=2, mm=False, routes=["oral"], nd=1, two_forms=True, transit=True)),
    ("held_03", dict(cpt=3, mm=True, routes=["iv_infusion", "oral"], nd=2, loading=1)),
    ("held_04", dict(cpt=1, mm=True, routes=["iv_bolus"], nd=3, unequal=True)),
    ("held_05", dict(cpt=2, mm=False, routes=["iv_infusion"], nd=1, wrap=True)),
    ("held_06", dict(cpt=2, mm=True, routes=["oral"], nd=1, lag=True, transit=True, slow=True)),
    ("held_07", dict(cpt=1, mm=False, routes=["oral"], nd=3, two_forms=True, lag=True)),
    ("held_08", dict(cpt=3, mm=False, routes=["iv_bolus", "iv_infusion"], nd=2, loading=3, gap=True)),
    ("held_09", dict(cpt=2, mm=True, routes=["iv_infusion"], nd=2, overlap=True, loading=1)),
    ("held_10", dict(cpt=1, mm=False, routes=["iv_bolus"], nd=4, multi_window=True)),
    ("held_11", dict(cpt=2, mm=False, routes=["oral"], nd=2, transit=True, lagwrap=True)),
    ("held_12", dict(cpt=3, mm=True, routes=["oral", "iv_bolus"], nd=3, two_forms=True)),
    ("held_13", dict(cpt=1, mm=True, routes=["iv_infusion"], nd=1, strong_mm=True)),
    ("held_14", dict(cpt=2, mm=False, routes=["iv_bolus"], nd=1, fast=True, loading=1, dip=True)),
    ("held_15", dict(cpt=2, mm=True, routes=["oral"], nd=2, lag=True, unequal=True)),
    ("held_16", dict(cpt=3, mm=False, routes=["iv_infusion"], nd=3, overlap=True, wrap=True)),
    ("held_17", dict(cpt=1, mm=False, routes=["oral", "iv_infusion"], nd=2, transit=True, loading=2, gap=True)),
    ("held_18", dict(cpt=2, mm=True, routes=["iv_bolus"], nd=2, slow=True)),
    ("held_19", dict(cpt=3, mm=True, routes=["oral"], nd=1, two_forms=True, transit=True, lag=True)),
    ("held_20", dict(cpt=1, mm=False, routes=["iv_bolus", "oral"], nd=5, multi_window=True)),
    ("held_21", dict(cpt=2, mm=False, routes=["iv_infusion", "oral"], nd=2, loading=3, gap=True, dip=True)),
    ("held_22", dict(cpt=2, mm=True, routes=["oral", "iv_infusion", "iv_bolus"], nd=4, two_forms=True, overlap=True)),
]


def r4(v):
    return float(f"{v:.4g}")


def rt(v, q=0.05):
    return round(round(v / q) * q, 6)


def U(rng, lo, hi):
    return float(rng.uniform(lo, hi))


def LU(rng, lo, hi):
    return float(math.exp(rng.uniform(math.log(lo), math.log(hi))))


def dose(rng, route, t, key, forms, dur_hint=None):
    d = {key: t, "route": route, "amount": r4(LU(rng, 20, 2000)), "duration": None, "formulation": None}
    if route == "iv_infusion":
        d["duration"] = rt(dur_hint if dur_hint else LU(rng, 0.25, 6), 0.05)
        d["duration"] = min(24.0, max(0.1, d["duration"]))
    if route == "oral":
        d["formulation"] = int(rng.choice([f["id"] for f in forms]))
    return d


def build(rng, st):
    V1 = r4(LU(rng, 5, 80))
    CL = r4(LU(rng, 0.3, 20))
    if st.get("slow"):
        CL = r4(LU(rng, 0.15, 0.6))
        V1 = r4(LU(rng, 30, 100))
    if st.get("fast"):
        CL = r4(LU(rng, 10, 40))
        V1 = r4(LU(rng, 5, 20))
    per = []
    for k in range(st["cpt"] - 1):
        per.append(dict(Q=r4(LU(rng, 0.5, 40)), V=r4(LU(rng, 5, 300))))
    mm = st["mm"]
    Vmax, Km = 0.0, r4(LU(rng, 0.2, 20))
    if mm:
        Vmax = r4(LU(rng, 2, 200))
        if st.get("strong_mm"):
            CL = r4(LU(rng, 0.1, 0.5))
            Vmax = r4(LU(rng, 20, 200))
    nf = 2 if st.get("two_forms") else 1
    forms = []
    for i in range(nf):
        f = dict(id=i + 1, F=r4(U(rng, 0.3, 1.0)), ka=r4(LU(rng, 0.2, 3)), tlag=0.0, n_transit=0, ktr=r4(LU(rng, 1, 8)))
        if st.get("lag") or st.get("lagwrap") or (nf == 2 and i == 1):
            f["tlag"] = rt(U(rng, 0.25, 2.0), 0.05)
        if st.get("transit") or (nf == 2 and i == 0):
            f["n_transit"] = int(rng.randint(1, 6))
        forms.append(f)
    period = float(rng.choice([6.0, 8.0, 12.0, 12.0, 24.0, 24.0, 48.0, 168.0] if not st.get("multi_window") else [12.0, 24.0]))
    if st.get("wrap"):
        period = float(rng.choice([8.0, 12.0, 24.0]))
    nd = st["nd"]
    routes = st["routes"]
    maint_routes = [r for r in routes if r != "iv_infusion_load"] or ["iv_bolus"]
    if st.get("unequal"):
        offs = sorted(set(rt(U(rng, 0, period * 0.999), 0.25) for _ in range(nd)))
    else:
        offs = [rt(period * k / nd, 0.25) for k in range(nd)]
    offs = [o for o in offs if o < period]
    if not offs:
        offs = [0.0]
    doses = []
    for i, o in enumerate(offs):
        route = maint_routes[i % len(maint_routes)]
        hint = None
        if route == "iv_infusion":
            if st.get("wrap"):
                hint = period * U(rng, 1.1, 1.8)
            elif st.get("overlap"):
                hint = period / len(offs) * U(rng, 1.2, 2.5)
        doses.append(dose(rng, route, o, "offset", forms, hint))
    if st.get("lagwrap"):
        doses[-1]["route"] = "oral"
        doses[-1]["formulation"] = forms[-1]["id"]
        doses[-1]["duration"] = None
        doses[-1]["offset"] = rt(period - 0.5 * forms[-1]["tlag"], 0.05)
        if forms[-1]["tlag"] == 0.0:
            forms[-1]["tlag"] = 1.0
            doses[-1]["offset"] = rt(period - 0.5, 0.05)
    start = 0.0
    loading = []
    nl = st.get("loading", 1 if "iv_infusion_load" in routes else 0)
    if nl:
        if st.get("gap"):
            start = rt(U(rng, 6, 48), 0.5)
        else:
            start = rt(U(rng, 1, 12), 0.5)
        for i in range(nl):
            t = rt(U(rng, 0, start * 0.6), 0.25)
            route = "iv_infusion" if ("iv_infusion_load" in routes or rng.rand() < 0.5) else str(rng.choice(["iv_bolus", "oral"]))
            d = dose(rng, route, t, "time", forms, min(max(0.1, start - t), 24.0) * U(rng, 0.3, 0.95) if route == "iv_infusion" else None)
            if route == "iv_infusion" and t + d["duration"] > start:
                d["duration"] = rt(max(0.1, start - t), 0.05)
                if t + d["duration"] > start:
                    d["duration"] = 0.1
                    d["time"] = rt(start - 0.1, 0.05)
            d["amount"] = r4(d["amount"] * U(rng, 1.5, 3))
            loading.append(d)
        loading.sort(key=lambda x: x["time"])
    n_show = int(rng.randint(2, 6))
    horizon = min(360.0, rt(start + n_show * period + U(rng, 0, period), 0.5))
    horizon = max(horizon, start + period)
    nq = int(rng.randint(3, 11))
    qts = sorted(set(rt(U(rng, 0.0, horizon), 0.05) for _ in range(nq)))
    while len(qts) < 3:
        qts.append(rt(U(rng, 0.0, horizon), 0.05))
    reg = dict(regimen_id="tmp", model=dict(V1=V1, CL=CL, Vmax=Vmax, Km=Km, peripheral=per), formulations=forms,
               loading_doses=loading, maintenance=dict(start=start, period=period, doses=doses), horizon=horizon,
               query_times=sorted(qts), window=dict(low=1.0, high=2.0))
    return reg


def tune_dip(reg, rng):
    """Scale the first loading dose so that the trough of cycle 1 lands inside the 1 % band around the
    steady-state trough while the peripheral compartment is still filling: later troughs then leave the
    band and re-enter it, so n_cycles_to_steady is not the first cycle inside the band. Linear model."""
    ld = reg["loading_doses"][0]
    if ld["route"] == "oral":
        ld["route"], ld["formulation"] = "iv_bolus", None
    if ld["route"] == "iv_infusion" and ld["time"] + ld["duration"] > reg["maintenance"]["start"]:
        return False
    vals = []
    for a in (100.0, 1000.0):
        ld["amount"] = a
        rep, aux = rg.solve(reg)
        vals.append(aux["troughs"][0])
    tr = rep["steady_state"]["trough"]
    slope = (vals[1] - vals[0]) / 900.0
    if slope <= 0:
        return False
    target = tr * (1 + U(rng, -0.006, 0.006))
    a = 100.0 + (target - vals[0]) / slope
    if not 1 <= a <= 5000:
        return False
    ld["amount"] = r4(a)
    return True


def bolus_times(reg):
    out = [d["time"] for d in reg["loading_doses"] if d["route"] == "iv_bolus"]
    st, P = reg["maintenance"]["start"], reg["maintenance"]["period"]
    for m in range(0, 70):
        for d in reg["maintenance"]["doses"]:
            if d["route"] == "iv_bolus":
                out.append(st + m * P + d["offset"])
    return out


def choose_window(rng, ptr, st, model):
    """Window from the steady-state curve: low and high strictly between cmin and cmax."""
    P = ptr.t1
    ts = np.linspace(0, P, 2001)[:-1]
    Cs = np.array([ptr.C(float(t)) for t in ts])
    lo, hi = float(Cs.min()), float(Cs.max())
    if st.get("multi_window"):
        qa, qb = U(rng, 0.35, 0.55), U(rng, 0.6, 0.85)
    else:
        qa, qb = U(rng, 0.1, 0.45), U(rng, 0.55, 0.95)
    low = lo + qa * (hi - lo)
    high = lo + qb * (hi - lo)
    return r4(low), r4(high)


def screen(reg, rep, aux, log):
    """Return list of guarantee violations."""
    bad = []
    bt = bolus_times(reg)
    for t in reg["query_times"] + [reg["horizon"]]:
        if any(abs(t - b) < 1e-3 for b in bt):
            bad.append(f"g1 query/horizon {t} at bolus")
    cmax, tcm = rep["cmax"], rep["t_cmax"]
    others = [(t, v, k) for t, v, k in aux["maxima"] if abs(t - tcm) > 1e-9]
    if any(v > (1 - 1e-4) * cmax for t, v, k in others):
        bad.append("g2 cmax not isolated: " + str([(round(t, 3), v / cmax) for t, v, k in others if v > (1 - 1e-4) * cmax][:3]))
    kind = [k for t, v, k in aux["maxima"] if abs(t - tcm) <= 1e-9]
    if "interior" in kind:
        x, rate = aux["traj"].state(tcm)
        d2 = aux["model"].d2C(x, rate)
        if abs(d2) < 1e-2 * cmax:
            bad.append(f"g2 flat max d2C {d2:.3g} vs {1e-2 * cmax:.3g}")
    ss = rep["steady_state"]
    low, high = reg["window"]["low"], reg["window"]["high"]
    ptr = aux["ptr"]
    for lv in (low, high):
        if abs(lv - ss["cmin"]) < 1e-3 * ss["cmin"] or abs(lv - ss["cmax"]) < 1e-3 * ss["cmax"]:
            bad.append("g3 level near extremum")
        cont, jumps = ptr.crossings(lv)
        for t, dC in cont:
            if abs(dC) < 1e-3 * ss["cmax"]:
                bad.append(f"g3 tangential crossing at {t:.3f} dC {dC:.3g}")
        for t, xpre, xpost in ptr.jumps:
            cpre, cpost = xpre[0] / aux["model"].V1, xpost[0] / aux["model"].V1
            if abs(cpre - lv) < 1e-3 * lv or abs(cpost - lv) < 1e-3 * lv:
                bad.append("g3 bolus value near level")
    tr = ss["trough"]
    for m_, v in enumerate(aux["troughs"], start=1):
        if abs(abs(v - tr) - 0.01 * tr) < 1e-4 * tr:
            bad.append(f"g4 trough margin at cycle {m_}")
    # L1 certification within 60 cycles (the oracle stops at the certifying cycle)
    P = reg["maintenance"]["period"]
    if aux["certified_at"] is None:
        bad.append("g4 not certified within 60 cycles")
    if ss["n_cycles_to_steady"] > 50:
        bad.append("g4 n_cycles above 50")
    if ss["cmin"] <= 0 or cmax < 1e-3:
        bad.append("g5 positivity")
    # window informative: crossing count
    ncross = sum(len(ptr.crossings(lv)[0]) + len(ptr.crossings(lv)[1]) for lv in (low, high))
    log["crossings"] = ncross
    if ncross == 0:
        bad.append("window never crossed")
    if not (0 < ss["time_in_window"] < P):
        bad.append("time_in_window degenerate")
    return bad


def main():
    idx = [int(v) for v in sys.argv[3:]] or list(range(len(PLAN)))
    summary = {}
    for i in idx:
        name, st = PLAN[i]
        for attempt in range(40):
            rng = np.random.RandomState(1000 + 37 * i + attempt)
            reg = build(rng, st)
            reg["regimen_id"] = name
            try:
                tv.validate_regimen(reg, name)
            except AssertionError as e:
                if DEBUG:
                    print(name, attempt, "domain:", e)
                continue
            t0 = time.time()
            try:
                if st.get("dip") and not tune_dip(reg, rng):
                    if DEBUG:
                        print(name, attempt, "dip tuning failed")
                    continue
                rep, aux = rg.solve(reg)
                low, high = choose_window(rng, aux["ptr"], st, aux["model"])
                reg["window"] = dict(low=low, high=high)
                rep, aux = rg.solve(reg)
            except Exception as e:  # noqa
                if DEBUG:
                    print(name, attempt, "oracle error:", repr(e))
                continue
            dt = time.time() - t0
            log = {}
            bad = screen(reg, rep, aux, log)
            if dt > 60:
                bad.append(f"slow {dt:.1f}s")
            if st.get("dip"):
                tr = rep["steady_state"]["trough"]
                first_in = next((m for m, v in enumerate(aux["troughs"], start=1) if abs(v - tr) <= 0.01 * tr), 60)
                if first_in >= rep["steady_state"]["n_cycles_to_steady"]:
                    bad.append(f"dip: first_in {first_in} n_cycles {rep['steady_state']['n_cycles_to_steady']}")
            if bad:
                if DEBUG:
                    print(name, attempt, bad[:3])
                continue
            (OUT / "regimens" / f"{name}.json").write_text(json.dumps(reg, indent=1) + "\n")
            (OUT / "expected" / f"{name}.json").write_text(json.dumps(rep, indent=1) + "\n")
            summary[name] = dict(attempt=attempt, seconds=round(dt / 2, 1), n_cycles=rep["steady_state"]["n_cycles_to_steady"],
                                 cmax_kind=[k for t, v, k in aux["maxima"] if abs(t - rep["t_cmax"]) <= 1e-9], crossings=log["crossings"],
                                 dim=aux["model"].n, t_cmax=rep["t_cmax"])
            print(name, summary[name], flush=True)
            break
        else:
            print(name, "FAILED to generate", flush=True)
    (OUT / "log" / f"summary_{idx[0]}_{idx[-1]}.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
