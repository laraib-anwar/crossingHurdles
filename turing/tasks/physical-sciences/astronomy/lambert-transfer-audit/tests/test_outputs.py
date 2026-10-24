"""Verifier for lambert-transfer-audit.

Grades the saved artifacts and fresh runs of /root/results/lambert.py on the shipped and
held-out systems against expected values computed by an independent implementation
(/tests/expected.json, from /tests/reference/reference.py), and checks the diagnosis witnesses by
executing the pristine legacy script and the independent reference. Every comparison is the one
LAMBERT_SPEC.md states; contract validation runs before any value is compared.
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

ARTIFACT = Path("/root/results/lambert.py")
BASE_REPORT = Path("/root/results/base_case_report.json")
DIAGNOSIS = Path("/root/results/diagnosis.json")
CASES = Path("/tests/cases")
EXPECTED_PATH = Path("/tests/expected.json")
LEGACY = Path("/tests/legacy/porkchop.py")
REFERENCE = Path("/tests/reference/reference.py")
SANDBOX = Path("/sandbox")
CALL_SECONDS = 60
TOL = 1e-9
QUANTITIES = {"position", "solution_count", "theta", "best_dv", "t_min"}
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


def vec(v):
    return isinstance(v, list) and len(v) == 3 and all(number(x) for x in v)


def vclose(a, b):
    import numpy as np
    a, b = np.asarray(a, float), np.asarray(b, float)
    return float(np.linalg.norm(a - b)) <= TOL * float(np.linalg.norm(b))


# ------------------------------------------------------------------ system domain (spec 2, 3)
def validate_system(m, label):
    keys = {"system_id", "mu_km3_s2", "objects", "ephemeris_queries", "transfer_queries"}
    assert isinstance(m, dict) and set(m) == keys, f"{label}: system keys must be exactly {sorted(keys)}"
    assert isinstance(m["system_id"], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", m["system_id"]), f"{label}: bad system_id"
    assert number(m["mu_km3_s2"]) and 1e4 <= m["mu_km3_s2"] <= 2e11, f"{label}: mu outside 1e4-2e11"
    objs = m["objects"]
    assert isinstance(objs, list) and 2 <= len(objs) <= 6, f"{label}: 2 to 6 objects required"
    names = []
    for n, o in enumerate(objs):
        assert isinstance(o, dict) and set(o) == {"name", "t0_days", "a_km", "e", "i_deg", "Omega_deg", "omega_deg", "M0_deg"}, f"{label}: objects[{n}] keys"
        assert isinstance(o["name"], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,32}", o["name"]), f"{label}: objects[{n}].name"
        names.append(o["name"])
        for k in ("t0_days", "a_km", "e", "i_deg", "Omega_deg", "omega_deg", "M0_deg"):
            assert number(o[k]), f"{label}: objects[{n}].{k} must be a number"
        a, e = o["a_km"], o["e"]
        if a > 0:
            assert 1e4 <= a <= 1e9 and 0 <= e <= 0.95, f"{label}: objects[{n}] ellipse outside the domain"
            assert a * (1 - e) >= 1e3, f"{label}: objects[{n}] periapsis below 1e3 km"
        else:
            assert -1e9 <= a <= -1e4 and 1.05 <= e <= 4, f"{label}: objects[{n}] hyperbola outside the domain"
            assert -a * (e - 1) >= 1e3, f"{label}: objects[{n}] periapsis below 1e3 km"
        assert 0 <= o["i_deg"] <= 180, f"{label}: objects[{n}].i_deg outside 0-180"
        for k in ("Omega_deg", "omega_deg", "M0_deg"):
            assert 0 <= o[k] < 360, f"{label}: objects[{n}].{k} outside [0, 360)"
        assert -2e4 <= o["t0_days"] <= 2e4, f"{label}: objects[{n}].t0_days outside -2e4..2e4"
    assert len(set(names)) == len(names), f"{label}: object names must be distinct"
    eq = m["ephemeris_queries"]
    assert isinstance(eq, list) and 2 <= len(eq) <= 8, f"{label}: 2 to 8 ephemeris queries"
    for n, q in enumerate(eq):
        assert isinstance(q, dict) and set(q) == {"object", "t_days"}, f"{label}: ephemeris_queries[{n}] keys"
        assert q["object"] in names and number(q["t_days"]) and -2e4 <= q["t_days"] <= 2e4, f"{label}: ephemeris_queries[{n}] values"
    tq = m["transfer_queries"]
    assert isinstance(tq, list) and 2 <= len(tq) <= 6, f"{label}: 2 to 6 transfer queries"
    for n, q in enumerate(tq):
        assert isinstance(q, dict) and set(q) == {"from", "t1_days", "to", "t2_days", "n_max"}, f"{label}: transfer_queries[{n}] keys"
        assert q["from"] in names and q["to"] in names and q["from"] != q["to"], f"{label}: transfer_queries[{n}] must name two different objects"
        assert number(q["t1_days"]) and number(q["t2_days"]) and -2e4 <= q["t1_days"] <= 2e4 and -2e4 <= q["t2_days"] <= 2e4, f"{label}: transfer_queries[{n}] times"
        assert 0.1 <= q["t2_days"] - q["t1_days"] <= 6000, f"{label}: transfer_queries[{n}] time of flight outside 0.1-6000 days"
        assert integer(q["n_max"]) and 0 <= q["n_max"] <= 4, f"{label}: transfer_queries[{n}].n_max outside 0-4"


# ------------------------------------------------------------------ report contract (spec 4)
def validate_report(rep, system, label):
    keys = {"system_id", "ephemeris", "transfers"}
    assert isinstance(rep, dict) and set(rep) == keys, f"{label}: report keys must be exactly {sorted(keys)}"
    assert rep["system_id"] == system["system_id"], f"{label}: system_id must be {system['system_id']!r}"
    eph = rep["ephemeris"]
    assert isinstance(eph, list) and len(eph) == len(system["ephemeris_queries"]), f"{label}: ephemeris must have one entry per query"
    for n, (e, q) in enumerate(zip(eph, system["ephemeris_queries"])):
        assert isinstance(e, dict) and set(e) == {"object", "t_days", "r_km", "v_km_s"}, f"{label}: ephemeris[{n}] keys"
        assert e["object"] == q["object"] and e["t_days"] == q["t_days"], f"{label}: ephemeris[{n}] query must be as given"
        assert vec(e["r_km"]) and vec(e["v_km_s"]), f"{label}: ephemeris[{n}] vectors"
    tr = rep["transfers"]
    assert isinstance(tr, list) and len(tr) == len(system["transfer_queries"]), f"{label}: transfers must have one entry per query"
    for n, (t, q) in enumerate(zip(tr, system["transfer_queries"])):
        where = f"{label}: transfers[{n}]"
        assert isinstance(t, dict) and set(t) == {"from", "t1_days", "to", "t2_days", "n_max", "theta_deg", "t_min_days", "solutions", "best"}, f"{where} keys"
        for k in ("from", "t1_days", "to", "t2_days", "n_max"):
            assert t[k] == q[k], f"{where}.{k} must be as given"
        assert number(t["theta_deg"]) and 0 < t["theta_deg"] < 360, f"{where}.theta_deg must lie in (0, 360)"
        tm = t["t_min_days"]
        assert isinstance(tm, list) and len(tm) == q["n_max"] and all(number(x) and x > 0 for x in tm), f"{where}.t_min_days must have n_max positive numbers"
        assert all(a < b for a, b in zip(tm, tm[1:])), f"{where}.t_min_days must increase"
        sols = t["solutions"]
        assert isinstance(sols, list) and sols, f"{where}.solutions must be a non-empty list"
        prev = None
        for k, s in enumerate(sols):
            assert isinstance(s, dict) and set(s) == {"N", "branch", "v1_km_s", "v2_km_s", "a_km", "e", "dv_km_s"}, f"{where}.solutions[{k}] keys"
            assert integer(s["N"]) and 0 <= s["N"] <= q["n_max"], f"{where}.solutions[{k}].N"
            assert s["branch"] in ("single", "low", "high"), f"{where}.solutions[{k}].branch"
            assert (s["N"] == 0) == (s["branch"] == "single"), f"{where}.solutions[{k}]: branch single exactly for N = 0"
            assert vec(s["v1_km_s"]) and vec(s["v2_km_s"]), f"{where}.solutions[{k}] vectors"
            assert number(s["a_km"]) and s["a_km"] != 0 and number(s["e"]) and s["e"] >= 0 and number(s["dv_km_s"]) and s["dv_km_s"] >= 0, f"{where}.solutions[{k}] scalars"
            key = (s["N"], {"single": 0, "low": 0, "high": 1}[s["branch"]])
            assert prev is None or key > prev, f"{where}.solutions must be ordered by N then low before high"
            prev = key
        assert integer(t["best"]) and 0 <= t["best"] < len(sols), f"{where}.best must index solutions"


def compare(rep, exp, label):
    """Failures of the comparison of spec section 5; empty list means pass."""
    errs = []
    for n, (a, e) in enumerate(zip(rep["transfers"], exp["transfers"])):
        if [(s["N"], s["branch"]) for s in a["solutions"]] != [(s["N"], s["branch"]) for s in e["solutions"]]:
            errs.append(f"{label}: transfers[{n}] solutions {[(s['N'], s['branch']) for s in a['solutions']]} vs {[(s['N'], s['branch']) for s in e['solutions']]}")
    if errs:
        return errs
    for n, (a, e) in enumerate(zip(rep["ephemeris"], exp["ephemeris"])):
        for k in ("r_km", "v_km_s"):
            if not vclose(a[k], e[k]):
                errs.append(f"{label}: ephemeris[{n}].{k} differs beyond {TOL} relative")
    for n, (a, e) in enumerate(zip(rep["transfers"], exp["transfers"])):
        where = f"{label}: transfers[{n}]"
        if not close_abs(a["theta_deg"], e["theta_deg"], TOL):
            errs.append(f"{where}.theta_deg {a['theta_deg']:.12g} vs {e['theta_deg']:.12g} (abs tol {TOL})")
        for k, (x, y) in enumerate(zip(a["t_min_days"], e["t_min_days"])):
            if not close_rel(x, y, TOL):
                errs.append(f"{where}.t_min_days[{k}] {x:.12g} vs {y:.12g} (rel tol {TOL})")
        if a["best"] != e["best"]:
            errs.append(f"{where}.best {a['best']} vs {e['best']}")
        for k, (s, q) in enumerate(zip(a["solutions"], e["solutions"])):
            for f in ("v1_km_s", "v2_km_s"):
                if not vclose(s[f], q[f]):
                    errs.append(f"{where}.solutions[{k}].{f} differs beyond {TOL} relative")
            for f in ("a_km", "e", "dv_km_s"):
                if not close_rel(s[f], q[f], TOL):
                    errs.append(f"{where}.solutions[{k}].{f} {s[f]:.12g} vs {q[f]:.12g} (rel tol {TOL})")
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
    record_property("solutions", sum(len(t["solutions"]) for t in rep["transfers"]))
    assert not errs, "\n".join(errs)


def quantity_of(rep, q, k):
    import numpy as np
    if q == "position":
        return float(np.linalg.norm(rep["ephemeris"][k]["r_km"]))
    t = rep["transfers"][k]
    if q == "solution_count":
        return len(t["solutions"])
    if q == "theta":
        return t["theta_deg"]
    if q == "best_dv":
        return t["solutions"][t["best"]]["dv_km_s"]
    return t["t_min_days"][0] if t["t_min_days"] else None


def test_diagnosis(record_property):
    """diagnosis.json holds 3 to 8 witnesses of at least three distinct quantities; for each, the
    pristine legacy script reproduces the reported legacy value, the independent reference
    reproduces the reported correct value, and the two differ."""
    doc = read_json(DIAGNOSIS)
    assert isinstance(doc, dict) and set(doc) == {"defects"}, "diagnosis.json must have exactly the key 'defects'"
    defects = doc["defects"]
    assert isinstance(defects, list) and 3 <= len(defects) <= 8, "defects must be a list of 3 to 8 entries"
    keys = {"description", "system", "quantity", "index", "legacy_value", "correct_value"}
    quantities = set()
    for n, d in enumerate(defects):
        label = f"defects[{n}]"
        assert isinstance(d, dict) and set(d) == keys, f"{label}: keys must be exactly {sorted(keys)}"
        assert isinstance(d["description"], str) and 1 <= len(d["description"]) <= 500, f"{label}: description must be 1 to 500 characters"
        validate_system(d["system"], label)
        q, k = d["quantity"], d["index"]
        assert q in QUANTITIES, f"{label}: quantity must be one of {sorted(QUANTITIES)}"
        n_list = len(d["system"]["ephemeris_queries"]) if q == "position" else len(d["system"]["transfer_queries"])
        assert integer(k) and 0 <= k < n_list, f"{label}: index must address the corresponding query list"
        if q == "t_min":
            assert d["system"]["transfer_queries"][k]["n_max"] >= 1, f"{label}: t_min needs n_max >= 1"
        if q == "solution_count":
            assert integer(d["legacy_value"]) and integer(d["correct_value"]), f"{label}: counts must be integers"
        else:
            assert number(d["legacy_value"]) and number(d["correct_value"]), f"{label}: values must be finite numbers"
        leg_rep = _invoke(f"{label} legacy", d["system"], LEGACY)
        assert isinstance(leg_rep, dict) and "ephemeris" in leg_rep and "transfers" in leg_rep, f"{label}: legacy report unreadable"
        leg = quantity_of(leg_rep, q, k)
        ref_rep = _invoke(f"{label} reference", d["system"], REFERENCE)
        validate_report(ref_rep, d["system"], f"{label} reference")
        ref = quantity_of(ref_rep, q, k)
        assert leg is not None and ref is not None, f"{label}: the quantity is undefined in one of the reports"
        if q == "solution_count":
            assert d["legacy_value"] == leg, f"{label}: legacy_value {d['legacy_value']!r} does not match the legacy script's {leg!r}"
            assert d["correct_value"] == ref, f"{label}: correct_value {d['correct_value']!r} does not match the independent value {ref!r}"
            assert leg != ref, f"{label}: the legacy script and the exact solution agree on {q}; it is not a witness"
        else:
            assert close_rel(d["legacy_value"], leg, TOL), f"{label}: legacy_value {d['legacy_value']} does not match the legacy script's {leg}"
            assert close_rel(d["correct_value"], ref, TOL), f"{label}: correct_value {d['correct_value']} does not match the independent value {ref}"
            assert not close_rel(leg, ref, 1e-6), f"{label}: the legacy script and the exact solution agree; it is not a witness"
        quantities.add(q)
    record_property("quantities", sorted(quantities))
    assert len(quantities) >= 3, f"witnesses cover only {sorted(quantities)}; at least three distinct quantities are required"
