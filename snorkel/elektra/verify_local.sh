#!/bin/bash
# Run a task's hidden tests locally, the way /review's oracle does, before pushing.
#   verify_local.sh <path to tasks/<slug>> [extra.patch ...]
# Prints the reward for the starting code (expect F2P 0/N, P2P all), for the reference
# solution (expect reward 1), and for any extra patches you pass (mutants: expect reward 0).
# Needs Colima running (see the tbscience-toolchain memory). Logs go to ~/elektra/verify-runs/.
set -u
export PATH=$HOME/.local/bin:$HOME/.local/lima/bin:$PATH DOCKER_HOST=unix://$HOME/.colima/default/docker.sock
T=$(cd "$1" && pwd); shift
colima status >/dev/null 2>&1 || colima start --vm-type vz --cpu 3 --memory 4 --disk 40 >/dev/null 2>&1
TAG=verify-$(basename "$T" | tr 'A-Z' 'a-z')
docker build -q -t "$TAG" "$T/tests" >/dev/null || { echo "tests image build failed"; exit 1; }
RUN=$HOME/elektra/verify-runs/$(date +%Y%m%d-%H%M%S); mkdir -p "$RUN/patches"
cp "$T/solution/fix.patch" "$RUN/patches/solution.patch"
for p in "$@"; do cp "$p" "$RUN/patches/$(basename "$p")"; done
for mode in base $(cd "$RUN/patches" && ls); do
  mkdir -p "$RUN/$mode"
  if [ "$mode" = base ]; then CMD='bash /tests/test.sh'; else CMD="cd /app && patch -p1 -s < /p/$mode && bash /tests/test.sh"; fi
  docker run --rm --network none -v "$RUN/patches:/p:ro" -v "$RUN/$mode:/logs/verifier" "$TAG" bash -c "$CMD" > "$RUN/$mode.out" 2>&1
  echo "$mode: $(cat "$RUN/$mode/reward.json" 2>/dev/null || echo 'no reward.json, see '"$RUN/$mode.out")"
done
# which tests failed, per run (base is expected to fail every f2p test)
python3 - "$RUN" <<'EOF'
import json, os, sys
run = sys.argv[1]
for d in sorted(os.listdir(run)):
    f = os.path.join(run, d, "ctrf.json")
    if d in ("base", "patches") or not os.path.exists(f):
        continue
    bad = [t["name"] for t in json.load(open(f))["results"]["tests"] if t["status"] != "passed"]
    print(f"{d} failing: {bad if bad else 'none'}")
EOF
