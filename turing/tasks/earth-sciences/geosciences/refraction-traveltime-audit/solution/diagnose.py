"""Find executable witnesses of the legacy script's defects at run time.

Runs the legacy script and the corrected program on the shipped models, compares the diagnosis
quantities of the spec, and writes diagnosis.json with one entry per defect. Nothing is stored.

usage: diagnose.py --program <raytimes.py> --legacy <ttcurve.py> --models <dir> --output <diagnosis.json>
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TOL = 1e-9
DESCRIPTIONS = {
    "first_arrival_time": "Every layer is replaced by its mean velocity, so the turning waves of the gradient layers "
                          "are replaced by head waves and the first-arrival times are wrong wherever a layer has a gradient.",
    "arrival_count": "Reflections are kept only up to the critical angle, so post-critical (wide-angle) reflections are "
                     "missing, and turning waves do not exist in the constant-velocity stand-in; the number of arrivals "
                     "at an offset is wrong.",
    "first_arrival_count": "The first-arrival curve is the envelope of the direct and head-wave lines only; reflections and "
                           "turning waves that arrive first (in shadow zones below low-velocity layers, or from gradient "
                           "layers) are ignored, so the number of first-arrival intervals is wrong.",
    "caustic_count": "No caustics are computed: the turning and reflection branches of gradient zones fold back and "
                     "produce caustics (triplications) that a constant-velocity stand-in cannot have.",
}
ORDER = ["first_arrival_time", "arrival_count", "first_arrival_count", "caustic_count"]


def run(program, model_path, out_path):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    subprocess.run([sys.executable, str(program), "--model", str(model_path), "--output", str(out_path)],
                   check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    with open(out_path, encoding="utf-8") as fh:
        return json.load(fh)


def candidates(q, model, leg, cor):
    out = []
    if q == "caustic_count" and len(leg["caustics"]) != len(cor["caustics"]):
        out.append((None, len(leg["caustics"]), len(cor["caustics"])))
    if q == "first_arrival_count" and len(leg["first_arrival"]) != len(cor["first_arrival"]):
        out.append((None, len(leg["first_arrival"]), len(cor["first_arrival"])))
    for a, b in zip(leg["arrivals"], cor["arrivals"]):
        if q == "arrival_count" and len(a["rays"]) != len(b["rays"]):
            out.append((a["x_km"], len(a["rays"]), len(b["rays"])))
        if q == "first_arrival_time" and a["rays"] and b["rays"]:
            ta, tb = a["rays"][0]["t_s"], b["rays"][0]["t_s"]
            if abs(ta - tb) > TOL * abs(tb):
                out.append((a["x_km"], ta, tb))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--models", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    results = []
    with tempfile.TemporaryDirectory() as td:
        for mp in sorted(Path(a.models).glob("*.json")):
            model = json.loads(mp.read_text(encoding="utf-8"))
            results.append((model, run(a.legacy, mp, Path(td) / "l.json"), run(a.program, mp, Path(td) / "c.json")))
    defects = []
    for q in ORDER:
        for model, leg, cor in results:
            c = candidates(q, model, leg, cor)
            if c:
                x, lv, cv = c[0]
                defects.append(dict(description=DESCRIPTIONS[q], model=model, quantity=q, offset_km=x,
                                    legacy_value=lv, correct_value=cv))
                break
    assert len(defects) >= 3, "too few witnesses found"
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump({"defects": defects}, fh, indent=1)
        fh.write("\n")
    print("diagnosis:", ", ".join(f"{d['quantity']}@{d['model']['model_id']}" for d in defects))


if __name__ == "__main__":
    main()
