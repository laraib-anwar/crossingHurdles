"""Find executable witnesses of the legacy script's defects at run time.

Runs the legacy script and the corrected program on the shipped recipes, compares every graded
quantity under the spec's tolerances, and writes diagnosis.json with one entry per defect,
each anchored to a recipe and a quantity on which the two disagree. Nothing is stored.

usage: diagnose.py --program <ixfront.py> --legacy <ixbreak.py> --recipes <dir> --output <diagnosis.json>
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TOL_BV_REL, TOL_BV_ABS, TOL_C = 2e-4, 1e-6, 1e-4
NIT = 1


def run(program, recipe_path, out_path):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    subprocess.run([sys.executable, str(program), "--recipe", str(recipe_path), "--output", str(out_path)],
                   check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    with open(out_path, encoding="utf-8") as fh:
        return json.load(fh)


def quantity(report, q, bv, recipe):
    if q == "shock_count":
        return len(report["shocks"])
    if q == "transition_count":
        return len(report["transitions"])
    if q == "nitrate_peak":
        return report["nitrate_peak"]["meq_per_L"]
    if q == "nitrate_limit_bv":
        return report["nitrate_limit_bv"]
    if q == "sample":
        return report["samples"][recipe["sample_bv"].index(bv)]
    raise ValueError(q)


def differ(q, a, b):
    if q in ("shock_count", "transition_count"):
        return a != b
    if q == "nitrate_limit_bv":
        if a is None or b is None:
            return (a is None) != (b is None)
        return abs(a - b) > max(TOL_BV_REL * abs(b), TOL_BV_ABS)
    if q == "nitrate_peak":
        return abs(a - b) > TOL_C
    if q == "sample":
        return any(abs(u - v) > TOL_C for u, v in zip(a, b))
    raise ValueError(q)


DESCRIPTIONS = {
    "transition_count": "Every front is treated as sharp. Unfavourable (desorbing) transitions spread into "
                        "continuous waves; the script reports none and misplaces the material they carry.",
    "shock_count": "Fronts are counted per ion from single-ion stoichiometry. The exact solution has one wave "
                   "per independent component with compositions fixed by the coherence (invariant) conditions, "
                   "so the number and positions of the discontinuities differ.",
    "nitrate_peak": "Plateau compositions are built ion by ion (ions whose front has passed sit at their feed "
                    "value), so the effluent can never exceed the influent. The exact solution displaces "
                    "weakly held nitrate above its feed concentration (chromatographic peaking).",
    "nitrate_limit_bv": "Because fronts are sharp and plateaus component-wise, the first exceedance of the "
                        "nitrate limit is placed at the wrong bed volume (or missed when it occurs inside a "
                        "spreading wave or on a rolled-up plateau).",
    "sample": "After a feed change the script superposes the new fronts on the old ones. Faster second-feed "
              "waves overtake and interact with first-feed waves, changing their positions and the "
              "compositions between them.",
}
ORDER = ["transition_count", "nitrate_peak", "sample", "shock_count", "nitrate_limit_bv"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--recipes", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    recipes = sorted(Path(args.recipes).glob("*.json"))
    found = {}
    with tempfile.TemporaryDirectory() as td:
        results = []
        for rp in recipes:
            recipe = json.loads(rp.read_text(encoding="utf-8"))
            leg = run(args.legacy, rp, Path(td) / "legacy.json")
            cor = run(args.program, rp, Path(td) / "correct.json")
            results.append((recipe, leg, cor))
        for q in ORDER:
            for recipe, leg, cor in results:
                if q == "sample":
                    # prefer a two-feed recipe, with a sample after the feed change
                    if len(recipe["feed_program"]) < 2:
                        continue
                    s = recipe["feed_program"][1]["start_bv"]
                    bvs = [b for b in recipe["sample_bv"] if b > s] or recipe["sample_bv"]
                    for bv in bvs:
                        a, b = quantity(leg, q, bv, recipe), quantity(cor, q, bv, recipe)
                        if differ(q, a, b):
                            found[q] = dict(recipe=recipe, bv=bv, legacy_value=a, correct_value=b)
                            break
                else:
                    a, b = quantity(leg, q, None, recipe), quantity(cor, q, None, recipe)
                    if differ(q, a, b):
                        found[q] = dict(recipe=recipe, bv=None, legacy_value=a, correct_value=b)
                if q in found:
                    break
        if "sample" not in found:                       # fall back to any recipe with a differing sample
            for recipe, leg, cor in results:
                for bv in recipe["sample_bv"]:
                    a, b = quantity(leg, "sample", bv, recipe), quantity(cor, "sample", bv, recipe)
                    if differ("sample", a, b):
                        found["sample"] = dict(recipe=recipe, bv=bv, legacy_value=a, correct_value=b)
                        break
                if "sample" in found:
                    break
    defects = [dict(description=DESCRIPTIONS[q], recipe=w["recipe"], quantity=q, bv=w["bv"],
                    legacy_value=w["legacy_value"], correct_value=w["correct_value"])
               for q, w in found.items()]
    assert len(defects) >= 3 and len({d["quantity"] for d in defects}) >= 3, "too few witnesses found"
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump({"defects": defects}, fh, indent=1)
        fh.write("\n")
    print(f"diagnosis: {len(defects)} witnesses: " + ", ".join(f"{d['quantity']}@{d['recipe']['recipe_id']}" for d in defects))


if __name__ == "__main__":
    main()
