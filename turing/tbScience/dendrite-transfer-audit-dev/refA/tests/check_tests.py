"""Runs reference.py on every test neuron, times it, and checks the reports against textbook
formulas and internal identities (reciprocity, DC = AC(f->0), guarantees, mode sums).

python check_tests.py            (uses the python it is run with)
"""
import json
import math
import os
import subprocess
import sys
import time

import numpy as np
import scipy.optimize

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(os.path.dirname(HERE), "reference.py")
sys.path.insert(0, os.path.dirname(HERE))
import reference as R  # noqa: E402

NAMES = ["cable_sealed", "cable_killed", "rall_exact", "rall_perturbed", "shunt_terminal",
         "near_symmetric", "tree10", "tree12_soma"]

fails = 0


def check(label, got, want, tol, rel=True):
    global fails
    err = abs(got - want) / (abs(want) if rel and want != 0 else 1.0)
    ok = err <= tol
    if not ok:
        fails += 1
    print("  %-58s %s  dev=%.2e" % (label, "ok  " if ok else "FAIL", err))
    return err


def run(name):
    nf = os.path.join(HERE, name + ".json")
    rf = os.path.join(HERE, name + "_report.json")
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    t0 = time.time()
    subprocess.run([sys.executable, REF, "--neuron", nf, "--output", rf], check=True, env=env,
                   stderr=subprocess.DEVNULL)
    dt = time.time() - t0
    return json.load(open(nf)), json.load(open(rf)), dt


def cable_params(nrn):
    seg = nrn.segs[1]
    Ltot = sum(s.L for s in nrn.segs.values())
    return seg, Ltot / seg.lam, Ltot


def sealed_cable_textbook(nrn, s_min):
    seg, X, Ltot = cable_params(nrn)
    G, Gs, Cs = seg.Ginf, nrn.Gs, nrn.Cs
    Rin_soma = 1.0 / (Gs + G * math.tanh(X))
    Rin_end = 1.0 / (G * (Gs + G * math.tanh(X)) / (G + Gs * math.tanh(X)))
    # exact modes with the soma: Gs + s Cs + G gamma tanh(gamma X) = 0  (gamma^2 = 1 + s tau)
    def F(s):
        g2 = 1.0 + s * seg.tau
        if g2 >= 0:
            g = math.sqrt(g2)
            return Gs + s * Cs + G * g * math.tanh(g * X)
        w = math.sqrt(-g2)
        return (Gs + s * Cs) * math.cos(w * X) - G * w * math.sin(w * X)   # cleared of cos
    grid = -np.geomspace(1e-4 / seg.tau, -s_min, 20000)
    vals = np.array([F(x) for x in grid])
    roots = []
    for i in range(len(grid) - 1):
        if vals[i] * vals[i + 1] < 0:
            roots.append(scipy.optimize.brentq(F, grid[i + 1], grid[i], rtol=1e-15, xtol=1e-300))
    taus = sorted([-1.0 / r for r in roots], reverse=True)
    no_soma = [seg.tau / (1.0 + (n * math.pi / X) ** 2) for n in range(len(taus))]
    return Rin_soma, Rin_end, taus, no_soma


def killed_cable_textbook(nrn, s_min):
    seg, X, Ltot = cable_params(nrn)
    G, Gs, Cs = seg.Ginf, nrn.Gs, nrn.Cs
    Rin_soma = 1.0 / (Gs + G / math.tanh(X))
    def F(s):
        g2 = 1.0 + s * seg.tau
        if g2 >= 0:
            g = math.sqrt(g2)
            return (Gs + s * Cs) * math.tanh(g * X) + G * g
        w = math.sqrt(-g2)
        return (Gs + s * Cs) * math.sin(w * X) + G * w * math.cos(w * X)
    grid = -np.geomspace(1e-4 / seg.tau, -s_min, 20000)
    vals = np.array([F(x) for x in grid])
    roots = []
    for i in range(len(grid) - 1):
        if vals[i] * vals[i + 1] < 0:
            roots.append(scipy.optimize.brentq(F, grid[i + 1], grid[i], rtol=1e-15, xtol=1e-300))
    taus = sorted([-1.0 / r for r in roots], reverse=True)
    no_soma = [seg.tau / (1.0 + ((n + 0.5) * math.pi / X) ** 2) for n in range(len(taus))]
    return Rin_soma, taus, no_soma


def generic_checks(obj, rep, nrn):
    # reciprocity of every impedance query that has its reverse in the list; DC vs AC(f=1 Hz)
    by = {}
    for q in rep["impedance"]:
        key = (q["source"]["segment"], q["source"]["fraction"], q["target"]["segment"],
               q["target"]["fraction"], q["frequency_Hz"])
        by[key] = q
    for key, q in by.items():
        rev = (key[2], key[3], key[0], key[1], key[4])
        if rev in by and rev > key:
            check("reciprocity |Z| %s" % (key,), q["magnitude_MOhm"], by[rev]["magnitude_MOhm"], 1e-12)
            check("reciprocity phase %s" % (key,), q["phase_deg"], by[rev]["phase_deg"], 1e-10, rel=False)
    # attenuation reciprocity identity: A(a->b) R_in(a) = A(b->a) R_in(b)  (= Z(a,b))
    rin = {(e["site"]["segment"], e["site"]["fraction"]): e["R_MOhm"] for e in rep["input_resistance"]}
    att = {}
    for e in rep["attenuation"]:
        att[(e["source"]["segment"], e["source"]["fraction"], e["target"]["segment"],
             e["target"]["fraction"])] = e["factor"]
    for k, a in att.items():
        rev = (k[2], k[3], k[0], k[1])
        if rev in att and rev > k and (k[0], k[1]) in rin and (k[2], k[3]) in rin:
            check("A(a->b)R(a) = A(b->a)R(b) %s" % (k,), a * rin[(k[0], k[1])],
                  att[rev] * rin[(k[2], k[3])], 1e-12)
    # guarantees on the mode list
    taus = [m["tau_ms"] for m in rep["modes"]]
    cs = [m["coefficient_MOhm"] for m in rep["modes"]]
    Rs = rin.get((0, 0))
    assert taus == sorted(taus, reverse=True)
    sep = min(abs(a - b) / a for a, b in zip(taus[:-1], taus[1:])) if len(taus) > 1 else 1
    print("  modes: %d, min consecutive separation %.2e, min |C|/R_in %.2e, closest to tau_min %.2e" %
          (len(taus), sep, min(abs(c) for c in cs) / Rs, min(abs(t - obj["tau_min_ms"]) / t for t in taus)))
    # sum of all coefficients with an extended mode list (internal tau floor)
    nr = R.Neuron(obj)
    log = []
    s_floor = -1.0 / (nr.tau_min / 400.0)
    modes = R.find_modes(nr, s_floor, log)
    tot = sum(c for _, c in modes) / 1e6
    # tail ~ sum 1/k^2 beyond K modes: extrapolate with the last 2 partial sums (Richardson in 1/K)
    K = len(modes)
    half = sum(c for _, c in modes[:K // 2]) / 1e6
    extrap = 2 * tot - half
    print("  sum of coefficients: %d modes -> %.9g, %d modes -> %.9g, Richardson %.9g, R_in(soma) %.9g" %
          (K // 2, half, K, tot, extrap, Rs))
    check("sum C_k (Richardson) vs R_in(soma)", extrap, Rs, 5e-3)
    for line in log:
        if "winding" in line or "compartmental vs" in line:
            print("   ", line)
    return Rs


def main():
    total = 0.0
    for name in NAMES:
        obj, rep, dt = run(name)
        total += dt
        nrn = R.Neuron(obj)
        s_min = -1.0 / nrn.tau_min
        print("%s: %.2f s, %d modes" % (name, dt, len(rep["modes"])))
        rin = [e["R_MOhm"] for e in rep["input_resistance"]]
        att = [e["factor"] for e in rep["attenuation"]]
        imp = rep["impedance"]
        taus = [m["tau_ms"] for m in rep["modes"]]
        if name == "cable_sealed":
            Rs, Re_, tb, ns = sealed_cable_textbook(nrn, s_min)
            check("R_in(soma) = 1/(G_s + G_inf tanh X)", rin[0], Rs / 1e6, 1e-14)
            check("R_in(end) textbook", rin[1], Re_ / 1e6, 1e-14)
            seg, X, L = cable_params(nrn)
            check("A(soma->end) = 1/cosh X", att[0], 1.0 / math.cosh(X), 1e-13)
            xi = 0.001 * 200e-4 / seg.lam
            check("A(soma->(1,0.001)) = cosh(X-xi)/cosh X", att[3], math.cosh(X - xi) / math.cosh(X), 1e-13)
            # textbook R_in at interior point xi of a sealed cable with soma at 0:
            G, Gs = seg.Ginf, nrn.Gs
            Yleft = G * (Gs + G * math.tanh(xi)) / (G + Gs * math.tanh(xi))
            Yright = G * math.tanh(X - xi)
            check("R_in((1,0.001)) textbook", rin[3], 1.0 / (Yleft + Yright) / 1e6, 1e-14)
            check("|Z(soma,soma,1 Hz)| ~ R_in(soma) (approx)", imp[5]["magnitude_MOhm"], rin[0], 1e-2)
            for k, (t, t0) in enumerate(zip(taus, tb)):
                check("tau_%d exact-with-soma condition" % k, t, t0 * 1e3, 1e-12)
            for k, (t, t0) in enumerate(zip(taus, ns)):
                check("tau_%d vs no-soma formula (approx)" % k, t, t0 * 1e3, 0.15)
            # no-soma coefficients: C_0 = Rm/(pi d L), C_n = 2 C_0 tau_n/tau_0 (approx, soma 3 %)
            C0 = seg.Rm / (math.pi * seg.d * L) / 1e6
            cs = [m["coefficient_MOhm"] for m in rep["modes"]]
            check("C_0 vs Rm/(pi d L) (approx)", cs[0], C0, 0.05)
            check("C_1 vs 2 C_0 tau_1/tau_0 (approx)", cs[1], 2 * C0 * ns[1] / ns[0], 0.1)
        if name == "cable_killed":
            Rs, tb, ns = killed_cable_textbook(nrn, s_min)
            seg, X, L = cable_params(nrn)
            check("R_in(soma) = 1/(G_s + G_inf coth X)", rin[0], Rs / 1e6, 1e-13)
            xi = 0.5 * 250e-4 / seg.lam + 150e-4 / seg.lam
            check("A(soma->(2,0.5)) = sinh(X-xi)/sinh X", att[0], math.sinh(X - xi) / math.sinh(X), 1e-13)
            xi9 = (150 + 250 + 0.9 * 200) * 1e-4 / seg.lam
            check("A(soma->(3,0.9)) = sinh(X-xi)/sinh X", att[2], math.sinh(X - xi9) / math.sinh(X), 1e-13)
            for k, (t, t0) in enumerate(zip(taus, tb)):
                check("tau_%d exact-with-soma condition" % k, t, t0 * 1e3, 1e-12)
            for k, (t, t0) in enumerate(zip(taus, ns)):
                check("tau_%d vs no-soma formula (approx)" % k, t, t0 * 1e3, 0.15)
        if name in ("rall_exact", "rall_perturbed"):
            s0, s1, s2 = nrn.segs[1], nrn.segs[2], nrn.segs[3]
            Xeq = s0.L / s0.lam + s1.L / s1.lam
            Req = 1.0 / (nrn.Gs + s0.Ginf * math.tanh(Xeq)) / 1e6
            tol = 1e-13 if name == "rall_exact" else 5e-3
            check("R_in(soma) = equivalent cylinder", rin[0], Req, tol)
            # attenuation soma -> each tip equals the equivalent cylinder's 1/cosh(Xeq)
            check("A(soma->tip2) = 1/cosh Xeq", att[0], 1.0 / math.cosh(Xeq), tol)
            check("A(soma->tip3) = 1/cosh Xeq", att[1], 1.0 / math.cosh(Xeq), tol)
            # AC: equivalent cylinder input impedance at 100 Hz
            s = 1j * 2 * math.pi * 100
            g = np.sqrt(1 + s * s0.tau)
            Zeq = 1.0 / (nrn.Gs + s * nrn.Cs + s0.Ginf * g * np.tanh(g * Xeq)) / 1e6
            check("|Z(soma,100 Hz)| = equivalent cylinder", imp[0]["magnitude_MOhm"], abs(Zeq), tol)
            check("phase Z(soma,100 Hz) = equivalent cylinder", imp[0]["phase_deg"],
                  math.degrees(np.angle(Zeq)), tol * 100, rel=False)
            # both tips see the same transfer impedance from the soma
            check("Z(soma->tip2) = Z(soma->tip3) at 300 Hz", imp[1]["magnitude_MOhm"],
                  imp[2]["magnitude_MOhm"], tol)
            if name == "rall_exact":
                # modes of the equivalent cylinder (visible ones); hidden modes have C = 0
                def F(sv):
                    g2 = 1.0 + sv * s0.tau
                    if g2 >= 0:
                        gg = math.sqrt(g2)
                        return nrn.Gs + sv * nrn.Cs + s0.Ginf * gg * math.tanh(gg * Xeq)
                    w = math.sqrt(-g2)
                    return (nrn.Gs + sv * nrn.Cs) * math.cos(w * Xeq) - s0.Ginf * w * math.sin(w * Xeq)
                grid = -np.geomspace(1e-4 / s0.tau, -s_min, 20000)
                vals = np.array([F(x) for x in grid])
                roots = [scipy.optimize.brentq(F, grid[i + 1], grid[i], rtol=1e-15, xtol=1e-300)
                         for i in range(len(grid) - 1) if vals[i] * vals[i + 1] < 0]
                teq = sorted([-1e3 / r for r in roots], reverse=True)
                print("  equivalent-cylinder taus:", ["%.10g" % t for t in teq])
                print("  reported modes:", [("%.10g" % m["tau_ms"], "%.3e" % m["coefficient_MOhm"]) for m in rep["modes"]])
        if name == "near_symmetric":
            cs = [m["coefficient_MOhm"] for m in rep["modes"]]
            print("  coefficients:", ["%.4e" % c for c in cs])
        if name == "tree12_soma":
            check("A(a->a) = 1 for coincident pair", att[1], 1.0, 0)
            check("R_in(soma) = R_in((1,0))", rin[0], rin[1], 0)
            check("|Z(a->a, 1 Hz)| vs R_in (7,1) within 1e-3", imp[1]["magnitude_MOhm"], rin[3], 1e-3)
        Rs = generic_checks(obj, rep, nrn)
    print("total runtime %.1f s; failures: %d" % (total, fails))


if __name__ == "__main__":
    main()
