"""Compare two report directories (dev tool): worst differences per quantity in the units of the
spec's tolerance rule (concentrations relative to cmax of B, auc relative, times absolute in h).

usage: agree.py <dir_A> <dir_B>
"""
import json, sys
from pathlib import Path
A, B = Path(sys.argv[1]), Path(sys.argv[2])
w = {}
bad, n = [], 0
def up(k, d, where):
    if d > w.get(k, (0.0, ""))[0]: w[k] = (d, where)
for pb in sorted(B.glob("*.json")):
    pa = A / pb.name
    if not pa.exists(): bad.append(f"{pb.stem}: missing in A"); continue
    a, b = json.loads(pa.read_text()), json.loads(pb.read_text()); n += 1
    S = b["cmax"]
    for i, (x, y) in enumerate(zip(a["concentrations"], b["concentrations"])): up("conc", abs(x - y) / S, f"{pb.stem} q{i}")
    up("auc", abs(a["auc"] - b["auc"]) / abs(b["auc"]), pb.stem)
    up("cmax", abs(a["cmax"] - b["cmax"]) / S, pb.stem)
    up("t_cmax", abs(a["t_cmax"] - b["t_cmax"]), pb.stem)
    for k in ("cmax", "cmin", "trough"): up("ss_" + k, abs(a["steady_state"][k] - b["steady_state"][k]) / S, pb.stem)
    up("tiw", abs(a["steady_state"]["time_in_window"] - b["steady_state"]["time_in_window"]), pb.stem)
    if a["steady_state"]["n_cycles_to_steady"] != b["steady_state"]["n_cycles_to_steady"]:
        bad.append(f"{pb.stem}: n_cycles {a['steady_state']['n_cycles_to_steady']} vs {b['steady_state']['n_cycles_to_steady']}")
for k, (d, where) in w.items(): print(f"worst {k:9s}: {d:.2e} ({where})")
for b_ in bad: print("!!", b_)
print(n, "compared")
