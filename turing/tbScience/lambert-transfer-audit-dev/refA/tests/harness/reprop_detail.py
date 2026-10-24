import json, sys, math, importlib.util
import numpy as np
from decimal import Decimal as D
sys.path.insert(0, '.')
import hp
spec = importlib.util.spec_from_file_location("reference", sys.argv[1] + "/reference.py")
ref = importlib.util.module_from_spec(spec); spec.loader.exec_module(ref)
rows = []
for fn in sys.argv[2:]:
    sysd = json.load(open(fn)); mu = sysd["mu_km3_s2"]
    dg = []; rep = ref.compute_report(sysd, dg)
    for qi, (tr, d) in enumerate(zip(rep["transfers"], dg)):
        for s in tr["solutions"]:
            v1 = np.array(s["v1_km_s"])
            rT, vT, _ = ref.kepler_universal(d["r1"], v1, d["T"], mu)
            e = np.linalg.norm(rT - d["r2"]) / np.linalg.norm(d["r2"])
            rows.append((e, sysd["system_id"], qi, s["N"], s["branch"], s["a_km"], s["e"], d["T"], d["r1"], v1, d["r2"], mu))
rows.sort(key=lambda r: -r[0])
for r in rows[:6]:
    e, sid, qi, N, br, a, ecc, T, r1, v1, r2, mu = r
    # Decimal propagation of the same double v1
    rx, vx = hp.kepler([D(float(t)) for t in r1], [D(float(t)) for t in v1], D(T), D(mu))
    ed = float(hp.dsqrt(sum((a_ - D(float(b))) ** 2 for a_, b in zip(rx, r2)))) / np.linalg.norm(r2)
    # sensitivity: finite-difference STM norm (Decimal)
    h = D(float(np.linalg.norm(v1))) * D(10) ** -20
    J = 0
    for j in range(3):
        vp = [D(float(t)) for t in v1]; vp[j] += h
        rp, _ = hp.kepler([D(float(t)) for t in r1], vp, D(T), D(mu))
        J = max(J, float(hp.dsqrt(sum((a_ - b) ** 2 for a_, b in zip(rp, rx))) / h))
    cond = J * np.linalg.norm(v1) / np.linalg.norm(r2)
    print("%s q%d N=%d %-6s a=%.4g e=%.4f T/P=%.3g  double-reprop %.2e  decimal-reprop %.2e  cond(|dr2/dv1| |v1|/|r2|) %.2e" % (
        sid, qi, N, br, a, ecc, T / (2 * math.pi * math.sqrt(abs(a) ** 3 / mu)), e, ed, cond))
