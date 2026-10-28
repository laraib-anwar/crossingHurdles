"""Generate the graded frames and screen them with the oracle for every guarantee of
FRAME_SPEC.md section 2. One random stream per slot.

usage: gen_frames.py <framedyn.py> <out_dir> [indices...]
"""
import importlib
import importlib.util
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("fd", sys.argv[1])
fd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fd)
sys.modules["pytest"] = importlib.import_module("pytest")
_tv = importlib.util.spec_from_file_location("tv", Path(sys.argv[1]).resolve().parents[1] / "tests/test_outputs.py")
tv = importlib.util.module_from_spec(_tv)
_tv.loader.exec_module(tv)
OUT = Path(sys.argv[2])
(OUT / "frames").mkdir(parents=True, exist_ok=True)
(OUT / "log").mkdir(parents=True, exist_ok=True)
DEBUG = bool(os.environ.get("GEN_DEBUG"))
SECTIONS = [  # (A m^2, I m^4): IPE/HE-like steel and some concrete sections
    (1.1e-3, 1.9e-6), (2.0e-3, 8.4e-6), (3.9e-3, 2.5e-5), (6.4e-3, 9.3e-5), (1.0e-2, 2.8e-4), (1.6e-2, 1.2e-3),
    (4.0e-2, 1.3e-3), (9.0e-2 / 2, 5e-3)]
MATERIALS = [(2.1e11, 7850.0), (7.0e10, 2700.0), (3.0e10, 2400.0), (2.0e11, 7800.0)]


def r5(v):
    return float(f"{v:.5g}")


def U(rng, lo, hi):
    return float(rng.uniform(lo, hi))


def node(i, x, y, sup=(False, False, False), m=0.0):
    return dict(id=i, x=r5(x), y=r5(y), mass_kg=r5(m), support=dict(ux=sup[0], uy=sup[1], rz=sup[2]))


def member(k, i, j, E, rho, A, I):
    return dict(id=k, i=i, j=j, E=E, A=A, I=I, rho=rho)


def support(rng, kind):
    return {"fixed": (True, True, True), "pinned": (True, True, False), "roller": (False, True, False), "free": (False, False, False)}[kind]


def build(rng, style):
    E, rho = MATERIALS[int(rng.randint(len(MATERIALS)))]
    A, I = SECTIONS[int(rng.randint(len(SECTIONS)))]
    sec = lambda: (min(5e-2, max(1e-4, A * U(rng, 0.9, 1.1))), min(5e-3, max(1e-7, I * U(rng, 0.8, 1.25))))
    nodes, mems = [], []
    if style in ("cantilever", "ss_beam"):
        n = int(rng.randint(2, 5))
        L = U(rng, 3, 15)
        for k in range(n + 1):
            x = L * k / n * (1 + U(rng, -0.05, 0.05) * (0 < k < n))
            nodes.append(node(k + 1, x, 0.0, (True, True, True) if (k == 0 and style == "cantilever") else
                              (True, True, False) if (k == 0) else (False, True, False) if (k == n and style == "ss_beam") else (False, False, False)))
        for k in range(n):
            a, i_ = sec()
            mems.append(member(k + 1, k + 1, k + 2, E, rho, r5(a), r5(i_)))
    elif style in ("portal", "portal_mass", "near_sym"):
        bays, storeys = int(rng.randint(1, 4)), int(rng.randint(1, 4))
        if style == "near_sym":
            bays, storeys = 1, int(rng.randint(1, 3))
        w, h = U(rng, 4, 8), U(rng, 3, 5)
        nid = {}
        k = 1
        for s in range(storeys + 1):
            for b in range(bays + 1):
                sup = support(rng, str(rng.choice(["fixed", "fixed", "pinned"]))) if s == 0 else (False, False, False)
                jitter = 0.0 if style == "near_sym" else U(rng, -0.3, 0.3)
                m = U(rng, 500, 20000) if (style == "portal_mass" and s > 0 and rng.rand() < 0.6) else 0.0
                nodes.append(node(k, b * w + jitter, s * h + (0.0 if s == 0 else jitter), sup, m))
                nid[(b, s)] = k
                k += 1
        mid = 1
        for s in range(storeys):
            for b in range(bays + 1):
                a, i_ = sec()
                if style == "near_sym":
                    i_ *= 1 + U(rng, 0.001, 0.01) * (b == bays)
                mems.append(member(mid, nid[(b, s)], nid[(b, s + 1)], E, rho, r5(a), r5(i_)))
                mid += 1
        for s in range(1, storeys + 1):
            for b in range(bays):
                a, i_ = sec()
                mems.append(member(mid, nid[(b, s)], nid[(b + 1, s)], E, rho, r5(min(5e-2, a * 1.2)), r5(min(5e-3, i_ * 1.5))))
                mid += 1
    elif style == "fixed_member":
        # a portal frame plus one member whose two nodes are both fully fixed (member-local modes)
        w, h = U(rng, 4, 8), U(rng, 3, 5)
        nodes = [node(1, 0, 0, (True, True, True)), node(2, 0, h), node(3, w, h), node(4, w, 0, (True, True, True)),
                 node(5, w + U(rng, 2, 6), 0, (True, True, True)), node(6, w + U(rng, 8, 14), 0, (True, True, True))]
        mems = [member(1, 1, 2, E, rho, *map(r5, sec())), member(2, 2, 3, E, rho, *map(r5, sec())), member(3, 3, 4, E, rho, *map(r5, sec())),
                member(4, 5, 6, E, rho, *map(r5, sec()))]
    elif style == "truss_like":
        # triangulated frame with rigid joints
        n = int(rng.randint(2, 4))
        w, h = U(rng, 3, 6), U(rng, 2, 4)
        for k in range(n + 1):
            nodes.append(node(2 * k + 1, k * w, 0.0, (True, True, False) if k == 0 else (False, True, False) if k == n else (False, False, False)))
            nodes.append(node(2 * k + 2, k * w + w / 2 * (k < n), h, (False, False, False)))
        mid = 1
        for k in range(n + 1):
            if k < n:
                mems.append(member(mid, 2 * k + 1, 2 * k + 3, E, rho, *map(r5, sec()))); mid += 1
                mems.append(member(mid, 2 * k + 2, 2 * k + 4, E, rho, *map(r5, sec()))); mid += 1
            mems.append(member(mid, 2 * k + 1, 2 * k + 2, E, rho, *map(r5, sec()))); mid += 1
            if k < n:
                mems.append(member(mid, 2 * k + 2, 2 * k + 3, E, rho, *map(r5, sec()))); mid += 1
        nodes = nodes[: 2 * n + 2]
    elif style == "stocky":
        n = int(rng.randint(2, 4))
        L = U(rng, 1, 3)
        for k in range(n + 1):
            nodes.append(node(k + 1, L * k, 0.0, (True, True, True) if k == 0 else (False, False, False)))
        for k in range(n):
            mems.append(member(k + 1, k + 1, k + 2, E, rho, r5(0.03 * U(rng, 0.8, 1.2)), r5(2e-3 * U(rng, 0.8, 1.2))))
    elif style == "slender":
        n = int(rng.randint(3, 6))
        L = U(rng, 8, 18)
        for k in range(n + 1):
            nodes.append(node(k + 1, L * k / n, 0.0, (True, True, False) if k == 0 else (False, True, False) if k == n else (False, False, False)))
        for k in range(n):
            mems.append(member(k + 1, k + 1, k + 2, E, rho, r5(1.5e-3 * U(rng, 0.8, 1.2)), r5(3e-6 * U(rng, 0.8, 1.2))))
    elif style == "arch":
        n = int(rng.randint(4, 8))
        R, th = U(rng, 6, 12), U(rng, 0.8, 1.6)
        for k in range(n + 1):
            ang = math.pi / 2 - th + 2 * th * k / n
            nodes.append(node(k + 1, R * math.cos(ang), R * math.sin(ang) - R * math.cos(th), (True, True, k % 2 == 0) if k in (0, n) else (False, False, False)))
        for k in range(n):
            mems.append(member(k + 1, k + 1, k + 2, E, rho, *map(r5, sec())))
    return nodes, mems


def choose_queries(rng, nodes, mems, style):
    free = [n["id"] for n in nodes if not all(n["support"].values())]
    nl = []
    for _ in range(int(rng.randint(1, 4))):
        nl.append(dict(node=int(rng.choice(free)), Fx=r5(U(rng, -1e5, 1e5)), Fy=r5(U(rng, -2e5, 5e4)), Mz=r5(U(rng, -5e4, 5e4))))
    ml = [dict(member=m["id"], wx=r5(U(rng, -5e3, 5e3)) if rng.rand() < 0.3 else 0.0, wy=r5(-U(rng, 1e3, 3e4))) for m in mems if rng.rand() < 0.5]
    fully_free = [n["id"] for n in nodes if not any(n["support"].values())] or free
    sq = sorted(set(int(x) for x in rng.choice(fully_free, size=min(len(fully_free), int(rng.randint(1, 7))), replace=False)))
    n_modes = int(rng.randint(3, 13))
    free_dofs = [(n["id"], d) for n in nodes for d in ("ux", "uy", "rz") if not n["support"][d]]
    hq = []
    for _ in range(int(rng.randint(1, 5))):
        ln, ld = free_dofs[int(rng.randint(len(free_dofs)))]
        rn, rd = free_dofs[int(rng.randint(len(free_dofs)))]
        hq.append(dict(load_node=int(ln), load_dof=ld, amplitude=r5(U(rng, 1e3, 1e5)), f_Hz=0.0, response_node=int(rn), response_dof=rd))
    return nl, ml, sq, n_modes, hq


def screen(m, want):
    try:
        tv.validate_frame(m, m["frame_id"])
    except AssertionError as error:
        return False, f"domain: {str(error)[:80]}", None
    F = fd.Frame(m)
    try:
        np.linalg.cholesky(F.assemble(0.0))
    except np.linalg.LinAlgError:
        return False, "mechanism", None
    t0 = time.time()
    try:
        rep = fd.solve(m)
    except Exception as error:
        return False, f"oracle: {error!r}"[:100], None
    if time.time() - t0 > 40:
        return False, "slow", rep
    fr = rep["frequencies_Hz"]
    n1 = F.frequencies(m["n_modes"] + 1)[-1] / (2 * math.pi)
    allf = fr + [n1]
    if any(b - a < 1e-6 * b for a, b in zip(allf, allf[1:])):
        return False, "frequencies too close", rep
    if any(abs(m["f_max_Hz"] - f) < 1e-6 * f for f in allf) or m["f_max_Hz"] > n1:
        return False, "f_max near a frequency or beyond the computed ones", rep
    # harmonic frequencies: at least 1e-2 relative from every natural frequency below them (and the next)
    for q in m["harmonic_queries"]:
        if any(abs(q["f_Hz"] - f) < 1e-2 * f for f in allf) or q["f_Hz"] > n1:
            return False, "harmonic frequency near a natural frequency", rep
    fmax_all = max([fr[-1], m["f_max_Hz"]] + [q["f_Hz"] for q in m["harmonic_queries"]])
    for mb in F.members:
        lam, alpha = mb.params(2 * math.pi * fmax_all)
        if lam > 40 or alpha > 40:
            return False, "lambda or alpha above 40", rep
    S = tv.scales(rep)
    for s in rep["static"]:
        for k in ("ux", "uy", "rz"):
            if abs(s[k]) < 1e-9 * (S["ro"] if k == "rz" else S["tr"]):
                return False, "tiny static value", rep
    for h in rep["harmonic"]:
        if h["U"] == 0.0 or abs(h["U"]) < 1e-9 * (S["hr"] if h["response_dof"] == "rz" else S["ht"]):
            return False, "tiny harmonic value", rep
    for s_ in rep["static"]:
        if any(s_[k] == 0.0 for k in ("ux", "uy", "rz")):
            return False, "zero static value", rep
    try:
        tv.validate_report(rep, m, m["frame_id"])
    except AssertionError as error:
        return False, f"report: {error}", rep
    return True, "ok", rep


def predicate(want, m, rep):
    fr = rep["frequencies_Hz"]
    if want.get("local_mode"):
        F = fd.Frame(m)
        # a member whose two nodes are fully fixed
        fixed = {n["id"] for n in m["nodes"] if all(n["support"].values())}
        if not any(mb["i"] in fixed and mb["j"] in fixed for mb in m["members"]): return False
    if want.get("close_pair") and not any((b - a) / b < 1e-2 for a, b in zip(fr, fr[1:])): return False
    if "min_count" in want and rep["count_below"] < want["min_count"]: return False
    if want.get("mass") and not any(n["mass_kg"] > 0 for n in m["nodes"]): return False
    if want.get("member_loads") and not m["member_loads"]: return False
    if want.get("harmonic_above_f1") and not any(q["f_Hz"] > fr[0] for q in m["harmonic_queries"]): return False
    if want.get("harmonic_below_f1") and not any(q["f_Hz"] < fr[0] for q in m["harmonic_queries"]): return False
    if "min_members" in want and len(m["members"]) < want["min_members"]: return False
    return True


PLAN = [
    ("model_01", True, "portal", dict(member_loads=True), "single-storey portal frame (base case)"),
    ("model_02", True, "cantilever", dict(min_count=4), "multi-member cantilever"),
    ("model_03", True, "fixed_member", dict(local_mode=True), "member between two fixed nodes: member-local modes"),
    ("model_04", True, "near_sym", dict(close_pair=True), "nearly symmetric frame with close frequencies"),
    ("model_05", True, "portal_mass", dict(mass=True, harmonic_above_f1=True), "frame with lumped masses, harmonic load above the first mode"),
    ("model_06", True, "truss_like", dict(min_members=8), "triangulated frame with rigid joints"),
    ("held_01", False, "cantilever", dict(), "cantilever beam"),
    ("held_02", False, "ss_beam", dict(member_loads=True), "simply supported beam with distributed load"),
    ("held_03", False, "portal", dict(min_members=6), "two-bay or two-storey portal frame"),
    ("held_04", False, "portal", dict(min_members=10), "multi-bay multi-storey frame"),
    ("held_05", False, "portal_mass", dict(mass=True), "frame with lumped masses"),
    ("held_06", False, "portal_mass", dict(mass=True, min_members=8), "larger frame with lumped masses"),
    ("held_07", False, "fixed_member", dict(local_mode=True, min_count=5), "member-local modes within the count"),
    ("held_08", False, "fixed_member", dict(local_mode=True), "member-local modes"),
    ("held_09", False, "near_sym", dict(close_pair=True), "close pair of frequencies"),
    ("held_10", False, "near_sym", dict(close_pair=True, member_loads=True), "close pair and distributed loads"),
    ("held_11", False, "stocky", dict(), "stocky members"),
    ("held_12", False, "slender", dict(min_count=6), "slender beam, many modes below f_max"),
    ("held_13", False, "arch", dict(), "polygonal arch"),
    ("held_14", False, "arch", dict(member_loads=True), "loaded polygonal arch"),
    ("held_15", False, "truss_like", dict(), "triangulated frame"),
    ("held_16", False, "truss_like", dict(min_members=10), "larger triangulated frame"),
    ("held_17", False, "portal", dict(harmonic_below_f1=True), "harmonic load below the first mode"),
    ("held_18", False, "portal", dict(harmonic_above_f1=True), "harmonic load above the first mode"),
    ("held_19", False, "ss_beam", dict(), "simply supported beam"),
    ("held_20", False, "cantilever", dict(member_loads=True), "cantilever with distributed load"),
    ("held_21", False, "portal_mass", dict(mass=True, close_pair=True), "masses and a close pair"),
    ("held_22", False, "portal", dict(min_members=12), "large frame"),
]


def build_slot(index):
    fid, shipped, style, want, label = PLAN[index]
    rng = np.random.RandomState(20261028 + 7919 * index)
    t0 = time.time()
    for attempt in range(1500):
        if time.time() - t0 > 1800:
            break
        try:
            nodes, mems = build(rng, style)
            nl, ml, sq, n_modes, hq = choose_queries(rng, nodes, mems, style)
            m = dict(frame_id=fid, nodes=nodes, members=mems, nodal_loads=nl, member_loads=ml, static_query_nodes=sq,
                     n_modes=n_modes, f_max_Hz=1.0, harmonic_queries=hq)
            # choose f_max and harmonic frequencies from a first solve
            F = fd.Frame(m)
            fr = [w / (2 * math.pi) for w in F.frequencies(n_modes + 1)]
            m["f_max_Hz"] = r5(min(500.0, max(1.0, U(rng, fr[0] * 1.05, fr[-2] * 1.3))))
            for q in hq:
                q["f_Hz"] = r5(max(0.1, min(500.0, U(rng, 0.2 * fr[0], fr[min(len(fr) - 1, 3)] * 0.95))))
            ok, why, rep = screen(m, want)
            if not ok:
                if DEBUG:
                    print("  reject", why, flush=True)
                continue
            if not predicate(want, m, rep):
                if DEBUG:
                    print("  reject predicate", flush=True)
                continue
        except Exception as error:
            if DEBUG:
                print("  reject error", repr(error)[:120], flush=True)
            continue
        json.dump(m, open(OUT / "frames" / f"{fid}.json", "w"), indent=1)
        log = dict(frame_id=fid, shipped=shipped, style=style, label=label, attempts=attempt + 1, nodes=len(nodes), members=len(mems),
                   n_modes=n_modes, f1=rep["frequencies_Hz"][0], count_below=rep["count_below"])
        json.dump(log, open(OUT / "log" / f"{fid}.json", "w"), indent=1)
        print(json.dumps(log), flush=True)
        return
    print(json.dumps(dict(frame_id=fid, failed=True, label=label)), flush=True)


if __name__ == "__main__":
    idx = [int(v) for v in sys.argv[3:]] or list(range(len(PLAN)))
    for i in idx:
        build_slot(i)
