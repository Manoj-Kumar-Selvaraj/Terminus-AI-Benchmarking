#!/bin/bash
set -euo pipefail
mkdir -p /app/build /app/out
cobc -x -free -O2 -o /app/build/parcel_credit_reconcile /app/src/parcel_credit_reconcile.cbl
/app/build/parcel_credit_reconcile
