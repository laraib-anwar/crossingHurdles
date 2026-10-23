"""Find executable witnesses of the legacy script's defects at run time.

Runs the legacy script and the corrected program on the shipped neurons, compares the diagnosis
quantities of the spec, and writes diagnosis.json with one entry per defect. Nothing is stored.

usage: diagnose.py --program <cabletree.py> --legacy <cableprop.py> --neurons <dir> --output <diagnosis.json>
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DESCRIPTIONS = {
    "input_resistance": "The tree is collapsed to a Rall equivalent cylinder with sealed ends: killed and shunted terminals, "
                        "non-uniform membrane and the actual branching load at the site are lost, so the input resistance is wrong.",
    "attenuation": "Attenuation is the infinite-cable law exp(-X/lambda) of the electrotonic distance, which is symmetric and "
                   "ignores the boundary loads, so the directional steady-state attenuation factor is wrong.",
    "impedance_magnitude": "Transfer impedances are those of a lumped RC circuit (R_in, tau_m) scaled by the DC attenuation; the "
                           "frequency-dependent spread of the cable (complex length constant) is missing, so the magnitude is wrong.",
    "mode_count": "Equalization time constants are Rall's tau_m / (1 + (n pi / L_eq)^2) of one equivalent cylinder, so the "
                  "number of modes above tau_min (which depends on every branch and boundary) is wrong.",
    "tau": "The slowest mode is set to tau_m of the mean membrane and the others to the equivalent-cylinder values; the "
           "actual eigenvalues of the branched tree with its soma, shunts and killed ends differ.",
}
ORDER = ["mode_count", "tau", "attenuation", "input_resistance", "impedance_magnitude"]


def run(program, path, out_path):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    subprocess.run([sys.executable, str(program), "--neuron", str(path), "--output", str(out_path)],
                   check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    with open(out_path, encoding="utf-8") as fh:
        return json.load(fh)


def candidates(q, leg, cor):
    out = []
    if q == "mode_count":
        if len(leg["modes"]) != len(cor["modes"]):
            out.append((None, len(leg["modes"]), len(cor["modes"])))
    elif q == "tau":
        for k, (a, b) in enumerate(zip(leg["modes"], cor["modes"])):
            if abs(a["tau_ms"] - b["tau_ms"]) > 1e-4 * abs(b["tau_ms"]):
                out.append((k, a["tau_ms"], b["tau_ms"]))
    else:
        key, field = {"input_resistance": ("input_resistance", "R_MOhm"), "attenuation": ("attenuation", "factor"),
                      "impedance_magnitude": ("impedance", "magnitude_MOhm")}[q]
        for k, (a, b) in enumerate(zip(leg[key], cor[key])):
            if abs(a[field] - b[field]) > 1e-4 * abs(b[field]):
                out.append((k, a[field], b[field]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--neurons", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    results = []
    with tempfile.TemporaryDirectory() as td:
        for mp in sorted(Path(a.neurons).glob("*.json")):
            neuron = json.loads(mp.read_text(encoding="utf-8"))
            results.append((neuron, run(a.legacy, mp, Path(td) / "l.json"), run(a.program, mp, Path(td) / "c.json")))
    defects = []
    for q in ORDER:
        for neuron, leg, cor in results:
            c = candidates(q, leg, cor)
            if c:
                k, lv, cv = c[0]
                defects.append(dict(description=DESCRIPTIONS[q], neuron=neuron, quantity=q, index=k,
                                    legacy_value=lv, correct_value=cv))
                break
    assert len(defects) >= 3, "too few witnesses found"
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump({"defects": defects}, fh, indent=1)
        fh.write("\n")
    print("diagnosis:", ", ".join(f"{d['quantity']}@{d['neuron']['neuron_id']}" for d in defects))


if __name__ == "__main__":
    main()
