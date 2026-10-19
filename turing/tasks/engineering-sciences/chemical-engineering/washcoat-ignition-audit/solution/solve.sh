#!/bin/bash
set -euo pipefail
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
cd /root
mkdir -p /root/results
cp /solution/lightoff_exact.py /root/results/lightoff_exact.py
python /root/results/lightoff_exact.py --recipe /root/data/recipes/lightoff_01.json --output /root/results/base_case_report.json
# the diagnosis is computed at run time by comparing the legacy script with the program
python /solution/diagnose.py --program /root/results/lightoff_exact.py --legacy /root/data/legacy/lightoff.py \
    --recipes /root/data/recipes --output /root/results/diagnosis.json
