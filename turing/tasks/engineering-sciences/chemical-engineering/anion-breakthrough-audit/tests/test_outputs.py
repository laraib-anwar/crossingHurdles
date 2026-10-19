"""Verifier for anion-breakthrough-audit.

Grades the saved artifacts and fresh runs of /root/results/ixfront.py on the shipped and
held-out recipes against expected values computed by an independent implementation
(/tests/expected.json, from /tests/reference/reference.py), and checks the diagnosis witnesses
by executing the pristine legacy script and the independent reference. Every comparison is the
one IX_SPEC.md states; contract validation runs before any value is compared.
"""
import json
import math
import os
import pwd
import re
import shutil
import signal
import stat
import subprocess

from pathlib import Path

import pytest

ARTIFACT = Path("/root/results/ixfront.py")
BASE_REPORT = Path("/root/results/base_case_report.json")
DIAGNOSIS = Path("/root/results/diagnosis.json")
CASES = Path("/tests/cases")
EXPECTED_PATH = Path("/tests/expected.json")
LEGACY = Path("/tests/legacy/ixbreak.py")
REFERENCE = Path("/tests/reference/reference.py")
SANDBOX = Path("/sandbox")
CALL_SECONDS = 60
TOL_BV_REL, TOL_BV_ABS, TOL_C = 2e-4, 1e-6, 1e-4
IONS = ["chloride", "nitrate", "sulfate", "bicarbonate"]
QUANTITIES = {"sample", "nitrate_peak", "nitrate_limit_bv", "shock_count", "transition_count"}
CASE_NAMES = sorted(p.stem for p in CASES.glob("*.json"))
BASE_CASE = "service_01"


# ------------------------------------------------------------------ small helpers
def strict_pairs(pairs):
    out = {}
    for key, value in pairs:
        assert key not in out, f"duplicate JSON key {key!r}"
        out[key] = value
    return out


def regular_file(path):
    """A submitted artifact must be a plain regular file: no symlink, FIFO, device or directory."""
    assert path.exists(), f"{path}: missing"
    assert not path.is_symlink() and stat.S_ISREG(os.lstat(path).st_mode), f"{path}: not a regular file"


def read_json(path):
    regular_file(path)
    assert 0 < path.stat().st_size <= 1_000_000, f"{path}: must be non-empty and at most 1 MB"
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=strict_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        pytest.fail(f"{path}: not valid UTF-8 JSON: {error}")


def number(v):
    return type(v) in (int, float) and math.isfinite(v)


def integer(v):
    return type(v) is int


def tol_bv(ref):
    return max(TOL_BV_REL * abs(ref), TOL_BV_ABS)


def close_bv(a, ref):
    return abs(a - ref) <= tol_bv(ref)


def close_c(a, ref):
    return all(abs(u - v) <= TOL_C for u, v in zip(a, ref))


def load_expected():
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ recipe domain (spec 2, 3)
def validate_recipe(r, label):
    keys = {"recipe_id", "ions", "alpha", "eps", "Q_eq_per_L_bed", "C_T_meq_per_L", "initial_resin_fraction",
            "feed_program", "run_bv", "sample_bv", "nitrate_limit_meq_per_L"}
    assert isinstance(r, dict) and set(r) == keys, f"{label}: recipe keys must be exactly {sorted(keys)}"
    assert isinstance(r["recipe_id"], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", r["recipe_id"]), f"{label}: bad recipe_id"
    assert r["ions"] == IONS, f"{label}: ions must be {IONS}"
    a = r["alpha"]
    assert isinstance(a, dict) and set(a) == set(IONS) and all(number(a[i]) for i in IONS), f"{label}: alpha"
    assert a["chloride"] == 1, f"{label}: alpha chloride must be 1"
    assert 1.5 <= a["nitrate"] <= 6.0 and 2.0 <= a["sulfate"] <= 25.0 and 0.10 <= a["bicarbonate"] <= 0.60, f"{label}: alpha domain"
    vals = [a[i] for i in IONS]
    assert min(abs(u - v) for i, u in enumerate(vals) for v in vals[i + 1:]) >= 0.005, f"{label}: separation factors too close"
    assert number(r["eps"]) and 0.35 <= r["eps"] <= 0.45, f"{label}: eps domain"
    assert number(r["Q_eq_per_L_bed"]) and 0.8 <= r["Q_eq_per_L_bed"] <= 1.6, f"{label}: Q domain"
    CT = r["C_T_meq_per_L"]
    assert number(CT) and 2.0 <= CT <= 15.0, f"{label}: C_T domain"
    y = r["initial_resin_fraction"]
    assert isinstance(y, dict) and set(y) == set(IONS) and all(number(y[i]) and 0 <= y[i] <= 1 for i in IONS), f"{label}: initial_resin_fraction"
    assert abs(math.fsum(y[i] for i in IONS) - 1.0) <= 1e-9, f"{label}: initial_resin_fraction must sum to 1"
    fp = r["feed_program"]
    assert isinstance(fp, list) and 1 <= len(fp) <= 2, f"{label}: feed_program must have 1 or 2 entries"
    assert number(r["run_bv"]) and 1.0 <= r["run_bv"] <= 5000.0, f"{label}: run_bv domain"
    for n, step in enumerate(fp):
        assert isinstance(step, dict) and set(step) == {"start_bv", "composition_meq_per_L"}, f"{label}: feed entry keys"
        c = step["composition_meq_per_L"]
        assert isinstance(c, dict) and set(c) == set(IONS) and all(number(c[i]) and 0 <= c[i] <= CT for i in IONS), f"{label}: feed composition"
        assert abs(math.fsum(c[i] for i in IONS) - CT) <= 1e-9 * CT, f"{label}: feed composition must sum to C_T"
        assert number(step["start_bv"]), f"{label}: start_bv"
        if n == 0:
            assert step["start_bv"] == 0, f"{label}: first feed must start at 0"
        else:
            assert 0 < step["start_bv"] < r["run_bv"], f"{label}: second feed start_bv must lie in (0, run_bv)"
    s = r["sample_bv"]
    assert isinstance(s, list) and len(s) <= 12 and all(number(v) and 0 < v <= r["run_bv"] for v in s), f"{label}: sample_bv"
    assert all(u < v for u, v in zip(s, s[1:])), f"{label}: sample_bv must increase strictly"
    assert number(r["nitrate_limit_meq_per_L"]) and 0.1 <= r["nitrate_limit_meq_per_L"] <= 2.0, f"{label}: nitrate limit domain"


# ------------------------------------------------------------------ report contract (spec 4)
def composition(v, label):
    assert isinstance(v, list) and len(v) == 4 and all(number(x) for x in v), f"{label}: must be a list of 4 finite numbers"


def validate_report(rep, recipe, label):
    run_bv = recipe["run_bv"]
    keys = {"recipe_id", "ions", "shocks", "transitions", "plateaus", "nitrate_peak", "nitrate_limit_bv", "samples"}
    assert isinstance(rep, dict) and set(rep) == keys, f"{label}: report keys must be exactly {sorted(keys)}"
    assert rep["recipe_id"] == recipe["recipe_id"], f"{label}: recipe_id must be {recipe['recipe_id']!r}"
    assert rep["ions"] == IONS, f"{label}: ions must be {IONS}"

    def in_window(v, name):
        assert number(v) and 0.0 <= v <= run_bv, f"{label}: {name} must be a finite number in [0, run_bv]"
    assert isinstance(rep["shocks"], list), f"{label}: shocks must be a list"
    for n, s in enumerate(rep["shocks"]):
        assert isinstance(s, dict) and set(s) == {"bv", "before_meq_per_L", "after_meq_per_L"}, f"{label}: shocks[{n}] keys"
        in_window(s["bv"], f"shocks[{n}].bv")
        composition(s["before_meq_per_L"], f"{label}: shocks[{n}].before_meq_per_L")
        composition(s["after_meq_per_L"], f"{label}: shocks[{n}].after_meq_per_L")
    bvs = [s["bv"] for s in rep["shocks"]]
    assert all(u < v for u, v in zip(bvs, bvs[1:])), f"{label}: shocks must be in strictly increasing bv"
    assert isinstance(rep["transitions"], list), f"{label}: transitions must be a list"
    for n, t in enumerate(rep["transitions"]):
        assert isinstance(t, dict) and set(t) == {"bv_start", "bv_end", "start_meq_per_L", "end_meq_per_L"}, f"{label}: transitions[{n}] keys"
        in_window(t["bv_start"], f"transitions[{n}].bv_start"); in_window(t["bv_end"], f"transitions[{n}].bv_end")
        assert t["bv_start"] < t["bv_end"], f"{label}: transitions[{n}] needs bv_start < bv_end"
        composition(t["start_meq_per_L"], f"{label}: transitions[{n}].start_meq_per_L")
        composition(t["end_meq_per_L"], f"{label}: transitions[{n}].end_meq_per_L")
    assert isinstance(rep["plateaus"], list), f"{label}: plateaus must be a list"
    for n, p in enumerate(rep["plateaus"]):
        assert isinstance(p, dict) and set(p) == {"bv_start", "bv_end", "composition_meq_per_L"}, f"{label}: plateaus[{n}] keys"
        in_window(p["bv_start"], f"plateaus[{n}].bv_start"); in_window(p["bv_end"], f"plateaus[{n}].bv_end")
        assert p["bv_start"] < p["bv_end"], f"{label}: plateaus[{n}] needs bv_start < bv_end"
        composition(p["composition_meq_per_L"], f"{label}: plateaus[{n}].composition_meq_per_L")
    starts = [t["bv_start"] for t in rep["transitions"]]
    assert all(u < v for u, v in zip(starts, starts[1:])), f"{label}: transitions must be in increasing bv_start"
    starts = [p["bv_start"] for p in rep["plateaus"]]
    assert all(u < v for u, v in zip(starts, starts[1:])), f"{label}: plateaus must be in increasing bv_start"
    # coverage: plateaus and transitions tile [0, run_bv] exactly; every shock is a boundary
    intervals = sorted([(p["bv_start"], p["bv_end"]) for p in rep["plateaus"]] +
                       [(t["bv_start"], t["bv_end"]) for t in rep["transitions"]])
    assert intervals, f"{label}: at least one plateau or transition is required"
    assert intervals[0][0] == 0.0, f"{label}: the first plateau or transition must start at 0"
    assert intervals[-1][1] == run_bv, f"{label}: the last plateau or transition must end at run_bv ({run_bv!r})"
    for (a0, a1), (b0, b1) in zip(intervals, intervals[1:]):
        assert a1 == b0, f"{label}: intervals must share their boundary exactly ({a1!r} vs {b0!r})"
    bounds = {v for iv in intervals for v in iv}
    for s in rep["shocks"]:
        assert s["bv"] in bounds, f"{label}: shock at {s['bv']!r} is not a boundary of a plateau or transition"
    pk = rep["nitrate_peak"]
    assert isinstance(pk, dict) and set(pk) == {"meq_per_L", "bv"}, f"{label}: nitrate_peak keys"
    assert number(pk["meq_per_L"]), f"{label}: nitrate_peak.meq_per_L must be a finite number"
    in_window(pk["bv"], "nitrate_peak.bv")
    lb = rep["nitrate_limit_bv"]
    assert lb is None or (number(lb) and 0.0 <= lb <= run_bv), f"{label}: nitrate_limit_bv must be null or a finite number in [0, run_bv]"
    assert isinstance(rep["samples"], list) and len(rep["samples"]) == len(recipe["sample_bv"]), \
        f"{label}: samples must have one entry per sample_bv ({len(recipe['sample_bv'])})"
    for n, s in enumerate(rep["samples"]):
        composition(s, f"{label}: samples[{n}]")


def compare(rep, exp, label):
    """Failures of the comparison of spec section 5; empty list means pass."""
    errs = []
    for name in ("shocks", "transitions", "plateaus"):
        if len(rep[name]) != len(exp[name]):
            errs.append(f"{label}: {len(rep[name])} {name} reported, {len(exp[name])} expected")
    if errs:
        return errs
    for n, (s, e) in enumerate(zip(rep["shocks"], exp["shocks"])):
        if not close_bv(s["bv"], e["bv"]):
            errs.append(f"{label}: shocks[{n}].bv {s['bv']:.6f} vs {e['bv']:.6f} (tol {tol_bv(e['bv']):.2e})")
        for side in ("before_meq_per_L", "after_meq_per_L"):
            if not close_c(s[side], e[side]):
                errs.append(f"{label}: shocks[{n}].{side} {s[side]} vs {e[side]} (tol {TOL_C})")
    for n, (t, e) in enumerate(zip(rep["transitions"], exp["transitions"])):
        for key in ("bv_start", "bv_end"):
            if not close_bv(t[key], e[key]):
                errs.append(f"{label}: transitions[{n}].{key} {t[key]:.6f} vs {e[key]:.6f} (tol {tol_bv(e[key]):.2e})")
        for side in ("start_meq_per_L", "end_meq_per_L"):
            if not close_c(t[side], e[side]):
                errs.append(f"{label}: transitions[{n}].{side} {t[side]} vs {e[side]} (tol {TOL_C})")
    for n, (p, e) in enumerate(zip(rep["plateaus"], exp["plateaus"])):
        for key in ("bv_start", "bv_end"):
            if not close_bv(p[key], e[key]):
                errs.append(f"{label}: plateaus[{n}].{key} {p[key]:.6f} vs {e[key]:.6f} (tol {tol_bv(e[key]):.2e})")
        if not close_c(p["composition_meq_per_L"], e["composition_meq_per_L"]):
            errs.append(f"{label}: plateaus[{n}].composition_meq_per_L {p['composition_meq_per_L']} vs {e['composition_meq_per_L']} (tol {TOL_C})")
    if abs(rep["nitrate_peak"]["meq_per_L"] - exp["nitrate_peak"]["meq_per_L"]) > TOL_C:
        errs.append(f"{label}: nitrate_peak.meq_per_L {rep['nitrate_peak']['meq_per_L']:.6f} vs {exp['nitrate_peak']['meq_per_L']:.6f} (tol {TOL_C})")
    if not close_bv(rep["nitrate_peak"]["bv"], exp["nitrate_peak"]["bv"]):
        errs.append(f"{label}: nitrate_peak.bv {rep['nitrate_peak']['bv']:.6f} vs {exp['nitrate_peak']['bv']:.6f} (tol {tol_bv(exp['nitrate_peak']['bv']):.2e})")
    a, e = rep["nitrate_limit_bv"], exp["nitrate_limit_bv"]
    if (a is None) != (e is None):
        errs.append(f"{label}: nitrate_limit_bv {a} vs {e}")
    elif a is not None and not close_bv(a, e):
        errs.append(f"{label}: nitrate_limit_bv {a:.6f} vs {e:.6f} (tol {tol_bv(e):.2e})")
    for n, (s, e) in enumerate(zip(rep["samples"], exp["samples"])):
        if not close_c(s, e):
            errs.append(f"{label}: samples[{n}] {s} vs {e} (tol {TOL_C})")
    return errs


# ------------------------------------------------------------------ hardened runner
def _drop_privileges():
    runner = pwd.getpwnam("runner")
    os.setgroups([])
    os.setgid(runner.pw_gid)
    os.setuid(runner.pw_uid)


def _clear_runner_processes():
    """Remove candidate-owned processes in this verifier's private PID namespace."""
    uid = pwd.getpwnam("runner").pw_uid
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            if entry.stat().st_uid == uid:
                os.kill(int(entry.name), signal.SIGKILL)
        except (ProcessLookupError, FileNotFoundError, PermissionError):
            pass


def _invoke(label, recipe, program_source):
    """Run one isolated, time-bounded call of a program on a recipe and return its report, without
    exposing tests or truth to the program: fresh working directory, unprivileged uid, process
    group kill on timeout, file-backed output, regular-file and size guards before every copy."""
    _clear_runner_processes()
    run_dir = SANDBOX / "run"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(mode=0o755)
    recipe_path, output_path = run_dir / "recipe.json", run_dir / "report.json"
    recipe_path.write_text(json.dumps(recipe, indent=1) + "\n", encoding="utf-8")
    recipe_path.chmod(0o444)
    runner = pwd.getpwnam("runner")
    os.chown(run_dir, runner.pw_uid, runner.pw_gid)
    program = SANDBOX / "program.py"
    regular_file(program_source)
    assert 0 < program_source.stat().st_size <= 1_000_000, f"{program_source}: program must be non-empty and at most 1 MB"
    shutil.copyfile(program_source, program)
    program.chmod(0o555)
    stdout_path, stderr_path = run_dir / ".stdout", run_dir / ".stderr"
    process, timed_out, returncode = None, False, None
    try:
        with stdout_path.open("w") as out, stderr_path.open("w") as err:
            process = subprocess.Popen(
                ["python", str(program), "--recipe", str(recipe_path), "--output", str(output_path)],
                cwd=run_dir,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin", "PYTHONHASHSEED": "0",
                     "TMPDIR": str(run_dir), "HOME": str(run_dir),
                     "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"},
                stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                start_new_session=True, preexec_fn=_drop_privileges,
            )
            try:
                returncode = process.wait(timeout=CALL_SECONDS)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        _clear_runner_processes()
    tail = lambda p: p.read_text(errors="replace")[-2000:] if p.is_file() else ""
    assert not timed_out, f"{label}: program exceeded the {CALL_SECONDS} s wall-clock limit"
    assert returncode == 0, f"{label}: program exited {returncode}; stdout={tail(stdout_path)!r}; stderr={tail(stderr_path)!r}"
    assert output_path.is_file(), f"{label}: program did not create the output file"
    return read_json(output_path)


def load_case(name):
    return json.loads((CASES / f"{name}.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ tests
def test_saved_base_case():
    """The declared artifacts exist as regular files and the saved base-case report meets the
    output contract and the tolerances against the independent expected values."""
    regular_file(ARTIFACT)
    assert 0 < ARTIFACT.stat().st_size <= 1_000_000, "program must be non-empty and at most 1 MB"
    regular_file(DIAGNOSIS)
    recipe = load_case(BASE_CASE)
    rep = read_json(BASE_REPORT)
    validate_report(rep, recipe, "base_case_report.json")
    errs = compare(rep, load_expected()[BASE_CASE], "base_case_report.json")
    assert not errs, "\n".join(errs)


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_fresh_case(case_name, record_property):
    """A fresh, stateless run of the program on a shipped or held-out recipe meets the output
    contract and every tolerance against the independent expected values."""
    recipe = load_case(case_name)
    rep = _invoke(case_name, recipe, ARTIFACT)
    validate_report(rep, recipe, case_name)
    errs = compare(rep, load_expected()[recipe["recipe_id"]], case_name)
    record_property("shocks", len(rep["shocks"]))
    record_property("transitions", len(rep["transitions"]))
    assert not errs, "\n".join(errs)


def quantity_of(report, q, bv, recipe):
    if q == "shock_count":
        return len(report["shocks"])
    if q == "transition_count":
        return len(report["transitions"])
    if q == "nitrate_peak":
        return report["nitrate_peak"]["meq_per_L"]
    if q == "nitrate_limit_bv":
        return report["nitrate_limit_bv"]
    return report["samples"][recipe["sample_bv"].index(bv)]


def value_ok(q, v, label):
    """Type of a witness value by quantity (spec 6)."""
    if q in ("shock_count", "transition_count"):
        assert integer(v), f"{label}: {q} value must be an integer"
    elif q == "nitrate_peak":
        assert number(v), f"{label}: nitrate_peak value must be a finite number"
    elif q == "nitrate_limit_bv":
        assert v is None or number(v), f"{label}: nitrate_limit_bv value must be null or a finite number"
    else:
        composition(v, f"{label}: sample value")


def matches(q, a, ref):
    if q in ("shock_count", "transition_count"):
        return a == ref
    if q == "nitrate_limit_bv":
        return (a is None and ref is None) or (a is not None and ref is not None and close_bv(a, ref))
    if q == "nitrate_peak":
        return abs(a - ref) <= TOL_C
    return close_c(a, ref)


def differ(q, a, b):
    if q in ("shock_count", "transition_count"):
        return a != b
    if q == "nitrate_limit_bv":
        if a is None or b is None:
            return (a is None) != (b is None)
        return not close_bv(a, b)
    if q == "nitrate_peak":
        return abs(a - b) > TOL_C
    return not close_c(a, b)


def test_diagnosis(record_property):
    """diagnosis.json holds 3 to 8 witnesses of at least three distinct quantities; for each, the
    pristine legacy script reproduces the reported legacy value, the independent reference
    reproduces the reported correct value, and the two differ by more than the tolerance."""
    doc = read_json(DIAGNOSIS)
    assert isinstance(doc, dict) and set(doc) == {"defects"}, "diagnosis.json must have exactly the key 'defects'"
    defects = doc["defects"]
    assert isinstance(defects, list) and 3 <= len(defects) <= 8, "defects must be a list of 3 to 8 entries"
    keys = {"description", "recipe", "quantity", "bv", "legacy_value", "correct_value"}
    quantities = set()
    for n, d in enumerate(defects):
        label = f"defects[{n}]"
        assert isinstance(d, dict) and set(d) == keys, f"{label}: keys must be exactly {sorted(keys)}"
        assert isinstance(d["description"], str) and 1 <= len(d["description"]) <= 500, f"{label}: description must be 1 to 500 characters"
        validate_recipe(d["recipe"], label)
        q = d["quantity"]
        assert q in QUANTITIES, f"{label}: quantity must be one of {sorted(QUANTITIES)}"
        if q == "sample":
            assert number(d["bv"]) and d["bv"] in d["recipe"]["sample_bv"], f"{label}: bv must be one of the recipe's sample_bv values"
        else:
            assert d["bv"] is None, f"{label}: bv must be null for quantity {q}"
        value_ok(q, d["legacy_value"], label)
        value_ok(q, d["correct_value"], label)
        legacy_rep = _invoke(f"{label} legacy", d["recipe"], LEGACY)
        for key in ("shocks", "transitions", "nitrate_peak", "nitrate_limit_bv", "samples"):
            assert key in legacy_rep, f"{label}: legacy report lacks {key}"
        leg = quantity_of(legacy_rep, q, d["bv"], d["recipe"])
        assert matches(q, d["legacy_value"], leg), f"{label}: legacy_value {d['legacy_value']} does not match the legacy script's {leg}"
        ref_rep = _invoke(f"{label} reference", d["recipe"], REFERENCE)
        validate_report(ref_rep, d["recipe"], f"{label} reference")
        ref = quantity_of(ref_rep, q, d["bv"], d["recipe"])
        assert matches(q, d["correct_value"], ref), f"{label}: correct_value {d['correct_value']} does not match the independent value {ref}"
        assert differ(q, leg, ref), f"{label}: the legacy script and the exact solution agree on {q} for this recipe; it is not a witness"
        quantities.add(q)
    record_property("quantities", sorted(quantities))
    assert len(quantities) >= 3, f"witnesses cover only {sorted(quantities)}; at least three distinct quantities are required"
