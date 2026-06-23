#!/bin/bash
set -euo pipefail
mkdir -p /app/build /app/out
cobc -x -free -O2 -o /app/build/laundry_credit_reconcile /app/src/laundry_credit_reconcile.cbl
/app/build/laundry_credit_reconcile
