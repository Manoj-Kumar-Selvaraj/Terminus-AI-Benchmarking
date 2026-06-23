#!/bin/bash
set -euo pipefail
mkdir -p /app/build /app/out
cobc -x -free -O2 -o /app/build/session_credit_reconcile /app/src/session_credit_reconcile.cbl
/app/build/session_credit_reconcile
