#!/bin/bash
set -euo pipefail
wc -l /app/data/lift_sessions.csv /app/data/gate_releases.csv /app/config/windows.csv
