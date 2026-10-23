"""Generate the graded neurons and screen them with the oracle and a finite-difference eigenvalue
cross-count for every guarantee of CABLE_SPEC.md section 2. One random stream per slot.

usage: gen_neurons.py <cabletree.py> <out_dir> [indices...]
"""
import importlib.util
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
from scipy.linalg import eigh

spec = importlib.util.spec_from_file_location("ct", sys.argv[1])
ct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ct)
OUT = Path(sys.argv[2])
(OUT / "neurons").mkdir(parents=True, exist_ok=True)
(OUT / "log").mkdir(parents=True, exist_ok=True)
DEBUG = bool(os.environ.get("GEN_DEBUG"))


def r4(v):
    return float(f"{v:.4g}")


def U(rng, lo, hi):
    return float(rng.uniform(lo, hi))


def LU(rng, lo, hi):
    return float(math.exp(rng.uniform(math.log(lo), math.log(hi))))


def loc(seg, f):
    return {"segment": seg, "fraction": f}


# ------------------------------------------------------------------ random neurons
def seg(i, parent, L, d, Rm, Ri, Cm, end=None):
    return {"id": i, "parent": parent, "L_um": r4(L), "d_um": r4(d), "Rm_ohm_cm2": r4(Rm), "Ri_ohm_cm": r4(Ri),
            "Cm_uF_cm2": r4(Cm), "end": end}


def end_of(rng, kinds):
    k = str(rng.choice(kinds))
    if k == "shunt":
        return {"type": "shunt", "g_nS": r4(LU(rng, 0.5, 20))}
    return {"type": k, "g_nS": None}


def soma_of(rng, style):
    if style == "negligible_soma":
        return {"d_um": r4(U(rng, 8, 10)), "Rm_ohm_cm2": r4(U(rng, 40000, 60000)), "Cm_uF_cm2": r4(U(rng, 0.6, 1.0)), "shunt_nS": 0.0}
    if style == "dominant_soma":
        return {"d_um": r4(U(rng, 32, 40)), "Rm_ohm_cm2": r4(U(rng, 2000, 6000)), "Cm_uF_cm2": r4(U(rng, 1.2, 2.0)), "shunt_nS": r4(U(rng, 5, 20))}
    return {"d_um": r4(U(rng, 10, 30)), "Rm_ohm_cm2": r4(LU(rng, 4000, 50000)), "Cm_uF_cm2": r4(U(rng, 0.7, 1.5)),
            "shunt_nS": r4(U(rng, 0, 10)) if rng.rand() < 0.5 else 0.0}


def build(rng, style):
    uniform = style not in ("nonuniform", "tree", "many_modes", "mixed_ends")
    Rm0, Ri0, Cm0 = LU(rng, 5000, 40000), U(rng, 80, 250), U(rng, 0.7, 1.5)

    def params():
        if style == "many_modes":
            return LU(rng, 25000, 60000), U(rng, 150, 300), U(rng, 1.4, 2.0)
        if uniform:
            return Rm0, Ri0, Cm0
        return LU(rng, 2000, 60000), U(rng, 70, 300), U(rng, 0.6, 2.0)
    segs = []
    if style in ("cable_sealed", "cable_killed", "cable_shunt", "long_thin", "thick_short"):
        n = int(rng.randint(3, 6))
        d = U(rng, 1.0, 4.0) if style != "long_thin" else U(rng, 0.3, 0.8)
        if style == "thick_short":
            d = U(rng, 4, 6)
        for i in range(1, n + 1):
            L = U(rng, 100, 600) if style != "thick_short" else U(rng, 20, 80)
            Rm, Ri, Cm = params()
            kinds = {"cable_sealed": ["sealed"], "cable_killed": ["killed"], "cable_shunt": ["shunt"]}.get(style, ["sealed", "killed", "shunt"])
            segs.append(seg(i, i - 1, L, d * (0.97 ** (i - 1)), Rm, Ri, Cm, end_of(rng, kinds) if i == n else None))
    elif style in ("bifurcation", "rall", "near_sym"):
        d0 = U(rng, 2, 5)
        Rm, Ri, Cm = params()
        segs.append(seg(1, 0, U(rng, 100, 400), d0, Rm, Ri, Cm))
        if style == "rall":
            d1 = d0 / 2 ** (2 / 3) * U(rng, 0.98, 1.0)
            d2 = (d0 ** 1.5 - d1 ** 1.5) ** (2 / 3)
            L1 = U(rng, 150, 500)
            L2 = L1 * U(rng, 0.9, 1.1)
        elif style == "near_sym":
            d1 = d0 * U(rng, 0.5, 0.7)
            d2 = d1 * (1 + U(rng, 0.004, 0.03) * (1 if rng.rand() < 0.5 else -1))
            L1 = U(rng, 150, 500)
            L2 = L1 * (1 + U(rng, -0.02, 0.02))
        else:
            d1, d2 = d0 * U(rng, 0.3, 0.8), d0 * U(rng, 0.3, 0.8)
            L1, L2 = U(rng, 100, 600), U(rng, 100, 600)
        kinds = ["sealed"] if style in ("rall", "near_sym") else ["sealed", "killed", "shunt"]
        Rm1, Ri1, Cm1 = params()
        Rm2, Ri2, Cm2 = params()
        segs.append(seg(2, 1, L1, d1, Rm1, Ri1, Cm1, end_of(rng, kinds)))
        segs.append(seg(3, 1, L2, d2, Rm2, Ri2, Cm2, end_of(rng, kinds)))
        if style == "near_sym" and rng.rand() < 0.5:
            # one more level of nearly symmetric daughters
            for p in (2, 3):
                segs[p - 1]["end"] = None
            dd = d1 * U(rng, 0.5, 0.75)
            Ld = U(rng, 100, 300)
            k = 4
            for p in (2, 3):
                for _ in range(2):
                    segs.append(seg(k, p, Ld * (1 + U(rng, -0.01, 0.01)), dd * (1 + U(rng, -0.01, 0.01)), Rm1, Ri1, Cm1, end_of(rng, ["sealed"])))
                    k += 1
    else:
        n = int(rng.randint(10, 13)) if style == "many_modes" else int(rng.randint(6, 13)) if style in ("tree", "nonuniform", "mixed_ends", "negligible_soma", "dominant_soma", "high_freq", "few_modes") else int(rng.randint(4, 9))
        max_depth = int(rng.randint(2, 5))
        trunks = int(rng.randint(1, 4)) if style == "multi_trunk" else int(rng.randint(1, 3))
        depth = {}
        for i in range(1, n + 1):
            if i <= trunks:
                parent = 0
            else:
                cands = [s for s in segs if depth[s["id"]] < max_depth]
                weights = np.array([1.0 + 2.0 * (depth[s["id"]] == max(depth.values())) for s in cands])
                parent = int(rng.choice([s["id"] for s in cands], p=weights / weights.sum()))
            depth[i] = 0 if parent == 0 else depth[parent] + 1
            pd_ = U(rng, 2.5, 6) if parent == 0 else segs[parent - 1]["d_um"]
            d = pd_ * U(rng, 0.45, 0.9) if parent else pd_
            if style == "many_modes":
                d = U(rng, 0.4, 1.2) if parent else U(rng, 1.2, 2.0)
            d = min(max(d, 0.3), 6.0)
            Rm, Ri, Cm = params()
            L = U(rng, 350, 600) if style == "many_modes" else U(rng, 30, 500)
            segs.append(seg(i, parent, L, d, Rm, Ri, Cm))
        has_child = {s["parent"] for s in segs}
        kinds = {"mixed_ends": ["sealed", "killed", "shunt"], "shunt_tree": ["shunt"], "killed_tree": ["killed", "sealed"]}.get(style, ["sealed", "sealed", "killed", "shunt"])
        for s in segs:
            if s["id"] not in has_child:
                s["end"] = end_of(rng, kinds)
    soma = soma_of(rng, style)
    return soma, segs


def choose_queries(rng, segs, style):
    killed_tips = {s["id"] for s in segs if s["end"] and s["end"]["type"] == "killed"}

    def rand_loc():
        if rng.rand() < 0.2:
            return loc(0, 0)
        s = segs[int(rng.randint(len(segs)))]
        f = round(float(rng.choice([0.25, 0.5, 0.75, 1.0, round(U(rng, 0.05, 0.95), 2)])), 2)
        if s["id"] in killed_tips and f >= 0.95:
            f = 0.5
        return loc(s["id"], f)
    sites = [loc(0, 0)] + [rand_loc() for _ in range(int(rng.randint(1, 8)))]
    uniq = []
    for v in sites:
        if v not in uniq:
            uniq.append(v)
    sites = uniq[:8]
    if len(sites) < 2:
        sites.append(loc(segs[0]["id"], 1.0))
    pairs = []
    for _ in range(int(rng.randint(2, 9))):
        a, b = rand_loc(), rand_loc()
        pairs.append({"source": a, "target": b})
    if rng.rand() < 0.7:
        pairs[0] = {"source": pairs[0]["source"], "target": loc(0, 0)}
        if len(pairs) > 1:
            pairs[1] = {"source": loc(0, 0), "target": pairs[0]["source"]}
    freqs = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000]
    if style == "high_freq":
        freqs = [500, 1000, 1500, 2000]
    queries = []
    for _ in range(int(rng.randint(2, 9))):
        a, b = rand_loc(), rand_loc()
        if rng.rand() < 0.3:
            b = a
        queries.append({"source": a, "target": b, "frequency_Hz": float(rng.choice(freqs))})
    return sites, pairs[:8], queries[:8]


# ------------------------------------------------------------------ finite-difference cross-count
def fd_taus(m, h_um=4.0):
    """Eigen-time-constants (ms) of a second-order compartmental model of the neuron."""
    segs = {s["id"]: s for s in m["segments"]}
    nodes = []            # (segment id, index) ; node 0 = soma
    G = {}
    C = {}
    idx = {("soma", 0): 0}
    Cs = math.pi * (m["soma"]["d_um"] * 1e-4) ** 2 * m["soma"]["Cm_uF_cm2"] * 1e-6
    Gs = math.pi * (m["soma"]["d_um"] * 1e-4) ** 2 / m["soma"]["Rm_ohm_cm2"] + m["soma"]["shunt_nS"] * 1e-9
    diag_g = {0: Gs}
    diag_c = {0: Cs}
    links = []
    killed = set()
    for s in segs.values():
        n = max(4, int(math.ceil(s["L_um"] / h_um)))
        dx = s["L_um"] * 1e-4 / n
        d = s["d_um"] * 1e-4
        g_ax = math.pi * d * d / 4 / (s["Ri_ohm_cm"] * dx)
        g_m = math.pi * d * dx / s["Rm_ohm_cm2"]
        c_m = math.pi * d * dx * s["Cm_uF_cm2"] * 1e-6
        # nodes at compartment boundaries 0..n ; interior nodes carry a full compartment, end
        # nodes a half compartment (cell-vertex scheme), making junctions exact
        for k in range(n + 1):
            key = (s["id"], k)
            if k == 0:
                prox = ("soma", 0) if s["parent"] == 0 else (s["parent"], max(4, int(math.ceil(segs[s["parent"]]["L_um"] / h_um))))
                idx[key] = idx[prox]
            else:
                idx[key] = len(diag_g)
                diag_g[idx[key]] = 0.0
                diag_c[idx[key]] = 0.0
            w = 0.5 if k in (0, n) else 1.0
            diag_g[idx[key]] += w * g_m
            diag_c[idx[key]] += w * c_m
            if k > 0:
                links.append((idx[(s["id"], k - 1)], idx[key], g_ax))
        if s["end"]:
            last = idx[(s["id"], n)]
            if s["end"]["type"] == "killed":
                killed.add(last)
            elif s["end"]["type"] == "shunt":
                diag_g[last] += s["end"]["g_nS"] * 1e-9
    N = len(diag_g)
    Gm = np.zeros((N, N))
    Cm = np.zeros(N)
    for i in range(N):
        Gm[i, i] = diag_g[i]
        Cm[i] = diag_c[i]
    for i, j, g in links:
        Gm[i, i] += g
        Gm[j, j] += g
        Gm[i, j] -= g
        Gm[j, i] -= g
    keep = [i for i in range(N) if i not in killed]
    Gm = Gm[np.ix_(keep, keep)]
    Cm = Cm[keep]
    w = eigh(Gm, np.diag(Cm), eigvals_only=True)
    return np.sort(1e3 / w)[::-1]


# ------------------------------------------------------------------ screening
def screen(m, want):
    t0 = time.time()
    rep = ct.solve(m)
    secs = time.time() - t0
    if secs > 15:
        return False, "slow", rep
    taus = [e["tau_ms"] for e in rep["modes"]]
    if not 2 <= len(taus) <= 60:
        return False, f"modes {len(taus)}", rep
    rel = [(a - b) / a for a, b in zip(taus, taus[1:])]
    if min(rel) < 1e-3:
        return False, "mode separation", rep
    if min(abs(t - m["tau_min_ms"]) / m["tau_min_ms"] for t in taus) < 1e-3:
        return False, "mode near tau_min", rep
    tau_max = max([s["Rm_ohm_cm2"] * s["Cm_uF_cm2"] * 1e-3 for s in m["segments"]] + [m["soma"]["Rm_ohm_cm2"] * m["soma"]["Cm_uF_cm2"] * 1e-3])
    if taus[0] > tau_max * (1 - 1e-5):
        return False, "slowest mode at the bound", rep
    rin = next(e["R_MOhm"] for e in rep["input_resistance"] if e["site"]["segment"] == 0)
    if min(abs(e["coefficient_MOhm"]) for e in rep["modes"]) < 1e-6 * rin:
        return False, "tiny coefficient", rep
    if min(e["factor"] for e in rep["attenuation"]) < 1e-6:
        return False, "tiny attenuation", rep
    if min(e["R_MOhm"] for e in rep["input_resistance"]) <= 0:
        return False, "zero input resistance", rep
    # finite-difference cross-count and cross-values
    fd = fd_taus(m)
    fd_in = [t for t in fd if t >= m["tau_min_ms"] * (1 - 3e-4)]
    if len(fd_in) != len(taus):
        return False, f"fd count {len(fd_in)} vs {len(taus)}", rep
    if max(abs(a - b) / a for a, b in zip(taus, fd_in)) > 2e-3:
        return False, "fd values", rep
    # sibling identity
    by_parent = {}
    for s in m["segments"]:
        by_parent.setdefault(s["parent"], []).append((s["L_um"], s["d_um"], s["Rm_ohm_cm2"], s["Ri_ohm_cm"], s["Cm_uF_cm2"]))
    if any(len(set(v)) != len(v) for v in by_parent.values()):
        return False, "identical siblings", rep
    return True, "ok", rep


def predicate(want, m, rep):
    taus = [e["tau_ms"] for e in rep["modes"]]
    rin = next(e["R_MOhm"] for e in rep["input_resistance"] if e["site"]["segment"] == 0)
    ends = [s["end"]["type"] for s in m["segments"] if s["end"]]
    if "min_modes" in want and len(taus) < want["min_modes"]: return False
    if "max_modes" in want and len(taus) > want["max_modes"]: return False
    if "ends" in want and not set(want["ends"]) <= set(ends): return False
    if want.get("hidden") and not any(abs(e["coefficient_MOhm"]) < 1e-3 * rin for e in rep["modes"]): return False
    if "min_segments" in want and len(m["segments"]) < want["min_segments"]: return False
    if want.get("close_pair") and min((a - b) / a for a, b in zip(taus, taus[1:])) > 2e-2: return False
    if want.get("asym") and not any(abs(a["factor"] - b["factor"]) > 0.05 for a in rep["attenuation"] for b in rep["attenuation"]
                                      if a["source"] == b["target"] and a["target"] == b["source"]): return False
    if want.get("phase_wrap") and not any(z["phase_deg"] < -90 for z in rep["impedance"]): return False
    if "depth" in want:
        segs = {s["id"]: s for s in m["segments"]}
        def dep(s):
            n = 0
            while s["parent"]:
                s = segs[s["parent"]]; n += 1
            return n
        if max(dep(s) for s in m["segments"]) < want["depth"]: return False
    return True


PLAN = [
    ("model_01", True, "cable_sealed", dict(), "unbranched sealed cable (base case)"),
    ("model_02", True, "bifurcation", dict(ends=["killed"], asym=True), "asymmetric bifurcation with a killed terminal"),
    ("model_03", True, "nonuniform", dict(min_segments=7, ends=["shunt"]), "tree with non-uniform membrane and a shunted terminal"),
    ("model_04", True, "dominant_soma", dict(max_modes=6), "dominant soma with shunt, few modes"),
    ("model_05", True, "near_sym", dict(hidden=True), "nearly symmetric siblings: nearly hidden mode"),
    ("model_06", True, "many_modes", dict(min_modes=25, min_segments=9), "large tree, many modes"),
    ("held_01", False, "cable_killed", dict(), "unbranched cable with a killed end"),
    ("held_02", False, "cable_shunt", dict(), "unbranched cable with a shunted end"),
    ("held_03", False, "rall", dict(), "bifurcation close to the 3/2 rule"),
    ("held_04", False, "bifurcation", dict(asym=True), "asymmetric bifurcation"),
    ("held_05", False, "tree", dict(depth=3, min_segments=8), "tree with four branch orders"),
    ("held_06", False, "nonuniform", dict(min_segments=6), "non-uniform membrane along the tree"),
    ("held_07", False, "mixed_ends", dict(ends=["sealed", "killed", "shunt"]), "sealed, killed and shunted terminals in one tree"),
    ("held_08", False, "negligible_soma", dict(), "negligible soma"),
    ("held_09", False, "dominant_soma", dict(), "dominant soma"),
    ("held_10", False, "near_sym", dict(hidden=True, close_pair=True), "nearly symmetric subtrees: close time constants"),
    ("held_11", False, "many_modes", dict(min_modes=40), "forty or more modes"),
    ("held_12", False, "few_modes", dict(max_modes=3), "two or three modes"),
    ("held_13", False, "high_freq", dict(phase_wrap=True), "high-frequency queries with phases beyond -90 degrees"),
    ("held_14", False, "long_thin", dict(), "long thin cables, large electrotonic length"),
    ("held_15", False, "thick_short", dict(), "thick short segments, compact tree"),
    ("held_16", False, "multi_trunk", dict(), "several trunks on the soma"),
    ("held_17", False, "shunt_tree", dict(ends=["shunt"]), "every terminal shunted"),
    ("held_18", False, "killed_tree", dict(ends=["killed"]), "killed terminals in a tree"),
    ("held_19", False, "tree", dict(min_segments=10), "ten or more segments"),
    ("held_20", False, "nonuniform", dict(ends=["killed", "shunt"]), "non-uniform tree with killed and shunted ends"),
    ("held_21", False, "near_sym", dict(), "nearly symmetric bifurcation"),
    ("held_22", False, "tree", dict(min_modes=15), "tree with fifteen or more modes"),
]


def choose_tau_min(rng, m, style):
    taus = [s["Rm_ohm_cm2"] * s["Cm_uF_cm2"] * 1e-3 for s in m["segments"]]
    cap = min(20.0, 0.5 * min(taus))
    if style in ("few_modes",):
        return r4(max(0.1, cap * U(rng, 0.6, 1.0)))
    if style in ("many_modes",):
        return r4(max(0.1, min(cap, U(rng, 0.1, 0.16))))
    return r4(max(0.1, min(cap, LU(rng, 0.15, cap))))


def build_slot(index):
    nid, shipped, style, want, label = PLAN[index]
    rng = np.random.RandomState(20261023 + 7919 * index)
    t0 = time.time()
    for attempt in range(600):
        if time.time() - t0 > 1500:
            break
        try:
            soma, segs = build(rng, style)
            sites, pairs, queries = choose_queries(rng, segs, style)
            m = dict(neuron_id=nid, soma=soma, segments=segs, input_resistance_sites=sites, attenuation_pairs=pairs,
                     impedance_queries=queries, tau_min_ms=0.1)
            m["tau_min_ms"] = choose_tau_min(rng, m, style)
            ok, why, rep = screen(m, want)
            if not ok:
                if DEBUG:
                    print("  reject", why, flush=True)
                continue
            if not predicate(want, m, rep):
                if DEBUG:
                    print("  reject predicate", len(rep["modes"]), flush=True)
                continue
        except Exception as error:
            if DEBUG:
                print("  reject error", repr(error)[:200], flush=True)
            continue
        json.dump(m, open(OUT / "neurons" / f"{nid}.json", "w"), indent=1)
        log = dict(neuron_id=nid, shipped=shipped, style=style, label=label, attempts=attempt + 1, segments=len(segs),
                   modes=len(rep["modes"]), tau_min=m["tau_min_ms"], ends=[s["end"]["type"] for s in segs if s["end"]])
        json.dump(log, open(OUT / "log" / f"{nid}.json", "w"), indent=1)
        print(json.dumps(log), flush=True)
        return
    print(json.dumps(dict(neuron_id=nid, failed=True, label=label)), flush=True)


if __name__ == "__main__":
    idx = [int(v) for v in sys.argv[3:]] or list(range(len(PLAN)))
    for i in idx:
        build_slot(i)
