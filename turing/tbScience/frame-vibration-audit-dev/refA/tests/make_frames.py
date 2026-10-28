#!/usr/bin/env python3
"""Writes the Reference A test frames to tests/frames/ (all inside the FRAME_SPEC domain)."""
import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "frames")


def node(i, x, y, m=0.0, ux=False, uy=False, rz=False):
    return {"id": i, "x": x, "y": y, "mass_kg": m, "support": {"ux": ux, "uy": uy, "rz": rz}}


def fixed(i, x, y, m=0.0):
    return node(i, x, y, m, True, True, True)


def mem(i, a, b, E, A, I, rho):
    return {"id": i, "i": a, "j": b, "E": E, "A": A, "I": I, "rho": rho}


def nl(n, fx=0.0, fy=0.0, mz=0.0):
    return {"node": n, "Fx": fx, "Fy": fy, "Mz": mz}


def ml(k, wx=0.0, wy=0.0):
    return {"member": k, "wx": wx, "wy": wy}


def hq(ln, ld, amp, f, rn, rd):
    return {"load_node": ln, "load_dof": ld, "amplitude": amp, "f_Hz": f,
            "response_node": rn, "response_dof": rd}


def frame(fid, nodes, members, nloads, mloads, sq, n_modes, fmax, harm):
    return {"frame_id": fid, "nodes": nodes, "members": members, "nodal_loads": nloads,
            "member_loads": mloads, "static_query_nodes": sq, "n_modes": n_modes,
            "f_max_Hz": fmax, "harmonic_queries": harm}


STEEL = dict(E=2.05e11, rho=7850.0)
CONC = dict(E=3.1e10, rho=2450.0)


def t1_cantilever3():
    # three collinear members along a 30 degree line, clamped at node 1; s = 0, 1.55, 3.05, 4.7
    th = math.radians(30.0)
    c, s = math.cos(th), math.sin(th)
    ss = [0.0, 1.55, 3.05, 4.7]
    nodes = [fixed(1, 0.0, 0.0)] + [node(k + 1, ss[k] * c, ss[k] * s) for k in range(1, 4)]
    A, I = 5.38e-3, 3.69e-5
    members = [mem(k, k, k + 1, STEEL["E"], A, I, STEEL["rho"]) for k in (1, 2, 3)]
    P, Nax, q = 18500.0, 240000.0, 2650.0
    # tip: transverse force P (perpendicular, +normal) and axial pull Nax; uniform transverse q
    nloads = [nl(4, Nax * c - P * s, Nax * s + P * c, 0.0)]
    mloads = [ml(k, -q * s, q * c) for k in (1, 2, 3)]
    harm = [hq(4, "uy", 1000.0, 23.7, 4, "uy"), hq(4, "ux", 1000.0, 23.7, 4, "uy")]
    return frame("t1_cantilever3", nodes, members, nloads, mloads, [2, 3, 4], 8, 260.0, harm)


def t2_ssbeam():
    # pin at node 1, roller at node 3, interior node 2 at a = 2.9 (span 6.3)
    nodes = [node(1, 0.0, 0.0, 0.0, True, True, False), node(2, 2.9, 0.0),
             node(3, 6.3, 0.0, 0.0, False, True, False)]
    A, I = 7.64e-3, 1.42e-4
    members = [mem(1, 1, 2, STEEL["E"], A, I, STEEL["rho"]),
               mem(2, 2, 3, STEEL["E"], A, I, STEEL["rho"])]
    nloads = [nl(2, 0.0, -36500.0, 0.0), nl(3, 61000.0, 0.0, 0.0)]
    mloads = [ml(1, 0.0, -4180.0), ml(2, 0.0, -4180.0)]
    harm = [hq(2, "uy", 2500.0, 11.3, 2, "uy"), hq(2, "uy", 2500.0, 61.9, 1, "rz")]
    return frame("t2_ssbeam", nodes, members, nloads, mloads, [2], 7, 330.0, harm)


def t3_portal():
    nodes = [fixed(1, 0.0, 0.0), node(2, 0.0, 4.15), node(3, 7.35, 4.15), fixed(4, 7.35, 0.0)]
    col = dict(A=9.12e-3, I=1.71e-4)
    beam = dict(A=7.03e-3, I=2.33e-4)
    members = [mem(1, 1, 2, STEEL["E"], col["A"], col["I"], STEEL["rho"]),
               mem(2, 2, 3, STEEL["E"], beam["A"], beam["I"], STEEL["rho"]),
               mem(3, 4, 3, STEEL["E"], col["A"], col["I"], STEEL["rho"])]
    nloads = [nl(2, 42700.0, 0.0, 0.0), nl(3, 0.0, -15200.0, 6100.0)]
    mloads = [ml(2, 0.0, -18300.0), ml(1, 3150.0, 0.0)]
    harm = [hq(2, "ux", 5000.0, 3.37, 3, "ux"), hq(3, "ux", 5000.0, 3.37, 2, "ux"),
            hq(2, "rz", 2000.0, 41.3, 3, "uy"), hq(3, "uy", 2000.0, 41.3, 2, "rz")]
    return frame("t3_portal", nodes, members, nloads, mloads, [2, 3], 10, 120.0, harm)


def t4_fixedfixed():
    # member 1 joins two fully fixed supports (member-local modes); a stocky cantilever column
    # (member 2) and an inclined strut (member 3) make up the rest of the frame
    nodes = [fixed(1, 0.0, 0.0), fixed(2, 11.6, 0.0), node(3, 0.0, 2.35, 850.0),
             node(4, 3.05, 3.4)]
    members = [mem(1, 1, 2, STEEL["E"], 1.84e-3, 2.9e-6, STEEL["rho"]),
               mem(2, 1, 3, STEEL["E"], 3.6e-2, 2.7e-3, STEEL["rho"]),
               mem(3, 3, 4, STEEL["E"], 2.1e-2, 1.6e-3, STEEL["rho"])]
    nloads = [nl(4, 12500.0, -48000.0, 3300.0)]
    mloads = [ml(1, 0.0, -1450.0), ml(3, 900.0, -2200.0)]
    harm = [hq(4, "uy", 3000.0, 57.4, 3, "ux")]
    return frame("t4_fixedfixed", nodes, members, nloads, mloads, [3, 4], 12, 140.0, harm)


def t5_closepair():
    # two-bay portal, short stocky columns and identical slender beams: beam modes come in
    # pairs split only by the weak coupling at the middle joint and a 0.03 mm bay difference
    H = 1.6
    nodes = [fixed(1, 0.0, 0.0), fixed(2, 9.0, 0.0), fixed(3, 18.00003, 0.0),
             node(4, 0.0, H), node(5, 9.0, H), node(6, 18.00003, H)]
    col = dict(A=5.0e-2, I=5.0e-3)
    beam = dict(A=1.2e-3, I=4.0e-7)
    members = [mem(1, 1, 4, CONC["E"], col["A"], col["I"], CONC["rho"]),
               mem(2, 2, 5, CONC["E"], col["A"], col["I"], CONC["rho"]),
               mem(3, 3, 6, CONC["E"], col["A"], col["I"], CONC["rho"]),
               mem(4, 4, 5, STEEL["E"], beam["A"], beam["I"], STEEL["rho"]),
               mem(5, 5, 6, STEEL["E"], beam["A"], beam["I"], STEEL["rho"])]
    nloads = [nl(4, 8800.0, 0.0, 0.0)]
    mloads = [ml(4, 0.0, -260.0), ml(5, 0.0, -260.0)]
    harm = [hq(5, "uy", 1500.0, 7.31, 4, "rz")]
    return frame("t5_closepair", nodes, members, nloads, mloads, [4, 5, 6], 8, 30.0, harm)


def t6_masses():
    # two-storey, one-bay frame with lumped floor masses; harmonic queries below and above the
    # first frequency, arranged in reciprocal pairs
    nodes = [fixed(1, 0.0, 0.0), fixed(2, 5.4, 0.0),
             node(3, 0.0, 3.3, 6200.0), node(4, 5.4, 3.3, 5750.0),
             node(5, 0.0, 6.45, 4100.0), node(6, 5.4, 6.45, 3890.0)]
    col = dict(A=1.06e-2, I=1.42e-4)
    bm = dict(A=6.26e-3, I=1.61e-4)
    members = [mem(1, 1, 3, STEEL["E"], col["A"], col["I"], STEEL["rho"]),
               mem(2, 2, 4, STEEL["E"], col["A"], col["I"], STEEL["rho"]),
               mem(3, 3, 5, STEEL["E"], col["A"], col["I"], STEEL["rho"]),
               mem(4, 4, 6, STEEL["E"], col["A"], col["I"], STEEL["rho"]),
               mem(5, 3, 4, STEEL["E"], bm["A"], bm["I"], STEEL["rho"]),
               mem(6, 5, 6, STEEL["E"], bm["A"], bm["I"], STEEL["rho"])]
    nloads = [nl(5, 21000.0, 0.0, 0.0), nl(3, 13500.0, 0.0, 0.0)]
    mloads = [ml(5, 0.0, -9700.0), ml(6, 0.0, -7300.0)]
    harm = [hq(5, "ux", 4000.0, 1.21, 4, "uy"), hq(4, "uy", 4000.0, 1.21, 5, "ux"),
            hq(3, "rz", 2500.0, 7.93, 6, "ux"), hq(6, "ux", 2500.0, 7.93, 3, "rz")]
    return frame("t6_masses", nodes, members, nloads, mloads, [3, 4, 5, 6], 9, 40.0, harm)


def t7_slender_stocky():
    # inclined slender tie (L/r about 970) beside a stocky short concrete post: stiff/soft contrast
    nodes = [fixed(1, 0.0, 0.0), node(2, 0.0, 1.1), node(3, 8.3, 5.05, 1200.0),
             node(4, 8.3, 0.0, 0.0, True, True, False)]
    members = [mem(1, 1, 2, CONC["E"], 4.9e-2, 4.6e-3, CONC["rho"]),
               mem(2, 2, 3, STEEL["E"], 1.13e-3, 1.0e-7 * 1.017, STEEL["rho"]),
               mem(3, 4, 3, STEEL["E"], 3.34e-3, 1.92e-5, STEEL["rho"])]
    nloads = [nl(3, 7400.0, -26000.0, 0.0), nl(2, 0.0, 0.0, -2900.0)]
    mloads = [ml(2, 0.0, -110.0)]
    harm = [hq(3, "uy", 1000.0, 2.93, 2, "rz"), hq(2, "rz", 1000.0, 2.93, 3, "uy")]
    return frame("t7_slender_stocky", nodes, members, nloads, mloads, [2, 3], 6, 55.0, harm)


def t8_local40():
    # member-local modes only up to f_max: a slender member between two fixed supports
    # (bending parameter about 39.4 at f_max) and two short fixed-fixed members whose lengths
    # differ by 2e-6 relative (pairs 4e-6 apart); a stocky column with a strut carries the
    # static and harmonic queries and has its own modes above f_max
    nodes = [fixed(1, 0.0, 0.0), fixed(2, 14.2, 0.0), fixed(3, 2.0, 3.0), fixed(4, 5.1, 3.0),
             fixed(5, 2.0, 4.5), fixed(6, 5.1000062, 4.5), node(7, 0.0, 1.25),
             node(8, 0.9, 1.25)]
    members = [mem(1, 1, 2, STEEL["E"], 1.2e-3, 1.6e-6, STEEL["rho"]),
               mem(2, 3, 4, STEEL["E"], 1.2e-3, 1.6e-6, STEEL["rho"]),
               mem(3, 5, 6, STEEL["E"], 1.2e-3, 1.6e-6, STEEL["rho"]),
               mem(4, 1, 7, STEEL["E"], 5.0e-2, 5.0e-3, STEEL["rho"]),
               mem(5, 7, 8, STEEL["E"], 3.0e-2, 2.5e-3, STEEL["rho"])]
    nloads = [nl(8, 35000.0, -120000.0, 8000.0)]
    mloads = [ml(1, 0.0, -350.0), ml(5, 0.0, -6400.0)]
    harm = [hq(8, "uy", 10000.0, 96.3, 7, "ux")]
    return frame("t8_local40", nodes, members, nloads, mloads, [7, 8], 12, 228.0, harm)


def t9_stress16():
    # largest size in the domain: 12 nodes, 16 members (3 bays x 2 storeys with two braces),
    # slender members and f_max close to the bending-parameter limit (runtime stress)
    xs = [0.0, 6.35, 12.4, 18.9]
    ys = [0.0, 3.9, 7.45]
    nodes = []
    for r, y in enumerate(ys):
        for c_, x in enumerate(xs):
            i = 4 * r + c_ + 1
            if r == 0:
                nodes.append(fixed(i, x, y))
            else:
                nodes.append(node(i, x + 0.013 * r * c_, y, 2100.0 if r == 2 else 0.0))
    col = dict(A=5.7e-3, I=4.95e-5)
    bm = dict(A=4.1e-3, I=2.27e-5)
    br = dict(A=1.9e-3, I=1.0e-7)
    members = []
    k = 0
    for r in range(2):
        for c_ in range(4):
            k += 1
            members.append(mem(k, 4 * r + c_ + 1, 4 * (r + 1) + c_ + 1, STEEL["E"], col["A"], col["I"],
                               STEEL["rho"]))
    for r in (1, 2):
        for c_ in range(3):
            k += 1
            members.append(mem(k, 4 * r + c_ + 1, 4 * r + c_ + 2, STEEL["E"], bm["A"], bm["I"],
                               STEEL["rho"]))
    members.append(mem(15, 1, 6, STEEL["E"], br["A"], br["I"], STEEL["rho"]))
    members.append(mem(16, 4, 7, STEEL["E"], br["A"], br["I"], STEEL["rho"]))
    nloads = [nl(9, 31000.0, 0.0, 0.0), nl(5, 17500.0, 0.0, 0.0), nl(11, 0.0, -42000.0, 0.0)]
    mloads = [ml(9, 0.0, -11800.0), ml(10, 0.0, -11800.0), ml(12, 0.0, -6900.0)]
    harm = [hq(9, "ux", 5000.0, 2.25, 12, "ux"), hq(12, "ux", 5000.0, 2.25, 9, "ux"),
            hq(10, "uy", 2000.0, 61.7, 6, "rz"), hq(7, "uy", 2000.0, 118.3, 11, "uy")]
    return frame("t9_stress16", nodes, members, nloads, mloads, [5, 6, 9, 10, 11, 12], 12, 161.0, harm)


def t10_extreme():
    # domain corner: a 19.7 m member with A = 5e-2 and I = 1e-7 (L/r about 14000, axial to
    # bending stiffness ratio about 1e7) on a stocky column; roller at the far end
    nodes = [fixed(1, 0.0, 0.0), node(2, 0.0, 3.0), node(3, 19.7, 3.4, 0.0, False, True, False)]
    members = [mem(1, 1, 2, STEEL["E"], 2.0e-2, 1.2e-4, STEEL["rho"]),
               mem(2, 2, 3, STEEL["E"], 5.0e-2, 1.0e-7, STEEL["rho"])]
    nloads = [nl(2, 15000.0, -8000.0, 1200.0)]
    mloads = [ml(2, 0.0, -50.0)]
    harm = [hq(2, "ux", 1000.0, 0.37, 3, "rz"), hq(3, "rz", 1000.0, 0.37, 2, "ux")]
    return frame("t10_extreme", nodes, members, nloads, mloads, [2], 6, 6.0, harm)


ALL = [t1_cantilever3, t2_ssbeam, t3_portal, t4_fixedfixed, t5_closepair, t6_masses,
       t7_slender_stocky, t8_local40, t9_stress16, t10_extreme]

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for fn in ALL:
        fr = fn()
        with open(os.path.join(OUT, fr["frame_id"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(fr, f, indent=1)
            f.write("\n")
        print("wrote", fr["frame_id"])
