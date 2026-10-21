"""Generate the graded traveltime models and screen them with the oracle for every guarantee of
TRAVELTIME_SPEC.md section 2. One random stream per model (deterministic).

usage: gen_models.py <raytimes.py> <out_dir> [indices...]
"""
import importlib.util
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("rt", sys.argv[1])
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)
OUT = Path(sys.argv[2])
(OUT / "models").mkdir(parents=True, exist_ok=True)
(OUT / "log").mkdir(parents=True, exist_ok=True)


def L(h, a, b):
    return {"thickness_km": None if h is None else float(round(h, 3)), "v_top_km_s": float(round(a, 3)),
            "gradient_per_s": float(round(b, 4))}


def grad(rng, lo, hi):
    g = rng.uniform(lo, hi)
    if abs(g) < 0.001:
        g = 0.001 if g >= 0 else -0.001
    return g


def build_layers(rng, style):
    """Random layer stack for a style; velocities kept in [1.5, 9.0] inside every layer."""
    for _ in range(1000):
        n = int(rng.randint(2, 7))
        layers, v = [], rng.uniform(1.6, 3.5)
        for k in range(n):
            last = k == n - 1
            h = None if last else rng.uniform(0.5, 15.0)
            if style == "constant":
                b = 0.0
            elif style == "lvz" and 0 < k < n - 1 and rng.rand() < 0.5:
                b = grad(rng, -0.3, -0.02)
            elif style == "caustic" and 0 < k < n - 1 and rng.rand() < 0.5:
                b = grad(rng, 0.5, 1.5); h = rng.uniform(0.5, 3.0)
            elif rng.rand() < (0.25 if style in ("mixed", "headwave") else 0.1):
                b = 0.0
            else:
                b = grad(rng, 0.002, 0.15 if style != "steep" else 0.8)
            if last and style == "gradient_halfspace":
                b = grad(rng, 0.002, 0.05)
            if last and style in ("constant_halfspace", "headwave", "far_head"):
                b = 0.0
            if k > 0:
                if style in ("lvz", "drop") and rng.rand() < 0.35:
                    v = v - rng.uniform(0.2, 1.2)              # velocity drop at the interface
                else:
                    v = v + rng.uniform(0.0, 1.5)
            v = min(max(v, 1.5), 8.5)
            vb = v + (b * h if h is not None else 0.0)
            if not (1.5 <= vb <= 9.0):
                break
            layers.append(L(h, v, b))
            v = vb if h is not None else v
        else:
            return layers
    return None


def events(rep, M, segs, spec):
    """Offsets where the number of arrivals changes (segment ends, head critical offsets) and
    the crossovers (interior first-arrival boundaries) and caustics."""
    ends = []
    for s in segs:
        ends += [s["X0"], s["X1"]]
    for kind, idx, p, xs, tau in spec:
        if xs > 0:
            ends.append(xs)
    cross = [f["x_end_km"] for f in rep["first_arrival"][:-1]]
    caus = [c["x_km"] for c in rep["caustics"]]
    return ends, cross, caus


def screen(m):
    t0 = time.time()
    rep = rt.solve(m)
    secs = time.time() - t0
    if secs > 20.0:
        return False, f"slow {secs:.1f}s", rep, secs
    M = rt.Model(m)
    segs, spec = M.segments(), M.specials()
    ends, cross, caus = events(rep, M, segs, spec)
    for x in m["offsets_km"]:
        for e in ends + cross + caus:
            if e > 0 and abs(x - e) < 1e-4 * x:
                return False, "offset near an event", rep, secs
    pts = sorted(cross + caus)
    for a, b in zip(pts, pts[1:]):
        if b > 0 and (b - a) / b < 1e-3:
            return False, "caustics/crossovers too close", rep, secs
    vels = set(M.a) | {v for v in M.vbot if math.isfinite(v)}
    for arr in rep["arrivals"]:
        rays = arr["rays"]
        if not rays:
            return False, "no arrival at an offset", rep, secs
        for i in range(len(rays)):
            for j in range(i + 1, len(rays)):
                if abs(rays[i]["t_s"] - rays[j]["t_s"]) < 1e-6 and abs(rays[i]["p_s_km"] - rays[j]["p_s_km"]) < 1e-6:
                    return False, "coincident arrivals", rep, secs
            for v in vels:
                if rays[i]["kind"] in ("turning", "reflection") and abs(rays[i]["p_s_km"] * v - 1.0) < 1e-8:
                    return False, "grazing arrival", rep, secs
    # no gap in the window: every first-arrival interval must be covered by its unit (a gap would
    # show as an interval whose exact time is infinite); check midpoints
    for f in rep["first_arrival"]:
        x = 0.5 * (f["x_start_km"] + f["x_end_km"])
        if not rt.solve(dict(m, offsets_km=[x]))["arrivals"][0]["rays"]:
            return False, "gap in the window", rep, secs
    return True, "ok", rep, secs


def choose_offsets(rng, m, rep0, n):
    """Offsets spread over the window, preferring places with many arrivals."""
    xmax = m["x_max_km"]
    grid = np.linspace(0.02 * xmax, xmax, 200)
    counts = [len(a["rays"]) for a in rt.solve(dict(m, offsets_km=[float(x) for x in grid]))["arrivals"]]
    order = np.argsort(-np.array(counts) + rng.uniform(0, 0.5, len(counts)))
    pick = sorted(set([float(f"{grid[i]:.5g}") for i in order[: n // 2]] +
                      [float(f"{x:.5g}") for x in rng.uniform(0.02 * xmax, xmax, n - n // 2)]))
    pick = [x for i, x in enumerate(pick) if i == 0 or x > pick[i - 1] * 1.001]
    return pick[:10]


PLAN = [
    ("model_01", True, "constant", dict(min_heads=2), "constant layers: direct and head waves (base case)"),
    ("model_02", True, "gradient_halfspace", dict(min_turning=2), "gradient crust over a gradient half-space"),
    ("model_03", True, "lvz", dict(lvz=True, refl_first=True), "low-velocity zone: reflection fills the shadow"),
    ("model_04", True, "caustic", dict(min_caustics=1), "strong-gradient zone with a caustic"),
    ("model_05", True, "drop", dict(drop=True, min_fa=3, refl_first=True), "velocity drop: shadow zone"),
    ("model_06", True, "far_head", dict(far_head=True), "head wave with critical offset beyond the window"),
    ("held_01", False, "constant", dict(min_heads=2), "constant layers"),
    ("held_02", False, "constant", dict(min_heads=3), "constant layers, three head waves"),
    ("held_03", False, "headwave", dict(min_heads=1, min_fa=3), "mixed layers with head waves"),
    ("held_04", False, "gradient_halfspace", dict(min_turning=2), "gradient layers"),
    ("held_05", False, "gradient_halfspace", dict(min_turning=3), "gradient layers, three turning branches"),
    ("held_06", False, "mixed", dict(min_fa=4), "first arrival with several crossovers"),
    ("held_07", False, "mixed", dict(min_fa=4), "first arrival with several crossovers"),
    ("held_08", False, "lvz", dict(lvz=True, neg=True), "negative-gradient low-velocity zone"),
    ("held_09", False, "lvz", dict(lvz=True, refl_first=True), "low-velocity zone: reflection fills the shadow"),
    ("held_10", False, "drop", dict(drop=True, refl_first=True), "velocity drop: reflection first"),
    ("held_11", False, "drop", dict(drop=True, min_fa=3, refl_first=True), "velocity drop: shadow zone"),
    ("held_12", False, "caustic", dict(min_caustics=1), "caustic on a turning branch"),
    ("held_13", False, "caustic", dict(min_caustics=2), "two caustics"),
    ("held_14", False, "caustic", dict(min_caustics=1, min_fa=3), "caustic and several first-arrival intervals"),
    ("held_15", False, "caustic", dict(min_arrivals=5), "triplication: five or more arrivals at one offset"),
    ("held_16", False, "steep", dict(min_arrivals=4), "steep gradients, four or more arrivals"),
    ("held_17", False, "far_head", dict(far_head=True), "head wave with critical offset beyond the window"),
    ("held_18", False, "constant_halfspace", dict(min_heads=1), "constant half-space below gradient layers"),
    ("held_19", False, "gradient_halfspace", dict(min_turning=1), "gradient half-space"),
    ("held_20", False, "mixed", dict(direct=True, min_fa=3), "direct wave and gradient layers"),
    ("held_21", False, "mixed", dict(), "mixed layers, long window"),
    ("held_22", False, "headwave", dict(min_heads=2), "head waves and post-critical reflections"),
]


def predicate(want, m, rep):
    lay = m["layers"]
    kinds = [r["kind"] for a in rep["arrivals"] for r in a["rays"]]
    heads = {r["index"] for a in rep["arrivals"] for r in a["rays"] if r["kind"] == "head"}
    turns = {r["index"] for a in rep["arrivals"] for r in a["rays"] if r["kind"] == "turning"}
    if len(heads) < want.get("min_heads", 0): return False
    if len(turns) < want.get("min_turning", 0): return False
    if len(rep["caustics"]) < want.get("min_caustics", 0): return False
    if want.get("refl_caustic") and not any(c["kind"] == "reflection" for c in rep["caustics"]): return False
    if max(len(a["rays"]) for a in rep["arrivals"]) < want.get("min_arrivals", 0): return False
    if len(rep["first_arrival"]) < want.get("min_fa", 0): return False
    if want.get("direct") and "direct" not in kinds: return False
    if want.get("refl_first") and not any(f["kind"] == "reflection" for f in rep["first_arrival"]): return False
    if want.get("neg") and not any(l["gradient_per_s"] < 0 for l in lay): return False
    if want.get("lvz") and not (any(l["gradient_per_s"] < 0 for l in lay) or drop_present(lay)): return False
    if want.get("drop") and not drop_present(lay): return False
    if want.get("far_head"):
        M = rt.Model(m)
        if not any(xs > m["x_max_km"] for kind, idx, p, xs, tau in M.specials() if kind == "head"): return False
    return True


def drop_present(lay):
    for k in range(1, len(lay)):
        prev = lay[k - 1]
        vb = prev["v_top_km_s"] + prev["gradient_per_s"] * prev["thickness_km"]
        if lay[k]["v_top_km_s"] < vb - 0.05:
            return True
    return False


def build(index):
    mid, shipped, style, want, label = PLAN[index]
    rng = np.random.RandomState(20261021 + 7919 * index)
    t0 = time.time()
    for attempt in range(3000):
        if time.time() - t0 > 900:
            break
        layers = build_layers(rng, style)
        if layers is None:
            continue
        depth = sum(l["thickness_km"] for l in layers[:-1])
        xmax = float(round(min(300.0, max(5.0, rng.uniform(4.0, 10.0) * depth)), 1))
        m = dict(model_id=mid, layers=layers, x_max_km=xmax, offsets_km=[0.5 * xmax, xmax])
        try:
            rep0 = rt.solve(m)
            if not predicate(want, m, rep0):
                continue
            m["offsets_km"] = choose_offsets(rng, m, rep0, int(rng.randint(5, 10)))
            if len(m["offsets_km"]) < 2:
                continue
            ok, why, rep, secs = screen(m)
        except Exception as e:
            continue
        if not ok or not predicate(want, m, rep):
            continue
        json.dump(m, open(OUT / "models" / f"{mid}.json", "w"), indent=1)
        log = dict(model_id=mid, shipped=shipped, label=label, layers=len(layers),
                   arrivals=[len(a["rays"]) for a in rep["arrivals"]], caustics=len(rep["caustics"]),
                   first_arrival=len(rep["first_arrival"]), secs=round(secs, 2), attempts=attempt + 1)
        json.dump(log, open(OUT / "log" / f"{mid}.json", "w"), indent=1)
        print(json.dumps(log), flush=True)
        return
    print(json.dumps(dict(model_id=mid, failed=True, label=label)), flush=True)


if __name__ == "__main__":
    idx = [int(v) for v in sys.argv[3:]] or list(range(len(PLAN)))
    for i in idx:
        build(i)
