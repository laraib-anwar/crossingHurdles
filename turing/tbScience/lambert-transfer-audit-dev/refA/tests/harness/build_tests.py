"""Construct refA test systems (validation only)."""
import json, math, sys
import numpy as np
from decimal import Decimal
sys.path.insert(0, '.')
from guarantees import load_ref, check

REFDIR = sys.argv[1]
OUT = sys.argv[2]
ref = load_ref(REFDIR)
DAY = 86400
THMARGIN = 0.5


def transfer(sysd, fr, t1, to, t2, n_max):
    mu = sysd["mu_km3_s2"]
    objs = {o["name"]: ref.Body(o, mu) for o in sysd["objects"]}
    r1, vA = objs[fr].state(t1); r2, vB = objs[to].state(t2)
    T = float((Decimal(t2) - Decimal(t1)) * DAY)
    lam, tmin, sols, best = ref.solve_transfer(r1, vA, r2, vB, T, mu, n_max)
    return lam, tmin, sols, best


def ok_query(sysd, fr, t1, to, t2, n_max):
    """Per-query guarantees 1, 2, 5."""
    lam, tmin, sols, best = transfer(sysd, fr, t1, to, t2, n_max)
    th = math.degrees(lam.theta)
    T = t2 - t1
    m = THMARGIN
    if not (1.0 + m <= th <= 179.0 - m or 181.0 + m <= th <= 359.0 - m):
        return None
    if any(abs(T - tm) < 1e-3 * tm for tm in tmin):
        return None
    dvs = sorted(s["dv_km_s"] for s in sols)
    if len(dvs) > 1 and dvs[1] - dvs[0] < 1e-4 * dvs[0]:
        return None
    for N in range(1, n_max + 1):
        ss = [s for s in sols if s["N"] == N]
        if ss and ss[1]["a_km"] - ss[0]["a_km"] < 1e-4 * ss[1]["a_km"]:
            return None
    for s in sols:
        a, e = s["a_km"], s["e"]
        rp = a * (1 - e) if a > 0 else -a * (e - 1)
        v1 = np.linalg.norm(s["v1_km_s"]); v2 = np.linalg.norm(s["v2_km_s"])
        if rp < 1e3 or not (1e-3 <= e <= 20) or max(v1, v2) > 200 or s["dv_km_s"] < 1e-3 * max(v1, v2):
            return None
    return lam, tmin, sols, best


def search(sysd, fr, t1, to, n_max, pred, Ts):
    for T in Ts:
        t2 = round(t1 + T, 6)
        r = ok_query(sysd, fr, t1, to, t2, n_max)
        if r is not None and pred(*r):
            return {"from": fr, "t1_days": t1, "to": to, "t2_days": t2, "n_max": n_max}
    raise RuntimeError("no T found for %s->%s" % (fr, to))


def search_t1(sysd, fr, t1s, to, n_max, pred, Ts):
    for t1 in t1s:
        try:
            return search(sysd, fr, t1, to, n_max, pred, Ts)
        except RuntimeError:
            pass
    raise RuntimeError("no t1 found for %s->%s" % (fr, to))


def is_hyp0(lam, tmin, sols, best, Asign):
    return sols[0]["a_km"] < 0 and (lam.A > 0) == (Asign > 0)


def summary(sysd):
    bad, rep = check(sysd, ref)
    print("==", sysd["system_id"], "in-domain" if not bad else bad)
    for t in rep["transfers"]:
        print("  %s->%s T=%.4f th=%.3f nsol=%d best=%d(N=%d %s) tmin=%s hyp0=%s" % (
            t["from"], t["to"], t["t2_days"] - t["t1_days"], t["theta_deg"], len(t["solutions"]), t["best"],
            t["solutions"][t["best"]]["N"], t["solutions"][t["best"]]["branch"],
            ["%.4f" % x for x in t["t_min_days"]], t["solutions"][0]["a_km"] < 0))
    return bad


def save(sysd):
    bad = summary(sysd)
    with open("%s/%s.json" % (OUT, sysd["system_id"]), "w") as fh:
        json.dump(sysd, fh, indent=1)
        fh.write("\n")
    return bad


geo = lambda T0, T1, n: list(np.geomspace(T0, T1, n))

# ---------------------------------------------------------------- t1 Hohmann (textbook)
mu_e = 398600.4418
a_t = (7000.0 + 42164.0) / 2
TH = math.pi * math.sqrt(a_t ** 3 / mu_e) / DAY
t1h = {
    "system_id": "t1_hohmann_textbook",
    "mu_km3_s2": mu_e,
    "objects": [
        {"name": "LEO", "t0_days": 0.0, "a_km": 7000.0, "e": 0.0, "i_deg": 0.0, "Omega_deg": 0.0, "omega_deg": 0.0, "M0_deg": 0.0},
        # GEO placed so that it is diametrically opposite LEO's departure point at the Hohmann time
        {"name": "GEO", "t0_days": 0.0, "a_km": 42164.0, "e": 0.0, "i_deg": 0.0, "Omega_deg": 0.0, "omega_deg": 0.0,
         "M0_deg": (180.0 - math.degrees(math.sqrt(mu_e / 42164.0 ** 3) * TH * DAY)) % 360.0},
        # Vallado, Fundamentals of Astrodynamics, Example 7-5 (universal variables): r0 = (15945.34, 0, 0),
        # r = (12214.83899, 10249.46731, 0) km, dt = 76 min
        {"name": "V75a", "t0_days": 0.0, "a_km": 15945.34, "e": 0.0, "i_deg": 0.0, "Omega_deg": 0.0, "omega_deg": 0.0, "M0_deg": 0.0},
        {"name": "V75b", "t0_days": 0.0, "a_km": math.hypot(12214.83899, 10249.46731), "e": 0.0, "i_deg": 0.0,
         "Omega_deg": 0.0, "omega_deg": 0.0,
         "M0_deg": (math.degrees(math.atan2(10249.46731, 12214.83899))
                    - math.degrees(math.sqrt(mu_e / math.hypot(12214.83899, 10249.46731) ** 3) * 76 * 60)) % 360.0},
    ],
    "ephemeris_queries": [{"object": "LEO", "t_days": 0.0}, {"object": "GEO", "t_days": TH},
                          {"object": "V75b", "t_days": 76.0 / 1440.0}],
    "transfer_queries": [
        # 1e-8 day after the Hohmann time: theta = 180.0000036 deg (just outside guarantee 1, unavoidable)
        {"from": "LEO", "t1_days": 0.0, "to": "GEO", "t2_days": TH + 1e-8, "n_max": 0},
        {"from": "V75a", "t1_days": 0.0, "to": "V75b", "t2_days": 76.0 / 1440.0, "n_max": 0},
    ],
}
save(t1h)

# ---------------------------------------------------------------- t2 hyperbolic object (heliocentric)
mu_s = 132712440018.0
t2s = {
    "system_id": "t2_hyperbolic_object",
    "mu_km3_s2": mu_s,
    "objects": [
        {"name": "Terra", "t0_days": 0.0, "a_km": 149598023.0, "e": 0.0167086, "i_deg": 0.00005, "Omega_deg": 348.73936,
         "omega_deg": 114.20783, "M0_deg": 358.617},
        {"name": "Visitor", "t0_days": 37.25, "a_km": -127230000.0, "e": 1.20113, "i_deg": 122.74, "Omega_deg": 24.597,
         "omega_deg": 241.81, "M0_deg": 12.5},
        {"name": "Rubra", "t0_days": -11.5, "a_km": 227939200.0, "e": 0.0934, "i_deg": 1.85, "Omega_deg": 49.558,
         "omega_deg": 286.502, "M0_deg": 19.412},
    ],
    "ephemeris_queries": [{"object": "Visitor", "t_days": 37.25}, {"object": "Visitor", "t_days": -1500.75},
                          {"object": "Visitor", "t_days": 1712.5}, {"object": "Terra", "t_days": 413.125},
                          {"object": "Rubra", "t_days": -2222.0}],
    "transfer_queries": [],
}
tq = t2s["transfer_queries"]
tq.append(search(t2s, "Terra", 100.0, "Visitor", 1, lambda *r: True, geo(60, 400, 80)))
tq.append(search(t2s, "Visitor", 230.0, "Rubra", 0, lambda *r: True, geo(150, 900, 80)))
tq.append(search_t1(t2s, "Terra", [40.0 + 37.5 * k for k in range(30)], "Rubra", 0, lambda *r: is_hyp0(*r, +1), geo(0.5, 300, 200)))
tq.append(search_t1(t2s, "Rubra", [310.0 + 37.5 * k for k in range(30)], "Terra", 0, lambda *r: is_hyp0(*r, -1), geo(0.5, 300, 200)))
save(t2s)

# ---------------------------------------------------------------- t3 five solutions (lunar-distance, geocentric)
t3s = {
    "system_id": "t3_five_solutions",
    "mu_km3_s2": mu_e,
    "objects": [
        {"name": "Tug", "t0_days": 2.375, "a_km": 26560.0, "e": 0.0102, "i_deg": 55.0, "Omega_deg": 121.4, "omega_deg": 33.7, "M0_deg": 201.9},
        {"name": "Depot", "t0_days": -4.5, "a_km": 41250.5, "e": 0.25, "i_deg": 61.2, "Omega_deg": 118.0, "omega_deg": 270.0, "M0_deg": 14.25},
        {"name": "Molniya", "t0_days": 0.0, "a_km": 26554.0, "e": 0.7222, "i_deg": 63.4, "Omega_deg": 300.0, "omega_deg": 270.0, "M0_deg": 0.0},
    ],
    "ephemeris_queries": [{"object": "Tug", "t_days": 3.0}, {"object": "Depot", "t_days": 7.75},
                          {"object": "Molniya", "t_days": 0.3}, {"object": "Molniya", "t_days": 995.0}],
    "transfer_queries": [],
}
tq = t3s["transfer_queries"]
five = lambda lam, tmin, sols, best: len(sols) == 5
tq.append(search(t3s, "Tug", 3.0, "Depot", 3, five, geo(0.1, 20, 600)))
tq.append(search(t3s, "Depot", 10.0, "Molniya", 4, five, geo(0.1, 20, 600)))
tq.append(search(t3s, "Molniya", 20.25, "Tug", 2, five, geo(0.1, 20, 600)))
save(t3s)

# ---------------------------------------------------------------- t4 theta > 180 with multi-rev, 9 solutions
t4s = {
    "system_id": "t4_theta_above_180",
    "mu_km3_s2": 4902.800066 * 1e1 * 2.5,     # 122570.0016: a fictitious central body inside the mu domain
    "objects": [
        {"name": "Lo", "t0_days": 0.0, "a_km": 12000.0, "e": 0.05, "i_deg": 10.0, "Omega_deg": 20.0, "omega_deg": 30.0, "M0_deg": 40.0},
        {"name": "Hi", "t0_days": 1.5, "a_km": 21000.0, "e": 0.3, "i_deg": 15.0, "Omega_deg": 80.0, "omega_deg": 100.0, "M0_deg": 310.0},
        {"name": "Retro", "t0_days": -3.0, "a_km": 18000.0, "e": 0.12, "i_deg": 170.0, "Omega_deg": 5.0, "omega_deg": 45.0, "M0_deg": 90.0},
    ],
    "ephemeris_queries": [{"object": "Lo", "t_days": 0.25}, {"object": "Retro", "t_days": 2.0}],
    "transfer_queries": [],
}
tq = t4s["transfer_queries"]
nine_gt180 = lambda lam, tmin, sols, best: len(sols) == 9 and lam.theta > math.pi
gt180_multi = lambda lam, tmin, sols, best: len(sols) >= 3 and lam.theta > math.pi
tq.append(search(t4s, "Lo", 0.5, "Hi", 4, nine_gt180, geo(0.1, 60, 2000)))
for t1 in (2.0, 2.3, 2.6, 2.9, 3.2, 3.5, 3.8):
    try:
        tq.append(search(t4s, "Hi", t1, "Retro", 2, gt180_multi, geo(0.1, 60, 1500)))
        break
    except RuntimeError:
        pass
tq.append(search(t4s, "Retro", 5.0, "Lo", 1, lambda lam, tmin, sols, best: lam.theta > math.pi and len(sols) == 1, geo(0.1, 60, 1500)))
save(t4s)

# ---------------------------------------------------------------- t5 best on a multi-revolution branch
t5s = {
    "system_id": "t5_best_multirev",
    "mu_km3_s2": 37931187.0,                    # Saturn-like
    "objects": [
        {"name": "Moon1", "t0_days": 0.0, "a_km": 185539.0, "e": 0.0196, "i_deg": 1.57, "Omega_deg": 173.0, "omega_deg": 14.0, "M0_deg": 3.0},
        {"name": "Moon2", "t0_days": 0.0, "a_km": 238042.0, "e": 0.0047, "i_deg": 0.009, "Omega_deg": 342.0, "omega_deg": 211.0, "M0_deg": 59.4},
        {"name": "Moon3", "t0_days": 0.0, "a_km": 294672.0, "e": 0.0001, "i_deg": 1.09, "Omega_deg": 260.0, "omega_deg": 104.0, "M0_deg": 177.3},
    ],
    "ephemeris_queries": [{"object": "Moon2", "t_days": 5.5}, {"object": "Moon3", "t_days": -17.0}],
    "transfer_queries": [],
}
tq = t5s["transfer_queries"]
best_multi = lambda lam, tmin, sols, best: sols[best]["N"] >= 1
best_multi_high = lambda lam, tmin, sols, best: sols[best]["N"] >= 2
tq.append(search(t5s, "Moon1", 1.0, "Moon2", 3, best_multi_high, geo(0.5, 30, 1500)))
tq.append(search(t5s, "Moon2", 4.0, "Moon3", 2, best_multi, geo(0.5, 30, 1500)))
tq.append(search(t5s, "Moon3", 9.0, "Moon1", 4, best_multi, geo(0.5, 30, 1500)))
save(t5s)

# ---------------------------------------------------------------- t6 distant epochs, e = 0.95, retrograde
t6s = {
    "system_id": "t6_distant_epochs",
    "mu_km3_s2": 126686534.0,                    # Jupiter-like
    "objects": [
        {"name": "Ecc", "t0_days": -11500.0, "a_km": 1.0e6, "e": 0.95, "i_deg": 3.0, "Omega_deg": 12.0, "omega_deg": 250.0, "M0_deg": 359.9},
        {"name": "Circ", "t0_days": 6900.0, "a_km": 671100.0, "e": 0.0, "i_deg": 0.47, "Omega_deg": 0.0, "omega_deg": 0.0, "M0_deg": 0.0},
        {"name": "Back", "t0_days": 14000.0, "a_km": 1070400.0, "e": 0.0011, "i_deg": 179.0, "Omega_deg": 200.0, "omega_deg": 10.0, "M0_deg": 123.4},
        {"name": "Flyby", "t0_days": 300.0, "a_km": -2.0e6, "e": 3.5, "i_deg": 90.0, "Omega_deg": 0.0, "omega_deg": 0.0, "M0_deg": 0.0},
    ],
    "ephemeris_queries": [{"object": "Ecc", "t_days": 0.0}, {"object": "Ecc", "t_days": -11499.98},
                          {"object": "Circ", "t_days": -100.0}, {"object": "Back", "t_days": -150.0},
                          {"object": "Flyby", "t_days": 280.0}, {"object": "Flyby", "t_days": 330.0}],
    "transfer_queries": [],
}
tq = t6s["transfer_queries"]
tq.append(search(t6s, "Circ", 100.0, "Ecc", 4, lambda *r: len(r[2]) >= 5, geo(1, 400, 1500)))
tq.append(search(t6s, "Ecc", 200.0, "Back", 2, lambda *r: True, geo(1, 400, 600)))
tq.append(search(t6s, "Back", 299.0, "Flyby", 0, lambda *r: True, geo(0.2, 30, 600)))
save(t6s)

# ---------------------------------------------------------------- t7 edges: theta near 1/179/181/359 deg, mu = 1e4, long T
THMARGIN = 0.0
t7s = {
    "system_id": "t7_angle_edges",
    "mu_km3_s2": 10000.0,
    "objects": [
        {"name": "Inner", "t0_days": 0.0, "a_km": 10000.0, "e": 0.0, "i_deg": 0.0, "Omega_deg": 0.0, "omega_deg": 0.0, "M0_deg": 0.0},
        {"name": "Outer", "t0_days": 0.0, "a_km": 15500.0, "e": 0.08, "i_deg": 0.3, "Omega_deg": 75.0, "omega_deg": 15.0, "M0_deg": 180.0},
        {"name": "Near", "t0_days": 0.5, "a_km": 10400.0, "e": 0.012, "i_deg": 0.3, "Omega_deg": 33.0, "omega_deg": 44.0, "M0_deg": 55.0},
        {"name": "Far", "t0_days": 0.0, "a_km": 160000.0, "e": 0.6, "i_deg": 5.0, "Omega_deg": 300.0, "omega_deg": 60.0, "M0_deg": 10.0},
    ],
    "ephemeris_queries": [{"object": "Inner", "t_days": 1.0}, {"object": "Far", "t_days": 5999.0}],
    "transfer_queries": [],
}
tq = t7s["transfer_queries"]
win = lambda lo, hi, k: (lambda lam, tmin, sols, best: lo <= math.degrees(lam.theta) <= hi and len(sols) >= k)
fine = list(np.arange(0.1, 12.0, 0.0005))
tq.append(search(t7s, "Inner", 1.0, "Outer", 4, win(178.6, 179.0, 3), fine))
tq.append(search(t7s, "Inner", 2.0, "Outer", 4, win(181.0, 181.4, 3), fine))
# theta ~ 359 deg with T ~ one revolution: pick t1 so that theta(T = 0.75 d) ~ 358.8 deg
best_t1 = min((abs(math.degrees(transfer(t7s, "Near", t1, "Inner", t1 + 0.75, 0)[0].theta) - 358.8), t1)
              for t1 in np.round(np.arange(3.0, 16.0, 0.005), 3))[1]
tq.append(search(t7s, "Near", float(best_t1), "Inner", 0, win(358.6, 359.0, 1), list(np.arange(0.6, 0.9, 0.0001))))
tq.append(search(t7s, "Inner", 10.0, "Far", 4, lambda *r: len(r[2]) == 9, list(np.geomspace(1000, 5990, 4000))))
save(t7s)

# ---------------------------------------------------------------- t8 small transfer angle (fast hyperbolic arcs), mu = 2e11
t8s = {
    "system_id": "t8_small_angle_fast",
    "mu_km3_s2": 200000000000.0,
    "objects": [
        {"name": "FarA", "t0_days": 0.0, "a_km": 100000000.0, "e": 0.0, "i_deg": 0.3, "Omega_deg": 0.0, "omega_deg": 0.0, "M0_deg": 10.0},
        {"name": "FarB", "t0_days": 0.0, "a_km": 102000000.0, "e": 0.01, "i_deg": 0.2, "Omega_deg": 0.0, "omega_deg": 0.0, "M0_deg": 10.4},
        {"name": "Wide", "t0_days": 0.0, "a_km": 400000000.0, "e": 0.4, "i_deg": 7.0, "Omega_deg": 100.0, "omega_deg": 200.0, "M0_deg": 300.0},
    ],
    "ephemeris_queries": [{"object": "FarA", "t_days": -19999.5}, {"object": "Wide", "t_days": 19999.5}],
    "transfer_queries": [],
}
tq = t8s["transfer_queries"]
tq.append(search(t8s, "FarA", 0.5, "FarB", 2, win(1.0, 1.4, 1), list(np.arange(0.1, 3.0, 0.001))))
tq.append(search(t8s, "FarA", 0.6, "FarB", 4, win(1.0, 1.1, 1), list(np.arange(0.1, 3.0, 0.0005))))
tq.append(search(t8s, "FarA", 2.0, "Wide", 3, lambda *r: len(r[2]) >= 5, list(np.geomspace(50, 5990, 3000))))
save(t8s)
