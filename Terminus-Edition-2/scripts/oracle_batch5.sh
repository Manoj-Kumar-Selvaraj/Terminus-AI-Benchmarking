#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
tasks=(
  go-marketplace-payout-matcher
  go-travel-booking-adjustment-matcher
  go-utility-refund-reconciler
  go-warehouse-pickwave-shortage-matcher
  go-waterpark-pass-refund-matcher
)
for t in "${tasks[@]}"; do
  echo "==== ORACLE $t ===="
  bash scripts/oracle_cumulative_go.sh "$t" 2>&1 | tail -25
  echo
done
