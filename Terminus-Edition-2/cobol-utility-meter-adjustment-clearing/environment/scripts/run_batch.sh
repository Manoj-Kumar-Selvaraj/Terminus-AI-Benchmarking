#!/bin/bash
set -euo pipefail
mkdir -p /app/build /app/out
cobc -x -free -O2 -o /app/build/meter_adjust_reconcile /app/src/meter_adjust_reconcile.cbl
/app/build/meter_adjust_reconcile
