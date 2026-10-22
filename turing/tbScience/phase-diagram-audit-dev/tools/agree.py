"""Compare two phase-diagram report directories (dev tool): counts, labels, worst differences."""
import json, sys
from pathlib import Path
A, B = Path(sys.argv[1]), Path(sys.argv[2])
w = dict(x=(0.0, ""), T=(0.0, "")); bad = []
def up(k, d, where):
    if d > w[k][0]: w[k] = (d, where)
n = 0
for pa in sorted(A.glob("*.json")):
    pb = B / pa.name
    if not pb.exists(): bad.append(f"{pa.stem}: missing in B"); continue
    a, b = json.loads(pa.read_text()), json.loads(pb.read_text()); n += 1
    for i, (ia, ib) in enumerate(zip(a["isotherms"], b["isotherms"])):
        if len(ia["single_phase_regions"]) != len(ib["single_phase_regions"]) or len(ia["tie_lines"]) != len(ib["tie_lines"]):
            bad.append(f"{pa.stem} iso {i}: regions {len(ia['single_phase_regions'])}/{len(ib['single_phase_regions'])} ties {len(ia['tie_lines'])}/{len(ib['tie_lines'])}"); continue
        for k, (g, q) in enumerate(zip(ia["single_phase_regions"], ib["single_phase_regions"])):
            if g["phase"] != q["phase"]: bad.append(f"{pa.stem} iso {i} region {k}: {g['phase']} vs {q['phase']}")
            for f in ("x_lo", "x_hi"): up("x", abs(g[f] - q[f]), f"{pa.stem} iso {i} region {k} {f}")
        for k, (t, q) in enumerate(zip(ia["tie_lines"], ib["tie_lines"])):
            if (t["left_phase"], t["right_phase"]) != (q["left_phase"], q["right_phase"]): bad.append(f"{pa.stem} iso {i} tie {k}: labels differ")
            for f in ("x_left", "x_right"): up("x", abs(t[f] - q[f]), f"{pa.stem} iso {i} tie {k} {f}")
    for key in ("invariants", "congruent_points", "critical_points"):
        if len(a[key]) != len(b[key]): bad.append(f"{pa.stem}: {key} {len(a[key])}/{len(b[key])}"); continue
        for k, (e, q) in enumerate(zip(a[key], b[key])):
            up("T", abs(e["temperature_K"] - q["temperature_K"]) / q["temperature_K"], f"{pa.stem} {key}[{k}] T")
            if key == "invariants":
                if (e["class"], e["name"]) != (q["class"], q["name"]): bad.append(f"{pa.stem} {key}[{k}]: {e['class']}/{e['name']} vs {q['class']}/{q['name']}")
                for j, (p, r) in enumerate(zip(e["phases"], q["phases"])):
                    if p["phase"] != r["phase"]: bad.append(f"{pa.stem} {key}[{k}] phase {j}: {p['phase']} vs {r['phase']}")
                    up("x", abs(p["x"] - r["x"]), f"{pa.stem} {key}[{k}] x{j}")
            else:
                up("x", abs(e["x"] - q["x"]), f"{pa.stem} {key}[{k}] x")
                for f in [f_ for f_ in e if f_ not in ("temperature_K", "x")]:
                    if e[f] != q[f]: bad.append(f"{pa.stem} {key}[{k}] {f}: {e[f]} vs {q[f]}")
print(f"worst x abs {w['x'][0]:.2e} ({w['x'][1]}); worst T rel {w['T'][0]:.2e} ({w['T'][1]})")
for b_ in bad: print("!!", b_)
print(n, "compared")
