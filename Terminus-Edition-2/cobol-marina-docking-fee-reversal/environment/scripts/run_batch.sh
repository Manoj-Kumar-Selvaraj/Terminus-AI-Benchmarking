#!/bin/bash
set -euo pipefail
mkdir -p /app/build /app/out
cobc -x -free -O2 -o /app/build/docking_reversal_reconcile /app/src/docking_reversal_reconcile.cbl
/app/build/docking_reversal_reconcile
