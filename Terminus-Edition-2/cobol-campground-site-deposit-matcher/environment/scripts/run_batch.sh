#!/usr/bin/env bash
set -euo pipefail
cd /app
mkdir -p /app/build /app/out
cobc -x -free -O2 -o /app/build/camp_deposit_reconcile /app/src/camp_deposit_reconcile.cbl
/app/build/camp_deposit_reconcile
