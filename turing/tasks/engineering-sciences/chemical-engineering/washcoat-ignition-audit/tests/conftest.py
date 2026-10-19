"""Preserve every parametrized pytest node in CTRF using actual phase reports.

pytest-json-ctrf 0.3.5 collapses parametrized cases by function name; this hook rewrites the
report with every node, its status and the phases in which it failed.
"""
import json
from pathlib import Path
import time

import pytest

_collected = []
_reports = {}
_started = 0


def pytest_sessionstart(session):
    global _started
    _collected.clear()
    _reports.clear()
    _started = int(time.time() * 1000)


def pytest_collection_finish(session):
    _collected.extend(item.nodeid for item in session.items)


def pytest_runtest_logreport(report):
    entry = _reports.setdefault(report.nodeid, {"name": report.nodeid, "status": "pending", "duration": 0.0})
    entry["duration"] += report.duration * 1000
    if report.when == "call" and report.user_properties:
        entry.setdefault("extra", {}).update(dict(report.user_properties))
    if report.failed:
        entry["status"] = "failed"
        entry["message"] = str(report.longrepr)
        entry.setdefault("extra", {}).setdefault("failure_phases", []).append(report.when)
    elif report.skipped and entry["status"] != "failed":
        entry["status"] = "skipped"
    elif report.when == "call" and entry["status"] not in {"failed", "skipped"}:
        entry["status"] = "passed"


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    yield
    tests = [_reports.get(nodeid, {"name": nodeid, "status": "pending", "duration": 0.0}) for nodeid in _collected]
    summary = {status: sum(item["status"] == status for item in tests)
               for status in ("passed", "failed", "skipped", "pending", "other")}
    summary.update(tests=len(tests), start=_started, stop=int(time.time() * 1000))
    payload = {"results": {"tool": {"name": "pytest", "version": pytest.__version__}, "summary": summary, "tests": tests}}
    Path("/logs/verifier/ctrf.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
