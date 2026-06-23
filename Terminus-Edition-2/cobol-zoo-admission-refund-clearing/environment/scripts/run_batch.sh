#!/bin/bash
set -euo pipefail
mkdir -p /app/build /app/out
cobc -x -free -O2 -o /app/build/zoo_refund_reconcile /app/src/zoo_refund_reconcile.cbl
/app/build/zoo_refund_reconcile
