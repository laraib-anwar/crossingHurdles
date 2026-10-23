#!/usr/bin/env python
"""Reference B: compartmental (finite-volume) referee for CABLE_SPEC reports.

Method (deliberately different from analytic cable theory): the whole tree is discretised into
compartments with nodes at compartment boundaries (vertex-centred finite volume, half-compartment
membrane at every segment end, shared node at branch points and at the soma). The scheme is
second-order accurate; it is evaluated on a nested family of grids (h0, h0/2, h0/4, h0/8) and
Richardson-extrapolated. Every queried location is placed exactly on a node by splitting the
segment at the queried fractions before discretising.

  DC      : G V = e_a          (sparse LU)
  AC      : (G + j w C) V = e_a (sparse complex LU)
  modes   : G v = mu C v        (ARPACK shift-invert + Rayleigh-quotient refinement; mode count
                                 cross-checked with a Sturm/inertia count by tree elimination)
  C_k     : tau_k v_k(soma)^2 / (v_k^T C v_k)
  transient: Crank-Nicolson with Rannacher start-up, Richardson in time, somatic unit step

Units inside: conductance uS, capacitance nF, time ms, current nA, voltage mV, resistance MOhm.
Membrane: area um^2 * 1e-2 / Rm -> uS; area * Cm * 1e-5 -> nF.
Axial   : 100 * pi d^2 / (4 Ri dx) -> uS (d, dx in um; Ri in ohm cm).

Usage:
  python referee.py --neuron N.json --report R.json [--out verdict.json] [--quiet]
  python referee.py --solve --neuron N.json --output R.json
"""
import argparse
import json
import math
import sys
import time
from collections import defaultdict

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

TOL_REL = 1e-6        # DC, AC magnitude, tau
TOL_PHASE = 1e-5      # degrees, absolute
TOL_COEF = 1e-6       # times R_in(soma)
TOL_TRANS = 1e-5      # times R_in(soma)
NODE_CAP = 20000
AC_NODE_CAP = 40000
AC_LAMBDA_RATIO = 8.0   # coarsest AC spacing is at most lambda/|gamma| / 8
EXTRA_MODES = 6


# ----------------------------------------------------------------------------- mesh

def _loc_key(loc):
    return (int(loc["segment"]), float(loc["fraction"]))


def all_locations(neuron):
    locs = list(neuron["input_resistance_sites"])
    for p in neuron["attenuation_pairs"]:
        locs += [p["source"], p["target"]]
    for q in neuron["impedance_queries"]:
        locs += [q["source"], q["target"]]
    return locs


class Mesh:
    """Compartmental mesh of the tree at refinement level `level` (spacing ~ h0 / 2**level)."""

    def __init__(self, neuron, level, h0):
        self.level = level
        soma = neuron["soma"]
        ds = float(soma["d_um"])
        area_s = math.pi * ds * ds
        gm = [area_s * 1e-2 / float(soma["Rm_ohm_cm2"]) + float(soma["shunt_nS"]) * 1e-3]
        cm = [area_s * float(soma["Cm_uF_cm2"]) * 1e-5]
        ga = [0.0]
        parent = [-1]
        killed = [False]
        distal = {0: 0}
        self.loc_node = {(0, 0.0): 0}
        fr = defaultdict(set)
        for loc in all_locations(neuron):
            s, f = _loc_key(loc)
            if s != 0:
                fr[s].add(f)
        mult = 2 ** level
        self.dx_min = math.inf
        self.dx_max = 0.0
        gm_a = [np.array(gm)]
        cm_a = [np.array(cm)]
        ga_a = [np.array(ga)]
        pa_a = [np.array(parent)]
        kill_nodes = []
        shunt_nodes = []
        count = 1
        for seg in neuron["segments"]:
            sid = int(seg["id"])
            L = float(seg["L_um"])
            d = float(seg["d_um"])
            Rm = float(seg["Rm_ohm_cm2"])
            Ri = float(seg["Ri_ohm_cm"])
            Cm = float(seg["Cm_uF_cm2"])
            bps = sorted({0.0, 1.0} | fr[sid])
            prox = distal[int(seg["parent"])]
            self.loc_node[(sid, 0.0)] = prox
            cur = prox
            k_ax = 100.0 * math.pi * d * d / (4.0 * Ri)
            gm_per_um = math.pi * d * 1e-2 / Rm
            cm_per_um = math.pi * d * Cm * 1e-5
            for a, b in zip(bps[:-1], bps[1:]):
                plen = (b - a) * L
                n = max(1, int(math.ceil(plen / h0 - 1e-9))) * mult
                dx = plen / n
                self.dx_min = min(self.dx_min, dx)
                self.dx_max = max(self.dx_max, dx)
                g = k_ax / dx
                base = count
                par = np.arange(base - 1, base + n - 1)
                par[0] = cur
                gmi = np.full(n, gm_per_um * dx)
                cmi = np.full(n, cm_per_um * dx)
                gmi[-1] = gm_per_um * dx / 2.0
                cmi[-1] = cm_per_um * dx / 2.0
                # the first existing node receives the proximal half compartment
                self._add_half(gm_a, cm_a, cur, gm_per_um * dx / 2.0, cm_per_um * dx / 2.0)
                gm_a.append(gmi)
                cm_a.append(cmi)
                ga_a.append(np.full(n, g))
                pa_a.append(par)
                count += n
                cur = count - 1
                self.loc_node[(sid, b)] = cur
            distal[sid] = cur
            end = seg["end"]
            if end is not None:
                if end["type"] == "killed":
                    kill_nodes.append(cur)
                elif end["type"] == "shunt":
                    shunt_nodes.append((cur, float(end["g_nS"]) * 1e-3))
                elif end["type"] != "sealed":
                    raise ValueError("unknown end type %r" % end["type"])
        gm = np.concatenate(gm_a)
        cm = np.concatenate(cm_a)
        ga = np.concatenate(ga_a)
        parent = np.concatenate(pa_a)
        for node, g in shunt_nodes:
            gm[node] += g
        n_all = gm.size
        keep = np.ones(n_all, dtype=bool)
        keep[kill_nodes] = False
        self.killed_nodes = set(kill_nodes)
        diag = gm + ga
        np.add.at(diag, parent[1:], ga[1:])
        rows = np.concatenate([np.arange(n_all), np.arange(1, n_all), parent[1:]])
        cols = np.concatenate([np.arange(n_all), parent[1:], np.arange(1, n_all)])
        vals = np.concatenate([diag, -ga[1:], -ga[1:]])
        G_full = sp.coo_matrix((vals, (rows, cols)), shape=(n_all, n_all)).tocsc()
        idx = np.flatnonzero(keep)
        self.new_index = -np.ones(n_all, dtype=int)
        self.new_index[idx] = np.arange(idx.size)
        self.G = G_full[idx][:, idx].tocsc()
        self.C = cm[idx]
        self.n = idx.size
        # tree arrays on kept nodes (killed nodes are leaves, so parents stay kept)
        self.parent = np.where(parent[idx] >= 0, self.new_index[np.maximum(parent[idx], 0)], -1)
        self.diag = diag[idx]
        self.off = ga[idx]          # conductance to parent (0 for the soma)
        self._lu = None

    @staticmethod
    def _add_half(gm_a, cm_a, node, dg, dc):
        # locate node in the chunk list and add the half compartment
        off = 0
        for i, arr in enumerate(gm_a):
            if node < off + arr.size:
                gm_a[i] = arr.copy()
                gm_a[i][node - off] += dg
                cm_a[i] = cm_a[i].copy()
                cm_a[i][node - off] += dc
                return
            off += arr.size
        raise IndexError(node)

    def node(self, loc):
        k = _loc_key(loc)
        full = self.loc_node[k]
        return self.new_index[full]      # -1 if the node is a killed terminal

    # ------------------------------------------------------------------ DC / AC
    def lu(self):
        if self._lu is None:
            self._lu = spla.splu(self.G)
        return self._lu

    def dc_solve(self, src):
        e = np.zeros(self.n)
        e[src] = 1.0
        V = self.lu().solve(e)
        # one step of iterative refinement
        r = e - self.G @ V
        V = V + self.lu().solve(r)
        return V

    def ac_solve(self, src, f_Hz):
        w = 2.0 * math.pi * f_Hz * 1e-3     # rad/ms
        A = (self.G + 1j * w * sp.diags(self.C)).tocsc()
        lu = spla.splu(A)
        e = np.zeros(self.n, dtype=complex)
        e[src] = 1.0
        V = lu.solve(e)
        r = e - A @ V
        V = V + lu.solve(r)
        return V

    # ------------------------------------------------------------------ modes
    def sturm_count(self, mu):
        """Number of eigenvalues of G v = mu C v strictly below mu (Sylvester inertia of G - mu C,
        LDL^T by elimination of the tree from the leaves)."""
        d = (self.diag - mu * self.C).tolist()
        off = self.off.tolist()
        par = self.parent.tolist()
        neg = 0
        for i in range(self.n - 1, 0, -1):
            di = d[i]
            if di < 0:
                neg += 1
            if di == 0.0:
                di = 1e-300
            d[par[i]] -= off[i] * off[i] / di
        if d[0] < 0:
            neg += 1
        return neg

    def modes(self, K):
        """K slowest modes: returns (tau desc, coefficient) arrays."""
        K = int(min(K, self.n - 2))
        M = sp.diags(self.C)
        vals, vecs = spla.eigsh(self.G, k=K, M=M.tocsc(), sigma=0.0, which="LM", tol=0.0,
                                maxiter=20000)
        # Rayleigh-quotient refinement (second-order accurate in the eigenvector error)
        GV = self.G @ vecs
        num = np.einsum("ij,ij->j", vecs, GV)
        den = np.einsum("ij,ij->j", vecs, vecs * self.C[:, None])
        mu = num / den
        order = np.argsort(mu)
        mu = mu[order]
        vecs = vecs[:, order]
        den = den[order]
        tau = 1.0 / mu
        coef = tau * vecs[0, :] ** 2 / den
        return tau, coef

    # ------------------------------------------------------------------ transient
    def step_response(self, dt, nsteps, record_steps):
        """Somatic voltage for a unit (1 nA) current step at the soma. Crank-Nicolson with a
        Rannacher start (first two steps as implicit Euler half-steps). Returns V_soma at the
        given step indices."""
        Cd = sp.diags(self.C)
        e = np.zeros(self.n)
        e[0] = 1.0
        A_cn = (Cd / dt + 0.5 * self.G).tocsc()
        B_cn = (Cd / dt - 0.5 * self.G).tocsr()
        lu_cn = spla.splu(A_cn)
        hd = dt / 2.0
        A_ie = (Cd / hd + self.G).tocsc()
        lu_ie = spla.splu(A_ie)
        Cv = self.C / hd
        V = np.zeros(self.n)
        out = {}
        rec = set(int(s) for s in record_steps)
        if 0 in rec:
            out[0] = 0.0
        for k in range(1, nsteps + 1):
            if k <= 2:
                V = lu_ie.solve(Cv * V + e)
                V = lu_ie.solve(Cv * V + e)
            else:
                V = lu_cn.solve(B_cn @ V + e)
            if k in rec:
                out[k] = V[0]
        return out


# ----------------------------------------------------------------------------- extrapolation

def richardson(vals, hs, exps):
    """Fit vals_l = q + sum_e a_e h_l^e and return q. Uses as many exponents as the data allow."""
    vals = np.asarray(vals, dtype=float)
    hs = np.asarray(hs, dtype=float)
    m = len(vals)
    exps = list(exps)[: m - 1]
    A = np.ones((m, len(exps) + 1))
    for j, e in enumerate(exps):
        A[:, j + 1] = hs ** e
    sol = np.linalg.solve(A, vals)
    return sol[0]


def extrapolate(levels_vals, hs, exps=(2, 3, 4)):
    """Return (best estimate, uncertainty estimate, observed order). Best estimate uses all
    levels; the uncertainty is the difference to the estimate from the finest levels minus one."""
    v = list(levels_vals)
    best = richardson(v, hs, exps)
    if len(v) >= 3:
        alt = richardson(v[1:], hs[1:], exps)
        unc = abs(best - alt)
        d1 = v[-3] - v[-2]
        d2 = v[-2] - v[-1]
        order = math.log2(abs(d1 / d2)) if d2 != 0 and d1 != 0 else float("nan")
    else:
        unc = abs(v[-1] - v[0])
        order = float("nan")
    return best, unc, order


def extrapolate_complex(levels_vals, hs, exps=(2, 3, 4)):
    re = extrapolate([z.real for z in levels_vals], hs, exps)
    im = extrapolate([z.imag for z in levels_vals], hs, exps)
    return complex(re[0], im[0]), math.hypot(re[1], im[1])


# ----------------------------------------------------------------------------- driver

def choose_levels(neuron, nlevels=4, h0=4.0):
    """Coarsest spacing so that the finest mesh stays below NODE_CAP nodes."""
    while True:
        m = Mesh(neuron, nlevels - 1, h0)
        if m.n <= NODE_CAP or h0 > 64:
            break
        h0 *= 1.25
    return h0


def compute_all(neuron, n_modes=None, nlevels=4, h0=None, log=print):
    """Run every level, return per-level raw results plus extrapolated quantities."""
    t0 = time.time()
    if h0 is None:
        h0 = choose_levels(neuron, nlevels)
    hs = [h0 / 2 ** l for l in range(nlevels)]
    meshes = [Mesh(neuron, l, h0) for l in range(nlevels)]
    log("levels: h0=%.4g um, nodes per level %s, dx range at finest %.4g..%.4g um"
        % (h0, [m.n for m in meshes], meshes[-1].dx_min, meshes[-1].dx_max))
    tau_min = float(neuron["tau_min_ms"])
    mu0 = 1.0 / tau_min

    # --- source nodes for DC
    src_locs = {}
    for loc in neuron["input_resistance_sites"]:
        src_locs[_loc_key(loc)] = loc
    for p in neuron["attenuation_pairs"]:
        src_locs[_loc_key(p["source"])] = p["source"]

    # AC queries whose AC length constant lambda/|gamma| is short get their own, finer mesh family
    ac_meshes = {}
    ac_h0 = {}
    for q in neuron["impedance_queries"]:
        f = float(q["frequency_Hz"])
        if f in ac_meshes:
            continue
        w = 2.0 * math.pi * f * 1e-3
        lam_eff = min(100.0 * math.sqrt(sg["Rm_ohm_cm2"] * sg["d_um"] / (4.0 * sg["Ri_ohm_cm"]))
                      / (1.0 + (w * sg["Rm_ohm_cm2"] * sg["Cm_uF_cm2"] * 1e-3) ** 2) ** 0.25
                      for sg in neuron["segments"])
        h_ac = lam_eff / AC_LAMBDA_RATIO
        if h_ac < h0:
            while Mesh(neuron, nlevels - 1, h_ac).n > AC_NODE_CAP and h_ac < h0:
                h_ac *= 1.25
            h_ac = min(h_ac, h0)
            if h_ac < h0:
                ac_meshes[f] = [Mesh(neuron, l, h_ac) for l in range(nlevels)]
                ac_h0[f] = h_ac
                log("  AC %g Hz: lambda_eff=%.3g um, own mesh family h0=%.4g, finest n=%d"
                    % (f, lam_eff, h_ac, ac_meshes[f][-1].n))

    per_level = []
    for m in meshes:
        t1 = time.time()
        res = {}
        dcV = {}
        for k, loc in src_locs.items():
            s = m.node(loc)
            dcV[k] = None if s < 0 else m.dc_solve(s)
        rin = []
        for loc in neuron["input_resistance_sites"]:
            V = dcV[_loc_key(loc)]
            s = m.node(loc)
            rin.append(0.0 if V is None else float(V[s]))
        att = []
        for p in neuron["attenuation_pairs"]:
            V = dcV[_loc_key(p["source"])]
            s = m.node(p["source"])
            t = m.node(p["target"])
            if V is None or t < 0:
                att.append(float("nan") if V is None else 0.0)
            else:
                att.append(float(V[t] / V[s]))
        imp = []
        for q in neuron["impedance_queries"]:
            f = float(q["frequency_Hz"])
            mm = m
            if f in ac_meshes:
                mm = ac_meshes[f][m.level]
            s = mm.node(q["source"])
            t = mm.node(q["target"])
            if s < 0 or t < 0:
                imp.append(0j)
                continue
            V = mm.ac_solve(s, f)
            imp.append(complex(V[t]))
        soma_V = dcV.get((0, 0.0))
        if soma_V is None:
            soma_V = m.dc_solve(0)
        res["rin_soma"] = float(soma_V[0])
        count = m.sturm_count(mu0)
        K = (count if n_modes is None else max(count, n_modes)) + EXTRA_MODES
        tau, coef = m.modes(K)
        res.update(rin=rin, att=att, imp=imp, count=count, tau=tau, coef=coef, n=m.n)
        per_level.append(res)
        log("  level %d: n=%d, Sturm count=%d, %.1fs" % (m.level, m.n, count, time.time() - t1))

    # --- extrapolation
    out = {"h": hs, "levels": per_level, "meshes": meshes, "h0": h0}
    nq = len(neuron["input_resistance_sites"])
    out["rin"] = [extrapolate([pl["rin"][i] for pl in per_level], hs) for i in range(nq)]
    na = len(neuron["attenuation_pairs"])
    out["att"] = [extrapolate([pl["att"][i] for pl in per_level], hs) for i in range(na)]
    ni = len(neuron["impedance_queries"])
    out["imp"] = []
    for i in range(ni):
        f = float(neuron["impedance_queries"][i]["frequency_Hz"])
        hs_i = [ac_h0[f] / 2 ** l for l in range(nlevels)] if f in ac_h0 else hs
        out["imp"].append(extrapolate_complex([pl["imp"][i] for pl in per_level], hs_i))
    out["ac_h0"] = ac_h0
    out["rin_soma"] = extrapolate([pl["rin_soma"] for pl in per_level], hs)
    counts = [pl["count"] for pl in per_level]
    Kmin = min(len(pl["tau"]) for pl in per_level)
    taus = [extrapolate([pl["tau"][k] for pl in per_level], hs) for k in range(Kmin)]
    coefs = [extrapolate([pl["coef"][k] for pl in per_level], hs) for k in range(Kmin)]
    out["tau_all"] = taus
    out["coef_all"] = coefs
    out["counts"] = counts
    # mode count: Sturm count at the finest level, confirmed by the extrapolated taus
    count_fine = counts[-1]
    count_extrap = sum(1 for t in taus if t[0] >= tau_min)
    out["count"] = count_fine
    out["count_extrap"] = count_extrap
    out["count_consistent"] = count_fine == count_extrap
    # check ARPACK found all: finest-level eigenvalues below mu0 must number count_fine
    tau_fine = per_level[-1]["tau"]
    out["arpack_count_fine"] = int(np.sum(tau_fine >= tau_min))
    out["time_s"] = time.time() - t0
    return out


def make_report(neuron, res):
    rep = {"neuron_id": neuron["neuron_id"]}
    rep["input_resistance"] = [{"site": loc, "R_MOhm": res["rin"][i][0]}
                               for i, loc in enumerate(neuron["input_resistance_sites"])]
    rep["attenuation"] = [{"source": p["source"], "target": p["target"], "factor": res["att"][i][0]}
                          for i, p in enumerate(neuron["attenuation_pairs"])]
    imp = []
    for i, q in enumerate(neuron["impedance_queries"]):
        z = res["imp"][i][0]
        imp.append({"source": q["source"], "target": q["target"], "frequency_Hz": q["frequency_Hz"],
                    "magnitude_MOhm": abs(z), "phase_deg": math.degrees(math.atan2(z.imag, z.real))})
    rep["impedance"] = imp
    n = res["count"]
    rep["modes"] = [{"tau_ms": res["tau_all"][k][0], "coefficient_MOhm": res["coef_all"][k][0]}
                    for k in range(n)]
    return rep


def transient_check(neuron, res, report, log=print, max_steps=20000):
    """Compare a direct CN simulation of the somatic unit step with the modal sum built from the
    REPORTED modes (completed by our own faster modes at the same level and the DC remainder)."""
    tau_min = float(neuron["tau_min_ms"])
    meshes = res["meshes"]
    # use the finest level with at most ~8000 nodes
    m = meshes[-1]
    for mm in reversed(meshes):
        if mm.n <= 8000:
            m = mm
            break
    lvl = m.level
    rin_sim = float(m.dc_solve(0)[0])
    rep_tau = np.array([md["tau_ms"] for md in report["modes"]], dtype=float)
    rep_coef = np.array([md["coefficient_MOhm"] for md in report["modes"]], dtype=float)
    own_tau = res["levels"][lvl]["tau"]
    own_coef = res["levels"][lvl]["coef"]
    fast = own_tau < tau_min
    extra_tau = own_tau[fast]
    extra_coef = own_coef[fast]
    c_rem = rin_sim - rep_coef.sum() - extra_coef.sum()
    tau_c = float(extra_tau.min()) if extra_tau.size else tau_min
    tau1 = float(rep_tau.max()) if rep_tau.size else float(own_tau.max())
    t_lo = 12.0 * tau_min
    t_end = max(3.0 * tau1, 1.5 * t_lo)
    dt = tau_min / 50.0
    if t_end / dt > max_steps:
        dt = t_end / max_steps
    dt2 = 2.0 * dt
    nsteps2 = int(math.ceil(t_end / dt2))
    nsteps = 2 * nsteps2
    dt = t_end / nsteps
    dt2 = 2 * dt
    times = np.geomspace(t_lo, t_end, 8)
    steps2 = sorted(set(int(round(t / dt2)) for t in times))
    steps2 = [s for s in steps2 if s >= 1]
    t_rec = np.array([s * dt2 for s in steps2])
    t1 = time.time()
    v_fine = m.step_response(dt, nsteps, [2 * s for s in steps2])
    v_coarse = m.step_response(dt2, nsteps2, steps2)
    vf = np.array([v_fine[2 * s] for s in steps2])
    vc = np.array([v_coarse[s] for s in steps2])
    v_sim = (4.0 * vf - vc) / 3.0
    v_mod = np.array([
        float(np.sum(rep_coef * (1 - np.exp(-t / rep_tau))))
        + float(np.sum(extra_coef * (1 - np.exp(-t / extra_tau)))) + c_rem for t in t_rec])
    diff = (v_sim - v_mod) / rin_sim
    bound = abs(c_rem) * np.exp(-t_rec / tau_c) / rin_sim
    time_err = np.abs(vf - vc) / 3.0 / rin_sim      # size of the time-step correction applied
    log("transient: level %d (n=%d), dt=%.3g ms, %d steps, %.1fs; max |sim-modes|/R_in = %.3g"
        % (lvl, m.n, dt, nsteps, time.time() - t1, float(np.max(np.abs(diff)))))
    return {
        "level": lvl, "nodes": m.n, "dt_ms": dt, "steps": nsteps, "t_ms": t_rec.tolist(),
        "v_sim_MOhm": v_sim.tolist(), "v_modes_MOhm": v_mod.tolist(),
        "diff_rel_rin": diff.tolist(), "max_diff_rel_rin": float(np.max(np.abs(diff))),
        "omitted_modes_bound_rel_rin": bound.tolist(),
        "time_extrapolation_correction_rel_rin": time_err.tolist(),
        "own_extra_modes": int(extra_tau.size), "remainder_coef_MOhm": c_rem,
        "rin_soma_sim_MOhm": rin_sim,
    }


def rel(a, b):
    if b != b or a != a:          # undefined reference (e.g. source at a killed terminal): fail
        return float("inf")
    return abs(a - b) / abs(b) if b != 0 else abs(a - b)


def check_report_schema(neuron, report):
    problems = []
    keys = {"neuron_id", "input_resistance", "attenuation", "impedance", "modes"}
    if set(report.keys()) != keys:
        problems.append("report keys %s" % sorted(report.keys()))
    if report.get("neuron_id") != neuron["neuron_id"]:
        problems.append("neuron_id mismatch")
    for name, qkey in (("input_resistance", "input_resistance_sites"),
                       ("attenuation", "attenuation_pairs"), ("impedance", "impedance_queries")):
        if len(report.get(name, [])) != len(neuron[qkey]):
            problems.append("%s has %d entries, expected %d"
                            % (name, len(report.get(name, [])), len(neuron[qkey])))
    for i, (e, loc) in enumerate(zip(report.get("input_resistance", []), neuron["input_resistance_sites"])):
        if set(e.keys()) != {"site", "R_MOhm"} or _loc_key(e["site"]) != _loc_key(loc):
            problems.append("input_resistance[%d] malformed" % i)
    for i, (e, p) in enumerate(zip(report.get("attenuation", []), neuron["attenuation_pairs"])):
        if set(e.keys()) != {"source", "target", "factor"} or _loc_key(e["source"]) != _loc_key(p["source"]) \
                or _loc_key(e["target"]) != _loc_key(p["target"]):
            problems.append("attenuation[%d] malformed" % i)
    for i, (e, q) in enumerate(zip(report.get("impedance", []), neuron["impedance_queries"])):
        if set(e.keys()) != {"source", "target", "frequency_Hz", "magnitude_MOhm", "phase_deg"} \
                or _loc_key(e["source"]) != _loc_key(q["source"]) \
                or _loc_key(e["target"]) != _loc_key(q["target"]) \
                or float(e["frequency_Hz"]) != float(q["frequency_Hz"]):
            problems.append("impedance[%d] malformed" % i)
    taus = [md["tau_ms"] for md in report.get("modes", [])]
    for md in report.get("modes", []):
        if set(md.keys()) != {"tau_ms", "coefficient_MOhm"}:
            problems.append("mode entry malformed")
            break
    if any(taus[i] <= taus[i + 1] for i in range(len(taus) - 1)):
        problems.append("modes not in strictly decreasing tau")
    return problems


def referee(neuron, report, log=print):
    t0 = time.time()
    problems = check_report_schema(neuron, report)
    n_rep_modes = len(report.get("modes", []))
    res = compute_all(neuron, n_modes=n_rep_modes, log=log)
    rin_soma = res["rin_soma"][0]
    verdict = {"neuron_id": neuron["neuron_id"], "schema_problems": problems,
               "h_levels_um": res["h"], "nodes_per_level": [pl["n"] for pl in res["levels"]],
               "ac_mesh_h0_um": res["ac_h0"],
               "rin_soma_MOhm": rin_soma, "rin_soma_uncertainty_rel": res["rin_soma"][1] / rin_soma}
    checks = {}

    # DC input resistance
    items = []
    for i, e in enumerate(report.get("input_resistance", [])):
        ref, unc, order = res["rin"][i]
        items.append({"index": i, "report": e["R_MOhm"], "ref": ref, "rel_diff": rel(e["R_MOhm"], ref),
                      "ref_uncertainty_rel": unc / abs(ref) if ref else unc, "observed_order": order,
                      "levels": [pl["rin"][i] for pl in res["levels"]]})
    checks["input_resistance"] = {"items": items,
                                  "max_rel_diff": max([it["rel_diff"] for it in items], default=0.0)}
    # attenuation
    items = []
    for i, e in enumerate(report.get("attenuation", [])):
        ref, unc, order = res["att"][i]
        items.append({"index": i, "report": e["factor"], "ref": ref, "rel_diff": rel(e["factor"], ref),
                      "ref_uncertainty_rel": unc / abs(ref) if ref else unc, "observed_order": order,
                      "levels": [pl["att"][i] for pl in res["levels"]]})
    checks["attenuation"] = {"items": items,
                             "max_rel_diff": max([it["rel_diff"] for it in items], default=0.0)}
    # impedance
    items = []
    for i, e in enumerate(report.get("impedance", [])):
        z, unc = res["imp"][i]
        mag = abs(z)
        ph = math.degrees(math.atan2(z.imag, z.real))
        dph = abs(e["phase_deg"] - ph)
        dph = min(dph, 360.0 - dph)
        if mag == 0.0 and e["magnitude_MOhm"] == 0.0:
            dph = 0.0           # phase of a zero transfer impedance is undefined
        items.append({"index": i, "report_magnitude": e["magnitude_MOhm"], "ref_magnitude": mag,
                      "rel_diff_magnitude": rel(e["magnitude_MOhm"], mag),
                      "report_phase": e["phase_deg"], "ref_phase": ph, "abs_diff_phase_deg": dph,
                      "phase_tol_deg": TOL_PHASE,
                      "ref_uncertainty_rel": unc / mag if mag else unc,
                      "levels_magnitude": [abs(pl["imp"][i]) for pl in res["levels"]]})
    checks["impedance"] = {"items": items,
                           "max_rel_diff_magnitude": max([it["rel_diff_magnitude"] for it in items], default=0.0),
                           "max_phase_diff_deg": max([it["abs_diff_phase_deg"] for it in items], default=0.0),
                           "phase_ok": all(it["abs_diff_phase_deg"] <= it["phase_tol_deg"] for it in items)}
    # modes
    tau_min = float(neuron["tau_min_ms"])
    count_ref = res["count"]
    items = []
    n_cmp = min(n_rep_modes, len(res["tau_all"]))
    for k in range(n_cmp):
        tref, tunc, order = res["tau_all"][k]
        cref, cunc, _ = res["coef_all"][k]
        md = report["modes"][k]
        items.append({"index": k, "report_tau": md["tau_ms"], "ref_tau": tref,
                      "rel_diff_tau": rel(md["tau_ms"], tref), "tau_uncertainty_rel": tunc / tref,
                      "observed_order_tau": order,
                      "report_coef": md["coefficient_MOhm"], "ref_coef": cref,
                      "diff_coef_rel_rin": abs(md["coefficient_MOhm"] - cref) / rin_soma,
                      "coef_uncertainty_rel_rin": cunc / rin_soma,
                      "levels_tau": [float(pl["tau"][k]) for pl in res["levels"]]})
    checks["modes"] = {
        "report_count": n_rep_modes, "ref_count_sturm_finest": count_ref,
        "ref_count_extrapolated": res["count_extrap"], "ref_count_arpack_finest": res["arpack_count_fine"],
        "sturm_counts_per_level": res["counts"], "items": items,
        "max_rel_diff_tau": max([it["rel_diff_tau"] for it in items], default=0.0),
        "max_diff_coef_rel_rin": max([it["diff_coef_rel_rin"] for it in items], default=0.0),
        "ref_sum_coef_all_computed_rel_rin": float(sum(c[0] for c in res["coef_all"]) / rin_soma),
        "tau_min_ms": tau_min,
        "ref_taus_near_tau_min": [t[0] for t in res["tau_all"] if abs(t[0] - tau_min) < 1e-3 * tau_min],
    }
    # transient
    try:
        checks["transient"] = transient_check(neuron, res, report, log=log) if n_rep_modes else \
            {"max_diff_rel_rin": float("nan")}
    except Exception as exc:  # pragma: no cover
        checks["transient"] = {"error": repr(exc), "max_diff_rel_rin": float("nan")}

    passes = {
        "schema": not problems,
        "input_resistance": checks["input_resistance"]["max_rel_diff"] <= TOL_REL,
        "attenuation": checks["attenuation"]["max_rel_diff"] <= TOL_REL,
        "impedance_magnitude": checks["impedance"]["max_rel_diff_magnitude"] <= TOL_REL,
        "impedance_phase": checks["impedance"]["phase_ok"],
        "mode_count": (n_rep_modes == count_ref) and (count_ref == res["count_extrap"])
                      and (count_ref == res["arpack_count_fine"]),
        "tau": checks["modes"]["max_rel_diff_tau"] <= TOL_REL and n_cmp == n_rep_modes,
        "coefficients": checks["modes"]["max_diff_coef_rel_rin"] <= TOL_COEF and n_cmp == n_rep_modes,
        "transient": checks["transient"]["max_diff_rel_rin"] <= TOL_TRANS
                     if checks["transient"]["max_diff_rel_rin"] == checks["transient"]["max_diff_rel_rin"] else False,
    }
    verdict["checks"] = checks
    verdict["passes"] = passes
    verdict["pass"] = all(passes.values())
    verdict["tolerances"] = {"rel": TOL_REL, "phase_deg_abs": TOL_PHASE, "coef_rel_rin": TOL_COEF,
                             "transient_rel_rin": TOL_TRANS}
    verdict["runtime_s"] = time.time() - t0
    return verdict


def _json_default(o):
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, complex):
        return [o.real, o.imag]
    raise TypeError(type(o))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--neuron", required=True)
    ap.add_argument("--report")
    ap.add_argument("--out")
    ap.add_argument("--solve", action="store_true")
    ap.add_argument("--output")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--levels", type=int, default=4)
    ap.add_argument("--h0", type=float, default=None)
    a = ap.parse_args(argv)
    log = (lambda *x, **k: None) if a.quiet else (lambda *x, **k: print(*x, file=sys.stderr, **k))
    with open(a.neuron) as fh:
        neuron = json.load(fh)
    if a.solve:
        res = compute_all(neuron, nlevels=a.levels, h0=a.h0, log=log)
        rep = make_report(neuron, res)
        out = a.output or a.out
        txt = json.dumps(rep, indent=1)
        if out:
            with open(out, "w") as fh:
                fh.write(txt + "\n")
        else:
            print(txt)
        log("solve: %d modes, %.1fs" % (len(rep["modes"]), res["time_s"]))
        return 0
    if not a.report:
        ap.error("--report is required unless --solve")
    with open(a.report) as fh:
        report = json.load(fh)
    verdict = referee(neuron, report, log=log)
    txt = json.dumps(verdict, indent=1, default=_json_default)
    if a.out:
        with open(a.out, "w") as fh:
            fh.write(txt + "\n")
    if not a.quiet:
        p = verdict["passes"]
        c = verdict["checks"]
        print("verdict: %s" % ("PASS" if verdict["pass"] else "FAIL"))
        print("  R_in      max rel diff %.3g  (ref unc %.3g)" % (
            c["input_resistance"]["max_rel_diff"],
            max([i["ref_uncertainty_rel"] for i in c["input_resistance"]["items"]], default=0)))
        print("  atten     max rel diff %.3g" % c["attenuation"]["max_rel_diff"])
        print("  |Z|       max rel diff %.3g ; phase max diff %.3g deg" % (
            c["impedance"]["max_rel_diff_magnitude"], c["impedance"]["max_phase_diff_deg"]))
        print("  modes     report %d, ref %d (sturm), %d (extrap), %d (arpack)" % (
            c["modes"]["report_count"], c["modes"]["ref_count_sturm_finest"],
            c["modes"]["ref_count_extrapolated"], c["modes"]["ref_count_arpack_finest"]))
        print("  tau       max rel diff %.3g ; coef max diff %.3g R_in" % (
            c["modes"]["max_rel_diff_tau"], c["modes"]["max_diff_coef_rel_rin"]))
        print("  transient max diff %.3g R_in" % c["transient"]["max_diff_rel_rin"])
        print("  failed: %s" % [k for k, v in p.items() if not v])
        print("  runtime %.1fs" % verdict["runtime_s"])
    return 0 if verdict["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
