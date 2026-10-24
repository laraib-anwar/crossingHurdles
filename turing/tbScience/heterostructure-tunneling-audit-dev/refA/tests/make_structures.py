"""Writes the refA test structures (tests/structures/*.json). All are inside the HETERO_SPEC domain;
their guarantees are verified by run_checks.py (see NOTES.md)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "structures")


def lay(d, m, vl, vr=None):
    return {"thickness_nm": d, "mass": m, "vl_eV": vl, "vr_eV": vl if vr is None else vr}


def st(sid, left, right, layers, Eq, win):
    return {"structure_id": sid, "left_lead": {"mass": left[0], "v_eV": left[1]},
            "right_lead": {"mass": right[0], "v_eV": right[1]}, "layers": layers,
            "transmission_energies_eV": Eq, "window_eV": win}


S = []
# t1: single finite well (outer barriers identical to the leads) -> BDD even/odd equations
S.append(st("t1_single_well", (0.0919, 0.32), (0.0919, 0.32),
            [lay(6.0, 0.0919, 0.32), lay(9.4, 0.0665, 0.0), lay(6.0, 0.0919, 0.32)],
            [0.33, 0.41, 0.5, 0.75], [0.34, 0.9]))
# t2: symmetric double well, thick central barrier -> small splittings; closed form even/odd
S.append(st("t2_sym_double_well", (0.0919, 0.28), (0.0919, 0.28),
            [lay(5.0, 0.0919, 0.28), lay(6.5, 0.0665, 0.0), lay(13.0, 0.0919, 0.28),
             lay(6.5, 0.0665, 0.0), lay(5.0, 0.0919, 0.28)],
            [0.2815, 0.3, 0.45], [0.29, 0.52]))
# t3: biased triangular well against a high wall, many states; Airy closed form for low states
S.append(st("t3_triangular_bias", (0.5, 1.95), (0.4, 1.9),
            [lay(24.0, 0.35, 0.0, 1.2), lay(12.0, 0.35, 1.2, 1.8), lay(4.0, 0.4, 1.8)],
            [1.96, 1.98, 2.1], [1.97, 2.4]))
# t4: thick double barrier, T ~ 1e-25 off resonance; no bound state
S.append(st("t4_thick_double_barrier", (0.067, 0.0), (0.067, 0.0),
            [lay(3.0, 0.067, 0.0), lay(10.0, 0.092, 1.0), lay(5.0, 0.067, 0.0),
             lay(10.0, 0.092, 1.0), lay(3.0, 0.067, 0.0)],
            [0.012, 0.05, 0.1, 0.3, 0.6], [1.02, 1.3]))
# t5: superlattice, 6 periods, miniband bound states and several above-barrier maxima
S.append(st("t5_superlattice", (0.07, 0.15), (0.07, 0.15),
            [lay(2.0, 0.09, 0.3), lay(4.0, 0.067, 0.0)] * 6,
            [0.16, 0.25, 0.4, 0.7], [0.31, 0.75]))
# t6: graded layers, leads with different masses and band edges
S.append(st("t6_graded_leads", (0.067, 0.0), (0.13, 0.35),
            [lay(8.0, 0.08, 0.25, 0.05), lay(7.0, 0.06, -0.2), lay(5.0, 0.07, -0.1, 0.3),
             lay(4.0, 0.11, 0.45), lay(6.0, 0.12, 0.42, 0.36)],
            [0.36, 0.42, 0.55, 0.8], [0.47, 1.2]))
# t7: single rectangular barrier (two identical halves) -> closed-form T and maxima
S.append(st("t7_rect_barrier", (0.067, 0.0), (0.067, 0.0),
            [lay(3.5, 0.0919, 0.35), lay(3.5, 0.0919, 0.35)],
            [0.05, 0.2, 0.34, 0.36, 0.5, 0.9], [0.36, 1.2]))
# t8: thick high barrier, T down to ~1e-26 -> closed form
S.append(st("t8_thick_barrier", (0.067, 0.0), (0.067, 0.0),
            [lay(3.5, 0.5, 1.6), lay(3.5, 0.5, 1.6)],
            [0.15, 0.4, 0.8, 1.2], [1.62, 2.4]))
# t9: heavy-mass sloped layers with slope 1e-3 eV/nm: Airy arguments of several hundred
S.append(st("t9_large_airy", (0.9, 1.96), (1.0, 1.97),
            [lay(10.0, 1.0, 1.90, 1.91), lay(10.0, 1.0, -0.95, -0.94),
             lay(15.0, 0.95, 1.92, 1.905)],
            [1.975, 2.2, 2.6], [1.99, 2.5]))

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for s in S:
        with open(os.path.join(OUT, s["structure_id"] + ".json"), "w") as fh:
            json.dump(s, fh, indent=1)
            fh.write("\n")
    print(len(S), "structures written to", OUT)
