#!/bin/bash
# Oracle, verifier, empty and FIFO runs in Docker; evidence copied out with docker cp.
export PATH=$HOME/.local/bin:$HOME/.local/lima/bin:$PATH DOCKER_HOST=unix://$HOME/.colima/default/docker.sock
T=/Users/adnananwar/Desktop/laraib/turing/tasks/engineering-sciences/civil-engineering/frame-vibration-audit
E=/Users/adnananwar/Desktop/laraib/turing/tbScience/frame-vibration-audit-dev/evidence
mkdir -p "$E"
cd "$T" || exit 1
docker build -q -t fv-env environment/ && docker build -q -t fv-tests tests/ && echo built
docker rm -f fv-oracle fv-verify fv-empty fv-fifo >/dev/null 2>&1
/usr/bin/time -p docker run --name fv-oracle -v "$T/solution:/solution:ro" fv-env bash /solution/solve.sh > "$E/oracle_run.log" 2>&1; echo "exit $?" >> "$E/oracle_run.log"
rm -rf "$E/results"; docker cp fv-oracle:/root/results "$E/results"; cp "$E/results/diagnosis.json" "$E/oracle_diagnosis.json"
docker create --name fv-verify fv-tests bash /tests/test.sh >/dev/null; docker cp "$E/results/." fv-verify:/root/results/
/usr/bin/time -p docker start -a fv-verify > "$E/verifier_final.log" 2>&1; echo "exit $?" >> "$E/verifier_final.log"
docker cp fv-verify:/logs/verifier/reward.txt "$E/reward_final.txt"; docker cp fv-verify:/logs/verifier/ctrf.json "$E/ctrf_final.json"
docker run --name fv-empty fv-tests bash /tests/test.sh > "$E/verifier_empty.log" 2>&1; echo "exit $?" >> "$E/verifier_empty.log"
docker cp fv-empty:/logs/verifier/reward.txt "$E/reward_empty.txt"
docker create --name fv-fifo fv-tests bash /tests/test.sh >/dev/null
rm -rf "$E/fifo"; mkdir "$E/fifo"; mkfifo "$E/fifo/framedyn.py"; echo "{}" > "$E/fifo/base_case_report.json"; echo "{}" > "$E/fifo/diagnosis.json"
docker cp "$E/fifo/." fv-fifo:/root/results/
docker start -a fv-fifo > "$E/verifier_fifo.log" 2>&1; echo "exit $?" >> "$E/verifier_fifo.log"
docker cp fv-fifo:/logs/verifier/reward.txt "$E/reward_fifo.txt"
rm -rf "$E/fifo"
echo DOCKER_CHAIN_DONE
