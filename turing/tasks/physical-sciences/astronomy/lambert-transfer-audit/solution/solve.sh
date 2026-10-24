#!/bin/bash
set -euo pipefail
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
cd /root
mkdir -p /root/results
cp /solution/lambert.py /root/results/lambert.py
python /root/results/lambert.py --system /root/data/systems/model_01.json --output /root/results/base_case_report.json
# the diagnosis is computed at run time by comparing the legacy script with the program
python /solution/diagnose.py --program /root/results/lambert.py --legacy /root/data/legacy/porkchop.py \
    --systems /root/data/systems --output /root/results/diagnosis.json
