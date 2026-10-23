#!/usr/bin/env python
"""Tests for Reference B.

1. cable_sealed: unbranched sealed cable with a negligible soma (d_s = 1e-4 um, outside the spec
   domain on purpose) checked against textbook formulas: R_in = coth(L/lambda)/G_inf,
   A(0->x) = cosh((L-x)/lambda)/cosh(L/lambda), Z = cosh(gamma (L-x)/lambda)/(G_inf gamma sinh(gamma L/lambda)),
   tau_n = tau_m/(1 + (n pi lambda/L)^2), C_0 = tau_m/C_tot, C_n = 2 tau_n/C_tot.
2. ytree_killed_shunt: soma + parent segment + two children (one killed, one shunted). DC and AC
   checked against the closed-form admittance recursion written here (independent of referee.py).

For both, the referee is run on the report produced by `referee.py --solve` (must pass) and on
perturbed copies (must fail).
"""
import cmath
import copy
import json
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(os.path.dirname(HERE), "referee.py")
PY = sys.executable


def cable_consts(seg):
    lam = 100.0 * math.sqrt(seg["Rm_ohm_cm2"] * seg["d_um"] / (4.0 * seg["Ri_ohm_cm"]))   # um (sqrt(cm um) = 100 um)
    tau = seg["Rm_ohm_cm2"] * seg["Cm_uF_cm2"] * 1e-3                             # ms
    ginf = (math.pi / 2.0) * seg["d_um"] ** 1.5 / math.sqrt(seg["Rm_ohm_cm2"] * seg["Ri_ohm_cm"])  # uS
    return lam, tau, ginf


def soma_admittance(soma, s=0.0):
    area = math.pi * soma["d_um"] ** 2
    G = area * 1e-2 / soma["Rm_ohm_cm2"] + soma["shunt_nS"] * 1e-3
    C = area * soma["Cm_uF_cm2"] * 1e-5
    return G + s * C


def neuron_1():
    seg = {"id": 1, "parent": 0, "L_um": 500.0, "d_um": 0.5, "Rm_ohm_cm2": 20000.0,
           "Ri_ohm_cm": 200.0, "Cm_uF_cm2": 1.0, "end": {"type": "sealed", "g_nS": None}}
    soma = {"d_um": 1e-4, "Rm_ohm_cm2": 60000.0, "Cm_uF_cm2": 1.0, "shunt_nS": 0.0}
    return {
        "neuron_id": "test_cable_sealed",
        "soma": soma, "segments": [seg],
        "input_resistance_sites": [{"segment": 0, "fraction": 0}, {"segment": 1, "fraction": 1.0},
                                   {"segment": 1, "fraction": 0.3}],
        "attenuation_pairs": [{"source": {"segment": 0, "fraction": 0}, "target": {"segment": 1, "fraction": 1.0}},
                              {"source": {"segment": 0, "fraction": 0}, "target": {"segment": 1, "fraction": 0.3}},
                              {"source": {"segment": 1, "fraction": 0.3}, "target": {"segment": 0, "fraction": 0}}],
        "impedance_queries": [{"source": {"segment": 0, "fraction": 0}, "target": {"segment": 0, "fraction": 0},
                               "frequency_Hz": 50.0},
                              {"source": {"segment": 0, "fraction": 0}, "target": {"segment": 1, "fraction": 0.3},
                               "frequency_Hz": 500.0},
                              {"source": {"segment": 0, "fraction": 0}, "target": {"segment": 1, "fraction": 1.0},
                               "frequency_Hz": 2000.0}],
        "tau_min_ms": 0.1,
    }


def analytic_1(n):
    seg = n["segments"][0]
    lam, tau_m, ginf = cable_consts(seg)
    L = seg["L_um"]
    ell = L / lam
    out = {}
    rin0 = (1.0 / math.tanh(ell)) / ginf
    out["rin"] = [rin0, rin0]
    # input resistance at x: two sealed cables of length x and L-x in parallel
    x = 0.3 * L
    g = ginf * (math.tanh(x / lam) + math.tanh((L - x) / lam))
    out["rin"].append(1.0 / g)
    out["att"] = [1.0 / math.cosh(ell), math.cosh((L - x) / lam) / math.cosh(ell),
                  math.cosh((L - x) / lam) / math.cosh(ell)]   # reciprocity: A(x->0) R_in(x) = A(0->x) R_in(0)
    out["att"][2] = out["att"][1] * rin0 / out["rin"][2]
    imp = []
    for q, xt in zip(n["impedance_queries"], [0.0, x, L]):
        s = 1j * 2 * math.pi * q["frequency_Hz"] * 1e-3
        gam = cmath.sqrt(1 + s * tau_m)
        z = cmath.cosh(gam * (L - xt) / lam) / (ginf * gam * cmath.sinh(gam * ell))
        imp.append(z)
    out["imp"] = imp
    ctot = math.pi * seg["d_um"] * L * seg["Cm_uF_cm2"] * 1e-5      # nF
    taus = []
    coefs = []
    k = 0
    while True:
        t = tau_m / (1 + (k * math.pi * lam / L) ** 2)
        if t < n["tau_min_ms"]:
            break
        taus.append(t)
        coefs.append((tau_m / ctot) if k == 0 else 2 * t / ctot)
        k += 1
    out["tau"] = taus
    out["coef"] = coefs
    return out


def neuron_2():
    segs = [
        {"id": 1, "parent": 0, "L_um": 180.0, "d_um": 3.2, "Rm_ohm_cm2": 15000.0, "Ri_ohm_cm": 120.0,
         "Cm_uF_cm2": 0.9, "end": None},
        {"id": 2, "parent": 1, "L_um": 320.0, "d_um": 1.4, "Rm_ohm_cm2": 30000.0, "Ri_ohm_cm": 150.0,
         "Cm_uF_cm2": 1.2, "end": {"type": "killed", "g_nS": None}},
        {"id": 3, "parent": 1, "L_um": 260.0, "d_um": 1.1, "Rm_ohm_cm2": 12000.0, "Ri_ohm_cm": 90.0,
         "Cm_uF_cm2": 1.5, "end": {"type": "shunt", "g_nS": 4.0}},
    ]
    soma = {"d_um": 22.0, "Rm_ohm_cm2": 18000.0, "Cm_uF_cm2": 1.1, "shunt_nS": 3.0}
    L = lambda s, f: {"segment": s, "fraction": f}
    return {
        "neuron_id": "test_ytree_killed_shunt",
        "soma": soma, "segments": segs,
        "input_resistance_sites": [L(0, 0), L(1, 1.0), L(2, 0.5), L(3, 1.0), L(3, 0.37)],
        "attenuation_pairs": [{"source": L(0, 0), "target": L(3, 1.0)},
                              {"source": L(3, 1.0), "target": L(0, 0)},
                              {"source": L(2, 0.5), "target": L(3, 0.37)},
                              {"source": L(1, 1.0), "target": L(2, 0.5)}],
        "impedance_queries": [{"source": L(0, 0), "target": L(0, 0), "frequency_Hz": 1.0},
                              {"source": L(0, 0), "target": L(3, 1.0), "frequency_Hz": 120.0},
                              {"source": L(2, 0.5), "target": L(3, 0.37), "frequency_Hz": 2000.0},
                              {"source": L(3, 0.37), "target": L(2, 0.5), "frequency_Hz": 7.5}],
        "tau_min_ms": 0.6,
    }


# --- closed-form admittance for the Y tree (independent of referee.py) --------------------------

def seg_input_admittance(seg, s, load):
    """Admittance looking into the proximal end of `seg` with terminal admittance `load`
    (complex, uS; None = sealed, 'killed' = clamped)."""
    lam, tau, ginf = cable_consts(seg)
    gam = cmath.sqrt(1 + s * tau)
    ell = gam * seg["L_um"] / lam
    Gi = ginf * gam
    if load == "killed":
        return Gi / cmath.tanh(ell)
    B = 0.0 if load is None else load / Gi
    t = cmath.tanh(ell)
    return Gi * (B + t) / (1 + B * t)


def seg_transfer(seg, s, load, x):
    """Potential ratio V(x)/V(0) along `seg` (x in um from proximal end) with distal load."""
    lam, tau, ginf = cable_consts(seg)
    gam = cmath.sqrt(1 + s * tau)
    Lc = seg["L_um"] / lam * gam
    xc = x / lam * gam
    if load == "killed":
        return cmath.sinh(Lc - xc) / cmath.sinh(Lc)
    B = 0.0 if load is None else load / (ginf * gam)
    return (cmath.cosh(Lc - xc) + B * cmath.sinh(Lc - xc)) / (cmath.cosh(Lc) + B * cmath.sinh(Lc))


def ytree_transfer(n, s, src, tgt):
    """Z(src -> tgt) for the Y tree at Laplace variable s via reciprocity and the chain rule.
    Locations: (seg, fraction). Uses: Z(a->b) = Z(b->a) (passive, reciprocal)."""
    soma, segs = n["soma"], {sg["id"]: sg for sg in n["segments"]}
    s1, s2, s3 = segs[1], segs[2], segs[3]
    load2 = "killed"
    load3 = s3["end"]["g_nS"] * 1e-3
    Y2 = seg_input_admittance(s2, s, load2)
    Y3 = seg_input_admittance(s3, s, load3)
    Y1 = seg_input_admittance(s1, s, Y2 + Y3)
    Ys = soma_admittance(soma, s)

    def pos(loc):
        return loc

    def path_to_soma(loc):
        # returns list of (segment, x) from soma side downward
        seg, f = loc
        if seg == 0:
            return []
        if seg == 1:
            return [(1, f * s1["L_um"])]
        return [(1, s1["L_um"]), (seg, f * segs[seg]["L_um"])]

    def V_from_soma(loc):
        """Potential at loc for unit potential at the soma (current injected at soma)."""
        v = 1.0 + 0j
        for seg, x in path_to_soma(loc):
            sg = segs[seg]
            load = (Y2 + Y3) if seg == 1 else (load2 if seg == 2 else load3)
            v *= seg_transfer(sg, s, load, x)
        return v

    def Z_soma_to(loc):
        return V_from_soma(loc) / (Ys + Y1)

    def Zin(loc):
        seg, f = loc
        if seg == 0:
            return 1.0 / (Ys + Y1)
        sg = segs[seg]
        x = f * sg["L_um"]
        lam, tau, ginf = cable_consts(sg)
        gam = cmath.sqrt(1 + s * tau)
        Gi = ginf * gam
        # distal side: cable of length L-x with its load
        sub = dict(sg)
        sub["L_um"] = sg["L_um"] - x
        load = (Y2 + Y3) if seg == 1 else (load2 if seg == 2 else load3)
        Yd = seg_input_admittance(sub, s, load) if sub["L_um"] > 0 else (
            float("inf") if load == "killed" else load)
        # proximal side: cable of length x loaded by what is upstream
        if seg == 1:
            up = Ys
        else:
            other = Y3 if seg == 2 else Y2
            # looking from the branch point towards the soma through segment 1
            up = seg_input_admittance(s1, s, Ys) + other
        subp = dict(sg)
        subp["L_um"] = x
        Yp = seg_input_admittance(subp, s, up) if x > 0 else up
        if Yd == float("inf"):
            return 0.0
        return 1.0 / (Yp + Yd)

    if src == tgt:
        return Zin(src)
    if src == (0, 0.0):
        return Z_soma_to(tgt)
    if tgt == (0, 0.0):
        return Z_soma_to(src)
    # both in dendrites: inject at src, potential at tgt. Chain through the common ancestor.
    # V(tgt)/V(src) = [V(tgt)/V(bp)] * [V(bp)/V(src)] where bp = nearest common point on the path.
    sseg, sf = src
    tseg, tf = tgt
    Zs = Zin(src)
    if sseg == tseg:
        raise NotImplementedError
    # transfer from src to the branch point (distal end of seg 1), going proximally along src's segment
    sg = segs[sseg]
    x = sf * sg["L_um"]
    if sseg == 1:
        # from x on segment 1 distally to the branch point (x = L1), loaded by the children
        subd = dict(sg)
        subd["L_um"] = sg["L_um"] - x
        r_src_to_bp = seg_transfer(subd, s, Y2 + Y3, subd["L_um"]) if subd["L_um"] > 0 else 1.0
    else:
        # ratio V(bp)/V(src) along the proximal piece of src's segment, loaded proximally by `up`.
        # Along a cable of length x from src (position x) toward the proximal end (position 0) with load
        # `up`: by symmetry this equals the transfer from 0 to x on a cable of length x loaded by `up`.
        other = Y3 if sseg == 2 else Y2
        up = seg_input_admittance(s1, s, Ys) + other
        subp = dict(sg)
        subp["L_um"] = x
        r_src_to_bp = seg_transfer(subp, s, up, x) if x > 0 else 1.0
    if tseg == 1:
        # target on segment 1 at distance tf*L1 from soma; go from bp (x=L1) toward soma: cable of length
        # L1 - tf*L1 loaded by (soma side admittance through the proximal piece)
        sub1 = dict(s1)
        sub1["L_um"] = tf * s1["L_um"]
        upl = seg_input_admittance(sub1, s, Ys) if tf > 0 else Ys
        sub2 = dict(s1)
        sub2["L_um"] = s1["L_um"] - tf * s1["L_um"]
        r_bp_to_tgt = seg_transfer(sub2, s, upl, sub2["L_um"]) if sub2["L_um"] > 0 else 1.0
    else:
        tg = segs[tseg]
        loadt = load2 if tseg == 2 else load3
        r_bp_to_tgt = seg_transfer(tg, s, loadt, tf * tg["L_um"])
    return Zs * r_src_to_bp * r_bp_to_tgt


def analytic_2(n):
    out = {"rin": [], "att": [], "imp": []}
    for loc in n["input_resistance_sites"]:
        k = (loc["segment"], float(loc["fraction"]))
        out["rin"].append(ytree_transfer(n, 0.0, k, k).real)
    for p in n["attenuation_pairs"]:
        a = (p["source"]["segment"], float(p["source"]["fraction"]))
        b = (p["target"]["segment"], float(p["target"]["fraction"]))
        out["att"].append((ytree_transfer(n, 0.0, a, b) / ytree_transfer(n, 0.0, a, a)).real)
    for q in n["impedance_queries"]:
        a = (q["source"]["segment"], float(q["source"]["fraction"]))
        b = (q["target"]["segment"], float(q["target"]["fraction"]))
        s = 1j * 2 * math.pi * q["frequency_Hz"] * 1e-3
        out["imp"].append(ytree_transfer(n, s, a, b))
    return out


def run(args):
    p = subprocess.run([PY, REF] + args, capture_output=True, text=True)
    return p


def compare(name, rep, ana, with_modes):
    worst = 0.0
    for i, e in enumerate(rep["input_resistance"]):
        d = abs(e["R_MOhm"] / ana["rin"][i] - 1)
        worst = max(worst, d)
        print("  R_in[%d]   solver %.12g  analytic %.12g  rel %.2e" % (i, e["R_MOhm"], ana["rin"][i], d))
    for i, e in enumerate(rep["attenuation"]):
        d = abs(e["factor"] / ana["att"][i] - 1)
        worst = max(worst, d)
        print("  A[%d]      solver %.12g  analytic %.12g  rel %.2e" % (i, e["factor"], ana["att"][i], d))
    for i, e in enumerate(rep["impedance"]):
        z = ana["imp"][i]
        d = abs(e["magnitude_MOhm"] / abs(z) - 1)
        ph = math.degrees(cmath.phase(z))
        dp = abs(e["phase_deg"] - ph)
        worst = max(worst, d, dp / 1e-5 * 1e-6)   # phase scored against the 1e-5 deg tolerance
        print("  |Z|[%d]    solver %.12g  analytic %.12g  rel %.2e ; phase %.9f vs %.9f (diff %.2e deg)"
              % (i, e["magnitude_MOhm"], abs(z), d, e["phase_deg"], ph, dp))
    if with_modes:
        print("  modes: solver %d, analytic %d" % (len(rep["modes"]), len(ana["tau"])))
        assert len(rep["modes"]) == len(ana["tau"]), "mode count mismatch"
        rin0 = ana["rin"][0]
        for k, md in enumerate(rep["modes"]):
            dt = abs(md["tau_ms"] / ana["tau"][k] - 1)
            dc = abs(md["coefficient_MOhm"] - ana["coef"][k]) / rin0
            worst = max(worst, dt, dc)
            print("  tau[%d]    solver %.12g  analytic %.12g  rel %.2e ; coef %.10g vs %.10g (diff %.2e R_in)"
                  % (k, md["tau_ms"], ana["tau"][k], dt, md["coefficient_MOhm"], ana["coef"][k], dc))
    print("  %s worst deviation from analytic: %.3e" % (name, worst))
    return worst


def perturb(rep, what):
    r = copy.deepcopy(rep)
    if what == "rin":
        r["input_resistance"][0]["R_MOhm"] *= 1 + 3e-6
    elif what == "att":
        r["attenuation"][1]["factor"] *= 1 - 3e-6
    elif what == "mag":
        r["impedance"][1]["magnitude_MOhm"] *= 1 + 3e-6
    elif what == "phase":
        r["impedance"][2]["phase_deg"] += 1e-4
    elif what == "tau":
        r["modes"][1]["tau_ms"] *= 1 + 3e-6
    elif what == "coef":
        r["modes"][0]["coefficient_MOhm"] += 3e-6 * r["input_resistance"][0]["R_MOhm"]
    elif what == "drop_mode":
        r["modes"].pop()
    elif what == "swap_coef":
        # keep the sum but move weight between two modes (caught by coefficient check and transient)
        d = 1e-4 * r["input_resistance"][0]["R_MOhm"]
        r["modes"][0]["coefficient_MOhm"] += d
        r["modes"][1]["coefficient_MOhm"] -= d
    return r


def main():
    tests = [("cable_sealed", neuron_1(), analytic_1, True),
             ("ytree_killed_shunt", neuron_2(), analytic_2, False)]
    ok = True
    for name, neuron, ana_fn, with_modes in tests:
        npath = os.path.join(HERE, name + ".json")
        rpath = os.path.join(HERE, name + "_report.json")
        vpath = os.path.join(HERE, name + "_verdict.json")
        with open(npath, "w") as fh:
            json.dump(neuron, fh, indent=1)
        print("== %s: solve" % name)
        p = run(["--solve", "--neuron", npath, "--output", rpath])
        print(p.stderr.strip())
        assert p.returncode == 0, p.stderr
        rep = json.load(open(rpath))
        ana = ana_fn(neuron)
        worst = compare(name, rep, ana, with_modes)
        if not with_modes:
            s = sum(m["coefficient_MOhm"] for m in rep["modes"])
            print("  sum of reported coefficients / R_in(soma) = %.8f (fast modes omitted)"
                  % (s / rep["input_resistance"][0]["R_MOhm"]))
        print("== %s: referee on own report" % name)
        p = run(["--neuron", npath, "--report", rpath, "--out", vpath])
        print(p.stdout.strip())
        print(p.stderr.strip())
        if p.returncode != 0:
            ok = False
            print("  !! expected PASS")
        for what in ["rin", "att", "mag", "phase", "tau", "coef", "drop_mode", "swap_coef"]:
            bad = perturb(rep, what)
            bpath = os.path.join(HERE, "_perturbed.json")
            with open(bpath, "w") as fh:
                json.dump(bad, fh)
            p = run(["--neuron", npath, "--report", bpath, "--quiet"])
            v = json.loads(open(bpath).read()) if False else None
            res = "FAIL" if p.returncode != 0 else "PASS"
            print("  perturbed (%s): %s%s" % (what, res, "" if res == "FAIL" else "  !! expected FAIL"))
            if res != "FAIL":
                ok = False
            os.remove(bpath)
        if worst > 1e-6:
            ok = False
            print("  !! deviation from analytic exceeds 1e-6")
    print("ALL OK" if ok else "SOME TESTS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
