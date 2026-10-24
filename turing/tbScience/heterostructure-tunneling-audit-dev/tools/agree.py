"""Compare two heterostructure report directories (dev tool): counts and worst differences."""
import json, sys
from pathlib import Path
A, B = Path(sys.argv[1]), Path(sys.argv[2])
w = {k: (0.0, "") for k in ("bound_E", "T", "max_E", "max_T")}
bad, n = [], 0
def up(k, d, where):
    if d > w[k][0]: w[k] = (d, where)
for pa in sorted(A.glob("*.json")):
    pb = B / pa.name
    if not pb.exists(): bad.append(f"{pa.stem}: missing in B"); continue
    a, b = json.loads(pa.read_text()), json.loads(pb.read_text()); n += 1
    if len(a["bound_states"]) != len(b["bound_states"]): bad.append(f"{pa.stem}: bound {len(a['bound_states'])}/{len(b['bound_states'])}")
    else:
        for i, (x, y) in enumerate(zip(a["bound_states"], b["bound_states"])): up("bound_E", abs(x["E_eV"] - y["E_eV"]), f"{pa.stem} bound {i}")
    for i, (x, y) in enumerate(zip(a["transmission"], b["transmission"])): up("T", abs(x["T"] / y["T"] - 1), f"{pa.stem} T {i}")
    if len(a["maxima"]) != len(b["maxima"]): bad.append(f"{pa.stem}: maxima {len(a['maxima'])}/{len(b['maxima'])}")
    else:
        for i, (x, y) in enumerate(zip(a["maxima"], b["maxima"])):
            up("max_E", abs(x["E_eV"] - y["E_eV"]), f"{pa.stem} max {i}"); up("max_T", abs(x["T"] / y["T"] - 1), f"{pa.stem} max {i}")
for k, (d, where) in w.items(): print(f"worst {k}: {d:.2e} ({where})")
for b_ in bad: print("!!", b_)
print(n, "compared")
