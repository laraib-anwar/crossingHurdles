"""Domain/guarantee checker for a system using reference.py's report (validation only)."""
import math, json, sys, importlib.util
import numpy as np
from decimal import Decimal as D


def load_ref(refdir):
    spec = importlib.util.spec_from_file_location("reference", refdir + "/reference.py")
    ref = importlib.util.module_from_spec(spec); spec.loader.exec_module(ref)
    return ref


def check(sysd, ref):
    bad = []
    mu = sysd["mu_km3_s2"]
    if not (1e4 <= mu <= 2e11): bad.append("mu")
    objs = {o["name"]: o for o in sysd["objects"]}
    if not (2 <= len(objs) <= 6): bad.append("nobj")
    for o in sysd["objects"]:
        a, e = o["a_km"], o["e"]
        if a > 0:
            if not (1e4 <= a <= 1e9 and 0 <= e <= 0.95): bad.append("elem " + o["name"])
            if a * (1 - e) < 1e3: bad.append("g4 " + o["name"])
        else:
            if not (-1e9 <= a <= -1e4 and 1.05 <= e <= 4): bad.append("elem " + o["name"])
            if -a * (e - 1) < 1e3: bad.append("g4 " + o["name"])
        if not (0 <= o["i_deg"] <= 180): bad.append("i")
        for k in ("Omega_deg", "omega_deg", "M0_deg"):
            if not (0 <= o[k] < 360): bad.append(k)
        if not (-2e4 <= o["t0_days"] <= 2e4): bad.append("t0")

    def g3(name, t):
        o = objs[name]; a = o["a_km"]
        n = math.sqrt(mu / abs(a) ** 3)
        if a > 0:
            P = 2 * math.pi / n / 86400
            return abs(t - o["t0_days"]) <= 2000 * P
        M = math.radians(o["M0_deg"]) + n * (t - o["t0_days"]) * 86400
        return abs(M) <= 50
    if not (2 <= len(sysd["ephemeris_queries"]) <= 8): bad.append("neph")
    for q in sysd["ephemeris_queries"]:
        if not g3(q["object"], q["t_days"]): bad.append("g3 eph")
        if not (-2e4 <= q["t_days"] <= 2e4): bad.append("t eph")
    if not (2 <= len(sysd["transfer_queries"]) <= 6): bad.append("ntr")
    dg = []
    rep = ref.compute_report(sysd, dg)
    for qi, (q, tr, d) in enumerate(zip(sysd["transfer_queries"], rep["transfers"], dg)):
        if q["from"] == q["to"]: bad.append("q%d same object" % qi)
        T = q["t2_days"] - q["t1_days"]
        if not (0.1 <= T <= 6000): bad.append("q%d T" % qi)
        if not (0 <= q["n_max"] <= 4): bad.append("nmax")
        for nm, t in ((q["from"], q["t1_days"]), (q["to"], q["t2_days"])):
            if not g3(nm, t): bad.append("q%d g3" % qi)
            if not (-2e4 <= t <= 2e4): bad.append("q%d t" % qi)
        th = tr["theta_deg"]
        if not (1 <= th <= 179 or 181 <= th <= 359): bad.append("q%d theta %.3f" % (qi, th))
        if np.linalg.norm(d["r1"]) < 1e3 or np.linalg.norm(d["r2"]) < 1e3: bad.append("q%d r" % qi)
        for tm in tr["t_min_days"]:
            if abs(T - tm) < 1e-6 * tm: bad.append("q%d tmin gap" % qi)
        dvs = sorted(s["dv_km_s"] for s in tr["solutions"])
        if len(dvs) > 1 and dvs[1] - dvs[0] < 1e-6 * dvs[0]: bad.append("q%d best not unique" % qi)
        for N in range(1, q["n_max"] + 1):
            ss = [s for s in tr["solutions"] if s["N"] == N]
            if ss and (ss[1]["a_km"] - ss[0]["a_km"]) < 1e-6 * ss[1]["a_km"]: bad.append("q%d a sep" % qi)
        for s in tr["solutions"]:
            a, e = s["a_km"], s["e"]
            rp = a * (1 - e) if a > 0 else -a * (e - 1)
            v1 = np.linalg.norm(s["v1_km_s"]); v2 = np.linalg.norm(s["v2_km_s"])
            if rp < 1e3: bad.append("q%d g5 rp N=%d %s" % (qi, s["N"], s["branch"]))
            if not (1e-3 <= e <= 20): bad.append("q%d g5 e" % qi)
            if max(v1, v2) > 200: bad.append("q%d g5 speed" % qi)
            if s["dv_km_s"] < 1e-3 * max(v1, v2): bad.append("q%d g5 dv" % qi)
    return bad, rep


if __name__ == "__main__":
    ref = load_ref(sys.argv[1])
    for fn in sys.argv[2:]:
        s = json.load(open(fn))
        bad, rep = check(s, ref)
        print(s["system_id"], "in-domain" if not bad else bad)
