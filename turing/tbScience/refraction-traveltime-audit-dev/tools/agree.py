"""Compare two traveltime report directories (dev tool)."""
import json, sys
from pathlib import Path
A, B = Path(sys.argv[1]), Path(sys.argv[2])
w = dict(tp=(0, ""), x=(0, "")); bad = []
for pa in sorted(A.glob("*.json")):
    pb = B / pa.name
    if not pb.exists(): bad.append(f"{pa.stem}: missing"); continue
    a, b = json.loads(pa.read_text()), json.loads(pb.read_text())
    ca, cb = [len(x["rays"]) for x in a["arrivals"]], [len(x["rays"]) for x in b["arrivals"]]
    if ca != cb or len(a["caustics"]) != len(b["caustics"]) or len(a["first_arrival"]) != len(b["first_arrival"]):
        bad.append(f"{pa.stem}: counts {ca}/{cb} caustics {len(a['caustics'])}/{len(b['caustics'])} fa {len(a['first_arrival'])}/{len(b['first_arrival'])}"); continue
    def up(k, d, where):
        if d > w[k][0]: w[k] = (d, where)
    for x, y in zip(a["arrivals"], b["arrivals"]):
        for i, (r, q) in enumerate(zip(x["rays"], y["rays"])):
            if (r["kind"], r["index"]) != (q["kind"], q["index"]): bad.append(f"{pa.stem} x {x['x_km']} ray {i}: {r['kind']}{r['index']} vs {q['kind']}{q['index']}")
            for k in ("t_s", "p_s_km"): up("tp", abs(r[k] - q[k]) / abs(q[k]), f"{pa.stem} x {x['x_km']} ray {i} {k}")
    for i, (c, q) in enumerate(zip(a["caustics"], b["caustics"])):
        up("x", abs(c["x_km"] - q["x_km"]) / q["x_km"], f"{pa.stem} caustic {i}")
        for k in ("t_s", "p_s_km"): up("tp", abs(c[k] - q[k]) / abs(q[k]), f"{pa.stem} caustic {i} {k}")
    for i, (f, q) in enumerate(zip(a["first_arrival"], b["first_arrival"])):
        if (f["kind"], f["index"]) != (q["kind"], q["index"]): bad.append(f"{pa.stem} fa {i}: {f['kind']}{f['index']} vs {q['kind']}{q['index']}")
        if i + 1 < len(b["first_arrival"]): up("x", abs(f["x_end_km"] - q["x_end_km"]) / q["x_end_km"], f"{pa.stem} fa {i} end")
print(f"worst t/p rel {w['tp'][0]:.2e} ({w['tp'][1]}); worst x rel {w['x'][0]:.2e} ({w['x'][1]})")
for b_ in bad: print("!!", b_)
print(len(list(A.glob('*.json'))), "compared")
