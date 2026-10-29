#!/bin/bash
set -euo pipefail
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
cd /root
mkdir -p /root/results
cp /solution/regimen.py /root/results/regimen.py
python /root/results/regimen.py --regimen /root/data/regimens/model_01.json --output /root/results/base_case_report.json
# the diagnosis is computed at run time by comparing the legacy script with the program
python /solution/diagnose.py --program /root/results/regimen.py --legacy /root/data/legacy/regimencalc.py \
    --regimens /root/data/regimens --output /root/results/diagnosis.json
