"""Compare two frame report directories (dev tool): counts and worst differences (section 5 rule)."""
import json, sys
from pathlib import Path
A, B = Path(sys.argv[1]), Path(sys.argv[2])
w = {k: (0.0, "") for k in ("freq", "static", "harm")}
bad, n = [], 0
def up(k, d, where):
    if d > w[k][0]: w[k] = (d, where)
for pa in sorted(A.glob("*.json")):
    pb = B / pa.name
    if not pb.exists(): bad.append(f"{pa.stem}: missing in B"); continue
    a, b = json.loads(pa.read_text()), json.loads(pb.read_text()); n += 1
    if a["count_below"] != b["count_below"]: bad.append(f"{pa.stem}: count_below {a['count_below']}/{b['count_below']}")
    for i, (x, y) in enumerate(zip(a["frequencies_Hz"], b["frequencies_Hz"])): up("freq", abs(x - y) / y, f"{pa.stem} f{i}")
    tr = max([abs(s[k]) for s in b["static"] for k in ("ux", "uy")] or [0]); ro = max([abs(s["rz"]) for s in b["static"]] or [0])
    for i, (x, y) in enumerate(zip(a["static"], b["static"])):
        for k in ("ux", "uy", "rz"): up("static", abs(x[k] - y[k]) / max(abs(y[k]), ro if k == "rz" else tr, 1e-300), f"{pa.stem} static {i} {k}")
    ht = max([abs(h["U"]) for h in b["harmonic"] if h["response_dof"] != "rz"] or [0]); hr = max([abs(h["U"]) for h in b["harmonic"] if h["response_dof"] == "rz"] or [0])
    for i, (x, y) in enumerate(zip(a["harmonic"], b["harmonic"])): up("harm", abs(x["U"] - y["U"]) / max(abs(y["U"]), hr if y["response_dof"] == "rz" else ht, 1e-300), f"{pa.stem} harm {i}")
for k, (d, where) in w.items(): print(f"worst {k}: {d:.2e} ({where})")
for b_ in bad: print("!!", b_)
print(n, "compared")
