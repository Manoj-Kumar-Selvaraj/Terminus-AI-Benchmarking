#!/usr/bin/env bash
set -euo pipefail
head -n 3 /app/data/records.csv /app/data/adjustments.csv 2>/dev/null || true
