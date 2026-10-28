"""Find executable witnesses of the legacy script's defects at run time.

Runs the legacy script and the corrected program on the shipped frames, compares the diagnosis
quantities of the spec, and writes diagnosis.json with one entry per defect. Nothing is stored.

usage: diagnose.py --program <framedyn.py> --legacy <framefreq.py> --frames <dir> --output <diagnosis.json>
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
    "frequency": "One cubic finite element per member with the member mass lumped at its ends cannot represent the "
                 "distributed-mass vibration of the members: the natural frequencies are off by percent and the modes of "
                 "members between fixed nodes are missing.",
    "count_below": "The lumped-mass model has as many frequencies as translational degrees of freedom and none of the "
                   "member-local modes, so the number of natural frequencies below a limit is wrong.",
    "static": "Uniform member loads are replaced by half the load at each end without the fixed-end moments, so the "
              "rotations and displacements of the loaded members' nodes are wrong.",
    "harmonic": "The harmonic response is computed with the lumped single-element model (K - omega^2 M) instead of the "
                "exact distributed-mass dynamic stiffness, so the amplitude is wrong.",
}
ORDER = ["count_below", "frequency", "static", "harmonic"]


def run(program, path, out_path):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    subprocess.run([sys.executable, str(program), "--frame", str(path), "--output", str(out_path)],
                   check=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
    with open(out_path, encoding="utf-8") as fh:
        return json.load(fh)


def candidates(q, frame, leg, cor):
    out = []
    if q == "count_below":
        if leg["count_below"] != cor["count_below"]:
            out.append((None, leg["count_below"], cor["count_below"]))
    elif q == "frequency":
        for k, (a, b) in enumerate(zip(leg["frequencies_Hz"], cor["frequencies_Hz"])):
            if abs(a - b) > 1e-4 * b:
                out.append((k, a, b))
    elif q == "static":
        tr = max([abs(s[d]) for s in cor["static"] for d in ("ux", "uy")] or [0])
        ro = max([abs(s["rz"]) for s in cor["static"]] or [0])
        for k, (a, b) in enumerate(zip(leg["static"], cor["static"])):
            for d in ("ux", "uy", "rz"):
                S = ro if d == "rz" else tr
                if abs(a[d] - b[d]) > 1e-4 * max(abs(b[d]), S):
                    out.append((dict(query=k, dof=d), a[d], b[d]))
    else:
        ht = max([abs(h["U"]) for h in cor["harmonic"] if h["response_dof"] != "rz"] or [0])
        hr = max([abs(h["U"]) for h in cor["harmonic"] if h["response_dof"] == "rz"] or [0])
        for k, (a, b) in enumerate(zip(leg["harmonic"], cor["harmonic"])):
            S = hr if b["response_dof"] == "rz" else ht
            if abs(a["U"] - b["U"]) > 1e-4 * max(abs(b["U"]), S):
                out.append((k, a["U"], b["U"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--program", required=True)
    ap.add_argument("--legacy", required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    results = []
    with tempfile.TemporaryDirectory() as td:
        for mp in sorted(Path(a.frames).glob("*.json")):
            frame = json.loads(mp.read_text(encoding="utf-8"))
            try:
                leg = run(a.legacy, mp, Path(td) / "l.json")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
                continue
            results.append((frame, leg, run(a.program, mp, Path(td) / "c.json")))
    defects = []
    for q in ORDER:
        for frame, leg, cor in results:
            c = candidates(q, frame, leg, cor)
            if c:
                k, lv, cv = c[0]
                defects.append(dict(description=DESCRIPTIONS[q], frame=frame, quantity=q, index=k,
                                    legacy_value=lv, correct_value=cv))
                break
    assert len(defects) >= 3, "too few witnesses found"
    with open(a.output, "w", encoding="utf-8") as fh:
        json.dump({"defects": defects}, fh, indent=1)
        fh.write("\n")
    print("diagnosis:", ", ".join(f"{d['quantity']}@{d['frame']['frame_id']}" for d in defects))


if __name__ == "__main__":
    main()
