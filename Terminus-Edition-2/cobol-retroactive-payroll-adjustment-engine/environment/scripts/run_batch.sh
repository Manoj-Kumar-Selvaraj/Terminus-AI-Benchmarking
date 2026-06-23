#!/usr/bin/env bash
set -Eeuo pipefail
mkdir -p /app/out
python3 /app/src/payroll_runtime.py
