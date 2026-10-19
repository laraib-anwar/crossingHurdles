#!/bin/bash
set -euo pipefail
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
cd /root
mkdir -p /root/results
cp /solution/ixfront.py /root/results/ixfront.py
python /root/results/ixfront.py --recipe /root/data/recipes/service_01.json --output /root/results/base_case_report.json
# the diagnosis is computed at run time by comparing the legacy script with the program
python /solution/diagnose.py --program /root/results/ixfront.py --legacy /root/data/legacy/ixbreak.py \
    --recipes /root/data/recipes --output /root/results/diagnosis.json
