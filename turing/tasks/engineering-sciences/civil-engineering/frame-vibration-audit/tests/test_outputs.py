"""Verifier for frame-vibration-audit.

Grades the saved artifacts and fresh runs of /root/results/framedyn.py on the shipped and
held-out frames against expected values computed by an independent implementation
(/tests/expected.json, from /tests/reference/reference.py), and checks the diagnosis witnesses by
executing the pristine legacy script and the independent reference. Every comparison is the one
FRAME_SPEC.md states; contract validation runs before any value is compared.
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

ARTIFACT = Path("/root/results/framedyn.py")
BASE_REPORT = Path("/root/results/base_case_report.json")
DIAGNOSIS = Path("/root/results/diagnosis.json")
CASES = Path("/tests/cases")
EXPECTED_PATH = Path("/tests/expected.json")
LEGACY = Path("/tests/legacy/framefreq.py")
REFERENCE = Path("/tests/reference/reference.py")
SANDBOX = Path("/sandbox")
CALL_SECONDS = 120
TOL = 1e-9
DOFS = ("ux", "uy", "rz")
QUANTITIES = {"frequency", "count_below", "static", "harmonic"}
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


# ------------------------------------------------------------------ frame domain (spec 2, 3)
def validate_frame(m, label):
    keys = {"frame_id", "nodes", "members", "nodal_loads", "member_loads", "static_query_nodes", "n_modes", "f_max_Hz", "harmonic_queries"}
    assert isinstance(m, dict) and set(m) == keys, f"{label}: frame keys must be exactly {sorted(keys)}"
    assert isinstance(m["frame_id"], str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", m["frame_id"]), f"{label}: bad frame_id"
    nodes = m["nodes"]
    assert isinstance(nodes, list) and 2 <= len(nodes) <= 12, f"{label}: 2 to 12 nodes required"
    coords = {}
    for n, nd in enumerate(nodes):
        assert isinstance(nd, dict) and set(nd) == {"id", "x", "y", "mass_kg", "support"}, f"{label}: nodes[{n}] keys"
        assert integer(nd["id"]) and nd["id"] == n + 1, f"{label}: nodes[{n}].id must be {n + 1}"
        assert number(nd["x"]) and number(nd["y"]) and -30 <= nd["x"] <= 30 and -30 <= nd["y"] <= 30, f"{label}: nodes[{n}] coordinates outside -30..30"
        assert number(nd["mass_kg"]) and 0 <= nd["mass_kg"] <= 5e4, f"{label}: nodes[{n}].mass_kg outside 0..5e4"
        sp = nd["support"]
        assert isinstance(sp, dict) and set(sp) == set(DOFS) and all(type(sp[k]) is bool for k in DOFS), f"{label}: nodes[{n}].support"
        coords[nd["id"]] = (nd["x"], nd["y"])
    mem = m["members"]
    assert isinstance(mem, list) and 1 <= len(mem) <= 16, f"{label}: 1 to 16 members required"
    for n, mb in enumerate(mem):
        assert isinstance(mb, dict) and set(mb) == {"id", "i", "j", "E", "A", "I", "rho"}, f"{label}: members[{n}] keys"
        assert integer(mb["id"]) and mb["id"] == n + 1, f"{label}: members[{n}].id must be {n + 1}"
        assert integer(mb["i"]) and integer(mb["j"]) and mb["i"] in coords and mb["j"] in coords and mb["i"] != mb["j"], f"{label}: members[{n}] end nodes"
        L = math.hypot(coords[mb["j"]][0] - coords[mb["i"]][0], coords[mb["j"]][1] - coords[mb["i"]][1])
        assert 0.5 <= L <= 20, f"{label}: members[{n}] length {L:.3g} outside 0.5..20 m"
        assert number(mb["E"]) and 2e10 <= mb["E"] <= 2.1e11, f"{label}: members[{n}].E outside 2e10..2.1e11"
        assert number(mb["A"]) and 1e-4 <= mb["A"] <= 5e-2, f"{label}: members[{n}].A outside 1e-4..5e-2"
        assert number(mb["I"]) and 1e-7 <= mb["I"] <= 5e-3, f"{label}: members[{n}].I outside 1e-7..5e-3"
        assert number(mb["rho"]) and 1500 <= mb["rho"] <= 8000, f"{label}: members[{n}].rho outside 1500..8000"
    for n, ld in enumerate(m["nodal_loads"]):
        assert isinstance(ld, dict) and set(ld) == {"node", "Fx", "Fy", "Mz"} and ld["node"] in coords, f"{label}: nodal_loads[{n}]"
        assert all(number(ld[k]) and abs(ld[k]) <= 1e6 for k in ("Fx", "Fy", "Mz")), f"{label}: nodal_loads[{n}] magnitude"
    for n, ld in enumerate(m["member_loads"]):
        assert isinstance(ld, dict) and set(ld) == {"member", "wx", "wy"} and integer(ld["member"]) and 1 <= ld["member"] <= len(mem), f"{label}: member_loads[{n}]"
        assert all(number(ld[k]) and abs(ld[k]) <= 1e5 for k in ("wx", "wy")), f"{label}: member_loads[{n}] magnitude"
    sq = m["static_query_nodes"]
    assert isinstance(sq, list) and 1 <= len(sq) <= 6 and all(integer(v) and v in coords for v in sq), f"{label}: static_query_nodes"
    assert integer(m["n_modes"]) and 3 <= m["n_modes"] <= 12, f"{label}: n_modes outside 3..12"
    assert number(m["f_max_Hz"]) and 1 <= m["f_max_Hz"] <= 500, f"{label}: f_max_Hz outside 1..500"
    hq = m["harmonic_queries"]
    assert isinstance(hq, list) and 1 <= len(hq) <= 4, f"{label}: 1 to 4 harmonic queries"
    for n, q in enumerate(hq):
        assert isinstance(q, dict) and set(q) == {"load_node", "load_dof", "amplitude", "f_Hz", "response_node", "response_dof"}, f"{label}: harmonic_queries[{n}] keys"
        assert q["load_node"] in coords and q["response_node"] in coords and q["load_dof"] in DOFS and q["response_dof"] in DOFS, f"{label}: harmonic_queries[{n}] nodes/dofs"
        assert number(q["amplitude"]) and 0 < abs(q["amplitude"]) <= 1e6 and number(q["f_Hz"]) and 0 < q["f_Hz"] <= 500, f"{label}: harmonic_queries[{n}] values"


# ------------------------------------------------------------------ report contract (spec 4)
def validate_report(rep, frame, label):
    keys = {"frame_id", "static", "frequencies_Hz", "count_below", "harmonic"}
    assert isinstance(rep, dict) and set(rep) == keys, f"{label}: report keys must be exactly {sorted(keys)}"
    assert rep["frame_id"] == frame["frame_id"], f"{label}: frame_id must be {frame['frame_id']!r}"
    st = rep["static"]
    assert isinstance(st, list) and len(st) == len(frame["static_query_nodes"]), f"{label}: static must have one entry per query node"
    for n, (s, nid) in enumerate(zip(st, frame["static_query_nodes"])):
        assert isinstance(s, dict) and set(s) == {"node", "ux", "uy", "rz"}, f"{label}: static[{n}] keys"
        assert s["node"] == nid, f"{label}: static[{n}].node must be {nid}"
        assert all(number(s[k]) for k in DOFS), f"{label}: static[{n}] values"
    fr = rep["frequencies_Hz"]
    assert isinstance(fr, list) and len(fr) == frame["n_modes"] and all(number(f) and f > 0 for f in fr), f"{label}: frequencies_Hz must hold n_modes positive numbers"
    assert all(a <= b for a, b in zip(fr, fr[1:])), f"{label}: frequencies_Hz must be non-decreasing"
    assert integer(rep["count_below"]) and rep["count_below"] >= 0, f"{label}: count_below must be a non-negative integer"
    hm = rep["harmonic"]
    assert isinstance(hm, list) and len(hm) == len(frame["harmonic_queries"]), f"{label}: harmonic must have one entry per query"
    for n, (h, q) in enumerate(zip(hm, frame["harmonic_queries"])):
        assert isinstance(h, dict) and set(h) == set(q) | {"U"}, f"{label}: harmonic[{n}] keys"
        assert all(h[k] == q[k] for k in q), f"{label}: harmonic[{n}] query fields must be as given"
        assert number(h["U"]), f"{label}: harmonic[{n}].U"


def scales(exp):
    """S of section 5 for each value kind of a reference report."""
    tr = [abs(s[k]) for s in exp["static"] for k in ("ux", "uy")]
    ro = [abs(s["rz"]) for s in exp["static"]]
    ht = [abs(h["U"]) for h in exp["harmonic"] if h["response_dof"] != "rz"]
    hr = [abs(h["U"]) for h in exp["harmonic"] if h["response_dof"] == "rz"]
    return dict(tr=max(tr, default=0.0), ro=max(ro, default=0.0), ht=max(ht, default=0.0), hr=max(hr, default=0.0))


def within(v, ref, S):
    return abs(v - ref) <= TOL * max(abs(ref), S)


def compare(rep, exp, label):
    """Failures of the comparison of spec section 5; empty list means pass."""
    errs = []
    if rep["count_below"] != exp["count_below"]:
        errs.append(f"{label}: count_below {rep['count_below']} vs {exp['count_below']}")
    S = scales(exp)
    for n, (a, e) in enumerate(zip(rep["static"], exp["static"])):
        for k in DOFS:
            if not within(a[k], e[k], S["ro"] if k == "rz" else S["tr"]):
                errs.append(f"{label}: static[{n}].{k} {a[k]:.15g} vs {e[k]:.15g}")
    for n, (a, e) in enumerate(zip(rep["frequencies_Hz"], exp["frequencies_Hz"])):
        if not close_rel(a, e, TOL):
            errs.append(f"{label}: frequencies_Hz[{n}] {a:.15g} vs {e:.15g} (rel tol {TOL})")
    for n, (a, e) in enumerate(zip(rep["harmonic"], exp["harmonic"])):
        if not within(a["U"], e["U"], S["hr"] if e["response_dof"] == "rz" else S["ht"]):
            errs.append(f"{label}: harmonic[{n}].U {a['U']:.15g} vs {e['U']:.15g}")
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


def _invoke(label, frame, program_source):
    """Run one isolated, time-bounded call of a program on a frame and return its report: fresh
    working directory, unprivileged uid, process-group kill on timeout, file-backed output,
    regular-file and size guards before every copy or read."""
    _clear_runner_processes()
    run_dir = SANDBOX / "run"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(mode=0o755)
    frame_path, output_path = run_dir / "frame.json", run_dir / "report.json"
    frame_path.write_text(json.dumps(frame, indent=1) + "\n", encoding="utf-8")
    frame_path.chmod(0o444)
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
                ["python", str(program), "--frame", str(frame_path), "--output", str(output_path)],
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
    frame = load_case(BASE_CASE)
    rep = read_json(BASE_REPORT)
    validate_report(rep, frame, "base_case_report.json")
    errs = compare(rep, load_expected()[BASE_CASE], "base_case_report.json")
    assert not errs, "\n".join(errs)


@pytest.mark.parametrize("case_name", CASE_NAMES)
def test_fresh_case(case_name, record_property):
    """A fresh, stateless run of the program on a shipped or held-out frame meets the output
    contract and every tolerance against the independent expected values."""
    frame = load_case(case_name)
    rep = _invoke(case_name, frame, ARTIFACT)
    validate_report(rep, frame, case_name)
    errs = compare(rep, load_expected()[frame["frame_id"]], case_name)
    record_property("count_below", rep["count_below"])
    assert not errs, "\n".join(errs)


def quantity_of(rep, q, k):
    if q == "count_below":
        return rep["count_below"]
    if q == "frequency":
        return rep["frequencies_Hz"][k] if k < len(rep["frequencies_Hz"]) else None
    if q == "harmonic":
        return rep["harmonic"][k]["U"]
    return rep["static"][k["query"]][k["dof"]]


def test_diagnosis(record_property):
    """diagnosis.json holds 3 to 8 witnesses of at least three distinct quantities; for each, the
    pristine legacy script reproduces the reported legacy value, the independent reference
    reproduces the reported correct value, and the two differ."""
    doc = read_json(DIAGNOSIS)
    assert isinstance(doc, dict) and set(doc) == {"defects"}, "diagnosis.json must have exactly the key 'defects'"
    defects = doc["defects"]
    assert isinstance(defects, list) and 3 <= len(defects) <= 8, "defects must be a list of 3 to 8 entries"
    keys = {"description", "frame", "quantity", "index", "legacy_value", "correct_value"}
    quantities = set()
    for n, d in enumerate(defects):
        label = f"defects[{n}]"
        assert isinstance(d, dict) and set(d) == keys, f"{label}: keys must be exactly {sorted(keys)}"
        assert isinstance(d["description"], str) and 1 <= len(d["description"]) <= 500, f"{label}: description must be 1 to 500 characters"
        validate_frame(d["frame"], label)
        q, k = d["quantity"], d["index"]
        assert q in QUANTITIES, f"{label}: quantity must be one of {sorted(QUANTITIES)}"
        if q == "count_below":
            assert k is None and integer(d["legacy_value"]) and integer(d["correct_value"]), f"{label}: count_below needs null index and integer values"
        elif q == "frequency":
            assert integer(k) and 0 <= k < d["frame"]["n_modes"], f"{label}: index must address frequencies_Hz"
        elif q == "harmonic":
            assert integer(k) and 0 <= k < len(d["frame"]["harmonic_queries"]), f"{label}: index must address harmonic_queries"
        else:
            assert isinstance(k, dict) and set(k) == {"query", "dof"} and integer(k["query"]) and 0 <= k["query"] < len(d["frame"]["static_query_nodes"]) and k["dof"] in DOFS, f"{label}: static index"
        if q != "count_below":
            assert number(d["legacy_value"]) and number(d["correct_value"]), f"{label}: values must be finite numbers"
        leg_rep = _invoke(f"{label} legacy", d["frame"], LEGACY)
        assert isinstance(leg_rep, dict) and all(key in leg_rep for key in ("static", "frequencies_Hz", "count_below", "harmonic")), f"{label}: legacy report unreadable"
        leg = quantity_of(leg_rep, q, k)
        ref_rep = _invoke(f"{label} reference", d["frame"], REFERENCE)
        validate_report(ref_rep, d["frame"], f"{label} reference")
        ref = quantity_of(ref_rep, q, k)
        assert leg is not None and ref is not None and (q == "count_below" or number(leg)), f"{label}: the quantity is undefined in one of the reports"
        if q == "count_below":
            assert d["legacy_value"] == leg, f"{label}: legacy_value {d['legacy_value']!r} does not match the legacy script's {leg!r}"
            assert d["correct_value"] == ref, f"{label}: correct_value {d['correct_value']!r} does not match the independent value {ref!r}"
            assert leg != ref, f"{label}: the legacy script and the exact solution agree on {q}; it is not a witness"
        else:
            S = 0.0
            if q == "static":
                S = scales(ref_rep)["ro" if k["dof"] == "rz" else "tr"]
            elif q == "harmonic":
                S = scales(ref_rep)["hr" if d["frame"]["harmonic_queries"][k]["response_dof"] == "rz" else "ht"]
            assert within(d["legacy_value"], leg, S), f"{label}: legacy_value {d['legacy_value']} does not match the legacy script's {leg}"
            assert within(d["correct_value"], ref, S), f"{label}: correct_value {d['correct_value']} does not match the independent value {ref}"
            assert abs(leg - ref) > 1e-6 * max(abs(ref), S), f"{label}: the legacy script and the exact solution agree; it is not a witness"
        quantities.add(q)
    record_property("quantities", sorted(quantities))
    assert len(quantities) >= 3, f"witnesses cover only {sorted(quantities)}; at least three distinct quantities are required"
