#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/build
cobc -x -free -o /app/build/batch /app/src/voucher_returns.cbl