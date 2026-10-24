"""Generate the graded systems and screen them with the oracle for every guarantee of
LAMBERT_SPEC.md section 2. One random stream per slot.

usage: gen_systems.py <lambert.py> <out_dir> [indices...]
"""
import importlib.util
import json
import math
import os
from fractions import Fraction
import sys
import time
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("lb", sys.argv[1])
lb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lb)
OUT = Path(sys.argv[2])
(OUT / "systems").mkdir(parents=True, exist_ok=True)
(OUT / "log").mkdir(parents=True, exist_ok=True)
DEBUG = bool(os.environ.get("GEN_DEBUG"))
DAY = 86400.0
MUS = {"earth": 398600.4418, "sun": 1.32712440018e11, "mars": 42828.37, "jupiter": 1.26686534e8, "generic": None}


def r6(v):
    return float(f"{v:.6g}")


def U(rng, lo, hi):
    return float(rng.uniform(lo, hi))


def LU(rng, lo, hi):
    return float(math.exp(rng.uniform(math.log(lo), math.log(hi))))


SYS_EPOCH = [0.0]


def body(rng, name, mu, kind, a_range, style):
    if kind == "hyperbola":
        e = U(rng, 1.05, 4.0)
        a = -LU(rng, *a_range)
    elif kind == "circular":
        e, a = 0.0 if rng.rand() < 0.5 else U(rng, 0.0, 0.02), LU(rng, *a_range)
    elif kind == "eccentric":
        e, a = U(rng, 0.6, 0.95), LU(rng, *a_range)
    else:
        e, a = U(rng, 0.0, 0.6), LU(rng, *a_range)
    i = U(rng, 0, 180) if style == "retrograde" or rng.rand() < 0.15 else U(rng, 0, 60)
    if style == "coplanar":
        i = U(rng, 0, 3)
    P = 2 * math.pi * math.sqrt(abs(a) ** 3 / mu) / DAY
    return dict(name=name, t0_days=r6(SYS_EPOCH[0] + U(rng, -1, 1) * min(20.0, 50 * P)), a_km=r6(a), e=r6(e), i_deg=r6(i), Omega_deg=r6(U(rng, 0, 360)),
                omega_deg=r6(U(rng, 0, 360)), M0_deg=r6(U(rng, 0, 360)))


def period_days(mu, a):
    return 2 * math.pi * math.sqrt(a ** 3 / mu) / DAY if a > 0 else None


def build(rng, style):
    mu_name = str(rng.choice(["earth", "sun", "mars", "jupiter", "generic"]))
    mu = MUS[mu_name] or LU(rng, 1e4, 2e11)
    if mu_name == "sun":
        a_range = (5e7, 1e9)
    elif mu_name == "generic":
        a_range = (1e4 * (mu / 1e4) ** 0.3, min(1e9, 1e5 * (mu / 1e4) ** 0.45))
    else:
        a_range = (1e4 if mu > 1e5 else 2e3 * 5, min(1e9, 3e5 * (mu / 398600) ** 0.33))
    a_range = (max(1e4, a_range[0]), max(2e4, min(1e9, a_range[1])))
    SYS_EPOCH[0] = U(rng, -1e4, 1e4)
    n_obj = int(rng.randint(2, 7))
    kinds = []
    for k in range(n_obj):
        if style == "hyperbolic" and k == n_obj - 1:
            kinds.append("hyperbola")
        elif style in ("eccentric", "far_epoch"):
            kinds.append("eccentric" if rng.rand() < 0.6 else "moderate")
        elif style == "circular":
            kinds.append("circular")
        else:
            kinds.append(str(rng.choice(["circular", "moderate", "moderate", "eccentric", "hyperbola"], p=[0.25, 0.3, 0.2, 0.15, 0.1])))
    objs = [body(rng, f"obj{k + 1}", mu, kinds[k], a_range, style) for k in range(n_obj)]
    for o in objs:
        rp = o["a_km"] * (1 - o["e"]) if o["a_km"] > 0 else -o["a_km"] * (o["e"] - 1)
        if rp < 1e3:
            return None
    return mu, objs


def choose_queries(rng, mu, objs, style):
    names = [o["name"] for o in objs]
    by = {o["name"]: o for o in objs}

    def time_near(o, span=None):
        if o["a_km"] > 0:
            P = period_days(mu, o["a_km"])
            lim = min(2000 * P, 2e4 - abs(o["t0_days"]))
            if style == "far_epoch":
                return r6(o["t0_days"] + U(rng, -1, 1) * min(lim, 1500 * P))
            return r6(o["t0_days"] + U(rng, -1, 1) * min(lim, (span or 30) * P))
        n = math.sqrt(mu / abs(o["a_km"]) ** 3)
        Mmax = 50.0
        return r6(o["t0_days"] + U(rng, -1, 1) * min(Mmax / n / DAY, 2e4 - abs(o["t0_days"])))
    eph = [dict(object=str(rng.choice(names)), t_days=time_near(by[str(rng.choice(names))])) for _ in range(int(rng.randint(2, 9)))]
    eph = [dict(object=q["object"], t_days=time_near(by[q["object"]])) for q in eph]
    trans = []
    for _ in range(int(rng.randint(2, 7))):
        a_name, b_name = [str(x) for x in rng.choice(names, size=2, replace=False)]
        A, B = by[a_name], by[b_name]
        t1 = r6(SYS_EPOCH[0] + U(rng, -1, 1) * min(20.0, 30 * min(period_days(mu, abs(A["a_km"])), period_days(mu, abs(B["a_km"])))))
        # time of flight scaled to the orbits
        ref = max(abs(A["a_km"]), abs(B["a_km"]))
        P = 2 * math.pi * math.sqrt(ref ** 3 / mu) / DAY
        if style == "long_flight":
            tof = P * U(rng, 2.0, 5.0)
        elif style == "short_flight":
            tof = P * U(rng, 0.02, 0.2)
        else:
            tof = P * LU(rng, 0.1, 3.0)
        tof = max(0.1, min(6000.0, tof))
        n_max = int(rng.randint(0, 5))
        if style == "many_revs":
            n_max, tof = 4, min(6000.0, P * U(rng, 3.5, 5.0))
        if style == "zero_rev":
            n_max = 0
        t2 = r6(t1 + tof)
        if not -2e4 <= t2 <= 2e4 or not 0.1 <= t2 - t1 <= 6000:
            continue
        trans.append({"from": a_name, "t1_days": t1, "to": b_name, "t2_days": t2, "n_max": n_max})
    return eph, trans[:6]


import importlib
sys.modules["pytest"] = importlib.import_module("pytest")
_tv_spec = importlib.util.spec_from_file_location("tv", Path(sys.argv[1]).resolve().parents[1] / "tests/test_outputs.py")
tv = importlib.util.module_from_spec(_tv_spec)
_tv_spec.loader.exec_module(tv)


def time_ok(o, mu, t):
    dt = float((Fraction(t) - Fraction(o["t0_days"])) * 86400)
    if o["a_km"] > 0:
        return abs(dt) <= 2000 * 2 * math.pi * math.sqrt(o["a_km"] ** 3 / mu)
    n = math.sqrt(mu / abs(o["a_km"]) ** 3)
    return abs(math.radians(o["M0_deg"]) + n * dt) <= 50


def screen(m, want):
    try:
        tv.validate_system(m, m["system_id"])
    except AssertionError as error:
        return False, f"domain: {error}", None
    mu_ = m["mu_km3_s2"]
    by = {o["name"]: o for o in m["objects"]}
    for q in m["ephemeris_queries"]:
        if not time_ok(by[q["object"]], mu_, q["t_days"]):
            return False, "guarantee 3 (ephemeris)", None
    for q in m["transfer_queries"]:
        if not (time_ok(by[q["from"]], mu_, q["t1_days"]) and time_ok(by[q["to"]], mu_, q["t2_days"])):
            return False, "guarantee 3 (transfer)", None
    t0 = time.time()
    rep = lb.solve(m)
    secs = time.time() - t0
    if secs > 10:
        return False, "slow", rep
    mu = m["mu_km3_s2"]
    bodies = {o["name"]: lb.Body(o, mu) for o in m["objects"]}
    for q, t in zip(m["transfer_queries"], rep["transfers"]):
        th = t["theta_deg"]
        if not (1 <= th <= 179 or 181 <= th <= 359):
            return False, "theta near 0/180", rep
        rA, _ = bodies[q["from"]].state(q["t1_days"])
        rB, _ = bodies[q["to"]].state(q["t2_days"])
        hh = np.cross(rA, rB)
        if abs(hh[2]) < 1e-3 * np.linalg.norm(hh):
            return False, "plane side in doubt", rep
        if np.linalg.norm(rA) < 1e3 or np.linalg.norm(rB) < 1e3:
            return False, "radius", rep
        tof = q["t2_days"] - q["t1_days"]
        if any(abs(tof - tm) < 1e-6 * tm for tm in t["t_min_days"]):
            return False, "tof at t_min", rep
        dvs = sorted(s["dv_km_s"] for s in t["solutions"])
        if len(dvs) > 1 and (dvs[1] - dvs[0]) < 1e-6 * dvs[0]:
            return False, "best not unique", rep
        for N in range(1, q["n_max"] + 1):
            pair = [s for s in t["solutions"] if s["N"] == N]
            if len(pair) == 2 and abs(pair[0]["a_km"] - pair[1]["a_km"]) < 1e-6 * abs(pair[1]["a_km"]):
                return False, "branches not distinct", rep
        if not all(math.isfinite(x) for s in t["solutions"] for x in s["v1_km_s"] + s["v2_km_s"] + [s["a_km"], s["e"], s["dv_km_s"]]):
            return False, "non-finite", rep
        # guarantee 5: no degenerate transfer arcs
        for s in t["solutions"]:
            a_, e_ = s["a_km"], s["e"]
            rp = a_ * (1 - e_) if a_ > 0 else -a_ * (e_ - 1)
            sp = max(float(np.linalg.norm(s["v1_km_s"])), float(np.linalg.norm(s["v2_km_s"])))
            if rp < 1e3 or not 1e-3 <= e_ <= 20 or sp > 200 or s["dv_km_s"] < 1e-3 * sp:
                return False, "degenerate arc", rep
        # re-propagation check of every solution
        for s in t["solutions"]:
            v1 = np.array(s["v1_km_s"])
            R = np.linalg.norm(rA)
            a = 1 / (2 / R - float(np.dot(v1, v1)) / mu)
            if abs(a - s["a_km"]) > 1e-9 * abs(a):
                return False, "a mismatch", rep
    try:
        tv.validate_report(rep, m, m["system_id"])
    except AssertionError as error:
        return False, f"report: {error}", rep
    return True, "ok", rep


def predicate(want, m, rep):
    counts = [len(t["solutions"]) for t in rep["transfers"]]
    thetas = [t["theta_deg"] for t in rep["transfers"]]
    if "min_count" in want and max(counts) < want["min_count"]: return False
    if want.get("hyperbolic_object") and not any(o["a_km"] < 0 for o in m["objects"]): return False
    if want.get("hyperbolic_arc") and not any(s["a_km"] < 0 for t in rep["transfers"] for s in t["solutions"]): return False
    if want.get("long_way") and not any(th > 181 for th in thetas): return False
    if want.get("short_way") and not any(th < 179 for th in thetas): return False
    if want.get("best_multirev") and not any(t["solutions"][t["best"]]["N"] >= 1 for t in rep["transfers"]): return False
    if want.get("best_high") and not any(t["solutions"][t["best"]]["branch"] == "high" for t in rep["transfers"]): return False
    if want.get("retrograde") and not any(o["i_deg"] > 90 for o in m["objects"]): return False
    if want.get("eccentric") and not any(0 < o["a_km"] and o["e"] >= 0.8 for o in m["objects"]): return False
    if want.get("far_epoch"):
        ok = False
        for q in m["ephemeris_queries"]:
            o = next(x for x in m["objects"] if x["name"] == q["object"])
            if o["a_km"] > 0 and abs(q["t_days"] - o["t0_days"]) > 500 * period_days(m["mu_km3_s2"], o["a_km"]):
                ok = True
        if not ok: return False
    if want.get("zero_only") and any(q["n_max"] > 0 for q in m["transfer_queries"]): return False
    if want.get("empty_family") and not any(q["n_max"] >= 1 and len(t["solutions"]) == 1 for q, t in zip(m["transfer_queries"], rep["transfers"])): return False
    if "counts" in want and not set(want["counts"]) <= set(counts): return False
    if want.get("sun") and m["mu_km3_s2"] < 1e11: return False
    return True


PLAN = [
    ("model_01", True, "circular", dict(min_count=3), "near-circular orbits, a multi-revolution family (base case)"),
    ("model_02", True, "hyperbolic", dict(hyperbolic_object=True), "a hyperbolic object"),
    ("model_03", True, "mixed", dict(long_way=True, min_count=3), "transfer through more than 180 degrees"),
    ("model_04", True, "many_revs", dict(min_count=7), "seven or more solutions in one query"),
    ("model_05", True, "far_epoch", dict(eccentric=True, far_epoch=True), "eccentric orbits, epochs hundreds of periods away"),
    ("model_06", True, "mixed", dict(best_multirev=True), "best solution on a multi-revolution branch"),
    ("held_01", False, "circular", dict(zero_only=True), "zero-revolution queries only"),
    ("held_02", False, "hyperbolic", dict(hyperbolic_object=True, hyperbolic_arc=True), "hyperbolic object and hyperbolic arc"),
    ("held_03", False, "short_flight", dict(hyperbolic_arc=True), "short flights: hyperbolic transfer arcs"),
    ("held_04", False, "long_flight", dict(min_count=5), "long flights, five or more solutions"),
    ("held_05", False, "many_revs", dict(counts=[9]), "nine solutions"),
    ("held_06", False, "mixed", dict(empty_family=True), "n_max above 0 with an empty family"),
    ("held_07", False, "retrograde", dict(retrograde=True), "retrograde object orbits"),
    ("held_08", False, "eccentric", dict(eccentric=True), "highly eccentric orbits"),
    ("held_09", False, "far_epoch", dict(far_epoch=True), "epochs thousands of periods away"),
    ("held_10", False, "mixed", dict(long_way=True, best_multirev=True), "long way and multi-revolution best"),
    ("held_11", False, "mixed", dict(best_high=True), "best solution on a high branch"),
    ("held_12", False, "mixed", dict(sun=True), "heliocentric system"),
    ("held_13", False, "coplanar", dict(min_count=3), "coplanar orbits"),
    ("held_14", False, "mixed", dict(counts=[1, 3, 5]), "counts 1, 3 and 5 in one system"),
    ("held_15", False, "hyperbolic", dict(hyperbolic_object=True, long_way=True), "hyperbolic object, long way"),
    ("held_16", False, "many_revs", dict(counts=[7]), "seven solutions"),
    ("held_17", False, "circular", dict(min_count=5), "near-circular, five solutions"),
    ("held_18", False, "eccentric", dict(min_count=3, long_way=True), "eccentric orbits, long way"),
    ("held_19", False, "far_epoch", dict(far_epoch=True, min_count=3), "far epochs with multi-revolution transfers"),
    ("held_20", False, "short_flight", dict(short_way=True), "short flights"),
    ("held_21", False, "long_flight", dict(best_multirev=True), "long flights with multi-revolution best"),
    ("held_22", False, "mixed", dict(min_count=3, hyperbolic_object=True), "mixed system with a hyperbolic object"),
]


def build_slot(index):
    sid, shipped, style, want, label = PLAN[index]
    rng = np.random.RandomState(20261024 + 7919 * index)
    t0 = time.time()
    for attempt in range(3000):
        if time.time() - t0 > 1200:
            break
        try:
            built = build(rng, style)
            if built is None:
                continue
            mu, objs = built
            eph, trans = choose_queries(rng, mu, objs, style)
            if len(eph) < 2 or len(trans) < 2:
                continue
            m = dict(system_id=sid, mu_km3_s2=r6(mu), objects=objs, ephemeris_queries=eph, transfer_queries=trans)
            ok, why, rep = screen(m, want)
            if not ok:
                if DEBUG and why.startswith("domain"):
                    print("  reject", why[:120], flush=True)
                if DEBUG:
                    print("  reject", why, flush=True)
                continue
            if not predicate(want, m, rep):
                if DEBUG:
                    print("  reject predicate", [len(t["solutions"]) for t in rep["transfers"]], flush=True)
                continue
        except Exception as error:
            if DEBUG:
                print("  reject error", repr(error)[:200], flush=True)
            continue
        json.dump(m, open(OUT / "systems" / f"{sid}.json", "w"), indent=1)
        log = dict(system_id=sid, shipped=shipped, style=style, label=label, attempts=attempt + 1, mu=m["mu_km3_s2"],
                   objects=len(objs), counts=[len(t["solutions"]) for t in rep["transfers"]],
                   thetas=[round(t["theta_deg"], 2) for t in rep["transfers"]])
        json.dump(log, open(OUT / "log" / f"{sid}.json", "w"), indent=1)
        print(json.dumps(log), flush=True)
        return
    print(json.dumps(dict(system_id=sid, failed=True, label=label)), flush=True)


if __name__ == "__main__":
    idx = [int(v) for v in sys.argv[3:]] or list(range(len(PLAN)))
    for i in idx:
        build_slot(i)
