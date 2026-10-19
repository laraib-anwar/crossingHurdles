"""Verifier for washcoat-ignition-audit.

Grades the saved artifacts and fresh runs of /root/results/lightoff_exact.py on the shipped and
held-out recipes against expected values computed by an independent implementation
(/tests/expected.json, from /tests/reference/reference.py), and checks the diagnosis witnesses
by executing the pristine legacy script and the independent reference. Every comparison is the
one WASHCOAT_SPEC.md states; contract validation runs before any value is compared.
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

ARTIFACT = Path("/root/results/lightoff_exact.py")
BASE_REPORT = Path("/root/results/base_case_report.json")
DIAGNOSIS = Path("/root/results/diagnosis.json")
CASES = Path("/tests/cases")
EXPECTED_PATH = Path("/tests/expected.json")
LEGACY = Path("/tests/legacy/lightoff.py")
REFERENCE = Path("/tests/reference/reference.py")
SANDBOX = Path("/sandbox")
CALL_SECONDS = 120
TOL_PHI, TOL_VAL, TOL_OMEGA = 1e-6, 1e-6, 1e-5
KINDS = {"ignition", "extinction"}
STABILITY = {"stable", "unstable_real", "unstable_complex"}
QUANTITIES = {"fold_count", "hopf_count", "state_count", "stability", "fold_phi"}
CASE_NAMES = sorted(p.stem for p in CASES.glob("*.json"))
BASE_CASE = "lightoff_01"
RECIPE_KEYS = {"recipe_id", "beta", "gamma", "Bi_m", "Bi_h", "Le", "phi_min", "phi_max", "phi_query"}


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


def close_rel(a, ref, tol):
    """Relative comparison with a floor of 1 on the scale: |a - ref| <= tol max(1, |ref|) for
    values (theta_c, eta), plain relative for phi and omega (always positive)."""
    return abs(a - ref) <= tol * abs(ref)


def close_val(a, ref):
    return abs(a - ref) <= TOL_VAL * max(1.0, abs(ref))


def load_expected():
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ recipe domain (spec 2, 3)
def validate_recipe(r, label):
    assert isinstance(r, dict) and set(r) == RECIPE_KEYS, f"{label}: recipe keys must be exactly {sorted(RECIPE_KEYS)}"
    assert isinstance(r["recipe_id"], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", r["recipe_id"]), f"{label}: bad recipe_id"
    for k in RECIPE_KEYS - {"recipe_id", "phi_query"}:
        assert number(r[k]), f"{label}: {k} must be a finite number"
    assert 0.05 <= r["beta"] <= 0.6, f"{label}: beta outside the domain"
    assert 8 <= r["gamma"] <= 40, f"{label}: gamma outside the domain"
    assert 1 <= r["Bi_m"] <= 200, f"{label}: Bi_m outside the domain"
    assert 0.5 <= r["Bi_h"] <= 50 and r["Bi_h"] <= r["Bi_m"], f"{label}: Bi_h outside the domain"
    assert r["beta"] * r["Bi_m"] / r["Bi_h"] <= 1.0, f"{label}: beta Bi_m / Bi_h must be at most 1"
    assert 0.05 <= r["Le"] <= 20, f"{label}: Le outside the domain"
    assert 0.01 <= r["phi_min"] <= 1, f"{label}: phi_min outside the domain"
    assert 0.3 <= r["phi_max"] <= 30 and r["phi_max"] >= 3 * r["phi_min"], f"{label}: phi_max outside the domain"
    q = r["phi_query"]
    assert isinstance(q, list) and 2 <= len(q) <= 8 and all(number(v) for v in q), f"{label}: phi_query must hold 2 to 8 numbers"
    assert all(a < b for a, b in zip(q, q[1:])), f"{label}: phi_query must increase strictly"
    assert r["phi_min"] <= q[0] and q[-1] <= r["phi_max"], f"{label}: phi_query must lie in [phi_min, phi_max]"


# ------------------------------------------------------------------ report contract (spec 4)
def validate_report(rep, recipe, label):
    keys = {"recipe_id", "folds", "hopf_points", "states"}
    assert isinstance(rep, dict) and set(rep) == keys, f"{label}: report keys must be exactly {sorted(keys)}"
    assert rep["recipe_id"] == recipe["recipe_id"], f"{label}: recipe_id must be {recipe['recipe_id']!r}"
    assert isinstance(rep["folds"], list), f"{label}: folds must be a list"
    for n, f in enumerate(rep["folds"]):
        assert isinstance(f, dict) and set(f) == {"phi", "theta_c", "eta", "kind"}, f"{label}: folds[{n}] keys"
        for k in ("phi", "theta_c", "eta"):
            assert number(f[k]), f"{label}: folds[{n}].{k} must be a finite number"
        assert f["kind"] in KINDS, f"{label}: folds[{n}].kind must be one of {sorted(KINDS)}"
    phis = [f["phi"] for f in rep["folds"]]
    assert all(a < b for a, b in zip(phis, phis[1:])), f"{label}: folds must be in increasing phi"
    assert isinstance(rep["hopf_points"], list), f"{label}: hopf_points must be a list"
    for n, h in enumerate(rep["hopf_points"]):
        assert isinstance(h, dict) and set(h) == {"phi", "theta_c", "eta", "omega"}, f"{label}: hopf_points[{n}] keys"
        for k in ("phi", "theta_c", "eta", "omega"):
            assert number(h[k]), f"{label}: hopf_points[{n}].{k} must be a finite number"
    phis = [h["phi"] for h in rep["hopf_points"]]
    assert all(a < b for a, b in zip(phis, phis[1:])), f"{label}: hopf_points must be in increasing phi"
    st = rep["states"]
    assert isinstance(st, list) and len(st) == len(recipe["phi_query"]), f"{label}: states must have one entry per phi_query"
    for n, (s, q) in enumerate(zip(st, recipe["phi_query"])):
        assert isinstance(s, dict) and set(s) == {"phi", "branches"}, f"{label}: states[{n}] keys"
        assert s["phi"] == q, f"{label}: states[{n}].phi must be the query value {q!r} exactly"
        assert isinstance(s["branches"], list), f"{label}: states[{n}].branches must be a list"
        for m, b in enumerate(s["branches"]):
            assert isinstance(b, dict) and set(b) == {"theta_c", "eta", "stability"}, f"{label}: states[{n}].branches[{m}] keys"
            assert number(b["theta_c"]) and number(b["eta"]), f"{label}: states[{n}].branches[{m}] values must be finite numbers"
            assert b["stability"] in STABILITY, f"{label}: states[{n}].branches[{m}].stability must be one of {sorted(STABILITY)}"
        th = [b["theta_c"] for b in s["branches"]]
        assert all(a < b for a, b in zip(th, th[1:])), f"{label}: states[{n}].branches must be in increasing theta_c"


def compare(rep, exp, label):
    """Failures of the comparison of spec section 5; empty list means pass."""
    errs = []
    if len(rep["folds"]) != len(exp["folds"]):
        errs.append(f"{label}: {len(rep['folds'])} folds reported, {len(exp['folds'])} expected")
    if len(rep["hopf_points"]) != len(exp["hopf_points"]):
        errs.append(f"{label}: {len(rep['hopf_points'])} Hopf points reported, {len(exp['hopf_points'])} expected")
    for n, (s, e) in enumerate(zip(rep["states"], exp["states"])):
        if len(s["branches"]) != len(e["branches"]):
            errs.append(f"{label}: {len(s['branches'])} steady states at phi {s['phi']}, {len(e['branches'])} expected")
    if errs:
        return errs
    for n, (f, e) in enumerate(zip(rep["folds"], exp["folds"])):
        if not close_rel(f["phi"], e["phi"], TOL_PHI):
            errs.append(f"{label}: folds[{n}].phi {f['phi']:.9g} vs {e['phi']:.9g} (rel tol {TOL_PHI})")
        for k in ("theta_c", "eta"):
            if not close_val(f[k], e[k]):
                errs.append(f"{label}: folds[{n}].{k} {f[k]:.9g} vs {e[k]:.9g} (tol {TOL_VAL} max(1, |ref|))")
        if f["kind"] != e["kind"]:
            errs.append(f"{label}: folds[{n}].kind {f['kind']} vs {e['kind']}")
    for n, (h, e) in enumerate(zip(rep["hopf_points"], exp["hopf_points"])):
        if not close_rel(h["phi"], e["phi"], TOL_PHI):
            errs.append(f"{label}: hopf_points[{n}].phi {h['phi']:.9g} vs {e['phi']:.9g} (rel tol {TOL_PHI})")
        for k in ("theta_c", "eta"):
            if not close_val(h[k], e[k]):
                errs.append(f"{label}: hopf_points[{n}].{k} {h[k]:.9g} vs {e[k]:.9g} (tol {TOL_VAL} max(1, |ref|))")
        if not close_rel(h["omega"], e["omega"], TOL_OMEGA):
            errs.append(f"{label}: hopf_points[{n}].omega {h['omega']:.9g} vs {e['omega']:.9g} (rel tol {TOL_OMEGA})")
    for n, (s, e) in enumerate(zip(rep["states"], exp["states"])):
        for m, (b, eb) in enumerate(zip(s["branches"], e["branches"])):
            for k in ("theta_c", "eta"):
                if not close_val(b[k], eb[k]):
                    errs.append(f"{label}: states[{n}].branches[{m}].{k} {b[k]:.9g} vs {eb[k]:.9g} (tol {TOL_VAL} max(1, |ref|))")
            if b["stability"] != eb["stability"]:
                errs.append(f"{label}: states[{n}].branches[{m}].stability {b['stability']} vs {eb['stability']}")
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
    """Run one isolated, time-bounded call of a program on a recipe and return its report:
    fresh working directory, unprivileged uid, process-group kill on timeout, file-backed
    output, regular-file and size guards before every copy or read."""
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
    record_property("folds", len(rep["folds"]))
    record_property("hopf_points", len(rep["hopf_points"]))
    assert not errs, "\n".join(errs)


def quantity_of(rep, q, sel, label):
    """The value of a diagnosis quantity in a report (legacy or reference)."""
    if q == "fold_count":
        return len(rep["folds"])
    if q == "hopf_count":
        return len(rep["hopf_points"])
    if q == "state_count":
        return len(next(s for s in rep["states"] if s["phi"] == sel)["branches"])
    if q == "stability":
        phi, idx = sel
        br = next(s for s in rep["states"] if s["phi"] == phi)["branches"]
        assert 0 <= idx < len(br), f"{label}: selector index {idx} outside the {len(br)} states at phi {phi}"
        return br[idx]["stability"]
    assert 0 <= sel < len(rep["folds"]), f"{label}: selector index {sel} outside the {len(rep['folds'])} folds"
    return rep["folds"][sel]["phi"]


def test_diagnosis(record_property):
    """diagnosis.json holds 3 to 8 witnesses of at least three distinct quantities; for each, the
    pristine legacy script reproduces the reported legacy value, the independent reference
    reproduces the reported correct value, and the two differ."""
    doc = read_json(DIAGNOSIS)
    assert isinstance(doc, dict) and set(doc) == {"defects"}, "diagnosis.json must have exactly the key 'defects'"
    defects = doc["defects"]
    assert isinstance(defects, list) and 3 <= len(defects) <= 8, "defects must be a list of 3 to 8 entries"
    keys = {"description", "recipe", "quantity", "selector", "legacy_value", "correct_value"}
    quantities = set()
    for n, d in enumerate(defects):
        label = f"defects[{n}]"
        assert isinstance(d, dict) and set(d) == keys, f"{label}: keys must be exactly {sorted(keys)}"
        assert isinstance(d["description"], str) and 1 <= len(d["description"]) <= 500, f"{label}: description must be 1 to 500 characters"
        validate_recipe(d["recipe"], label)
        q, sel = d["quantity"], d["selector"]
        assert q in QUANTITIES, f"{label}: quantity must be one of {sorted(QUANTITIES)}"
        if q in ("fold_count", "hopf_count"):
            assert sel is None, f"{label}: selector must be null for {q}"
            assert integer(d["legacy_value"]) and integer(d["correct_value"]), f"{label}: values must be integers"
        elif q == "state_count":
            assert number(sel) and sel in d["recipe"]["phi_query"], f"{label}: selector must be one of the recipe's phi_query values"
            assert integer(d["legacy_value"]) and integer(d["correct_value"]), f"{label}: values must be integers"
        elif q == "stability":
            assert isinstance(sel, list) and len(sel) == 2 and number(sel[0]) and sel[0] in d["recipe"]["phi_query"] and integer(sel[1]), \
                f"{label}: selector must be [phi_query value, integer index]"
            assert d["legacy_value"] in STABILITY and d["correct_value"] in STABILITY, f"{label}: values must be stability classes"
        else:
            assert integer(sel), f"{label}: selector must be an integer fold index"
            assert number(d["legacy_value"]) and number(d["correct_value"]), f"{label}: values must be finite numbers"
        legacy_rep = _invoke(f"{label} legacy", d["recipe"], LEGACY)
        ref_rep = _invoke(f"{label} reference", d["recipe"], REFERENCE)
        validate_report(ref_rep, d["recipe"], f"{label} reference")
        if q == "stability":
            phi = sel[0]
            nl = len(next(s for s in legacy_rep["states"] if s["phi"] == phi)["branches"])
            nr = len(next(s for s in ref_rep["states"] if s["phi"] == phi)["branches"])
            assert nl == nr, f"{label}: a stability witness needs the same number of states in both reports ({nl} vs {nr})"
        if q == "fold_phi":
            assert len(legacy_rep["folds"]) == len(ref_rep["folds"]), f"{label}: a fold_phi witness needs the same number of folds in both reports"
        leg = quantity_of(legacy_rep, q, sel, label)
        ref = quantity_of(ref_rep, q, sel, label)
        if q == "fold_phi":
            assert close_rel(d["legacy_value"], leg, TOL_PHI), f"{label}: legacy_value {d['legacy_value']} does not match the legacy script's {leg}"
            assert close_rel(d["correct_value"], ref, TOL_PHI), f"{label}: correct_value {d['correct_value']} does not match the independent value {ref}"
            assert not close_rel(leg, ref, TOL_PHI), f"{label}: the legacy script and the exact solution agree on this fold; it is not a witness"
        else:
            assert d["legacy_value"] == leg, f"{label}: legacy_value {d['legacy_value']!r} does not match the legacy script's {leg!r}"
            assert d["correct_value"] == ref, f"{label}: correct_value {d['correct_value']!r} does not match the independent value {ref!r}"
            assert leg != ref, f"{label}: the legacy script and the exact solution agree on {q}; it is not a witness"
        quantities.add(q)
    record_property("quantities", sorted(quantities))
    assert len(quantities) >= 3, f"witnesses cover only {sorted(quantities)}; at least three distinct quantities are required"
