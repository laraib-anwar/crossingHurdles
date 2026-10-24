"""Find executable witnesses of the legacy script's defects at run time.

Runs the legacy script and the corrected program on the shipped systems, compares the diagnosis
quantities of the spec, and writes diagnosis.json with one entry per defect. Nothing is stored.

usage: diagnose.py --program <lambert.py> --legacy <porkchop.py> --systems <dir> --output <diagnosis.json>
"""
import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DESCRIPTIONS = {
    "position": "Kepler's equation is solved by fixed-point iteration with a fixed number of sweeps, which converges "
                "too slowly for eccentric orbits and many periods from the epoch, so the position is wrong.",
    "theta": "The transfer angle is always taken the short way between the position vectors, so a prograde transfer "
             "through more than 180 degrees is reported with the wrong angle and solved on the wrong (retrograde) plane.",
    "solution_count": "Multi-revolution solutions are created from a resonant-orbit estimate whenever the time of flight "
                      "exceeds N + 1/2 Hohmann periods, instead of being solved; the number of solutions is wrong.",
    "t_min": "The minimum time of flight of the N-revolution family is set to N + 1/2 Hohmann periods between the two radii "
             "instead of the minimum over the family of transfer ellipses through both positions.",
    "best_dv": "The multi-revolution solutions are not real transfer arcs (they do not reach the arrival position) and the "
               "zero-revolution arc is the short-way one, so the minimum impulsive cost is wrong.",
}
ORDER = ["solution_count", "t_min", "theta", "best_dv", "position"]


def run(program, path, out_path):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    subprocess.run([sys.executable, str(program), "--system", str(path), "--output", str(out_path)],
                   check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    with open(out_path, encoding="utf-8") as fh:
        return json.load(fh)


def norm(v):
    return math.sqrt(sum(x * x for x in v))


def candidates(q, system, leg, cor):
    out = []
    if q == "position":
        for k, (a, b) in enumerate(zip(leg["ephemeris"], cor["ephemeris"])):
            la, cb = norm(a["r_km"]), norm(b["r_km"])
            if abs(la - cb) > 1e-4 * cb:
                out.append((k, la, cb))
        return out
    for k, (a, b) in enumerate(zip(leg["transfers"], cor["transfers"])):
        if q == "solution_count":
            if len(a["solutions"]) != len(b["solutions"]):
                out.append((k, len(a["solutions"]), len(b["solutions"])))
        elif q == "theta":
            if abs(a["theta_deg"] - b["theta_deg"]) > 1e-4 * b["theta_deg"]:
                out.append((k, a["theta_deg"], b["theta_deg"]))
        elif q == "t_min":
            if a["t_min_days"] and b["t_min_days"] and abs(a["t_min_days"][0] - b["t_min_days"][0]) > 1e-4 * b["t_min_days"][0]:
                out.append((k, a["t_min_days"][0], b["t_min_days"][0]))
        else:
            la, cb = a["solutions"][a["best"]]["dv_km_s"], b["solutions"][b["best"]]["dv_km_s"]
            if abs(la - cb) > 1e-4 * cb:
                out.append((k, la, cb))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--systems", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    results = []
    with tempfile.TemporaryDirectory() as td:
        for mp in sorted(Path(a.systems).glob("*.json")):
            system = json.loads(mp.read_text(encoding="utf-8"))
            results.append((system, run(a.legacy, mp, Path(td) / "l.json"), run(a.program, mp, Path(td) / "c.json")))
    defects = []
    for q in ORDER:
        for system, leg, cor in results:
            c = candidates(q, system, leg, cor)
            if c:
                k, lv, cv = c[0]
                defects.append(dict(description=DESCRIPTIONS[q], system=system, quantity=q, index=k,
                                    legacy_value=lv, correct_value=cv))
                break
    assert len(defects) >= 3, "too few witnesses found"
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump({"defects": defects}, fh, indent=1)
        fh.write("\n")
    print("diagnosis:", ", ".join(f"{d['quantity']}@{d['system']['system_id']}" for d in defects))


if __name__ == "__main__":
    main()
