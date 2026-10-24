"""Self-consistency of a Lambert report (dev tool): every solution re-propagated from (r1, v1)
over the time of flight with the oracle's Kepler machinery must land on r2 with velocity v2;
the revolution count is checked from the mean motion; energies and sums are printed.

usage: check.py <system.json> <report.json>
"""
import importlib.util, json, math, sys
import numpy as np
from pathlib import Path
spec = importlib.util.spec_from_file_location("lb", Path(__file__).resolve().parents[3] / "tasks/physical-sciences/astronomy/lambert-transfer-audit/solution/lambert.py")
lb = importlib.util.module_from_spec(spec); spec.loader.exec_module(lb)
m, r = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
mu = m["mu_km3_s2"]
bodies = {o["name"]: lb.Body(o, mu) for o in m["objects"]}


def propagate(r0, v0, dt):
    """Universal-variable-free: convert to elements and use the oracle's Kepler solver."""
    r0, v0 = np.asarray(r0), np.asarray(v0)
    R = np.linalg.norm(r0); vv = float(np.dot(v0, v0))
    a = 1 / (2 / R - vv / mu)
    h = np.cross(r0, v0); ev = np.cross(v0, h) / mu - r0 / R; e = np.linalg.norm(ev)
    n = math.sqrt(mu / abs(a) ** 3)
    # true anomaly at start
    nu0 = math.atan2(float(np.dot(np.cross(ev, r0), h)) / np.linalg.norm(h), float(np.dot(ev, r0)))
    if e < 1:
        E0 = 2 * math.atan2(math.sqrt(1 - e) * math.sin(nu0 / 2), math.sqrt(1 + e) * math.cos(nu0 / 2))
        M0 = E0 - e * math.sin(E0)
        M = M0 + n * dt
        E = lb.kepler_E(M, e)
        nu = 2 * math.atan2(math.sqrt(1 + e) * math.sin(E / 2), math.sqrt(1 - e) * math.cos(E / 2))
        revs = (M - M0) / (2 * math.pi)
    else:
        H0 = 2 * math.atanh(math.sqrt((e - 1) / (e + 1)) * math.tan(nu0 / 2))
        M0 = e * math.sinh(H0) - H0
        M = M0 + n * dt
        H = lb.kepler_H(M, e)
        nu = 2 * math.atan(math.sqrt((e + 1) / (e - 1)) * math.tanh(H / 2))
        revs = 0.0
    p = a * (1 - e * e)
    rr = p / (1 + e * math.cos(nu))
    ir = ev / e; ih = h / np.linalg.norm(h); it = np.cross(ih, ir)
    r1 = rr * (math.cos(nu) * ir + math.sin(nu) * it)
    v1 = math.sqrt(mu / p) * (-math.sin(nu) * ir + (e + math.cos(nu)) * it)
    return r1, v1, revs, nu - nu0


worst_r = worst_v = 0.0
for q, t in zip(m["transfer_queries"], r["transfers"]):
    rA, vA = bodies[q["from"]].state(q["t1_days"]); rB, vB = bodies[q["to"]].state(q["t2_days"])
    tof = (q["t2_days"] - q["t1_days"]) * 86400
    for s in t["solutions"]:
        r2p, v2p, revs, dnu = propagate(rA, s["v1_km_s"], tof)
        er = np.linalg.norm(r2p - rB) / np.linalg.norm(rB); ev_ = np.linalg.norm(v2p - np.array(s["v2_km_s"])) / np.linalg.norm(s["v2_km_s"])
        worst_r, worst_v = max(worst_r, er), max(worst_v, ev_)
        hz = np.cross(rA, s["v1_km_s"])[2]
        print(f"{q['from']}->{q['to']} N={s['N']} {s['branch']:6s} land err r {er:.2e} v {ev_:.2e} revs {revs:.4f} hz>0 {hz > 0} a {s['a_km']:.3f} dv {s['dv_km_s']:.6f}")
    print("   theta %.6f tmin %s best %d" % (t["theta_deg"], ["%.6f" % x for x in t["t_min_days"]], t["best"]))
print("worst landing error r %.2e v %.2e" % (worst_r, worst_v))
