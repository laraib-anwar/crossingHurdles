"""Verifier for heterostructure-tunneling-audit.

Grades the saved artifacts and fresh runs of /root/results/hetero.py on the shipped and
held-out structures against expected values computed by an independent implementation
(/tests/expected.json, from /tests/reference/reference.py), and checks the diagnosis witnesses by
executing the pristine legacy script and the independent reference. Every comparison is the one
HETERO_SPEC.md states; contract validation runs before any value is compared.
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

ARTIFACT = Path("/root/results/hetero.py")
BASE_REPORT = Path("/root/results/base_case_report.json")
DIAGNOSIS = Path("/root/results/diagnosis.json")
CASES = Path("/tests/cases")
EXPECTED_PATH = Path("/tests/expected.json")
LEGACY = Path("/tests/legacy/qwell.py")
REFERENCE = Path("/tests/reference/reference.py")
SANDBOX = Path("/sandbox")
CALL_SECONDS = 120
TOL_E, TOL_T, TOL_EMAX = 1e-9, 1e-9, 1e-8
QUANTITIES = {"bound_count", "bound_energy", "transmission", "maxima_count", "maximum_energy"}
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


# ------------------------------------------------------------------ structure domain (spec 2, 3)
def validate_structure(m, label):
    keys = {"structure_id", "left_lead", "right_lead", "layers", "transmission_energies_eV", "window_eV"}
    assert isinstance(m, dict) and set(m) == keys, f"{label}: structure keys must be exactly {sorted(keys)}"
    assert isinstance(m["structure_id"], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", m["structure_id"]), f"{label}: bad structure_id"
    pots = []
    for side in ("left_lead", "right_lead"):
        ld = m[side]
        assert isinstance(ld, dict) and set(ld) == {"mass", "v_eV"}, f"{label}: {side} keys"
        assert number(ld["mass"]) and 0.03 <= ld["mass"] <= 1.0, f"{label}: {side}.mass outside 0.03-1.0"
        assert number(ld["v_eV"]) and -1.0 <= ld["v_eV"] <= 2.0, f"{label}: {side}.v_eV outside -1.0-2.0"
        pots.append(ld["v_eV"])
    lay = m["layers"]
    assert isinstance(lay, list) and 2 <= len(lay) <= 14, f"{label}: 2 to 14 layers required"
    total = 0.0
    for n, ly in enumerate(lay):
        assert isinstance(ly, dict) and set(ly) == {"thickness_nm", "mass", "vl_eV", "vr_eV"}, f"{label}: layers[{n}] keys"
        assert number(ly["thickness_nm"]) and 0.3 <= ly["thickness_nm"] <= 30, f"{label}: layers[{n}].thickness_nm outside 0.3-30"
        assert number(ly["mass"]) and 0.03 <= ly["mass"] <= 1.0, f"{label}: layers[{n}].mass outside 0.03-1.0"
        for k in ("vl_eV", "vr_eV"):
            assert number(ly[k]) and -1.0 <= ly[k] <= 2.0, f"{label}: layers[{n}].{k} outside -1.0-2.0"
            pots.append(ly[k])
        if ly["vl_eV"] != ly["vr_eV"]:
            slope = abs(ly["vr_eV"] - ly["vl_eV"]) / ly["thickness_nm"]
            assert 1e-3 <= slope <= 0.5, f"{label}: layers[{n}] slope outside 1e-3-0.5 eV/nm"
        total += ly["thickness_nm"]
    assert total <= 150, f"{label}: total thickness above 150 nm"
    te = m["transmission_energies_eV"]
    assert isinstance(te, list) and 2 <= len(te) <= 8 and all(number(e) for e in te), f"{label}: 2 to 8 transmission energies"
    assert all(a < b for a, b in zip(te, te[1:])), f"{label}: transmission energies must increase strictly"
    edge = max(m["left_lead"]["v_eV"], m["right_lead"]["v_eV"])
    assert all(e >= edge + 1e-3 for e in te), f"{label}: transmission energies must lie 1e-3 eV above both lead edges"
    w = m["window_eV"]
    assert isinstance(w, list) and len(w) == 2 and all(number(e) for e in w), f"{label}: window_eV"
    assert 0.01 <= w[1] - w[0] <= 1.0, f"{label}: window width outside 0.01-1.0 eV"
    assert w[0] >= max(pots) + 0.01, f"{label}: window must lie 0.01 eV above the potential maximum"


# ------------------------------------------------------------------ report contract (spec 4)
def validate_report(rep, structure, label):
    keys = {"structure_id", "bound_states", "transmission", "maxima"}
    assert isinstance(rep, dict) and set(rep) == keys, f"{label}: report keys must be exactly {sorted(keys)}"
    assert rep["structure_id"] == structure["structure_id"], f"{label}: structure_id must be {structure['structure_id']!r}"
    bs = rep["bound_states"]
    assert isinstance(bs, list), f"{label}: bound_states must be a list"
    for n, b in enumerate(bs):
        assert isinstance(b, dict) and set(b) == {"E_eV"} and number(b["E_eV"]), f"{label}: bound_states[{n}]"
    es = [b["E_eV"] for b in bs]
    assert all(a < b for a, b in zip(es, es[1:])), f"{label}: bound_states must be in increasing energy"
    E_th = min(structure["left_lead"]["v_eV"], structure["right_lead"]["v_eV"])
    assert all(e < E_th for e in es), f"{label}: bound states must lie below the lower lead edge"
    tr = rep["transmission"]
    assert isinstance(tr, list) and len(tr) == len(structure["transmission_energies_eV"]), f"{label}: transmission must have one entry per energy"
    for n, (t, E) in enumerate(zip(tr, structure["transmission_energies_eV"])):
        assert isinstance(t, dict) and set(t) == {"E_eV", "T"}, f"{label}: transmission[{n}] keys"
        assert t["E_eV"] == E, f"{label}: transmission[{n}].E_eV must be {E!r} exactly"
        assert number(t["T"]) and 0 < t["T"] <= 1 + 1e-12, f"{label}: transmission[{n}].T must lie in (0, 1]"
    mx = rep["maxima"]
    assert isinstance(mx, list), f"{label}: maxima must be a list"
    lo, hi = structure["window_eV"]
    for n, x in enumerate(mx):
        assert isinstance(x, dict) and set(x) == {"E_eV", "T"} and number(x["E_eV"]) and number(x["T"]), f"{label}: maxima[{n}]"
        assert lo < x["E_eV"] < hi, f"{label}: maxima[{n}] outside the window"
    ms = [x["E_eV"] for x in mx]
    assert all(a < b for a, b in zip(ms, ms[1:])), f"{label}: maxima must be in increasing energy"


def compare(rep, exp, label):
    """Failures of the comparison of spec section 5; empty list means pass."""
    errs = []
    if len(rep["bound_states"]) != len(exp["bound_states"]):
        errs.append(f"{label}: {len(rep['bound_states'])} bound states, {len(exp['bound_states'])} expected")
    if len(rep["maxima"]) != len(exp["maxima"]):
        errs.append(f"{label}: {len(rep['maxima'])} maxima, {len(exp['maxima'])} expected")
    if errs:
        return errs
    for n, (a, e) in enumerate(zip(rep["bound_states"], exp["bound_states"])):
        if not close_abs(a["E_eV"], e["E_eV"], TOL_E):
            errs.append(f"{label}: bound_states[{n}].E_eV {a['E_eV']:.15g} vs {e['E_eV']:.15g} (abs tol {TOL_E})")
    for n, (a, e) in enumerate(zip(rep["transmission"], exp["transmission"])):
        if not close_rel(a["T"], e["T"], TOL_T):
            errs.append(f"{label}: transmission[{n}].T {a['T']:.15g} vs {e['T']:.15g} (rel tol {TOL_T})")
    for n, (a, e) in enumerate(zip(rep["maxima"], exp["maxima"])):
        if not close_abs(a["E_eV"], e["E_eV"], TOL_EMAX):
            errs.append(f"{label}: maxima[{n}].E_eV {a['E_eV']:.15g} vs {e['E_eV']:.15g} (abs tol {TOL_EMAX})")
        if not close_rel(a["T"], e["T"], TOL_T):
            errs.append(f"{label}: maxima[{n}].T {a['T']:.15g} vs {e['T']:.15g} (rel tol {TOL_T})")
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


def _invoke(label, structure, program_source):
    """Run one isolated, time-bounded call of a program on a structure and return its report: fresh
    working directory, unprivileged uid, process-group kill on timeout, file-backed output,
    regular-file and size guards before every copy or read."""
    _clear_runner_processes()
    run_dir = SANDBOX / "run"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(mode=0o755)
    structure_path, output_path = run_dir / "structure.json", run_dir / "report.json"
    structure_path.write_text(json.dumps(structure, indent=1) + "\n", encoding="utf-8")
    structure_path.chmod(0o444)
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
                ["python", str(program), "--structure", str(structure_path), "--output", str(output_path)],
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
    structure = load_case(BASE_CASE)
    rep = read_json(BASE_REPORT)
    validate_report(rep, structure, "base_case_report.json")
    errs = compare(rep, load_expected()[BASE_CASE], "base_case_report.json")
    assert not errs, "\n".join(errs)


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_fresh_case(case_name, record_property):
    """A fresh, stateless run of the program on a shipped or held-out structure meets the output
    contract and every tolerance against the independent expected values."""
    structure = load_case(case_name)
    rep = _invoke(case_name, structure, ARTIFACT)
    validate_report(rep, structure, case_name)
    errs = compare(rep, load_expected()[structure["structure_id"]], case_name)
    record_property("bound_states", len(rep["bound_states"]))
    record_property("maxima", len(rep["maxima"]))
    assert not errs, "\n".join(errs)


def quantity_of(rep, q, k):
    if q == "bound_count":
        return len(rep["bound_states"])
    if q == "maxima_count":
        return len(rep["maxima"])
    if q == "bound_energy":
        return rep["bound_states"][k]["E_eV"] if k < len(rep["bound_states"]) else None
    if q == "maximum_energy":
        return rep["maxima"][k]["E_eV"] if k < len(rep["maxima"]) else None
    return rep["transmission"][k]["T"]


def test_diagnosis(record_property):
    """diagnosis.json holds 3 to 8 witnesses of at least three distinct quantities; for each, the
    pristine legacy script reproduces the reported legacy value, the independent reference
    reproduces the reported correct value, and the two differ."""
    doc = read_json(DIAGNOSIS)
    assert isinstance(doc, dict) and set(doc) == {"defects"}, "diagnosis.json must have exactly the key 'defects'"
    defects = doc["defects"]
    assert isinstance(defects, list) and 3 <= len(defects) <= 8, "defects must be a list of 3 to 8 entries"
    keys = {"description", "structure", "quantity", "index", "legacy_value", "correct_value"}
    quantities = set()
    for n, d in enumerate(defects):
        label = f"defects[{n}]"
        assert isinstance(d, dict) and set(d) == keys, f"{label}: keys must be exactly {sorted(keys)}"
        assert isinstance(d["description"], str) and 1 <= len(d["description"]) <= 500, f"{label}: description must be 1 to 500 characters"
        validate_structure(d["structure"], label)
        q, k = d["quantity"], d["index"]
        assert q in QUANTITIES, f"{label}: quantity must be one of {sorted(QUANTITIES)}"
        if q in ("bound_count", "maxima_count"):
            assert k is None, f"{label}: index must be null for {q}"
            assert integer(d["legacy_value"]) and integer(d["correct_value"]), f"{label}: counts must be integers"
        else:
            assert integer(k) and k >= 0, f"{label}: index must be a non-negative integer"
            if q == "transmission":
                assert k < len(d["structure"]["transmission_energies_eV"]), f"{label}: index must address transmission_energies_eV"
            assert number(d["legacy_value"]) and number(d["correct_value"]), f"{label}: values must be finite numbers"
        leg_rep = _invoke(f"{label} legacy", d["structure"], LEGACY)
        assert isinstance(leg_rep, dict) and all(key in leg_rep for key in ("bound_states", "transmission", "maxima")), f"{label}: legacy report unreadable"
        leg = quantity_of(leg_rep, q, k)
        ref_rep = _invoke(f"{label} reference", d["structure"], REFERENCE)
        validate_report(ref_rep, d["structure"], f"{label} reference")
        ref = quantity_of(ref_rep, q, k)
        assert leg is not None and ref is not None, f"{label}: index {k} does not exist in both reports"
        if q in ("bound_count", "maxima_count"):
            assert d["legacy_value"] == leg, f"{label}: legacy_value {d['legacy_value']!r} does not match the legacy script's {leg!r}"
            assert d["correct_value"] == ref, f"{label}: correct_value {d['correct_value']!r} does not match the independent value {ref!r}"
            assert leg != ref, f"{label}: the legacy script and the exact solution agree on {q}; it is not a witness"
        else:
            assert number(leg), f"{label}: the legacy value is not a finite number"
            if q == "transmission":
                same = lambda a, b: close_rel(a, b, TOL_T)
                differ = not close_rel(leg, ref, 1e-6)
            else:
                tol = TOL_E if q == "bound_energy" else TOL_EMAX
                same = lambda a, b, tol=tol: close_abs(a, b, tol)
                differ = not close_abs(leg, ref, 1e-6)
            assert same(d["legacy_value"], leg), f"{label}: legacy_value {d['legacy_value']} does not match the legacy script's {leg}"
            assert same(d["correct_value"], ref), f"{label}: correct_value {d['correct_value']} does not match the independent value {ref}"
            assert differ, f"{label}: the legacy script and the exact solution agree; it is not a witness"
        quantities.add(q)
    record_property("quantities", sorted(quantities))
    assert len(quantities) >= 3, f"witnesses cover only {sorted(quantities)}; at least three distinct quantities are required"
