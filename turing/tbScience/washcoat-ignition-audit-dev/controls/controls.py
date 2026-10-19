"""Wrong-method controls (dev tool, not shipped), each the exact oracle with one shortcut:

  no_film     exposed face at bulk-gas conditions (Bi_m, Bi_h -> infinity)
  slope_rule  exact steady states, stability by the slope rule (middle of three unstable,
              everything else stable), no Hopf analysis
  coarse      exact curve sampled on 60 points, folds and states read off the grid without refinement
  legacy      the shipped legacy script

usage: controls.py <control> --recipe R --output O
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TASK = HERE.parents[2] / "tasks/engineering-sciences/chemical-engineering/washcoat-ignition-audit"
spec = importlib.util.spec_from_file_location("lo", TASK / "solution/lightoff_exact.py")
lo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lo)


def no_film(r):
    rr = dict(r, Bi_m=1e7, Bi_h=1e7)
    return lo.solve(rr)


def slope_rule(r):
    rep = lo.solve(r)
    rep["hopf_points"] = []
    for s in rep["states"]:
        n = len(s["branches"])
        for k, b in enumerate(s["branches"]):
            b["stability"] = "unstable_real" if (n >= 3 and k % 2 == 1) else "stable"
    return rep


def coarse(r):
    L = lo.Layer(r)
    zs = np.linspace(-30.0, 23.0, 60)
    S = [L.state(lo.cs_of(z)) for z in zs]
    ph = np.array([s[0] for s in S])
    folds = []
    for i in range(1, len(zs) - 1):
        if (ph[i] - ph[i - 1]) * (ph[i + 1] - ph[i]) < 0 and r["phi_min"] < ph[i] < r["phi_max"]:
            folds.append(dict(phi=float(ph[i]), theta_c=float(S[i][1]), eta=float(S[i][2]),
                              kind="ignition" if ph[i] > ph[i - 1] else "extinction"))
    exact = lo.solve(r)
    states = []
    for q in r["phi_query"]:
        br = []
        for i in range(len(zs) - 1):
            if (ph[i] - q) * (ph[i + 1] - q) < 0:
                w = (q - ph[i]) / (ph[i + 1] - ph[i])
                br.append(dict(theta_c=float(S[i][1] + w * (S[i + 1][1] - S[i][1])),
                               eta=float(S[i][2] + w * (S[i + 1][2] - S[i][2]))))
        br.sort(key=lambda b: b["theta_c"])
        ex = next(s for s in exact["states"] if s["phi"] == q)["branches"]
        for k, b in enumerate(br):
            b["stability"] = ex[k]["stability"] if k < len(ex) else "stable"
        states.append(dict(phi=q, branches=br))
    folds.sort(key=lambda f: f["phi"])
    return dict(recipe_id=r["recipe_id"], folds=folds, hopf_points=exact["hopf_points"], states=states)


def legacy(r):
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        rp, op = Path(td) / "r.json", Path(td) / "o.json"
        rp.write_text(json.dumps(r))
        subprocess.run([sys.executable, str(TASK / "environment/data/legacy/lightoff.py"), "--recipe", str(rp), "--output", str(op)], check=True)
        return json.loads(op.read_text())


CONTROLS = dict(no_film=no_film, slope_rule=slope_rule, coarse=coarse, legacy=legacy)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("control", choices=sorted(CONTROLS))
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    r = json.loads(Path(a.recipe).read_text())
    Path(a.output).write_text(json.dumps(CONTROLS[a.control](r), indent=1) + "\n")
