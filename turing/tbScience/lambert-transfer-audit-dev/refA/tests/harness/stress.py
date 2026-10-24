"""Random in-domain-ish stress: no exceptions, finite outputs, counts vs dense naive scan,
re-propagation (double) and, for a subset, 60-digit shooting."""
import json, math, sys, time, random
import numpy as np
from decimal import Decimal as D
sys.path.insert(0, '.')
import hp
from guarantees import load_ref
ref = load_ref(sys.argv[1])
NSYS = int(sys.argv[2]); SEED = int(sys.argv[3]); NSHOOT = int(sys.argv[4])
rng = random.Random(SEED)


def rand_obj(name, mu):
    if rng.random() < 0.15:
        a = -10 ** rng.uniform(4, 9); e = rng.uniform(1.05, 4)
        if -a * (e - 1) < 1e3: a = -1e3 / (e - 1) * 1.5
    else:
        a = 10 ** rng.uniform(4, 9); e = rng.choice([0.0, rng.uniform(0, 0.3), rng.uniform(0, 0.95)])
        if a * (1 - e) < 1e3: e = 1 - 1e3 / a * 1.2
    return {"name": name, "t0_days": round(rng.uniform(-2e4, 2e4), 3), "a_km": a, "e": e,
            "i_deg": rng.choice([rng.uniform(0, 180), rng.uniform(0, 10), rng.uniform(170, 180)]),
            "Omega_deg": rng.uniform(0, 360), "omega_deg": rng.uniform(0, 360), "M0_deg": rng.uniform(0, 360)}


def ok_time(o, mu, t):
    a = o["a_km"]; n = math.sqrt(mu / abs(a) ** 3)
    if a > 0:
        return abs(t - o["t0_days"]) <= 2000 * 2 * math.pi / n / 86400
    return abs(math.radians(o["M0_deg"]) + n * (t - o["t0_days"]) * 86400) <= 50


def rand_time(o, mu):
    for _ in range(200):
        a = o["a_km"]; n = math.sqrt(mu / abs(a) ** 3)
        if a > 0:
            span = min(2e4, 2000 * 2 * math.pi / n / 86400)
            t = o["t0_days"] + rng.uniform(-span, span)
        else:
            t = o["t0_days"] + rng.uniform(-50, 50) / n / 86400
        if -2e4 <= t <= 2e4 - 6000:
            return round(t, 4)
    return None


stats = {"transfers": 0, "solutions": 0, "fail": 0, "count_mismatch": 0, "reprop": 0.0, "shoot_v": 0.0,
         "shoot_dv": 0.0, "shoot_a": 0.0, "maxtime": 0.0, "skipped": 0}
nshoot = 0
WORST = []
for k in range(NSYS):
    mu = 10 ** rng.uniform(4, math.log10(2e11))
    objs = [rand_obj("o%d" % i, mu) for i in range(rng.randint(2, 4))]
    tqs = []
    for _ in range(4):
        A, B = rng.sample(objs, 2)
        t1 = rand_time(A, mu)
        if t1 is None: continue
        # T scaled to the dynamical time of A
        P = 2 * math.pi * math.sqrt(abs(A["a_km"]) ** 3 / mu) / 86400
        T = min(6000.0, max(0.1, P * 10 ** rng.uniform(-1.5, 0.9)))
        t2 = round(t1 + T, 4)
        if not ok_time(B, mu, t2) or not ok_time(A, mu, t1): continue
        tqs.append({"from": A["name"], "t1_days": t1, "to": B["name"], "t2_days": t2, "n_max": rng.randint(0, 4)})
    if not tqs:
        continue
    sysd = {"system_id": "s%d" % k, "mu_km3_s2": mu, "objects": objs,
            "ephemeris_queries": [{"object": o["name"], "t_days": t} for o in objs for t in [rand_time(o, mu)] if t is not None][:8],
            "transfer_queries": tqs}
    t0 = time.time()
    try:
        dg = []
        rep = ref.compute_report(sysd, dg)
        ref.check_finite(rep)
    except Exception as exc:
        stats["fail"] += 1
        json.dump(sysd, open("fail_%d_%d.json" % (SEED, k), "w"), indent=1)
        print("FAIL", k, repr(exc))
        continue
    stats["maxtime"] = max(stats["maxtime"], time.time() - t0)
    for q, tr, d in zip(tqs, rep["transfers"], dg):
        th = tr["theta_deg"]
        if not (1 <= th <= 179 or 181 <= th <= 359):
            stats["skipped"] += 1
            continue
        T = d["T"]
        if any(abs(T / 86400 - tm) < 1e-6 * tm for tm in tr["t_min_days"]):
            stats["skipped"] += 1
            continue
        g5 = True
        for s_ in tr["solutions"]:
            a_, e_ = s_["a_km"], s_["e"]
            rp_ = a_ * (1 - e_) if a_ > 0 else -a_ * (e_ - 1)
            vm = max(np.linalg.norm(s_["v1_km_s"]), np.linalg.norm(s_["v2_km_s"]))
            if rp_ < 1e3 or not (1e-3 <= e_ <= 20) or vm > 200 or s_["dv_km_s"] < 1e-3 * vm:
                g5 = False
        if not g5:
            stats["skipped_g5"] = stats.get("skipped_g5", 0) + 1
            continue
        stats["transfers"] += 1
        lam = d["lam"]
        # expected count from T_min (scan-independent) and an independent dense naive scan of T_min(1)
        cnt = 1 + 2 * sum(1 for tm in tr["t_min_days"] if T / 86400 > tm)
        if cnt != len(tr["solutions"]):
            stats["count_mismatch"] += 1
        for N in range(1, q["n_max"] + 1):
            xs = np.linspace(2 * math.pi * N, 2 * math.pi * (N + 1), 4001)[1:-1]
            vals = []
            for x in xs:
                C, S = ref.stumpff(x * x)
                y = lam.r1 + lam.r2 + lam.A * (x * x * S - 1) / math.sqrt(C)
                vals.append((math.sqrt(y / C) ** 3 * S + lam.A * math.sqrt(y)) / lam.sm / 86400)
            vmin = min(vals)
            if vmin < tr["t_min_days"][N - 1] * (1 - 1e-9) or vmin > tr["t_min_days"][N - 1] * (1 + 1e-3):
                stats["count_mismatch"] += 1
                print("tmin mismatch", k, N, vmin, tr["t_min_days"][N - 1])
        for s in tr["solutions"]:
            stats["solutions"] += 1
            v1 = np.array(s["v1_km_s"])
            try:
                rT, vT, _ = ref.kepler_universal(d["r1"], v1, T, mu)
            except Exception as exc:
                print("reprop exception", k, s["N"], s["a_km"], s["e"], repr(exc))
                continue
            rr = np.linalg.norm(rT - d["r2"]) / np.linalg.norm(d["r2"])
            stats["reprop"] = max(stats["reprop"], rr)
            WORST.append((rr, list(map(float, d["r1"])), list(map(float, v1)), list(map(float, d["r2"])), s["v2_km_s"], T, mu, s["N"], s["a_km"], s["e"]))
            if nshoot < NSHOOT:
                nshoot += 1
                vx1, vx2, res = hp.lambert_shoot(d["r1"], v1, d["r2"], D(T), D(mu))
                ve1 = np.array([float(t) for t in vx1]); ve2 = np.array([float(t) for t in vx2])
                ev = max(np.linalg.norm(v1 - ve1) / np.linalg.norm(ve1), np.linalg.norm(np.array(s["v2_km_s"]) - ve2) / np.linalg.norm(ve2))
                stats["shoot_v"] = max(stats["shoot_v"], ev)
                if ev > 1e-11:
                    print("shoot", k, s["N"], s["branch"], ev, s["a_km"], s["e"])
print(stats)

WORST.sort(key=lambda w: -w[0])
json.dump(WORST[:int(sys.argv[5]) if len(sys.argv) > 5 else 30], open("worst_%d.json" % SEED, "w"))
