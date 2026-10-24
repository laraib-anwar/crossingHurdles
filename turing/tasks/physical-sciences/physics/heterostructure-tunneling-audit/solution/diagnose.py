"""Find executable witnesses of the legacy script's defects at run time.

Runs the legacy script and the corrected program on the shipped structures, compares the
diagnosis quantities of the spec, and writes diagnosis.json with one entry per defect. Nothing
is stored.

usage: diagnose.py --program <hetero.py> --legacy <qwell.py> --structures <dir> --output <diagnosis.json>
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
    "bound_count": "Bound states come from finite differences on a box that ends 10 nm into each contact with hard walls, "
                   "with one effective mass everywhere: levels near the contact band edge are pushed up or lost and the "
                   "number of bound states is wrong.",
    "bound_energy": "The effective mass of the left contact is used in every layer (no BenDaniel-Duke boundary condition) "
                    "and the Laplacian is a three-point difference on a 0.1 nm grid, so the bound-state energies are wrong.",
    "transmission": "The transmission is |t|^2 without the ratio of the contact velocities k_R m_L / (k_L m_R), graded and "
                    "biased layers are replaced by five flat steps, and one mass is used throughout.",
    "maxima_count": "The transmission maxima are read off a 1 meV scan of the window with the approximate transmission, "
                    "so maxima are lost, added or shifted.",
    "maximum_energy": "Maxima are reported at the 1 meV grid points of the approximate transmission instead of the exact "
                      "stationary points of T(E).",
}
ORDER = ["bound_count", "transmission", "bound_energy", "maxima_count", "maximum_energy"]


def run(program, path, out_path):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    subprocess.run([sys.executable, str(program), "--structure", str(path), "--output", str(out_path)],
                   check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    with open(out_path, encoding="utf-8") as fh:
        return json.load(fh)


def finite(v):
    return isinstance(v, (int, float)) and math.isfinite(v)


def candidates(q, leg, cor):
    out = []
    if q == "bound_count":
        if len(leg["bound_states"]) != len(cor["bound_states"]):
            out.append((None, len(leg["bound_states"]), len(cor["bound_states"])))
    elif q == "maxima_count":
        if len(leg["maxima"]) != len(cor["maxima"]):
            out.append((None, len(leg["maxima"]), len(cor["maxima"])))
    elif q == "transmission":
        for k, (a, b) in enumerate(zip(leg["transmission"], cor["transmission"])):
            if finite(a["T"]) and abs(a["T"] - b["T"]) > 1e-4 * b["T"]:
                out.append((k, a["T"], b["T"]))
    else:
        key = "bound_states" if q == "bound_energy" else "maxima"
        for k, (a, b) in enumerate(zip(leg[key], cor[key])):
            if finite(a["E_eV"]) and abs(a["E_eV"] - b["E_eV"]) > 1e-4:
                out.append((k, a["E_eV"], b["E_eV"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--structures", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    results = []
    with tempfile.TemporaryDirectory() as td:
        for mp in sorted(Path(a.structures).glob("*.json")):
            structure = json.loads(mp.read_text(encoding="utf-8"))
            try:
                leg = run(a.legacy, mp, Path(td) / "l.json")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
                continue
            results.append((structure, leg, run(a.program, mp, Path(td) / "c.json")))
    defects = []
    for q in ORDER:
        for structure, leg, cor in results:
            c = candidates(q, leg, cor)
            if c:
                k, lv, cv = c[0]
                defects.append(dict(description=DESCRIPTIONS[q], structure=structure, quantity=q, index=k,
                                    legacy_value=lv, correct_value=cv))
                break
    assert len(defects) >= 3, "too few witnesses found"
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump({"defects": defects}, fh, indent=1)
        fh.write("\n")
    print("diagnosis:", ", ".join(f"{d['quantity']}@{d['structure']['structure_id']}" for d in defects))


if __name__ == "__main__":
    main()
