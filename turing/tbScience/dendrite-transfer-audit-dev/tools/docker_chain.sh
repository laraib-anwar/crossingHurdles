#!/bin/bash
# Oracle, verifier, empty and FIFO runs in Docker; evidence copied out with docker cp.
export PATH=$HOME/.local/bin:$HOME/.local/lima/bin:$PATH DOCKER_HOST=unix://$HOME/.colima/default/docker.sock
T=/Users/adnananwar/Desktop/laraib/turing/tasks/life-sciences/neuroscience/dendrite-transfer-audit
E=/Users/adnananwar/Desktop/laraib/turing/tbScience/dendrite-transfer-audit-dev/evidence
mkdir -p "$E"
cd "$T" || exit 1
docker build -q -t dt-env environment/ && docker build -q -t dt-tests tests/ && echo built
docker rm -f dt-oracle dt-verify dt-empty dt-fifo >/dev/null 2>&1
/usr/bin/time -p docker run --name dt-oracle -v "$T/solution:/solution:ro" dt-env bash /solution/solve.sh > "$E/oracle_run.log" 2>&1; echo "exit $?" >> "$E/oracle_run.log"
rm -rf "$E/results"; docker cp dt-oracle:/root/results "$E/results"; cp "$E/results/diagnosis.json" "$E/oracle_diagnosis.json"
docker create --name dt-verify dt-tests bash /tests/test.sh >/dev/null; docker cp "$E/results/." dt-verify:/root/results/
/usr/bin/time -p docker start -a dt-verify > "$E/verifier_final.log" 2>&1; echo "exit $?" >> "$E/verifier_final.log"
docker cp dt-verify:/logs/verifier/reward.txt "$E/reward_final.txt"; docker cp dt-verify:/logs/verifier/ctrf.json "$E/ctrf_final.json"
docker run --name dt-empty dt-tests bash /tests/test.sh > "$E/verifier_empty.log" 2>&1; echo "exit $?" >> "$E/verifier_empty.log"
docker cp dt-empty:/logs/verifier/reward.txt "$E/reward_empty.txt"
docker create --name dt-fifo dt-tests bash /tests/test.sh >/dev/null
rm -rf "$E/fifo"; mkdir "$E/fifo"; mkfifo "$E/fifo/cabletree.py"; echo "{}" > "$E/fifo/base_case_report.json"; echo "{}" > "$E/fifo/diagnosis.json"
docker cp "$E/fifo/." dt-fifo:/root/results/
docker start -a dt-fifo > "$E/verifier_fifo.log" 2>&1; echo "exit $?" >> "$E/verifier_fifo.log"
docker cp dt-fifo:/logs/verifier/reward.txt "$E/reward_fifo.txt"
rm -rf "$E/fifo"
echo DOCKER_CHAIN_DONE
