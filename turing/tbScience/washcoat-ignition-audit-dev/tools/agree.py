"""Compare two report directories quantity by quantity (dev tool)."""
import json, sys
from pathlib import Path
A, B = Path(sys.argv[1]), Path(sys.argv[2])
worst = dict(phi=(0, ""), val=(0, ""), omega=(0, ""))
bad = []
for pa in sorted(A.glob("*.json")):
    pb = B / pa.name
    if not pb.exists():
        bad.append(f"{pa.stem}: missing in {B}"); continue
    a, b = json.loads(pa.read_text()), json.loads(pb.read_text())
    if len(a["folds"]) != len(b["folds"]) or len(a["hopf_points"]) != len(b["hopf_points"]) or \
       [len(s["branches"]) for s in a["states"]] != [len(s["branches"]) for s in b["states"]]:
        bad.append(f"{pa.stem}: counts differ folds {len(a['folds'])}/{len(b['folds'])} hopf {len(a['hopf_points'])}/{len(b['hopf_points'])} states {[len(s['branches']) for s in a['states']]}/{[len(s['branches']) for s in b['states']]}"); continue
    def upd(k, d, where):
        if d > worst[k][0]: worst[k] = (d, where)
    for i, (f, g) in enumerate(zip(a["folds"], b["folds"])):
        upd("phi", abs(f["phi"] - g["phi"]) / g["phi"], f"{pa.stem} folds[{i}]")
        for k in ("theta_c", "eta"): upd("val", abs(f[k] - g[k]) / max(1, abs(g[k])), f"{pa.stem} folds[{i}].{k}")
        if f["kind"] != g["kind"]: bad.append(f"{pa.stem}: folds[{i}] kind {f['kind']}/{g['kind']}")
    for i, (h, g) in enumerate(zip(a["hopf_points"], b["hopf_points"])):
        upd("phi", abs(h["phi"] - g["phi"]) / g["phi"], f"{pa.stem} hopf[{i}]")
        upd("omega", abs(h["omega"] - g["omega"]) / g["omega"], f"{pa.stem} hopf[{i}]")
        for k in ("theta_c", "eta"): upd("val", abs(h[k] - g[k]) / max(1, abs(g[k])), f"{pa.stem} hopf[{i}].{k}")
    for s, t in zip(a["states"], b["states"]):
        for j, (x, y) in enumerate(zip(s["branches"], t["branches"])):
            for k in ("theta_c", "eta"): upd("val", abs(x[k] - y[k]) / max(1, abs(y[k])), f"{pa.stem} phi {s['phi']} [{j}].{k}")
            if x["stability"] != y["stability"]: bad.append(f"{pa.stem}: phi {s['phi']} [{j}] {x['stability']}/{y['stability']}")
for k, (d, w) in worst.items(): print(f"worst {k}: {d:.2e} at {w}")
for x in bad: print("!!", x)
print(len(list(A.glob('*.json'))), "reports compared")
