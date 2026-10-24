"""Compare two Lambert report directories (dev tool): labels, best, worst relative differences."""
import json, sys
import numpy as np
from pathlib import Path
A, B = Path(sys.argv[1]), Path(sys.argv[2])
w = {k: (0.0, "") for k in ("r", "v", "vel", "a", "e", "dv", "tmin", "theta")}
bad, n = [], 0
def up(k, d, where):
    if d > w[k][0]: w[k] = (d, where)
def rel(x, y): return abs(x - y) / abs(y)
def vrel(x, y): return float(np.linalg.norm(np.array(x) - np.array(y)) / np.linalg.norm(y))
for pa in sorted(A.glob("*.json")):
    pb = B / pa.name
    if not pb.exists(): bad.append(f"{pa.stem}: missing in B"); continue
    a, b = json.loads(pa.read_text()), json.loads(pb.read_text()); n += 1
    for i, (x, y) in enumerate(zip(a["ephemeris"], b["ephemeris"])):
        up("r", vrel(x["r_km"], y["r_km"]), f"{pa.stem} eph {i}"); up("v", vrel(x["v_km_s"], y["v_km_s"]), f"{pa.stem} eph {i}")
    for i, (x, y) in enumerate(zip(a["transfers"], b["transfers"])):
        if [(s["N"], s["branch"]) for s in x["solutions"]] != [(s["N"], s["branch"]) for s in y["solutions"]]:
            bad.append(f"{pa.stem} transfer {i}: labels differ {[(s['N'], s['branch']) for s in x['solutions']]} vs {[(s['N'], s['branch']) for s in y['solutions']]}"); continue
        if x["best"] != y["best"]: bad.append(f"{pa.stem} transfer {i}: best {x['best']} vs {y['best']}")
        up("theta", abs(x["theta_deg"] - y["theta_deg"]), f"{pa.stem} transfer {i}")
        for k, (p, q) in enumerate(zip(x["t_min_days"], y["t_min_days"])): up("tmin", rel(p, q), f"{pa.stem} transfer {i} tmin {k}")
        for k, (s, t) in enumerate(zip(x["solutions"], y["solutions"])):
            up("vel", max(vrel(s["v1_km_s"], t["v1_km_s"]), vrel(s["v2_km_s"], t["v2_km_s"])), f"{pa.stem} transfer {i} sol {k}")
            up("a", rel(s["a_km"], t["a_km"]), f"{pa.stem} transfer {i} sol {k}"); up("e", rel(s["e"], t["e"]), f"{pa.stem} transfer {i} sol {k}"); up("dv", rel(s["dv_km_s"], t["dv_km_s"]), f"{pa.stem} transfer {i} sol {k}")
for k, (d, where) in w.items(): print(f"worst {k}: {d:.2e} ({where})")
for b_ in bad: print("!!", b_)
print(n, "compared")
