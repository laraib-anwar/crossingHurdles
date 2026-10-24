#!/usr/bin/env python3
"""Write the two constructed test systems and their hand values (plain `math`, no refB code).

hohmann_like.json      two coplanar circular orbits (20000 km, 40000 km).  Transfer 0 departs
                       tangentially from periapsis of an ellipse built by hand to pass r = 40000 km
                       at true anomaly 170 deg, so its time of flight, dv and T_min bounds are
                       closed-form.
hyperbolic_long_way.json  a hyperbolic object queried at periapsis (closed-form state) and a
                       circular planet placed at 250 deg, so theta = 250 deg exactly.
"""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def hohmann_like():
    mu, R1, R2, th = 398600.0, 20000.0, 40000.0, math.radians(170.0)
    e = (R2 - R1) / (R1 - R2 * math.cos(th))          # tangential departure at periapsis through R2 at nu=170
    a = R1 / (1 - e)
    p = R1 * (1 + e)
    E = 2 * math.atan(math.sqrt((1 - e) / (1 + e)) * math.tan(th / 2))
    T = math.sqrt(a ** 3 / mu) * (E - e * math.sin(E))  # periapsis to nu = 170 deg
    t2 = T / 86400.0
    v1 = math.sqrt(mu * (1 + e) / R1)
    vr2 = math.sqrt(mu / p) * e * math.sin(th)
    vt2 = math.sqrt(mu / p) * (1 + e * math.cos(th))
    vc1, vc2 = math.sqrt(mu / R1), math.sqrt(mu / R2)
    dv = (v1 - vc1) + math.hypot(vr2, vt2 - vc2)
    # T_min(1) bounds: N P(a_m) < T_min(N) < T(alpha = pi) on the minimum-energy ellipse
    c = math.sqrt(R1 ** 2 + R2 ** 2 - 2 * R1 * R2 * math.cos(th))
    s = (R1 + R2 + c) / 2
    am = s / 2
    bm = 2 * math.asin(math.sqrt((s - c) / s))
    lower = 2 * math.pi * math.sqrt(am ** 3 / mu)
    upper = math.sqrt(am ** 3 / mu) * (2 * math.pi + math.pi - (bm - math.sin(bm)))
    system = {
        "system_id": "refB_hohmann_like",
        "mu_km3_s2": mu,
        "objects": [
            {"name": "inner", "t0_days": 0.0, "a_km": R1, "e": 0.0, "i_deg": 0.0, "Omega_deg": 0.0, "omega_deg": 0.0, "M0_deg": 0.0},
            {"name": "outer", "t0_days": t2, "a_km": R2, "e": 0.0, "i_deg": 0.0, "Omega_deg": 0.0, "omega_deg": 0.0, "M0_deg": 170.0},
        ],
        "ephemeris_queries": [{"object": "inner", "t_days": 0.0}, {"object": "outer", "t_days": t2}],
        "transfer_queries": [
            {"from": "inner", "t1_days": 0.0, "to": "outer", "t2_days": t2, "n_max": 1},
            {"from": "inner", "t1_days": 0.25, "to": "outer", "t2_days": 2.9, "n_max": 3},
        ],
    }
    hand = {
        "ephemeris": [
            {"r_km": [R1, 0.0, 0.0], "v_km_s": [0.0, vc1, 0.0]},
            {"r_km": [R2 * math.cos(th), R2 * math.sin(th), 0.0], "v_km_s": [-vc2 * math.sin(th), vc2 * math.cos(th), 0.0]},
        ],
        "transfer0": {
            "theta_deg": 170.0, "N0_a_km": a, "N0_e": e, "N0_v1_km_s": [0.0, v1, 0.0],
            "N0_v2_km_s": [vr2 * math.cos(th) - vt2 * math.sin(th), vr2 * math.sin(th) + vt2 * math.cos(th), 0.0],
            "N0_dv_km_s": dv, "t_min1_lower_days": lower / 86400, "t_min1_upper_days": upper / 86400,
            "solutions": 1, "T_days": t2,
            "hohmann_dv_km_s_for_scale": (math.sqrt(2 * mu * R2 / (R1 * (R1 + R2))) - vc1) + (vc2 - math.sqrt(2 * mu * R1 / (R2 * (R1 + R2)))),
        },
    }
    return system, hand


def hyperbolic_long_way():
    mu = 1.32712440018e11
    aH, eH, iH = -3.0e8, 1.6, 12.0
    R = 1.5e8
    t1 = 1000.0
    rp = -aH * (eH - 1)
    vp = math.sqrt(mu * (eH + 1) / rp)
    system = {
        "system_id": "refB_hyperbolic_long_way",
        "mu_km3_s2": mu,
        "objects": [
            {"name": "visitor", "t0_days": t1, "a_km": aH, "e": eH, "i_deg": iH, "Omega_deg": 0.0, "omega_deg": 0.0, "M0_deg": 0.0},
            {"name": "planet", "t0_days": 1400.0, "a_km": R, "e": 0.0, "i_deg": 0.0, "Omega_deg": 0.0, "omega_deg": 0.0, "M0_deg": 250.0},
            {"name": "rock", "t0_days": 0.0, "a_km": 2.6e8, "e": 0.18, "i_deg": 7.5, "Omega_deg": 40.0, "omega_deg": 300.0, "M0_deg": 15.0},
        ],
        "ephemeris_queries": [{"object": "visitor", "t_days": t1}, {"object": "planet", "t_days": 1400.0}, {"object": "visitor", "t_days": 1123.4}],
        "transfer_queries": [
            {"from": "visitor", "t1_days": t1, "to": "planet", "t2_days": 1400.0, "n_max": 1},
            {"from": "planet", "t1_days": 1400.0, "to": "rock", "t2_days": 2600.0, "n_max": 2},
            {"from": "visitor", "t1_days": t1, "to": "planet", "t2_days": 1060.0, "n_max": 0},
        ],
    }
    ci, si = math.cos(math.radians(iH)), math.sin(math.radians(iH))
    hand = {
        "ephemeris": [
            {"r_km": [rp, 0.0, 0.0], "v_km_s": [0.0, vp * ci, vp * si]},
            {"r_km": [R * math.cos(math.radians(250)), R * math.sin(math.radians(250)), 0.0],
             "v_km_s": [-math.sqrt(mu / R) * math.sin(math.radians(250)), math.sqrt(mu / R) * math.cos(math.radians(250)), 0.0]},
        ],
        "transfer0": {"theta_deg": 250.0},
        # the planet at t = 1060 d sits 340 d of circular motion before its 250 deg epoch position
        "transfer2": {"theta_deg": (250.0 - math.degrees(math.sqrt(mu / R ** 3) * 340 * 86400.0)) % 360.0},
    }
    return system, hand


if __name__ == "__main__":
    hands = {}
    for fn in (hohmann_like, hyperbolic_long_way):
        system, hand = fn()
        with open(os.path.join(HERE, system["system_id"] + ".json"), "w") as fh:
            json.dump(system, fh, indent=1)
        hands[system["system_id"]] = hand
    with open(os.path.join(HERE, "hand_values.json"), "w") as fh:
        json.dump(hands, fh, indent=1)
    print("wrote", ", ".join(sorted(hands)))
