#!/usr/bin/env python3
"""Internal checks of Reference A on the test frames (writes tests/check_results.json).

    python run_checks.py            (from anywhere; uses the venv interpreter that runs it)

1. report format; runtime; determinism (two runs in fresh directories, verifier environment)
2. closed forms: cantilever and simply supported beam frequencies (bending and axial), static
   deflections, cantilever tip receptance; clamped-clamped member-local modes
3. 60-digit re-evaluation of every frequency and harmonic amplitude (hp_check.py)
4. reciprocity of the harmonic response
5. h-version cubic Hermite FE converging to the exact roots (observed order ~4)
6. block LDL^T count == dense Bunch-Kaufman LDL^T inertia of the assembled FE matrix
7. Taylor-series propagator vs scipy.linalg.expm; det G roots with either
8. statics vs the classical stiffness method, harmonic vs the p-version FE (from --diag)
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time

import numpy as np
import scipy.linalg as sla
from scipy.optimize import brentq

HERE = os.path.dirname(os.path.abspath(__file__))
REFDIR = os.path.dirname(HERE)
sys.path.insert(0, REFDIR)
import reference as R  # noqa: E402

PY = sys.executable
FR_DIR = os.path.join(HERE, "frames")
REP_DIR = os.path.join(HERE, "reports")
TWO_PI = 2 * math.pi
ENV = {"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": "0", "OPENBLAS_NUM_THREADS": "1",
       "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}


def run_ref(frame, out, diag=None):
    wd = tempfile.mkdtemp()
    env = dict(ENV, HOME=wd, TMPDIR=wd)
    cmd = [PY, os.path.join(REFDIR, "reference.py"), "--frame", frame, "--output", out]
    if diag:
        cmd += ["--diag", diag]
    t0 = time.time()
    p = subprocess.run(cmd, cwd=wd, env=env, capture_output=True)
    dt = time.time() - t0
    shutil.rmtree(wd, ignore_errors=True)
    return p.returncode, dt


def check_format(raw, rep):
    keys = {"frame_id", "static", "frequencies_Hz", "count_below", "harmonic"}
    assert set(rep) == keys
    assert rep["frame_id"] == raw["frame_id"]
    assert len(rep["static"]) == len(raw["static_query_nodes"])
    for s, n in zip(rep["static"], raw["static_query_nodes"]):
        assert set(s) == {"node", "ux", "uy", "rz"} and s["node"] == n
        assert all(math.isfinite(s[k]) for k in ("ux", "uy", "rz"))
    assert len(rep["frequencies_Hz"]) == raw["n_modes"]
    f = rep["frequencies_Hz"]
    assert all(math.isfinite(v) and v > 0 for v in f) and all(f[i] < f[i + 1] for i in range(len(f) - 1))
    assert isinstance(rep["count_below"], int)
    assert len(rep["harmonic"]) == len(raw["harmonic_queries"])
    for h, q in zip(rep["harmonic"], raw["harmonic_queries"]):
        assert set(h) == set(q) | {"U"} and all(h[k] == q[k] for k in q) and math.isfinite(h["U"])
    return True


# ----------------------------------------------------------------------------- closed forms

def cc_beta(n):
    g = (2 * n + 1) * math.pi / 2
    return brentq(lambda b: math.cos(b) - 1.0 / math.cosh(b), g - 0.5, g + 0.5, xtol=1e-15)


def cf_beta(n):
    g = (2 * n - 1) * math.pi / 2
    if n == 1:
        g = 1.875
    return brentq(lambda b: math.cos(b) + 1.0 / math.cosh(b), g - 0.5, g + 0.5, xtol=1e-15)


def rel(a, b):
    return abs(a - b) / abs(b)


def closed_forms(results):
    out = {}
    # t1: cantilever of 3 collinear members along 30 degrees
    raw = json.load(open(os.path.join(FR_DIR, "t1_cantilever3.json")))
    rep = json.load(open(os.path.join(REP_DIR, "t1_cantilever3.json")))
    m = raw["members"][0]
    E, A, I, rho = m["E"], m["A"], m["I"], m["rho"]
    L = 4.7
    cb = math.sqrt(E * I / (rho * A)) / (TWO_PI * L * L)
    fb = [cf_beta(n) ** 2 * cb for n in range(1, 16)]
    fa = [(2 * n - 1) * math.pi / 2 * math.sqrt(E / rho) / (TWO_PI * L) for n in range(1, 8)]
    allf = sorted(fb + fa)
    errs = [rel(a, b) for a, b in zip(rep["frequencies_Hz"], allf)]
    cnt = sum(1 for v in allf if v <= raw["f_max_Hz"])
    out["t1_frequencies_max_rel"] = max(errs)
    out["t1_frequencies_first_bending_betaL"] = [cf_beta(n) for n in (1, 2, 3)]
    out["t1_count_below_ok"] = cnt == rep["count_below"]
    th = math.radians(30.0)
    c, s = math.cos(th), math.sin(th)
    P, Nax, q = 18500.0, 240000.0, 2650.0
    EI, EA = E * I, E * A
    errs = []
    scale = {"ux": 0.0, "uy": 0.0, "rz": 0.0}
    vals = []
    for sq, x in zip(rep["static"], [1.55, 3.05, 4.7]):
        v = P * x * x * (3 * L - x) / (6 * EI) + q * x * x * (6 * L * L - 4 * L * x + x * x) / (24 * EI)
        t = P * x * (2 * L - x) / (2 * EI) + q * x * (3 * L * L - 3 * L * x + x * x) / (6 * EI)
        u = Nax * x / EA
        ex = {"ux": c * u - s * v, "uy": s * u + c * v, "rz": t}
        vals.append((sq, ex))
        for k in ex:
            scale[k] = max(scale[k], abs(ex[k]))
    for sq, ex in vals:
        for k in ex:
            errs.append(abs(sq[k] - ex[k]) / scale[k])
    out["t1_static_max_err_rel_to_kind_max"] = max(errs)
    # tip receptances at 23.7 Hz (transverse cantilever, axial fixed-free bar)
    om = TWO_PI * 23.7
    lam = L * (rho * A * om * om / EI) ** 0.25
    al = om * L * math.sqrt(rho / E)
    at = (math.sin(lam) * math.cosh(lam) - math.cos(lam) * math.sinh(lam)) / (
        EI * (lam / L) ** 3 * (1 + math.cos(lam) * math.cosh(lam)))
    aa = L * math.tan(al) / (EA * al)
    U1 = 1000.0 * (at * c * c + aa * s * s)
    U2 = 1000.0 * c * s * (aa - at)
    out["t1_harmonic_tip_receptance_rel"] = [rel(rep["harmonic"][0]["U"], U1),
                                             rel(rep["harmonic"][1]["U"], U2)]
    # t2: simply supported beam, pin at node 1, roller at node 3
    raw = json.load(open(os.path.join(FR_DIR, "t2_ssbeam.json")))
    rep = json.load(open(os.path.join(REP_DIR, "t2_ssbeam.json")))
    m = raw["members"][0]
    E, A, I, rho = m["E"], m["A"], m["I"], m["rho"]
    L, a = 6.3, 2.9
    b = L - a
    cb = math.sqrt(E * I / (rho * A)) / (TWO_PI * L * L)
    fb = [(n * math.pi) ** 2 * cb for n in range(1, 12)]
    fa = [(2 * n - 1) * math.pi / 2 * math.sqrt(E / rho) / (TWO_PI * L) for n in range(1, 8)]
    allf = sorted(fb + fa)
    out["t2_frequencies_max_rel"] = max(rel(x, y) for x, y in zip(rep["frequencies_Hz"], allf))
    out["t2_count_below_ok"] = sum(1 for v in allf if v <= raw["f_max_Hz"]) == rep["count_below"]
    EI, EA = E * I, E * A
    P, q, Fx = 36500.0, 4180.0, 61000.0
    v = -q * a * (L ** 3 - 2 * L * a * a + a ** 3) / (24 * EI) - P * b * a * (L * L - b * b - a * a) / (6 * EI * L)
    t = -q * (L ** 3 - 6 * L * a * a + 4 * a ** 3) / (24 * EI) - P * b * (L * L - b * b - 3 * a * a) / (6 * EI * L)
    u = Fx * a / EA
    sq = rep["static"][0]
    out["t2_static_rel"] = {"ux": rel(sq["ux"], u), "uy": rel(sq["uy"], v), "rz": rel(sq["rz"], t)}
    # t4: member 1 between two fixed supports: its local modes must be in the list
    raw = json.load(open(os.path.join(FR_DIR, "t4_fixedfixed.json")))
    rep = json.load(open(os.path.join(REP_DIR, "t4_fixedfixed.json")))
    m = raw["members"][0]
    E, A, I, rho = m["E"], m["A"], m["I"], m["rho"]
    L = 11.6
    cb = math.sqrt(E * I / (rho * A)) / (TWO_PI * L * L)
    loc = [cc_beta(n) ** 2 * cb for n in range(1, 15)] + [n * math.sqrt(E / rho) / (2 * L) for n in range(1, 4)]
    loc = sorted(v for v in loc if v <= rep["frequencies_Hz"][-1] * 1.0001)
    f = rep["frequencies_Hz"]
    matches = [min(rel(x, v) for x in f) for v in loc]
    out["t4_local_modes_found"] = len(loc)
    out["t4_local_modes_max_rel"] = max(matches)
    out["t4_clamped_betaL"] = [cc_beta(1), cc_beta(2)]
    # t8: every frequency up to f_max is a member-local mode (closed form)
    raw = json.load(open(os.path.join(FR_DIR, "t8_local40.json")))
    rep = json.load(open(os.path.join(REP_DIR, "t8_local40.json")))
    allf = []
    for m in raw["members"][:3]:
        n1, n2 = raw["nodes"][m["i"] - 1], raw["nodes"][m["j"] - 1]
        L = math.hypot(n2["x"] - n1["x"], n2["y"] - n1["y"])
        cb = math.sqrt(m["E"] * m["I"] / (m["rho"] * m["A"])) / (TWO_PI * L * L)
        allf += [cc_beta(n) ** 2 * cb for n in range(1, 16)]
        allf += [n * math.sqrt(m["E"] / m["rho"]) / (2 * L) for n in range(1, 4)]
    allf.sort()
    out["t8_frequencies_max_rel"] = max(rel(x, y) for x, y in zip(rep["frequencies_Hz"], allf))
    out["t8_count_below_ok"] = sum(1 for v in allf if v <= raw["f_max_Hz"]) == rep["count_below"]
    out["t8_pair_gap_rel"] = rep["frequencies_Hz"][7] / rep["frequencies_Hz"][6] - 1
    fr = R.Frame(raw)
    out["t8_lambda_at_fmax"] = float(np.max(fr.lam(TWO_PI * raw["f_max_Hz"])))
    results["closed_forms"] = out


# ----------------------------------------------------------------------------- h-version FE

def hfe_eigs(fr, ne, K):
    """h-version cubic Hermite FE (bending and axial Hermite cubics, ne elements per member),
    dense generalized eigenproblem; lowest K frequencies in Hz."""
    Mref, K1, K2 = hermite_refs()
    ndof = 3 * fr.N
    extra = []
    nint_total = 0
    blocks = []
    for k in range(fr.M):
        L = fr.L[k]
        h = L / ne
        # local chain dofs per element node p: (u, h u', v, h th); total 4(ne+1)
        nd = 4 * (ne + 1)
        Kl = np.zeros((nd, nd))
        Ml = np.zeros((nd, nd))
        for e in range(ne):
            ia = [4 * e, 4 * e + 1, 4 * e + 4, 4 * e + 5]
            ib = [4 * e + 2, 4 * e + 3, 4 * e + 6, 4 * e + 7]
            Kl[np.ix_(ia, ia)] += fr.EA[k] / h * K1
            Ml[np.ix_(ia, ia)] += fr.rA[k] * h * Mref
            Kl[np.ix_(ib, ib)] += fr.EI[k] / h ** 3 * K2
            Ml[np.ix_(ib, ib)] += fr.rA[k] * h * Mref
        blocks.append((Kl, Ml))
        nint_total += nd - 6
    n = ndof + nint_total
    Kg = np.zeros((n, n))
    Mg = np.zeros((n, n))
    off = ndof
    for k, (Kl, Ml) in enumerate(blocks):
        nd = Kl.shape[0]
        c, s, L = fr.c[k], fr.s[k], fr.L[k]
        h = L / ne
        Tm = np.zeros((nd, n))
        i, j = fr.mi[k], fr.mj[k]
        Rm = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])
        for endn, node in ((0, i), (ne, j)):
            base = 4 * endn
            Tm[base, 3 * node:3 * node + 3] = Rm[0]         # u
            Tm[base + 2, 3 * node:3 * node + 3] = Rm[1]     # v
            Tm[base + 3, 3 * node + 2] = h                  # h theta
        q = off
        for r in range(nd):
            if r in (0, 2, 3, 4 * ne, 4 * ne + 2, 4 * ne + 3):
                continue
            Tm[r, q] = 1.0
            q += 1
        off = q
        Kg += Tm.T @ Kl @ Tm
        Mg += Tm.T @ Ml @ Tm
    for nd_ in range(fr.N):
        Mg[3 * nd_, 3 * nd_] += fr.mass[nd_]
        Mg[3 * nd_ + 1, 3 * nd_ + 1] += fr.mass[nd_]
    keep = np.concatenate([np.nonzero(fr.free)[0], np.arange(ndof, n)])
    ev = sla.eigh(Kg[np.ix_(keep, keep)], Mg[np.ix_(keep, keep)], eigvals_only=True,
                  subset_by_index=[0, K - 1])
    return np.sqrt(ev) / TWO_PI


def hermite_refs():
    xg, wg = np.polynomial.legendre.leggauss(6)
    t = (xg + 1) / 2
    w = wg / 2
    H = np.array([1 - 3 * t ** 2 + 2 * t ** 3, t - 2 * t ** 2 + t ** 3, 3 * t ** 2 - 2 * t ** 3, -t ** 2 + t ** 3])
    dH = np.array([-6 * t + 6 * t ** 2, 1 - 4 * t + 3 * t ** 2, 6 * t - 6 * t ** 2, -2 * t + 3 * t ** 2])
    ddH = np.array([-6 + 12 * t, -4 + 6 * t, 6 - 12 * t, -2 + 6 * t])
    return (H * w) @ H.T, (dH * w) @ dH.T, (ddH * w) @ ddH.T


def h_convergence(results):
    out = {}
    for fid, K in (("t3_portal", 6), ("t6_masses", 6), ("t1_cantilever3", 5)):
        raw = json.load(open(os.path.join(FR_DIR, fid + ".json")))
        rep = json.load(open(os.path.join(REP_DIR, fid + ".json")))
        fr = R.Frame(raw)
        ex = np.array(rep["frequencies_Hz"][:K])
        rows = []
        prev = None
        for ne in (2, 4, 8, 16):
            e = hfe_eigs(fr, ne, K)
            err = e / ex - 1.0
            order = None if prev is None else [float(math.log2(a / b)) if b > 0 and a > 0 else None
                                               for a, b in zip(prev, err)]
            rows.append({"elements_per_member": ne, "rel_err": [float(v) for v in err],
                         "observed_order": order})
            prev = err
        out[fid] = rows
    results["h_version_fe_convergence"] = out


# ----------------------------------------------------------------------------- LDL equivalence

def assembled_pfe(fr, pb, pa, omega):
    """Full assembled p-version FE matrix K - omega^2 M (node dofs + all bubbles)."""
    Mb, Kb4, Ma, Ka2 = R.ref_matrices(pb, pa)
    ndof = 3 * fr.N
    nb_b, nb_a = pb - 3, pa - 1
    n = ndof + fr.M * (nb_b + nb_a)
    Kg = np.zeros((n, n))
    Mg = np.zeros((n, n))
    for k in range(fr.M):
        L = fr.L[k]
        mu0 = fr.rA[k] * L / 2
        kb = fr.EI[k] * (2 / L) ** 3
        ka = fr.EA[k] * (2 / L)
        # local dofs: [v0, (L/2)th0, v1, (L/2)th1, bubbles_b..., u0, u1, bubbles_a...]
        Kb = np.zeros((pb + 1, pb + 1))
        Kb[:4, :4] = Kb4
        Kb[4:, 4:] = np.eye(nb_b)
        Ka = np.zeros((pa + 1, pa + 1))
        Ka[:2, :2] = Ka2
        Ka[2:, 2:] = np.eye(nb_a)
        c, s = fr.c[k], fr.s[k]
        i, j = fr.mi[k], fr.mj[k]
        Tb = np.zeros((pb + 1, n))
        Ta = np.zeros((pa + 1, n))
        # v = -s ux + c uy ; slope dof = (L/2) rz
        Tb[0, 3 * i] = -s; Tb[0, 3 * i + 1] = c
        Tb[1, 3 * i + 2] = L / 2
        Tb[2, 3 * j] = -s; Tb[2, 3 * j + 1] = c
        Tb[3, 3 * j + 2] = L / 2
        base = ndof + k * (nb_b + nb_a)
        for q in range(nb_b):
            Tb[4 + q, base + q] = 1.0
        Ta[0, 3 * i] = c; Ta[0, 3 * i + 1] = s
        Ta[1, 3 * j] = c; Ta[1, 3 * j + 1] = s
        for q in range(nb_a):
            Ta[2 + q, base + nb_b + q] = 1.0
        Kg += Tb.T @ (kb * Kb) @ Tb + Ta.T @ (ka * Ka) @ Ta
        Mg += Tb.T @ (mu0 * Mb) @ Tb + Ta.T @ (mu0 * Ma) @ Ta
    for nd_ in range(fr.N):
        Mg[3 * nd_, 3 * nd_] += fr.mass[nd_]
        Mg[3 * nd_ + 1, 3 * nd_ + 1] += fr.mass[nd_]
    keep = np.concatenate([np.nonzero(fr.free)[0], np.arange(ndof, n)])
    A = (Kg - omega ** 2 * Mg)[np.ix_(keep, keep)]
    return A


def ldl_negatives(A):
    lu, d, perm = sla.ldl(A, lower=True)
    neg = 0
    i = 0
    n = d.shape[0]
    while i < n:
        if i + 1 < n and d[i + 1, i] != 0.0:
            ev = np.linalg.eigvalsh(d[i:i + 2, i:i + 2])
            neg += int(np.sum(ev < 0))
            i += 2
        else:
            neg += int(d[i, i] < 0)
            i += 1
    return neg


def ldl_equivalence(results):
    out = {}
    for fid in ("t3_portal", "t5_closepair", "t6_masses"):
        raw = json.load(open(os.path.join(FR_DIR, fid + ".json")))
        rep = json.load(open(os.path.join(REP_DIR, fid + ".json")))
        fr = R.Frame(raw)
        pb, pa = 30, 22
        fe = R.FrameFE(fr, np.full(fr.M, pb), np.full(fr.M, pa))
        f = rep["frequencies_Hz"]
        pts = [0.5 * f[0]] + [0.5 * (f[q] + f[q + 1]) for q in range(len(f) - 1)] + [raw["f_max_Hz"], 1.3 * f[-1]]
        agree = []
        for fh in pts:
            om = TWO_PI * fh
            agree.append([fe.count(om), ldl_negatives(assembled_pfe(fr, pb, pa, om))])
        out[fid] = {"all_equal": all(a == b for a, b in agree), "counts": agree}
    results["block_vs_dense_ldl"] = out


# ----------------------------------------------------------------------------- expm cross-check

def expm_check(results):
    out = {}
    for fn in sorted(os.listdir(FR_DIR)):
        raw = json.load(open(os.path.join(FR_DIR, fn)))
        rep = json.load(open(os.path.join(REP_DIR, fn)))
        fr = R.Frame(raw)
        om = TWO_PI * max(rep["frequencies_Hz"][-1], raw["f_max_Hz"])
        _, _, P1 = R.bending_bases(fr, om)
        _, _, P2 = R.bending_bases(fr, om, use_scipy=True)
        d_prop = float(np.max(np.abs(P1 - P2)) / np.max(np.abs(P2)))
        # roots of det G with the scipy propagator, started from the reported frequencies
        devs = []
        for f in rep["frequencies_Hz"][:4]:
            w = TWO_PI * f

            def g(x):
                G = R.assemble_G(fr, x, use_scipy=True)
                s, l = R.signed_logdet(G * R.row_scale(G)[:, None])
                return s * math.exp(min(l - l0, 700))
            _, l0 = R.det_eval(fr, w * (1 + 1e-9))
            lo, hi = w * (1 - 1e-9), w * (1 + 1e-9)
            r = brentq(g, lo, hi, xtol=1e-300, rtol=8.9e-16)
            devs.append(abs(r / w - 1))
        out[raw["frame_id"]] = {"propagator_max_rel_diff": d_prop, "root_max_rel_diff": max(devs)}
    results["taylor_vs_scipy_expm"] = out


# ----------------------------------------------------------------------------- reciprocity

def reciprocity(results):
    pairs = {"t3_portal": [(0, 1), (2, 3)], "t6_masses": [(0, 1), (2, 3)], "t7_slender_stocky": [(0, 1)],
             "t9_stress16": [(0, 1)], "t10_extreme": [(0, 1)]}
    out = {}
    for fid, pl in pairs.items():
        rep = json.load(open(os.path.join(REP_DIR, fid + ".json")))
        h = rep["harmonic"]
        out[fid] = [[h[a]["U"], h[b]["U"], abs(h[a]["U"] - h[b]["U"]) / abs(h[a]["U"])] for a, b in pl]
    # t1: tip ux <- uy force vs tip uy <- ux force (extra evaluation at 23.7 Hz)
    raw = json.load(open(os.path.join(FR_DIR, "t1_cantilever3.json")))
    fr = R.Frame(raw)
    om = TWO_PI * 23.7
    D1, _ = R.harmonic(fr, om, 3, 0, 1000.0)
    D2, _ = R.harmonic(fr, om, 3, 1, 1000.0)
    D3, _ = R.harmonic(fr, om, 1, 2, 1000.0)
    out["t1_cantilever3"] = [[float(D1[3, 1]), float(D2[3, 0]), float(abs(D1[3, 1] - D2[3, 0]) / abs(D1[3, 1]))],
                             [float(D3[3, 1]), float(D2[1, 2]), float(abs(D3[3, 1] - D2[1, 2]) / abs(D3[3, 1]))]]
    results["reciprocity"] = out


def main():
    results = {"frames": {}}
    tmp = tempfile.mkdtemp()
    for fn in sorted(os.listdir(FR_DIR)):
        fid = fn[:-5]
        fpath = os.path.join(FR_DIR, fn)
        out1 = os.path.join(REP_DIR, fn)
        out2 = os.path.join(tmp, fn)
        diag = os.path.join(tmp, fid + ".diag.json")
        rc1, t1 = run_ref(fpath, out1, diag)
        rc2, t2 = run_ref(fpath, out2)
        same = open(out1, "rb").read() == open(out2, "rb").read()
        raw = json.load(open(fpath))
        rep = json.load(open(out1))
        d = json.load(open(diag))
        hp = json.loads(subprocess.run([PY, os.path.join(HERE, "hp_check.py"), fpath, out1],
                                       capture_output=True, text=True).stdout)
        fq = d["frequencies"]
        results["frames"][fid] = {
            "exit_codes": [rc1, rc2], "runtime_s": [round(t1, 2), round(t2, 2)],
            "deterministic": same, "format_ok": check_format(raw, rep),
            "frequencies_Hz": rep["frequencies_Hz"], "count_below": rep["count_below"],
            "hp_freq_max_rel": max(v[2] for v in hp["freq"]),
            "hp_harmonic_max_rel": max(v[2] for v in hp["harmonic"]),
            "hp_static_rel_to_kind_max": hp["static"],
            "det_roots_vs_pfe_fine_max_rel": fq["max_rel_exact_vs_fe_fine"],
            "pfe_fine_vs_coarse_max_rel": fq["max_rel_fe_fine_vs_coarse"],
            "certified": fq["certified"], "count_checks": fq["count_checks"],
            "count_below_checks": fq["count_below_checks"],
            "count_below_det_check": fq["count_below_det_check"],
            "static_vs_classical_stiffness": d["static_vs_classical_stiffness"],
            "harmonic_vs_pfe_rel": [v[2] for v in d["harmonic_vs_fe"]],
            "warnings": d.get("warnings", []),
        }
        print(fid, "done", round(t1, 2), "s", flush=True)
    shutil.rmtree(tmp, ignore_errors=True)
    closed_forms(results)
    reciprocity(results)
    h_convergence(results)
    ldl_equivalence(results)
    expm_check(results)
    with open(os.path.join(HERE, "check_results.json"), "w") as f:
        json.dump(results, f, indent=1)
        f.write("\n")
    print(json.dumps({k: v for k, v in results.items() if k != "frames"}, indent=1)[:6000])


if __name__ == "__main__":
    main()
