"""Verifier for refraction-traveltime-audit.

Grades the saved artifacts and fresh runs of /root/results/raytimes.py on the shipped and held-out
models against expected values computed by an independent implementation (/tests/expected.json,
from /tests/reference/reference.py), and checks the diagnosis witnesses by executing the pristine
legacy script and the independent reference. Every comparison is the one TRAVELTIME_SPEC.md
states; contract validation runs before any value is compared.
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

ARTIFACT = Path("/root/results/raytimes.py")
BASE_REPORT = Path("/root/results/base_case_report.json")
DIAGNOSIS = Path("/root/results/diagnosis.json")
CASES = Path("/tests/cases")
EXPECTED_PATH = Path("/tests/expected.json")
LEGACY = Path("/tests/legacy/ttcurve.py")
REFERENCE = Path("/tests/reference/reference.py")
SANDBOX = Path("/sandbox")
CALL_SECONDS = 60
TOL_TP, TOL_X = 1e-9, 5e-7
KINDS = {"direct", "turning", "reflection", "head"}
QUANTITIES = {"arrival_count", "first_arrival_time", "caustic_count", "first_arrival_count"}
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


def close(a, ref, tol):
    return abs(a - ref) <= tol * abs(ref)


def load_expected():
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ model domain (spec 2, 3)
def validate_model(m, label):
    keys = {"model_id", "layers", "x_max_km", "offsets_km"}
    assert isinstance(m, dict) and set(m) == keys, f"{label}: model keys must be exactly {sorted(keys)}"
    assert isinstance(m["model_id"], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", m["model_id"]), f"{label}: bad model_id"
    lay = m["layers"]
    assert isinstance(lay, list) and 2 <= len(lay) <= 6, f"{label}: 2 to 6 layers required"
    for n, l in enumerate(lay):
        assert isinstance(l, dict) and set(l) == {"thickness_km", "v_top_km_s", "gradient_per_s"}, f"{label}: layers[{n}] keys"
        last = n == len(lay) - 1
        if last:
            assert l["thickness_km"] is None, f"{label}: the last layer must have thickness_km null"
        else:
            assert number(l["thickness_km"]) and 0.5 <= l["thickness_km"] <= 15, f"{label}: layers[{n}].thickness_km outside 0.5-15"
        assert number(l["v_top_km_s"]) and 1.5 <= l["v_top_km_s"] <= 8.5, f"{label}: layers[{n}].v_top_km_s outside 1.5-8.5"
        g = l["gradient_per_s"]
        assert number(g) and -0.3 <= g <= 1.5, f"{label}: layers[{n}].gradient_per_s outside -0.3-1.5"
        if not last:
            vb = l["v_top_km_s"] + g * l["thickness_km"]
            assert 1.5 <= vb <= 9.0, f"{label}: layers[{n}] velocity leaves 1.5-9.0"
    assert number(m["x_max_km"]) and 5 <= m["x_max_km"] <= 300, f"{label}: x_max_km outside 5-300"
    off = m["offsets_km"]
    assert isinstance(off, list) and 2 <= len(off) <= 10 and all(number(x) for x in off), f"{label}: 2 to 10 offsets required"
    assert all(a < b for a, b in zip(off, off[1:])), f"{label}: offsets_km must increase strictly"
    assert 0 < off[0] and off[-1] <= m["x_max_km"], f"{label}: offsets_km must lie in (0, x_max_km]"


# ------------------------------------------------------------------ report contract (spec 4)
def validate_report(rep, model, label):
    keys = {"model_id", "arrivals", "caustics", "first_arrival"}
    assert isinstance(rep, dict) and set(rep) == keys, f"{label}: report keys must be exactly {sorted(keys)}"
    assert rep["model_id"] == model["model_id"], f"{label}: model_id must be {model['model_id']!r}"
    arr = rep["arrivals"]
    assert isinstance(arr, list) and len(arr) == len(model["offsets_km"]), f"{label}: arrivals must have one entry per offset"
    for n, (a, x) in enumerate(zip(arr, model["offsets_km"])):
        assert isinstance(a, dict) and set(a) == {"x_km", "rays"}, f"{label}: arrivals[{n}] keys"
        assert a["x_km"] == x, f"{label}: arrivals[{n}].x_km must be the offset {x!r} exactly"
        assert isinstance(a["rays"], list), f"{label}: arrivals[{n}].rays must be a list"
        for m_, r in enumerate(a["rays"]):
            assert isinstance(r, dict) and set(r) == {"kind", "index", "p_s_km", "t_s"}, f"{label}: arrivals[{n}].rays[{m_}] keys"
            assert r["kind"] in KINDS, f"{label}: arrivals[{n}].rays[{m_}].kind must be one of {sorted(KINDS)}"
            assert integer(r["index"]), f"{label}: arrivals[{n}].rays[{m_}].index must be an integer"
            assert number(r["p_s_km"]) and number(r["t_s"]), f"{label}: arrivals[{n}].rays[{m_}] values must be finite numbers"
        ts = [r["t_s"] for r in a["rays"]]
        assert all(u < v for u, v in zip(ts, ts[1:])), f"{label}: arrivals[{n}].rays must be in increasing t_s"
    ca = rep["caustics"]
    assert isinstance(ca, list), f"{label}: caustics must be a list"
    for n, c in enumerate(ca):
        assert isinstance(c, dict) and set(c) == {"kind", "index", "p_s_km", "x_km", "t_s"}, f"{label}: caustics[{n}] keys"
        assert c["kind"] in ("turning", "reflection"), f"{label}: caustics[{n}].kind must be turning or reflection"
        assert integer(c["index"]), f"{label}: caustics[{n}].index must be an integer"
        assert all(number(c[k]) for k in ("p_s_km", "x_km", "t_s")), f"{label}: caustics[{n}] values must be finite numbers"
    xs = [c["x_km"] for c in ca]
    assert all(u < v for u, v in zip(xs, xs[1:])), f"{label}: caustics must be in increasing x_km"
    fa = rep["first_arrival"]
    assert isinstance(fa, list) and fa, f"{label}: first_arrival must be a non-empty list"
    for n, f in enumerate(fa):
        assert isinstance(f, dict) and set(f) == {"kind", "index", "x_start_km", "x_end_km"}, f"{label}: first_arrival[{n}] keys"
        assert f["kind"] in KINDS and integer(f["index"]), f"{label}: first_arrival[{n}] kind/index"
        assert number(f["x_start_km"]) and number(f["x_end_km"]) and f["x_start_km"] < f["x_end_km"], f"{label}: first_arrival[{n}] bounds"
    assert fa[0]["x_start_km"] == 0, f"{label}: the first interval must start at 0"
    assert fa[-1]["x_end_km"] == model["x_max_km"], f"{label}: the last interval must end at x_max_km exactly"
    for n in range(len(fa) - 1):
        assert fa[n]["x_end_km"] == fa[n + 1]["x_start_km"], f"{label}: first_arrival[{n}] and [{n + 1}] must share their boundary exactly"


def compare(rep, exp, label):
    """Failures of the comparison of spec section 5; empty list means pass."""
    errs = []
    for n, (a, e) in enumerate(zip(rep["arrivals"], exp["arrivals"])):
        if len(a["rays"]) != len(e["rays"]):
            errs.append(f"{label}: {len(a['rays'])} arrivals at x {a['x_km']}, {len(e['rays'])} expected")
    if len(rep["caustics"]) != len(exp["caustics"]):
        errs.append(f"{label}: {len(rep['caustics'])} caustics, {len(exp['caustics'])} expected")
    if len(rep["first_arrival"]) != len(exp["first_arrival"]):
        errs.append(f"{label}: {len(rep['first_arrival'])} first-arrival intervals, {len(exp['first_arrival'])} expected")
    if errs:
        return errs
    for n, (a, e) in enumerate(zip(rep["arrivals"], exp["arrivals"])):
        for m_, (r, q) in enumerate(zip(a["rays"], e["rays"])):
            where = f"{label}: arrivals[{n}] (x {a['x_km']}) rays[{m_}]"
            if (r["kind"], r["index"]) != (q["kind"], q["index"]):
                errs.append(f"{where}: {r['kind']} {r['index']} vs {q['kind']} {q['index']}")
            for k in ("p_s_km", "t_s"):
                if not close(r[k], q[k], TOL_TP):
                    errs.append(f"{where}.{k} {r[k]:.12g} vs {q[k]:.12g} (rel tol {TOL_TP})")
    for n, (c, q) in enumerate(zip(rep["caustics"], exp["caustics"])):
        if (c["kind"], c["index"]) != (q["kind"], q["index"]):
            errs.append(f"{label}: caustics[{n}] {c['kind']} {c['index']} vs {q['kind']} {q['index']}")
        for k in ("p_s_km", "t_s"):
            if not close(c[k], q[k], TOL_TP):
                errs.append(f"{label}: caustics[{n}].{k} {c[k]:.12g} vs {q[k]:.12g} (rel tol {TOL_TP})")
        if not close(c["x_km"], q["x_km"], TOL_X):
            errs.append(f"{label}: caustics[{n}].x_km {c['x_km']:.10g} vs {q['x_km']:.10g} (rel tol {TOL_X})")
    for n, (f, q) in enumerate(zip(rep["first_arrival"], exp["first_arrival"])):
        if (f["kind"], f["index"]) != (q["kind"], q["index"]):
            errs.append(f"{label}: first_arrival[{n}] {f['kind']} {f['index']} vs {q['kind']} {q['index']}")
        if n + 1 < len(exp["first_arrival"]) and not close(f["x_end_km"], q["x_end_km"], TOL_X):
            errs.append(f"{label}: first_arrival[{n}].x_end_km {f['x_end_km']:.10g} vs {q['x_end_km']:.10g} (rel tol {TOL_X})")
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


def _invoke(label, model, program_source):
    """Run one isolated, time-bounded call of a program on a model and return its report: fresh
    working directory, unprivileged uid, process-group kill on timeout, file-backed output,
    regular-file and size guards before every copy or read."""
    _clear_runner_processes()
    run_dir = SANDBOX / "run"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(mode=0o755)
    model_path, output_path = run_dir / "model.json", run_dir / "report.json"
    model_path.write_text(json.dumps(model, indent=1) + "\n", encoding="utf-8")
    model_path.chmod(0o444)
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
                ["python", str(program), "--model", str(model_path), "--output", str(output_path)],
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
    model = load_case(BASE_CASE)
    rep = read_json(BASE_REPORT)
    validate_report(rep, model, "base_case_report.json")
    errs = compare(rep, load_expected()[BASE_CASE], "base_case_report.json")
    assert not errs, "\n".join(errs)


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_fresh_case(case_name, record_property):
    """A fresh, stateless run of the program on a shipped or held-out model meets the output
    contract and every tolerance against the independent expected values."""
    model = load_case(case_name)
    rep = _invoke(case_name, model, ARTIFACT)
    validate_report(rep, model, case_name)
    errs = compare(rep, load_expected()[model["model_id"]], case_name)
    record_property("caustics", len(rep["caustics"]))
    record_property("first_arrival_intervals", len(rep["first_arrival"]))
    assert not errs, "\n".join(errs)


def quantity_of(rep, q, x):
    if q == "caustic_count":
        return len(rep["caustics"])
    if q == "first_arrival_count":
        return len(rep["first_arrival"])
    rays = next(a for a in rep["arrivals"] if a["x_km"] == x)["rays"]
    if q == "arrival_count":
        return len(rays)
    return min(r["t_s"] for r in rays) if rays else None


def test_diagnosis(record_property):
    """diagnosis.json holds 3 to 8 witnesses of at least three distinct quantities; for each, the
    pristine legacy script reproduces the reported legacy value, the independent reference
    reproduces the reported correct value, and the two differ."""
    doc = read_json(DIAGNOSIS)
    assert isinstance(doc, dict) and set(doc) == {"defects"}, "diagnosis.json must have exactly the key 'defects'"
    defects = doc["defects"]
    assert isinstance(defects, list) and 3 <= len(defects) <= 8, "defects must be a list of 3 to 8 entries"
    keys = {"description", "model", "quantity", "offset_km", "legacy_value", "correct_value"}
    quantities = set()
    for n, d in enumerate(defects):
        label = f"defects[{n}]"
        assert isinstance(d, dict) and set(d) == keys, f"{label}: keys must be exactly {sorted(keys)}"
        assert isinstance(d["description"], str) and 1 <= len(d["description"]) <= 500, f"{label}: description must be 1 to 500 characters"
        validate_model(d["model"], label)
        q, x = d["quantity"], d["offset_km"]
        assert q in QUANTITIES, f"{label}: quantity must be one of {sorted(QUANTITIES)}"
        if q in ("arrival_count", "first_arrival_time"):
            assert number(x) and x in d["model"]["offsets_km"], f"{label}: offset_km must be one of the model's offsets"
        else:
            assert x is None, f"{label}: offset_km must be null for {q}"
        if q == "first_arrival_time":
            assert number(d["legacy_value"]) and number(d["correct_value"]), f"{label}: values must be finite numbers"
        else:
            assert integer(d["legacy_value"]) and integer(d["correct_value"]), f"{label}: values must be integers"
        leg = quantity_of(_invoke(f"{label} legacy", d["model"], LEGACY), q, x)
        ref_rep = _invoke(f"{label} reference", d["model"], REFERENCE)
        validate_report(ref_rep, d["model"], f"{label} reference")
        ref = quantity_of(ref_rep, q, x)
        if q == "first_arrival_time":
            assert leg is not None and close(d["legacy_value"], leg, TOL_TP), f"{label}: legacy_value {d['legacy_value']} does not match the legacy script's {leg}"
            assert close(d["correct_value"], ref, TOL_TP), f"{label}: correct_value {d['correct_value']} does not match the independent value {ref}"
            assert not close(leg, ref, TOL_TP), f"{label}: the legacy script and the exact solution agree; it is not a witness"
        else:
            assert d["legacy_value"] == leg, f"{label}: legacy_value {d['legacy_value']!r} does not match the legacy script's {leg!r}"
            assert d["correct_value"] == ref, f"{label}: correct_value {d['correct_value']!r} does not match the independent value {ref!r}"
            assert leg != ref, f"{label}: the legacy script and the exact solution agree on {q}; it is not a witness"
        quantities.add(q)
    record_property("quantities", sorted(quantities))
    assert len(quantities) >= 3, f"witnesses cover only {sorted(quantities)}; at least three distinct quantities are required"
