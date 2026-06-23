#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TASKS=(
  cobol-escrow-return-reconciliation
  cobol-wire-return-settlement
  go-carwash-subscription-rebate-matcher
  go-catering-order-adjustment-matcher
  go-logistics-accessorial-credit-matcher
  go-travel-booking-adjustment-matcher
  go-pharmacy-coldchain-exception-router
  ruby-energy-demand-response-settler
)
pass=0
fail=0
for t in "${TASKS[@]}"; do
  echo "===== ORACLE $t ====="
  if bash "$ROOT/scripts/terminus2_cli.sh" oracle "$ROOT/$t"; then
    pass=$((pass + 1))
  else
    fail=$((fail + 1))
    echo "FAILED $t"
  fi
done
echo "=== RETRY pass=$pass fail=$fail ==="
