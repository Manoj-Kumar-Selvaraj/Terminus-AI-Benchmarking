#!/bin/bash
set -euo pipefail
mkdir -p /app/build /app/out
cobc -x -free -O2 -o /app/build/claim_denial_reconcile /app/src/claim_denial_reconcile.cbl
/app/build/claim_denial_reconcile
