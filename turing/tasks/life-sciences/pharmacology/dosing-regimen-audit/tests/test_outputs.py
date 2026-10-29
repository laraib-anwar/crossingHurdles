"""Verifier for dosing-regimen-audit.

Grades the saved artifacts and fresh runs of /root/results/regimen.py on the shipped and
held-out regimens against expected values computed by an independent implementation
(/tests/expected.json, from /tests/reference/reference.py), and checks the diagnosis witnesses by
executing the pristine legacy script and the independent reference. Every comparison is the one
REGIMEN_SPEC.md states; contract validation runs before any value is compared.
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

ARTIFACT = Path("/root/results/regimen.py")
BASE_REPORT = Path("/root/results/base_case_report.json")
DIAGNOSIS = Path("/root/results/diagnosis.json")
CASES = Path("/tests/cases")
EXPECTED_PATH = Path("/tests/expected.json")
LEGACY = Path("/tests/legacy/regimencalc.py")
REFERENCE = Path("/tests/reference/reference.py")
SANDBOX = Path("/sandbox")
CALL_SECONDS = 120
TOL_C = 1e-8        # concentrations, relative to the reference cmax of the report
TOL_AUC = 1e-8      # relative
TOL_T = 1e-6        # hours, absolute
ROUTES = ("iv_bolus", "iv_infusion", "oral")
QUANTITIES = {"concentration", "auc", "cmax", "t_cmax", "ss_cmax", "ss_cmin", "ss_trough", "time_in_window", "n_cycles_to_steady"}
CONC_Q = {"concentration", "cmax", "ss_cmax", "ss_cmin", "ss_trough"}
TIME_Q = {"t_cmax", "time_in_window"}
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


def load_expected():
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ regimen domain (spec 2, 3)
def validate_dose(dose, label, maint, form_ids):
    tkey = "offset" if maint else "time"
    assert isinstance(dose, dict) and set(dose) == {tkey, "route", "amount", "duration", "formulation"}, f"{label}: dose keys"
    assert number(dose[tkey]) and dose[tkey] >= 0, f"{label}: {tkey} must be a non-negative number"
    assert dose["route"] in ROUTES, f"{label}: route must be one of {ROUTES}"
    assert number(dose["amount"]) and 1 <= dose["amount"] <= 5000, f"{label}: amount outside 1..5000 mg"
    if dose["route"] == "iv_infusion":
        assert number(dose["duration"]) and 0.1 <= dose["duration"] <= 24, f"{label}: infusion duration outside 0.1..24 h"
    else:
        assert dose["duration"] is None, f"{label}: duration must be null unless the route is iv_infusion"
    if dose["route"] == "oral":
        assert dose["formulation"] in form_ids, f"{label}: formulation must be a formulation id"
    else:
        assert dose["formulation"] is None, f"{label}: formulation must be null unless the route is oral"


def validate_regimen(r, label):
    keys = {"regimen_id", "model", "formulations", "loading_doses", "maintenance", "horizon", "query_times", "window"}
    assert isinstance(r, dict) and set(r) == keys, f"{label}: regimen keys must be exactly {sorted(keys)}"
    assert isinstance(r["regimen_id"], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", r["regimen_id"]), f"{label}: bad regimen_id"
    m = r["model"]
    assert isinstance(m, dict) and set(m) == {"V1", "CL", "Vmax", "Km", "peripheral"}, f"{label}: model keys"
    assert number(m["V1"]) and 3 <= m["V1"] <= 100, f"{label}: V1 outside 3..100 L"
    assert number(m["CL"]) and 0.1 <= m["CL"] <= 50, f"{label}: CL outside 0.1..50 L/h"
    assert number(m["Vmax"]) and (m["Vmax"] == 0 or 0.5 <= m["Vmax"] <= 500), f"{label}: Vmax must be 0 or within 0.5..500 mg/h"
    assert number(m["Km"]) and 0.05 <= m["Km"] <= 50, f"{label}: Km outside 0.05..50 mg/L"
    per = m["peripheral"]
    assert isinstance(per, list) and len(per) <= 2, f"{label}: 0 to 2 peripheral compartments"
    for n, p in enumerate(per):
        assert isinstance(p, dict) and set(p) == {"Q", "V"}, f"{label}: peripheral[{n}] keys"
        assert number(p["Q"]) and 0.1 <= p["Q"] <= 100 and number(p["V"]) and 1 <= p["V"] <= 500, f"{label}: peripheral[{n}] values"
    forms = r["formulations"]
    assert isinstance(forms, list) and 1 <= len(forms) <= 2, f"{label}: 1 to 2 formulations"
    for n, f in enumerate(forms):
        assert isinstance(f, dict) and set(f) == {"id", "F", "ka", "tlag", "n_transit", "ktr"}, f"{label}: formulations[{n}] keys"
        assert integer(f["id"]) and f["id"] == n + 1, f"{label}: formulations[{n}].id must be {n + 1}"
        assert number(f["F"]) and 0.1 <= f["F"] <= 1, f"{label}: formulations[{n}].F outside 0.1..1"
        assert number(f["ka"]) and 0.1 <= f["ka"] <= 5, f"{label}: formulations[{n}].ka outside 0.1..5"
        assert number(f["tlag"]) and 0 <= f["tlag"] <= 2, f"{label}: formulations[{n}].tlag outside 0..2"
        assert integer(f["n_transit"]) and 0 <= f["n_transit"] <= 5, f"{label}: formulations[{n}].n_transit outside 0..5"
        assert number(f["ktr"]) and 0.5 <= f["ktr"] <= 10, f"{label}: formulations[{n}].ktr outside 0.5..10"
    form_ids = {f["id"] for f in forms}
    mt = r["maintenance"]
    assert isinstance(mt, dict) and set(mt) == {"start", "period", "doses"}, f"{label}: maintenance keys"
    assert number(mt["start"]) and 0 <= mt["start"] <= 72, f"{label}: start outside 0..72 h"
    assert number(mt["period"]) and 4 <= mt["period"] <= 168, f"{label}: period outside 4..168 h"
    assert isinstance(mt["doses"], list) and 1 <= len(mt["doses"]) <= 6, f"{label}: 1 to 6 maintenance doses"
    for n, dose in enumerate(mt["doses"]):
        validate_dose(dose, f"{label}: maintenance.doses[{n}]", True, form_ids)
        assert dose["offset"] < mt["period"], f"{label}: maintenance.doses[{n}].offset must be below the period"
    ld = r["loading_doses"]
    assert isinstance(ld, list) and len(ld) <= 4, f"{label}: 0 to 4 loading doses"
    for n, dose in enumerate(ld):
        validate_dose(dose, f"{label}: loading_doses[{n}]", False, form_ids)
        assert dose["time"] <= mt["start"], f"{label}: loading_doses[{n}].time must not exceed start"
        if dose["route"] == "iv_infusion":
            assert dose["time"] + dose["duration"] <= mt["start"], f"{label}: loading_doses[{n}] infusion must end by start"
    assert number(r["horizon"]) and mt["start"] + mt["period"] <= r["horizon"] <= 360, f"{label}: horizon outside start+period..360 h"
    qt = r["query_times"]
    assert isinstance(qt, list) and 3 <= len(qt) <= 10 and all(number(t) and 0 <= t <= r["horizon"] for t in qt), f"{label}: query_times"
    w = r["window"]
    assert isinstance(w, dict) and set(w) == {"low", "high"} and number(w["low"]) and number(w["high"]) and 0 < w["low"] < w["high"], f"{label}: window"


# ------------------------------------------------------------------ report contract (spec 4)
def validate_report(rep, regimen, label):
    keys = {"regimen_id", "concentrations", "auc", "cmax", "t_cmax", "steady_state"}
    assert isinstance(rep, dict) and set(rep) == keys, f"{label}: report keys must be exactly {sorted(keys)}"
    assert rep["regimen_id"] == regimen["regimen_id"], f"{label}: regimen_id must be {regimen['regimen_id']!r}"
    c = rep["concentrations"]
    assert isinstance(c, list) and len(c) == len(regimen["query_times"]) and all(number(v) for v in c), f"{label}: concentrations must hold one finite number per query time"
    assert all(number(rep[k]) for k in ("auc", "cmax", "t_cmax")), f"{label}: auc, cmax and t_cmax must be finite numbers"
    ss = rep["steady_state"]
    skeys = {"cmax", "cmin", "trough", "time_in_window", "n_cycles_to_steady"}
    assert isinstance(ss, dict) and set(ss) == skeys, f"{label}: steady_state keys must be exactly {sorted(skeys)}"
    assert all(number(ss[k]) for k in ("cmax", "cmin", "trough", "time_in_window")), f"{label}: steady_state values must be finite numbers"
    assert integer(ss["n_cycles_to_steady"]) and ss["n_cycles_to_steady"] >= 1, f"{label}: n_cycles_to_steady must be a positive integer"


def within_c(v, ref, S):
    return abs(v - ref) <= TOL_C * S


def compare(rep, exp, label):
    """Failures of the comparison of spec section 5; empty list means pass."""
    errs = []
    S = exp["cmax"]
    if rep["steady_state"]["n_cycles_to_steady"] != exp["steady_state"]["n_cycles_to_steady"]:
        errs.append(f"{label}: n_cycles_to_steady {rep['steady_state']['n_cycles_to_steady']} vs {exp['steady_state']['n_cycles_to_steady']}")
    for n, (a, e) in enumerate(zip(rep["concentrations"], exp["concentrations"])):
        if not within_c(a, e, S):
            errs.append(f"{label}: concentrations[{n}] {a:.15g} vs {e:.15g}")
    if not abs(rep["auc"] - exp["auc"]) <= TOL_AUC * abs(exp["auc"]):
        errs.append(f"{label}: auc {rep['auc']:.15g} vs {exp['auc']:.15g}")
    if not within_c(rep["cmax"], exp["cmax"], S):
        errs.append(f"{label}: cmax {rep['cmax']:.15g} vs {exp['cmax']:.15g}")
    if not abs(rep["t_cmax"] - exp["t_cmax"]) <= TOL_T:
        errs.append(f"{label}: t_cmax {rep['t_cmax']:.15g} vs {exp['t_cmax']:.15g}")
    for k in ("cmax", "cmin", "trough"):
        if not within_c(rep["steady_state"][k], exp["steady_state"][k], S):
            errs.append(f"{label}: steady_state.{k} {rep['steady_state'][k]:.15g} vs {exp['steady_state'][k]:.15g}")
    if not abs(rep["steady_state"]["time_in_window"] - exp["steady_state"]["time_in_window"]) <= TOL_T:
        errs.append(f"{label}: steady_state.time_in_window {rep['steady_state']['time_in_window']:.15g} vs {exp['steady_state']['time_in_window']:.15g}")
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


def _invoke(label, regimen, program_source):
    """Run one isolated, time-bounded call of a program on a regimen and return its report: fresh
    working directory, unprivileged uid, process-group kill on timeout, file-backed output,
    regular-file and size guards before every copy or read."""
    _clear_runner_processes()
    run_dir = SANDBOX / "run"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(mode=0o755)
    in_path, output_path = run_dir / "regimen.json", run_dir / "report.json"
    in_path.write_text(json.dumps(regimen, indent=1) + "\n", encoding="utf-8")
    in_path.chmod(0o444)
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
                ["python", str(program), "--regimen", str(in_path), "--output", str(output_path)],
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
    regimen = load_case(BASE_CASE)
    rep = read_json(BASE_REPORT)
    validate_report(rep, regimen, "base_case_report.json")
    errs = compare(rep, load_expected()[BASE_CASE], "base_case_report.json")
    assert not errs, "\n".join(errs)


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_fresh_case(case_name, record_property):
    """A fresh, stateless run of the program on a shipped or held-out regimen meets the output
    contract and every tolerance against the independent expected values."""
    regimen = load_case(case_name)
    rep = _invoke(case_name, regimen, ARTIFACT)
    validate_report(rep, regimen, case_name)
    errs = compare(rep, load_expected()[regimen["regimen_id"]], case_name)
    record_property("n_cycles_to_steady", rep["steady_state"]["n_cycles_to_steady"])
    assert not errs, "\n".join(errs)


def quantity_of(rep, q, k):
    if q == "concentration":
        return rep["concentrations"][k] if k < len(rep["concentrations"]) else None
    if q in ("auc", "cmax", "t_cmax"):
        return rep[q]
    if q.startswith("ss_"):
        return rep["steady_state"][q[3:]]
    return rep["steady_state"][q]


def test_diagnosis(record_property):
    """diagnosis.json holds 3 to 8 witnesses of at least three distinct quantities; for each, the
    pristine legacy script reproduces the reported legacy value, the independent reference
    reproduces the reported correct value, and the two differ."""
    doc = read_json(DIAGNOSIS)
    assert isinstance(doc, dict) and set(doc) == {"defects"}, "diagnosis.json must have exactly the key 'defects'"
    defects = doc["defects"]
    assert isinstance(defects, list) and 3 <= len(defects) <= 8, "defects must be a list of 3 to 8 entries"
    keys = {"description", "regimen", "quantity", "index", "legacy_value", "correct_value"}
    quantities = set()
    for n, d in enumerate(defects):
        label = f"defects[{n}]"
        assert isinstance(d, dict) and set(d) == keys, f"{label}: keys must be exactly {sorted(keys)}"
        assert isinstance(d["description"], str) and 1 <= len(d["description"]) <= 500, f"{label}: description must be 1 to 500 characters"
        validate_regimen(d["regimen"], label)
        q, k = d["quantity"], d["index"]
        assert q in QUANTITIES, f"{label}: quantity must be one of {sorted(QUANTITIES)}"
        if q == "concentration":
            assert integer(k) and 0 <= k < len(d["regimen"]["query_times"]), f"{label}: index must address query_times"
        else:
            assert k is None, f"{label}: index must be null for {q}"
        if q == "n_cycles_to_steady":
            assert integer(d["legacy_value"]) and integer(d["correct_value"]), f"{label}: n_cycles_to_steady needs integer values"
        else:
            assert number(d["legacy_value"]) and number(d["correct_value"]), f"{label}: values must be finite numbers"
        leg_rep = _invoke(f"{label} legacy", d["regimen"], LEGACY)
        assert isinstance(leg_rep, dict) and all(key in leg_rep for key in ("concentrations", "auc", "cmax", "t_cmax", "steady_state")), f"{label}: legacy report unreadable"
        try:
            leg = quantity_of(leg_rep, q, k)
        except (KeyError, TypeError, IndexError):
            leg = None
        ref_rep = _invoke(f"{label} reference", d["regimen"], REFERENCE)
        validate_report(ref_rep, d["regimen"], f"{label} reference")
        ref = quantity_of(ref_rep, q, k)
        assert leg is not None and ref is not None and (integer(leg) if q == "n_cycles_to_steady" else number(leg)), f"{label}: the quantity is undefined in one of the reports"
        if q == "n_cycles_to_steady":
            assert d["legacy_value"] == leg, f"{label}: legacy_value {d['legacy_value']!r} does not match the legacy script's {leg!r}"
            assert d["correct_value"] == ref, f"{label}: correct_value {d['correct_value']!r} does not match the independent value {ref!r}"
            assert leg != ref, f"{label}: the legacy script and the exact solution agree on {q}; it is not a witness"
        else:
            if q in CONC_Q:
                tol, gap = TOL_C * ref_rep["cmax"], 1e-6 * ref_rep["cmax"]
            elif q == "auc":
                tol, gap = TOL_AUC * abs(ref), 1e-6 * abs(ref)
            else:
                tol, gap = TOL_T, 1e-4
            assert abs(d["legacy_value"] - leg) <= tol, f"{label}: legacy_value {d['legacy_value']} does not match the legacy script's {leg}"
            assert abs(d["correct_value"] - ref) <= tol, f"{label}: correct_value {d['correct_value']} does not match the independent value {ref}"
            assert abs(leg - ref) > gap, f"{label}: the legacy script and the exact solution agree; it is not a witness"
        quantities.add(q)
    record_property("quantities", sorted(quantities))
    assert len(quantities) >= 3, f"witnesses cover only {sorted(quantities)}; at least three distinct quantities are required"
