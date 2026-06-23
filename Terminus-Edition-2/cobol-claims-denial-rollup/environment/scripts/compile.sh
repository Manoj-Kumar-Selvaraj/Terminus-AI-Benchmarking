#!/usr/bin/env bash
set -euo pipefail

mkdir -p /app/build
cobc -x -free -O2 -o /app/build/claim_rollup /app/src/claim_rollup.cbl
