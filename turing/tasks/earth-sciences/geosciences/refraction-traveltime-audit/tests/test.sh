#!/bin/bash
set -euo pipefail
mkdir -p /logs/verifier
# Fail-safe: a reward of 0 exists before any grading step; finalize_reward.py overwrites it with 1 on success.
echo 0 > /logs/verifier/reward.txt
# The candidate program runs as uid 10001. Host bind mounts may otherwise expose a writable
# reward directory, letting a detached child rename and replace the final reward.
chmod 700 /logs/verifier
# Candidate code may write only its fresh per-call working directory. Shared temporary and home
# locations must not carry state between invocations.
chown root:root /home/runner
chmod 700 /tmp /var/tmp /home/runner /dev/shm /dev/mqueue /run/lock 2>/dev/null || true
rm -f /logs/verifier/ctrf.json
python -c 'import os; os.setgroups([]); os.setgid(10001); os.setuid(10001); assert all(not os.access(p, os.W_OK) for p in ["/logs/verifier", "/tmp", "/var/tmp", "/home/runner", "/dev/shm", "/dev/mqueue", "/run/lock"] if os.path.exists(p)), "candidate can write persistent verifier state"'
pytest_status=0
pytest -rA --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py || pytest_status=$?
# Interrupted collection, internal errors, usage errors and empty collections are infrastructure
# failures: preserve the diagnostics without issuing a score.
if (( pytest_status > 1 )); then
    exit "$pytest_status"
fi
python /tests/finalize_reward.py "$pytest_status"
