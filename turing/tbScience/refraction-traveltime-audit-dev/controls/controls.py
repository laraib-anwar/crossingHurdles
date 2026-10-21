"""Wrong-method controls (dev tool, not shipped), each the exact oracle with one shortcut:

  precritical      reflections only up to the critical angle (p < 1/v below the interface when faster)
  no_refl_first    first-arrival curve built without reflections (refraction-picking habit)
  coarse           exact arrivals; caustic offsets and first-arrival crossovers read off a
                   600-point offset grid without refinement
  legacy           the shipped legacy script

usage: controls.py <control> --model M --output O
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
TASK = HERE.parents[2] / "tasks/earth-sciences/geosciences/refraction-traveltime-audit"
spec = importlib.util.spec_from_file_location("rt", TASK / "solution/raytimes.py")
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)


def precritical(m):
    M = rt.Model(m)
    orig = M.branches

    def br():
        out = []
        for kind, idx, lo, hi in orig():
            if kind == "reflection" and M.a[idx] > M.Vm[idx]:
                hi = min(hi, 1.0 / M.a[idx])
            out.append((kind, idx, lo, hi))
        return out
    M.branches = br
    segs, spec_ = M.segments(), M.specials()
    return dict(model_id=M.id, arrivals=[dict(x_km=x, rays=M.arrivals_at(float(x), segs, spec_)) for x in M.offsets_raw],
                caustics=M.caustics(segs), first_arrival=M.first_arrival(segs, spec_))


def no_refl_first(m):
    M = rt.Model(m)
    segs, spec_ = M.segments(), M.specials()
    rep = rt.solve(m)
    rep["first_arrival"] = M.first_arrival([s for s in segs if s["kind"] != "reflection"], spec_) \
        if any(s["kind"] != "reflection" for s in segs) or spec_ else rep["first_arrival"]
    return rep


def coarse(m):
    rep = rt.solve(m)
    xmax = m["x_max_km"]
    grid = np.linspace(0, xmax, 601)[1:]
    for c in rep["caustics"]:
        c["x_km"] = float(grid[np.argmin(np.abs(grid - c["x_km"]))])
    for f in rep["first_arrival"][:-1]:
        f["x_end_km"] = float(grid[np.argmin(np.abs(grid - f["x_end_km"]))])
    for a, b in zip(rep["first_arrival"][:-1], rep["first_arrival"][1:]):
        b["x_start_km"] = a["x_end_km"]
    rep["first_arrival"] = [f for f in rep["first_arrival"] if f["x_end_km"] > f["x_start_km"]]
    return rep


def legacy(m):
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mp, op = Path(td) / "m.json", Path(td) / "o.json"
        mp.write_text(json.dumps(m))
        subprocess.run([sys.executable, str(TASK / "environment/data/legacy/ttcurve.py"), "--model", str(mp), "--output", str(op)], check=True)
        return json.loads(op.read_text())


CONTROLS = dict(precritical=precritical, no_refl_first=no_refl_first, coarse=coarse, legacy=legacy)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("control", choices=sorted(CONTROLS))
    ap.add_argument("--model", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    m = json.loads(Path(a.model).read_text())
    Path(a.output).write_text(json.dumps(CONTROLS[a.control](m), indent=1) + "\n")
