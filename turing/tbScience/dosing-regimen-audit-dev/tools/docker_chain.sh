#!/bin/bash
# Oracle, verifier, empty and FIFO runs in Docker; evidence copied out with docker cp.
export PATH=$HOME/.local/bin:$HOME/.local/lima/bin:$PATH DOCKER_HOST=unix://$HOME/.colima/default/docker.sock
T=/Users/adnananwar/Desktop/laraib/turing/tasks/life-sciences/pharmacology/dosing-regimen-audit
E=/Users/adnananwar/Desktop/laraib/turing/tbScience/dosing-regimen-audit-dev/evidence
mkdir -p "$E"
cd "$T" || exit 1
docker build -q -t dr-env environment/ && docker build -q -t dr-tests tests/ && echo built
docker rm -f dr-oracle dr-verify dr-empty dr-fifo >/dev/null 2>&1
/usr/bin/time -p docker run --name dr-oracle -v "$T/solution:/solution:ro" dr-env bash /solution/solve.sh > "$E/oracle_run.log" 2>&1; echo "exit $?" >> "$E/oracle_run.log"
rm -rf "$E/results"; docker cp dr-oracle:/root/results "$E/results"; cp "$E/results/diagnosis.json" "$E/oracle_diagnosis.json"
docker create --name dr-verify dr-tests bash /tests/test.sh >/dev/null; docker cp "$E/results/." dr-verify:/root/results/
/usr/bin/time -p docker start -a dr-verify > "$E/verifier_final.log" 2>&1; echo "exit $?" >> "$E/verifier_final.log"
docker cp dr-verify:/logs/verifier/reward.txt "$E/reward_final.txt"; docker cp dr-verify:/logs/verifier/ctrf.json "$E/ctrf_final.json"
docker run --name dr-empty dr-tests bash /tests/test.sh > "$E/verifier_empty.log" 2>&1; echo "exit $?" >> "$E/verifier_empty.log"
docker cp dr-empty:/logs/verifier/reward.txt "$E/reward_empty.txt"
docker create --name dr-fifo dr-tests bash /tests/test.sh >/dev/null
rm -rf "$E/fifo"; mkdir "$E/fifo"; mkfifo "$E/fifo/regimen.py"; echo "{}" > "$E/fifo/base_case_report.json"; echo "{}" > "$E/fifo/diagnosis.json"
docker cp "$E/fifo/." dr-fifo:/root/results/
docker start -a dr-fifo > "$E/verifier_fifo.log" 2>&1; echo "exit $?" >> "$E/verifier_fifo.log"
docker cp dr-fifo:/logs/verifier/reward.txt "$E/reward_fifo.txt"
rm -rf "$E/fifo"
echo DOCKER_CHAIN_DONE
