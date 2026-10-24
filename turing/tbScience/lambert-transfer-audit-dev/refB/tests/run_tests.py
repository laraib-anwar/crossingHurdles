#!/usr/bin/env python3
"""refB self-tests.

1. The two constructed systems (make_tests.py): the --solve third opinion is compared with the
   closed-form hand values, and the referee must pass the solver's report.
2. Negative tests: small corruptions of a passing report must FAIL (exit status 1): every
   corruption is 3x the contract tolerance or a discrete change.  The same continuous
   perturbations at 0.3x the tolerance must PASS.

usage: python run_tests.py [--oracle SYSTEM.json REPORT.json] ...   (extra passing pairs to corrupt)
"""
import argparse
import copy
import json
import math
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(os.path.dirname(HERE), "referee.py")
sys.path.insert(0, os.path.dirname(HERE))
import referee as rf  # noqa: E402

PY = sys.executable


def relv(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b))) / math.sqrt(sum(y * y for y in b))


def rels(a, b):
    return abs(a - b) / abs(b)


def run_cli(system_path, report_path):
    return subprocess.run([PY, REF, "--system", system_path, "--report", report_path, "--quiet"]).returncode


def solve(system_path, out_path):
    subprocess.run([PY, REF, "--solve", "--quiet", "--system", system_path, "--output", out_path], check=True)


def check_hand(sid, rep, hand, problems):
    def need(cond, msg):
        if not cond:
            problems.append("%s: %s" % (sid, msg))

    for k, h in enumerate(hand["ephemeris"]):
        need(relv(rep["ephemeris"][k]["r_km"], h["r_km"]) < 1e-12, "ephemeris %d r vs hand %.2e" % (k, relv(rep["ephemeris"][k]["r_km"], h["r_km"])))
        need(relv(rep["ephemeris"][k]["v_km_s"], h["v_km_s"]) < 1e-12, "ephemeris %d v vs hand" % k)
    for key in ("transfer0", "transfer1", "transfer2"):
        if key not in hand:
            continue
        h = hand[key]
        t = rep["transfers"][int(key[-1])]
        need(abs(t["theta_deg"] - h["theta_deg"]) < 1e-9, "%s theta %.15g vs hand %.15g" % (key, t["theta_deg"], h["theta_deg"]))
        if "N0_v1_km_s" in h:
            s = t["solutions"][0]
            need(len(t["solutions"]) == h["solutions"], "%s count" % key)
            need(relv(s["v1_km_s"], h["N0_v1_km_s"]) < 1e-10, "%s v1 vs hand %.2e" % (key, relv(s["v1_km_s"], h["N0_v1_km_s"])))
            need(relv(s["v2_km_s"], h["N0_v2_km_s"]) < 1e-10, "%s v2 vs hand %.2e" % (key, relv(s["v2_km_s"], h["N0_v2_km_s"])))
            need(rels(s["a_km"], h["N0_a_km"]) < 1e-10, "%s a vs hand" % key)
            need(rels(s["e"], h["N0_e"]) < 1e-10, "%s e vs hand" % key)
            need(rels(s["dv_km_s"], h["N0_dv_km_s"]) < 1e-10, "%s dv vs hand %.2e" % (key, rels(s["dv_km_s"], h["N0_dv_km_s"])))
            tm = t["t_min_days"][0]
            need(h["t_min1_lower_days"] < tm < h["t_min1_upper_days"], "%s T_min(1) %.9g outside hand bounds" % (key, tm))
            need(h["T_days"] < h["t_min1_lower_days"], "%s hand: T below T_min(1) lower bound, so no N=1 arc" % key)
    print("  %s: hand values checked" % sid)


def corruptions(rep, scale=3e-9):
    """(name, corrupted report) pairs; each must fail.  With scale=3e-10 only the continuous
    perturbations are returned, and each of those must pass (the referee is not stricter than
    the contract)."""
    out = []
    # pick the transfer with the most solutions
    k = max(range(len(rep["transfers"])), key=lambda i: len(rep["transfers"][i]["solutions"]))
    t = rep["transfers"][k]
    j = len(t["solutions"]) - 1

    def perturb(vecv, rel):
        n = math.sqrt(sum(x * x for x in vecv))
        d = [0.6, -0.48, 0.64]   # unit vector
        return [x + rel * n * dd for x, dd in zip(vecv, d)]

    x = scale
    c = copy.deepcopy(rep)
    c["transfers"][k]["solutions"][j]["v1_km_s"] = perturb(t["solutions"][j]["v1_km_s"], x)
    out.append(("v1 x (1 + %g dir)" % x, c))
    c = copy.deepcopy(rep)
    c["transfers"][k]["solutions"][j]["v2_km_s"] = perturb(t["solutions"][j]["v2_km_s"], x)
    out.append(("v2 x (1 + %g dir)" % x, c))
    c = copy.deepcopy(rep)
    c["ephemeris"][0]["r_km"] = perturb(rep["ephemeris"][0]["r_km"], x)
    out.append(("ephemeris r x (1 + %g dir)" % x, c))
    for key in ("a_km", "e", "dv_km_s"):
        c = copy.deepcopy(rep)
        c["transfers"][k]["solutions"][j][key] *= 1 + x
        out.append(("%s x (1 + %g)" % (key, x), c))
    c = copy.deepcopy(rep)
    c["transfers"][k]["theta_deg"] += x
    out.append(("theta + %g deg" % x, c))
    if t["t_min_days"]:
        c = copy.deepcopy(rep)
        c["transfers"][k]["t_min_days"][-1] *= 1 + x
        out.append(("T_min(n_max) x (1 + %g)" % x, c))
    if scale < 1e-9:
        return out
    if len(t["solutions"]) > 1:
        c = copy.deepcopy(rep)
        dropped = c["transfers"][k]["solutions"].pop(j)
        c["transfers"][k]["best"] = min(c["transfers"][k]["best"], len(c["transfers"][k]["solutions"]) - 1)
        out.append(("drop solution N=%d %s" % (dropped["N"], dropped["branch"]), c))
        c = copy.deepcopy(rep)
        c["transfers"][k]["best"] = (t["best"] + 1) % len(t["solutions"])
        out.append(("best moved", c))
    pairs = [i for i in range(len(t["solutions"]) - 1) if t["solutions"][i]["branch"] == "low"]
    if pairs:
        i = pairs[-1]
        c = copy.deepcopy(rep)
        s = c["transfers"][k]["solutions"]
        s[i]["branch"], s[i + 1]["branch"] = "high", "low"
        s[i], s[i + 1] = s[i + 1], s[i]          # keep the low-before-high order: values swapped
        if c["transfers"][k]["best"] in (i, i + 1):
            c["transfers"][k]["best"] = 2 * i + 1 - c["transfers"][k]["best"]
        out.append(("swap low/high labels of N=%d" % t["solutions"][i]["N"], c))
        c = copy.deepcopy(rep)
        c["transfers"][k]["solutions"][i]["branch"], c["transfers"][k]["solutions"][i + 1]["branch"] = "high", "low"
        out.append(("swap low/high labels in place", c))
    return out


def negative_tests(system_path, report, tmp, problems):
    system = rf.load_json(system_path)
    base = rf.referee(system, report)
    if not base["pass"]:
        problems.append("%s: baseline report does not pass, negative tests skipped" % system["system_id"])
        return
    for name, c in corruptions(report):
        v = rf.referee(system, c)
        status = "FAIL (as required)" if not v["pass"] else "PASS (WRONG)"
        first = v["failures"][0] if v["failures"] else ""
        print("    %-36s %s  %s" % (name, status, first[:110]))
        if v["pass"]:
            problems.append("%s: corruption '%s' was not detected" % (system["system_id"], name))
    for name, c in corruptions(report, 3e-10):
        v = rf.referee(system, c)
        print("    %-36s %s" % (name, "PASS (as required)" if v["pass"] else "FAIL (WRONG) " + v["failures"][0][:100]))
        if not v["pass"]:
            problems.append("%s: in-tolerance perturbation '%s' was rejected" % (system["system_id"], name))
    # the command line: exit status 0 for the clean report, 1 for one corruption
    clean = os.path.join(tmp, "clean.json")
    bad = os.path.join(tmp, "bad.json")
    with open(clean, "w") as fh:
        json.dump(report, fh)
    with open(bad, "w") as fh:
        json.dump(corruptions(report)[0][1], fh)
    if run_cli(system_path, clean) != 0 or run_cli(system_path, bad) != 1:
        problems.append("%s: command-line exit status wrong" % system["system_id"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oracle", nargs=2, action="append", default=[], metavar=("SYSTEM", "REPORT"))
    args = ap.parse_args()
    problems = []
    hands = json.load(open(os.path.join(HERE, "hand_values.json")))
    with tempfile.TemporaryDirectory() as tmp:
        for sid in sorted(hands):
            sp = os.path.join(HERE, sid + ".json")
            rp = os.path.join(tmp, sid + ".report.json")
            solve(sp, rp)
            rep = json.load(open(rp))
            print("%s (solver report)" % sid)
            check_hand(sid, rep, hands[sid], problems)
            negative_tests(sp, rep, tmp, problems)
        for sp, rp in args.oracle:
            print("%s (given report %s)" % (os.path.basename(sp), os.path.basename(rp)))
            negative_tests(sp, rf.load_json(rp), tmp, problems)
    print("PROBLEMS:" if problems else "all refB self-tests passed")
    for p in problems:
        print("  " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
