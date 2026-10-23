"""Compare two cable report directories (dev tool): counts and worst relative differences."""
import json, sys
from pathlib import Path
A, B = Path(sys.argv[1]), Path(sys.argv[2])
w = {k: (0.0, "") for k in ("rin", "att", "zmag", "zph", "tau", "coef")}
bad, n = [], 0
def up(k, d, where):
    if d > w[k][0]: w[k] = (d, where)
for pa in sorted(A.glob("*.json")):
    pb = B / pa.name
    if not pb.exists(): bad.append(f"{pa.stem}: missing in B"); continue
    a, b = json.loads(pa.read_text()), json.loads(pb.read_text()); n += 1
    if len(a["modes"]) != len(b["modes"]): bad.append(f"{pa.stem}: modes {len(a['modes'])}/{len(b['modes'])}")
    rin = next(e["R_MOhm"] for e in b["input_resistance"] if e["site"]["segment"] == 0) if any(e["site"]["segment"] == 0 for e in b["input_resistance"]) else b["input_resistance"][0]["R_MOhm"]
    for i, (x, y) in enumerate(zip(a["input_resistance"], b["input_resistance"])): up("rin", abs(x["R_MOhm"] - y["R_MOhm"]) / y["R_MOhm"], f"{pa.stem} rin {i}")
    for i, (x, y) in enumerate(zip(a["attenuation"], b["attenuation"])): up("att", abs(x["factor"] - y["factor"]) / y["factor"], f"{pa.stem} att {i}")
    for i, (x, y) in enumerate(zip(a["impedance"], b["impedance"])):
        up("zmag", abs(x["magnitude_MOhm"] - y["magnitude_MOhm"]) / y["magnitude_MOhm"], f"{pa.stem} z {i}")
        up("zph", abs(x["phase_deg"] - y["phase_deg"]), f"{pa.stem} z {i} phase")
    for i, (x, y) in enumerate(zip(a["modes"], b["modes"])):
        up("tau", abs(x["tau_ms"] - y["tau_ms"]) / y["tau_ms"], f"{pa.stem} tau {i}")
        up("coef", abs(x["coefficient_MOhm"] - y["coefficient_MOhm"]) / rin, f"{pa.stem} coef {i}")
for k, (d, where) in w.items(): print(f"worst {k}: {d:.2e} ({where})")
for b_ in bad: print("!!", b_)
print(n, "compared")
