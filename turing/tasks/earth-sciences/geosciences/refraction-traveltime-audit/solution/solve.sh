#!/bin/bash
set -euo pipefail
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
cd /root
mkdir -p /root/results
cp /solution/raytimes.py /root/results/raytimes.py
python /root/results/raytimes.py --model /root/data/models/model_01.json --output /root/results/base_case_report.json
# the diagnosis is computed at run time by comparing the legacy script with the program
python /solution/diagnose.py --program /root/results/raytimes.py --legacy /root/data/legacy/ttcurve.py \
    --models /root/data/models --output /root/results/diagnosis.json
