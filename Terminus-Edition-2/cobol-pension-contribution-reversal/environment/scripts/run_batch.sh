#!/bin/bash
set -euo pipefail
mkdir -p /app/build /app/out
cobc -x -free -O2 -o /app/build/pension_reversal_reconcile /app/src/pension_reversal_reconcile.cbl
/app/build/pension_reversal_reconcile
