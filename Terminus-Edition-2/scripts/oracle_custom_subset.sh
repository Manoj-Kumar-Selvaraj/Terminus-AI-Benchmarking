#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/Revision-ChatGpt/revision_batch_logs/oracle_custom_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1

TASKS=(
  go-conference-sponsor-rebate-matcher
  cobol-vendor-return-settlement
  go-marketplace-payout-matcher
  cobol-utility-meter-adjustment-clearing
  ruby-theater-booking-refund-matcher
  go-hotel-reservation-credit-reconciler
  go-waterpark-pass-refund-matcher
  go-parking-citation-credit-matcher
  go-logistics-accessorial-credit-matcher
  ruby-hotel-night-audit-chargeback-router
)

pass=0
fail=0
for t in "${TASKS[@]}"; do
  echo "===== ORACLE $t ====="
  if bash "$ROOT/scripts/terminus2_cli.sh" oracle "$t"; then
    ((pass++)) || true
  else
    ((fail++)) || true
  fi
done
echo "=== ORACLE CUSTOM SUBSET pass=$pass fail=$fail log=$LOG ==="
