"""Find executable witnesses of the legacy script's defects at run time.

Runs the legacy script and the corrected program on the shipped recipes, compares the diagnosis
quantities of the spec, and writes diagnosis.json with one entry per defect. Nothing is stored.

usage: diagnose.py --program <lightoff_exact.py> --legacy <lightoff.py> --recipes <dir> --output <diagnosis.json>
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TOL_PHI = 1e-6

DESCRIPTIONS = {
    "fold_phi": "The film resistances are ignored (the exposed face is put at bulk-gas conditions), so "
                "the ignition and extinction points sit at the wrong Thiele modulus; the turning points "
                "are also read off a coarse grid without refinement.",
    "fold_count": "The steady-state curve is sampled on a coarse grid of wall concentrations under the "
                  "wrong boundary conditions, so narrow hysteresis loops (and the second loop of a "
                  "four-fold curve) are missed or invented.",
    "state_count": "With the film ignored and the curve read off a coarse grid, the number of steady states "
                   "at a given Thiele modulus is wrong where the exact curve has a loop the script does not "
                   "see, and states beyond the grid's range are lost.",
    "stability": "Stability follows the slope rule (middle state unstable, outer states stable). With a "
                 "Lewis number below one the ignited state loses stability through a Hopf bifurcation, "
                 "which only the linearised transient problem shows.",
    "hopf_count": "No transient analysis is done, so Hopf points (and the oscillatory instability between "
                  "them) are never reported.",
}
ORDER = ["fold_phi", "fold_count", "state_count", "stability", "hopf_count"]


def run(program, recipe_path, out_path):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    subprocess.run([sys.executable, str(program), "--recipe", str(recipe_path), "--output", str(out_path)],
                   check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    with open(out_path, encoding="utf-8") as fh:
        return json.load(fh)


def witnesses(q, recipe, leg, cor):
    """Candidate (selector, legacy, correct) triples for quantity q on one recipe."""
    out = []
    if q == "fold_count" and len(leg["folds"]) != len(cor["folds"]):
        out.append((None, len(leg["folds"]), len(cor["folds"])))
    if q == "hopf_count" and len(leg["hopf_points"]) != len(cor["hopf_points"]):
        out.append((None, len(leg["hopf_points"]), len(cor["hopf_points"])))
    if q == "fold_phi" and len(leg["folds"]) == len(cor["folds"]):
        for i, (a, b) in enumerate(zip(leg["folds"], cor["folds"])):
            if abs(a["phi"] - b["phi"]) > TOL_PHI * abs(b["phi"]):
                out.append((i, a["phi"], b["phi"]))
    for sl, sc in zip(leg["states"], cor["states"]):
        if q == "state_count" and len(sl["branches"]) != len(sc["branches"]):
            out.append((sl["phi"], len(sl["branches"]), len(sc["branches"])))
        if q == "stability" and len(sl["branches"]) == len(sc["branches"]):
            for i, (a, b) in enumerate(zip(sl["branches"], sc["branches"])):
                if a["stability"] != b["stability"]:
                    out.append(([sl["phi"], i], a["stability"], b["stability"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--recipes", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    results = []
    with tempfile.TemporaryDirectory() as td:
        for rp in sorted(Path(a.recipes).glob("*.json")):
            recipe = json.loads(rp.read_text(encoding="utf-8"))
            results.append((recipe, run(a.legacy, rp, Path(td) / "l.json"), run(a.program, rp, Path(td) / "c.json")))
    defects = []
    for q in ORDER:
        for recipe, leg, cor in results:
            cands = witnesses(q, recipe, leg, cor)
            if cands:
                sel, lv, cv = cands[0]
                defects.append(dict(description=DESCRIPTIONS[q], recipe=recipe, quantity=q, selector=sel,
                                    legacy_value=lv, correct_value=cv))
                break
    assert len(defects) >= 3, "too few witnesses found"
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump({"defects": defects}, fh, indent=1)
        fh.write("\n")
    print("diagnosis:", ", ".join(f"{d['quantity']}@{d['recipe']['recipe_id']}" for d in defects))


if __name__ == "__main__":
    main()
