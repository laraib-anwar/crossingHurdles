#!/usr/bin/env python3
"""Hand-verifiable tests for Reference B.

1. Solve three constructed frames with `referee.py --solve` (extrapolated FE) and compare with closed
   forms: inclined 3-member cantilever (bending roots of 1 + cos x cosh x = 0, i.e. beta L = 1.875104,
   4.694091, 7.854757, ..., axial (2n-1) pi / 2; tip statics; tip receptances), 4-member simply
   supported beam (beta L = n pi, axial fixed-free; statics; midspan and axial receptances), portal
   frame whose tie member is clamped at both ends (its clamped-clamped frequencies beta L = 4.730041,
   7.853205, 10.995608 must appear among the natural frequencies).
2. The referee must pass the solver's own reports and must FAIL perturbed reports: a frequency shifted
   by 3e-9 relative, a dropped frequency, count_below off by one (both ways), a static displacement and
   a harmonic amplitude shifted by 3e-9 relative (the value that sets its section-5 scale), and a
   section-4 violation; shifts of 3e-10 must still pass.
3. Domain-edge stress frame (16 members, lambda 39.8): runtime, uncertainty, count = finest inertia.
Optional: --pair FRAME REPORT (repeatable) runs the same negative tests on an external report.
usage: python tests/run_tests.py [--pair F R ...]
"""
import argparse
import copy
import json
import math
import os
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "..", "referee.py")
PY = sys.executable
LD = np.longdouble
PI = 4 * np.arctan(LD(1))
OUT = os.path.join(HERE, "out")
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print("%-4s %s %s" % ("ok" if ok else "FAIL", name, detail), flush=True)


def referee(args):
    p = subprocess.run([PY, REF] + args, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def root(fun, a, b):
    """bisection then Newton-free polish by bisection in longdouble"""
    a, b = LD(a), LD(b)
    fa, fb = fun(a), fun(b)
    assert fa * fb < 0, (a, b)
    for _ in range(400):
        m = (a + b) / 2
        fm = fun(m)
        if fm == 0:
            return m
        if (fm > 0) == (fa > 0):
            a, fa = m, fm
        else:
            b = m
    return (a + b) / 2


def cant_roots(n):  # 1 + cos x cosh x = 0
    return [root(lambda x: 1 + np.cos(x) * np.cosh(x), (k - 0.5) * math.pi - 1.0, (k - 0.5) * math.pi + 0.6)
            for k in range(1, n + 1)]


def cc_roots(n):  # cos x cosh x = 1, x > 0
    return [root(lambda x: np.cos(x) * np.cosh(x) - 1, (k + 0.5) * math.pi - 0.5, (k + 0.5) * math.pi + 0.5)
            for k in range(1, n + 1)]


def props(fr, k=0):
    m = fr["members"][k]
    return LD(m["E"]), LD(m["A"]), LD(m["I"]), LD(m["rho"])


def length(fr, i, j):
    a, b = fr["nodes"][i - 1], fr["nodes"][j - 1]
    return np.sqrt((LD(b["x"]) - LD(a["x"])) ** 2 + (LD(b["y"]) - LD(a["y"])) ** 2)


def rel(a, b):
    return float(abs(LD(a) - LD(b)) / abs(LD(b)))


def solve(fr):
    os.makedirs(OUT, exist_ok=True)
    fp = os.path.join(HERE, fr["frame_id"] + ".json")
    rp = os.path.join(OUT, fr["frame_id"] + ".report.json")
    dp = os.path.join(OUT, fr["frame_id"] + ".solve.json")
    rc, txt = referee(["--solve", "--frame", fp, "--output", rp, "--out", dp])
    check("%s solve runs" % fr["frame_id"], rc == 0, txt)
    return json.load(open(rp)), json.load(open(dp)), fp, rp


def receptances(L, EI, EA, rA, rho, E, om):
    beta = np.sqrt(np.sqrt(rA * om * om / EI))
    x = beta * L
    D = 1 + np.cos(x) * np.cosh(x)
    RvP = (np.cosh(x) * np.sin(x) - np.sinh(x) * np.cos(x)) / (EI * beta ** 3 * D)
    RtP = np.sinh(x) * np.sin(x) / (EI * beta ** 2 * D)
    RtM = (np.cosh(x) * np.sin(x) + np.sinh(x) * np.cos(x)) / (EI * beta * D)
    k = om * np.sqrt(rho / E)
    Ru = np.tan(k * L) / (EA * k)
    return RvP, RtP, RtM, Ru


def test_cantilever():
    fr = json.load(open(os.path.join(HERE, "tb_cantilever.json")))
    rep, sol, fp, rp = solve(fr)
    E, A, I, rho = props(fr)
    EI, EA, rA = E * I, E * A, rho * A
    L = sum(length(fr, m["i"], m["j"]) for m in fr["members"])
    r = cant_roots(12)
    check("cantilever roots match beta L = 1.875104, 4.694091, 7.854757",
          all(abs(float(r[i]) - v) < 5e-7 for i, v in enumerate((1.875104, 4.694091, 7.854757))),
          str([float(x) for x in r[:3]]))
    fb = [x * x / (2 * PI * L * L) * np.sqrt(EI / rA) for x in r]
    fa = [(2 * n - 1) / (4 * L) * np.sqrt(E / rho) for n in range(1, 6)]
    ex = sorted(fb + fa, key=float)
    worst = max(rel(rep["frequencies_Hz"][i], ex[i]) for i in range(fr["n_modes"]))
    check("cantilever frequencies vs closed form (bending + axial) <= 1e-11", worst <= 1e-11, "worst %.2e" % worst)
    cnt = sum(1 for x in ex if x <= LD(fr["f_max_Hz"]))
    check("cantilever count_below = %d" % cnt, rep["count_below"] == cnt)
    # statics
    c, s = LD(0.8), LD(0.6)
    nl = fr["nodal_loads"][0]
    Pa = LD(nl["Fx"]) * c + LD(nl["Fy"]) * s
    Pt = -LD(nl["Fx"]) * s + LD(nl["Fy"]) * c
    Mz = LD(nl["Mz"])
    wy = LD(fr["member_loads"][0]["wy"])
    qa, qt = wy * s, wy * c
    S = {"tr": 0.0, "rot": 0.0}
    vals = []
    for q, nd in enumerate(fr["static_query_nodes"]):
        x = length(fr, 1, nd)
        v = Pt * x * x * (3 * L - x) / (6 * EI) + Mz * x * x / (2 * EI) + qt * x * x * (6 * L * L - 4 * L * x + x * x) / (24 * EI)
        t = Pt * x * (2 * L - x) / (2 * EI) + Mz * x / EI + qt * x * (3 * L * L - 3 * L * x + x * x) / (6 * EI)
        u = Pa * x / EA + qa * (L * x - x * x / 2) / EA
        e = {"ux": c * u - s * v, "uy": s * u + c * v, "rz": t}
        vals.append(e)
        S["tr"] = max(S["tr"], abs(float(e["ux"])), abs(float(e["uy"])))
        S["rot"] = max(S["rot"], abs(float(e["rz"])))
    worst = 0.0
    for q, e in enumerate(vals):
        for d in ("ux", "uy", "rz"):
            sc = max(abs(float(e[d])), S["rot" if d == "rz" else "tr"])
            worst = max(worst, float(abs(LD(rep["static"][q][d]) - e[d])) / sc)
    check("cantilever statics vs closed form <= 1e-12 of scale", worst <= 1e-12, "worst %.2e" % worst)
    # harmonic: tip receptances
    worst = 0.0
    for q, h in enumerate(fr["harmonic_queries"]):
        om = 2 * PI * LD(h["f_Hz"])
        RvP, RtP, RtM, Ru = receptances(L, EI, EA, rA, rho, E, om)
        P = LD(h["amplitude"])
        key = (h["load_dof"], h["response_dof"])
        U = {("ux", "ux"): P * (c * c * Ru + s * s * RvP), ("uy", "rz"): P * c * RtP, ("rz", "rz"): P * RtM}[key]
        worst = max(worst, rel(rep["harmonic"][q]["U"], U))
    check("cantilever harmonic tip receptances vs closed form <= 1e-11", worst <= 1e-11, "worst %.2e" % worst)
    return fr, rep, sol, fp, rp


def test_ssbeam():
    fr = json.load(open(os.path.join(HERE, "tb_ssbeam.json")))
    rep, sol, fp, rp = solve(fr)
    E, A, I, rho = props(fr)
    EI, EA, rA = E * I, E * A, rho * A
    L = LD(fr["nodes"][-1]["x"]) - LD(fr["nodes"][0]["x"])
    fb = [(n * PI) ** 2 / (2 * PI * L * L) * np.sqrt(EI / rA) for n in range(1, 10)]
    fa = [(2 * n - 1) / (4 * L) * np.sqrt(E / rho) for n in range(1, 5)]
    ex = sorted(fb + fa, key=float)
    worst = max(rel(rep["frequencies_Hz"][i], ex[i]) for i in range(fr["n_modes"]))
    check("ss beam frequencies (beta L = n pi, axial fixed-free) <= 1e-11", worst <= 1e-11, "worst %.2e" % worst)
    cnt = sum(1 for x in ex if x <= LD(fr["f_max_Hz"]))
    check("ss beam count_below = %d" % cnt, rep["count_below"] == cnt)
    # statics: uniform wy, point load P at node 2 (x = a), axial Fx at the roller end
    wy = LD(fr["member_loads"][0]["wy"])
    P = LD(fr["nodal_loads"][0]["Fy"])
    a = LD(fr["nodes"][fr["nodal_loads"][0]["node"] - 1]["x"])
    b = L - a
    Fx = LD(fr["nodal_loads"][1]["Fx"])
    vals = []
    for nd in fr["static_query_nodes"]:
        x = LD(fr["nodes"][nd - 1]["x"])
        v = wy * x * (L ** 3 - 2 * L * x * x + x ** 3) / (24 * EI)
        t = wy * (L ** 3 - 6 * L * x * x + 4 * x ** 3) / (24 * EI)
        if x <= a:
            v += P * b * x * (L * L - b * b - x * x) / (6 * L * EI)
            t += P * b * (L * L - b * b - 3 * x * x) / (6 * L * EI)
        else:
            y = L - x
            v += P * a * y * (L * L - a * a - y * y) / (6 * L * EI)
            t += -P * a * (L * L - a * a - 3 * y * y) / (6 * L * EI)
        vals.append({"ux": Fx * x / EA, "uy": v, "rz": t})
    Str = max(max(abs(float(e["ux"])), abs(float(e["uy"]))) for e in vals)
    Srt = max(abs(float(e["rz"])) for e in vals)
    worst = max(float(abs(LD(rep["static"][q][d]) - e[d])) / max(abs(float(e[d])), Srt if d == "rz" else Str)
                for q, e in enumerate(vals) for d in ("ux", "uy", "rz"))
    check("ss beam statics vs closed form <= 1e-12 of scale", worst <= 1e-12, "worst %.2e" % worst)
    worst = 0.0
    for q, h in enumerate(fr["harmonic_queries"]):
        om = 2 * PI * LD(h["f_Hz"])
        Pq = LD(h["amplitude"])
        if h["load_dof"] == "uy":
            beta = np.sqrt(np.sqrt(rA * om * om / EI))
            x = beta * L / 2
            U = Pq * (np.tan(x) - np.tanh(x)) / (4 * EI * beta ** 3)
        else:
            k = om * np.sqrt(rho / E)
            U = Pq * np.tan(k * L) / (EA * k)
        worst = max(worst, rel(rep["harmonic"][q]["U"], U))
    check("ss beam harmonic (midspan, axial) vs closed form <= 1e-11", worst <= 1e-11, "worst %.2e" % worst)
    return fr, rep, sol, fp, rp


def test_fixedmember():
    fr = json.load(open(os.path.join(HERE, "tb_fixedmember.json")))
    rep, sol, fp, rp = solve(fr)
    m = fr["members"][3]
    E, A, I, rho = (LD(m[k]) for k in ("E", "A", "I", "rho"))
    L = length(fr, m["i"], m["j"])
    r = cc_roots(3)
    check("clamped-clamped roots match beta L = 4.730041, 7.853205, 10.995608",
          all(abs(float(r[i]) - v) < 5e-7 for i, v in enumerate((4.730041, 7.853205, 10.995608))),
          str([float(x) for x in r]))
    fcc = [x * x / (2 * PI * L * L) * np.sqrt(E * I / (rho * A)) for x in r]
    got = [LD(x) for x in rep["frequencies_Hz"]]
    for n, f in enumerate(fcc):
        d = min(float(abs(g - f) / f) for g in got)
        check("tie member clamped-clamped mode %d (%.9f Hz) present <= 1e-11" % (n + 1, float(f)), d <= 1e-11, "closest %.2e" % d)
    return fr, rep, sol, fp, rp


def test_stress():
    """domain edge: 12 nodes, 16 members (slender braces), lumped masses, inclined members, member load,
    max lambda 39.8 at f_max = 235 Hz (99 natural frequencies below f_max): self-consistency and runtime"""
    import time
    fr = json.load(open(os.path.join(HERE, "tb_stress16.json")))
    t = time.time()
    rep, sol, fp, rp = solve(fr)
    dt = time.time() - t
    check("stress16 solve runtime %.1f s < 180 s" % dt, dt < 180)
    check("stress16 referee uncertainty <= 1e-11", max(sol["f_unc"]) <= 1e-11, "%.1e" % max(sol["f_unc"]))
    lv = sol["diagnostics"]["levels"]
    check("stress16 count_below 99 equals finest-mesh inertia count", rep["count_below"] == 99 and lv[-1]["N_below"] == 99,
          "levels %s" % [x["N_below"] for x in lv])
    return fr, rep, sol, fp, rp


def negatives(fr, rep, fp, f_next, label):
    tmp = tempfile.mkdtemp(prefix="refB_neg_")

    def run(rp_obj, tag, expect_pass):
        p = os.path.join(tmp, tag + ".json")
        with open(p, "w") as fh:
            json.dump(rp_obj, fh)
        rc, txt = referee(["--frame", fp, "--report", p, "--out", os.path.join(tmp, tag + ".verdict.json"), "--quiet"])
        v = json.load(open(os.path.join(tmp, tag + ".verdict.json")))
        ok = (rc == 0) if expect_pass else (rc == 1 and not v["pass"])
        check("%s %s -> %s" % (label, tag, "pass" if expect_pass else "FAIL"), ok,
              "" if ok or expect_pass else "exit %d" % rc)
        return v

    v = run(rep, "original", True)
    nm = len(rep["frequencies_Hz"])
    j = nm // 2
    for eps, exp in ((3e-9, False), (-3e-9, False), (3e-10, True)):
        r = copy.deepcopy(rep)
        r["frequencies_Hz"][j] *= 1 + eps
        run(r, "freq%d_shift_%+.0e" % (j, eps), exp)
    r = copy.deepcopy(rep)
    del r["frequencies_Hz"][1]
    r["frequencies_Hz"].append(f_next)
    run(r, "dropped_freq1", False)
    for dcount in (1, -1):
        r = copy.deepcopy(rep)
        r["count_below"] += dcount
        run(r, "count%+d" % dcount, False)
    # static and harmonic: shift the value that sets its section-5 scale
    for kind in ("static", "harmonic"):
        recs = v["checks"][kind]
        for grp in ("tr", "rot"):
            mine = [c for c in recs if (c["dof"] == "rz") == (grp == "rot")]
            if not mine:
                continue
            cand = [c for c in mine if abs(c["reference"]) == c["scale"]]
            if cand:  # this value sets its section-5 scale: a 3e-9 relative shift must fail
                c, unit = cand[0], "rel"
            else:  # scale set by another value: shift by 3e-9 of the scale (absolute)
                c, unit = max(mine, key=lambda c: abs(c["reference"])), "of_scale"
            for eps, exp in ((3e-9, False), (3e-10, True)):
                r = copy.deepcopy(rep)
                dv = eps * (abs(c["reference"]) if unit == "rel" else c["scale"]) * (1 if c["reference"] >= 0 else -1)
                if kind == "static":
                    r["static"][c["q"]][c["dof"]] += dv
                else:
                    r["harmonic"][c["q"]]["U"] += dv
                run(r, "%s%d_%s_shift_%+.0e_%s" % (kind, c["q"], c["dof"], eps, unit), exp)
    r = copy.deepcopy(rep)
    r["comment"] = "x"
    run(r, "section4_extra_key", False)
    r = copy.deepcopy(rep)
    r["frequencies_Hz"] = r["frequencies_Hz"][::-1]
    run(r, "frequencies_reversed", False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pair", nargs=2, action="append", default=[], metavar=("FRAME", "REPORT"))
    a = ap.parse_args()
    for t in (test_cantilever, test_ssbeam, test_fixedmember, test_stress):
        fr, rep, sol, fp, rp = t()
        f_next = sol["diagnostics"]["frequencies"][-1]["f_Hz"]
        negatives(fr, rep, fp, f_next, fr["frame_id"])
    for fp, rp in a.pair:
        fr = json.load(open(fp))
        rep = json.load(open(rp))
        tmpv = tempfile.mktemp(suffix=".json")
        rc, txt = referee(["--frame", fp, "--report", rp, "--out", tmpv, "--quiet"])
        f_next = json.load(open(tmpv))["referee"]["f_next_Hz"]
        negatives(fr, rep, fp, f_next, fr["frame_id"])
    nf = sum(1 for _, ok in RESULTS if not ok)
    print("%d checks, %d failed" % (len(RESULTS), nf))
    return 1 if nf else 0


if __name__ == "__main__":
    sys.exit(main())
