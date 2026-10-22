"""Find executable witnesses of the legacy script's defects at run time.

Runs the legacy script and the corrected program on the shipped systems, compares the diagnosis
quantities of the spec, and writes diagnosis.json with one entry per defect. Nothing is stored.

usage: diagnose.py --program <phasediagram.py> --legacy <tangentdiag.py> --systems <dir> --output <diagnosis.json>
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TOL = 1e-6
DESCRIPTIONS = {
    "tie_line_count": "Tie-lines are taken from pairwise common tangents checked only at their midpoint against the other "
                      "solution phases, never against the whole hull, so metastable tangents survive and compounds are "
                      "admitted or dropped by the mechanical-mixture line; the number of tie-lines at an isotherm is wrong.",
    "two_phase_fraction": "Miscibility gaps are bounded by the spinodal (zero second derivative) instead of the binodal "
                          "(common tangent), and metastable tangents replace the stable ones, so the total two-phase "
                          "extent at an isotherm is wrong.",
    "invariant_count": "Three-phase equilibria are read off changes of the pairwise tangent set on a 5 K scan: equilibria "
                       "between two states of one phase and a third phase are misread as congruent points, metastable "
                       "tangents create spurious changes and invariants involving compounds are missed, so the number "
                       "of invariants in the window is wrong.",
    "peritectic_count": "Every three-phase equilibrium is classified eutectic-type (eutectic if the liquid takes part, "
                        "eutectoid otherwise); the stability of the middle phase above or below the invariant "
                        "temperature is never examined, so peritectic-class reactions are never found.",
    "critical_count": "Consolute points come from the regular-solution formula T_c = L0/(2R) at x = 1/2 for every phase "
                      "with a positive L0, whether or not the gap is stable, without the asymmetric and temperature "
                      "terms, so the number of critical points in the window is wrong.",
}
ORDER = ["peritectic_count", "critical_count", "invariant_count", "tie_line_count", "two_phase_fraction"]


def run(program, system_path, out_path):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    subprocess.run([sys.executable, str(program), "--system", str(system_path), "--output", str(out_path)],
                   check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    with open(out_path, encoding="utf-8") as fh:
        return json.load(fh)


def quantity(rep, q, T):
    if q == "invariant_count":
        return len(rep["invariants"])
    if q == "peritectic_count":
        return sum(1 for e in rep["invariants"] if e["class"] == "peritectic")
    if q == "critical_count":
        return len(rep["critical_points"])
    iso = next(it for it in rep["isotherms"] if it["temperature_K"] == T)
    if q == "tie_line_count":
        return len(iso["tie_lines"])
    return sum(t["x_right"] - t["x_left"] for t in iso["tie_lines"])


def candidates(q, system, leg, cor):
    out = []
    Ts = system["isotherms_K"] if q in ("tie_line_count", "two_phase_fraction") else [None]
    for T in Ts:
        try:
            lv, cv = quantity(leg, q, T), quantity(cor, q, T)
        except StopIteration:
            continue
        if q == "two_phase_fraction":
            if abs(lv - cv) > 10 * TOL:
                out.append((T, lv, cv))
        elif lv != cv:
            out.append((T, lv, cv))
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
                T, lv, cv = c[0]
                defects.append(dict(description=DESCRIPTIONS[q], system=system, quantity=q, temperature_K=T,
                                    legacy_value=lv, correct_value=cv))
                break
    assert len(defects) >= 3, "too few witnesses found"
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump({"defects": defects}, fh, indent=1)
        fh.write("\n")
    print("diagnosis:", ", ".join(f"{d['quantity']}@{d['system']['system_id']}" for d in defects))


if __name__ == "__main__":
    main()
