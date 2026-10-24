#!/usr/bin/env python3
"""Ref B test suite.

  python tests/run_tests.py [--regen-hand] [--skip-long]

1. hand reports (closed forms, tests/hand.py) must PASS; Ref B's own solver
   must reproduce them (element-wise differences printed);
2. own --solve reports for every test structure must PASS;
3. double vs 80-bit long-double solver (measured precision);
4. negative tests: 3e-9 eV in a bound energy, 3e-9 relative in T (queries and
   maxima), 3e-8 eV in a maximum energy, a dropped bound state, a dropped
   maximum, an extra maximum, format violations must FAIL; perturbations of
   0.9x tolerance must PASS;
5. CLI exit codes.
"""
from __future__ import annotations

import argparse
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import referee  # noqa: E402

SDIR = os.path.join(HERE, "structures")
HDIR = os.path.join(HERE, "hand_reports")
HAND = ["hand_barrier", "hand_well", "hand_well_edge", "hand_triangle"]
STRESS = ["stress_doublewell", "stress_thickbarrier", "stress_superlattice",
          "stress_manylevels", "stress_graded150", "stress_nobound"]


def run_ref(struct, rep_obj, tmp, extra=(), raw_text=None):
    rp = os.path.join(tmp, "rep.json")
    vp = os.path.join(tmp, "verdict.json")
    with open(rp, "w", encoding="utf-8") as fh:
        if raw_text is not None:
            fh.write(raw_text)
        else:
            json.dump(rep_obj, fh)
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = referee.main(["--structure", struct, "--report", rp, "--out", vp, *extra])
    with open(vp) as fh:
        v = json.load(fh)
    return code, v, buf.getvalue().strip()


def solve(struct, out, precision="double"):
    buf = io.StringIO()
    with redirect_stdout(buf):
        referee.main(["--solve", "--structure", struct, "--output", out, "--precision", precision, "--quiet"])
    with open(out) as fh:
        return json.load(fh)


def diffs(a, b):
    """element-wise differences between two reports with equal counts"""
    out = {"counts_equal": (len(a["bound_states"]) == len(b["bound_states"]) and len(a["maxima"]) == len(b["maxima"]))}
    out["bound_dE"] = max([abs(x["E_eV"] - y["E_eV"]) for x, y in zip(a["bound_states"], b["bound_states"])], default=0.0)
    out["T_rel"] = max([abs(x["T"] / y["T"] - 1) for x, y in zip(a["transmission"], b["transmission"])], default=0.0)
    out["max_dE"] = max([abs(x["E_eV"] - y["E_eV"]) for x, y in zip(a["maxima"], b["maxima"])], default=0.0)
    out["max_T_rel"] = max([abs(x["T"] / y["T"] - 1) for x, y in zip(a["maxima"], b["maxima"])], default=0.0)
    return out


def fmtd(d):
    return (f"counts_equal={d['counts_equal']} bound_dE={d['bound_dE']:.1e} T_rel={d['T_rel']:.1e} "
            f"max_dE={d['max_dE']:.1e} max_T_rel={d['max_T_rel']:.1e}")


def negatives(base):
    """(name, mutated report or raw text, expected pass)"""
    cases = []
    nb, nm = len(base["bound_states"]), len(base["maxima"])

    def mut(f):
        r = copy.deepcopy(base)
        f(r)
        return r

    if nb:
        i = nb // 2
        cases.append(("bound E +3e-9", mut(lambda r: r["bound_states"][i].__setitem__("E_eV", r["bound_states"][i]["E_eV"] + 3e-9)), False))
        cases.append(("bound E -3e-9", mut(lambda r: r["bound_states"][i].__setitem__("E_eV", r["bound_states"][i]["E_eV"] - 3e-9)), False))
        cases.append(("bound E +0.9e-9", mut(lambda r: r["bound_states"][i].__setitem__("E_eV", r["bound_states"][i]["E_eV"] + 0.9e-9)), True))
        cases.append(("drop last bound state", mut(lambda r: r["bound_states"].pop()), False))
        cases.append(("drop first bound state", mut(lambda r: r["bound_states"].pop(0)), False))
    else:
        cases.append(("spurious bound state", mut(lambda r: r["bound_states"].append({"E_eV": -0.5})), False))
    j = len(base["transmission"]) // 2
    cases.append(("T x(1+3e-9)", mut(lambda r: r["transmission"][j].__setitem__("T", r["transmission"][j]["T"] * (1 + 3e-9))), False))
    cases.append(("T x(1-3e-9)", mut(lambda r: r["transmission"][j].__setitem__("T", r["transmission"][j]["T"] * (1 - 3e-9))), False))
    cases.append(("T x(1+0.9e-9)", mut(lambda r: r["transmission"][j].__setitem__("T", r["transmission"][j]["T"] * (1 + 0.9e-9))), True))
    if nm:
        k = nm // 2
        cases.append(("max E +3e-8", mut(lambda r: r["maxima"][k].__setitem__("E_eV", r["maxima"][k]["E_eV"] + 3e-8)), False))
        cases.append(("max E -3e-8", mut(lambda r: r["maxima"][k].__setitem__("E_eV", r["maxima"][k]["E_eV"] - 3e-8)), False))
        cases.append(("max E +0.9e-8", mut(lambda r: r["maxima"][k].__setitem__("E_eV", r["maxima"][k]["E_eV"] + 0.9e-8)), True))
        cases.append(("max T x(1+3e-9)", mut(lambda r: r["maxima"][k].__setitem__("T", r["maxima"][k]["T"] * (1 + 3e-9))), False))
        cases.append(("drop a maximum", mut(lambda r: r["maxima"].pop(k)), False))
    cases.append(("extra maximum", mut(lambda r: r["maxima"].append({"E_eV": 1e3, "T": 0.5})), False))
    cases.append(("extra key", mut(lambda r: r.__setitem__("note", "x")), False))
    cases.append(("query energy altered by 1 ulp", mut(lambda r: r["transmission"][0].__setitem__("E_eV", r["transmission"][0]["E_eV"] * (1 + 2.3e-16))), False))
    cases.append(("wrong structure_id", mut(lambda r: r.__setitem__("structure_id", r["structure_id"] + "x")), False))
    txt = json.dumps(base)
    cases.append(("duplicate key", txt[:-1] + ', "maxima": []}', False))
    cases.append(("NaN number", txt.replace('"T": ', '"T": NaN, "_": ', 1), False))
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regen-hand", action="store_true")
    ap.add_argument("--skip-long", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    nfail = 0
    if a.regen_hand:
        subprocess.check_call([sys.executable, os.path.join(HERE, "make_stress.py")])
        subprocess.check_call([sys.executable, os.path.join(HERE, "hand.py")])
    tmp = tempfile.mkdtemp(prefix="refB_tests_")
    print("== 1. hand (closed-form) reports ==")
    for sid in HAND:
        st = os.path.join(SDIR, sid + ".json")
        hand = json.load(open(os.path.join(HDIR, sid + ".json")))
        code, v, line = run_ref(st, hand, tmp)
        ok = code == 0
        nfail += not ok
        own = solve(st, os.path.join(tmp, sid + "_own.json"))
        print(f"  [{'ok' if ok else 'FAIL'}] referee on hand report: {line}")
        print(f"        own solver vs hand: {fmtd(diffs(own, hand))}")
    print("== 2. own solver reports must pass; 3. double vs long double ==")
    owns = {}
    for sid in HAND + STRESS:
        st = os.path.join(SDIR, sid + ".json")
        own = solve(st, os.path.join(tmp, sid + "_own.json"))
        owns[sid] = own
        code, v, line = run_ref(st, own, tmp)
        ok = code == 0 and not v["warnings"]
        nfail += not ok
        print(f"  [{'ok' if ok else 'FAIL'}] {line}")
        if not a.skip_long:
            lng = solve(st, os.path.join(tmp, sid + "_long.json"), precision="long")
            print(f"        double vs long: {fmtd(diffs(own, lng))}")
    print("== 4. negative and tolerance-edge tests ==")
    for sid in ["hand_barrier", "hand_well", "hand_well_edge", "hand_triangle", "stress_doublewell",
                "stress_manylevels", "stress_superlattice", "stress_thickbarrier"]:
        st = os.path.join(SDIR, sid + ".json")
        base = json.load(open(os.path.join(HDIR, sid + ".json"))) if sid in HAND else owns[sid]
        res = []
        for name, rep, expect in negatives(base):
            if isinstance(rep, str):
                code, v, line = run_ref(st, None, tmp, raw_text=rep)
            else:
                code, v, line = run_ref(st, rep, tmp)
            got = code == 0
            good = got == expect
            nfail += not good
            res.append(f"{'ok' if good else 'WRONG'}:{name}->{'PASS' if got else 'FAIL'}")
            if not good:
                print(f"  WRONG {sid} {name}: {line} {v.get('failures')}")
        print(f"  {sid}: " + "; ".join(res))
    print("== 5. CLI exit codes ==")
    st = os.path.join(SDIR, "hand_well.json")
    good_rep = os.path.join(HDIR, "hand_well.json")
    bad = copy.deepcopy(json.load(open(good_rep)))
    bad["bound_states"].pop()
    bad_rep = os.path.join(tmp, "bad.json")
    json.dump(bad, open(bad_rep, "w"))
    for rp, want in ((good_rep, 0), (bad_rep, 1)):
        p = subprocess.run([sys.executable, os.path.join(ROOT, "referee.py"), "--structure", st, "--report", rp],
                           capture_output=True, text=True)
        ok = p.returncode == want
        nfail += not ok
        print(f"  [{'ok' if ok else 'FAIL'}] exit {p.returncode} (want {want}): {p.stdout.strip()}")
    print(f"== done: {nfail} unexpected results, {time.time() - t0:.0f}s ==")
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())
