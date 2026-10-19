"""Final gate for every recipe: Reference A agrees with the oracle, and the spec's guarantees hold
on Reference A's report. usage: final_gate.py <recipes> <oracle_dir> <refA_dir>"""
import json, sys
from pathlib import Path
R, O, A = (Path(p) for p in sys.argv[1:4])
fails = []
for p in sorted(R.glob("*.json")):
    r = json.loads(p.read_text()); rid = p.stem
    if not (O / p.name).exists() or not (A / p.name).exists():
        fails.append(f"{rid}: missing report"); continue
    a, o = json.loads((A / p.name).read_text()), json.loads((O / p.name).read_text())
    ev = sorted([f["phi"] for f in a["folds"]] + [h["phi"] for h in a["hopf_points"]])
    if any((y - x) / y < 1e-3 for x, y in zip(ev, ev[1:])): fails.append(f"{rid}: events within 1e-3")
    if any(abs(q - e) / e < 1e-3 for q in r["phi_query"] for e in ev): fails.append(f"{rid}: query within 1e-3 of an event")
    if any(not (0.05 <= h["omega"] <= 200) for h in a["hopf_points"]): fails.append(f"{rid}: omega outside [0.05, 200]")
    if any(not (r["phi_min"] < e < r["phi_max"]) for e in ev): fails.append(f"{rid}: event on the window edge")
    if len(a["states"][0]["branches"]) < 1: fails.append(f"{rid}: no state at first query")
    same = (len(a["folds"]) == len(o["folds"]) and len(a["hopf_points"]) == len(o["hopf_points"]) and
            [len(s["branches"]) for s in a["states"]] == [len(s["branches"]) for s in o["states"]] and
            all(x["stability"] == y["stability"] for s, t in zip(a["states"], o["states"]) for x, y in zip(s["branches"], t["branches"])) and
            all(f["kind"] == g["kind"] for f, g in zip(a["folds"], o["folds"])))
    if not same: fails.append(f"{rid}: oracle and Reference A disagree on structure")
print("recipes", len(list(R.glob('*.json'))), "| gate failures:", len(fails))
for f in fails: print("  !!", f)
