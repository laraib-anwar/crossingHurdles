#!/bin/bash
# Oracle, verifier, empty and FIFO runs in Docker; evidence copied out with docker cp.
export PATH=$HOME/.local/bin:$HOME/.local/lima/bin:$PATH DOCKER_HOST=unix://$HOME/.colima/default/docker.sock
T=/Users/adnananwar/Desktop/laraib/turing/tasks/physical-sciences/astronomy/lambert-transfer-audit
E=/Users/adnananwar/Desktop/laraib/turing/tbScience/lambert-transfer-audit-dev/evidence
mkdir -p "$E"
cd "$T" || exit 1
docker build -q -t lt-env environment/ && docker build -q -t lt-tests tests/ && echo built
docker rm -f lt-oracle lt-verify lt-empty lt-fifo >/dev/null 2>&1
/usr/bin/time -p docker run --name lt-oracle -v "$T/solution:/solution:ro" lt-env bash /solution/solve.sh > "$E/oracle_run.log" 2>&1; echo "exit $?" >> "$E/oracle_run.log"
rm -rf "$E/results"; docker cp lt-oracle:/root/results "$E/results"; cp "$E/results/diagnosis.json" "$E/oracle_diagnosis.json"
docker create --name lt-verify lt-tests bash /tests/test.sh >/dev/null; docker cp "$E/results/." lt-verify:/root/results/
/usr/bin/time -p docker start -a lt-verify > "$E/verifier_final.log" 2>&1; echo "exit $?" >> "$E/verifier_final.log"
docker cp lt-verify:/logs/verifier/reward.txt "$E/reward_final.txt"; docker cp lt-verify:/logs/verifier/ctrf.json "$E/ctrf_final.json"
docker run --name lt-empty lt-tests bash /tests/test.sh > "$E/verifier_empty.log" 2>&1; echo "exit $?" >> "$E/verifier_empty.log"
docker cp lt-empty:/logs/verifier/reward.txt "$E/reward_empty.txt"
docker create --name lt-fifo lt-tests bash /tests/test.sh >/dev/null
rm -rf "$E/fifo"; mkdir "$E/fifo"; mkfifo "$E/fifo/lambert.py"; echo "{}" > "$E/fifo/base_case_report.json"; echo "{}" > "$E/fifo/diagnosis.json"
docker cp "$E/fifo/." lt-fifo:/root/results/
docker start -a lt-fifo > "$E/verifier_fifo.log" 2>&1; echo "exit $?" >> "$E/verifier_fifo.log"
docker cp lt-fifo:/logs/verifier/reward.txt "$E/reward_fifo.txt"
rm -rf "$E/fifo"
echo DOCKER_CHAIN_DONE
