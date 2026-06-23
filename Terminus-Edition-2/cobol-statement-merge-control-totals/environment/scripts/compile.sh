#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/build
cobc -x -free -I /app/copybooks -o /app/build/batch /app/src/stmt_merge.cbl
