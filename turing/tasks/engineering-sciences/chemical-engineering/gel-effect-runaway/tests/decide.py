"""Pure verifier decision: pytest exit status + CTRF report -> reward.

Prints 1 or 0 and exits 0 for a valid grading run. Exits 2 (infrastructure error, no
decision) for a pytest exit other than 0/1, an unreadable report, a test set other than
EXPECTED, any skipped/pending/other test, or counts that disagree with the exit status.
"""
import json
import sys

EXPECTED = ["test_state.py::test_castings_conversion_and_exotherm",
            "test_state.py::test_castings_molar_masses",
            "test_state.py::test_castings_mwd_fractions",
            "test_state.py::test_cure_program_in_plant"]


def decide(exit_status, report):
    if exit_status not in (0, 1):
        raise ValueError(f"pytest exit status {exit_status} is not a test outcome")
    tests, summary = report["results"]["tests"], report["results"]["summary"]
    names = sorted(t["name"] for t in tests)
    if names != EXPECTED:
        raise ValueError(f"collected {names}, expected {EXPECTED}")
    statuses = [t["status"] for t in tests]
    if any(s not in ("passed", "failed") for s in statuses):
        raise ValueError(f"non-graded test status in {statuses}")
    failed = statuses.count("failed")
    counts = {"tests": len(tests), "passed": len(tests) - failed, "failed": failed,
              "skipped": 0, "pending": 0, "other": 0}
    if any(summary.get(k) != v for k, v in counts.items()):
        raise ValueError(f"summary {summary} disagrees with the test list")
    if (exit_status == 0) != (failed == 0):
        raise ValueError(f"exit status {exit_status} disagrees with {failed} failed test(s)")
    return 1 if failed == 0 else 0


if __name__ == "__main__":
    try:
        with open(sys.argv[2], encoding="utf-8") as fh:
            reward = decide(int(sys.argv[1]), json.load(fh))
    except Exception as e:  # any doubt about the run is an infrastructure error
        print(f"infrastructure error: {e}", file=sys.stderr)
        sys.exit(2)
    print(reward)
