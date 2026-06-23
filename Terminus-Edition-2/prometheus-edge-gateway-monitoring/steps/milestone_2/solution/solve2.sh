#!/usr/bin/env bash
set -Eeuo pipefail
cd /app
cp "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/edge_metrics.py.m2" /app/tools/edge_metrics.py
chmod +x /app/tools/edge_metrics.py
python3 -m py_compile /app/tools/edge_metrics.py
