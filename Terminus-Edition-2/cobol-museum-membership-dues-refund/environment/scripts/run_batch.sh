#!/bin/bash
set -euo pipefail
mkdir -p /app/build /app/out
cobc -x -free -O2 -o /app/build/membership_refund_reconcile /app/src/membership_refund_reconcile.cbl
/app/build/membership_refund_reconcile
