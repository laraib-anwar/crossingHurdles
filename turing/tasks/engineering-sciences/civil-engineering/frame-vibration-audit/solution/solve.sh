#!/bin/bash
set -euo pipefail
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
cd /root
mkdir -p /root/results
cp /solution/framedyn.py /root/results/framedyn.py
python /root/results/framedyn.py --frame /root/data/frames/model_01.json --output /root/results/base_case_report.json
# the diagnosis is computed at run time by comparing the legacy script with the program
python /solution/diagnose.py --program /root/results/framedyn.py --legacy /root/data/legacy/framefreq.py \
    --frames /root/data/frames --output /root/results/diagnosis.json
