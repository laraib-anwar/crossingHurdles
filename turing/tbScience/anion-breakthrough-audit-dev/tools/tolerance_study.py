"""Tolerance study (dev tool; its results go into the README).

Leg 1, method spread: largest difference per graded quantity between the oracle and
Reference A (both exact, different methods) over all recipes, and between the oracle and the
Reference B finite-volume extrapolation where available.
Leg 2, nearest wrong answer: for each wrong-method control, the smallest error it makes on any
graded quantity where it differs from the exact value, and its pass count under the verifier's
compare() with the spec tolerances.

usage: tolerance_study.py <recipes_dir> <oracle_dir> <refA_dir> <controls_root> <test_outputs.py>
       controls_root holds <control>/<recipe>.json
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

recipes = {p.stem: json.loads(p.read_text()) for p in Path(sys.argv[1]).glob("*.json")}
oracle = {p.stem: json.loads(p.read_text()) for p in Path(sys.argv[2]).glob("*.json")}
refA = {p.stem: json.loads(p.read_text()) for p in Path(sys.argv[3]).glob("*.json")}
for _k in oracle:
    refA.setdefault(_k, oracle[_k])   # fallback while a reference report is missing
controls_root = Path(sys.argv[4])
spec = importlib.util.spec_from_file_location("T", sys.argv[5])
T = importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)


def quantities(rep):
    """(name, kind, value) triples; kind 'bv' (relative tol) or 'c' (absolute meq/L) or 'count'."""
    out = [("shocks.count", "count", len(rep["shocks"])), ("transitions.count", "count", len(rep["transitions"])),
           ("plateaus.count", "count", len(rep["plateaus"]))]
    for i, s in enumerate(rep["shocks"]):
        out.append((f"shocks[{i}].bv", "bv", s["bv"]))
        out += [(f"shocks[{i}].before[{j}]", "c", v) for j, v in enumerate(s["before_meq_per_L"])]
        out += [(f"shocks[{i}].after[{j}]", "c", v) for j, v in enumerate(s["after_meq_per_L"])]
    for i, t in enumerate(rep["transitions"]):
        out += [(f"transitions[{i}].bv_start", "bv", t["bv_start"]), (f"transitions[{i}].bv_end", "bv", t["bv_end"])]
        out += [(f"transitions[{i}].start[{j}]", "c", v) for j, v in enumerate(t["start_meq_per_L"])]
        out += [(f"transitions[{i}].end[{j}]", "c", v) for j, v in enumerate(t["end_meq_per_L"])]
    for i, p in enumerate(rep["plateaus"]):
        out += [(f"plateaus[{i}].bv_start", "bv", p["bv_start"]), (f"plateaus[{i}].bv_end", "bv", p["bv_end"])]
        out += [(f"plateaus[{i}].c[{j}]", "c", v) for j, v in enumerate(p["composition_meq_per_L"])]
    out += [("nitrate_peak.meq_per_L", "c", rep["nitrate_peak"]["meq_per_L"]), ("nitrate_peak.bv", "bv", rep["nitrate_peak"]["bv"])]
    out.append(("nitrate_limit_bv", "bv", rep["nitrate_limit_bv"]))
    for i, s in enumerate(rep["samples"]):
        out += [(f"samples[{i}][{j}]", "c", v) for j, v in enumerate(s)]
    return out


def spread(a, b):
    """Per kind: largest |difference| (relative for bv) between two reports of the same structure."""
    qa, qb = dict((n, (k, v)) for n, k, v in quantities(a)), dict((n, (k, v)) for n, k, v in quantities(b))
    worst = {"bv": (0.0, ""), "c": (0.0, ""), "count": (0, "")}
    for n, (k, va) in qa.items():
        if n not in qb:
            worst["count"] = (1, n); continue
        vb = qb[n][1]
        if va is None or vb is None:
            if va != vb: worst["count"] = (1, n)
            continue
        d = abs(va - vb) / max(1.0, abs(vb)) if k == "bv" else abs(va - vb)
        if d > worst[k][0]:
            worst[k] = (d, n)
    return worst


print("== Leg 1: method spread, oracle vs Reference A")
wbv, wc, bad = (0.0, "", ""), (0.0, "", ""), []
for rid in sorted(recipes):
    if rid not in refA or rid not in oracle:
        bad.append(f"{rid}: missing report"); continue
    w = spread(oracle[rid], refA[rid])
    if w["count"][0]:
        bad.append(f"{rid}: structure differs at {w['count'][1]}"); continue
    if w["bv"][0] > wbv[0]: wbv = (w["bv"][0], rid, w["bv"][1])
    if w["c"][0] > wc[0]: wc = (w["c"][0], rid, w["c"][1])
print(f"  worst relative BV difference {wbv[0]:.2e} ({wbv[1]} {wbv[2]})")
print(f"  worst composition difference {wc[0]:.2e} meq/L ({wc[1]} {wc[2]})")
for b in bad: print("  !!", b)

print("== Leg 2: wrong-method controls (graded with the verifier's compare at the spec tolerances)")
for ctrl in sorted(p.name for p in controls_root.iterdir() if p.is_dir()):
    passed, total, min_bv, min_c = 0, 0, (np.inf, ""), (np.inf, "")
    for rid in sorted(recipes):
        p = controls_root / ctrl / f"{rid}.json"
        if not p.exists():
            continue
        total += 1
        rep = json.loads(p.read_text())
        try:
            T.validate_report(rep, recipes[rid], rid)
            ok = not T.compare(rep, refA[rid], rid)
        except AssertionError:
            ok = False
        passed += ok
        # the smallest non-zero error the control makes on any quantity of the right structure
        qa, qb = dict((n, (k, v)) for n, k, v in quantities(rep)), dict((n, (k, v)) for n, k, v in quantities(refA[rid]))
        for n, (k, va) in qa.items():
            if n in qb and va is not None and qb[n][1] is not None and k != "count":
                vb = qb[n][1]
                d = abs(va - vb) / max(1.0, abs(vb)) if k == "bv" else abs(va - vb)
                if k == "bv" and 1e-12 < d < min_bv[0]: min_bv = (d, f"{rid} {n}")
                if k == "c" and 1e-12 < d < min_c[0]: min_c = (d, f"{rid} {n}")
    print(f"  {ctrl:10s} passes {passed}/{total}; smallest non-zero BV error {min_bv[0]:.2e} ({min_bv[1]}); smallest composition error {min_c[0]:.2e} ({min_c[1]})")
