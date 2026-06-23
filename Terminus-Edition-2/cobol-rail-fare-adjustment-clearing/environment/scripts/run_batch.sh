#!/bin/bash
set -euo pipefail
mkdir -p /app/build /app/out
cobc -x -free -O2 -o /app/build/fare_adjust_reconcile /app/src/fare_adjust_reconcile.cbl
/app/build/fare_adjust_reconcile
