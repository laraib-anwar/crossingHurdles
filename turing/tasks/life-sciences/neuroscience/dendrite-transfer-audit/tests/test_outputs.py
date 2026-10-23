"""Verifier for dendrite-transfer-audit.

Grades the saved artifacts and fresh runs of /root/results/cabletree.py on the shipped and
held-out neurons against expected values computed by an independent implementation
(/tests/expected.json, from /tests/reference/reference.py), and checks the diagnosis witnesses by
executing the pristine legacy script and the independent reference. Every comparison is the one
CABLE_SPEC.md states; contract validation runs before any value is compared.
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

ARTIFACT = Path("/root/results/cabletree.py")
BASE_REPORT = Path("/root/results/base_case_report.json")
DIAGNOSIS = Path("/root/results/diagnosis.json")
CASES = Path("/tests/cases")
EXPECTED_PATH = Path("/tests/expected.json")
LEGACY = Path("/tests/legacy/cableprop.py")
REFERENCE = Path("/tests/reference/reference.py")
SANDBOX = Path("/sandbox")
CALL_SECONDS = 60
TOL_REL, TOL_PHASE, TOL_COEF = 1e-9, 1e-7, 1e-9
ENDS = {"sealed", "killed", "shunt"}
QUANTITIES = {"input_resistance", "attenuation", "impedance_magnitude", "mode_count", "tau"}
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


# ------------------------------------------------------------------ neuron domain (spec 2, 3)
def location(v, label, segs):
    assert isinstance(v, dict) and set(v) == {"segment", "fraction"}, f"{label}: location keys"
    assert integer(v["segment"]) and (v["segment"] == 0 or v["segment"] in segs), f"{label}: location segment"
    assert number(v["fraction"]) and 0 <= v["fraction"] <= 1, f"{label}: location fraction"
    if v["segment"] == 0:
        assert v["fraction"] == 0, f"{label}: the soma is location (0, 0)"


def validate_neuron(m, label):
    keys = {"neuron_id", "soma", "segments", "input_resistance_sites", "attenuation_pairs", "impedance_queries", "tau_min_ms"}
    assert isinstance(m, dict) and set(m) == keys, f"{label}: neuron keys must be exactly {sorted(keys)}"
    assert isinstance(m["neuron_id"], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", m["neuron_id"]), f"{label}: bad neuron_id"
    so = m["soma"]
    assert isinstance(so, dict) and set(so) == {"d_um", "Rm_ohm_cm2", "Cm_uF_cm2", "shunt_nS"}, f"{label}: soma keys"
    assert number(so["d_um"]) and 8 <= so["d_um"] <= 40, f"{label}: soma d_um outside 8-40"
    assert number(so["Rm_ohm_cm2"]) and 2000 <= so["Rm_ohm_cm2"] <= 60000, f"{label}: soma Rm outside 2000-60000"
    assert number(so["Cm_uF_cm2"]) and 0.6 <= so["Cm_uF_cm2"] <= 2, f"{label}: soma Cm outside 0.6-2"
    assert number(so["shunt_nS"]) and 0 <= so["shunt_nS"] <= 20, f"{label}: soma shunt outside 0-20"
    segs = m["segments"]
    assert isinstance(segs, list) and 3 <= len(segs) <= 12, f"{label}: 3 to 12 segments required"
    ids, children, taus = set(), {}, []
    for n, s in enumerate(segs):
        assert isinstance(s, dict) and set(s) == {"id", "parent", "L_um", "d_um", "Rm_ohm_cm2", "Ri_ohm_cm", "Cm_uF_cm2", "end"}, f"{label}: segments[{n}] keys"
        assert integer(s["id"]) and s["id"] == n + 1, f"{label}: segments[{n}].id must be {n + 1}"
        assert integer(s["parent"]) and (s["parent"] == 0 or s["parent"] in ids), f"{label}: segments[{n}].parent must be 0 or an earlier id"
        ids.add(s["id"])
        children.setdefault(s["parent"], []).append(s["id"])
        assert number(s["L_um"]) and 20 <= s["L_um"] <= 600, f"{label}: segments[{n}].L_um outside 20-600"
        assert number(s["d_um"]) and 0.3 <= s["d_um"] <= 6, f"{label}: segments[{n}].d_um outside 0.3-6"
        assert number(s["Rm_ohm_cm2"]) and 2000 <= s["Rm_ohm_cm2"] <= 60000, f"{label}: segments[{n}].Rm outside 2000-60000"
        assert number(s["Ri_ohm_cm"]) and 70 <= s["Ri_ohm_cm"] <= 300, f"{label}: segments[{n}].Ri outside 70-300"
        assert number(s["Cm_uF_cm2"]) and 0.6 <= s["Cm_uF_cm2"] <= 2, f"{label}: segments[{n}].Cm outside 0.6-2"
        taus.append(s["Rm_ohm_cm2"] * s["Cm_uF_cm2"] * 1e-3)
    for n, s in enumerate(segs):
        if s["id"] in children:
            assert s["end"] is None, f"{label}: segments[{n}] has children and must have end null"
        else:
            e = s["end"]
            assert isinstance(e, dict) and set(e) == {"type", "g_nS"} and e["type"] in ENDS, f"{label}: segments[{n}].end"
            if e["type"] == "shunt":
                assert number(e["g_nS"]) and 0.5 <= e["g_nS"] <= 20, f"{label}: segments[{n}].end.g_nS outside 0.5-20"
            else:
                assert e["g_nS"] is None, f"{label}: segments[{n}].end.g_nS must be null"
    sites = m["input_resistance_sites"]
    assert isinstance(sites, list) and 2 <= len(sites) <= 8, f"{label}: 2 to 8 input resistance sites"
    for k, v in enumerate(sites):
        location(v, f"{label}: input_resistance_sites[{k}]", ids)
    pairs = m["attenuation_pairs"]
    assert isinstance(pairs, list) and 2 <= len(pairs) <= 8, f"{label}: 2 to 8 attenuation pairs"
    for k, p in enumerate(pairs):
        assert isinstance(p, dict) and set(p) == {"source", "target"}, f"{label}: attenuation_pairs[{k}] keys"
        location(p["source"], f"{label}: attenuation_pairs[{k}].source", ids)
        location(p["target"], f"{label}: attenuation_pairs[{k}].target", ids)
    qs = m["impedance_queries"]
    assert isinstance(qs, list) and 2 <= len(qs) <= 8, f"{label}: 2 to 8 impedance queries"
    for k, q in enumerate(qs):
        assert isinstance(q, dict) and set(q) == {"source", "target", "frequency_Hz"}, f"{label}: impedance_queries[{k}] keys"
        location(q["source"], f"{label}: impedance_queries[{k}].source", ids)
        location(q["target"], f"{label}: impedance_queries[{k}].target", ids)
        assert number(q["frequency_Hz"]) and 1 <= q["frequency_Hz"] <= 2000, f"{label}: impedance_queries[{k}].frequency_Hz outside 1-2000"
    tm = m["tau_min_ms"]
    assert number(tm) and 0.1 <= tm <= 20 and tm <= 0.5 * min(taus), f"{label}: tau_min_ms outside its domain"


# ------------------------------------------------------------------ report contract (spec 4)
def validate_report(rep, neuron, label):
    keys = {"neuron_id", "input_resistance", "attenuation", "impedance", "modes"}
    assert isinstance(rep, dict) and set(rep) == keys, f"{label}: report keys must be exactly {sorted(keys)}"
    assert rep["neuron_id"] == neuron["neuron_id"], f"{label}: neuron_id must be {neuron['neuron_id']!r}"
    rin = rep["input_resistance"]
    assert isinstance(rin, list) and len(rin) == len(neuron["input_resistance_sites"]), f"{label}: input_resistance must have one entry per site"
    for n, (e, site) in enumerate(zip(rin, neuron["input_resistance_sites"])):
        assert isinstance(e, dict) and set(e) == {"site", "R_MOhm"}, f"{label}: input_resistance[{n}] keys"
        assert e["site"] == site, f"{label}: input_resistance[{n}].site must be the site exactly"
        assert number(e["R_MOhm"]) and e["R_MOhm"] > 0, f"{label}: input_resistance[{n}].R_MOhm"
    att = rep["attenuation"]
    assert isinstance(att, list) and len(att) == len(neuron["attenuation_pairs"]), f"{label}: attenuation must have one entry per pair"
    for n, (e, p) in enumerate(zip(att, neuron["attenuation_pairs"])):
        assert isinstance(e, dict) and set(e) == {"source", "target", "factor"}, f"{label}: attenuation[{n}] keys"
        assert e["source"] == p["source"] and e["target"] == p["target"], f"{label}: attenuation[{n}] locations must be as given"
        assert number(e["factor"]) and 0 < e["factor"] <= 1, f"{label}: attenuation[{n}].factor"
    imp = rep["impedance"]
    assert isinstance(imp, list) and len(imp) == len(neuron["impedance_queries"]), f"{label}: impedance must have one entry per query"
    for n, (e, q) in enumerate(zip(imp, neuron["impedance_queries"])):
        assert isinstance(e, dict) and set(e) == {"source", "target", "frequency_Hz", "magnitude_MOhm", "phase_deg"}, f"{label}: impedance[{n}] keys"
        assert e["source"] == q["source"] and e["target"] == q["target"] and e["frequency_Hz"] == q["frequency_Hz"], f"{label}: impedance[{n}] query must be as given"
        assert number(e["magnitude_MOhm"]) and e["magnitude_MOhm"] > 0, f"{label}: impedance[{n}].magnitude_MOhm"
        assert number(e["phase_deg"]) and -180 < e["phase_deg"] <= 180, f"{label}: impedance[{n}].phase_deg must lie in (-180, 180]"
    modes = rep["modes"]
    assert isinstance(modes, list), f"{label}: modes must be a list"
    for n, e in enumerate(modes):
        assert isinstance(e, dict) and set(e) == {"tau_ms", "coefficient_MOhm"}, f"{label}: modes[{n}] keys"
        assert number(e["tau_ms"]) and e["tau_ms"] >= neuron["tau_min_ms"], f"{label}: modes[{n}].tau_ms must be a number >= tau_min_ms"
        assert number(e["coefficient_MOhm"]), f"{label}: modes[{n}].coefficient_MOhm"
    taus = [e["tau_ms"] for e in modes]
    assert all(a > b for a, b in zip(taus, taus[1:])), f"{label}: modes must be in strictly decreasing tau_ms"


def soma_rin(exp):
    for e in exp["input_resistance"]:
        if e["site"]["segment"] == 0:
            return e["R_MOhm"]
    return None


def compare(rep, exp, label, rin_soma):
    """Failures of the comparison of spec section 5; empty list means pass."""
    errs = []
    if len(rep["modes"]) != len(exp["modes"]):
        return [f"{label}: {len(rep['modes'])} modes, {len(exp['modes'])} expected"]
    for n, (a, e) in enumerate(zip(rep["input_resistance"], exp["input_resistance"])):
        if not close_rel(a["R_MOhm"], e["R_MOhm"], TOL_REL):
            errs.append(f"{label}: input_resistance[{n}].R_MOhm {a['R_MOhm']:.12g} vs {e['R_MOhm']:.12g} (rel tol {TOL_REL})")
    for n, (a, e) in enumerate(zip(rep["attenuation"], exp["attenuation"])):
        if not close_rel(a["factor"], e["factor"], TOL_REL):
            errs.append(f"{label}: attenuation[{n}].factor {a['factor']:.12g} vs {e['factor']:.12g} (rel tol {TOL_REL})")
    for n, (a, e) in enumerate(zip(rep["impedance"], exp["impedance"])):
        if not close_rel(a["magnitude_MOhm"], e["magnitude_MOhm"], TOL_REL):
            errs.append(f"{label}: impedance[{n}].magnitude_MOhm {a['magnitude_MOhm']:.12g} vs {e['magnitude_MOhm']:.12g} (rel tol {TOL_REL})")
        if not close_abs(a["phase_deg"], e["phase_deg"], TOL_PHASE):
            errs.append(f"{label}: impedance[{n}].phase_deg {a['phase_deg']:.12g} vs {e['phase_deg']:.12g} (abs tol {TOL_PHASE})")
    for n, (a, e) in enumerate(zip(rep["modes"], exp["modes"])):
        if not close_rel(a["tau_ms"], e["tau_ms"], TOL_REL):
            errs.append(f"{label}: modes[{n}].tau_ms {a['tau_ms']:.12g} vs {e['tau_ms']:.12g} (rel tol {TOL_REL})")
        if not close_abs(a["coefficient_MOhm"], e["coefficient_MOhm"], TOL_COEF * rin_soma):
            errs.append(f"{label}: modes[{n}].coefficient_MOhm {a['coefficient_MOhm']:.12g} vs {e['coefficient_MOhm']:.12g} (abs tol {TOL_COEF} x R_in(soma))")
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


def _invoke(label, neuron, program_source):
    """Run one isolated, time-bounded call of a program on a neuron and return its report: fresh
    working directory, unprivileged uid, process-group kill on timeout, file-backed output,
    regular-file and size guards before every copy or read."""
    _clear_runner_processes()
    run_dir = SANDBOX / "run"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(mode=0o755)
    neuron_path, output_path = run_dir / "neuron.json", run_dir / "report.json"
    neuron_path.write_text(json.dumps(neuron, indent=1) + "\n", encoding="utf-8")
    neuron_path.chmod(0o444)
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
                ["python", str(program), "--neuron", str(neuron_path), "--output", str(output_path)],
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
    neuron = load_case(BASE_CASE)
    rep = read_json(BASE_REPORT)
    validate_report(rep, neuron, "base_case_report.json")
    exp = load_expected()[BASE_CASE]
    errs = compare(rep, exp, "base_case_report.json", soma_rin(exp))
    assert not errs, "\n".join(errs)


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_fresh_case(case_name, record_property):
    """A fresh, stateless run of the program on a shipped or held-out neuron meets the output
    contract and every tolerance against the independent expected values."""
    neuron = load_case(case_name)
    rep = _invoke(case_name, neuron, ARTIFACT)
    validate_report(rep, neuron, case_name)
    exp = load_expected()[neuron["neuron_id"]]
    errs = compare(rep, exp, case_name, soma_rin(exp))
    record_property("modes", len(rep["modes"]))
    assert not errs, "\n".join(errs)


def quantity_of(rep, q, k):
    if q == "mode_count":
        return len(rep["modes"])
    if q == "tau":
        return rep["modes"][k]["tau_ms"] if k < len(rep["modes"]) else None
    if q == "input_resistance":
        return rep["input_resistance"][k]["R_MOhm"]
    if q == "attenuation":
        return rep["attenuation"][k]["factor"]
    return rep["impedance"][k]["magnitude_MOhm"]


def test_diagnosis(record_property):
    """diagnosis.json holds 3 to 8 witnesses of at least three distinct quantities; for each, the
    pristine legacy script reproduces the reported legacy value, the independent reference
    reproduces the reported correct value, and the two differ."""
    doc = read_json(DIAGNOSIS)
    assert isinstance(doc, dict) and set(doc) == {"defects"}, "diagnosis.json must have exactly the key 'defects'"
    defects = doc["defects"]
    assert isinstance(defects, list) and 3 <= len(defects) <= 8, "defects must be a list of 3 to 8 entries"
    keys = {"description", "neuron", "quantity", "index", "legacy_value", "correct_value"}
    quantities = set()
    for n, d in enumerate(defects):
        label = f"defects[{n}]"
        assert isinstance(d, dict) and set(d) == keys, f"{label}: keys must be exactly {sorted(keys)}"
        assert isinstance(d["description"], str) and 1 <= len(d["description"]) <= 500, f"{label}: description must be 1 to 500 characters"
        validate_neuron(d["neuron"], label)
        q, k = d["quantity"], d["index"]
        assert q in QUANTITIES, f"{label}: quantity must be one of {sorted(QUANTITIES)}"
        lists = {"input_resistance": "input_resistance_sites", "attenuation": "attenuation_pairs", "impedance_magnitude": "impedance_queries"}
        if q in lists:
            assert integer(k) and 0 <= k < len(d["neuron"][lists[q]]), f"{label}: index must address the neuron's {lists[q]}"
        elif q == "tau":
            assert integer(k) and k >= 0, f"{label}: index must be a non-negative integer"
        else:
            assert k is None, f"{label}: index must be null for mode_count"
        if q == "mode_count":
            assert integer(d["legacy_value"]) and integer(d["correct_value"]), f"{label}: counts must be integers"
        else:
            assert number(d["legacy_value"]) and number(d["correct_value"]), f"{label}: values must be finite numbers"
        leg_rep = _invoke(f"{label} legacy", d["neuron"], LEGACY)
        assert isinstance(leg_rep, dict) and all(key in leg_rep for key in ("input_resistance", "attenuation", "impedance", "modes")), f"{label}: legacy report unreadable"
        leg = quantity_of(leg_rep, q, k)
        ref_rep = _invoke(f"{label} reference", d["neuron"], REFERENCE)
        validate_report(ref_rep, d["neuron"], f"{label} reference")
        ref = quantity_of(ref_rep, q, k)
        assert leg is not None and ref is not None, f"{label}: index {k} does not exist in both reports"
        if q == "mode_count":
            assert d["legacy_value"] == leg, f"{label}: legacy_value {d['legacy_value']!r} does not match the legacy script's {leg!r}"
            assert d["correct_value"] == ref, f"{label}: correct_value {d['correct_value']!r} does not match the independent value {ref!r}"
            assert leg != ref, f"{label}: the legacy script and the exact solution agree on {q}; it is not a witness"
        else:
            assert close_rel(d["legacy_value"], leg, TOL_REL), f"{label}: legacy_value {d['legacy_value']} does not match the legacy script's {leg}"
            assert close_rel(d["correct_value"], ref, TOL_REL), f"{label}: correct_value {d['correct_value']} does not match the independent value {ref}"
            assert not close_rel(leg, ref, 1e-6), f"{label}: the legacy script and the exact solution agree; it is not a witness"
        quantities.add(q)
    record_property("quantities", sorted(quantities))
    assert len(quantities) >= 3, f"witnesses cover only {sorted(quantities)}; at least three distinct quantities are required"
