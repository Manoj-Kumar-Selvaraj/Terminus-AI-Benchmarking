#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MILESTONE="1"
if grep -q 'CALL "SYSTEM" USING "python3' /app/src/camp_deposit_reconcile.cbl 2>/dev/null; then
  :
else
  if [[ "$MILESTONE" != "1" ]] && ! grep -q 'NORMALIZE-SITE' /app/src/camp_deposit_reconcile.cbl 2>/dev/null; then
    bash "/steps/milestone_1/solution/solve1.sh"
  fi
fi
cp "$SCRIPT_DIR/oracle_m1.cbl" /app/src/camp_deposit_reconcile.cbl
/app/scripts/run_batch.sh
