#!/usr/bin/env python
"""Hand-style verification of the refB test systems, written from the textbook equations
without importing referee.py.  Each feature is computed with scipy.optimize on the explicit
common-tangent / tangency / spinodal equations, and compared with the solver's report."""
import json
import os
import sys

import numpy as np
from scipy.optimize import brentq, fsolve

R = 8.314462618
HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    with open(os.path.join(HERE, name + ".json")) as f:
        s = json.load(f)
    with open(os.path.join(HERE, name + "_report.json")) as f:
        r = json.load(f)
    return s, r


def make_G(ph):
    hA, sA = ph["end_members"]["A"]["h"], ph["end_members"]["A"]["s"]
    hB, sB = ph["end_members"]["B"]["h"], ph["end_members"]["B"]["s"]
    L = [(c["a"], c["b"]) for c in ph["redlich_kister"]]

    def G(x, T):
        ex = sum((a + b * T) * (1 - 2 * x) ** k for k, (a, b) in enumerate(L))
        return (1 - x) * (hA - sA * T) + x * (hB - sB * T) + R * T * (x * np.log(x) + (1 - x) * np.log(1 - x)) + x * (1 - x) * ex

    def dG(x, T):
        ex = sum((a + b * T) * (1 - 2 * x) ** k for k, (a, b) in enumerate(L))
        dex = sum((a + b * T) * (-2 * k) * (1 - 2 * x) ** (k - 1) for k, (a, b) in enumerate(L) if k > 0)
        return (hB - sB * T) - (hA - sA * T) + R * T * np.log(x / (1 - x)) + (1 - 2 * x) * ex + x * (1 - x) * dex

    return G, dG


def brute_stable(ph, T, P, xl, xr, msg):
    """The common tangent through (xl, P) must lie below every phase on a dense grid."""
    m = P[1](xl, T)
    c = P[0](xl, T) - m * xl
    xs = np.linspace(1e-6, 1 - 1e-6, 400001)
    worst = max(np.max(m * xs + c - G(xs, T)) for G, _ in ph.values())
    print("  %-52s worst (line - G) = %.2e J/mol %s" % (msg + " stable", worst, "OK" if worst < 1e-6 else "UNSTABLE"))
    return worst < 1e-6


def report_val(msg, mine, theirs, tol):
    ok = abs(mine - theirs) <= tol
    print("  %-52s mine=%.15g report=%.15g diff=%.2e %s" % (msg, mine, theirs, abs(mine - theirs), "OK" if ok else "MISMATCH"))
    return ok


def verify_eutectic():
    print("eutectic")
    s, r = load("eutectic")
    ph = {p["name"]: make_G(p) for p in s["solution_phases"]}
    GL, dGL = ph["liquid"]
    Ga, dGa = ph["alpha"]
    Gb, dGb = ph["beta"]
    ok = True

    # three-phase common tangent: alpha(xa), liquid(xl), beta(xb) on one line, all tangent
    def eqs(z):
        xa, xl, xb, T = z
        m = dGL(xl, T)
        return [dGa(xa, T) - m, dGb(xb, T) - m,
                Ga(xa, T) + m * (xl - xa) - GL(xl, T),
                Gb(xb, T) + m * (xl - xb) - GL(xl, T)]
    z = fsolve(eqs, [0.02, 0.5, 0.98, 650.0], xtol=1e-14)
    print("  eutectic (alpha, liquid, beta) x = %.12f %.12f %.12f  T = %.9f K" % tuple(z))
    inv = [e for e in r["invariants"]]
    if s["window_K"][0] < z[3] < s["window_K"][1]:
        ok &= len(inv) == 1
        if inv:
            ok &= report_val("T_eutectic", z[3], inv[0]["temperature_K"], 1e-7 * z[3])
            for k, xk in enumerate(z[:3]):
                ok &= report_val("x%d" % (k + 1), xk, inv[0]["phases"][k]["x"], 1e-9)
    else:
        print("  eutectic lies outside the window; report has %d invariants" % len(inv))
        ok &= len(inv) == 0
    # pure-end melting points
    TA = (10000 - 0) / (10 - 0)
    TB = 10500 / 10
    print("  pure A melts at %.1f K, pure B at %.1f K (not reported)" % (TA, TB))
    # isotherm tie-lines by two-phase common tangents
    for iso in r["isotherms"]:
        T = iso["temperature_K"]
        for t in iso["tie_lines"]:
            P, Q = ph[t["left_phase"]], ph[t["right_phase"]]

            def ct(z, P=P, Q=Q):
                xl, xr = z
                return [P[1](xl, T) - Q[1](xr, T), P[0](xl, T) + P[1](xl, T) * (xr - xl) - Q[0](xr, T)]
            z = fsolve(ct, [t["x_left"] + 2e-3, t["x_right"] - 2e-3], xtol=1e-14)
            ok &= brute_stable(ph, T, P, z[0], z[1], "%g K %s-%s" % (T, t["left_phase"], t["right_phase"]))
            ok &= report_val("%g K %s-%s x_left" % (T, t["left_phase"], t["right_phase"]), z[0], t["x_left"], 1e-9)
            ok &= report_val("%g K %s-%s x_right" % (T, t["left_phase"], t["right_phase"]), z[1], t["x_right"], 1e-9)
    return ok


def verify_congruent():
    print("congruent_compound")
    s, r = load("congruent_compound")
    ph = {p["name"]: make_G(p) for p in s["solution_phases"]}
    GL, dGL = ph["liquid"]
    c = s["compounds"][0]
    ok = True
    # congruent melting: G_L(0.5, T) = h - s T, linear in T -> closed form
    hA, sA = 12000, 12
    hB, sB = 9000, 10
    x = 0.5
    A = (1 - x) * hA + x * hB + x * (1 - x) * (-8000)
    B = -((1 - x) * sA + x * sB) + R * (x * np.log(x) + (1 - x) * np.log(1 - x))
    Tc = (c["h"] - A) / (B + c["s"])
    print("  congruent melting of AB at T = %.12f K (closed form)" % Tc)
    con = r["congruent_points"]
    ok &= len(con) == 1
    if con:
        ok &= report_val("T_congruent", Tc, con[0]["temperature_K"], 1e-7 * Tc)
        ok &= con[0]["x"] == 0.5 and con[0]["phase_above"] == "liquid" and con[0]["phase_below"] == "AB" and con[0]["two_phase_side"] == "below"
        print("  sides:", con[0]["phase_above"], con[0]["phase_below"], con[0]["two_phase_side"])
    # eutectics: solid solution S tangent, line through compound point, liquid tangent
    for S, guess in (("alpha", [0.005, 0.25, 790.0]), ("beta", [0.996, 0.79, 730.0])):
        GS, dGS = ph[S]
        Gc = lambda T: c["h"] - c["s"] * T

        def eqs(z, GS=GS, dGS=dGS):
            xs, xl, T = z
            m = dGL(xl, T)
            return [dGS(xs, T) - m, GS(xs, T) + m * (xl - xs) - GL(xl, T), GL(xl, T) + m * (0.5 - xl) - Gc(T)]
        z = fsolve(eqs, guess, xtol=1e-14)
        print("  eutectic with %s: x_%s=%.12f x_L=%.12f T=%.9f" % (S, S, z[0], z[1], z[2]))
        match = [e for e in r["invariants"] if abs(e["temperature_K"] - z[2]) < 0.5]
        ok &= len(match) == 1
        if match:
            e = match[0]
            ok &= report_val("T_eutectic(%s)" % S, z[2], e["temperature_K"], 1e-7 * z[2])
            xs = [p["x"] for p in e["phases"]]
            names = [p["phase"] for p in e["phases"]]
            want = {S: z[0], "liquid": z[1], "AB": 0.5}
            for n, xv in zip(names, xs):
                ok &= report_val("x(%s)" % n, want[n], xv, 1e-9)
            ok &= e["class"] == "eutectic" and e["name"] == "eutectic"
    return ok


def verify_consolute():
    print("consolute")
    s, r = load("consolute")
    L0 = 20000.0
    Tc = L0 / (2 * R)
    print("  regular solution: T_c = L0/(2R) = %.12f K at x = 0.5" % Tc)
    ok = len(r["critical_points"]) == 1 and len(r["invariants"]) == 0 and len(r["congruent_points"]) == 0
    if r["critical_points"]:
        e = r["critical_points"][0]
        ok &= report_val("T_c", Tc, e["temperature_K"], 1e-7 * Tc)
        ok &= report_val("x_c", 0.5, e["x"], 1e-9)
        ok &= e["gap_side"] == "below" and e["phase"] == "alpha"
    for iso in r["isotherms"]:
        T = iso["temperature_K"]
        if T < Tc:
            # binodal of the symmetric regular solution: ln(x/(1-x)) = (L0/RT)(2x-1)
            f = lambda x: np.log(x / (1 - x)) - L0 / (R * T) * (2 * x - 1)
            xb = brentq(f, 1e-9, 0.5 - 1e-9, xtol=1e-15)
            t = iso["tie_lines"][0]
            ok &= report_val("%g K binodal x_left" % T, xb, t["x_left"], 1e-9)
            ok &= report_val("%g K binodal x_right" % T, 1 - xb, t["x_right"], 1e-9)
        else:
            ok &= len(iso["tie_lines"]) == 0
            print("  %g K: single alpha region, %d tie-lines" % (T, len(iso["tie_lines"])))
    return ok


if __name__ == "__main__":
    allok = verify_eutectic() & verify_congruent() & verify_consolute()
    print("ALL OK" if allok else "SOME MISMATCH")
    sys.exit(0 if allok else 1)
