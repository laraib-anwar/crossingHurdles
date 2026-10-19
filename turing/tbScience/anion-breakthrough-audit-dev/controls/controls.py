"""Wrong-method controls (dev tool, not shipped). Each control is a program with the task's CLI
built from the oracle's machinery with one scientific shortcut, so that it is graded by the
verifier's own validate/compare functions:

  allshock    every spreading wave replaced by a single sharp front at the jump-condition
              position of its two end states (the sharp-front assumption, D1)
  superpose   the second feed's waves superposed on the first feed's without interactions (D4)
  clamp       the exact history with every effluent concentration capped at the largest feed
              value of that ion ("effluent cannot exceed influent", the component-wise habit D2/D3)
  legacy      the shipped legacy script itself

usage: controls.py <control> --recipe <recipe.json> --output <report.json>
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOL = HERE.parents[2] / "tasks/engineering-sciences/chemical-engineering/anion-breakthrough-audit/solution/ixfront.py"
LEGACY = HERE.parents[2] / "tasks/engineering-sciences/chemical-engineering/anion-breakthrough-audit/environment/data/legacy/ixbreak.py"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def allshock(recipe):
    ix = load(SOL, "ix_allshock")
    orig = ix.riemann_waves

    def waves(sysm, hU, hD):
        out = []
        for w in orig(sysm, hU, hD):
            if w["kind"] == "fan":
                k = w["k"]
                out.append(dict(kind="shock", k=k, h_ahead=w["h_ahead"], h_behind=w["h_behind"],
                                sig=sysm.sigma(w["h_ahead"], k, w["h_behind"][k])))
            else:
                out.append(w)
        return out
    ix.riemann_waves = waves
    return ix.solve(recipe)


def superpose(recipe):
    ix = load(SOL, "ix_superpose")
    ix.cross = lambda *a, **k: None
    ix.merge_same_family = lambda sysm, A, B, target: [c for c in A + B if c.alive]
    return ix.solve(recipe)


def clamp(recipe):
    ix = load(SOL, "ix_clamp")
    rep = ix.solve(recipe)
    CT = recipe["C_T_meq_per_L"]
    cap = [max(step["composition_meq_per_L"][i] for step in recipe["feed_program"]) for i in ix.IONS]
    x0 = recipe["initial_resin_fraction"]
    a = recipe["alpha"]
    s = sum(x0[i] / a[i] for i in ix.IONS)
    init = [CT * (x0[i] / a[i]) / s for i in ix.IONS]
    cap = [max(c, v) for c, v in zip(cap, init)]

    def fix(comp):
        c = [min(v, m) for v, m in zip(comp, cap)]
        tot = sum(c)
        return [v * CT / tot for v in c]
    for sh in rep["shocks"]:
        sh["before_meq_per_L"], sh["after_meq_per_L"] = fix(sh["before_meq_per_L"]), fix(sh["after_meq_per_L"])
    for t in rep["transitions"]:
        t["start_meq_per_L"], t["end_meq_per_L"] = fix(t["start_meq_per_L"]), fix(t["end_meq_per_L"])
    for p in rep["plateaus"]:
        p["composition_meq_per_L"] = fix(p["composition_meq_per_L"])
    rep["samples"] = [fix(s) for s in rep["samples"]]
    # peak and limit from the clamped history (plateaus, shock afters, transition ends)
    cand = [(p["bv_start"], p["composition_meq_per_L"][1]) for p in rep["plateaus"]]
    cand += [(s["bv"], s["after_meq_per_L"][1]) for s in rep["shocks"]]
    cand += [(t["bv_start"], t["start_meq_per_L"][1]) for t in rep["transitions"]] + [(t["bv_end"], t["end_meq_per_L"][1]) for t in rep["transitions"]]
    peak = max(v for _, v in cand)
    rep["nitrate_peak"] = dict(meq_per_L=peak, bv=min(b for b, v in cand if v == peak))
    lim = recipe["nitrate_limit_meq_per_L"]
    above = sorted(b for b, v in cand if v > lim)
    rep["nitrate_limit_bv"] = above[0] if above else None
    return rep


def legacy(recipe):
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        rp, op = Path(td) / "r.json", Path(td) / "o.json"
        rp.write_text(json.dumps(recipe))
        subprocess.run([sys.executable, str(LEGACY), "--recipe", str(rp), "--output", str(op)], check=True)
        return json.loads(op.read_text())


CONTROLS = dict(allshock=allshock, superpose=superpose, clamp=clamp, legacy=legacy)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("control", choices=sorted(CONTROLS))
    ap.add_argument("--recipe", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    recipe = json.loads(Path(args.recipe).read_text())
    rep = CONTROLS[args.control](recipe)
    Path(args.output).write_text(json.dumps(rep, indent=1) + "\n")
