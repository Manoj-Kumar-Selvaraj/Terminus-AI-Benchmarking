#!/bin/bash
set -euo pipefail
mkdir -p /app/build /app/out
cobc -x -free -O2 -o /app/build/league_fee_reversal_reconcile /app/src/league_fee_reversal_reconcile.cbl
/app/build/league_fee_reversal_reconcile
