#!/bin/bash
set -euo pipefail
mkdir -p /app/build /app/out
cobc -x -free -O2 -o /app/build/scooter_surcharge_reconcile /app/src/scooter_surcharge_reconcile.cbl
/app/build/scooter_surcharge_reconcile
