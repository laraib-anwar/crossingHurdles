#!/bin/bash
set -euo pipefail
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
cd /root
mkdir -p /root/results
cp /solution/cabletree.py /root/results/cabletree.py
python /root/results/cabletree.py --neuron /root/data/neurons/model_01.json --output /root/results/base_case_report.json
# the diagnosis is computed at run time by comparing the legacy script with the program
python /solution/diagnose.py --program /root/results/cabletree.py --legacy /root/data/legacy/cableprop.py \
    --neurons /root/data/neurons --output /root/results/diagnosis.json
