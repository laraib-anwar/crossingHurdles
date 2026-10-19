#!/bin/bash
set -euo pipefail
cd /root
python3 /solution/solve.py /root/results/predictions.json /root/results/cure_program.json
