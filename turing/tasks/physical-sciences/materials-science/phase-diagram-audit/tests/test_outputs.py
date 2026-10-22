"""Verifier for phase-diagram-audit.

Grades the saved artifacts and fresh runs of /root/results/phasediagram.py on the shipped and
held-out systems against expected values computed by an independent implementation
(/tests/expected.json, from /tests/reference/reference.py), and checks the diagnosis witnesses by
executing the pristine legacy script and the independent reference. Every comparison is the one
PHASE_SPEC.md states; contract validation runs before any value is compared.
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

ARTIFACT = Path("/root/results/phasediagram.py")
BASE_REPORT = Path("/root/results/base_case_report.json")
DIAGNOSIS = Path("/root/results/diagnosis.json")
CASES = Path("/tests/cases")
EXPECTED_PATH = Path("/tests/expected.json")
LEGACY = Path("/tests/legacy/tangentdiag.py")
REFERENCE = Path("/tests/reference/reference.py")
SANDBOX = Path("/sandbox")
CALL_SECONDS = 120
TOL_X, TOL_T, TOL_FRACTION = 1e-8, 1e-7, 1e-6
SOLUTION_NAMES = {"liquid", "alpha", "beta", "gamma", "delta"}
CLASSES = {"eutectic", "peritectic"}
NAMES = {"eutectic", "monotectic", "eutectoid", "metatectic", "peritectic", "syntectic", "peritectoid", "inverse_monotectic"}
SIDES = {"below", "above"}
QUANTITIES = {"tie_line_count", "two_phase_fraction", "invariant_count", "peritectic_count", "critical_count"}
CASE_NAMES = sorted(p.stem for p in CASES.glob("*.json"))
BASE_CASE = "model_01"


# ------------------------------------------------------------------ helpers
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


def close_abs(a, ref, tol):
    return abs(a - ref) <= tol


def close_rel(a, ref, tol):
    return abs(a - ref) <= tol * abs(ref)


def load_expected():
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ system domain (spec 2, 3)
def validate_system(m, label):
    keys = {"system_id", "solution_phases", "compounds", "window_K", "isotherms_K"}
    assert isinstance(m, dict) and set(m) == keys, f"{label}: system keys must be exactly {sorted(keys)}"
    assert isinstance(m["system_id"], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", m["system_id"]), f"{label}: bad system_id"
    sols = m["solution_phases"]
    assert isinstance(sols, list) and 2 <= len(sols) <= 4, f"{label}: 2 to 4 solution phases required"
    names = []
    for n, s in enumerate(sols):
        assert isinstance(s, dict) and set(s) == {"name", "end_members", "redlich_kister"}, f"{label}: solution_phases[{n}] keys"
        assert s["name"] in SOLUTION_NAMES, f"{label}: solution_phases[{n}].name must be one of {sorted(SOLUTION_NAMES)}"
        names.append(s["name"])
        em = s["end_members"]
        assert isinstance(em, dict) and set(em) == {"A", "B"}, f"{label}: solution_phases[{n}].end_members keys"
        for e in ("A", "B"):
            assert isinstance(em[e], dict) and set(em[e]) == {"h", "s"}, f"{label}: solution_phases[{n}].end_members.{e} keys"
            assert number(em[e]["h"]) and -60000 <= em[e]["h"] <= 60000, f"{label}: solution_phases[{n}] h outside -60000..60000"
            assert number(em[e]["s"]) and -60 <= em[e]["s"] <= 60, f"{label}: solution_phases[{n}] s outside -60..60"
        rk = s["redlich_kister"]
        assert isinstance(rk, list) and len(rk) == 3, f"{label}: solution_phases[{n}].redlich_kister must have 3 entries"
        for c in rk:
            assert isinstance(c, dict) and set(c) == {"a", "b"}, f"{label}: solution_phases[{n}].redlich_kister keys"
            assert number(c["a"]) and -60000 <= c["a"] <= 60000, f"{label}: a_k outside -60000..60000"
            assert number(c["b"]) and -30 <= c["b"] <= 30, f"{label}: b_k outside -30..30"
    assert len(set(names)) == len(names) and names.count("liquid") == 1, f"{label}: distinct names with exactly one liquid"
    comps = m["compounds"]
    assert isinstance(comps, list) and len(comps) <= 3, f"{label}: at most 3 compounds"
    xs = []
    for n, c in enumerate(comps):
        assert isinstance(c, dict) and set(c) == {"name", "x_b", "h", "s"}, f"{label}: compounds[{n}] keys"
        assert isinstance(c["name"], str) and re.fullmatch(r"[A-Za-z0-9]{1,12}", c["name"]) and c["name"] not in names, f"{label}: compounds[{n}].name"
        names.append(c["name"])
        assert number(c["x_b"]) and 0.1 <= c["x_b"] <= 0.9, f"{label}: compounds[{n}].x_b outside 0.1..0.9"
        assert number(c["h"]) and -60000 <= c["h"] <= 60000 and number(c["s"]) and -60 <= c["s"] <= 60, f"{label}: compounds[{n}] h/s"
        xs.append(c["x_b"])
    assert len(set(names)) == len(names), f"{label}: phase names must be distinct"
    xs.sort()
    assert all(b - a >= 0.02 for a, b in zip(xs, xs[1:])), f"{label}: compounds must be at least 0.02 apart"
    w = m["window_K"]
    assert isinstance(w, list) and len(w) == 2 and all(number(v) for v in w), f"{label}: window_K"
    assert 250 <= w[0] < w[1] <= 2500 and 100 <= w[1] - w[0] <= 1200, f"{label}: window outside the domain"
    iso = m["isotherms_K"]
    assert isinstance(iso, list) and 2 <= len(iso) <= 6 and all(number(v) for v in iso), f"{label}: 2 to 6 isotherms required"
    assert all(a < b for a, b in zip(iso, iso[1:])), f"{label}: isotherms_K must increase strictly"
    assert w[0] < iso[0] and iso[-1] < w[1], f"{label}: isotherms must lie strictly inside the window"


# ------------------------------------------------------------------ report contract (spec 4)
def validate_report(rep, system, label):
    names = {s["name"] for s in system["solution_phases"]} | {c["name"] for c in system["compounds"]}
    comp_x = {c["name"]: c["x_b"] for c in system["compounds"]}
    keys = {"system_id", "isotherms", "invariants", "congruent_points", "critical_points"}
    assert isinstance(rep, dict) and set(rep) == keys, f"{label}: report keys must be exactly {sorted(keys)}"
    assert rep["system_id"] == system["system_id"], f"{label}: system_id must be {system['system_id']!r}"
    iso = rep["isotherms"]
    assert isinstance(iso, list) and len(iso) == len(system["isotherms_K"]), f"{label}: isotherms must have one entry per isotherm"
    for n, (it, T) in enumerate(zip(iso, system["isotherms_K"])):
        where = f"{label}: isotherms[{n}]"
        assert isinstance(it, dict) and set(it) == {"temperature_K", "single_phase_regions", "tie_lines"}, f"{where} keys"
        assert it["temperature_K"] == T, f"{where}.temperature_K must be {T!r} exactly"
        regs, ties = it["single_phase_regions"], it["tie_lines"]
        assert isinstance(regs, list) and regs, f"{where}.single_phase_regions must be a non-empty list"
        for k, g in enumerate(regs):
            assert isinstance(g, dict) and set(g) == {"phase", "x_lo", "x_hi"}, f"{where}.single_phase_regions[{k}] keys"
            assert g["phase"] in names and g["phase"] not in comp_x, f"{where}.single_phase_regions[{k}].phase must be a solution phase"
            assert number(g["x_lo"]) and number(g["x_hi"]) and g["x_lo"] < g["x_hi"], f"{where}.single_phase_regions[{k}] bounds"
        assert regs[0]["x_lo"] == 0, f"{where}: the first region must start at 0"
        assert regs[-1]["x_hi"] == 1, f"{where}: the last region must end at 1"
        assert all(a["x_hi"] <= b["x_lo"] for a, b in zip(regs, regs[1:])), f"{where}: regions must be in increasing x"
        assert isinstance(ties, list), f"{where}.tie_lines must be a list"
        for k, t in enumerate(ties):
            assert isinstance(t, dict) and set(t) == {"left_phase", "x_left", "right_phase", "x_right"}, f"{where}.tie_lines[{k}] keys"
            assert t["left_phase"] in names and t["right_phase"] in names, f"{where}.tie_lines[{k}] phase names"
            assert number(t["x_left"]) and number(t["x_right"]) and t["x_left"] < t["x_right"], f"{where}.tie_lines[{k}] bounds"
            for side in ("left", "right"):
                ph = t[f"{side}_phase"]
                if ph in comp_x:
                    assert t[f"x_{side}"] == comp_x[ph], f"{where}.tie_lines[{k}]: compound {ph} must be at its x_b exactly"
        assert all(a["x_right"] <= b["x_left"] for a, b in zip(ties, ties[1:])), f"{where}: tie-lines must be in increasing x"
    inv = rep["invariants"]
    assert isinstance(inv, list), f"{label}: invariants must be a list"
    for n, e in enumerate(inv):
        where = f"{label}: invariants[{n}]"
        assert isinstance(e, dict) and set(e) == {"temperature_K", "class", "name", "phases"}, f"{where} keys"
        assert number(e["temperature_K"]), f"{where}.temperature_K"
        assert e["class"] in CLASSES and e["name"] in NAMES, f"{where} class/name"
        ph = e["phases"]
        assert isinstance(ph, list) and len(ph) == 3, f"{where}.phases must have exactly three entries"
        for k, p in enumerate(ph):
            assert isinstance(p, dict) and set(p) == {"phase", "x"}, f"{where}.phases[{k}] keys"
            assert p["phase"] in names and number(p["x"]), f"{where}.phases[{k}] values"
            if p["phase"] in comp_x:
                assert p["x"] == comp_x[p["phase"]], f"{where}.phases[{k}]: compound at its x_b exactly"
        assert ph[0]["x"] < ph[1]["x"] < ph[2]["x"], f"{where}.phases must be in increasing x"
    con = rep["congruent_points"]
    assert isinstance(con, list), f"{label}: congruent_points must be a list"
    for n, e in enumerate(con):
        where = f"{label}: congruent_points[{n}]"
        assert isinstance(e, dict) and set(e) == {"temperature_K", "x", "phase_above", "phase_below", "two_phase_side"}, f"{where} keys"
        assert number(e["temperature_K"]) and number(e["x"]), f"{where} values"
        assert e["phase_above"] in names and e["phase_below"] in names and e["phase_above"] != e["phase_below"], f"{where} phases"
        assert e["two_phase_side"] in SIDES, f"{where}.two_phase_side"
    cri = rep["critical_points"]
    assert isinstance(cri, list), f"{label}: critical_points must be a list"
    for n, e in enumerate(cri):
        where = f"{label}: critical_points[{n}]"
        assert isinstance(e, dict) and set(e) == {"temperature_K", "x", "phase", "gap_side"}, f"{where} keys"
        assert number(e["temperature_K"]) and number(e["x"]), f"{where} values"
        assert e["phase"] in names and e["phase"] not in comp_x and e["gap_side"] in SIDES, f"{where} phase/gap_side"
    for key in ("invariants", "congruent_points", "critical_points"):
        Ts = [e["temperature_K"] for e in rep[key]]
        assert all(a < b for a, b in zip(Ts, Ts[1:])), f"{label}: {key} must be in increasing temperature_K"


def compare(rep, exp, label):
    """Failures of the comparison of spec section 5; empty list means pass."""
    errs = []
    for n, (a, e) in enumerate(zip(rep["isotherms"], exp["isotherms"])):
        if len(a["single_phase_regions"]) != len(e["single_phase_regions"]):
            errs.append(f"{label}: isotherms[{n}] has {len(a['single_phase_regions'])} regions, {len(e['single_phase_regions'])} expected")
        if len(a["tie_lines"]) != len(e["tie_lines"]):
            errs.append(f"{label}: isotherms[{n}] has {len(a['tie_lines'])} tie-lines, {len(e['tie_lines'])} expected")
    for key in ("invariants", "congruent_points", "critical_points"):
        if len(rep[key]) != len(exp[key]):
            errs.append(f"{label}: {len(rep[key])} {key}, {len(exp[key])} expected")
    if errs:
        return errs
    for n, (a, e) in enumerate(zip(rep["isotherms"], exp["isotherms"])):
        for k, (g, q) in enumerate(zip(a["single_phase_regions"], e["single_phase_regions"])):
            where = f"{label}: isotherms[{n}].single_phase_regions[{k}]"
            if g["phase"] != q["phase"]:
                errs.append(f"{where}.phase {g['phase']} vs {q['phase']}")
            for f in ("x_lo", "x_hi"):
                if not close_abs(g[f], q[f], TOL_X):
                    errs.append(f"{where}.{f} {g[f]:.12g} vs {q[f]:.12g} (abs tol {TOL_X})")
        for k, (t, q) in enumerate(zip(a["tie_lines"], e["tie_lines"])):
            where = f"{label}: isotherms[{n}].tie_lines[{k}]"
            if (t["left_phase"], t["right_phase"]) != (q["left_phase"], q["right_phase"]):
                errs.append(f"{where} phases {t['left_phase']}-{t['right_phase']} vs {q['left_phase']}-{q['right_phase']}")
            for f in ("x_left", "x_right"):
                if not close_abs(t[f], q[f], TOL_X):
                    errs.append(f"{where}.{f} {t[f]:.12g} vs {q[f]:.12g} (abs tol {TOL_X})")
    for n, (a, e) in enumerate(zip(rep["invariants"], exp["invariants"])):
        where = f"{label}: invariants[{n}]"
        if not close_rel(a["temperature_K"], e["temperature_K"], TOL_T):
            errs.append(f"{where}.temperature_K {a['temperature_K']:.12g} vs {e['temperature_K']:.12g} (rel tol {TOL_T})")
        if a["class"] != e["class"] or a["name"] != e["name"]:
            errs.append(f"{where} {a['class']}/{a['name']} vs {e['class']}/{e['name']}")
        for k, (p, q) in enumerate(zip(a["phases"], e["phases"])):
            if p["phase"] != q["phase"]:
                errs.append(f"{where}.phases[{k}] {p['phase']} vs {q['phase']}")
            if not close_abs(p["x"], q["x"], TOL_X):
                errs.append(f"{where}.phases[{k}].x {p['x']:.12g} vs {q['x']:.12g} (abs tol {TOL_X})")
    for n, (a, e) in enumerate(zip(rep["congruent_points"], exp["congruent_points"])):
        where = f"{label}: congruent_points[{n}]"
        if not close_rel(a["temperature_K"], e["temperature_K"], TOL_T):
            errs.append(f"{where}.temperature_K {a['temperature_K']:.12g} vs {e['temperature_K']:.12g} (rel tol {TOL_T})")
        if not close_abs(a["x"], e["x"], TOL_X):
            errs.append(f"{where}.x {a['x']:.12g} vs {e['x']:.12g} (abs tol {TOL_X})")
        for f in ("phase_above", "phase_below", "two_phase_side"):
            if a[f] != e[f]:
                errs.append(f"{where}.{f} {a[f]} vs {e[f]}")
    for n, (a, e) in enumerate(zip(rep["critical_points"], exp["critical_points"])):
        where = f"{label}: critical_points[{n}]"
        if not close_rel(a["temperature_K"], e["temperature_K"], TOL_T):
            errs.append(f"{where}.temperature_K {a['temperature_K']:.12g} vs {e['temperature_K']:.12g} (rel tol {TOL_T})")
        if not close_abs(a["x"], e["x"], TOL_X):
            errs.append(f"{where}.x {a['x']:.12g} vs {e['x']:.12g} (abs tol {TOL_X})")
        for f in ("phase", "gap_side"):
            if a[f] != e[f]:
                errs.append(f"{where}.{f} {a[f]} vs {e[f]}")
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


def _invoke(label, system, program_source):
    """Run one isolated, time-bounded call of a program on a system and return its report: fresh
    working directory, unprivileged uid, process-group kill on timeout, file-backed output,
    regular-file and size guards before every copy or read."""
    _clear_runner_processes()
    run_dir = SANDBOX / "run"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(mode=0o755)
    system_path, output_path = run_dir / "system.json", run_dir / "report.json"
    system_path.write_text(json.dumps(system, indent=1) + "\n", encoding="utf-8")
    system_path.chmod(0o444)
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
                ["python", str(program), "--system", str(system_path), "--output", str(output_path)],
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
    system = load_case(BASE_CASE)
    rep = read_json(BASE_REPORT)
    validate_report(rep, system, "base_case_report.json")
    errs = compare(rep, load_expected()[BASE_CASE], "base_case_report.json")
    assert not errs, "\n".join(errs)


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_fresh_case(case_name, record_property):
    """A fresh, stateless run of the program on a shipped or held-out system meets the output
    contract and every tolerance against the independent expected values."""
    system = load_case(case_name)
    rep = _invoke(case_name, system, ARTIFACT)
    validate_report(rep, system, case_name)
    errs = compare(rep, load_expected()[system["system_id"]], case_name)
    record_property("invariants", len(rep["invariants"]))
    record_property("congruent_points", len(rep["congruent_points"]))
    record_property("critical_points", len(rep["critical_points"]))
    assert not errs, "\n".join(errs)


def quantity_of(rep, q, T):
    if q == "invariant_count":
        return len(rep["invariants"])
    if q == "peritectic_count":
        return sum(1 for e in rep["invariants"] if e["class"] == "peritectic")
    if q == "critical_count":
        return len(rep["critical_points"])
    iso = next(it for it in rep["isotherms"] if it["temperature_K"] == T)
    if q == "tie_line_count":
        return len(iso["tie_lines"])
    return sum(t["x_right"] - t["x_left"] for t in iso["tie_lines"])


def test_diagnosis(record_property):
    """diagnosis.json holds 3 to 8 witnesses of at least three distinct quantities; for each, the
    pristine legacy script reproduces the reported legacy value, the independent reference
    reproduces the reported correct value, and the two differ."""
    doc = read_json(DIAGNOSIS)
    assert isinstance(doc, dict) and set(doc) == {"defects"}, "diagnosis.json must have exactly the key 'defects'"
    defects = doc["defects"]
    assert isinstance(defects, list) and 3 <= len(defects) <= 8, "defects must be a list of 3 to 8 entries"
    keys = {"description", "system", "quantity", "temperature_K", "legacy_value", "correct_value"}
    quantities = set()
    for n, d in enumerate(defects):
        label = f"defects[{n}]"
        assert isinstance(d, dict) and set(d) == keys, f"{label}: keys must be exactly {sorted(keys)}"
        assert isinstance(d["description"], str) and 1 <= len(d["description"]) <= 500, f"{label}: description must be 1 to 500 characters"
        validate_system(d["system"], label)
        q, T = d["quantity"], d["temperature_K"]
        assert q in QUANTITIES, f"{label}: quantity must be one of {sorted(QUANTITIES)}"
        if q in ("tie_line_count", "two_phase_fraction"):
            assert number(T) and T in d["system"]["isotherms_K"], f"{label}: temperature_K must be one of the system's isotherms"
        else:
            assert T is None, f"{label}: temperature_K must be null for {q}"
        if q == "two_phase_fraction":
            assert number(d["legacy_value"]) and number(d["correct_value"]), f"{label}: values must be finite numbers"
        else:
            assert integer(d["legacy_value"]) and integer(d["correct_value"]), f"{label}: values must be integers"
        leg_rep = _invoke(f"{label} legacy", d["system"], LEGACY)
        assert isinstance(leg_rep, dict) and "isotherms" in leg_rep and "invariants" in leg_rep and "critical_points" in leg_rep, f"{label}: legacy report unreadable"
        leg = quantity_of(leg_rep, q, T)
        ref_rep = _invoke(f"{label} reference", d["system"], REFERENCE)
        validate_report(ref_rep, d["system"], f"{label} reference")
        ref = quantity_of(ref_rep, q, T)
        if q == "two_phase_fraction":
            assert close_abs(d["legacy_value"], leg, TOL_FRACTION), f"{label}: legacy_value {d['legacy_value']} does not match the legacy script's {leg}"
            assert close_abs(d["correct_value"], ref, TOL_FRACTION), f"{label}: correct_value {d['correct_value']} does not match the independent value {ref}"
            assert not close_abs(leg, ref, TOL_FRACTION), f"{label}: the legacy script and the exact solution agree; it is not a witness"
        else:
            assert d["legacy_value"] == leg, f"{label}: legacy_value {d['legacy_value']!r} does not match the legacy script's {leg!r}"
            assert d["correct_value"] == ref, f"{label}: correct_value {d['correct_value']!r} does not match the independent value {ref!r}"
            assert leg != ref, f"{label}: the legacy script and the exact solution agree on {q}; it is not a witness"
        quantities.add(q)
    record_property("quantities", sorted(quantities))
    assert len(quantities) >= 3, f"witnesses cover only {sorted(quantities)}; at least three distinct quantities are required"
