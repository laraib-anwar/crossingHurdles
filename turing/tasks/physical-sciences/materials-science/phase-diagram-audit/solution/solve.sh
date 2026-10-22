#!/bin/bash
set -euo pipefail
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
cd /root
mkdir -p /root/results
cp /solution/phasediagram.py /root/results/phasediagram.py
python /root/results/phasediagram.py --system /root/data/systems/model_01.json --output /root/results/base_case_report.json
# the diagnosis is computed at run time by comparing the legacy script with the program
python /solution/diagnose.py --program /root/results/phasediagram.py --legacy /root/data/legacy/tangentdiag.py \
    --systems /root/data/systems --output /root/results/diagnosis.json
