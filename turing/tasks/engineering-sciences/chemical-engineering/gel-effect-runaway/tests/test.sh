#!/bin/bash
set -euo pipefail
# Sole writer of /logs/verifier/reward.txt. The reward is written as 0 before anything else, so
# a crash or an infrastructure error at any later point still leaves a valid binary result.
#   pytest exit 0 (every grading test passed)    -> reward 1
#   pytest exit 1 (at least one test failed)     -> reward 0
#   anything else (missing file, truth or plant hash mismatch, pytest exit 2-5,
#   rejected CTRF report, unexpected command failure) -> reward stays 0, exit 2
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
rm -f /logs/verifier/ctrf.json
trap 'echo "infrastructure error: unexpected failure at line $LINENO" >&2; exit 2' ERR
for f in /tests/test_state.py /tests/decide.py /tests/plant.py /tests/truth/expected.json \
         /tests/truth/design.json /tests/truth/SHA256SUMS.txt; do
    if [ ! -f "$f" ]; then
        echo "infrastructure error: missing $f" >&2
        exit 2
    fi
done
if ! (cd /tests && sha256sum --check --strict --status truth/SHA256SUMS.txt); then
    echo "infrastructure error: truth or plant model does not match its recorded hash" >&2
    exit 2
fi
status=0
pytest -p no:cacheprovider --ctrf /logs/verifier/ctrf.json /tests/test_state.py -rA || status=$?
if [ "$status" -ne 0 ] && [ "$status" -ne 1 ]; then
    echo "infrastructure error: pytest exit status $status" >&2
    exit 2
fi
# The CTRF report must list exactly the expected tests, none skipped, consistent with $status.
if ! python3 -I -B /tests/decide.py "$status" /logs/verifier/ctrf.json; then
    echo "infrastructure error: CTRF report rejected" >&2
    exit 2
fi
if [ "$status" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
