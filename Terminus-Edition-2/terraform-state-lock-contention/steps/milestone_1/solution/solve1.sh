#!/usr/bin/env bash
set -Eeuo pipefail
cd /app
cp "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/tf_state_sim.py.m1" /app/tools/tf_state_sim.py
chmod +x /app/tools/tf_state_sim.py
python3 -m py_compile /app/tools/tf_state_sim.py
