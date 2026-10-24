#!/usr/bin/env python3
"""In-domain stress structures for Ref B (no closed form; checked by the
double/long-double comparison, the tighter second run and the DOP853 cross-check)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SDIR = os.path.join(HERE, "structures")


def lead(m, v):
    return {"mass": m, "v_eV": v}


def layer(d, m, vl, vr=None):
    return {"thickness_nm": d, "mass": m, "vl_eV": vl, "vr_eV": vl if vr is None else vr}


def superlattice():
    L = [layer(2.4, 0.092, 0.31)]
    for _ in range(6):
        L += [layer(3.1, 0.067, 0.0), layer(2.4, 0.092, 0.31)]
    return L[:14]


STRESS = {
    # symmetric double well, 11 nm middle barrier: closely spaced doublets
    "stress_doublewell": {
        "left_lead": lead(0.092, 0.35), "right_lead": lead(0.092, 0.35),
        "layers": [layer(8.0, 0.092, 0.35), layer(6.0, 0.067, 0.0), layer(13.0, 0.092, 0.35),
                   layer(6.0, 0.067, 0.0), layer(8.0, 0.092, 0.35)],
        "transmission_energies_eV": [0.36, 0.38, 0.45, 0.6],
        "window_eV": [0.37, 0.61]},
    # thick high barrier, heavy mass: T down to ~1e-28
    "stress_thickbarrier": {
        "left_lead": lead(0.067, 0.0), "right_lead": lead(0.1, 0.05),
        "layers": [layer(4.0, 0.4, 1.6), layer(3.6, 0.4, 1.6)],
        "transmission_energies_eV": [0.06, 0.1, 0.3, 0.6, 1.0, 1.5],
        "window_eV": [1.62, 2.4]},
    # 6-period superlattice, 13 layers, many maxima across a 0.95 eV window
    "stress_superlattice": {
        "left_lead": lead(0.067, 0.0), "right_lead": lead(0.067, 0.0),
        "layers": superlattice(),
        "transmission_energies_eV": [0.05, 0.12, 0.2, 0.33, 0.5, 0.8, 1.0, 1.2],
        "window_eV": [0.33, 0.97]},
    # wide deep well with ~30+ bound states
    "stress_manylevels": {
        "left_lead": lead(0.15, 0.8), "right_lead": lead(0.17, 0.85),
        "layers": [layer(1.5, 0.15, 0.8), layer(14.0, 0.15, 0.0), layer(14.0, 0.15, 0.0),
                   layer(14.0, 0.15, 0.0), layer(14.0, 0.15, 0.0), layer(2.0, 0.17, 0.85)],
        "transmission_energies_eV": [0.86, 0.9, 1.1],
        "window_eV": [0.87, 1.3]},
    # 150 nm graded/biased structure with heavy masses and a high window: runtime stress
    "stress_graded150": {
        "left_lead": lead(0.9, 1.2), "right_lead": lead(0.6, -0.9),
        "layers": [layer(30.0, 1.0, 1.2, 0.6), layer(30.0, 0.8, 0.5, -0.4), layer(20.0, 0.067, -1.0, -1.0),
                   layer(30.0, 1.0, 1.9, 0.9), layer(25.0, 0.5, 0.2, -0.7), layer(15.0, 0.6, -0.9, -0.9)],
        "transmission_energies_eV": [1.7, 1.85, 2.0, 2.5],
        "window_eV": [1.95, 2.95]},
    # different lead masses and band edges, no bound state, narrow window without maximum
    "stress_nobound": {
        "left_lead": lead(0.03, 0.1), "right_lead": lead(0.9, -0.2),
        "layers": [layer(0.3, 0.5, 0.6), layer(1.2, 0.2, 0.15, 0.25)],
        "transmission_energies_eV": [0.101, 0.2, 0.7],
        "window_eV": [0.62, 0.63]},
}


def main():
    os.makedirs(SDIR, exist_ok=True)
    for sid, st in STRESS.items():
        obj = {"structure_id": sid}
        obj.update(st)
        with open(os.path.join(SDIR, sid + ".json"), "w") as fh:
            json.dump(obj, fh, indent=1)
            fh.write("\n")
        print("wrote", sid)


if __name__ == "__main__":
    main()
