"""Writes the test neurons of refA/tests (run from anywhere; writes next to itself)."""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def seg(i, parent, L, d, Rm, Ri, Cm, end=None):
    if end is None:
        e = None
    elif end == "sealed" or end == "killed":
        e = {"type": end, "g_nS": None}
    else:
        e = {"type": "shunt", "g_nS": float(end)}
    return {"id": i, "parent": parent, "L_um": L, "d_um": d, "Rm_ohm_cm2": Rm,
            "Ri_ohm_cm": Ri, "Cm_uF_cm2": Cm, "end": e}


def loc(s, f):
    return {"segment": s, "fraction": f}


def pair(a, b):
    return {"source": a, "target": b}


def imp(a, b, f):
    return {"source": a, "target": b, "frequency_Hz": f}


def write(name, soma, segments, rin, att, imps, tau_min):
    obj = {"neuron_id": name, "soma": soma, "segments": segments,
           "input_resistance_sites": rin, "attenuation_pairs": att,
           "impedance_queries": imps, "tau_min_ms": tau_min}
    with open(os.path.join(HERE, name + ".json"), "w") as fh:
        json.dump(obj, fh, indent=1)
        fh.write("\n")


tiny_soma = {"d_um": 8, "Rm_ohm_cm2": 60000, "Cm_uF_cm2": 0.6, "shunt_nS": 0}

# 1. unbranched sealed cable (3 identical segments in a chain), negligible soma
S = loc(0, 0)
write("cable_sealed", tiny_soma,
      [seg(1, 0, 200, 2, 20000, 100, 1.0), seg(2, 1, 200, 2, 20000, 100, 1.0),
       seg(3, 2, 200, 2, 20000, 100, 1.0, "sealed")],
      [S, loc(3, 1), loc(2, 0.5), loc(1, 0.001)],
      [pair(S, loc(3, 1)), pair(loc(3, 1), S), pair(loc(1, 0.25), loc(3, 0.75)), pair(S, loc(1, 0.001))],
      [imp(S, S, 10), imp(S, loc(2, 0.5), 100), imp(loc(2, 0.5), S, 100), imp(loc(3, 1), S, 2000),
       imp(S, loc(3, 1), 2000), imp(S, S, 1)],
      0.1)

# 2. unbranched killed cable, non-identical segment lengths, negligible soma
write("cable_killed", tiny_soma,
      [seg(1, 0, 150, 1.5, 30000, 150, 0.8), seg(2, 1, 250, 1.5, 30000, 150, 0.8),
       seg(3, 2, 200, 1.5, 30000, 150, 0.8, "killed")],
      [S, loc(2, 0.5), loc(3, 0.9)],
      [pair(S, loc(2, 0.5)), pair(loc(2, 0.5), S), pair(S, loc(3, 0.9))],
      [imp(S, S, 50), imp(S, loc(3, 0.9), 500), imp(loc(3, 0.9), S, 500), imp(loc(2, 0.5), loc(2, 0.5), 2000)],
      0.15)

# 3. Rall bifurcation, exact (equivalent cylinder holds; children differ in d and L but share the
#    electrotonic length, so hidden modes exist -> violates guarantee 2; DC/AC checks only)
d0, d1 = 4.0, 3.0
d2 = (d0 ** 1.5 - d1 ** 1.5) ** (2.0 / 3.0)
L1 = 200.0
L2 = L1 * math.sqrt(d2 / d1)
rall_soma = {"d_um": 15, "Rm_ohm_cm2": 20000, "Cm_uF_cm2": 1.0, "shunt_nS": 0}
write("rall_exact", rall_soma,
      [seg(1, 0, 150, d0, 20000, 100, 1.0), seg(2, 1, L1, d1, 20000, 100, 1.0, "sealed"),
       seg(3, 1, L2, d2, 20000, 100, 1.0, "sealed")],
      [S, loc(1, 1), loc(2, 1), loc(3, 1)],
      [pair(S, loc(2, 1)), pair(S, loc(3, 1)), pair(loc(2, 1), S), pair(loc(1, 1), loc(2, 0.5))],
      [imp(S, S, 100), imp(S, loc(2, 1), 300), imp(S, loc(3, 1), 300), imp(loc(2, 1), loc(3, 1), 1000),
       imp(loc(3, 1), loc(2, 1), 1000)],
      0.2)

# 3b. same tree with the second child 1 % longer (in the guarantees)
write("rall_perturbed", rall_soma,
      [seg(1, 0, 150, d0, 20000, 100, 1.0), seg(2, 1, L1, d1, 20000, 100, 1.0, "sealed"),
       seg(3, 1, 1.01 * L2, d2, 20000, 100, 1.0, "sealed")],
      [S, loc(1, 1), loc(2, 1), loc(3, 1)],
      [pair(S, loc(2, 1)), pair(S, loc(3, 1)), pair(loc(2, 1), S), pair(loc(1, 1), loc(2, 0.5))],
      [imp(S, S, 100), imp(S, loc(2, 1), 300), imp(S, loc(3, 1), 300), imp(loc(2, 1), loc(3, 1), 1000),
       imp(loc(3, 1), loc(2, 1), 1000)],
      0.2)

# 4. shunted terminal next to a sealed one, non-uniform membrane
write("shunt_terminal", {"d_um": 20, "Rm_ohm_cm2": 15000, "Cm_uF_cm2": 1.0, "shunt_nS": 3},
      [seg(1, 0, 120, 3.0, 20000, 120, 1.0), seg(2, 1, 300, 1.2, 40000, 120, 0.9, 6.0),
       seg(3, 1, 180, 2.0, 12000, 120, 1.2), seg(4, 3, 350, 1.0, 25000, 120, 1.0, "sealed")],
      [S, loc(2, 1), loc(4, 1), loc(2, 0.5)],
      [pair(S, loc(2, 1)), pair(loc(2, 1), S), pair(loc(4, 1), loc(2, 1)), pair(loc(2, 1), loc(4, 1))],
      [imp(S, loc(2, 1), 20), imp(loc(2, 1), S, 20), imp(loc(4, 1), loc(2, 0.5), 2000),
       imp(loc(2, 0.5), loc(4, 1), 2000), imp(S, S, 1)],
      0.3)

# 5. nearly symmetric bifurcation: child 3 is 0.3 % longer than child 2 -> nearly hidden modes
write("near_symmetric", {"d_um": 12, "Rm_ohm_cm2": 30000, "Cm_uF_cm2": 1.0, "shunt_nS": 0},
      [seg(1, 0, 100, 2.5, 25000, 100, 1.0), seg(2, 1, 400, 1.5, 25000, 100, 1.0, "sealed"),
       seg(3, 1, 401.2, 1.5, 25000, 100, 1.0, "sealed")],
      [S, loc(2, 1), loc(3, 1)],
      [pair(S, loc(2, 1)), pair(loc(2, 1), loc(3, 1)), pair(loc(3, 1), loc(2, 1))],
      [imp(S, S, 10), imp(loc(2, 1), loc(3, 1), 200), imp(loc(3, 1), loc(2, 1), 200)],
      0.1)

# 6. ten-segment tree, three branch orders, all terminal types, non-uniform Rm/Cm, many modes
write("tree10", {"d_um": 25, "Rm_ohm_cm2": 20000, "Cm_uF_cm2": 1.0, "shunt_nS": 2},
      [seg(1, 0, 90, 4.0, 20000, 100, 1.0),
       seg(2, 1, 210, 2.2, 30000, 100, 1.0),
       seg(3, 1, 160, 2.6, 20000, 150, 1.3),
       seg(4, 2, 380, 1.1, 45000, 100, 0.8, "sealed"),
       seg(5, 2, 290, 1.4, 30000, 100, 1.0, "killed"),
       seg(6, 3, 240, 1.7, 20000, 150, 1.3),
       seg(7, 3, 330, 0.9, 25000, 150, 1.0, 4.0),
       seg(8, 6, 500, 0.8, 50000, 150, 1.0, "sealed"),
       seg(9, 6, 420, 1.0, 35000, 150, 1.5, "sealed"),
       seg(10, 1, 600, 0.6, 60000, 70, 2.0, "sealed")],
      [S, loc(4, 1), loc(8, 1), loc(10, 1), loc(5, 0.5), loc(7, 0.3)],
      [pair(S, loc(8, 1)), pair(loc(8, 1), S), pair(loc(4, 1), loc(9, 1)), pair(loc(9, 1), loc(4, 1)),
       pair(loc(10, 1), loc(5, 0.5)), pair(loc(6, 0), loc(6, 1))],
      [imp(S, S, 1), imp(S, loc(8, 1), 500), imp(loc(8, 1), S, 500), imp(loc(4, 1), loc(10, 1), 2000),
       imp(loc(10, 1), loc(4, 1), 2000), imp(loc(7, 0.3), loc(7, 0.3), 50)],
      0.12)

# 7. twelve-segment tree with a dominant soma, coincident query locations, fractions 0 and 1
write("tree12_soma", {"d_um": 40, "Rm_ohm_cm2": 2000, "Cm_uF_cm2": 2.0, "shunt_nS": 20},
      [seg(1, 0, 60, 5.0, 10000, 200, 1.0),
       seg(2, 0, 80, 3.0, 12000, 200, 1.0),
       seg(3, 1, 200, 3.0, 10000, 200, 1.0),
       seg(4, 1, 150, 2.0, 10000, 200, 1.0, "sealed"),
       seg(5, 3, 300, 1.5, 15000, 200, 1.0, "sealed"),
       seg(6, 3, 250, 1.8, 15000, 200, 1.0),
       seg(7, 6, 400, 1.0, 20000, 200, 1.0, "sealed"),
       seg(8, 6, 350, 1.2, 20000, 200, 1.0, 10.0),
       seg(9, 2, 300, 2.0, 12000, 200, 1.0),
       seg(10, 9, 200, 1.0, 12000, 200, 1.0, "killed"),
       seg(11, 9, 450, 1.3, 12000, 200, 1.0, "sealed"),
       seg(12, 2, 500, 0.7, 8000, 200, 1.0, "sealed")],
      [S, loc(1, 0), loc(3, 0), loc(7, 1), loc(10, 0.5), loc(12, 1), loc(11, 0.75)],
      [pair(S, loc(1, 0)), pair(loc(7, 1), loc(7, 1)), pair(S, loc(7, 1)), pair(loc(7, 1), S),
       pair(loc(12, 1), loc(11, 0.75)), pair(loc(10, 0.5), loc(11, 1))],
      [imp(S, S, 2000), imp(loc(7, 1), loc(7, 1), 1), imp(loc(12, 1), S, 100), imp(S, loc(12, 1), 100),
       imp(loc(4, 1), loc(8, 1), 1500), imp(loc(8, 1), loc(4, 1), 1500)],
      0.5)
print("written")
