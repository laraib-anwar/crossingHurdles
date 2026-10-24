#!/bin/bash
# Oracle, verifier, empty and FIFO runs in Docker; evidence copied out with docker cp.
export PATH=$HOME/.local/bin:$HOME/.local/lima/bin:$PATH DOCKER_HOST=unix://$HOME/.colima/default/docker.sock
T=/Users/adnananwar/Desktop/laraib/turing/tasks/physical-sciences/physics/heterostructure-tunneling-audit
E=/Users/adnananwar/Desktop/laraib/turing/tbScience/heterostructure-tunneling-audit-dev/evidence
mkdir -p "$E"
cd "$T" || exit 1
docker build -q -t ht-env environment/ && docker build -q -t ht-tests tests/ && echo built
docker rm -f ht-oracle ht-verify ht-empty ht-fifo >/dev/null 2>&1
/usr/bin/time -p docker run --name ht-oracle -v "$T/solution:/solution:ro" ht-env bash /solution/solve.sh > "$E/oracle_run.log" 2>&1; echo "exit $?" >> "$E/oracle_run.log"
rm -rf "$E/results"; docker cp ht-oracle:/root/results "$E/results"; cp "$E/results/diagnosis.json" "$E/oracle_diagnosis.json"
docker create --name ht-verify ht-tests bash /tests/test.sh >/dev/null; docker cp "$E/results/." ht-verify:/root/results/
/usr/bin/time -p docker start -a ht-verify > "$E/verifier_final.log" 2>&1; echo "exit $?" >> "$E/verifier_final.log"
docker cp ht-verify:/logs/verifier/reward.txt "$E/reward_final.txt"; docker cp ht-verify:/logs/verifier/ctrf.json "$E/ctrf_final.json"
docker run --name ht-empty ht-tests bash /tests/test.sh > "$E/verifier_empty.log" 2>&1; echo "exit $?" >> "$E/verifier_empty.log"
docker cp ht-empty:/logs/verifier/reward.txt "$E/reward_empty.txt"
docker create --name ht-fifo ht-tests bash /tests/test.sh >/dev/null
rm -rf "$E/fifo"; mkdir "$E/fifo"; mkfifo "$E/fifo/hetero.py"; echo "{}" > "$E/fifo/base_case_report.json"; echo "{}" > "$E/fifo/diagnosis.json"
docker cp "$E/fifo/." ht-fifo:/root/results/
docker start -a ht-fifo > "$E/verifier_fifo.log" 2>&1; echo "exit $?" >> "$E/verifier_fifo.log"
docker cp ht-fifo:/logs/verifier/reward.txt "$E/reward_fifo.txt"
rm -rf "$E/fifo"
echo DOCKER_CHAIN_DONE
