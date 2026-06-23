#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if grep -q 'FUNCTION UPPER-CASE(CAL-STATE(CAL-IDX))' /app/src/scooter_surcharge_reconcile.cbl 2>/dev/null \
   && ! grep -q 'LOAD-REASONS' /app/src/scooter_surcharge_reconcile.cbl 2>/dev/null; then
  /app/scripts/run_batch.sh
  exit 0
fi
cp "$SCRIPT_DIR/oracle_m3.cbl" /app/src/scooter_surcharge_reconcile.cbl
/app/scripts/run_batch.sh
