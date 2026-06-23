#!/bin/bash
set -euo pipefail
mkdir -p /app/build /app/out
cobc -x -free -O2 -o /app/build/storage_credit_reconcile /app/src/storage_credit_reconcile.cbl
/app/build/storage_credit_reconcile
